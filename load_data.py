import os
import sqlite3
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
PROCESSED_DIR = BASE_DIR / "processed" / "sql"
DB_PATH = BASE_DIR / "delivery.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"

with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
    SCHEMA_SQL = f.read()

LOAD_PLAN = [
    ("REGION", "Region.csv"),
    ("COURIER", "Courier.csv"),
    ("AOI", "AOI.csv"),
    ("COURIER_AOI", "Courier_AOI.csv"),
    ("ORDER", "Order.csv"),
    ("ACCEPTANCE_LOCATION", "Acceptance_Location.csv"),
    ("DELIVERY_LOCATION", "Delivery_Location.csv"),
]


def create_database():
    """Delete old DB, create fresh one, apply schema."""
    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"🗑  Removed old database: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")

    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        print("✅ Schema created")
    except sqlite3.Error as e:
        print(f"❌ Schema error: {e}")
        conn.close()
        raise

    return conn


def load_table(conn, table, csv_file):
    """Load one CSV into one table. Returns number of rows loaded."""
    path = PROCESSED_DIR / csv_file

    if not path.exists():
        print(f"⚠️  Missing file: {path} — skipping {table}")
        return 0

    df = pd.read_csv(path)

    rename_map = {
        "REGION": {},
        "COURIER": {},
        "AOI": {},
        "COURIER_AOI": {},
        "ORDER": {
            "accept_time": "accept_time",
            "delivery_time": "delivery_time",
            "courier_id": "courier_id",
            "aoi_id": "aoi_id",
            "order_id": "order_id",
        },
        "ACCEPTANCE_LOCATION": {
            "accept_gps_time": "gps_time",
            "accept_gps_lng": "longitude",
            "accept_gps_lat": "latitude",
            "order_id": "order_id",
        },
        "DELIVERY_LOCATION": {
            "delivery_gps_time": "gps_time",
            "delivery_gps_lng": "longitude",
            "delivery_gps_lat": "latitude",
            "order_id": "order_id",
        },
    }

    if table in rename_map:
        df = df.rename(columns=rename_map[table])

    if table == "ORDER":
        if "is_delayed" not in df.columns:
            df["is_delayed"] = 0
        df["is_delayed"] = pd.to_numeric(df["is_delayed"], errors="coerce").fillna(0).astype(int)
        df = df[["order_id", "courier_id", "aoi_id", "accept_time", "delivery_time", "is_delayed"]]
    elif table == "ACCEPTANCE_LOCATION":
        df = df[["order_id", "gps_time", "longitude", "latitude"]]
    elif table == "DELIVERY_LOCATION":
        df = df[["order_id", "gps_time", "longitude", "latitude"]]

    try:
        df.to_sql(table, conn, if_exists="append", index=False)
        conn.commit()
        print(f"   Loaded {len(df):>7} rows → {table}")
        return len(df)
    except Exception as e:
        conn.rollback()
        print(f"❌ Failed loading {table}: {e}")
        print(f"   File: {path}")
        print(f"   Columns: {list(df.columns)}")
        raise


def verify(conn):
    """Print row counts and run a sample join."""
    cur = conn.cursor()

    print("\n📊 Row counts")
    print(f"{'Table':<25}{'Rows':>10}")
    print("-" * 35)

    for table, _ in LOAD_PLAN:
        cur.execute(f'SELECT COUNT(*) FROM "{table}"')
        print(f"{table:<25}{cur.fetchone()[0]:>10}")

    print("\n🔗 Sample join (first 5 orders)")
    try:
        cur.execute("""
            SELECT o.order_id, o.courier_id, c.region_id, o.aoi_id,
                   o.accept_time, o.delivery_time
            FROM "ORDER" o
            JOIN COURIER c ON o.courier_id = c.courier_id
            LIMIT 5
        """)
        rows = cur.fetchall()
        if not rows:
            print("   (no rows — check your data)")
        for row in rows:
            print("   ", row)
    except sqlite3.Error as e:
        print(f"   Join failed: {e}")


def main():
    print("=" * 50)
    print("  SQLite Loader — Last-Mile Delivery System")
    print("=" * 50)

    if not PROCESSED_DIR.is_dir():
        print(f"\n❌ Folder not found: {PROCESSED_DIR}")
        print("   Place the CSV files in processed/sql and try again.")
        return

    print("\n[1/3] Creating database...")
    conn = create_database()

    print("\n[2/3] Loading CSVs...")
    total = 0
    try:
        for table, csv_file in LOAD_PLAN:
            total += load_table(conn, table, csv_file)
    except Exception:
        conn.close()
        print("\n❌ Load aborted.")
        return

    print("\n[3/3] Verifying...")
    verify(conn)

    conn.close()
    print(f"\n✅ Done. {total} rows loaded into {DB_PATH}")


if __name__ == "__main__":
    main()