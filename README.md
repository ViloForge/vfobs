# vfobs — ViloForge Pipeline Observability

API-first observability service for the ViloForge AI pipeline:
event ingestion, SSE streams, anomaly detection, cost rollups, and
workgraph DAG views.

**Status:** scaffolding (WG0). v1 design + implementation plan live
in `viloforge/viloforge-platform`:

- [`docs/pipeline-observability-DESIGN.md`](https://github.com/viloforge/viloforge-platform/blob/main/docs/pipeline-observability-DESIGN.md) — v0.2 design
- [`docs/pipeline-observability-IMPLEMENTATION-PLAN.md`](https://github.com/viloforge/viloforge-platform/blob/main/docs/pipeline-observability-IMPLEMENTATION-PLAN.md) — v0.2 plan
- [`docs/engineering-principles.md`](https://github.com/viloforge/viloforge-platform/blob/main/docs/engineering-principles.md) — non-negotiable north star

SDD artifacts (workgraphs, decisions, gotchas, observations) live in
[`viloforge-projects/vfobs`](https://github.com/viloforge-projects/vfobs).

## Layout

```
.
├── src/vfobs/                 # service code (FastAPI app, repositories, workers)
├── vfobs-sdk-python/          # canonical Python SDK (separate package, same repo)
├── charts/vfobs/              # Helm chart (atomic versioning with service)
├── tests/
│   ├── unit/                  # fast (<100ms), per-function/class
│   ├── integration/           # real components (Postgres, HTTP)
│   ├── contract/              # SDK ↔ API + event-schema validation
│   ├── scenario/              # full lifecycle, kind cluster
│   └── fixtures/              # shared test data
├── docs/                      # repo-local docs (architectural decisions land in viloforge-projects/vfobs)
├── Makefile                   # test-unit / test-integration / test-contract / test-scenario / test-all
└── pyproject.toml             # service package metadata + pytest config
```

## Quick start

```bash
# install dev deps
pip install -e '.[dev]'

# fast feedback (default — unit only)
make test-unit

# everything
make test-all
```

## Engineering discipline

Every change applies the
[engineering north star](https://github.com/viloforge/viloforge-platform/blob/main/docs/engineering-principles.md):
SOLID + named design patterns + TDD red/green + full testing pyramid
up to scenario. No exceptions.
