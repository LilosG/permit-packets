"""Plans carry named markers and an optional route between two of them."""
import os

import pytest
from fastapi.testclient import TestClient

from app import app
from permit_packets.core.property_plan import PropertyPlan

os.environ["DEMO_PASSWORD"] = "test-password"



@pytest.fixture
def client() -> TestClient:
    signed_in = TestClient(app)
    assert signed_in.post("/api/signin", json={"password": "test-password"}).status_code == 200
    return signed_in


LOT = [(250.0, 250.0), (750.0, 250.0), (750.0, 750.0), (250.0, 750.0)]


def test_route_runs_between_the_named_markers_through_the_bends():
    plan = PropertyPlan(
        scale_ft_per_in=30, markers={"a": (0, 0), "b": (10, 0), "c": (99, 99)},
        route=[(5, 5)], route_between=("a", "b"),
    )
    assert plan.route_points == [(0, 0), (5, 5), (10, 0)]


def test_no_route_between_means_no_route():
    plan = PropertyPlan(scale_ft_per_in=30, markers={"a": (0, 0)}, lot=LOT)
    assert plan.route_points == []
    assert plan.measured_route_ft == 0
    assert plan.distance_to_lot_line_ft((500, 500)) == 52
    assert PropertyPlan(scale_ft_per_in=30, markers={}).distance_to_lot_line_ft((1, 1)) is None


def test_an_ev_plan_without_both_markers_is_refused(client):
    plan = {"scale_ft_per_in": 30, "markers": {"panel": [400, 500]}}
    response = client.post("/api/jobs/ev-charger/packet", json=_payload(plan))
    assert response.status_code == 422


def _payload(plan: dict) -> dict:
    return dict(
        customer="Sample", address="123 Sample St", contractor="Sample Electric", license_number="1",
        home={"square_feet": 2000}, service_amps=200, open_breaker_spaces=4, charger_amps=40,
        location="attached_garage", run_ft=30, plan=plan,
    )
