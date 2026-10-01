"""Fictional Indian shop conversations, separate from model training/evaluation."""
import hashlib
from . import storage

TICKETS = [
    ("demo-parcel", "Aarav Desai", "Parcel still in transit", "My parcel tracking link says delivery delayed. The courier has not delivered my package to Ahmedabad."),
    ("demo-refund", "Meera Patel", "Waiting for my money back", "I returned my shoes last week. Please check the refund status; the money has not reached my bank account."),
    ("demo-mixed", "Rohan Shah", "Broken bottle, what next?", "The item is broken and I want a refund. I could also exchange it if a replacement is available."),
    ("demo-payment", "Ishita Nair", "UPI payment debited twice", "My UPI payment failed at checkout but money was debited twice for the same payment transaction."),
    ("demo-related", "Priya Joshi", "Delivery delayed again", "My parcel tracking link says delivery delayed. The courier has not delivered my package to Ahmedabad."),
    ("demo-unknown", "Dev Trivedi", "A different kind of request", "Can your team arrange a birthday party for my sister in Surat?"),
]

def seed(db, model):
    for ticket_id, customer, subject, message in TICKETS:
        fields = {"customer": customer, "email": "", "subject": subject, "message": message, "priority": "high" if ticket_id == "demo-payment" else "normal"}
        prediction = model.classify(subject + " " + message)
        storage.insert(db, ticket_id, fields, prediction, None, hashlib.sha256(ticket_id.encode()).hexdigest())
    item = storage.load(db, "demo-refund")
    storage.update(db, item["id"], {"intent": "refund", "priority": "normal", "status": "in_progress", "assignee": "Meera Shah", "reviewed": True}, item["revision"])
