"""Reproduce the original, fictional English examples shipped with this project."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAIN = {
    "delivery": [
        "My delivery is late and the parcel has not arrived", "Track my order and tell me the delivery date",
        "The courier marked my package delivered but I did not receive it", "Where is my shipment tracking number",
        "My parcel is stuck in transit for three days", "The delivery driver could not find my address",
        "Please update the delivery address for my package", "My shipment arrived at the wrong address",
        "When will my order be delivered to Ahmedabad", "The parcel tracking link says delivery delayed",
        "My courier delivery is missing and tracking has not moved", "I need the shipping status of my package",
    ],
    "refund": [
        "I returned my order and need my refund", "The refund has not reached my bank account",
        "Please refund the money for the returned item", "How long will my refund take after returning the product",
        "I received only a partial refund for my return", "My return is accepted but the refund is pending",
        "Send my refund to the original payment method", "Can I get my money back for this returned order",
        "I want to return this purchase and request a refund", "The refund amount for my returned shoes is incorrect",
        "My return pickup is done but the money has not been refunded", "Please check the refund status of my returned parcel",
    ],
    "cancellation": [
        "Please cancel my order before it ships", "I placed the wrong order and want to cancel it",
        "Can I cancel my purchase today", "Cancel the duplicate order I placed by mistake",
        "I cannot find the order cancellation button", "Stop this order from being shipped and cancel it",
        "I no longer need the item please cancel the order", "My cancellation request is still pending",
        "Please confirm that my order has been cancelled", "I want to withdraw my order before dispatch",
        "Cancel my order because I selected the wrong size", "I changed my mind and need to cancel this purchase",
    ],
    "payment": [
        "My UPI payment failed but money was debited", "I was charged twice for the same payment",
        "The checkout payment page shows an error", "My card payment was declined during checkout",
        "UPI says payment successful but the order is not confirmed", "I cannot pay with my debit card",
        "The payment transaction timed out and money left my account", "Cash on delivery is not available at checkout",
        "How can I change the payment method for my purchase", "My payment is pending in the UPI application",
        "I need an invoice for the payment transaction", "The payment gateway is rejecting my card",
    ],
    "product": [
        "The product arrived damaged with a broken screen", "I received the wrong size and need a replacement",
        "The item is defective and does not work", "My package contains the wrong product",
        "The colour of the shirt is different from the listing", "One item is missing from the product box",
        "I need to exchange these shoes for a larger size", "The charger is broken and I want a replacement",
        "The product quality is poor and the material is torn", "The delivered item is faulty and needs an exchange",
        "The glass bottle was damaged and leaking when I opened it", "I ordered blue but received a red product",
    ],
    "account": [
        "I cannot log into my account", "Please help me reset my password",
        "The login OTP has not arrived on my phone", "I forgot my password and cannot sign in",
        "My account is locked after multiple login attempts", "How can I change my account email address",
        "The password reset link has expired", "I need help updating my profile phone number",
        "My login verification code is not working", "I cannot access my shopping account",
        "Please delete my account and personal profile", "My account login says invalid password",
    ],
}
HELDOUT = {
    "delivery": ["The courier still has my parcel; when will it arrive?", "Tracking shows delivered yesterday, but nothing came to my door.", "The shipping status has not changed all week.", "Can the delivery address be changed before my package arrives?"],
    "refund": ["My returned bag was collected, but I am waiting for my money back.", "A refund was promised last week and it is still pending.", "The return refund credited to my bank is less than expected.", "How do I check when the refunded amount will arrive?"],
    "cancellation": ["I accidentally bought two; please cancel the extra order.", "Please stop dispatching my purchase, I wish to cancel it.", "The cancellation I submitted yesterday is not confirmed.", "I do not want this order anymore; can it be cancelled?"],
    "payment": ["My UPI transfer completed but checkout failed.", "Two card charges appeared for one transaction.", "The payment gateway gives an error each time I pay.", "Money was taken after a transaction timeout during payment."],
    "product": ["My new headphones do not work and need replacing.", "The shirt in the box is the wrong colour and size.", "A cracked bottle arrived and the product is leaking.", "Please exchange the faulty charger for a working one."],
    "account": ["I keep getting an invalid password error when signing in.", "The OTP for login never reaches my mobile.", "I need a new password reset link for my account.", "My profile has an old email address; how can I update it?"],
}
OOD = ["What is the weather in Surat?", "Tell me a story about a dragon.", "Please arrange a birthday party for my uncle.", "How do I cook dal and rice?", "hello", "The moon is bright tonight"]
AMBIGUOUS = ["The item is broken and I want a refund.", "Cancel the order because my payment failed.", "My parcel did not arrive and I want my money back."]

def main():
    train = [{"id": f"train-{intent}-{i+1:02}", "text": text, "intent": intent} for intent, texts in TRAIN.items() for i, text in enumerate(texts)]
    test = [{"id": f"test-{intent}-{i+1:02}", "text": text, "intent": intent, "kind": "intent"} for intent, texts in HELDOUT.items() for i, text in enumerate(texts)]
    test += [{"id": f"ood-{i+1:02}", "text": text, "intent": None, "kind": "out_of_domain"} for i, text in enumerate(OOD)]
    test += [{"id": f"ambiguous-{i+1:02}", "text": text, "intent": None, "kind": "ambiguous"} for i, text in enumerate(AMBIGUOUS)]
    for name, rows in [("training.json", train), ("evaluation.json", test)]:
        (ROOT / "data" / name).write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
