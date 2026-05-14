#!/usr/bin/env bash
set -euo pipefail

CLUSTER="${KIND_CLUSTER:-vfobs-scenario}"

if ! command -v kind >/dev/null; then
  echo "kind not installed — nothing to tear down."
  exit 0
fi

if kind get clusters | grep -qx "$CLUSTER"; then
  echo "==> deleting kind cluster '$CLUSTER'"
  kind delete cluster --name "$CLUSTER"
else
  echo "==> cluster '$CLUSTER' not found — nothing to tear down."
fi
