import pytest
from triage import create_app
from triage.model import TriageModel

@pytest.fixture(scope="session")
def model():
    return TriageModel()

@pytest.fixture
def app(tmp_path, model):
    return create_app({"TESTING": True, "DATA_DIR": str(tmp_path), "SEED_DEMO": False, "SECRET_KEY": "test-only-secret", "MODEL": model})

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def csrf(client):
    return {"X-CSRF-Token": client.get('/api/bootstrap').get_json()['csrf']}

@pytest.fixture
def ticket_body():
    return {"customer": "Aarav Patel", "email": "aarav@example.test", "subject": "Delivery tracking delayed", "message": "My delivery is late and the parcel has not arrived. Please check courier tracking.", "priority": "normal"}

@pytest.fixture
def ticket(client, csrf, ticket_body):
    response = client.post('/api/tickets', json=ticket_body, headers=csrf)
    assert response.status_code == 201
    return response.get_json()['ticket']
