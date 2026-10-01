"""Opt-in, bounded public-data experiment. Imported data stays in ignored instance/."""
import argparse
import csv
import hashlib
import json
import random
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from sklearn.cluster import DBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset"
REVISION = "430d1a8"
FILENAME = "Bitext_Sample_Customer_Support_Training_Dataset_27K_responses-v11.csv"
URL = f"{SOURCE}/resolve/{REVISION}/{FILENAME}"
LICENSE = "https://cdla.dev/sharing-1-0/"
LIMIT_BYTES = 32 * 1024 * 1024
MAPPING = {
    "track_order": "delivery", "delivery_period": "delivery", "delivery_options": "delivery", "change_shipping_address": "delivery",
    "get_refund": "refund", "track_refund": "refund", "check_refund_policy": "refund",
    "cancel_order": "cancellation",
    "payment_issue": "payment", "check_payment_methods": "payment", "get_invoice": "payment",
    "recover_password": "account", "edit_account": "account", "delete_account": "account", "registration_problems": "account",
}

def canonical(value):
    value = re.sub(r"\{\{.*?\}\}", " entity ", value.casefold())
    return " ".join(re.findall(r"[a-z0-9]+", value))

def download(target):
    # Fixed publisher URL, no user URL or runtime web scraping; bound network read.
    request = urllib.request.Request(URL, headers={"User-Agent": "Sutra-local-dataset-experiment/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        blob = response.read(LIMIT_BYTES + 1)
    if len(blob) > LIMIT_BYTES:
        raise ValueError("Dataset exceeds the 32 MB download limit.")
    target.write_bytes(blob)

def split_csv(path, per_intent=60):
    if not 20 <= per_intent <= 200 or path.stat().st_size > LIMIT_BYTES:
        raise ValueError("Use 20 to 200 rows per mapped intent and a CSV no larger than 32 MB.")
    pools = {label: {} for label in set(MAPPING.values())}
    seen = {}
    conflicts = set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not {"instruction", "intent"}.issubset(reader.fieldnames or []):
            raise ValueError("Expected the publisher's instruction and intent CSV columns.")
        for index, row in enumerate(reader):
            if index >= 50000:
                raise ValueError("CSV exceeds the 50000-row scan limit.")
            label = MAPPING.get(row["intent"])
            value = row["instruction"].strip()
            if not label or not 1 <= len(value) <= 4000:
                continue
            key = canonical(value)
            if not key:
                continue
            if key in seen and seen[key] != label:
                conflicts.add(key)
            seen[key] = label
            pools[label].setdefault(key, {"text": value, "intent": label, "source_intent": row["intent"], "source": "Bitext Innovations, 2024"})
    selected = []
    for label, values in sorted(pools.items()):
        rows = [row for key, row in sorted(values.items(), key=lambda item: hashlib.sha256(item[0].encode()).hexdigest()) if key not in conflicts][:per_intent]
        if len(rows) < 20:
            raise ValueError(f"Not enough distinct mapped examples for {label}.")
        selected.extend(rows)
    matrix = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), max_features=12000).fit_transform([canonical(row["text"]) for row in selected])
    clusters = DBSCAN(eps=0.14, min_samples=1, metric="cosine").fit_predict(matrix)
    train, test = [], []
    rng = random.Random(17)
    for label in sorted(pools):
        groups = sorted({int(cluster) for row, cluster in zip(selected, clusters) if row["intent"] == label})
        if len(groups) < 2:
            raise ValueError(f"Not enough independent text groups for {label}.")
        rng.shuffle(groups)
        held = set(groups[:max(1, len(groups) // 5)])
        for index, (row, cluster) in enumerate(zip(selected, clusters)):
            if row["intent"] == label:
                result = {**row, "id": f"bitext-{index:04}", "group": int(cluster), "kind": "intent"}
                (test if int(cluster) in held else train).append(result)
    return train, test

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Download the fixed publisher CSV; otherwise use a previously downloaded local CSV")
    parser.add_argument("--accept-license", action="store_true", help="Confirm you read CDLA-Sharing-1.0 and its redistribution terms")
    parser.add_argument("--per-intent", type=int, default=60)
    args = parser.parse_args()
    if not args.accept_license:
        parser.error(f"Read {LICENSE} and the dataset card, then use --accept-license.")
    output = ROOT / "instance/bitext"
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / FILENAME
    try:
        if args.download:
            download(csv_path)
        imported_train, imported_test = split_csv(csv_path, args.per_intent)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Import failed: {error}\n")
    original_train = json.loads((ROOT / "data/training.json").read_text())
    original_test = json.loads((ROOT / "data/evaluation.json").read_text())
    # Preserve the app's product intent: the source has no clean product-fault label.
    # Remove any exact cross-source match rather than silently leaking it across splits.
    original_keys = {canonical(row["text"]) for row in original_train + original_test}
    imported_train = [row for row in imported_train if canonical(row["text"]) not in original_keys]
    imported_test = [row for row in imported_test if canonical(row["text"]) not in original_keys]
    for name, rows in [("training.json", original_train + imported_train), ("evaluation.json", original_test + imported_test)]:
        (output / name).write_text(json.dumps(rows, indent=2) + "\n")
    provenance = {"source": SOURCE, "publisher": "Bitext Innovations, 2024", "revision": REVISION, "download_url": URL, "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(), "retrieved_at": datetime.now(timezone.utc).isoformat(), "license": "CDLA-Sharing-1.0", "license_url": LICENSE, "modified": True, "modifications": "Selected instruction/intent columns; mapped five labels; canonical deduplication; char n-gram near-duplicate clustering; group-disjoint split; supplemented original MIT product/examples.", "mapping": MAPPING, "public_train_rows": len(imported_train), "public_test_rows": len(imported_test), "limitations": "Hybrid synthetic data. Product training remains original. Near-duplicate grouping reduces but cannot eliminate shared templates or semantic leakage. Not an independent production benchmark."}
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    (output / "DATA_LICENSE.md").write_text(f"# Modified Bitext dataset experiment\n\nPublisher: Bitext Innovations, 2024. Source: {SOURCE}\n\nImported/modified Bitext rows are governed by [CDLA-Sharing-1.0]({LICENSE}). The original examples retain MIT licensing. Preserve attribution, modification notices and the CDLA license link if redistributing imported/modified data. See provenance.json for changes and source digest. These files are ignored by Git.\n")
    print(json.dumps({"public_train_rows": len(imported_train), "public_test_rows": len(imported_test), "output": str(output)}, indent=2))

if __name__ == "__main__":
    main()
