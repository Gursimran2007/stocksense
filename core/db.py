"""SQLite / libSQL persistence for the normalized schema. No ORM, no heavy deps.

Two backends, one code path:
  * Local dev / demo  -> a single SQLite file under DATA_DIR.
  * Production        -> a hosted **Turso (libSQL)** database, when the env vars
                         TURSO_DATABASE_URL (+ TURSO_AUTH_TOKEN) are set.
Turso is hosted SQLite, so the exact same SQL runs on both — the only difference
is where the bytes live. On a free host the local filesystem is wiped on every
restart; Turso keeps each shop's data forever (free tier, no card).

Multi-tenancy is **row-level**: every business row carries a shop_id (the
logged-in user's id). A ContextVar holds the current shop so concurrent
Streamlit sessions never see each other's data, and queries scope to it
automatically — callers don't pass it around.
"""
import os
import sqlite3
import contextvars
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable

BASE_DIR = Path(__file__).resolve().parent.parent

# Persisted data location. Overridable so a host with a persistent disk can
# point us at it; on Turso this is unused.
DATA_DIR = Path(os.environ.get("STOCKSENSE_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "stocksense.db"          # single local DB file

# Hosted libSQL (Turso). Presence of the URL flips the backend.
# Resolved lazily and from BOTH sources because hosts differ: Render exposes
# config as env vars, while Streamlit Community Cloud exposes it via st.secrets
# (not os.environ). Checking both means the same code just works on either.
def _cfg(key):
    val = os.environ.get(key)
    if val:
        return val
    try:
        import streamlit as st
        return st.secrets.get(key)
    except Exception:
        return None


def turso_url():
    return _cfg("TURSO_DATABASE_URL")


def turso_token():
    return _cfg("TURSO_AUTH_TOKEN")


def using_turso():
    return bool(turso_url())


# The shop whose data the current request is allowed to touch. 0 = the
# single-tenant default (tests, or running without login).
_shop = contextvars.ContextVar("shop", default=0)


def set_shop(uid):
    """Scope all subsequent DB calls in this context to this shop."""
    _shop.set(int(uid or 0))


def current_shop():
    return _shop.get()


SCHEMA = """
CREATE TABLE IF NOT EXISTS products(
  shop_id INTEGER NOT NULL DEFAULT 0,
  sku TEXT, name TEXT, unit_cost REAL DEFAULT 0,
  PRIMARY KEY(shop_id, sku)
);
CREATE TABLE IF NOT EXISTS sales(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  shop_id INTEGER NOT NULL DEFAULT 0,
  sku TEXT, date TEXT, qty REAL
);
CREATE TABLE IF NOT EXISTS inventory(
  shop_id INTEGER NOT NULL DEFAULT 0,
  sku TEXT, on_hand REAL DEFAULT 0, updated_at TEXT,
  PRIMARY KEY(shop_id, sku)
);
CREATE TABLE IF NOT EXISTS suppliers(
  shop_id INTEGER NOT NULL DEFAULT 0,
  sku TEXT, lead_time_days REAL DEFAULT 7, reliability REAL DEFAULT 0.95,
  supplier_id INTEGER,
  PRIMARY KEY(shop_id, sku)
);
CREATE TABLE IF NOT EXISTS supplier_master(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  shop_id INTEGER NOT NULL DEFAULT 0,
  name TEXT, phone TEXT,
  lead_time_days REAL DEFAULT 7, reliability REAL DEFAULT 0.95
);
CREATE TABLE IF NOT EXISTS outcomes(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  shop_id INTEGER NOT NULL DEFAULT 0,
  sku TEXT, date TEXT, forecast_qty REAL, actual_qty REAL,
  stockout INTEGER DEFAULT 0, spoilage REAL DEFAULT 0, lead_time_actual REAL
);
CREATE TABLE IF NOT EXISTS settings(
  shop_id INTEGER NOT NULL DEFAULT 0,
  key TEXT, value TEXT,
  PRIMARY KEY(shop_id, key)
);
CREATE INDEX IF NOT EXISTS idx_sales_shop_sku ON sales(shop_id, sku);
"""


# ---- libSQL adapter ------------------------------------------------------
# The libsql client returns plain tuples and has no row_factory. These thin
# wrappers give it the same dict-row, cursor and commit surface our code (and
# sqlite3.Row) already relies on, so the rest of the module is backend-blind.
class _DictCursor:
    def __init__(self, cur):
        self._cur = cur
        self._cols = [d[0] for d in cur.description] if cur.description else []

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    def _wrap(self, row):
        return dict(zip(self._cols, row)) if row is not None else None

    def fetchone(self):
        return self._wrap(self._cur.fetchone())

    def fetchall(self):
        return [self._wrap(r) for r in self._cur.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class _LibsqlConn:
    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=None):
        cur = self._raw.execute(sql, params) if params else self._raw.execute(sql)
        return _DictCursor(cur)

    def executemany(self, sql, seq):
        self._raw.executemany(sql, list(seq))
        return self

    def executescript(self, sql):
        self._raw.executescript(sql)
        return self

    def commit(self):
        self._raw.commit()

    def close(self):
        try:
            self._raw.close()
        except Exception:
            pass


@contextmanager
def conn(db_path=None):
    if using_turso():
        import libsql_experimental as libsql
        token = turso_token()
        kwargs = {"auth_token": token} if token else {}
        c = _LibsqlConn(libsql.connect(turso_url(), **kwargs))
        try:
            yield c
            c.commit()
        finally:
            c.close()
    else:
        # timeout + WAL + busy_timeout keep concurrent Streamlit reruns from
        # hitting "database is locked" when two writes race.
        c = sqlite3.connect(db_path or DB_PATH, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=30000")
        try:
            yield c
            c.commit()
        finally:
            c.close()


def init_db(db_path=None):
    with conn(db_path) as c:
        c.executescript(SCHEMA)


def reset_db(db_path=None):
    """Wipe ONLY the current shop's data (single shared DB — never drop tables)."""
    sid = current_shop()
    with conn(db_path) as c:
        c.executescript(SCHEMA)
        for t in ("products", "sales", "inventory", "suppliers", "outcomes",
                  "settings", "supplier_master"):
            c.execute(f"DELETE FROM {t} WHERE shop_id=?", (sid,))


# ---- upserts -------------------------------------------------------------
def upsert_products(rows: Iterable[dict], db_path=None):
    sid = current_shop()
    with conn(db_path) as c:
        for r in rows:
            c.execute(
                """INSERT INTO products(shop_id,sku,name,unit_cost) VALUES(?,?,?,?)
                   ON CONFLICT(shop_id,sku) DO UPDATE SET
                     name=COALESCE(NULLIF(excluded.name,''),products.name),
                     unit_cost=CASE WHEN excluded.unit_cost>0
                                    THEN excluded.unit_cost ELSE products.unit_cost END""",
                (sid, r["sku"], r.get("name", ""), float(r.get("unit_cost", 0) or 0)))


def insert_sales(rows: Iterable[dict], db_path=None):
    sid = current_shop()
    with conn(db_path) as c:
        c.executemany("INSERT INTO sales(shop_id,sku,date,qty) VALUES(?,?,?,?)",
                      [(sid, r["sku"], r["date"], float(r.get("qty", 0) or 0))
                       for r in rows])


def record_sale(sku, qty, date=None, db_path=None):
    """Log a sale AND auto-decrement on-hand stock (never below 0).
    This is what keeps inventory self-updating — no manual recounting."""
    from datetime import date as _d
    sid = current_shop()
    date = date or _d.today().isoformat()
    now = datetime.now().isoformat()
    with conn(db_path) as c:
        c.execute("INSERT INTO sales(shop_id,sku,date,qty) VALUES(?,?,?,?)",
                  (sid, sku, date, float(qty)))
        c.execute(
            """INSERT INTO inventory(shop_id,sku,on_hand,updated_at) VALUES(?,?,0,?)
               ON CONFLICT(shop_id,sku) DO UPDATE SET
                 on_hand=MAX(inventory.on_hand - ?, 0), updated_at=excluded.updated_at""",
            (sid, sku, now, float(qty)))


def receive_stock(sku, qty, db_path=None):
    """Stock arrived from supplier -> auto-increment on-hand."""
    sid = current_shop()
    now = datetime.now().isoformat()
    with conn(db_path) as c:
        c.execute(
            """INSERT INTO inventory(shop_id,sku,on_hand,updated_at) VALUES(?,?,?,?)
               ON CONFLICT(shop_id,sku) DO UPDATE SET
                 on_hand=inventory.on_hand + ?, updated_at=excluded.updated_at""",
            (sid, sku, float(qty), now, float(qty)))


def upsert_inventory(rows: Iterable[dict], db_path=None):
    sid = current_shop()
    now = datetime.now().isoformat()
    with conn(db_path) as c:
        for r in rows:
            c.execute(
                """INSERT INTO inventory(shop_id,sku,on_hand,updated_at) VALUES(?,?,?,?)
                   ON CONFLICT(shop_id,sku) DO UPDATE SET
                     on_hand=excluded.on_hand, updated_at=excluded.updated_at""",
                (sid, r["sku"], float(r.get("stock", r.get("on_hand", 0)) or 0),
                 r.get("updated_at", now)))


def upsert_suppliers(rows: Iterable[dict], db_path=None):
    sid = current_shop()
    with conn(db_path) as c:
        for r in rows:
            c.execute(
                """INSERT INTO suppliers(shop_id,sku,lead_time_days,reliability)
                   VALUES(?,?,?,?)
                   ON CONFLICT(shop_id,sku) DO UPDATE SET
                     lead_time_days=excluded.lead_time_days,
                     reliability=excluded.reliability""",
                (sid, r["sku"], float(r.get("lead_time_days", 7) or 7),
                 float(r.get("reliability", 0.95) or 0.95)))


# ---- named suppliers (master) + per-product assignment -------------------
def add_supplier(name, phone="", lead_time_days=7, reliability=0.95, db_path=None):
    """Create a named supplier; returns its new id."""
    sid = current_shop()
    with conn(db_path) as c:
        cur = c.execute(
            """INSERT INTO supplier_master(shop_id,name,phone,lead_time_days,reliability)
               VALUES(?,?,?,?,?)""",
            (sid, name, phone, float(lead_time_days or 7), float(reliability or 0.95)))
        return cur.lastrowid


def update_supplier(sid_, name, phone, lead_time_days, reliability, db_path=None):
    shop = current_shop()
    with conn(db_path) as c:
        c.execute(
            """UPDATE supplier_master SET name=?,phone=?,lead_time_days=?,reliability=?
               WHERE id=? AND shop_id=?""",
            (name, phone, float(lead_time_days or 7), float(reliability or 0.95),
             sid_, shop))
        # keep each assigned product's lead-time/reliability in sync
        c.execute("""UPDATE suppliers SET lead_time_days=?, reliability=?
                     WHERE supplier_id=? AND shop_id=?""",
                  (float(lead_time_days or 7), float(reliability or 0.95), sid_, shop))


def delete_supplier(sid_, db_path=None):
    """Remove a supplier; any product pointing at it falls back to defaults."""
    shop = current_shop()
    with conn(db_path) as c:
        c.execute("DELETE FROM supplier_master WHERE id=? AND shop_id=?", (sid_, shop))
        c.execute("UPDATE suppliers SET supplier_id=NULL WHERE supplier_id=? AND shop_id=?",
                  (sid_, shop))


def get_supplier_master(db_path=None):
    return _all("supplier_master", db_path)


def assign_product_supplier(sku, supplier_id, db_path=None):
    """Attach a product to a named supplier (or None to clear). Reorder math for
    that product then uses the supplier's lead-time/reliability until changed."""
    shop = current_shop()
    with conn(db_path) as c:
        lt, rel = 7, 0.95
        if supplier_id:
            m = c.execute(
                "SELECT lead_time_days,reliability FROM supplier_master WHERE id=? AND shop_id=?",
                (supplier_id, shop)).fetchone()
            if m:
                lt, rel = m["lead_time_days"], m["reliability"]
        c.execute(
            """INSERT INTO suppliers(shop_id,sku,lead_time_days,reliability,supplier_id)
               VALUES(?,?,?,?,?)
               ON CONFLICT(shop_id,sku) DO UPDATE SET supplier_id=excluded.supplier_id,
                 lead_time_days=excluded.lead_time_days,
                 reliability=excluded.reliability""",
            (shop, sku, float(lt), float(rel), supplier_id))


def get_product_supplier_map(db_path=None):
    """sku -> assigned supplier dict {id,name,phone,lead_time_days,reliability}."""
    shop = current_shop()
    with conn(db_path) as c:
        rows = c.execute(
            """SELECT s.sku, m.id, m.name, m.phone, m.lead_time_days, m.reliability
               FROM suppliers s JOIN supplier_master m
                 ON s.supplier_id=m.id AND s.shop_id=m.shop_id
               WHERE s.shop_id=?""", (shop,)).fetchall()
    return {r["sku"]: dict(r) for r in rows}


def log_outcomes(rows: Iterable[dict], db_path=None):
    sid = current_shop()
    with conn(db_path) as c:
        c.executemany(
            """INSERT INTO outcomes(shop_id,sku,date,forecast_qty,actual_qty,stockout,spoilage,lead_time_actual)
               VALUES(?,?,?,?,?,?,?,?)""",
            [(sid, r["sku"], r["date"], r.get("forecast_qty", 0), r.get("actual_qty", 0),
              int(r.get("stockout", 0)), r.get("spoilage", 0),
              r.get("lead_time_actual")) for r in rows])


# ---- reads ---------------------------------------------------------------
def _all(table, db_path=None):
    sid = current_shop()
    with conn(db_path) as c:
        return [dict(x) for x in
                c.execute(f"SELECT * FROM {table} WHERE shop_id=?", (sid,))]


def set_setting(key, value, db_path=None):
    sid = current_shop()
    with conn(db_path) as c:
        c.execute("""INSERT INTO settings(shop_id,key,value) VALUES(?,?,?)
                     ON CONFLICT(shop_id,key) DO UPDATE SET value=excluded.value""",
                  (sid, key, str(value)))


def get_setting(key, default=None, db_path=None):
    sid = current_shop()
    with conn(db_path) as c:
        row = c.execute("SELECT value FROM settings WHERE shop_id=? AND key=?",
                        (sid, key)).fetchone()
    return row["value"] if row else default


def get_products(db_path=None):  return _all("products", db_path)
def get_inventory(db_path=None): return _all("inventory", db_path)
def get_suppliers(db_path=None): return _all("suppliers", db_path)
def get_outcomes(db_path=None):  return _all("outcomes", db_path)


def get_sales(db_path=None):
    sid = current_shop()
    with conn(db_path) as c:
        return [dict(x) for x in c.execute(
            "SELECT sku,date,qty FROM sales WHERE shop_id=? ORDER BY date", (sid,))]


def sales_for(sku, db_path=None):
    sid = current_shop()
    with conn(db_path) as c:
        return [dict(x) for x in c.execute(
            "SELECT date,qty FROM sales WHERE shop_id=? AND sku=? ORDER BY date",
            (sid, sku))]
