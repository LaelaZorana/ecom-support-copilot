"""Policy-driven return/refund decision engine.

This is the highest-stakes automation in the product, so the logic is explicit,
deterministic, and unit-tested rather than left to the language model. The LLM drafts
the customer-facing wording; *this* decides what we will actually do, with the policy
clause that justifies it.

Decision outcomes:
    approve   — eligible refund, possibly net of a return-shipping fee
    deny      — not eligible (final sale, worn, outside window, hygiene)
    escalate  — needs a human (e.g. claimed defect, which requires inspecting a photo)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .orders import Order

RETURN_WINDOW_DAYS = 30
RETURN_SHIPPING_FEE = 7.95

_DEFECT_TERMS = re.compile(
    r"\b(defect|defective|broke|broken|snapped|split|tore|torn|ripped|faulty|"
    r"damaged on arrival|arrived damaged|stopped working|malfunction)\b",
    re.IGNORECASE,
)
_WORN_TERMS = re.compile(
    r"\b(worn|used|washed|wore|after .*hike|on .*hikes|opened|mouthpiece)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RefundDecision:
    outcome: str  # "approve" | "deny" | "escalate"
    refund_amount: float
    reason: str
    policy_citation: str
    fee_applied: float = 0.0
    requires_human: bool = False
    notes: list[str] = field(default_factory=list)


def decide_refund(
    order: Order,
    message: str = "",
    today: date | None = None,
    our_error: bool = False,
) -> RefundDecision:
    """Decide a refund for ``order`` given the customer's ``message``.

    ``our_error`` marks the return as caused by us (wrong/defective item confirmed),
    which waives the return-shipping fee per the Returns policy.
    """
    today = today or date.today()
    claims_defect = bool(_DEFECT_TERMS.search(message))
    claims_worn = bool(_WORN_TERMS.search(message))

    # 1) Defect claims go to warranty/human review — we don't auto-approve money on an
    #    unverified physical defect; a photo must be inspected.
    if claims_defect:
        return RefundDecision(
            outcome="escalate",
            refund_amount=0.0,
            reason=(
                "Customer reports a possible manufacturing defect. Warranty claims "
                "require a human to review the photo of the defect before approval."
            ),
            policy_citation="Warranty policy",
            requires_human=True,
            notes=["defect_claim"],
        )

    # 2) Final sale / hygiene items are never refundable.
    if order.final_sale:
        return RefundDecision(
            outcome="deny",
            refund_amount=0.0,
            reason=(
                "This order contains Final Sale item(s), which are not returnable or "
                "refundable. A manufacturing-defect warranty claim is still possible."
            ),
            policy_citation="Final Sale policy",
            notes=["final_sale"],
        )

    # 3) Worn/washed/used items are not eligible for a standard refund.
    if claims_worn:
        return RefundDecision(
            outcome="deny",
            refund_amount=0.0,
            reason=(
                "The item is described as worn/used, which is not eligible for a "
                "standard refund. Only unused items in original condition qualify."
            ),
            policy_citation="Returns policy",
            notes=["worn_or_used"],
        )

    # 4) Standard return window. Undelivered orders are still inside the window
    #    (clock starts at delivery), so treat "not yet delivered" as eligible.
    days = order.days_since_delivery(today)
    if days is not None and days > RETURN_WINDOW_DAYS:
        return RefundDecision(
            outcome="deny",
            refund_amount=0.0,
            reason=(
                f"This order was delivered {days} days ago, beyond the "
                f"{RETURN_WINDOW_DAYS}-day return window."
            ),
            policy_citation="Returns policy",
            notes=["outside_window"],
        )

    # 5) Eligible standard refund. Apply the return-shipping fee unless it's our error.
    fee = 0.0 if our_error else RETURN_SHIPPING_FEE
    refund = round(max(order.total - fee, 0.0), 2)
    reason = (
        "Unused item within the 30-day return window, eligible for a refund to the "
        "original payment method."
    )
    if fee:
        reason += f" A ${fee:.2f} return-shipping fee applies."
    else:
        reason += " Return shipping is free because the return is due to our error."
    return RefundDecision(
        outcome="approve",
        refund_amount=refund,
        reason=reason,
        policy_citation="Returns policy",
        fee_applied=fee,
        notes=["standard_refund"],
    )
