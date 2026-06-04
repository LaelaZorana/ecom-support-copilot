"""Load the seed store data and turn it into retrievable documents.

A :class:`Document` is one citable unit of knowledge: a policy section or a single
product. Keeping products and policy sections as separate documents means the agent
can cite exactly what it used ("Returns policy", "Ultralight 2-Person Tent").
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import get_settings


@dataclass(frozen=True)
class Document:
    """One retrievable, citable knowledge unit."""

    doc_id: str
    kind: str  # "policy" | "product"
    title: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


_HEADING = re.compile(r"^##\s+(.*)$", re.MULTILINE)


def load_policy_documents(policies_path: Path) -> list[Document]:
    """Split ``policies.md`` into one document per ``##`` section."""
    raw = policies_path.read_text(encoding="utf-8")
    docs: list[Document] = []
    matches = list(_HEADING.finditer(raw))
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        body = raw[start:end].strip()
        if not body:
            continue
        # Repeat the section title so the heading (a strong topical signal) is
        # weighted into retrieval, e.g. a "shipping" query should land on the
        # Shipping section, not merely any section that mentions shipping in passing.
        docs.append(
            Document(
                doc_id=f"policy::{title.lower().replace(' ', '-')}",
                kind="policy",
                title=f"{title} policy",
                text=f"{title}. {title}. {body}",
                metadata={"section": title},
            )
        )
    return docs


def load_product_documents(catalog_path: Path) -> list[Document]:
    """Turn each catalog product into a retrievable document."""
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    docs: list[Document] = []
    for p in data.get("products", []):
        stock = "in stock" if p.get("in_stock") else "out of stock"
        tags = " ".join(p.get("tags", []))
        text = (
            f"{p['name']} (SKU {p['sku']}, {p['category']}). "
            f"Price ${p['price']:.2f}, {stock}. "
            f"Weight {p.get('weight_kg', 'n/a')} kg. "
            f"Warranty {p.get('warranty_years', 'n/a')} years. "
            f"{p['description']} Keywords: {tags}."
        )
        docs.append(
            Document(
                doc_id=f"product::{p['sku']}",
                kind="product",
                title=p["name"],
                text=text,
                metadata=p,
            )
        )
    return docs


def load_knowledge_base(data_dir: Path | None = None) -> list[Document]:
    """Load every policy and product document from the data directory."""
    data_dir = data_dir or get_settings().data_dir
    docs = load_policy_documents(data_dir / "policies.md")
    docs += load_product_documents(data_dir / "catalog.json")
    return docs
