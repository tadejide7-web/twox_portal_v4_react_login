"""SQLite persistence: the SSOT (single source of truth) for assessments, users and the verification log."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.getenv("TWOX_DB", "twox.db")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db() -> None:
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS assessments_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT NOT NULL,
            assessed_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            two_x_qualified TEXT NOT NULL,
            two_x_woman_owned TEXT NOT NULL,
            inputs TEXT NOT NULL,
            outcome_json TEXT NOT NULL)""")
        cols = [r["name"] for r in c.execute("PRAGMA table_info(assessments_v2)")]
        if "created_by" not in cols:   # added with login and roles; older rows stay NULL
            c.execute("ALTER TABLE assessments_v2 ADD COLUMN created_by TEXT")
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            full_name TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            last_login TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS verifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assessment_id INTEGER NOT NULL,
            rule_id INTEGER NOT NULL,
            old_status TEXT NOT NULL,
            new_status TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            verified_by TEXT NOT NULL,
            at TEXT NOT NULL)""")


# ---------------- assessments
def save(client_name: str, assessed_by: str, inputs: dict, outcome: dict, created_by: Optional[str] = None) -> int:
    with conn() as c:
        cur = c.execute(
            "INSERT INTO assessments_v2 (client_name, assessed_by, created_at, two_x_qualified,"
            " two_x_woman_owned, inputs, outcome_json, created_by) VALUES (?,?,?,?,?,?,?,?)",
            (client_name, assessed_by, now_iso(), outcome["two_x_qualified"], outcome["two_x_woman_owned"],
             json.dumps(inputs), json.dumps(outcome), created_by))
        return cur.lastrowid


def update_assessment(assessment_id: int, inputs: dict, outcome: dict) -> None:
    with conn() as c:
        c.execute("UPDATE assessments_v2 SET inputs=?, outcome_json=?, two_x_qualified=?, two_x_woman_owned=?"
                  " WHERE id=?", (json.dumps(inputs), json.dumps(outcome), outcome["two_x_qualified"],
                                  outcome["two_x_woman_owned"], assessment_id))


def _row(r: sqlite3.Row) -> dict:
    return {"id": r["id"], "client_name": r["client_name"], "assessed_by": r["assessed_by"],
            "created_at": r["created_at"], "created_by": r["created_by"], "inputs": json.loads(r["inputs"]),
            **json.loads(r["outcome_json"])}


def get(assessment_id: int):
    with conn() as c:
        r = c.execute("SELECT * FROM assessments_v2 WHERE id=?", (assessment_id,)).fetchone()
        return _row(r) if r else None


def list_all(limit: int = 100):
    with conn() as c:
        rows = c.execute("SELECT * FROM assessments_v2 ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [_row(r) for r in rows]


# ---------------- verification log
def add_verification(assessment_id: int, rule_id: int, old: str, new: str, note: str, by: str) -> None:
    with conn() as c:
        c.execute("INSERT INTO verifications (assessment_id, rule_id, old_status, new_status, note, verified_by, at)"
                  " VALUES (?,?,?,?,?,?,?)", (assessment_id, rule_id, old, new, note, by, now_iso()))


def list_verifications(assessment_id: int) -> list:
    with conn() as c:
        rows = c.execute("SELECT * FROM verifications WHERE assessment_id=? ORDER BY id", (assessment_id,)).fetchall()
        return [dict(r) for r in rows]


# ---------------- users
def _user(r) -> Optional[dict]:
    if not r:
        return None
    d = dict(r)
    d["active"] = bool(d["active"])
    return d


def count_users() -> int:
    with conn() as c:
        return c.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def count_active_admins() -> int:
    with conn() as c:
        return c.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]


def create_user(username: str, full_name: str, role: str, password_hash: str) -> int:
    with conn() as c:
        cur = c.execute("INSERT INTO users (username, full_name, role, password_hash, active, created_at)"
                        " VALUES (?,?,?,?,1,?)", (username, full_name, role, password_hash, now_iso()))
        return cur.lastrowid


def get_user(user_id: int):
    with conn() as c:
        return _user(c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())


def get_user_by_username(username: str):
    with conn() as c:
        return _user(c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone())


def list_users() -> list:
    with conn() as c:
        return [_user(r) for r in c.execute("SELECT * FROM users ORDER BY id").fetchall()]


def update_user(user_id: int, **fields) -> None:
    allowed = {"full_name", "role", "active", "password_hash", "last_login"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return
    with conn() as c:
        c.execute(f"UPDATE users SET {', '.join(k + '=?' for k in sets)} WHERE id=?",
                  (*[int(v) if k == 'active' else v for k, v in sets.items()], user_id))
