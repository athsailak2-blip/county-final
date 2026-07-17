# CONFIG_WRITE_FAILED

**County:** Harris County, Texas
**Slug:** harris_tx
**At:** 2026-07-16T14:35:00Z

## What happened

Wrote a Harris County config dict with sources including `court_civil`. After multiple schema-invalid writer failures and targeted repairs, the latest writer call failed with:

- Schema validation failed at `['sources', 'court_civil', 'auto_resolve_status']`: `'CREDENTIALS_PROVIDED'` is not one of `['NOT_ATTEMPTED','ATTEMPTING','RESOLVED','PARTIALLY_RESOLVED','FAILED','REQUIRES_OPERATOR_APPROVAL','REQUIRES_CREDENTIALS','REQUIRES_PAYMENT','REQUIRES_MANUAL_ASSISTANCE','NOT_ALLOWED','']`

## Diagnosis

The localized symptom is the `court_civil.auto_resolve_status` value `CREDENTIALS_PROVIDED`, which does not match the schema enum. Changing it to `REQUIRES_CREDENTIALS` should resolve this specific failure, but because this exact issue has recurred across repeated patch-then-retry cycles, the safest repo-compliant action is to stop and surface the choice in `operator_notes.md`.

## Temp artifacts

- `/Users/krishnamukteswararaoappana/county-final/config/counties/harris_tx.iokheuek.tmp.json`

## Required next action

In `operator_notes.md`, choose one:
- A. Defer `court_civil` and keep Phase 0 READY_TO_BUILD without the login-walled source.
- B. Keep `court_civil` as `REQUIRES_CREDENTIALS` and proceed to Build Mode with secure credential injection handled outside the schema.
