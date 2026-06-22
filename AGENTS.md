# AGENTS.md

Repository operating rules for AI agents working on the Xcerebro County Intelligence Framework.

## Required Reading Before Work

Before creating or modifying files, read:

1. `README.md`
2. `START_HERE.md`
3. `MASTER_PROMPT.md`
4. `TASK_QUEUE.md`
5. `.agent/memory/current_state.md`
6. `.agent/memory/architecture.md`
7. `.agent/memory/decisions.md`
8. `.agent/memory/mistakes.md`
9. Any county-specific launch file under `runs/<slug>/` if a county run exists

If the task is county implementation, also read every file listed in `MASTER_PROMPT.md` Section 1 before writing code.

## Canonical Precedence Rule

If memory files conflict with `README.md`, `START_HERE.md`, `MASTER_PROMPT.md`, `knowledge_base/`, schemas, or framework contracts, the canonical framework documents always win.

## Scope Discipline

This repository is a universal county lead intelligence framework.

Do not hardcode a county, state, source URL, portal hostname, municipality list, statute, scraper dispatch path, or vendor-specific rule in universal framework code.

County-specific information belongs only in:

- `config/counties/<slug>.json`
- `runs/<slug>/`
- `scrapers/<source>.py`
- County-scoped translator registration when needed
- County-scoped build artifacts

## Task Execution Rule

When assigned work:

1. Work only on the highest-priority active task.
2. Complete one task only.
3. Stop after task completion.
4. Report:
   - files changed
   - tests run
   - blockers found
   - next recommended task

Do not automatically continue to the next task.

## Read-Only Audit Rule

When asked to audit, review, analyze, summarize, or report, do not modify files unless explicitly instructed.

## Queue Update Rule

When a task starts, mark it In Progress.

When completed, mark it Completed.

Do not automatically start the next task.

## County Implementation Guardrail

Do not start county implementation unless the operator explicitly authorizes it.

County implementation includes:

- Running Phase 0 recon
- Creating or populating `config/counties/<slug>.json`
- Creating `runs/<slug>/`
- Building scrapers
- Building adapters
- Creating dashboards
- Deploying GitHub Pages
- Creating Supabase tables
- Running production refresh or alerting work

## First-Run County Rule

If the operator asks to build a county with a one-sentence instruction, follow `MASTER_PROMPT.md` Section 4.5.

Default behavior:

1. Parse target county and state.
2. Show interpreted target and slug.
3. Check whether `config/counties/<slug>.json` or `runs/<slug>/` already exists.
4. If neither exists, request approval for only:
   `python scaffold/bootstrap_county.py --county "<County Name>" --state "<State>" --slug <slug> --phase phase0`
5. Run Phase 0 only.
6. Stop at the Build Mode Approval Gate.

## Product Rule

This is an official event source-driven lead intelligence framework.

Primary lead events can originate from clerk, recorder, court, sheriff, tax delinquency, foreclosure, probate, lien, judgment, lis pendens, code enforcement, demolition, condemnation, or similar official event sources.

Enrichment sources never create lead rows by themselves. Parcel, GIS, assessor, tax roll, owner, vacancy, valuation, and similar data can only decorate or filter event-originated leads.

If no verified primary lead source exists, stop honestly. Do not create a false dashboard.

## Evidence Rule

If a fact is not in source data, county config, knowledge base, scraper log, verified output, or operator-provided notes, do not present it as true.

Use the framework labels:

- `Confirmed`
- `Estimated`
- `Possible`
- `Unknown`
- `Needs Review`
- `Unsupported`
- `Blocked`
- `Do Not Export`

## Verification Rule

Do not declare work complete unless the relevant verification gate has passed.

For framework changes, run the appropriate tests when available.

For county build work, follow the phase gates in `MASTER_PROMPT.md`, including:

- Phase 0 source verification
- Schema validation
- P0 gate
- Synthetic harness
- County-agnostic regression
- Mechanical verification
- Semantic verification
- Human review gates

## Config Write Rule

Populated county configs must be written through `scaffold/ops/write_county_config.py`.

Do not stream-write large county JSON configs by hand.

If the writer fails, follow the structured repair rule in `MASTER_PROMPT.md` Section 4.28.

## Memory Update Rule

Update `.agent/memory/` files when work changes durable project state.

Use these files as follows:

- `current_state.md` records what is true right now.
- `architecture.md` records stable architecture and invariants.
- `decisions.md` records operator-approved decisions and why they were made.
- `mistakes.md` records known failure modes and prevention rules.

Do not put secrets, credentials, API keys, tokens, private client details, or paid portal credentials in memory files.

`current_state.md` must be updated whenever the active task or next allowed action changes.

## Change Manifest Rule

After modifying framework files, report a change manifest with:

- Files changed
- Reason for each change
- New fields added
- Rules modified
- Rules removed
- Tests updated or run
- Whether any county-specific language was found in universal files

## Collaboration Rule

Prefer the smallest correct change.

Do not rename folders, move canonical files, create parallel systems, or alter locked framework rules without explicit operator approval.
