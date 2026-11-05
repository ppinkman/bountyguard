"""Durable bounties, single-use challenges, immutable reviews and operation intents."""
from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3
import time
import uuid

from .domain import GuardError, canonical, digest
from .limits import development_limit


class Store:
    def __init__(self, path):
        self.path = str(Path(path).resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS bounties (
                    id TEXT PRIMARY KEY, version INTEGER NOT NULL DEFAULT 0,
                    state TEXT NOT NULL, creator_id INTEGER NOT NULL,
                    document TEXT NOT NULL, created_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS challenges (
                    id TEXT PRIMARY KEY, actor_id INTEGER NOT NULL, bounty_id TEXT NOT NULL,
                    purpose TEXT NOT NULL, expires_at INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0,
                    document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS bindings (
                    bounty_id TEXT NOT NULL, actor_id INTEGER NOT NULL, purpose TEXT NOT NULL,
                    document TEXT NOT NULL, PRIMARY KEY(bounty_id,actor_id,purpose));
                CREATE TABLE IF NOT EXISTS claims (
                    id TEXT PRIMARY KEY, bounty_id TEXT NOT NULL, actor_id INTEGER NOT NULL,
                    document TEXT NOT NULL, UNIQUE(bounty_id,actor_id));
                CREATE TABLE IF NOT EXISTS reviews (
                    fingerprint TEXT PRIMARY KEY, bounty_id TEXT NOT NULL,
                    document TEXT NOT NULL, created_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS ai_calls (
                    fingerprint TEXT PRIMARY KEY, created_at INTEGER NOT NULL,
                    state TEXT NOT NULL, document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS operations (
                    id TEXT PRIMARY KEY, bounty_id TEXT NOT NULL, kind TEXT NOT NULL,
                    intent_hash TEXT NOT NULL, state TEXT NOT NULL, document TEXT NOT NULL,
                    created_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, bounty_id TEXT NOT NULL,
                    kind TEXT NOT NULL, document TEXT NOT NULL, created_at INTEGER NOT NULL);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def get(self, bounty_id):
        with self.connection() as db:
            row = db.execute("SELECT document,version,state FROM bounties WHERE id=?", (bounty_id,)).fetchone()
        if not row:
            raise GuardError("Bounty not found.", 404)
        return {**json.loads(row["document"]), "version": row["version"], "state": row["state"]}

    def list(self):
        with self.connection() as db:
            rows = db.execute("SELECT id FROM bounties ORDER BY created_at DESC,id LIMIT 100").fetchall()
        return [self.get(r[0]) for r in rows]

    def create(self, document):
        with self.connection() as db:
            db.execute("INSERT INTO bounties VALUES (?,0,'DRAFT',?,?,?)", (document["id"], document["creator_id"], canonical(document), int(time.time())))
        return self.get(document["id"])

    def save(self, document, state, event, detail=None):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            result = db.execute("UPDATE bounties SET document=?,state=?,version=version+1 WHERE id=? AND version=?", (canonical(document), state, document["id"], document["version"]))
            if result.rowcount != 1:
                raise GuardError("Bounty changed concurrently. Reload its current state.")
            db.execute("INSERT INTO events(bounty_id,kind,document,created_at) VALUES (?,?,?,?)", (document["id"], event, canonical(detail or {}), int(time.time())))
        return self.get(document["id"])

    def binding(self, bounty_id, actor_id, purpose):
        with self.connection() as db:
            row = db.execute("SELECT document FROM bindings WHERE bounty_id=? AND actor_id=? AND purpose=?", (bounty_id, actor_id, purpose)).fetchone()
        if not row:
            raise GuardError("Complete the GitHub-bound wallet signature first.")
        return json.loads(row[0])

    def operation(self, operation_id, bounty_id, kind, intent):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            if row:
                if row["intent_hash"] != digest(intent):
                    raise GuardError("Operation was already bound to different terms.")
                if row["state"] == "NOT_SIGNED":
                    pending = db.execute("SELECT id FROM operations WHERE id<>? AND state IN ('PREPARED','SUBMITTED','UNKNOWN') AND json_extract(document,'$.intent.signer')=?", (operation_id, intent.get("signer"))).fetchone()
                    if pending:
                        raise GuardError("Another operation already reserved this signer: " + pending[0])
                    db.execute("UPDATE operations SET state='PREPARED' WHERE id=?", (operation_id,))
                    return dict(row), True
                return dict(row), False
            if kind == "fund_assigned" and db.execute("SELECT COUNT(*) FROM operations WHERE kind='fund_assigned'").fetchone()[0] >= development_limit("funding"):
                raise GuardError("This project's configured funding-intent development limit was reached.")
            pending = db.execute("SELECT id FROM operations WHERE state IN ('PREPARED','SUBMITTED','UNKNOWN') AND json_extract(document,'$.intent.signer')=?", (intent.get("signer"),)).fetchone()
            if pending:
                raise GuardError("Reconcile the signer's original pending operation first: " + pending[0])
            db.execute("INSERT INTO operations VALUES (?,?,?,?,?,?,?)", (operation_id, bounty_id, kind, digest(intent), "PREPARED", canonical({"intent": intent}), int(time.time())))
            row = dict(db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone())
        return row, True

    def events(self, bounty_id):
        with self.connection() as db:
            return [{**dict(row), "document": json.loads(row["document"])} for row in db.execute("SELECT * FROM events WHERE bounty_id=? ORDER BY id", (bounty_id,))]

    def operations(self, bounty_id):
        with self.connection() as db:
            rows = db.execute("SELECT * FROM operations WHERE bounty_id=? ORDER BY created_at,id", (bounty_id,)).fetchall()
        return [{"id": row["id"], "kind": row["kind"], "state": row["state"], "intent_hash": row["intent_hash"], "transaction_hash": json.loads(row["document"]).get("tx_hash"), "receipt": json.loads(row["document"]).get("receipt")} for row in rows]
