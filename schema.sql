-- 1. REGION
CREATE TABLE IF NOT EXISTS REGION (
    region_id   INTEGER PRIMARY KEY,
    city        TEXT NOT NULL
);

-- 2. COURIER
CREATE TABLE IF NOT EXISTS COURIER (
    courier_id  TEXT PRIMARY KEY,
    region_id   INTEGER,
    FOREIGN KEY (region_id) REFERENCES REGION(region_id)
);

-- 3. AOI
CREATE TABLE IF NOT EXISTS AOI (
    aoi_id      TEXT PRIMARY KEY,
    aoi_type    TEXT
);

-- 4. COURIER_AOI (M:N junction)
CREATE TABLE IF NOT EXISTS COURIER_AOI (
    courier_id  TEXT,
    aoi_id      TEXT,
    PRIMARY KEY (courier_id, aoi_id),
    FOREIGN KEY (courier_id) REFERENCES COURIER(courier_id),
    FOREIGN KEY (aoi_id)     REFERENCES AOI(aoi_id)
);

-- 5. ORDER
CREATE TABLE IF NOT EXISTS "ORDER" (
    order_id        TEXT PRIMARY KEY,
    courier_id      TEXT,
    aoi_id          TEXT,
    accept_time     TEXT,
    delivery_time   TEXT,
    ds              TEXT,
    FOREIGN KEY (courier_id) REFERENCES COURIER(courier_id),
    FOREIGN KEY (aoi_id)     REFERENCES AOI(aoi_id)
);

-- 6. ACCEPTANCE_LOCATION
CREATE TABLE IF NOT EXISTS ACCEPTANCE_LOCATION (
    accept_loc_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id        TEXT UNIQUE,
    gps_time        TEXT,
    longitude       REAL,
    latitude        REAL,
    FOREIGN KEY (order_id) REFERENCES "ORDER"(order_id)
);

-- 7. DELIVERY_LOCATION
CREATE TABLE IF NOT EXISTS DELIVERY_LOCATION (
    delivery_loc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id        TEXT UNIQUE,
    gps_time        TEXT,
    longitude       REAL,
    latitude        REAL,
    FOREIGN KEY (order_id) REFERENCES "ORDER"(order_id)
);