"""ROI metrics are computed correctly and consistently from the seeded tickets."""

from __future__ import annotations

import pytest

from supportcopilot.metrics import compute_roi, load_tickets


@pytest.fixture(scope="module")
def report(agent):
    return compute_roi(agent=agent, monthly_ticket_volume=3000)


def test_counts_are_consistent(report):
    assert report.total_tickets == report.auto_resolved + report.escalated
    assert report.total_tickets == len(report.outcomes)
    assert report.total_tickets > 0


def test_rates_are_fractions_and_complementary(report):
    assert 0.0 <= report.deflection_rate <= 1.0
    assert 0.0 <= report.escalation_rate <= 1.0
    assert report.deflection_rate + report.escalation_rate == pytest.approx(1.0, abs=1e-6)


def test_deflection_meets_target(report):
    # The seeded mix is designed so the agent deflects a strong majority while still
    # escalating the genuinely hard tickets.
    assert report.deflection_rate >= 0.6


def test_time_and_cost_math(report):
    blob = load_tickets()
    baseline = blob["baseline_handle_time_min"]
    rate = blob["agent_loaded_cost_per_hour"]

    expected_min = report.auto_resolved * baseline
    assert report.handle_time_saved_min == pytest.approx(expected_min, abs=1e-6)

    expected_cost = (expected_min / 60.0) * rate
    assert report.cost_saved == pytest.approx(round(expected_cost, 2), abs=1e-2)


def test_monthly_projection_scales_with_volume(agent):
    r1 = compute_roi(agent=agent, monthly_ticket_volume=1000)
    r2 = compute_roi(agent=agent, monthly_ticket_volume=2000)
    # Projection scales linearly with volume (within cent-rounding).
    assert r2.monthly_cost_saved_projection == pytest.approx(
        2 * r1.monthly_cost_saved_projection, abs=0.02
    )


def test_specific_tickets_escalate(report):
    # The two defect claims, the manager demand, and the billing dispute must escalate.
    escalated_ids = {o.ticket_id for o in report.outcomes if o.escalated}
    for tid in ("T-010", "T-014", "T-017", "T-018"):
        assert tid in escalated_ids, f"{tid} should have escalated"


def test_is_deterministic(agent):
    a = compute_roi(agent=agent)
    b = compute_roi(agent=agent)
    assert a.deflection_rate == b.deflection_rate
    assert a.cost_saved == b.cost_saved
