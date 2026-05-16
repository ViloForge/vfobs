# vfobs — ViloForge Pipeline Observability

**See what your AI pipeline is doing while it's doing it.**

vfobs is an API-first observability service for the ViloForge AI
pipeline. The pipeline runs autonomous executor/judge agents
(vafi) against vtaskforge tasks; vfobs lets you **stream events
in, query them back, and watch a run live** — so you catch a
stuck, looping, or over-budget run *early* instead of staring at a
task until its timeout fires.

> The problem it kills: an agent that is *alive but not
> progressing* (heartbeating, no real work) used to be invisible
> until the timeout. vfobs makes that a one-line `STALLED` alert.

## What you can do with it

| Want to… | Use |
|---|---|
| Emit pipeline events from your service | `vfobs-sdk-python` `Emitter` (fire-and-forget; never breaks your hot path) |
| Ask "what happened on task/workgraph X?" | Read API — `GET /tasks/<id>/events`, `/events?filter=…` |
| Ask "how much did this cost?" | `GET /workgraphs/<id>/cost`, `/agents/<id>/cost` |
| Watch a run live & get alerted when it's stuck | `vfobs-watch --task <id>` (CRASHED / STALLED / APPROACHING_TIMEOUT) |

Status, exactly what's built/deployed/pending, and the design
decisions: **[`docs/IMPLEMENTATION-STATUS.md`](docs/IMPLEMENTATION-STATUS.md)**.

## Quick start

### Run the service

```bash
pip install -e '.[dev]'
make test-unit            # fast feedback (unit only, the default)
make test-all             # full pyramid
# container: Helm chart in charts/vfobs ; deployed to vafi-dev via ArgoCD
```

`VFOBS_DATABASE_URL` (Postgres) and `VFOBS_INGEST_TOKEN` are
required; `VFOBS_VTASKFORGE_URL` enables the read-side auth (unset
⇒ read API returns 503 by design; ingest/write unaffected).

### Emit events (the SDK)

```python
from vfobs_sdk import make_emitter, task_heartbeat

emitter = make_emitter(enabled=True, url=VFOBS_URL, token=INGEST_TOKEN)
emitter.emit(task_heartbeat(workgraph_id="wg_1", task_id="t_1",
                            source="my-service"))
# emit() is O(1), never raises, never blocks — observability is
# never on your critical path.
```

### Watch a run

```bash
pip install ./sdk/python
vfobs-watch --task t_1 --url http://localhost:8080 --token "$VTF_TOKEN" \
            --task-timeout 1800
# prints a live verdict each poll; exits non-zero on the first
# ALERT — usable as a proactive gate in an experiment harness.
```

## The SDK is the contract

`sdk/python/` (`vfobs-sdk-python`) is the **only** supported way
to talk to vfobs — the HTTP shape is an SDK implementation detail
(NFR5). It ships the typed `Emitter`, `ReadClient`, and the
`vfobs-watch` tool. Consumers (the vafi controller, watchers,
future tooling) depend on the SDK, not raw HTTP.

## Layout

```
src/vfobs/        FastAPI service (ingest + read API, repositories)
sdk/python/       vfobs-sdk-python — Emitter, ReadClient, vfobs-watch
charts/vfobs/     Helm chart (versioned atomically with the service)
tests/            unit / integration / contract / scenario + fixtures
docs/             this repo's docs (start with IMPLEMENTATION-STATUS.md)
```

Design rationale + SDD history live outside this repo:
- Design: [`viloforge-platform/docs/pipeline-observability-DESIGN.md`](https://github.com/viloforge/viloforge-platform/blob/main/docs/pipeline-observability-DESIGN.md)
- Workgraphs / decisions / retros: [`viloforge-projects/vfobs`](https://github.com/viloforge-projects/vfobs)

## Engineering discipline

Every change applies the
[engineering north star](https://github.com/viloforge/viloforge-platform/blob/main/docs/engineering-principles.md):
SOLID + named design patterns + TDD red/green + the full testing
pyramid up to scenario — and external integrations are grounded in
the **real** provider contract, never an assumed one.
