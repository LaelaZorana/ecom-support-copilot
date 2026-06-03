"""Mock orders API.

Stands in for a real OMS/Shopify Orders endpoint. Reads ``orders.json`` and offers
lookup by order id (optionally verified against the customer email). In production you
would swap this class for a thin HTTP client to the real orders service; the rest of
the app depends only on its small interface.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .config import get_settings


@dataclass(frozen=True)
class Order:
    order_id: str
    email: str
    status: str
    placed_at: str
    delivered_at: str | None
    carrier: str | None
    tracking: str | None
    items: list[dict[str, Any]]
    total: float
    final_sale: bool

    def days_since_delivery(self, today: date | None = None) -> int | None:
        """Whole days since delivery, or ``None`` if not delivered yet."""
        if not self.delivered_at:
            return None
        today = today or date.today()
        delivered = date.fromisoformat(self.delivered_at)
        return (today - delivered).days

    def human_status(self) -> str:
        if self.status == "shipped" and self.tracking:
            return f"shipped via {self.carrier} (tracking {self.tracking})"
        if self.status == "delivered":
            return f"delivered on {self.delivered_at}"
        return self.status


class OrdersService:
    """In-memory mock orders store loaded from ``orders.json``."""

    def __init__(self, orders_path: Path | None = None):
        path = orders_path or (get_settings().data_dir / "orders.json")
        raw = json.loads(path.read_text(encoding="utf-8"))
        self._orders: dict[str, Order] = {}
        for o in raw.get("orders", []):
            self._orders[o["order_id"].upper()] = Order(
                order_id=o["order_id"],
                email=o["email"],
                status=o["status"],
                placed_at=o["placed_at"],
                delivered_at=o.get("delivered_at"),
                carrier=o.get("carrier"),
                tracking=o.get("tracking"),
                items=o.get("items", []),
                total=float(o.get("total", 0.0)),
                final_sale=bool(o.get("final_sale", False)),
            )

    def get(self, order_id: str, email: str | None = None) -> Order | None:
        """Look up an order. If ``email`` is given it must match (case-insensitive)."""
        order = self._orders.get((order_id or "").strip().upper())
        if order is None:
            return None
        if email and order.email.lower() != email.strip().lower():
            return None
        return order

    def all(self) -> list[Order]:
        return list(self._orders.values())
