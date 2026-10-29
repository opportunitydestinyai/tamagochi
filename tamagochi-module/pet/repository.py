"""Versioned SQLite repository with an atomic state + events + awards transaction."""
from __future__ import annotations

import contextlib
import json
import sqlite3
from pathlib import Path

from .model import DEFAULT_CONFIG, initial_state, now_utc, validate_config

SCHEMA_VERSION = 2


def dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


class PetRepository:
    def __init__(self, path: str | Path, *, clock=now_utc, initial_config=None):
        self.path = Path(path)
        self.clock = clock
        self.initial_config = validate_config(initial_config if initial_config is not None else DEFAULT_CONFIG)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def connect(self):
        conn = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def _migrate(self):
        conn = self.connect()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("BEGIN IMMEDIATE")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError(f"Banco mais novo ({version}) que este protótipo ({SCHEMA_VERSION}).")
            if version == 0:
                # Statements are individual: executescript would commit the migration early.
                for statement in (
                    "CREATE TABLE pet (pet_id TEXT PRIMARY KEY, state_json TEXT NOT NULL, config_json TEXT NOT NULL)",
                    "CREATE TABLE processed_events (event_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, event_type TEXT NOT NULL, processed_at TEXT NOT NULL)",
                    "CREATE TABLE logical_events (event_type TEXT NOT NULL, logical_key TEXT NOT NULL, PRIMARY KEY(event_type, logical_key))",
                    "CREATE TABLE xp_awards (id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL, reason TEXT NOT NULL, amount INTEGER NOT NULL, day TEXT NOT NULL, logical_key TEXT UNIQUE, created_at TEXT NOT NULL, UNIQUE(event_id, reason))",
                    "CREATE INDEX xp_awards_day_reason ON xp_awards(day, reason)",
                    "CREATE TABLE pet_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE, event_type TEXT NOT NULL, timestamp TEXT NOT NULL, source TEXT NOT NULL, payload_json TEXT NOT NULL)",
                    "CREATE TABLE memories (id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL, event_id TEXT)",
                    "CREATE INDEX memories_created_at ON memories(created_at DESC)",
                    "CREATE TABLE autonomy_history (id TEXT PRIMARY KEY, activity TEXT NOT NULL, status TEXT NOT NULL, summary TEXT NOT NULL, created_at TEXT NOT NULL, scheduled INTEGER NOT NULL)",
                ):
                    conn.execute(statement)
                conn.execute("PRAGMA user_version=1")
                version = 1
            if version == 1:
                # v2 adds a configurable local conversation length threshold.
                # Preserve all user settings and XP; validate before committing.
                for row in conn.execute("SELECT pet_id, config_json FROM pet").fetchall():
                    config = json.loads(row["config_json"])
                    config.setdefault("meaningfulChatMinChars", DEFAULT_CONFIG["meaningfulChatMinChars"])
                    validate_config(config)
                    conn.execute("UPDATE pet SET config_json=? WHERE pet_id=?", (dump(config), row["pet_id"]))
                conn.execute("PRAGMA user_version=2")
            if conn.execute("SELECT 1 FROM pet WHERE pet_id='SL-001'").fetchone() is None:
                config = json.loads(dump(self.initial_config))
                conn.execute("INSERT INTO pet VALUES (?, ?, ?)", ("SL-001", dump(initial_state(config, self.clock())), dump(config)))
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextlib.contextmanager
    def transaction(self):
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def load(self, conn):
        row = conn.execute("SELECT state_json, config_json FROM pet WHERE pet_id='SL-001'").fetchone()
        if row is None:
            raise RuntimeError("Estado do SL-001 ausente; nenhum dado será substituído.")
        # A corrupt state is surfaced rather than silently resetting the pet.
        return json.loads(row["state_json"]), json.loads(row["config_json"])

    @staticmethod
    def save(conn, state, config):
        cursor = conn.execute("UPDATE pet SET state_json=?, config_json=? WHERE pet_id='SL-001'",
                              (dump(state), dump(config)))
        if cursor.rowcount != 1:
            raise RuntimeError("Não foi possível salvar o estado do pet.")

    def integrity(self):
        with contextlib.closing(self.connect()) as conn:
            return conn.execute("PRAGMA integrity_check").fetchone()[0]
