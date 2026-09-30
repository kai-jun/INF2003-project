"""
init_mongo.py
Loads two JSON files from ./processed/ into MongoDB.
Adjust FILENAMES and COLLECTION NAMES to match yours.
"""

import os
import json
from pymongo import MongoClient, GEOSPHERE, ASCENDING

# ---------- Connection ----------
client = MongoClient("mongodb://localhost:27017/")
# For Atlas:
# client = MongoClient("mongodb+srv://<user>:<pass>@cluster0.xxxxx.mongodb.net/")

db = client["lastmile"]

# ---------- Paths ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED = os.path.join(BASE_DIR, "processed")

# ---------- File → Collection mapping ----------
# Change these to your actual filenames + target collection names
FILES = [
    ("mongo/delivery_events.json", "delivery_events"),
    ("mongo/gps_tracking_logs.json",  "courier_tracking"),  
]


def load_collection(json_file, collection_name):
    path = os.path.join(PROCESSED, json_file)

    if not os.path.exists(path):
        print(f"⚠️  Skipping {collection_name} — not found: {path}")
        return

    # Fresh start
    db[collection_name].drop()

    with open(path, "r", encoding="utf-8") as f:
        docs = json.load(f)

    # If the file is a dict with a list inside, unwrap it
    if isinstance(docs, dict):
        for key in ("data", "records", "items", "documents"):
            if key in docs and isinstance(docs[key], list):
                docs = docs[key]
                break
        else:
            docs = [docs]

    if not docs:
        print(f"⚠️  {json_file} is empty — nothing to insert")
        return

    # Insert in batches to avoid memory issues
    batch_size = 1000
    total = 0
    for i in range(0, len(docs), batch_size):
        batch = docs[i:i + batch_size]
        db[collection_name].insert_many(batch)
        total += len(batch)

    print(f"✅ {total} docs → {collection_name}")

    return collection_name


def create_indexes(collection_name):
    """Create indexes appropriate to each collection's shape."""
    col = db[collection_name]

    # delivery_events-style (flat GPS events)
    if collection_name == "delivery_events":
        col.create_index([("order_id", ASCENDING)])
        col.create_index([("courier_id", ASCENDING)])
        col.create_index([("event_type", ASCENDING)])
        col.create_index([("timestamp", ASCENDING)])
        # Geospatial: MongoDB needs GeoJSON — add a 2dsphere on a derived field
        # if you build one; otherwise use a plain compound index:
        col.create_index([("lng", ASCENDING), ("lat", ASCENDING)])

    # courier_tracking-style (bucketed pings with GeoJSON)
    elif collection_name == "courier_tracking":
        col.create_index([("courier_id", ASCENDING), ("date", ASCENDING)])
        col.create_index([("pings.loc", GEOSPHERE)])

    print(f"✅ Indexes created for {collection_name}")


def main():
    print("=" * 50)
    print("  MongoDB Loader")
    print("=" * 50)

    if not os.path.isdir(PROCESSED):
        print(f"❌ Folder not found: {PROCESSED}")
        return

    for json_file, collection_name in FILES:
        loaded = load_collection(json_file, collection_name)
        if loaded:
            create_indexes(loaded)

    print("\n✅ MongoDB setup complete")


if __name__ == "__main__":
    main()