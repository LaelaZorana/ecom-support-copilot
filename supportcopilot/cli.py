"""Command-line entry points: ask a single question or print the ROI report.

    python -m supportcopilot.cli ask "what is your return policy?"
    python -m supportcopilot.cli ask "return my tent" --order NW-1001
    python -m supportcopilot.cli roi
"""

from __future__ import annotations

import argparse
import json
import sys

from .agent import SupportAgent
from .metrics import compute_roi


def _cmd_ask(args: argparse.Namespace) -> int:
    agent = SupportAgent()
    resp = agent.handle(args.message, order_id=args.order, email=args.email)
    if args.json:
        print(json.dumps(resp.to_dict(), indent=2))
        return 0
    status = "ESCALATED" if resp.escalated else "AUTO-RESOLVED"
    print(f"[{status}] intent={resp.intent} confidence={resp.confidence:.2f}\n")
    print(resp.answer)
    if resp.refund:
        print(f"\nRefund decision: {resp.refund.outcome.upper()} "
              f"(${resp.refund.refund_amount:.2f}), per {resp.refund.policy_citation}")
    if resp.citations:
        print("\nSources:")
        for c in resp.citations:
            print(f"  - [{c.kind}] {c.title}")
    return 0


def _cmd_roi(args: argparse.Namespace) -> int:
    report = compute_roi()
    if args.json:
        print(json.dumps(report.as_summary(), indent=2))
        return 0
    s = report
    print("=== SupportCopilot ROI (replayed on seeded tickets) ===")
    print(f"Tickets handled:      {s.total_tickets}")
    print(f"Auto-resolved:        {s.auto_resolved} ({s.deflection_rate * 100:.0f}% deflection)")
    print(f"Escalated to human:   {s.escalated} ({s.escalation_rate * 100:.0f}%)")
    print(f"Agent time saved:     {s.handle_time_saved_hours:.2f} h "
          f"({s.baseline_handle_time_min:.0f} min/ticket baseline)")
    print(f"Cost saved (sample):  ${s.cost_saved:,.2f}")
    print(f"Projected monthly:    ${s.monthly_cost_saved_projection:,.0f} "
          f"(@3000 tickets/mo, ${s.agent_cost_per_hour:.0f}/agent-hr)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="supportcopilot", description="SupportCopilot CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ask = sub.add_parser("ask", help="Ask the support copilot a question")
    p_ask.add_argument("message")
    p_ask.add_argument("--order", default=None, help="Order id, e.g. NW-1001")
    p_ask.add_argument("--email", default=None, help="Customer email for verification")
    p_ask.add_argument("--json", action="store_true", help="Emit JSON")
    p_ask.set_defaults(func=_cmd_ask)

    p_roi = sub.add_parser("roi", help="Print the ROI report")
    p_roi.add_argument("--json", action="store_true", help="Emit JSON")
    p_roi.set_defaults(func=_cmd_roi)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
