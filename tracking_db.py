import sqlite3
import json
import time
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "tracking.db"


def _conn():
    return sqlite3.connect(str(DB_PATH))


def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    c = _conn()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            label       TEXT NOT NULL,
            started_at  REAL NOT NULL,
            ended_at    REAL,
            notes       TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS eye_contact_episodes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER NOT NULL REFERENCES sessions(id),
            start_time  REAL NOT NULL,
            duration_ms REAL NOT NULL,
            phase       INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS joint_attention_episodes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER NOT NULL REFERENCES sessions(id),
            trial       INTEGER NOT NULL,
            timestamp   REAL NOT NULL,
            success     INTEGER NOT NULL,
            latency_ms  REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS false_belief_trials (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL REFERENCES sessions(id),
            trial           INTEGER NOT NULL,
            correct         INTEGER NOT NULL,
            latency_ms      REAL NOT NULL,
            error_pattern   TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS response_times (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL REFERENCES sessions(id),
            stimulus_type   TEXT NOT NULL,
            timestamp       REAL NOT NULL,
            latency_ms      REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS spontaneous_initiatives (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL REFERENCES sessions(id),
            timestamp       REAL NOT NULL,
            description     TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS calibration (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL REFERENCES sessions(id),
            yaw_center      REAL NOT NULL,
            pitch_center    REAL NOT NULL,
            recorded_at     REAL NOT NULL
        );
    """)
    c.commit()
    c.close()


def create_session(label: str = "Demo") -> int:
    c = _conn()
    cur = c.execute("INSERT INTO sessions (label, started_at) VALUES (?, ?)",
                    (label, time.time()))
    c.commit()
    sid = cur.lastrowid
    c.close()
    return sid


def close_session(sid: int):
    c = _conn()
    c.execute("UPDATE sessions SET ended_at = ? WHERE id = ?", (time.time(), sid))
    c.commit()
    c.close()


def log_eye_contact(session_id: int, duration_ms: float, phase: int = 0):
    c = _conn()
    c.execute("""INSERT INTO eye_contact_episodes
                 (session_id, start_time, duration_ms, phase)
                 VALUES (?, ?, ?, ?)""",
              (session_id, time.time(), duration_ms, phase))
    c.commit()
    c.close()


def log_joint_attention(session_id: int, trial: int,
                        success: bool, latency_ms: float):
    c = _conn()
    c.execute("""INSERT INTO joint_attention_episodes
                 (session_id, trial, timestamp, success, latency_ms)
                 VALUES (?, ?, ?, ?, ?)""",
              (session_id, trial, time.time(), int(success), latency_ms))
    c.commit()
    c.close()


def log_false_belief(session_id: int, trial: int,
                     correct: bool, latency_ms: float,
                     error_pattern: str = ""):
    c = _conn()
    c.execute("""INSERT INTO false_belief_trials
                 (session_id, trial, correct, latency_ms, error_pattern)
                 VALUES (?, ?, ?, ?, ?)""",
              (session_id, trial, int(correct), latency_ms, error_pattern))
    c.commit()
    c.close()


def log_response_time(session_id: int, stimulus_type: str,
                      latency_ms: float):
    c = _conn()
    c.execute("""INSERT INTO response_times
                 (session_id, stimulus_type, timestamp, latency_ms)
                 VALUES (?, ?, ?, ?)""",
              (session_id, stimulus_type, time.time(), latency_ms))
    c.commit()
    c.close()


def log_initiative(session_id: int, description: str = ""):
    c = _conn()
    c.execute("""INSERT INTO spontaneous_initiatives
                 (session_id, timestamp, description)
                 VALUES (?, ?, ?)""",
              (session_id, time.time(), description))
    c.commit()
    c.close()


def save_calibration(session_id: int, yaw_center: float, pitch_center: float):
    c = _conn()
    c.execute("""INSERT INTO calibration
                 (session_id, yaw_center, pitch_center, recorded_at)
                 VALUES (?, ?, ?, ?)""",
              (session_id, yaw_center, pitch_center, time.time()))
    c.commit()
    c.close()


def get_sessions():
    c = _conn()
    c.row_factory = sqlite3.Row
    rows = c.execute("""
        SELECT id, label, started_at, ended_at,
               (SELECT COUNT(*) FROM eye_contact_episodes WHERE session_id = sessions.id) as oe1_count,
               (SELECT COUNT(*) FROM joint_attention_episodes WHERE session_id = sessions.id) as oe2_count,
               (SELECT COUNT(*) FROM false_belief_trials WHERE session_id = sessions.id) as oe3_count,
               (SELECT COUNT(*) FROM response_times WHERE session_id = sessions.id) as oe4_count,
               (SELECT COUNT(*) FROM spontaneous_initiatives WHERE session_id = sessions.id) as oe5_count
        FROM sessions ORDER BY id
    """).fetchall()
    c.close()
    return [dict(r) for r in rows]


def get_session_summary(sid: int) -> dict:
    c = _conn()
    c.row_factory = sqlite3.Row

    session = c.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
    if not session:
        c.close()
        return {}

    o1 = c.execute("""
        SELECT COUNT(*) as count, COALESCE(AVG(duration_ms), 0) as avg_duration
        FROM eye_contact_episodes WHERE session_id = ?
    """, (sid,)).fetchone()

    o2 = c.execute("""
        SELECT COUNT(*) as count, COALESCE(AVG(success), 0) as success_rate
        FROM joint_attention_episodes WHERE session_id = ?
    """, (sid,)).fetchone()

    o3 = c.execute("""
        SELECT COUNT(*) as count, COALESCE(AVG(correct), 0) as accuracy
        FROM false_belief_trials WHERE session_id = ?
    """, (sid,)).fetchone()

    o4 = c.execute("""
        SELECT COUNT(*) as count, COALESCE(AVG(latency_ms), 0) as avg_latency
        FROM response_times WHERE session_id = ?
    """, (sid,)).fetchone()

    o5 = c.execute("""
        SELECT COUNT(*) as count FROM spontaneous_initiatives WHERE session_id = ?
    """, (sid,)).fetchone()

    cal = c.execute("""
        SELECT yaw_center, pitch_center FROM calibration
        WHERE session_id = ? ORDER BY id LIMIT 1
    """, (sid,)).fetchone()

    c.close()

    return {
        "session": {
            "id": session["id"],
            "label": session["label"],
            "started_at": session["started_at"],
            "ended_at": session["ended_at"],
        },
        "calibration": dict(cal) if cal else None,
        "oe1": {"count": o1["count"], "avg_duration_s": round(o1["avg_duration"] / 1000, 2)},
        "oe2": {"count": o2["count"], "success_rate": round(o2["success_rate"], 2),
                "trials": o2["count"]},
        "oe3": {"count": o3["count"], "accuracy": round(o3["accuracy"], 2)},
        "oe4": {"count": o4["count"], "avg_latency_ms": round(o4["avg_latency"], 1)},
        "oe5": {"count": o5["count"]},
    }


def get_cross_session_summary() -> list:
    sessions = get_sessions()
    return [get_session_summary(s["id"]) for s in sessions]


def get_session_report(sid: int) -> dict:
    c = _conn()
    c.row_factory = sqlite3.Row

    session = c.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
    if not session:
        c.close()
        return {}

    episodes = [dict(r) for r in c.execute(
        "SELECT * FROM eye_contact_episodes WHERE session_id = ? ORDER BY id", (sid,)).fetchall()]
    ja = [dict(r) for r in c.execute(
        "SELECT * FROM joint_attention_episodes WHERE session_id = ? ORDER BY trial", (sid,)).fetchall()]
    fb = [dict(r) for r in c.execute(
        "SELECT * FROM false_belief_trials WHERE session_id = ? ORDER BY trial", (sid,)).fetchall()]
    rt = [dict(r) for r in c.execute(
        "SELECT * FROM response_times WHERE session_id = ? ORDER BY id", (sid,)).fetchall()]
    init = [dict(r) for r in c.execute(
        "SELECT * FROM spontaneous_initiatives WHERE session_id = ? ORDER BY id", (sid,)).fetchall()]
    cal = c.execute(
        "SELECT * FROM calibration WHERE session_id = ? ORDER BY id LIMIT 1", (sid,)).fetchone()

    c.close()
    return {
        "session": dict(session),
        "calibration": dict(cal) if cal else None,
        "oe1_eye_contact": episodes,
        "oe2_joint_attention": ja,
        "oe3_false_belief": fb,
        "oe4_response_times": rt,
        "oe5_initiatives": init,
        "summary": get_session_summary(sid),
    }
