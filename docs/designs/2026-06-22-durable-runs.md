# Durable runs — Phase 1 (resumable job, no new deps)

## Problem

A run was a single synchronous `ResearchPipeline.create_run` call: it discovered
candidates, looped them doing evidence → metadata → qualify → score → strategy →
apollo → outreach **all in memory**, and only `save_run`'d once at the very end. If the
Cloud Run instance recycled mid-loop (it's a private, scale-to-zero service), the entire
run was lost — which is exactly why only the code-resident seed run survives a restart and
user-created runs are ephemeral.

The stated #1 priority is **durable, resumable workflows**. Phase 1 makes a run a
durable job using the existing DB-backed store — no Temporal/DBOS/Inngest yet.

## Model

A run carries a `job` block (NOT `workflow` — that key is reserved by the store for the
lead-status UI surface, stripped on save and regenerated on hydrate; `job` survives the
round-trip):

```
run["job"] = {
  "stage": "processing" | "done",
  "candidates": [ <serialized DiscoveryCandidate>, ... ],  # captured once, at discovery
  "processed_domains": [ ... ],                            # the cursor
  "total": N,
  "qualified_count": int, "outreach_count": int,           # metering, accumulated + persisted
  "criteria_markdown": str,                                # captured inputs → deterministic resume
  "options": { fetch, max_pages, include_github, use_apollo, qualifier, outreach_mode },
  "started_at", "updated_at", "attempts", "error",
}
```

## Control flow

- `create_run` resolves criteria/settings, runs **discovery** (the metered, non-idempotent
  step) exactly once, records the discovery charge immediately, builds the `job` skeleton
  with `status:"running"`, and `save_run`s **before** any candidate work. The run now exists
  in the store the moment it starts.
- `_drive_run` (shared by create + resume) loops the captured candidates, skipping any in
  `processed_domains`, and `save_run`s a **checkpoint after each candidate**. A recycle now
  loses at most one in-flight candidate, not the whole run. On any exception it stamps
  `job.error`, sets `status:"failed"`, persists, and re-raises (preserving the original
  HTTP-500 semantics for `POST /api/runs`).
- `resume_run(run_id)` reloads a `running`/`failed` run, bumps `attempts`, clears `error`,
  and drives the remainder to `completed`. It reads everything from the persisted run
  (captured candidates + criteria + options), so resume is deterministic and — critically —
  **never re-discovers or re-charges**. Already-`completed` → no-op; unknown → `None`;
  pre-durability run with no captured candidates → returned untouched (nothing safe to resume).
- `POST /api/runs/{id}/resume` exposes recovery to an operator. No new budget guard: the work
  was authorized at create time; resume only finishes captured work.

## Metering

Discovery is recorded once in `create_run` (it already happened, so the charge is captured
even if processing later crashes). Qualify/outreach counts accumulate on the `job` block per
candidate (crash-safe) and are recorded once at finalize using the persisted totals — same
batched audit semantics as before, but now durable across a resume (skipped candidates aren't
re-counted).

## Tests

- `tests/test_research.py::DurableRunTest` — crash mid-loop persists a `failed` run with the
  first lead + cursor + captured candidates, discovery charged once; resume completes it with
  both leads, `attempts:2`, and **no second discovery call**; completed-run resume is a no-op;
  happy-path run carries the `job` block and the final checkpoint matches the reload; unknown
  run → `None`.
- `tests/test_web.py::WebResumeTest` — `POST /resume` no-ops a completed run and 404s an
  unknown id.

## Deferred (Phase 1.5+)

- **Auto-resume on boot**: on server start, scan for `running`/`failed` runs and drive them in
  a background thread so recovery is automatic, not operator-triggered. Safe because the
  checkpoint is post-candidate (idempotent resume). Left out of Phase 1 to keep the change
  reviewable and avoid blocking startup.
- **Sub-candidate checkpointing** (evidence vs qualify vs outreach as separate stages) and a
  real workflow engine (Temporal/DBOS/Inngest) remain Phase 2 — only warranted once the
  job-controller seam proves insufficient.
- **Concurrent-resume guard**: two resumers on the same run would double-process the tail.
  A `running` lease/owner stamp is the Phase 1.5 fix; today resume is operator-serial.
