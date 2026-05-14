import os
import shutil
import socket
import subprocess
import time
from collections.abc import Iterator

import pytest

KIND_CLUSTER = os.environ.get("KIND_CLUSTER", "vfobs-scenario")
NAMESPACE = os.environ.get("VFOBS_TEST_NAMESPACE", "vfobs-test")


def _kctx_args() -> list[str]:
    return ["--context", f"kind-{KIND_CLUSTER}", "-n", NAMESPACE]


def _wait_port(host: str, port: int, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return
        except OSError as err:
            last_err = err
            time.sleep(0.5)
    raise RuntimeError(f"port-forward to {host}:{port} never came up: {last_err}")


def _start_port_forward(svc: str, local_port: int, remote_port: int) -> subprocess.Popen:
    cmd = [
        "kubectl", *_kctx_args(),
        "port-forward", f"svc/{svc}",
        f"{local_port}:{remote_port}",
    ]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    _wait_port("127.0.0.1", local_port)
    return proc


@pytest.fixture(scope="session", autouse=True)
def _scenario_preflight():
    """Skip scenario tests entirely if the scenario environment is not
    prepared. The Makefile target `scenario-prepare` is responsible for
    bringing the cluster + pods up; this fixture just confirms readiness
    rather than booting anything from inside the test."""
    if shutil.which("kubectl") is None:
        pytest.skip("kubectl not available — cannot drive scenario tests")
    if shutil.which("kind") is None:
        pytest.skip("kind not available — cannot drive scenario tests")
    clusters = subprocess.run(
        ["kind", "get", "clusters"], capture_output=True, text=True, check=False
    ).stdout.split()
    if KIND_CLUSTER not in clusters:
        pytest.skip(
            f"kind cluster '{KIND_CLUSTER}' not found — run `make scenario-prepare` first"
        )


@pytest.fixture
def vfobs_port() -> Iterator[int]:
    proc = _start_port_forward("vfobs", 18080, 8080)
    try:
        yield 18080
    finally:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.fixture
def pg_port() -> Iterator[int]:
    proc = _start_port_forward("vfobs-pg-postgresql", 15433, 5432)
    try:
        yield 15433
    finally:
        proc.terminate()
        proc.wait(timeout=5)
