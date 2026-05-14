# CLAUDE.md — vfobs (ViloForge Pipeline Observability)

Guidance for Claude Code sessions working in this repo.

## What this is

vfobs is the **pipeline observability service** for the ViloForge
AI agent fleet. v1 ships event ingestion, SSE streams, anomaly
detection (one detector: stuck-task), cost rollups, and workgraph
DAG views. API-first; SDK-as-boundary.

## Canonical docs (read first)

These live in `viloforge/viloforge-platform` — NOT here — and they
override anything you might infer from this repo:

- `docs/pipeline-observability-DESIGN.md` (v0.2 — locked architecture)
- `docs/pipeline-observability-IMPLEMENTATION-PLAN.md` (v0.2 — 5 WGs)
- `docs/engineering-principles.md` (v1.0 — non-negotiable north star)

SDD artifacts (workgraphs, decisions, gotchas) live in
`viloforge-projects/vfobs`.

## Non-negotiable engineering discipline

Every change applies the engineering north star:

- **SOLID** + named design patterns (cited in commit / PR)
- **TDD red/green** for every implementation step
- **Full testing pyramid**: unit → integration → contract → scenario,
  at the levels that scope touches
- **Extensibility affordances**: `org_id`, `cluster_id`, config-driven
  thresholds present in v1 contracts (hardcoded to `viloforge` /
  `vafi-dev` defaults)
- **SDK-as-boundary**: no raw HTTP consumers, ever — go through
  `vfobs-sdk-python`

## Layout

```
src/vfobs/                 service code (FastAPI app, repositories, workers)
vfobs-sdk-python/          canonical Python SDK (NFR5; SDK-as-boundary)
charts/vfobs/              Helm chart (atomic versioning with service)
tests/{unit,integration,contract,scenario}/
docs/                      repo-local docs only; decisions live in viloforge-projects/vfobs
```

## Tests

```bash
make test-unit          # fast, default — every commit
make test-integration   # real Postgres + HTTP
make test-contract      # SDK ↔ API + event schema
make test-scenario      # kind cluster, full lifecycle
make test-all           # everything
```

## Postgres

Per OIQ2 resolution: vfobs **shares vtaskforge's Postgres instance**;
own schema (`vfobs`), own DB user, schema-scoped grants. Event table
is partitioned by time from day 1 (retention discipline).

## Implementation pace

Per operator decision 2026-05-14: I (Claude in chat) implement vfobs
manually using full SDD discipline while vafi-executor remains
unreliable. Per-task vtaskforge records still get created (the
discipline doesn't change, only who runs the code).
