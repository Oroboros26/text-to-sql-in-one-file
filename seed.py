"""Builds shop.db with deterministic synthetic retail data (seed 42). No real data."""
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB = Path(__file__).resolve().parent / "shop.db"
SCHEMA = """
CREATE TABLE products (product_id INTEGER PRIMARY KEY, name TEXT, category TEXT, list_price REAL);
CREATE TABLE orders (order_id INTEGER PRIMARY KEY, order_date TEXT, channel TEXT, country TEXT);
CREATE TABLE order_lines (order_id INTEGER, product_id INTEGER, quantity INTEGER, discount_pct REAL);
"""
PRICE_RANGE = {"Jackets": (120, 350), "Shoes": (60, 220), "Backpacks": (40, 160), "Socks": (8, 25), "Gloves": (20, 90)}
COUNTRIES = ["France", "Germany", "Italy", "Spain", "Sweden", "United Kingdom"]


def build(path: Path = DB, n_orders: int = 3000) -> None:
    rng = random.Random(42)
    path.unlink(missing_ok=True)
    products = [(i, f"{cat} model {m}", cat, round(rng.uniform(*PRICE_RANGE[cat]), 2))
                for i, (cat, m) in enumerate(((c, m) for c in PRICE_RANGE for m in range(1, 9)), start=1)]
    orders, lines = [], []
    for oid in range(1, n_orders + 1):
        day = date(2025, 1, 1) + timedelta(days=rng.randrange(365))
        orders.append((oid, day.isoformat(), rng.choices(["online", "store"], [0.6, 0.4])[0], rng.choice(COUNTRIES)))
        for pid in rng.sample(range(1, len(products) + 1), rng.randint(1, 4)):
            lines.append((oid, pid, rng.randint(1, 3), rng.choice([0, 0, 0, 0.1, 0.2, 0.3, 0.5])))
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.executemany("INSERT INTO products VALUES (?,?,?,?)", products)
    con.executemany("INSERT INTO orders VALUES (?,?,?,?)", orders)
    con.executemany("INSERT INTO order_lines VALUES (?,?,?,?)", lines)
    con.commit()
    con.close()


if __name__ == "__main__":
    build()
    print(f"built {DB.name}")
