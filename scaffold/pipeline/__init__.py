"""
County Lead Intelligence Engine — pipeline package.

Production pipeline that turns raw source records into stacked, scored,
classified leads ready for the dashboard. Synthetic-data harness
(Phase 1) uses the same modules; the only thing that changes between
synthetic and production runs is the input source (jsonl fixtures vs.
real scraper output) and the output path
(`data/leads_synthetic.json` vs. `data/leads.json`).

Module map:

    normalize.py   — doc-type normalization + parcel attribute derivation
    stack.py       — signal aggregation, lifecycle/TTL filtering, pattern collapse
    score.py       — base scoring + stack bonus + recency + attribute bonus
    classify.py    — deal-path classifier
    evidence.py    — evidence-ledger entry builder
    review.py      — review-queue flag evaluator
    dashboard.py   — dashboard projection
    manifest.py    — run-manifest + heartbeat builders
    build_leads.py — orchestrator (CLI entry point)
"""

__version__ = "0.1.0-phase1"
