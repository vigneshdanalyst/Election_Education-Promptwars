"""Basic tests for VoteWise India API."""
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_config_endpoint():
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "counting_date" in data
    assert "states" in data
    assert isinstance(data["states"], list)


def test_states_endpoint():
    response = client.get("/api/states")
    assert response.status_code == 200
    states = response.json()
    assert isinstance(states, list)
    assert len(states) > 0


def test_overview_endpoint():
    response = client.get("/api/overview")
    assert response.status_code == 200
    data = response.json()
    assert "stats" in data
    assert "seats" in data["stats"]


def test_timeline_endpoint():
    response = client.get("/api/timeline")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_voter_missing_epic():
    response = client.get("/api/voter")
    assert response.status_code == 422


def test_voter_invalid_epic():
    response = client.get("/api/voter?epic=!!invalid!!")
    assert response.status_code == 400


def test_candidate_not_found():
    response = client.get("/api/candidate/999999")
    assert response.status_code == 404


def test_elector_stats():
    response = client.get("/api/elector-stats")
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "total" in data["summary"]


def test_advanced_stats():
    response = client.get("/api/stats/advanced")
    assert response.status_code == 200
    data = response.json()
    assert "crorepatis" in data
    assert "criminal_cases" in data


def test_parse_rs():
    from main import _parse_rs
    assert _parse_rs("Nil") == 0.0
    assert _parse_rs("") == 0.0
    assert _parse_rs("Rs 50,00,000") == 0.05
    assert _parse_rs("5 Crore") == 5.0
    assert _parse_rs("50 Lac") == 0.5
