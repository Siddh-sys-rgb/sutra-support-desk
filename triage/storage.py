"""SQLite transactions enforce revisions and keep the original model suggestion."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

class Conflict(ValueError):
    pass

class Invalid(ValueError):
    pass

STATUSES = ("open", "in_progress", "resolved")
PRIORITIES = ("low", "normal", "high")
AGENTS = ("Unassigned", "Meera Shah", "Kavya Joshi", "Aarav Patel")
TRANSITIONS = {"open": {"open", "in_progress"}, "in_progress": {"in_progress", "open", "resolved"}, "resolved": {"resolved", "open"}}

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def connect(path):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=10000")
    return db

def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS tickets (
          id TEXT PRIMARY KEY, customer TEXT NOT NULL, email TEXT NOT NULL,
          subject TEXT NOT NULL, message TEXT NOT NULL, intent TEXT NOT NULL,
          priority TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
          assignee TEXT NOT NULL DEFAULT 'Unassigned', review_required INTEGER NOT NULL,
          prediction TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
          request_key TEXT UNIQUE, request_hash TEXT NOT NULL,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id TEXT NOT NULL REFERENCES tickets(id),
          action TEXT NOT NULL, actor TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ticket_created ON tickets(created_at);
        """)

def unpack(row):
    result = dict(row)
    result["prediction"] = json.loads(result["prediction"])
    result["review_required"] = bool(result["review_required"])
    result.pop("request_key", None)
    result.pop("request_hash", None)
    return result

def load(db, ticket_id):
    row = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
    if row is None:
        raise LookupError("Ticket not found.")
    return unpack(row)

def record(db, ticket_id, action, details, actor="Kavya Joshi"):
    db.execute("INSERT INTO events(ticket_id, action, actor, details, created_at) VALUES(?,?,?,?,?)", (ticket_id, action, actor, json.dumps(details), now()))

def insert(db, ticket_id, fields, prediction, request_key, request_hash):
    timestamp = now()
    with db:
        db.execute("""INSERT INTO tickets(id, customer, email, subject, message, intent,
            priority, review_required, prediction, request_key, request_hash, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (ticket_id, fields["customer"], fields["email"], fields["subject"], fields["message"], "unassigned" if prediction["review_required"] else prediction["predicted_intent"], fields["priority"], int(prediction["review_required"]), json.dumps(prediction), request_key, request_hash, timestamp, timestamp))
        record(db, ticket_id, "created", {"model_version": prediction["model_version"], "suggested_intent": prediction["predicted_intent"], "review_required": prediction["review_required"]}, actor=fields["customer"])
    return load(db, ticket_id)

def update(db, ticket_id, fields, revision):
    try:
        db.execute("BEGIN IMMEDIATE")
        old = load(db, ticket_id)
        if old["revision"] != revision:
            raise Conflict("This ticket changed in another tab. Reload before saving.")
        if fields["status"] not in TRANSITIONS[old["status"]]:
            raise Invalid("Start work before resolving an open ticket; reopen a resolved ticket before starting work.")
        reviewed = not old["review_required"] or fields["reviewed"]
        if fields["intent"] != old["intent"] and not fields["reviewed"]:
            raise Invalid("Confirm human review when correcting the routing intent.")
        if fields["reviewed"] and fields["intent"] == "unassigned":
            raise Invalid("Choose a routing intent before confirming human review.")
        if fields["status"] == "resolved" and (not reviewed or fields["intent"] == "unassigned" or fields["assignee"] == "Unassigned"):
            raise Invalid("Resolution needs a reviewed routing intent and an assigned teammate.")
        changed = {key: {"before": old[key], "after": fields[key]} for key in ("intent", "priority", "status", "assignee") if old[key] != fields[key]}
        if fields["reviewed"]:
            changed["human_review"] = True
        if not changed:
            raise Invalid("No changes to save.")
        db.execute("""UPDATE tickets SET intent=?, priority=?, status=?, assignee=?,
            review_required=?, revision=revision+1, updated_at=? WHERE id=?""", (fields["intent"], fields["priority"], fields["status"], fields["assignee"], int(not reviewed), now(), ticket_id))
        record(db, ticket_id, "reviewed" if fields["reviewed"] else "updated", changed)
        db.commit()
        return load(db, ticket_id)
    except Exception:
        db.rollback()
        raise
