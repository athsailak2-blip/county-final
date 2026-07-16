# Current State

Last updated: 2026-07-16

## Repository

This repository contains the Xcerebro County Intelligence Framework.

It is a portable framework for building county-level lead intelligence dashboards. It is not itself a county-specific build.

The framework version stated in `README.md` is v5.3.1 stable.

## Current Work

Duval County Build Mode was explicitly authorized on 2026-07-16. The scoped build
produced a passing synthetic pipeline artifact under `runs/duval_fl/build/`.

## County Build State

The Duval Phase 0 config and launch file are in the active county's scoped paths.
Build Mode is source-limited: the repository has no current `data/raw/` inputs, and
the required Duval recon artifact set is not present.

Build verdict: `READY_WITH_BLOCKERS`.

No scrapers, adapters, dashboards, deployment files, or production refresh work were started.

## Important Active Constraint

Do not treat the build as production-ready. A live refresh requires current raw source
pulls plus the missing recon-gate artifacts and a schema-compatible translator config.

## Next Allowed Action

Next allowed action: resolve the Duval schema/recon blockers, then run a live source
refresh and mechanical/semantic verification before deployment.
