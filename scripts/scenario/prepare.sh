#!/usr/bin/env bash
set -euo pipefail

# Operator runbook: docs/scenario-test-runbook.md

CLUSTER="${KIND_CLUSTER:-vfobs-scenario}"
NS="vfobs-test"
IMAGE_TAG="${IMAGE_TAG:-scenario}"
KEEP_CLUSTER="${KEEP_CLUSTER:-0}"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

# ---- 1. tool presence --------------------------------------------------------

for tool in kind helm kubectl docker; do
  if ! command -v "$tool" >/dev/null; then
    echo "ERROR: required tool '$tool' not on PATH" >&2
    case "$tool" in
      kind) echo "  install: curl -L -o ~/.local/bin/kind https://kind.sigs.k8s.io/dl/v0.24.0/kind-linux-amd64 && chmod +x ~/.local/bin/kind" >&2 ;;
      helm) echo "  install: https://helm.sh/docs/intro/install/" >&2 ;;
      kubectl) echo "  install: https://kubernetes.io/docs/tasks/tools/" >&2 ;;
      docker) echo "  install: https://docs.docker.com/engine/install/" >&2 ;;
    esac
    exit 1
  fi
done

echo "==> tools present"

# ---- 2. cluster --------------------------------------------------------------

if kind get clusters | grep -qx "$CLUSTER"; then
  echo "==> cluster '$CLUSTER' already exists (reusing)"
else
  echo "==> creating kind cluster '$CLUSTER'"
  kind create cluster --name "$CLUSTER"
fi

kubectl --context "kind-$CLUSTER" create namespace "$NS" --dry-run=client -o yaml \
  | kubectl --context "kind-$CLUSTER" apply -f -

# ---- 3. postgres -------------------------------------------------------------
# Use a minimal in-cluster Postgres manifest (postgres:15-alpine).
# We do NOT use the bitnami/postgresql chart: Bitnami removed
# bitnami/* images from Docker Hub in 2025 (chart 15.5.20 still
# references docker.io/bitnami/postgresql:16.3.0-debian-12-r23 which
# returns 404). The simple manifest avoids the moving-target.

echo "==> deploying postgres (postgres:15-alpine) via kubectl apply"
kubectl --context "kind-$CLUSTER" apply -f tests/fixtures/scenario-postgres.yaml -n "$NS"

echo "==> waiting for postgres pod readiness"
kubectl --context "kind-$CLUSTER" wait --for=condition=ready pod \
  -l app.kubernetes.io/name=vfobs-pg \
  -n "$NS" --timeout=120s

# ---- 4. schema bootstrap -----------------------------------------------------

echo "==> bootstrapping vfobs schema via alembic"

# Start a port-forward in the background and wait until it accepts a TCP connection.
kubectl --context "kind-$CLUSTER" -n "$NS" port-forward svc/vfobs-pg-postgresql 15432:5432 >/dev/null 2>&1 &
PF_PID=$!
cleanup() { kill "$PF_PID" 2>/dev/null || true; }
trap cleanup EXIT

for _ in $(seq 1 30); do
  if (echo > /dev/tcp/127.0.0.1/15432) >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

VFOBS_DATABASE_URL="postgresql+asyncpg://vfobs_app:devpassword@127.0.0.1:15432/vfobs" \
VFOBS_INGEST_TOKEN="scenario-test-token" \
"$REPO_ROOT/.venv/bin/alembic" upgrade head

cleanup
trap - EXIT

# ---- 5. build + load image ---------------------------------------------------

echo "==> building vfobs image (tag=$IMAGE_TAG)"
docker build -t "viloforge/vfobs:$IMAGE_TAG" .
echo "==> loading image into kind"
kind load docker-image "viloforge/vfobs:$IMAGE_TAG" --name "$CLUSTER"

# ---- 6. literal secret + helm install vfobs ---------------------------------

echo "==> applying scenario secret (literal, ESO disabled)"
kubectl --context "kind-$CLUSTER" apply -f tests/fixtures/scenario-secrets.yaml -n "$NS"

echo "==> helm install vfobs"
helm --kube-context "kind-$CLUSTER" upgrade --install vfobs ./charts/vfobs \
  --values tests/fixtures/values-scenario.yaml \
  --namespace "$NS" \
  --set image.tag="$IMAGE_TAG" \
  --wait --timeout 5m

# ---- 7. readiness ------------------------------------------------------------

echo "==> waiting for vfobs pod readiness"
kubectl --context "kind-$CLUSTER" wait --for=condition=ready pod \
  -l app.kubernetes.io/name=vfobs \
  -n "$NS" --timeout=120s

echo "==> scenario environment ready"
