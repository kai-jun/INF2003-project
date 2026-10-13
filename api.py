import os
import logging
import queue
import sqlite3
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from pydantic import BaseModel, Field

APP_TITLE = "Last-Mile Delivery API"
DEFAULT_SQLITE_DB_PATH = os.path.join(os.path.dirname(__file__), "delivery.db")
DEFAULT_MONGO_URI = "mongodb://localhost:27017/"
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SQLiteConnectionPool:
    def __init__(self, database_path: str, max_connections: int = 5):
        self.database_path = database_path
        self.max_connections = max_connections
        self.connections: queue.LifoQueue[sqlite3.Connection] = queue.LifoQueue(max_connections)
        self.created_connections = 0
        self.lock = threading.Lock()
        self.closed = False

    def _create_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.database_path,
            timeout=10,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def acquire(self) -> sqlite3.Connection:
        if self.closed:
            raise RuntimeError("SQLite connection pool is closed")
        try:
            return self.connections.get_nowait()
        except queue.Empty:
            with self.lock:
                if self.closed:
                    raise RuntimeError("SQLite connection pool is closed")
                if self.created_connections < self.max_connections:
                    self.created_connections += 1
                    try:
                        return self._create_connection()
                    except Exception:
                        self.created_connections -= 1
                        raise
        return self.connections.get()

    def release(self, conn: sqlite3.Connection) -> None:
        if self.closed:
            conn.close()
            return
        self.connections.put(conn)

    def close(self) -> None:
        self.closed = True
        while True:
            try:
                self.connections.get_nowait().close()
            except queue.Empty:
                break


@asynccontextmanager
async def lifespan(application: FastAPI):
    application.state.sqlite_pool = SQLiteConnectionPool(get_sqlite_db_path())
    try:
        yield
    finally:
        application.state.sqlite_pool.close()
        mongo_client = getattr(application.state, "mongo_client", None)
        if mongo_client is not None:
            mongo_client.close()
            application.state.mongo_client = None
            application.state.mongo_client_uri = None

app = FastAPI(
    title=APP_TITLE,
    lifespan=lifespan,
    redoc_url=None,
    swagger_ui_parameters={"syntaxHighlight": False},
)


class OrderCreate(BaseModel):
    order_id: str = Field(min_length=1)
    courier_id: str | None = None
    aoi_id: str | None = None
    accept_time: str | None = None
    delivery_time: str | None = None
    ds: str | None = None


class OrderUpdate(BaseModel):
    courier_id: str | None = None
    aoi_id: str | None = None
    accept_time: str | None = None
    delivery_time: str | None = None
    ds: str | None = None


def get_sqlite_db_path() -> str:
    return getattr(app.state, "sqlite_db_path", os.getenv("SQLITE_DB_PATH", DEFAULT_SQLITE_DB_PATH))


def get_mongo_uri() -> str:
    return getattr(app.state, "mongo_uri", os.getenv("MONGO_URI", DEFAULT_MONGO_URI))


@contextmanager
def get_connection():
    pool = getattr(app.state, "sqlite_pool", None)
    if pool is None:
        pool = SQLiteConnectionPool(get_sqlite_db_path())
        app.state.sqlite_pool = pool
    conn = pool.acquire()
    try:
        yield conn
    finally:
        pool.release(conn)


def parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format; use YYYY-MM-DD HH:MM:SS")


def order_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    order = dict(row)
    order["accept_time"] = order.get("accept_time")
    order["delivery_time"] = order.get("delivery_time")
    return order


def order_with_duration(row: sqlite3.Row) -> dict[str, Any]:
    order = order_to_dict(row)
    accept_time = parse_datetime(order.get("accept_time"))
    delivery_time = parse_datetime(order.get("delivery_time"))
    if accept_time is not None and delivery_time is not None:
        duration_hours = (delivery_time - accept_time).total_seconds() / 3600
        order["delivery_duration_hours"] = round(duration_hours, 4)
    else:
        order["delivery_duration_hours"] = None
    return order


def fetch_order(conn: sqlite3.Connection, order_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM \"ORDER\" WHERE order_id = ?",
        (order_id,),
    ).fetchone()


def row_count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


def get_mongo_client() -> MongoClient:
    uri = get_mongo_uri()
    client = getattr(app.state, "mongo_client", None)
    if client is None or getattr(app.state, "mongo_client_uri", None) != uri:
        if client is not None:
            client.close()
        client = MongoClient(uri, serverSelectionTimeoutMS=2000)
        app.state.mongo_client = client
        app.state.mongo_client_uri = uri
    return client


def get_mongo_collection():
    try:
        client = get_mongo_client()
        client.admin.command("ping")
        return client["lastmile"]["delivery_events"]
    except (PyMongoError, OSError):
        raise HTTPException(
            status_code=503,
            detail="MongoDB is unavailable. Start MongoDB or configure MONGO_URI.",
        ) from None


def get_tracking_collection():
    try:
        client = get_mongo_client()
        client.admin.command("ping")
        return client["lastmile"]["tracking_logs"]
    except (PyMongoError, OSError):
        raise HTTPException(
            status_code=503,
            detail="MongoDB is unavailable. Start MongoDB or configure MONGO_URI.",
        ) from None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/orders")
def list_orders() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM \"ORDER\" ORDER BY order_id"
        ).fetchall()
        return [order_with_duration(row) for row in rows]


@app.get("/orders/{order_id}")
def get_order(order_id: str) -> dict[str, Any]:
    with get_connection() as conn:
        row = fetch_order(conn, order_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Order not found")
        return order_with_duration(row)


@app.post("/orders", status_code=201)
def create_order(order: OrderCreate) -> dict[str, Any]:
    with get_connection() as conn:
        if fetch_order(conn, order.order_id) is not None:
            raise HTTPException(status_code=409, detail="Order already exists")

        conn.execute(
            "INSERT INTO \"ORDER\" (order_id, courier_id, aoi_id, accept_time, delivery_time, ds) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                order.order_id,
                order.courier_id,
                order.aoi_id,
                order.accept_time,
                order.delivery_time,
                order.ds,
            ),
        )
        conn.commit()

        row = fetch_order(conn, order.order_id)
        return order_with_duration(row)


@app.put("/orders/{order_id}")
def update_order(order_id: str, updates: OrderUpdate) -> dict[str, Any]:
    with get_connection() as conn:
        existing = fetch_order(conn, order_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Order not found")

        fields: dict[str, Any] = {}
        for field_name, value in updates.model_dump(exclude_none=True).items():
            fields[field_name] = value

        if not fields:
            return order_with_duration(existing)

        assignments = ", ".join(f'"{name}" = ?' for name in fields)
        values = list(fields.values()) + [order_id]
        conn.execute(
            f"UPDATE \"ORDER\" SET {assignments} WHERE order_id = ?",
            values,
        )
        conn.commit()

        row = fetch_order(conn, order_id)
        return order_with_duration(row)


@app.delete("/orders/{order_id}")
def delete_order(order_id: str) -> dict[str, str]:
    with get_connection() as conn:
        row = fetch_order(conn, order_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Order not found")

        conn.execute('DELETE FROM "ORDER" WHERE order_id = ?', (order_id,))
        conn.commit()
        return {"message": "Order deleted", "order_id": order_id}


@app.get("/couriers")
def list_couriers() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM COURIER ORDER BY courier_id").fetchall()
        return [dict(row) for row in rows]


@app.get("/couriers/{courier_id}/orders")
def orders_by_courier(courier_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM \"ORDER\" WHERE courier_id = ? ORDER BY order_id",
            (courier_id,),
        ).fetchall()
        return [order_with_duration(row) for row in rows]


@app.get("/orders/{order_id}/tracking")
def order_tracking_sql(order_id: str) -> dict[str, Any]:
    with get_connection() as conn:
        if fetch_order(conn, order_id) is None:
            raise HTTPException(status_code=404, detail="Order not found")

        locations = conn.execute(
            """
            SELECT 'accept' AS event_type, gps_time AS timestamp, latitude, longitude
            FROM ACCEPTANCE_LOCATION WHERE order_id = ?
            UNION ALL
            SELECT 'delivery' AS event_type, gps_time AS timestamp, latitude, longitude
            FROM DELIVERY_LOCATION WHERE order_id = ?
            ORDER BY timestamp
            """,
            (order_id, order_id),
        ).fetchall()

        return {
            "order_id": order_id,
            "locations": [dict(row) for row in locations],
        }


@app.get("/compare/tracking/{order_id}")
def compare_tracking(order_id: str) -> dict[str, Any]:
    sql_started = time.perf_counter()
    with get_connection() as conn:
        sql_rows = conn.execute(
            """
            SELECT o.order_id,
                   a.gps_time AS accept_timestamp,
                   a.latitude AS accept_latitude,
                   a.longitude AS accept_longitude,
                   d.gps_time AS delivery_timestamp,
                   d.latitude AS delivery_latitude,
                   d.longitude AS delivery_longitude
            FROM "ORDER" o
            LEFT JOIN ACCEPTANCE_LOCATION a ON a.order_id = o.order_id
            LEFT JOIN DELIVERY_LOCATION d ON d.order_id = o.order_id
            WHERE o.order_id = ?
            """,
            (order_id,),
        ).fetchall()
        sql_results = [dict(row) for row in sql_rows]
    sql_execution_time_ms = (time.perf_counter() - sql_started) * 1000

    mongo_started = time.perf_counter()
    query_values: list[str | int] = [order_id]
    if order_id.isdigit():
        query_values.append(int(order_id))
    collection = get_tracking_collection()
    mongo_results = list(
        collection.find({"order_id": {"$in": query_values}}).sort("timestamp", 1)
    )
    for event in mongo_results:
        event["_id"] = str(event["_id"])
    mongo_execution_time_ms = (time.perf_counter() - mongo_started) * 1000

    logger.info(
        "tracking comparison order_id=%s SQL=%.3fms MongoDB=%.3fms",
        order_id,
        sql_execution_time_ms,
        mongo_execution_time_ms,
    )
    return {
        "order_id": order_id,
        "sql": {
            "execution_time_ms": round(sql_execution_time_ms, 3),
            "results": sql_results,
        },
        "mongodb": {
            "execution_time_ms": round(mongo_execution_time_ms, 3),
            "results": mongo_results,
        },
    }


@app.get("/orders/{order_id}/events")
def order_tracking_mongo(order_id: str) -> dict[str, Any]:
    collection = get_mongo_collection()
    events = list(collection.find({"order_id": int(order_id) if order_id.isdigit() else order_id}).sort("timestamp", 1))
    for event in events:
        event["_id"] = str(event["_id"])
    return {"order_id": order_id, "events": events}


@app.get("/analytics/delivery-time")
def delivery_time_stats() -> dict[str, Any]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT accept_time, delivery_time FROM \"ORDER\" WHERE accept_time IS NOT NULL AND delivery_time IS NOT NULL"
        ).fetchall()

        durations = []
        for row in rows:
            accept_time = parse_datetime(row["accept_time"])
            delivery_time = parse_datetime(row["delivery_time"])
            if accept_time is not None and delivery_time is not None:
                durations.append((delivery_time - accept_time).total_seconds() / 3600)

        if not durations:
            return {"average_delivery_hours": 0.0, "order_count": 0}

        return {
            "average_delivery_hours": round(sum(durations) / len(durations), 4),
            "order_count": len(durations),
        }


@app.get("/analytics/courier-performance")
def courier_performance(
    limit: int = Query(default=10, ge=1)
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT c.courier_id,
                   COUNT(o.order_id) AS order_count,
                   ROUND(AVG((strftime('%s', o.delivery_time) - strftime('%s', o.accept_time)) / 3600), 4) AS avg_delivery_hours
            FROM COURIER c
            LEFT JOIN \"ORDER\" o ON o.courier_id = c.courier_id
            WHERE o.accept_time IS NOT NULL AND o.delivery_time IS NOT NULL
            GROUP BY c.courier_id
            ORDER BY avg_delivery_hours DESC, order_count DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


@app.get("/analytics/delayed-orders")
def delayed_orders() -> dict[str, list[dict[str, Any]]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT o.order_id, o.courier_id, o.aoi_id, o.accept_time, o.delivery_time,
                   CASE WHEN o.ds IS NOT NULL AND lower(o.ds) LIKE '%delay%' THEN 1 ELSE 0 END AS is_delayed
            FROM \"ORDER\" o
            WHERE o.ds IS NOT NULL
            ORDER BY o.order_id
            """
        ).fetchall()
        delayed = [
            {
                "order_id": row["order_id"],
                "courier_id": row["courier_id"],
                "aoi_id": row["aoi_id"],
                "accept_time": row["accept_time"],
                "delivery_time": row["delivery_time"],
            }
            for row in rows
            if row["is_delayed"] == 1
        ]
        return {"orders": delayed}


@app.exception_handler(HTTPException)
async def http_exception_handler(_, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
