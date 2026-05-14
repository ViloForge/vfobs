# Scenario test runbook

The scenario test exercises vfobs end-to-end through a real Kubernetes
deployment: bitnami/postgresql + the vfobs image + the Helm chart from
T5, with port-forwarded HTTP + direct DB reads to verify a round-tripped
event. Per `vtf-methodologies/spec-author/bugfix.md` R10 the delivery
mechanism today is a Makefile target — CI wiring is a follow-up
`kind: infrastructure` workgraph (per `pipeline-observability-IMPLEMENTATION-PLAN.md` §13).

## Prerequisites

The following must be on `PATH`:

- `kind` (v0.24+ — `curl -L -o ~/.local/bin/kind https://kind.sigs.k8s.io/dl/v0.24.0/kind-linux-amd64 && chmod +x ~/.local/bin/kind`)
- `helm` (v3+)
- `kubectl`
- `docker`

Plus the vfobs dev install:

```bash
pip install -e '.[dev]'
```

## Running the scenario

One-shot (recommended first time):

```bash
make test-scenario
```

That target runs `scenario-prepare` (creates the kind cluster, deploys
Postgres + applies migrations, builds + loads the vfobs image, helm
installs vfobs, waits for pod readiness) then `pytest -m scenario`.

For iteration on the test code without re-spinning the cluster every
time:

```bash
make scenario-prepare          # once
make test-scenario SKIP_PREPARE=1   # repeat per test edit
```

When done:

```bash
make scenario-teardown
```

To keep the cluster around between runs (e.g., for `kubectl` debugging):

```bash
KEEP_CLUSTER=1 make scenario-prepare
```

## What the scenario actually verifies

The scenario test guards against defects that unit + integration miss:

- **Chart template defects** — only surface when `helm install` runs
  against a real apiserver.
- **Probe-path mismatches** between T3 (`/healthz`, `/readyz`) and T5
  (chart `httpGet.path`). Drift here causes silent pod restarts.
- **DSN encoding bugs** — only matter when the connection string
  travels through Secret → env → asyncpg.
- **Image build defects** — missing files, wrong entrypoint, missing
  Python dependencies (caught only at runtime).
- **DB grant gotchas** — the migration's
  `GRANT SELECT, INSERT ON ALL TABLES` runs against a real `vfobs_app`
  user.

## Troubleshooting

- **"required tool 'kind' not on PATH"** — install per the prerequisite
  block above.
- **`kind create cluster` fails with "Cannot connect to the Docker
  daemon"** — start docker (`sudo systemctl start docker` on Linux) or
  ensure your user is in the `docker` group.
- **Pod readiness times out at 120s** — `kubectl --context
  kind-vfobs-scenario -n vfobs-test describe pod -l
  app.kubernetes.io/name=vfobs` shows the failure. Common: image pull
  policy mismatch (must be `IfNotPresent` for kind-loaded images),
  bitnami postgres not ready yet.
- **`alembic upgrade head` fails during prepare** — the port-forward
  to the bitnami postgres may not have come up. Re-run prepare; the
  script waits for TCP readiness but slow Docker can extend bootup.

## CI wiring (future)

Out of scope for WG1 per the implementation plan. When CI lands as a
follow-up `kind: infrastructure` workgraph, the scenario test runs
nightly + on release candidates against the same `Makefile` target.
The test code does not need to change.
