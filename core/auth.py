"""Username/password auth + sessions — stdlib only, no paid services.

Design choices (all driven by "a shopkeeper will actually use this"):

  * Passwords hashed with pbkdf2_hmac(sha256, 200k rounds) + per-user salt.
    No bcrypt/argon2 dependency to install or break on a free host.
  * Username = whatever the shopkeeper types (often a phone number). They
    usually have no email, so login + password-change are the only recovery
    paths; there is no email-reset flow to depend on a mail provider.
  * Usernames normalized (trim + lowercase) so "Raju ", "raju", "RAJU" are
    one account and a tired user can't accidentally make duplicates.
  * Sessions are random opaque tokens stored server-side with a 30-day expiry,
    so a browser refresh keeps you logged in without putting anything
    sensitive (or forgeable) in the URL.

The auth DB is a single shared file (auth.db); each shop's *business* data
lives in its own isolated file (see db.shop_db_path).
"""
import os
import sqlite3
import hashlib
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta

from . import db as _db

AUTH_DB = _db.DATA_DIR / "auth.db"

_PBKDF_ROUNDS = 200_000
_SESSION_DAYS = 30
MIN_PASSWORD_LEN = 6

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  shop_name TEXT,
  salt TEXT NOT NULL,
  pw_hash TEXT NOT NULL,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS sessions(
  token TEXT PRIMARY KEY,
  uid INTEGER NOT NULL,
  expires_at TEXT NOT NULL
);
"""


@contextmanager
def _conn():
    c = sqlite3.connect(AUTH_DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with _conn() as c:
        c.executescript(_SCHEMA)


# ---- password hashing ----------------------------------------------------
def _hash(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"),
        bytes.fromhex(salt), _PBKDF_ROUNDS).hex()


def _norm(username):
    return (username or "").strip().lower()


# ---- public API ----------------------------------------------------------
class AuthError(Exception):
    """Friendly, user-facing auth failure."""


def signup(username, password, shop_name=""):
    """Create an account. Returns the new uid. Raises AuthError on bad input."""
    username = _norm(username)
    if not username:
        raise AuthError("Please enter a username (your phone number works).")
    if len(password or "") < MIN_PASSWORD_LEN:
        raise AuthError(f"Password must be at least {MIN_PASSWORD_LEN} characters.")
    salt = secrets.token_hex(16)
    pw_hash = _hash(password, salt)
    now = datetime.now().isoformat()
    try:
        with _conn() as c:
            cur = c.execute(
                """INSERT INTO users(username,shop_name,salt,pw_hash,created_at)
                   VALUES(?,?,?,?,?)""",
                (username, shop_name.strip(), salt, pw_hash, now))
            return cur.lastrowid
    except sqlite3.IntegrityError:
        raise AuthError("That username is already taken. Try logging in instead.")


def login(username, password):
    """Verify credentials -> user dict. Raises AuthError if wrong."""
    username = _norm(username)
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    # Always run a hash even on missing user to blunt timing/enumeration.
    salt = row["salt"] if row else secrets.token_hex(16)
    candidate = _hash(password or "", salt)
    if not row or not secrets.compare_digest(candidate, row["pw_hash"]):
        raise AuthError("Wrong username or password.")
    return {"id": row["id"], "username": row["username"], "shop_name": row["shop_name"]}


def change_password(uid, old_password, new_password):
    """Self-service password change (the only recovery path — no email)."""
    if len(new_password or "") < MIN_PASSWORD_LEN:
        raise AuthError(f"New password must be at least {MIN_PASSWORD_LEN} characters.")
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not row or not secrets.compare_digest(
                _hash(old_password or "", row["salt"]), row["pw_hash"]):
            raise AuthError("Current password is wrong.")
        salt = secrets.token_hex(16)
        c.execute("UPDATE users SET salt=?, pw_hash=? WHERE id=?",
                  (salt, _hash(new_password, salt), uid))


def set_shop_name(uid, shop_name):
    with _conn() as c:
        c.execute("UPDATE users SET shop_name=? WHERE id=?",
                  (shop_name.strip(), uid))


def get_user(uid):
    with _conn() as c:
        row = c.execute("SELECT id,username,shop_name FROM users WHERE id=?",
                        (uid,)).fetchone()
    return dict(row) if row else None


# ---- sessions ------------------------------------------------------------
def create_session(uid):
    """Issue an opaque token, persisted with a 30-day expiry."""
    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(days=_SESSION_DAYS)).isoformat()
    with _conn() as c:
        c.execute("INSERT INTO sessions(token,uid,expires_at) VALUES(?,?,?)",
                  (token, uid, expires))
    return token


def resolve_session(token):
    """Token -> user dict, or None if missing/expired (expired rows pruned)."""
    if not token:
        return None
    with _conn() as c:
        row = c.execute("SELECT uid,expires_at FROM sessions WHERE token=?",
                        (token,)).fetchone()
        if not row:
            return None
        if datetime.fromisoformat(row["expires_at"]) < datetime.now():
            c.execute("DELETE FROM sessions WHERE token=?", (token,))
            return None
    return get_user(row["uid"])


def destroy_session(token):
    if not token:
        return
    with _conn() as c:
        c.execute("DELETE FROM sessions WHERE token=?", (token,))
