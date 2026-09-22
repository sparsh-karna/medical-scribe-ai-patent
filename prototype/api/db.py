"""
SQLite persistence for doctors, sessions, patients and cases. Deliberately
stdlib-only (sqlite3, hashlib, secrets) -- no ORM, no extra pip installs,
given how unreliable package/model downloads were in this environment.

The pipeline itself (extraction, grounding, calibration, audit) is
untouched and still lives in src/ + per-run files under api/runs/<run_id>/.
This module only adds who-owns-what: which doctor a patient belongs to,
which patient a case belongs to, and which run_id backs a case.
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS doctors (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  salt TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  doctor_id INTEGER NOT NULL REFERENCES doctors(id),
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS patients (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  doctor_id INTEGER NOT NULL REFERENCES doctors(id),
  name TEXT NOT NULL,
  identifier TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  doctor_id INTEGER NOT NULL REFERENCES doctors(id),
  title TEXT NOT NULL,
  source TEXT NOT NULL,
  source_ref TEXT,
  run_id TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
    return digest, salt


def create_doctor(conn: sqlite3.Connection, name: str, email: str, password: str) -> int:
    digest, salt = hash_password(password)
    cur = conn.execute(
        "INSERT INTO doctors (name, email, password_hash, salt, created_at) VALUES (?, ?, ?, ?, ?)",
        (name, email.lower().strip(), digest, salt, now()),
    )
    conn.commit()
    return cur.lastrowid


def verify_doctor(conn: sqlite3.Connection, email: str, password: str):
    row = conn.execute("SELECT * FROM doctors WHERE email = ?", (email.lower().strip(),)).fetchone()
    if row is None:
        return None
    digest, _ = hash_password(password, row["salt"])
    if not secrets.compare_digest(digest, row["password_hash"]):
        return None
    return row


def create_session(conn: sqlite3.Connection, doctor_id: int) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute("INSERT INTO sessions (token, doctor_id, created_at) VALUES (?, ?, ?)", (token, doctor_id, now()))
    conn.commit()
    return token


def get_doctor_by_session(conn: sqlite3.Connection, token: str):
    row = conn.execute(
        """SELECT doctors.* FROM sessions
           JOIN doctors ON doctors.id = sessions.doctor_id
           WHERE sessions.token = ?""",
        (token,),
    ).fetchone()
    return row


def delete_session(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
