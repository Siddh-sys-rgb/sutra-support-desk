"""Flask HTTP boundary: bounded input, CSRF, same-origin checks and typed fields."""
import hashlib
import json
import re
import secrets
import sqlite3
import uuid
from pathlib import Path

from flask import Flask, g, jsonify, render_template, request, session
from werkzeug.exceptions import HTTPException

from .model import INTENTS, LABELS, TriageModel
from . import storage

ROOT = Path(__file__).resolve().parents[1]

def text(value, label, limit, required=True):
    if not isinstance(value, str):
        raise storage.Invalid(f"{label} must be text.")
    value = value.strip()
    if (required and not value) or len(value) > limit:
        raise storage.Invalid(f"{label} must contain {'1' if required else '0'} to {limit} characters.")
    if any(ord(char) < 32 and char not in "\n\t" for char in value):
        raise storage.Invalid(f"{label} contains unsupported control characters.")
    return value

def new_fields(body):
    fields = {"customer": text(body.get("customer"), "Customer name", 80), "email": text(body.get("email", ""), "Email", 160, False), "subject": text(body.get("subject"), "Subject", 140), "message": text(body.get("message"), "Message", 4000), "priority": body.get("priority", "normal")}
    if fields["email"] and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", fields["email"]):
        raise storage.Invalid("Enter a valid email or leave it blank.")
    if fields["priority"] not in storage.PRIORITIES:
        raise storage.Invalid("Unknown priority.")
    return fields

def edit_fields(body):
    values = {key: body.get(key) for key in ("intent", "priority", "status", "assignee")}
    for key, options in [("intent", (*INTENTS, "unassigned")), ("priority", storage.PRIORITIES), ("status", storage.STATUSES), ("assignee", storage.AGENTS)]:
        if values[key] not in options:
            raise storage.Invalid(f"Unknown {key}.")
    reviewed = body.get("reviewed", False)
    if type(reviewed) is not bool:
        raise storage.Invalid("Human review must be true or false.")
    values["reviewed"] = reviewed
    revision = body.get("revision")
    if type(revision) is not int or revision < 1:
        raise storage.Invalid("A positive integer revision is required.")
    return values, revision

def create_app(config=None):
    app = Flask(__name__, instance_path=str(ROOT / "instance"))
    app.config.update(DATA_DIR=str(ROOT / "instance"), SEED_DEMO=True, MAX_CONTENT_LENGTH=32 * 1024, TRUSTED_HOSTS=["localhost", "127.0.0.1", "[::1]"], SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict", SESSION_COOKIE_NAME="sutra_session")
    if config:
        app.config.update(config)
    directory = Path(app.config["DATA_DIR"])
    directory.mkdir(parents=True, exist_ok=True)
    app.config["DATABASE"] = str(directory / "triage.db")
    if not app.config.get("SECRET_KEY"):
        key_path = directory / "session.key"
        try:
            with key_path.open("x") as handle:
                handle.write(secrets.token_hex(32))
            key_path.chmod(0o600)
        except FileExistsError:
            pass
        app.config["SECRET_KEY"] = key_path.read_text()
    storage.initialize(app.config["DATABASE"])
    app.extensions["triage_model"] = app.config.get("MODEL") or TriageModel(app.config.get("TRAINING_DATA"))

    def db():
        if "db" not in g:
            g.db = storage.connect(app.config["DATABASE"])
        return g.db

    @app.teardown_appcontext
    def close_db(_error):
        connection = g.pop("db", None)
        if connection is not None:
            connection.close()

    @app.before_request
    def require_csrf():
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("Origin")
            if origin and origin != request.host_url.rstrip("/"):
                return jsonify(error="A same-origin request is required."), 403
            token = request.headers.get("X-CSRF-Token", "")
            expected = session.get("csrf", "")
            if not expected or not secrets.compare_digest(token.encode("utf-8"), expected.encode("ascii")):
                return jsonify(error="Session token missing or expired. Reload the page."), 403

    @app.after_request
    def headers(response):
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(Exception)
    def handle_error(error):
        if isinstance(error, HTTPException):
            return jsonify(error=error.description), error.code
        if isinstance(error, storage.Conflict):
            return jsonify(error=str(error)), 409
        if isinstance(error, storage.Invalid):
            return jsonify(error=str(error)), 422
        if isinstance(error, LookupError):
            return jsonify(error=str(error)), 404
        app.logger.exception("Request failed")
        return jsonify(error="The request could not be completed."), 500

    def body():
        value = request.get_json()
        if not isinstance(value, dict):
            raise storage.Invalid("A JSON object is required.")
        return value

    def stats():
        rows = db().execute("SELECT status, review_required, COUNT(*) AS n FROM tickets GROUP BY status, review_required").fetchall()
        return {"total": sum(row["n"] for row in rows), "open": sum(row["n"] for row in rows if row["status"] == "open"), "in_progress": sum(row["n"] for row in rows if row["status"] == "in_progress"), "resolved": sum(row["n"] for row in rows if row["status"] == "resolved"), "needs_review": sum(row["n"] for row in rows if row["review_required"])}

    @app.get("/")
    def home():
        return render_template("index.html")

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", app="Sutra Support Desk", model=app.extensions["triage_model"].version)

    @app.get("/api/bootstrap")
    def bootstrap():
        session.setdefault("csrf", secrets.token_hex(24))
        model = app.extensions["triage_model"]
        return jsonify(csrf=session["csrf"], store="Aangan Online", agent="Kavya Joshi", intents=LABELS, agents=storage.AGENTS, stats=stats(), model={"version": model.version, "training_examples": model.training_size, "threshold": model.threshold, "margin_threshold": model.margin_threshold, "source": model.source, "note": "Uncalibrated model scores, not guarantees. Check training provenance."})

    @app.get("/api/tickets")
    def tickets():
        queue = request.args.get("queue", "all")
        if queue not in {"all", "review", *storage.STATUSES}:
            raise storage.Invalid("Unknown inbox queue.")
        query = text(request.args.get("q", ""), "Search", 120, False)
        # Bound the interactive demo to the newest 500 records; no user SQL is constructed.
        rows = db().execute("SELECT * FROM tickets ORDER BY created_at DESC, rowid DESC LIMIT 500").fetchall()
        items = [storage.unpack(row) for row in rows]
        if queue != "all":
            items = [row for row in items if row["review_required"]] if queue == "review" else [row for row in items if row["status"] == queue]
        if query:
            items = [row for row in items if query.casefold() in (row["customer"] + " " + row["subject"] + " " + row["message"]).casefold()]
        return jsonify(tickets=items, stats=stats(), limit=500)

    @app.post("/api/tickets")
    def create_ticket():
        payload = body()
        fields = new_fields(payload)
        key = payload.get("request_key")
        if key is not None:
            key = text(key, "Request key", 100)
        digest = hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()
        if key:
            existing = db().execute("SELECT id, request_hash FROM tickets WHERE request_key=?", (key,)).fetchone()
            if existing:
                if existing["request_hash"] != digest:
                    raise storage.Conflict("That request key belongs to a different ticket submission.")
                return jsonify(ticket=storage.load(db(), existing["id"]), replayed=True), 200
        prediction = app.extensions["triage_model"].classify(fields["subject"] + " " + fields["message"])
        try:
            item = storage.insert(db(), uuid.uuid4().hex, fields, prediction, key, digest)
        except sqlite3.IntegrityError:
            existing = db().execute("SELECT id, request_hash FROM tickets WHERE request_key=?", (key,)).fetchone()
            if not existing or existing["request_hash"] != digest:
                raise storage.Conflict("This request key was already used.")
            return jsonify(ticket=storage.load(db(), existing["id"]), replayed=True), 200
        return jsonify(ticket=item, replayed=False), 201

    @app.get("/api/tickets/<ticket_id>")
    def detail(ticket_id):
        item = storage.load(db(), ticket_id)
        rows = db().execute("SELECT id, subject, message, customer, status FROM tickets WHERE id!=? ORDER BY created_at DESC, rowid DESC LIMIT 500", (ticket_id,)).fetchall()
        similar = app.extensions["triage_model"].similar(item["subject"] + " " + item["message"], [dict(row) for row in rows])
        events = [dict(row) for row in db().execute("SELECT * FROM events WHERE ticket_id=? ORDER BY id DESC", (ticket_id,))]
        for event in events:
            event["details"] = json.loads(event["details"])
        return jsonify(ticket=item, similar=similar, events=events)

    @app.patch("/api/tickets/<ticket_id>")
    def edit(ticket_id):
        fields, revision = edit_fields(body())
        return jsonify(ticket=storage.update(db(), ticket_id, fields, revision))

    if app.config["SEED_DEMO"]:
        with app.app_context():
            if db().execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 0:
                from .demo import seed
                seed(db(), app.extensions["triage_model"])
    return app
