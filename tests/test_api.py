import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from triage import create_app, storage


def edit(ticket, **changes):
    return {'revision': ticket['revision'], 'intent': ticket['intent'], 'priority': ticket['priority'], 'status': ticket['status'], 'assignee': ticket['assignee'], 'reviewed': False, **changes}

def test_bootstrap_health_html_and_isolated_cookie(client):
    assert client.get('/api/health').get_json()['status'] == 'ok'
    response = client.get('/api/bootstrap')
    assert response.status_code == 200
    assert 'sutra_session=' in response.headers['Set-Cookie']
    assert 'HttpOnly' in response.headers['Set-Cookie']
    assert 'SameSite=Strict' in response.headers['Set-Cookie']
    assert response.get_json()['model']['training_examples'] == 72
    page = client.get('/')
    assert b'Sutra' in page.data
    assert "script-src 'self'" in page.headers['Content-Security-Policy']
    assert client.get('/api/tickets').headers['Cache-Control'] == 'no-store'
    assert client.get('/static/app.js').status_code == 200

@pytest.mark.parametrize('headers', [{}, {'X-CSRF-Token': 'wrong'}, {'Origin': 'https://evil.example', 'X-CSRF-Token': 'irrelevant'}])
def test_mutations_require_session_csrf_and_same_origin(client, ticket_body, headers):
    assert client.post('/api/tickets', json=ticket_body, headers=headers).status_code == 403

def test_cross_origin_rejected_even_with_valid_token(client, csrf, ticket_body):
    assert client.post('/api/tickets', json=ticket_body, headers={**csrf, 'Origin': 'http://evil.example'}).status_code == 403
    assert client.post('/api/tickets', json=ticket_body, headers={**csrf, 'Origin': 'http://localhost'}).status_code == 201

def test_unicode_csrf_is_rejected_without_server_error(client, csrf, ticket_body):
    assert client.post('/api/tickets', json=ticket_body, headers={'X-CSRF-Token': 'é'}).status_code == 403

def test_untrusted_host_is_rejected(client):
    assert client.get('/api/health', headers={'Host': 'malicious.example'}).status_code == 400

@pytest.mark.parametrize('changes', [
    {'customer': ''}, {'customer': 'x' * 81}, {'customer': None}, {'customer': '\u0000'},
    {'subject': ''}, {'subject': 'x' * 141}, {'message': ''}, {'message': 'x' * 4001},
    {'message': ['text']}, {'email': 'bad-email'}, {'email': 'a' * 161},
    {'priority': 'urgent'}, {'priority': ['high']},
])
def test_invalid_new_fields_do_not_write_any_rows(client, csrf, ticket_body, changes):
    response = client.post('/api/tickets', json={**ticket_body, **changes}, headers=csrf)
    assert response.status_code == 422
    assert client.get('/api/tickets').get_json()['stats']['total'] == 0

@pytest.mark.parametrize('payload,expected', [([], 422), ('value', 422), (None, 400)])
def test_json_shape_or_missing_body(client, csrf, payload, expected):
    response = client.post('/api/tickets', data=json.dumps(payload) if payload is not None else '', content_type='application/json', headers=csrf)
    assert response.status_code == expected

def test_oversize_and_malformed_requests(client, csrf):
    assert client.post('/api/tickets', data='x' * 33000, content_type='application/json', headers=csrf).status_code == 413
    assert client.post('/api/tickets', data='{', content_type='application/json', headers=csrf).status_code == 400
    assert client.post('/api/tickets', data='hello', headers=csrf).status_code == 415

def test_idempotent_submission_replays_and_conflicting_payload_is_rejected(client, csrf, ticket_body):
    first = client.post('/api/tickets', json={**ticket_body, 'request_key': 'browser-request-1'}, headers=csrf)
    second = client.post('/api/tickets', json={**ticket_body, 'request_key': 'browser-request-1'}, headers=csrf)
    assert first.status_code == 201 and second.status_code == 200
    assert second.get_json()['replayed']
    assert first.get_json()['ticket']['id'] == second.get_json()['ticket']['id']
    conflict = client.post('/api/tickets', json={**ticket_body, 'subject': 'Something changed', 'request_key': 'browser-request-1'}, headers=csrf)
    assert conflict.status_code == 409
    assert client.get('/api/tickets').get_json()['stats']['total'] == 1

@pytest.mark.parametrize('key', ['', 'x' * 101, 5])
def test_invalid_request_key(client, csrf, ticket_body, key):
    assert client.post('/api/tickets', json={**ticket_body, 'request_key': key}, headers=csrf).status_code == 422

def test_unknown_ticket_and_invalid_queue(client):
    assert client.get('/api/tickets/missing').status_code == 404
    assert client.get('/api/tickets?queue=unknown').status_code == 422
    assert client.get('/api/tickets?q=' + 'x' * 121).status_code == 422

def test_safe_storage_search_and_possible_related_tickets(client, csrf, ticket_body):
    first = client.post('/api/tickets', json={**ticket_body, 'customer': '<img src=x onerror=alert(1)>'}, headers=csrf).get_json()['ticket']
    second = client.post('/api/tickets', json={**ticket_body, 'customer': 'Priya Joshi'}, headers=csrf).get_json()['ticket']
    result = client.get('/api/tickets/' + first['id']).get_json()
    assert result['ticket']['customer'] == '<img src=x onerror=alert(1)>'
    assert result['similar'][0]['id'] == second['id'] and result['similar'][0]['exact']
    assert len(client.get('/api/tickets?q=priya').get_json()['tickets']) == 1
    assert len(result['events']) == 1
    assert len(client.get('/api/tickets').get_json()['tickets']) == 2

@pytest.mark.parametrize('changes', [
    {'revision': True}, {'revision': 0}, {'revision': '1'}, {'revision': None},
    {'intent': 'other'}, {'priority': 'critical'}, {'status': 'deleted'},
    {'assignee': 'Someone unknown'}, {'reviewed': 'true'},
])
def test_invalid_update_does_not_change_revision(client, csrf, ticket, changes):
    assert client.patch('/api/tickets/' + ticket['id'], json=edit(ticket, **changes), headers=csrf).status_code == 422
    assert client.get('/api/tickets/' + ticket['id']).get_json()['ticket']['revision'] == 1

def test_review_correction_retains_original_model_and_history(client, csrf, ticket):
    result = client.patch('/api/tickets/' + ticket['id'], json=edit(ticket, intent='refund', reviewed=True, status='in_progress', assignee='Meera Shah'), headers=csrf)
    assert result.status_code == 200
    item = result.get_json()['ticket']
    assert item['intent'] == 'refund' and item['revision'] == 2
    assert item['prediction'] == ticket['prediction']
    assert not item['review_required']
    detail = client.get('/api/tickets/' + ticket['id']).get_json()
    assert detail['events'][0]['action'] == 'reviewed'
    assert detail['events'][0]['details']['intent'] == {'before': 'delivery', 'after': 'refund'}
    assert client.get('/api/tickets?queue=in_progress').get_json()['stats']['in_progress'] == 1

def test_stale_revision_cannot_overwrite_a_review(client, csrf, ticket):
    first = client.patch('/api/tickets/' + ticket['id'], json=edit(ticket, priority='high'), headers=csrf)
    assert first.status_code == 200
    assert client.patch('/api/tickets/' + ticket['id'], json=edit(ticket, priority='low'), headers=csrf).status_code == 409
    assert client.get('/api/tickets/' + ticket['id']).get_json()['ticket']['priority'] == 'high'

def test_invalid_transition_and_missing_review_do_not_write_events(client, csrf, ticket):
    path = '/api/tickets/' + ticket['id']
    assert client.patch(path, json=edit(ticket, status='resolved', assignee='Meera Shah', reviewed=True), headers=csrf).status_code == 422
    assert client.patch(path, json=edit(ticket, intent='refund'), headers=csrf).status_code == 422
    assert client.patch(path, json=edit(ticket), headers=csrf).status_code == 422
    assert len(client.get(path).get_json()['events']) == 1

def test_ambiguous_ticket_requires_routing_and_teammate_to_resolve(client, csrf, ticket_body):
    payload = {**ticket_body, 'subject': 'Need help', 'message': 'The item is broken and I want a refund.'}
    item = client.post('/api/tickets', json=payload, headers=csrf).get_json()['ticket']
    path = '/api/tickets/' + item['id']
    assert item['review_required'] and item['intent'] == 'unassigned'
    assert client.get('/api/tickets?queue=review').get_json()['stats']['needs_review'] == 1
    assert client.patch(path, json=edit(item, reviewed=True), headers=csrf).status_code == 422
    item = client.patch(path, json=edit(item, status='in_progress'), headers=csrf).get_json()['ticket']
    assert client.patch(path, json=edit(item, status='resolved'), headers=csrf).status_code == 422
    item = client.patch(path, json=edit(item, intent='refund', reviewed=True), headers=csrf).get_json()['ticket']
    assert client.patch(path, json=edit(item, status='resolved'), headers=csrf).status_code == 422
    item = client.patch(path, json=edit(item, status='resolved', assignee='Kavya Joshi'), headers=csrf).get_json()['ticket']
    assert item['status'] == 'resolved'
    assert client.patch(path, json=edit(item, status='in_progress'), headers=csrf).status_code == 422
    reopened = client.patch(path, json=edit(item, status='open'), headers=csrf).get_json()['ticket']
    assert reopened['status'] == 'open'

def test_concurrent_revision_updates_allow_exactly_one_writer(app, ticket):
    fields = {'intent': ticket['intent'], 'priority': 'high', 'status': 'open', 'assignee': 'Unassigned', 'reviewed': False}
    def write():
        db = storage.connect(app.config['DATABASE'])
        try:
            try:
                storage.update(db, ticket['id'], fields, 1)
                return 'saved'
            except storage.Conflict:
                return 'conflict'
        finally:
            db.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: write(), range(2)))
    assert sorted(results) == ['conflict', 'saved']
    with storage.connect(app.config['DATABASE']) as db:
        assert storage.load(db, ticket['id'])['revision'] == 2
        assert db.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 2

def test_demo_seed_once_and_persistent_secret(tmp_path, model):
    settings = {'DATA_DIR': str(tmp_path), 'MODEL': model}
    first = create_app(settings)
    second = create_app(settings)
    assert first.config['SECRET_KEY'] == second.config['SECRET_KEY']
    with second.test_client() as client:
        result = client.get('/api/tickets').get_json()
        assert result['stats']['total'] == 6
        assert result['stats']['needs_review'] == 2
        assert len(client.get('/api/tickets/demo-parcel').get_json()['similar']) >= 1

def test_unknown_edit_rolls_back(client, csrf, ticket):
    assert client.patch('/api/tickets/missing', json=edit(ticket, priority='high'), headers=csrf).status_code == 404
    assert client.patch('/api/tickets/' + ticket['id'], json=edit(ticket, priority='high'), headers=csrf).status_code == 200

def test_confident_suggestion_still_requires_human_confirmation_before_resolution(client, csrf, ticket):
    assert not ticket['review_required'] and not ticket['human_reviewed']
    path = '/api/tickets/' + ticket['id']
    item = client.patch(path, json=edit(ticket, status='in_progress', assignee='Meera Shah'), headers=csrf).get_json()['ticket']
    assert client.patch(path, json=edit(item, status='resolved'), headers=csrf).status_code == 422
    result = client.patch(path, json=edit(item, status='resolved', reviewed=True), headers=csrf)
    assert result.status_code == 200
    assert result.get_json()['ticket']['human_reviewed']
