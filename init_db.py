import sqlite3

conn = sqlite3.connect("delivery.db")
conn.execute("PRAGMA foreign_keys = ON;")   # enable FK enforcement

with open("schema.sql", "r") as f:
    conn.executescript(f.read())

conn.commit()
conn.close()
print("Database created: delivery.db")