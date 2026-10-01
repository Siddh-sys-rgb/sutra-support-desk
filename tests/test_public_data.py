"""Importer contract tests use generated CSV fixtures, never downloaded customer text."""
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from scripts import import_bitext
from triage.model import TriageModel

ROOT = Path(__file__).resolve().parents[1]

def synthetic_csv(path):
    rows = []
    for source_intent in ['track_order', 'get_refund', 'cancel_order', 'payment_issue', 'recover_password']:
        for i in range(35):
            unique = hashlib.sha256(f'{source_intent}-{i}'.encode()).hexdigest()
            rows.append({'intent': source_intent, 'instruction': f'{source_intent} example details {unique[:24]} separate {unique[24:48]}'})
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['intent', 'instruction'])
        writer.writeheader()
        writer.writerows(rows + [rows[0], {'intent': 'unmapped', 'instruction': 'Ignore this unrelated intent'}])

def test_canonical_removes_case_punctuation_and_entity_variants():
    assert import_bitext.canonical('Track ORDER {{Order Number}}!') == import_bitext.canonical('track order {{Invoice Number}}')

def test_bounded_import_group_split_is_disjoint_and_deterministic(tmp_path):
    path = tmp_path / 'publisher.csv'
    synthetic_csv(path)
    train, test = import_bitext.split_csv(path, 30)
    train2, test2 = import_bitext.split_csv(path, 30)
    assert train == train2 and test == test2
    assert len(train) + len(test) == 150
    assert not {row['group'] for row in train} & {row['group'] for row in test}
    assert not {import_bitext.canonical(row['text']) for row in train} & {import_bitext.canonical(row['text']) for row in test}
    assert len({row['intent'] for row in test}) == 5
    assert all(row['source'] == 'Bitext Innovations, 2024' for row in train)

@pytest.mark.parametrize('limit', [0, 19, 201])
def test_bad_per_intent_limit_is_rejected(tmp_path, limit):
    path = tmp_path / 'sample.csv'
    path.write_text('intent,instruction\n')
    with pytest.raises(ValueError, match='20 to 200'):
        import_bitext.split_csv(path, limit)

def test_missing_columns_and_sparse_source_are_rejected(tmp_path):
    path = tmp_path / 'sample.csv'
    path.write_text('label,text\none,two\n')
    with pytest.raises(ValueError, match='columns'):
        import_bitext.split_csv(path)
    path.write_text('intent,instruction\ntrack_order,Track my parcel\n')
    with pytest.raises(ValueError, match='Not enough'):
        import_bitext.split_csv(path)

def test_download_bound_without_real_network(tmp_path, monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, size): return b'x' * size
    monkeypatch.setattr(import_bitext, 'LIMIT_BYTES', 32)
    monkeypatch.setattr(import_bitext.urllib.request, 'urlopen', lambda *args, **kwargs: Response())
    with pytest.raises(ValueError, match='download limit'):
        import_bitext.download(tmp_path / 'sample.csv')
    assert not (tmp_path / 'sample.csv').exists()

def test_evaluation_cli_refuses_training_overlap(tmp_path):
    training = json.loads((ROOT / 'data/training.json').read_text())
    path = tmp_path / 'leaked.json'
    path.write_text(json.dumps([training[0]]))
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/evaluate.py'), '--evaluation-data', str(path)], capture_output=True, text=True)
    assert result.returncode == 2
    assert 'overlap' in result.stderr

def test_training_file_size_bound(tmp_path):
    path = tmp_path / 'oversized.json'
    with path.open('wb') as handle:
        handle.truncate(4 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match='4 MB'):
        TriageModel(path)
