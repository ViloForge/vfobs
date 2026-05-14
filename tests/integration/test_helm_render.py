import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CHART = REPO_ROOT / "charts" / "vfobs"
DEV_VALUES = REPO_ROOT / "tests" / "fixtures" / "values-dev.yaml"
MON_VALUES = REPO_ROOT / "tests" / "fixtures" / "values-monitoring.yaml"

requires_helm = pytest.mark.skipif(
    shutil.which("helm") is None, reason="helm binary not on PATH"
)


def _render(values: Path) -> list[dict]:
    out = subprocess.check_output(
        [
            "helm", "template", "vfobs-test", str(CHART),
            "--namespace", "vfobs-test",
            "--values", str(values),
        ],
        text=True,
    )
    return [d for d in yaml.safe_load_all(out) if d]


@pytest.mark.integration
@requires_helm
def test_dev_values_render_core_resources():
    docs = _render(DEV_VALUES)
    kinds = {d["kind"] for d in docs}
    assert "Deployment" in kinds
    assert "Service" in kinds
    assert "ServiceAccount" in kinds
    assert "ExternalSecret" in kinds
    assert "ServiceMonitor" not in kinds  # monitoring.enabled=false by default


@pytest.mark.integration
@requires_helm
def test_monitoring_enabled_renders_servicemonitor():
    docs = _render(MON_VALUES)
    kinds = {d["kind"] for d in docs}
    assert "ServiceMonitor" in kinds


@pytest.mark.integration
@requires_helm
def test_deployment_probes_match_t3_endpoints():
    docs = _render(DEV_VALUES)
    deps = [d for d in docs if d["kind"] == "Deployment"]
    assert len(deps) == 1
    container = deps[0]["spec"]["template"]["spec"]["containers"][0]
    assert container["livenessProbe"]["httpGet"]["path"] == "/healthz"
    assert container["readinessProbe"]["httpGet"]["path"] == "/readyz"
    assert container["livenessProbe"]["httpGet"]["port"] == "http"
    assert container["readinessProbe"]["httpGet"]["port"] == "http"
    # container port matches T3
    assert container["ports"][0]["containerPort"] == 8080
    # secrets wired
    env_names = {e["name"] for e in container["env"]}
    assert "VFOBS_DATABASE_URL" in env_names
    assert "VFOBS_INGEST_TOKEN" in env_names


@pytest.mark.integration
@requires_helm
def test_helm_lint_clean():
    subprocess.check_call(
        ["helm", "lint", str(CHART)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


@pytest.mark.integration
@requires_helm
def test_migrate_job_renders_with_hook_annotations():
    docs = _render(DEV_VALUES)
    jobs = [d for d in docs if d["kind"] == "Job"]
    assert len(jobs) == 1, f"expected one migrate Job, got {len(jobs)}"
    job = jobs[0]
    ann = job["metadata"]["annotations"]
    assert ann["helm.sh/hook"] == "pre-install,pre-upgrade"
    assert ann["helm.sh/hook-delete-policy"] == "before-hook-creation"
    assert ann["argocd.argoproj.io/hook"] == "PreSync"
    # vfobs_app password is read from the runtime Secret's POSTGRES_PASSWORD
    # key — must agree with the migration's CREATE ROLE statement.
    env = job["spec"]["template"]["spec"]["containers"][0]["env"]
    env_names = {e["name"] for e in env}
    assert env_names == {"VFOBS_DATABASE_URL", "VFOBS_APP_DB_PASSWORD", "VFOBS_INGEST_TOKEN"}


@pytest.mark.integration
@requires_helm
def test_migrate_job_suppressed_when_disabled(tmp_path):
    values = tmp_path / "values.yaml"
    values.write_text(
        "image:\n  repository: viloforge/vfobs\n  tag: '0.0.1'\n"
        "eso:\n  enabled: true\n  secretStore:\n    name: aws-sm\n  refreshInterval: 1h\n"
        "monitoring:\n  enabled: false\n"
        "migrate:\n  enabled: false\n"
    )
    docs = _render(values)
    jobs = [d for d in docs if d["kind"] == "Job"]
    assert jobs == []


@pytest.mark.integration
@requires_helm
def test_externalsecret_disabled_when_eso_disabled(tmp_path):
    no_eso = tmp_path / "values.yaml"
    no_eso.write_text(
        "image:\n  repository: viloforge/vfobs\n  tag: '0.0.1'\n"
        "eso:\n  enabled: false\n  secretStore:\n    name: vault-backend\n  refreshInterval: 1h\n"
        "monitoring:\n  enabled: false\n"
    )
    docs = _render(no_eso)
    kinds = {d["kind"] for d in docs}
    assert "ExternalSecret" not in kinds
