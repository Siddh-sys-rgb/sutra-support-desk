"""Evaluate held-out labels and review coverage; never fit on evaluation examples."""
import argparse
import json
import sys
from pathlib import Path
from sklearn.metrics import confusion_matrix, f1_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from triage.model import INTENTS, TriageModel


def evaluate(model, rows):
    results = [{"id": row["id"], "expected": row.get("intent"), "kind": row.get("kind", "intent"), "prediction": model.classify(row["text"])} for row in rows]
    labelled = [row for row in results if row["expected"] in INTENTS]
    covered = [row for row in labelled if not row["prediction"]["review_required"]]
    expected = [row["expected"] for row in labelled]
    predicted = [row["prediction"]["predicted_intent"] for row in labelled]
    correct = lambda values: sum(row["expected"] == row["prediction"]["predicted_intent"] for row in values)
    summary = {"model_version": model.version, "training_examples": model.training_size, "labelled_examples": len(labelled), "top_intent_accuracy": correct(labelled) / len(labelled) if labelled else None, "macro_f1": float(f1_score(expected, predicted, labels=list(INTENTS), average="macro", zero_division=0)) if labelled else None, "suggestion_coverage": len(covered) / len(labelled) if labelled else None, "accepted_suggestion_accuracy": correct(covered) / len(covered) if covered else None, "held_for_review": len(labelled) - len(covered), "confusion_matrix_order": list(INTENTS), "confusion_matrix": confusion_matrix(expected, predicted, labels=list(INTENTS)).tolist() if labelled else [], "review_checks": {}}
    for kind in ("out_of_domain", "ambiguous"):
        checks = [row for row in results if row["kind"] == kind]
        summary["review_checks"][kind] = {"total": len(checks), "held_for_review": sum(row["prediction"]["review_required"] for row in checks)}
    return {"summary": summary, "results": results, "caveat": "Synthetic evaluation only. Accuracy on these examples does not establish production performance or calibrated probabilities."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-data", type=Path)
    parser.add_argument("--evaluation-data", type=Path, default=ROOT / "data/evaluation.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    model = TriageModel(args.training_data)
    if args.evaluation_data.stat().st_size > 4 * 1024 * 1024:
        parser.error("Evaluation JSON must be at most 4 MB.")
    rows = json.loads(args.evaluation_data.read_text())
    if not isinstance(rows, list) or not 1 <= len(rows) <= 10000:
        parser.error("Evaluation JSON must contain 1 to 10000 examples.")
    training = json.loads((args.training_data or ROOT / "data/training.json").read_text())
    keys = {" ".join(row["text"].casefold().split()) for row in training}
    if any(" ".join(row["text"].casefold().split()) in keys for row in rows):
        parser.error("Training and evaluation texts overlap; keep them separate.")
    report = evaluate(model, rows)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["summary"], indent=2))

if __name__ == "__main__":
    main()
