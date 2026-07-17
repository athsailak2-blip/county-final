# TASK_QUEUE.md

Durable task queue for this repository.

Last updated: 2026-07-16

## Status

Repository management system has been created. No county implementation has started.

## Active Gate

Operator approved creation of:

- `AGENTS.md`
- `TASK_QUEUE.md`
- `.agent/`
- `.agent/memory/`
- `.agent/memory/current_state.md`
- `.agent/memory/architecture.md`
- `.agent/memory/decisions.md`
- `.agent/memory/mistakes.md`

## Queue Processing Rule

Only the first non-blocked task may be worked on.

Completion of a task does not authorize the next task.

Wait for operator approval before continuing.

When a task starts, mark it In Progress.

When completed, mark it Completed.

Do not automatically start the next task.

## Queue

| ID | Status | Priority | Task | Notes |
|---|---|---:|---|---|
| TQ-001 | Completed | High | Create repository management system | Created only the approved files and folders. No county implementation was started. |
| TQ-002 | Completed | High | County implementation | Duval Build Mode was authorized and the scoped synthetic gate completed; production remains blocked by missing raw/recon inputs and schema drift. |
| TQ-003 | Pending | Medium | Maintain project memory after future work | Update `.agent/memory/` after durable architecture, state, decision, or mistake changes. |

## Rules

- Do not start tasks marked `Blocked`.
- Do not infer county target from repo name.
- Do not run Phase 0 unless explicitly authorized.
- Do not enter Build Mode unless the Build Mode Approval Gate is explicitly approved.
- Keep this queue factual and current.
