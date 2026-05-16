# vfobs — implementation status & wrap-up

**As of 2026-05-16.** This is the honest record of what is *built,
deployed, and verified* — and what is not yet. It supersedes the
old README "WG0 scaffolding" framing. Design rationale lives in
`viloforge-platform/docs/pipeline-observability-DESIGN.md`; SDD
history (workgraphs/decisions/retros) in `viloforge-projects/vfobs`.

Status legend: ✅ done+merged ・ 🟢 deployed+verified on vafi-dev
・ 🟡 built, not yet end-to-end verified ・ ⛔ not built (future).

## What vfobs is

An API-first observability service for the ViloForge AI pipeline.
The pipeline (vafi controller running executor/judge agents
against vtaskforge tasks) emits events into vfobs; operators query
and **watch runs live** to catch a stuck/looping/over-budget run
*early* instead of waiting for the task timeout.

## What was built

### WG1 — foundation (write side + event store) ✅ 🟢
- `POST /events` ingest API; shared-token (`IngestAuth`) auth.
- 17 typed event models across 6 namespaces
  (`task.*`, `harness.*`, `workgraph.*`, `gate.*`, `judge.*`,
  `anomaly.*`); v1 envelope schema **locked** in
  `tests/fixtures/event_schemas.v1.json`.
- Postgres event store: time-partitioned `vfobs.events`,
  `EventRepository` (Postgres + InMemory LSP impls).
- Helm chart, alembic migrate Job, kind scenario harness.

### WG2 — read API + cost (PRs vfobs#10–#15) ✅ 🟢
- `GET /workgraphs/<id>`, `/tasks/<id>`, `/tasks/<id>/events`,
  `/events?filter=…`, `/workgraphs/<id>/cost`,
  `/agents/<id>/cost`.
- `ReadAuth` strategy (operator token, see OIQ3 below).
- **Verifier-found corrections (load-bearing):**
  - **F1 → R2:** the DB id is *not* on the wire `Event` (its v1
    schema is a locked contract). A read-only
    `StoredEvent{id,event}` carries it; pagination uses that.
  - **F2:** cost rollups count the *latest* `execution_summary`
    per task (no double-count under rework).
  - **D-T0-1:** read-side is *degradable* — a misconfigured
    vtaskforge URL must not crash the app (returns 503, app+write
    path stay up). Health/readiness separation, not boot-crash.

### WG5-minimal — emit + watch (PRs vfobs#16–#19, vafi#5) ✅
- **`vfobs-sdk-python`** (`sdk/python/`): fire-and-forget
  `Emitter` (bounded queue, never raises into the caller,
  `NullEmitter` when unconfigured) + typed event constructors +
  `ReadClient`. The versioned client contract (NFR5).
- **`vfobs-watch`** CLI: polls the read API, applies anomaly
  rules (`Crashed` > `Stall` > `ApproachingTimeout`) and prints a
  live verdict; non-zero exit on first ALERT. `Stall` keys on
  **workdir-change recency** (the harness is an opaque
  subprocess — no mid-run harness events; corrected from the
  first design in vfobs#18).
- **vafi controller hooks** (vafi#5, T1): emits `task.claimed`,
  per-tick `task.heartbeat` + `task.workdir_changed`, terminal
  `task.state_changed`, coarse `harness.turn_*`. Optional dep,
  **default OFF**, fail-safe (a dead/slow vfobs cannot raise,
  block, or slow the controller — proven by test).
  `vfobs "workgraph" == vtaskforge milestone` (D-T1-impl-1).

### OIQ3 grounding fix (PR vfobs#20) ✅ 🟢
WG2's token-piggyback auth was built against an **invented**
`/v2/auth/whoami` + `Bearer` (vtaskforge has neither). Corrected
against the **real** vtaskforge source, every endpoint/field
cited:
- `GET /v2/auth/validate/` with `Authorization: Token <t>`
  (DRF) — the real token-validation endpoint.
- `get_workgraph → /v2/milestones/<id>/`,
  `get_task → /v2/tasks/<id>/`; DTOs ← real serializers.
- Metadata calls fail-safe (non-200/non-JSON → None, never 500);
  `read_auth=None → 503` (the D-T0-1 promise, was a 500).
- vtfstub + all tests **rederived from the real contract**.

## Verified vs pending

- 🟢 **Verified end-to-end on vafi-dev (real vtaskforge, real
  token):** read API auth — unauth/bad → 401, real token → 200;
  `vfobs-watch` consumes the deployed read API and produces
  correct anomaly verdicts. Repo suite: 84 unit / 3 contract /
  39 integration green.
- 🟢 **L4b — emission path live & verified on vafi-dev
  (2026-05-16):** the `vafi-executor`/`pi`/`judge` fleet is
  redeployed on the observability-extra image (`aa32a8a`) with
  `VFOBS_EMIT_*` + the `vfobs-ingest-token` ESO-plumbed into
  `vafi-secrets`. Verified *in the running executor pod*:
  `vfobs_sdk` imports, `emission._SDK_AVAILABLE == True`,
  `build_emitter()` returns a real **`HttpEmitter`** (not
  `NullEmitter`) pointed at the OIQ3-fixed vfobs. Executor is
  registered + polling. **First `task.*`/`harness.*` events land
  when it next claims a task — normal operation, not a defect.**
  The found+fixed root cause (the image lacked the optional
  `[observability]` extra ⇒ silent `NullEmitter`) is kb gotcha
  `uiZQyRGr`.
- 🟡 **Remaining = demonstration, not engineering:** a captured
  live `vfobs-watch` STALLED-before-timeout against a real run.
  Gated only on a claimable task existing — i.e. normal
  vtaskforge/vafi development use, which is exactly what this
  unblocks. The WG5-min T3 kind-scenario (specced, stub
  rederived) is the offline equivalent and can run anytime via
  `make scenario-prepare && make test-scenario`.
- ⛔ **Not built (future workgraphs):** SSE streams + DAG view
  (WG3); server-side anomaly worker / cost-anomaly (WG4); full
  controller instrumentation, judge-path events (later WG5).

## Deployment

- vafi-dev: ArgoCD app `vfobs-dev` (multi-source: chart from
  `viloforge/vfobs`, values from `viloforge-platform`
  `argo/products/vfobs/values.yaml`). Image tag auto-bumped by
  the build pipeline on every `vfobs:main` push.
- **Operational note:** ArgoCD's compare-cache can go stale —
  if a known-merged change isn't live, hard-refresh the app
  (`kubectl annotate application vfobs-dev -n argocd
  argocd.argoproj.io/refresh=hard --overwrite`) before deeper
  debugging.
- `VFOBS_VTASKFORGE_URL` must point at the real vtaskforge API
  (`vtf-api.vtf-dev.svc.cluster.local:8000`); unset ⇒ read API
  degrades to 503 (by design), write/ingest unaffected.

## Lessons captured (so they don't recur)

- The OIQ3 defect (build against an invented external endpoint,
  validated only by a self-authored stub) is recorded as kb
  `feedback-external-contract-grounding` and enforced by verifier
  **V18** (`vtf-methodologies/verifier/bugfix.md`): external
  contracts must cite the real provider source/OpenAPI; stubs
  derived from it, never invented.
- Verifier V16 (required-config vs frozen fixtures) and V17
  (inline patch vs locked-contract artifact) likewise came from
  this build.

## Pointers

- Design: `viloforge-platform/docs/pipeline-observability-DESIGN.md`
- SDD history: `viloforge-projects/vfobs/workgraphs/{foundation,
  read-api,controller-instrumentation}/`
- Operate the scenario: `docs/scenario-test-runbook.md`
- Use it: `README.md` (quick start, SDK, watcher)
