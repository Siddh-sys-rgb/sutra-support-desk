import json
from pathlib import Path
import pytest
from triage.model import TriageModel, INTENTS
from scripts.evaluate import evaluate

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('text,intent', [
    ('Please cancel my order before it ships', 'cancellation'),
    ('My UPI payment failed but money was debited', 'payment'),
    ('My return is accepted but the refund is pending', 'refund'),
    ('The parcel tracking link says delivery delayed', 'delivery'),
    ('The charger is broken and I want a replacement', 'product'),
    ('The password reset link has expired', 'account'),
])
def test_learned_prediction_has_supported_scores_and_text_evidence(model, text, intent):
    result = model.classify(text)
    assert result['predicted_intent'] == intent
    assert not result['review_required']
    assert set(row['intent'] for row in result['scores']) == set(INTENTS)
    assert sum(row['score'] for row in result['scores']) == pytest.approx(1, abs=.001)
    assert result['evidence']

@pytest.mark.parametrize('text', ['hello', 'Tell me about dragons', 'What is the weather in Surat?', 'The item is broken and I want a refund.', 'Cancel the order because my payment failed.'])
def test_uncertain_or_unrelated_messages_are_held(model, text):
    assert model.classify(text)['review_required']

def test_identical_text_similarity_is_one(model):
    candidates = [{'id': 'same', 'subject': 'PAYMENT FAILED', 'message': 'Money was debited', 'customer': 'Meera', 'status': 'open'}, {'id': 'other', 'subject': 'Login password', 'message': 'Reset account password', 'customer': 'Dev', 'status': 'open'}]
    result = model.similar('payment failed Money was debited', candidates)
    assert result[0]['id'] == 'same' and result[0]['exact']
    assert result[0]['score'] == pytest.approx(1)
    assert model.similar('no vocabulary related here', []) == []

def test_similarity_is_bounded_and_ignores_unrelated_ticket(model):
    rows = [{'id': str(i), 'subject': 'Delivery delayed', 'message': 'My parcel tracking shows delivery delayed', 'customer': 'Priya', 'status': 'open'} for i in range(5)]
    rows.append({'id': 'unrelated', 'subject': 'Account password', 'message': 'Reset password login', 'customer': 'Dev', 'status': 'open'})
    result = model.similar('Delivery delayed My parcel tracking shows delivery delayed', rows)
    assert len(result) == 3
    assert all(row['id'] != 'unrelated' for row in result)

def test_heldout_evaluation_reports_coverage_without_training_on_test(model):
    train = json.loads((ROOT / 'data/training.json').read_text())
    test = json.loads((ROOT / 'data/evaluation.json').read_text())
    assert not set(row['text'] for row in train) & set(row['text'] for row in test)
    report = evaluate(model, test)['summary']
    assert report['labelled_examples'] == 24
    assert report['top_intent_accuracy'] >= .8
    assert .2 < report['suggestion_coverage'] < 1
    assert report['review_checks']['out_of_domain'] == {'total': 6, 'held_for_review': 6}
    assert report['review_checks']['ambiguous'] == {'total': 3, 'held_for_review': 3}

@pytest.mark.parametrize('rows', [[], [{'text': 'hi', 'intent': 'bad'}] * 12, [{'text': 'one text', 'intent': intent} for intent in INTENTS for _ in range(2)]])
def test_custom_training_rejects_empty_bad_labels_and_duplicates(tmp_path, rows):
    path = tmp_path / 'training.json'
    path.write_text(json.dumps(rows))
    with pytest.raises(ValueError):
        TriageModel(path)

def test_custom_training_requires_every_intent(tmp_path):
    rows = [{'text': f'Example number {i} payment', 'intent': 'payment'} for i in range(12)]
    path = tmp_path / 'training.json'
    path.write_text(json.dumps(rows))
    with pytest.raises(ValueError, match='every intent'):
        TriageModel(path)

def test_default_model_matches_validated_custom_file(model):
    custom = TriageModel(ROOT / 'data/training.json')
    assert custom.classify('Please cancel my order') == model.classify('Please cancel my order')
    assert custom.source.startswith('custom')
