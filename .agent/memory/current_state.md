# Current State

Last updated: 2026-07-16

## Repository

This repository contains the Xcerebro County Intelligence Framework.

It is a portable framework for building county-level lead intelligence dashboards. It is not itself a county-specific build.

The framework version stated in `README.md` is v5.3.1 stable.

## Current Work

Duval County Build Mode is authorized (D-002, D-003). The scoped synthetic pipeline
artifact under `runs/duval_fl/build/` passes, and the schema/translator enum blocker
is resolved: `config/counties/duval_fl.json` now passes JSON Schema validation.

## County Build State

The Duval Phase 0 config and launch file are in the active county's scoped paths.
`config/counties/duval_fl.json` passes JSON Schema validation (translator enum drift
fixed in `_schema.json`). The synthetic build, county-agnostic regression, translator
registry, and v5.3/v5.4 contract gates pass.

Build Mode remains source-limited: the repository has no current `data/raw/` inputs,
and the required Duval recon artifact set is not present.

Build verdict: `READY_WITH_BLOCKERS` (schema blocker cleared).

Duval-scoped scrapers/adapters and translators exist under `scrapers/` and `scaffold/pipeline/translators/`. No dashboards were deployed and no production refresh was run.

## Important Active Constraint

Do not treat the build as production-ready. A live refresh requires current raw source
pulls plus the missing recon-gate artifacts. The schema/translator blocker is now cleared.

The five legacy Duval adapter tests (`official_records`, `foreclosure_sales`,
`tax_deed_sales`, `publicsearch_clerk_recordings`, `tax_collector`) still fail: their
fixtures/expected fields diverge from the current adapter parse APIs. Fixing them
correctly requires verified real portal HTML/JSON samples, which are among the missing
recon artifacts. Do NOT rewrite those fixtures to force a green gate without verified
source samples (Evidence Rule).

## Next Allowed Action

Next allowed action: obtain verified Duval raw source samples for the five adapters,
reconcile each adapter/test/fixture against the real portal response, then run a live
source refresh and mechanical/semantic verification before deployment.
