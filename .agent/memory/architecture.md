# Architecture Memory

Last updated: 2026-06-22

## Framework Purpose

The framework builds autonomous county lead intelligence systems for real estate investor operators.

The product is fresh county-level distress intelligence with daily refresh.

The dashboard exists to help a human operator call property owners tied to verified distress events.

## Universal Architecture Rule

The framework is universal. The county is configured.

Universal code must not contain county-specific facts.

County-specific facts belong in county-scoped config, run artifacts, scrapers, and translator registrations.

## Source Hierarchy

Primary lead sources can originate leads.

Examples include:

- Clerk records
- Recorder records
- Court dockets
- Foreclosure filings
- Probate cases
- Sheriff sales
- Tax delinquency events
- Tax sale events
- Liens
- Judgments
- Lis pendens
- Code enforcement events
- Demolition or condemnation events

Supporting lead sources strengthen or confirm leads but do not create independent lead volume.

Enrichment sources decorate leads only and cannot create active lead rows.

Examples include:

- Parcel data
- GIS data
- Assessor data
- Non-delinquent tax roll data
- Owner mailing data
- Valuation data
- Vacancy data
- Equity proxies

## Lead Origination Rule

Every dashboard row, CSV export row, and operator-facing lead artifact must originate from at least one verified primary lead event.

A parcel record alone is not a lead.

If primary sources are blocked, the system stops or ships an explicitly labeled partial board. It never fills a dashboard with enrichment records to look productive.

## Phase Model

Phase 0 is County Source Recon and Onboarding Gate.

Build Mode does not begin until Phase 0 is complete and the operator explicitly approves the Build Mode Approval Gate.

Build Mode includes scraper building, adapter selection, normalization, dashboard work, heartbeat, deployment, scheduler, and production verification.

## Phase 0 Required Outputs

Recon must produce a complete Source of Record Matrix before Build Mode can begin.

Required artifacts include:

- `runs/<slug>/recon/source_of_record_matrix.json`
- `runs/<slug>/recon/source_of_record_matrix.md`
- `runs/<slug>/recon/source_coverage_map.md`
- `runs/<slug>/recon/api_discovery_report.md`
- `runs/<slug>/recon/operator_verified_sources.yml` if operator surfaced sources
- `runs/<slug>/recon/build_eligibility_report.md`

## Verification Gates

The framework relies on multiple gates:

- Five-layer source verification gate
- Build Eligibility Gate
- P0 primary source gate
- Schema validation
- Synthetic harness
- County-agnostic regression
- Mechanical dashboard verification
- Semantic verification
- Human review gates

Work must stop at gates until the required condition or operator approval exists.

## Data Contracts

County configs live in `config/counties/<slug>.json`.

Large populated county configs must be written through `scaffold/ops/write_county_config.py`, not streamed by hand.

Scraper output must use the wrapped raw-record shape documented in `MASTER_PROMPT.md` Section 4.32.

Translators emit stable per-source base files.

Aggregators read only from base files and never from their own output.

Aggregator output must be idempotent.

## Semantic Verification

Mechanical verification is not enough.

Semantic verification checks whether output is meaningful, including debtor attribution, owner type classification, parcel resolution plausibility, enrichment decoupling, signal aggregation integrity, dashboard row integrity, and source proof links.

Deploy verdicts are:

- `DEPLOY_OK`
- `DEPLOY_BLOCKED`
- `NEEDS_OPERATOR_REVIEW`

## Memory System Role

The `.agent/memory/` folder is not part of the product pipeline.

It exists to preserve agent context across sessions and reduce drift.

It must not override `README.md`, `START_HERE.md`, `MASTER_PROMPT.md`, or the knowledge base.
