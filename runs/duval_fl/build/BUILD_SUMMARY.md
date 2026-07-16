# Duval County Build Summary

Date: 2026-07-16  
Build label: `SOURCE_LIMITED`  
Mode: synthetic gate only

## Result

The operator authorized Build Mode with blockers. The Phase 1 synthetic harness
completed successfully using the framework fixtures:

- 24 event-derived leads produced
- 24 matched leads written
- 24 scored leads written
- 2 leads enriched and 22 explicitly `UNENRICHED`
- §20 semantic verdict: `NEEDS_OPERATOR_REVIEW`

The synthetic output is under `runs/duval_fl/build/synthetic/`. The approval flag
was required because the framework's semantic gate intentionally routes fixture
rows to review; this is not a production deploy approval.

## Production status

No live production refresh was run. The repository has no current `data/raw/`
source inputs for this run. The existing root-level Duval data snapshot is
historical and was not copied into the county build as a new live result.

Production remains blocked by:

1. Duval's required recon-gate artifact set is missing from `runs/duval_fl/recon/`.
2. `config/counties/duval_fl.json` currently uses translator names that are not
   accepted by `config/counties/_schema.json`, so schema validation is red.
3. Live raw pulls must be produced and verified before mechanical and semantic
   production gates can run.
4. Court and code-enforcement sources retain CAPTCHA/request-only constraints.

No dashboard deployment was performed. Enrichment remains subordinate to event
lead origination, and no parcel-only rows were created.

## Verification commands

```text
.venv/bin/python scaffold/pipeline/build_leads.py --county-config config/counties/duval_fl.json --synthetic --approve-needs-review --out runs/duval_fl/build/synthetic
.venv/bin/python scaffold/tests/verify_synthetic_harness.py
.venv/bin/python scaffold/tests/test_county_agnostic_regression.py
.venv/bin/python -m jsonschema -i config/counties/duval_fl.json config/counties/_schema.json
.venv/bin/python scaffold/tests/run_all.py
```

The first two build commands are expected to pass. The schema and full framework
gate results are recorded in the PR because they expose pre-existing contract
drift and legacy adapter failures that must be resolved before production deploy:

- Schema validation fails for `foreclosure_auction_calendar`,
  `tax_delinquency_list`, and `tax_deed_auction_listing` translator enum values.
- `run_all.py` passes the core, county-agnostic, v5.3, and v5.4 gates but fails
  the legacy official-records, foreclosure-sales, tax-deed, tax-collector, and
  public-search adapter tests.
