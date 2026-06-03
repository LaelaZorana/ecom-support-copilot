"""Smoke tests for the FastAPI web layer using the offline stub provider."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from supportcopilot.app import create_app


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["provider"] == "stub"  # offline by default in tests


def test_index_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Customer support chat" in r.text


def test_dashboard_renders(client):
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert "ROI dashboard" in r.text
    assert "deflection rate" in r.text.lower()


def test_chat_json(client):
    r = client.post(
        "/chat",
        data={"message": "what is your return policy?", "order_id": "", "email": ""},
        headers={"accept": "application/json"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "refund" or body["intent"] == "general"
    assert body["auto_resolved"] is True
    assert len(body["citations"]) >= 1


def test_chat_html_fragment_for_refund(client):
    r = client.post(
        "/chat",
        data={
            "message": "I'd like to return my tent, it's unused with tags.",
            "order_id": "NW-1001",
            "email": "alex@example.com",
        },
    )
    assert r.status_code == 200
    assert "Refund decision" in r.text
    assert "APPROVE" in r.text


def test_api_roi(client):
    r = client.get("/api/roi")
    assert r.status_code == 200
    body = r.json()
    assert body["total_tickets"] > 0
    assert 0.0 <= body["deflection_rate"] <= 1.0
    assert "outcomes" in body
