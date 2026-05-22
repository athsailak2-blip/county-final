# v5.4.0 pending behavioral specs

The tests in this directory are **pending v5.4.0 behavioral specifications**.
They are **expected to fail today** and that is correct.

## What these are

These are executable behavioral specs for the v5.4.0 staged pipeline engine.
Each test imports a real engine module, calls it on a real input, and asserts
on the real output. They are **not** doc-presence checks — they do not scan
markdown for phrases. (The doc-presence pattern in `scaffold/tests/v5_3_0/` is
exactly the gap that escalation ESC-002 exposed: the §16-§20 contracts were
shipped as documentation with passing doc-presence tests, while the executable
pipeline behind them was never built. v5.4.0 builds that engine; these tests
prove it behaves.)

## Why they fail right now

v5.4.0 Session 1 delivered the interface contracts and the engine **stubs**.
Every engine function currently does `raise NotImplementedError`. So every test
here fails today — they have nothing implemented to exercise yet. That is the
point of quarantining them here.

## Why they are NOT in run_all.py

`scaffold/tests/run_all.py` is the default regression gate and must stay green.
These specs are red until the engine is built, so wiring them into `run_all.py`
now would make the default suite red. They are deliberately excluded.

## Promotion schedule

As each engine stage is implemented, that session moves its spec(s) out of this
directory into `scaffold/tests/v5_4_0/` and wires them into `run_all.py`, so the
default suite grows to gate real engine behavior:

| Session | Implements | Promotes |
|---|---|---|
| Session 2 | §17 debtor party engine | `test_debtor_party_engine_behavior.py`, `test_filer_suppression_behavior.py` |
| Session 3 | §18 aggregation key engine + leads-base writer | `test_aggregation_key_behavior.py` |
| Session 4 | §19 idempotent aggregator | `test_aggregator_idempotent_behavior.py` |
| Session 5 | cutover | (all promoted; monolith retired) |

A spec is promoted only once the stage it covers is implemented and the spec
passes. Until then it stays here, red, as the binding spec for that stage.

## The tests

- `test_debtor_party_engine_behavior.py` — the §17 engine resolves the debtor
  (lead subject), not the filer. Anchored on the LAKEVIEW → CANTY lis pendens
  case: the plaintiff/lender LAKEVIEW LOAN SERVICING files; the defendant CANTY
  is the lead subject.
- `test_filer_suppression_behavior.py` — a known filer (government / lender /
  trustee) is never emitted as `owner_name`; it is routed to `REVIEW_REQUIRED`
  with the filer captured in `filer_entity` (§17.D / §17.E).
- `test_aggregation_key_behavior.py` — the §18.B key groups same-key records
  and keeps distinct `signal_type` values distinct (§18.F anti-collapse rule).
- `test_aggregator_idempotent_behavior.py` — the §19 aggregator produces
  identical output on a second run and refuses to read `matched_leads.json` as
  input (§19.C / §19.D).
