"""SQLite persistence for the normalized schema. No ORM, no heavy deps."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable

DB_PATH = Path(__file__).resolve().parent.parent / "inventory.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS products(
  sku TEXT PRIMARY KEY, name TEXT, unit_cost REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sales(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sku TEXT, date TEXT, qty REAL
);
CREATE TABLE IF NOT EXISTS inventory(
  sku TEXT PRIMARY KEY, on_hand REAL DEFAULT 0, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS suppliers(
  sku TEXT PRIMARY KEY, lead_time_days REAL DEFAULT 7, reliability REAL DEFAULT 0.95,
  supplier_id INTEGER
);
CREATE TABLE IF NOT EXISTS supplier_master(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT, phone TEXT,
  lead_time_days REAL DEFAULT 7, reliability REAL DEFAULT 0.95
);
CREATE TABLE IF NOT EXISTS outcomes(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sku TEXT, date TEXT, forecast_qty REAL, actual_qty REAL,
  stockout INTEGER DEFAULT 0, spoilage REAL DEFAULT 0, lead_time_actual REAL
);
CREATE TABLE IF NOT EXISTS settings(
  key TEXT PRIMARY KEY, value TEXT
);
CREATE INDEX IF NOT EXISTS idx_sales_sku ON sales(sku);
"""


@contextmanager
def conn(db_path=DB_PATH):
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db(db_path=DB_PATH):
    with conn(db_path) as c:
        c.executescript(SCHEMA)
        # Migrate older DBs that predate per-product supplier links.
        cols = [r["name"] for r in c.execute("PRAGMA table_info(suppliers)")]
        if "supplier_id" not in cols:
            c.execute("ALTER TABLE suppliers ADD COLUMN supplier_id INTEGER")


def reset_db(db_path=DB_PATH):
    with conn(db_path) as c:
        for t in ("products", "sales", "inventory", "suppliers", "outcomes",
                  "settings", "supplier_master"):
            c.execute(f"DROP TABLE IF EXISTS {t}")
        c.executescript(SCHEMA)


# ---- upserts -------------------------------------------------------------
def upsert_products(rows: Iterable[dict], db_path=DB_PATH):
    with conn(db_path) as c:
        for r in rows:
            c.execute(
                """INSERT INTO products(sku,name,unit_cost) VALUES(?,?,?)
                   ON CONFLICT(sku) DO UPDATE SET
                     name=COALESCE(NULLIF(excluded.name,''),products.name),
                     unit_cost=CASE WHEN excluded.unit_cost>0
                                    THEN excluded.unit_cost ELSE products.unit_cost END""",
                (r["sku"], r.get("name", ""), float(r.get("unit_cost", 0) or 0)))


def insert_sales(rows: Iterable[dict], db_path=DB_PATH):
    with conn(db_path) as c:
        c.executemany("INSERT INTO sales(sku,date,qty) VALUES(?,?,?)",
                      [(r["sku"], r["date"], float(r.get("qty", 0) or 0)) for r in rows])


def record_sale(sku, qty, date=None, db_path=DB_PATH):
    """Log a sale AND auto-decrement on-hand stock (never below 0).
    This is what keeps inventory self-updating — no manual recounting."""
    from datetime import date as _d
    date = date or _d.today().isoformat()
    now = datetime.now().isoformat()
    with conn(db_path) as c:
        c.execute("INSERT INTO sales(sku,date,qty) VALUES(?,?,?)",
                  (sku, date, float(qty)))
        c.execute(
            """INSERT INTO inventory(sku,on_hand,updated_at) VALUES(?,0,?)
               ON CONFLICT(sku) DO UPDATE SET
                 on_hand=MAX(inventory.on_hand - ?, 0), updated_at=excluded.updated_at""",
            (sku, now, float(qty)))


def receive_stock(sku, qty, db_path=DB_PATH):
    """Stock arrived from supplier -> auto-increment on-hand."""
    now = datetime.now().isoformat()
    with conn(db_path) as c:
        c.execute(
            """INSERT INTO inventory(sku,on_hand,updated_at) VALUES(?,?,?)
               ON CONFLICT(sku) DO UPDATE SET
                 on_hand=inventory.on_hand + ?, updated_at=excluded.updated_at""",
            (sku, float(qty), now, float(qty)))


def upsert_inventory(rows: Iterable[dict], db_path=DB_PATH):
    now = datetime.now().isoformat()
    with conn(db_path) as c:
        for r in rows:
            c.execute(
                """INSERT INTO inventory(sku,on_hand,updated_at) VALUES(?,?,?)
                   ON CONFLICT(sku) DO UPDATE SET
                     on_hand=excluded.on_hand, updated_at=excluded.updated_at""",
                (r["sku"], float(r.get("stock", r.get("on_hand", 0)) or 0),
                 r.get("updated_at", now)))


def upsert_suppliers(rows: Iterable[dict], db_path=DB_PATH):
    with conn(db_path) as c:
        for r in rows:
            c.execute(
                """INSERT INTO suppliers(sku,lead_time_days,reliability) VALUES(?,?,?)
                   ON CONFLICT(sku) DO UPDATE SET
                     lead_time_days=excluded.lead_time_days,
                     reliability=excluded.reliability""",
                (r["sku"], float(r.get("lead_time_days", 7) or 7),
                 float(r.get("reliability", 0.95) or 0.95)))


# ---- named suppliers (master) + per-product assignment -------------------
def add_supplier(name, phone="", lead_time_days=7, reliability=0.95, db_path=DB_PATH):
    """Create a named supplier; returns its new id."""
    with conn(db_path) as c:
        cur = c.execute(
            "INSERT INTO supplier_master(name,phone,lead_time_days,reliability) VALUES(?,?,?,?)",
            (name, phone, float(lead_time_days or 7), float(reliability or 0.95)))
        return cur.lastrowid


def update_supplier(sid, name, phone, lead_time_days, reliability, db_path=DB_PATH):
    with conn(db_path) as c:
        c.execute(
            """UPDATE supplier_master SET name=?,phone=?,lead_time_days=?,reliability=?
               WHERE id=?""",
            (name, phone, float(lead_time_days or 7), float(reliability or 0.95), sid))
        # keep each assigned product's lead-time/reliability in sync with its supplier
        c.execute("""UPDATE suppliers SET lead_time_days=?, reliability=?
                     WHERE supplier_id=?""",
                  (float(lead_time_days or 7), float(reliability or 0.95), sid))


def delete_supplier(sid, db_path=DB_PATH):
    """Remove a supplier; any product pointing at it falls back to defaults."""
    with conn(db_path) as c:
        c.execute("DELETE FROM supplier_master WHERE id=?", (sid,))
        c.execute("UPDATE suppliers SET supplier_id=NULL WHERE supplier_id=?", (sid,))


def get_supplier_master(db_path=DB_PATH):
    return _all("supplier_master", db_path)


def assign_product_supplier(sku, supplier_id, db_path=DB_PATH):
    """Attach a product to a named supplier (or None to clear). Reorder math for
    that product then uses the supplier's lead-time/reliability until changed."""
    with conn(db_path) as c:
        lt, rel = 7, 0.95
        if supplier_id:
            m = c.execute(
                "SELECT lead_time_days,reliability FROM supplier_master WHERE id=?",
                (supplier_id,)).fetchone()
            if m:
                lt, rel = m["lead_time_days"], m["reliability"]
        c.execute(
            """INSERT INTO suppliers(sku,lead_time_days,reliability,supplier_id)
               VALUES(?,?,?,?)
               ON CONFLICT(sku) DO UPDATE SET supplier_id=excluded.supplier_id,
                 lead_time_days=excluded.lead_time_days,
                 reliability=excluded.reliability""",
            (sku, float(lt), float(rel), supplier_id))


def get_product_supplier_map(db_path=DB_PATH):
    """sku -> assigned supplier dict {id,name,phone,lead_time_days,reliability}."""
    with conn(db_path) as c:
        rows = c.execute(
            """SELECT s.sku, m.id, m.name, m.phone, m.lead_time_days, m.reliability
               FROM suppliers s JOIN supplier_master m ON s.supplier_id=m.id""").fetchall()
    return {r["sku"]: dict(r) for r in rows}


def log_outcomes(rows: Iterable[dict], db_path=DB_PATH):
    with conn(db_path) as c:
        c.executemany(
            """INSERT INTO outcomes(sku,date,forecast_qty,actual_qty,stockout,spoilage,lead_time_actual)
               VALUES(?,?,?,?,?,?,?)""",
            [(r["sku"], r["date"], r.get("forecast_qty", 0), r.get("actual_qty", 0),
              int(r.get("stockout", 0)), r.get("spoilage", 0),
              r.get("lead_time_actual")) for r in rows])


# ---- reads ---------------------------------------------------------------
def _all(table, db_path=DB_PATH):
    with conn(db_path) as c:
        return [dict(x) for x in c.execute(f"SELECT * FROM {table}")]


def set_setting(key, value, db_path=DB_PATH):
    with conn(db_path) as c:
        c.execute("""INSERT INTO settings(key,value) VALUES(?,?)
                     ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                  (key, str(value)))


def get_setting(key, default=None, db_path=DB_PATH):
    with conn(db_path) as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def get_products(db_path=DB_PATH):  return _all("products", db_path)
def get_inventory(db_path=DB_PATH): return _all("inventory", db_path)
def get_suppliers(db_path=DB_PATH): return _all("suppliers", db_path)
def get_outcomes(db_path=DB_PATH):  return _all("outcomes", db_path)


def get_sales(db_path=DB_PATH):
    with conn(db_path) as c:
        return [dict(x) for x in
                c.execute("SELECT sku,date,qty FROM sales ORDER BY date")]


def sales_for(sku, db_path=DB_PATH):
    with conn(db_path) as c:
        return [dict(x) for x in c.execute(
            "SELECT date,qty FROM sales WHERE sku=? ORDER BY date", (sku,))]
