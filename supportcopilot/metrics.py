"""ROI metrics: replay the seeded tickets through the agent and compute the impact story.

Every number on the dashboard comes from actually running each seeded ticket through
the real :class:`SupportAgent`. Nothing is hard-coded, so the metrics move if you
change the policies, catalog, agent logic, or the ticket set. They are *earned*.

Definitions:
    deflection_rate     fraction of tickets auto-resolved without human escalation
    handle_time_saved   baseline human minutes that the auto-resolved tickets would
                        have consumed (the agent handles them in seconds)
    cost_saved          handle_time_saved valued at the loaded agent hourly cost
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .agent import SupportAgent
from .config import get_settings


@dataclass(frozen=True)
class TicketOutcome:
    ticket_id: str
    channel: str
    message: str
    intent: str
    auto_resolved: bool
    escalated: bool
    confidence: float
    answer: str


@dataclass(frozen=True)
class ROIReport:
    total_tickets: int
    auto_resolved: int
    escalated: int
    deflection_rate: float  # 0..1
    escalation_rate: float  # 0..1
    baseline_handle_time_min: float
    handle_time_saved_min: float
    handle_time_saved_hours: float
    agent_cost_per_hour: float
    cost_saved: float
    monthly_cost_saved_projection: float
    by_intent: dict[str, int]
    outcomes: list[TicketOutcome] = field(default_factory=list)

    def as_summary(self) -> dict[str, Any]:
        """Dashboard-ready dict without the per-ticket detail."""
        d = asdict(self)
        d.pop("outcomes", None)
        return d


def load_tickets(data_dir: Path | None = None) -> dict[str, Any]:
    data_dir = data_dir or get_settings().data_dir
    return json.loads((data_dir / "tickets.json").read_text(encoding="utf-8"))


def compute_roi(
    agent: SupportAgent | None = None,
    data_dir: Path | None = None,
    monthly_ticket_volume: int = 3000,
) -> ROIReport:
    """Replay seeded tickets through ``agent`` and compute the ROI report.

    ``monthly_ticket_volume`` projects the per-ticket savings to a monthly figure for
    the headline ROI number (defaults to a modest mid-market store volume).
    """
    settings = get_settings()
    agent = agent or SupportAgent(settings=settings)
    blob = load_tickets(data_dir or settings.data_dir)

    baseline_min = float(blob.get("baseline_handle_time_min", 7.0))
    cost_per_hour = float(blob.get("agent_loaded_cost_per_hour", 28.0))
    tickets = blob.get("tickets", [])

    outcomes: list[TicketOutcome] = []
    by_intent: dict[str, int] = {}
    for t in tickets:
        resp = agent.handle(
            t["message"], order_id=t.get("order_id"), email=t.get("email")
        )
        outcomes.append(
            TicketOutcome(
                ticket_id=t["id"],
                channel=t.get("channel", "chat"),
                message=t["message"],
                intent=resp.intent,
                auto_resolved=resp.auto_resolved,
                escalated=resp.escalated,
                confidence=round(resp.confidence, 3),
                answer=resp.answer,
            )
        )
        by_intent[resp.intent] = by_intent.get(resp.intent, 0) + 1

    total = len(outcomes)
    auto = sum(1 for o in outcomes if o.auto_resolved)
    escalated = sum(1 for o in outcomes if o.escalated)
    deflection = (auto / total) if total else 0.0
    escalation_rate = (escalated / total) if total else 0.0

    # Auto-resolved tickets are the ones a human no longer touches.
    saved_min = auto * baseline_min
    saved_hours = saved_min / 60.0
    cost_saved = saved_hours * cost_per_hour

    # Per-ticket saving projected to monthly volume.
    per_ticket_saving = (cost_saved / total) if total else 0.0
    monthly_projection = per_ticket_saving * monthly_ticket_volume

    return ROIReport(
        total_tickets=total,
        auto_resolved=auto,
        escalated=escalated,
        deflection_rate=round(deflection, 4),
        escalation_rate=round(escalation_rate, 4),
        baseline_handle_time_min=baseline_min,
        handle_time_saved_min=round(saved_min, 1),
        handle_time_saved_hours=round(saved_hours, 2),
        agent_cost_per_hour=cost_per_hour,
        cost_saved=round(cost_saved, 2),
        monthly_cost_saved_projection=round(monthly_projection, 2),
        by_intent=by_intent,
        outcomes=outcomes,
    )
