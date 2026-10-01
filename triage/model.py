"""Small, inspectable learned classifier; no pickle or remote inference."""
import json
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity

INTENTS = ("delivery", "refund", "cancellation", "payment", "product", "account")
LABELS = {"delivery": "Delivery & tracking", "refund": "Returns & refunds", "cancellation": "Order cancellation", "payment": "Payment trouble", "product": "Product & exchange", "account": "Account access"}
ROOT = Path(__file__).resolve().parents[1]

class TriageModel:
    threshold = 0.58
    margin_threshold = 0.18

    def __init__(self, training_path=None):
        rows = json.loads(Path(training_path or ROOT / "data/training.json").read_text())
        if not rows or any(row["intent"] not in INTENTS for row in rows):
            raise ValueError("Training examples must use the six supported intents.")
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english", max_features=6000)
        matrix = self.vectorizer.fit_transform([row["text"] for row in rows])
        self.classifier = LogisticRegression(C=6.0, max_iter=1000, random_state=17)
        self.classifier.fit(matrix, [row["intent"] for row in rows])
        self.training_size = len(rows)
        self.version = "tfidf-logreg-original-v1"
        self.features = self.vectorizer.get_feature_names_out()

    def classify(self, text):
        vector = self.vectorizer.transform([text])
        scores = self.classifier.predict_proba(vector)[0]
        ranked = sorted(zip(self.classifier.classes_, scores), key=lambda item: item[1], reverse=True)
        predicted, score = ranked[0]
        margin = score - ranked[1][1]
        # No learned vocabulary match is an explicit reason to abstain.
        uncertain = vector.nnz == 0 or score < self.threshold or margin < self.margin_threshold
        reason = "No recognised training vocabulary" if vector.nnz == 0 else ("Low model score" if score < self.threshold else ("Two intents are close" if margin < self.margin_threshold else "Clear model suggestion"))
        class_index = list(self.classifier.classes_).index(predicted)
        contributions = vector.toarray()[0] * self.classifier.coef_[class_index]
        indices = np.argsort(contributions)[::-1]
        evidence = [str(self.features[i]) for i in indices if contributions[i] > 0][:5]
        return {"predicted_intent": str(predicted), "score": round(float(score), 4), "margin": round(float(margin), 4), "review_required": bool(uncertain), "reason": reason, "scores": [{"intent": str(label), "score": round(float(value), 4)} for label, value in ranked], "evidence": evidence, "model_version": self.version}

    def similar(self, text, candidates, limit=3):
        if not candidates:
            return []
        left = self.vectorizer.transform([text])
        right = self.vectorizer.transform([row["subject"] + " " + row["message"] for row in candidates])
        values = cosine_similarity(left, right)[0]
        normal = lambda value: " ".join(value.casefold().split())
        result = []
        for row, score in zip(candidates, values):
            exact = normal(text) == normal(row["subject"] + " " + row["message"])
            if exact or score >= 0.38:
                result.append({"id": row["id"], "subject": row["subject"], "customer": row["customer"], "status": row["status"], "score": round(float(score), 4), "exact": exact})
        return sorted(result, key=lambda row: (row["exact"], row["score"]), reverse=True)[:limit]
