import os
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import app


@pytest.fixture()
def sqlite_db_path(tmp_path: Path):
    db_path = tmp_path / "delivery.db"
    schema = Path("schema.sql").read_text(encoding="utf-8")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(schema)
    conn.execute(
        "INSERT INTO REGION (region_id, city) VALUES (1, 'Test City')"
    )
    conn.execute(
        "INSERT INTO COURIER (courier_id, region_id) VALUES ('C1', 1)"
    )
    conn.execute(
        "INSERT INTO AOI (aoi_id, aoi_type) VALUES ('A1', 'urban')"
    )
    conn.execute(
        "INSERT INTO \"ORDER\" (order_id, courier_id, aoi_id, accept_time, delivery_time, ds, is_delayed) "
        "VALUES ('O1', 'C1', 'A1', '2026-01-01 09:00:00', '2026-01-01 10:15:00', 'regular', 1)"
    )
    conn.execute(
        "INSERT INTO ACCEPTANCE_LOCATION (order_id, gps_time, longitude, latitude) "
        "VALUES ('O1', '2026-01-01 09:00:00', 1.0, 2.0)"
    )
    conn.execute(
        "INSERT INTO DELIVERY_LOCATION (order_id, gps_time, longitude, latitude) "
        "VALUES ('O1', '2026-01-01 10:15:00', 3.0, 4.0)"
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture()
def client(sqlite_db_path: Path):
    app.state.sqlite_db_path = str(sqlite_db_path)
    app.state.mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    with TestClient(app) as test_client:
        yield test_client


def test_orders_crud_and_analytics(client: TestClient):
    response = client.get("/orders")
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = client.get("/orders/O1")
    assert response.status_code == 200
    assert response.json()["order_id"] == "O1"

    response = client.get("/orders/O2")
    assert response.status_code == 404

    response = client.post(
        "/orders",
        json={
            "order_id": "O2",
            "courier_id": "C1",
            "aoi_id": "A1",
            "accept_time": "2026-01-02 09:00:00",
            "delivery_time": "2026-01-02 10:30:00",
            "ds": "regular",
        },
    )
    assert response.status_code == 201

    response = client.put(
        "/orders/O2",
        json={"delivery_time": "2026-01-02 10:00:00", "ds": "priority", "is_delayed": 1},
    )
    assert response.status_code == 200
    assert response.json()["ds"] == "priority"
    assert response.json()["is_delayed"] == 1

    response = client.get("/couriers")
    assert response.status_code == 200
    assert any(item["courier_id"] == "C1" for item in response.json())

    response = client.get("/couriers/C1/orders")
    assert response.status_code == 200
    assert {item["order_id"] for item in response.json()} == {"O1", "O2"}

    response = client.get("/orders/O1/tracking")
    assert response.status_code == 200
    assert len(response.json()["locations"]) == 2

    response = client.get("/analytics/delivery-time")
    assert response.status_code == 200
    assert response.json()["average_delivery_hours"] > 0

    response = client.get("/analytics/courier-performance")
    assert response.status_code == 200
    assert response.json()[0]["courier_id"] == "C1"

    response = client.get("/analytics/delayed-orders")
    assert response.status_code == 200
    assert {order["order_id"] for order in response.json()["orders"]} == {"O1", "O2"}

    response = client.delete("/orders/O2")
    assert response.status_code == 200
    assert client.get("/orders/O2").status_code == 404


def test_mongo_tracking_is_unavailable_without_a_server(client: TestClient):
    client.app.state.mongo_uri = "mongodb://127.0.0.1:1/"
    response = client.get("/orders/O1/events")
    assert response.status_code == 503
    assert "MongoDB" in response.json()["detail"]


def test_tracking_comparison_returns_both_results_and_timings(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    import api

    class FakeCursor(list):
        def sort(self, field: str, direction: int):
            return self

    class FakeCollection:
        def find(self, query):
            assert query == {"order_id": {"$in": ["O1"]}}
            return FakeCursor(
                [{"_id": "O1_accept", "order_id": "O1", "event_type": "accept"}]
            )

    monkeypatch.setattr(api, "get_tracking_collection", lambda: FakeCollection())
    response = client.get("/compare/tracking/O1")

    assert response.status_code == 200
    result = response.json()
    assert len(result["sql"]["results"]) == 1
    assert result["sql"]["results"][0]["accept_latitude"] == 2.0
    assert result["sql"]["results"][0]["delivery_longitude"] == 3.0
    assert result["mongodb"]["results"][0]["event_type"] == "accept"
    assert result["sql"]["execution_time_ms"] >= 0
    assert result["mongodb"]["execution_time_ms"] >= 0


def test_sqlite_connection_pool_reuses_connections(client: TestClient):
    import api

    with api.get_connection() as first_connection:
        first_connection_id = id(first_connection)
    with api.get_connection() as second_connection:
        assert id(second_connection) == first_connection_id
    assert app.state.sqlite_pool.created_connections == 1


def test_dashboard_is_served_without_hiding_api_docs(client: TestClient):
    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "Operations overview" in dashboard.text
    assert 'id="trackingMap"' in dashboard.text
    assert 'id="delayedOrderRows"' in dashboard.text
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_order_loader_preserves_delayed_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import load_data

    (tmp_path / "Order.csv").write_text(
        "order_id,courier_id,aoi_id,accept_time,delivery_time,is_delayed\n"
        "O1,C1,A1,2026-01-01 09:00:00,2026-01-01 10:15:00,1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(load_data, "PROCESSED_DIR", tmp_path)
    conn = sqlite3.connect(":memory:")
    conn.execute(
        'CREATE TABLE "ORDER" (order_id TEXT, courier_id TEXT, aoi_id TEXT, '
        'accept_time TEXT, delivery_time TEXT, is_delayed INTEGER)'
    )

    assert load_data.load_table(conn, "ORDER", "Order.csv") == 1
    assert conn.execute('SELECT is_delayed FROM "ORDER" WHERE order_id = ?', ("O1",)).fetchone()[0] == 1
    conn.close()
