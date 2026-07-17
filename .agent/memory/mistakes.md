# Mistakes And Prevention Rules

Last updated: 2026-07-16

This file records known failure modes so future agents do not repeat them.

## Known Framework Failure Modes

| ID | Mistake | Consequence | Prevention |
|---|---|---|---|
| M-001 | Treating enrichment records as leads | Creates false dashboards and noisy lead output | Only primary event sources can originate active lead rows. Parcel, GIS, assessor, owner, valuation, and vacancy data decorate leads only. |
| M-002 | Hardcoding county-specific facts in universal code | Breaks portability and contaminates the framework | Keep county names, city names, source URLs, portal hostnames, field names, doc-type synonyms, and parcel prefixes in county-scoped config or county-scoped code. |
| M-003 | Guessing URLs or portals during recon | Produces unverifiable source maps | Discover URLs from official county, state, municipal, court, or officially linked vendor pages. Mark unknown sources `NOT_FOUND` or `UNVERIFIED`. |
| M-004 | Building before Phase 0 is complete | Builds on unverified sources and invalid assumptions | Complete source recon, source proof packets, Source of Record Matrix, schema validation, and P0 gate before Build Mode. |
| M-005 | Proceeding past Build Mode Approval Gate without explicit approval | Violates operator control and framework process | Stop after Phase 0 verdict and wait for explicit operator instruction. |
| M-006 | Stream-writing large county config JSON | Can corrupt nested JSON or duplicate blocks | Use `scaffold/ops/write_county_config.py` for populated county configs. |
| M-007 | Showing internal lead codes to operators | Produces unclear, non-callable dashboard output | Translate internal codes and raw doc abbreviations into operator-readable lead names. |
| M-008 | Dropping leads because enrichment failed | Loses valid distress events | Decouple lead origination from enrichment. Route unresolved matches to review instead of deleting events. |
| M-009 | Aggregator reading from its own output | Causes lead inflation across runs | Aggregators read only stable per-source base files and must be idempotent. |
| M-010 | Declaring build complete without verification | Ships broken or misleading output | Run the relevant tests and verification gates before declaring completion. |
| M-011 | Silently ignoring operator-volunteered source knowledge | Loses operational context between runs | Capture casual county/source knowledge in the appropriate run-level notes file when a county run exists. |
| M-012 | Creating parallel framework systems or duplicate canonical files | Increases drift and confusion | Use existing canonical paths. Do not create replacement systems without explicit operator approval. |
| M-013 | Schema translator enum drifting from the translator registry | Valid county configs fail JSON Schema even though the translator is registered | Keep `config/counties/_schema.json` translator enum in sync with `scaffold/pipeline/translators/` registered names. Guarded by `test_translator_registry.py::test_schema_enum_covers_registry`. |

## Current Session Guardrail

The operator explicitly instructed:

Do not start county implementation.

Any action that creates county run artifacts, county configs, scrapers, dashboards, or recon output would violate the current scope.
