"""Retrieval returns the expected document for seeded queries."""

from __future__ import annotations

import pytest

# (query, expected document title) — these mirror the seeded support tickets.
SEED_QUERIES = [
    ("how long does standard shipping take and is it free", "Shipping policy"),
    ("what is your return policy for unused items", "Returns policy"),
    ("do you price match a cheaper competitor", "Price Match policy"),
    ("what warranty do you offer on your products", "Warranty policy"),
    ("can I cancel my order before it ships", "Order Changes and Cancellations policy"),
    ("ultralight 2 person backpacking tent weight", "Ultralight 2-Person Backpacking Tent"),
    ("R-value of the insulated sleeping pad", "Insulated Sleeping Pad"),
    ("is the women's waterproof rain jacket in stock", "Waterproof Rain Jacket (Women's)"),
    ("rechargeable headlamp lumens", "Rechargeable Headlamp"),
    ("does the canister stove include fuel", "Canister Camp Stove"),
]


@pytest.mark.parametrize("query,expected", SEED_QUERIES)
def test_top_result_matches(retriever, query, expected):
    results = retriever.search(query, top_k=3)
    titles = [r.document.title for r in results]
    assert expected in titles, f"{expected!r} not in top-3 for {query!r}: {titles}"
    # The intended document should be the single best match for these clear queries.
    assert titles[0] == expected, f"expected {expected!r} at rank 1, got {titles}"


def test_scores_are_normalized(retriever):
    results = retriever.search("return policy", top_k=3)
    for r in results:
        assert 0.0 <= r.score <= 1.0
    # Results are sorted by descending score.
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_offtopic_query_has_low_confidence(retriever):
    # A query with no lexical overlap with the KB should score ~0, which downstream
    # triggers escalation.
    results = retriever.search("how do I bake sourdough bread", top_k=3)
    assert results[0].score == pytest.approx(0.0, abs=1e-9)


def test_python_fallback_backend_ranks_correctly():
    # Exercise the dependency-free fallback backend directly to ensure it ranks the
    # right document even without scikit-learn.
    from supportcopilot.knowledge import load_knowledge_base
    from supportcopilot.retrieval import _NumpyTfidf

    backend = _NumpyTfidf(load_knowledge_base())
    results = backend.query("what is your return policy", top_k=1)
    assert results[0].document.title == "Returns policy"
