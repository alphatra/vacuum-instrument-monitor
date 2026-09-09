"""Deployment contract: only tested code reaches the Pi.

These assert on the workflow and deploy script rather than on Python, because
that is where the deployment decision actually lives.
"""

import pathlib

import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
DEPLOY_WORKFLOW = REPO / ".github/workflows/deploy-pi.yml"
DEPLOY_SCRIPT = REPO / "scripts/deploy_on_pi.sh"


def load_workflow() -> dict:
    # PyYAML parses the `on:` key as boolean True.
    return yaml.safe_load(DEPLOY_WORKFLOW.read_text())


def triggers(workflow: dict) -> dict:
    # PyYAML parses the `on:` key as boolean True.
    return workflow.get("on") or workflow.get(True, {})


def test_deploy_does_not_run_on_push():
    """push starts CI and deploy in parallel, so untested code can land."""
    assert "push" not in triggers(load_workflow()), (
        "deploy triggers on push; it would race CI instead of waiting for it"
    )


def test_deploy_waits_for_ci_workflow():
    trigger = triggers(load_workflow())
    assert "workflow_run" in trigger, "deploy must be gated on the CI workflow"
    assert "CI" in trigger["workflow_run"]["workflows"]


def test_deploy_requires_ci_success():
    job = load_workflow()["jobs"]["deploy"]
    condition = job.get("if", "")
    assert "success" in condition and "conclusion" in condition, (
        f"deploy job must require a successful CI run, got: {condition!r}"
    )


def test_deploy_passes_the_tested_commit():
    """The commit CI verified, not whatever main points at during deploy."""
    text = DEPLOY_WORKFLOW.read_text()
    assert "head_sha" in text, "deploy must pass the CI-verified SHA to the Pi"


def test_deploy_script_checks_out_exact_commit():
    text = DEPLOY_SCRIPT.read_text()
    assert 'git reset --hard "origin/$BRANCH"' not in text, (
        "resetting to the branch tip can deploy a commit CI never saw"
    )
    assert "TARGET_SHA" in text or "DEPLOY_SHA" in text, (
        "deploy script must accept an explicit commit to deploy"
    )
