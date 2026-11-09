"""Steps parsing the workflows pubfleet ships, as YAML, the way GitHub does."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from pytest_bdd import parsers, scenarios, then, when

scenarios("workflows.feature")

SOURCE = Path(__file__).resolve().parents[2]
WORKFLOWS = SOURCE / ".github" / "workflows"


@when(parsers.parse('I parse the workflow "{workflow}"'), target_fixture="workflow")
def parse(workflow):
    text = (WORKFLOWS / workflow).read_text()
    return {"text": text, "data": yaml.safe_load(text)}


def triggers(workflow):
    # YAML reads the bare key `on` as the boolean true.
    data = workflow["data"]
    return data.get("on", data.get(True))


@then("it is called with workflow_call")
def called(workflow):
    assert "workflow_call" in triggers(workflow)


@then("every input has only a type, a default, a description or required")
def inputs_well_formed(workflow):
    inputs = triggers(workflow)["workflow_call"]["inputs"]
    for name, spec in inputs.items():
        extra = set(spec) - {"type", "default", "description", "required"}
        assert not extra, f"input {name} has unexpected keys {extra}"


@then("every job the workflow runs uses only its declared inputs")
def inputs_declared(workflow):
    declared = set(triggers(workflow)["workflow_call"]["inputs"])
    used = set(re.findall(r"inputs\.([A-Za-z0-9_-]+)", workflow["text"]))
    assert used <= declared, f"undeclared inputs used: {used - declared}"


@then("every action it uses is pinned to a full commit hash, with its version in a comment")
def pinned(workflow):
    for line in workflow["text"].splitlines():
        match = re.match(r"\s*(?:- )?uses: (\S+)(.*)", line)
        if not match or match.group(1).startswith("./") or line.lstrip().startswith("#"):
            continue
        action, rest = match.groups()
        # pubrel's and pubkit's own reusable workflows too (SonarQube's S7637).
        assert re.search(r"@[0-9a-f]{40}$", action), f"not pinned to a commit: {line.strip()}"
        assert re.match(r"\s+# v\d+\.\d+\.\d+$", rest), f"no version comment: {line.strip()}"


@then(parsers.parse('it takes a required "{name}" secret and reads the repository\'s contents only'))
def board_secret(workflow, name):
    assert triggers(workflow)["workflow_call"]["secrets"][name]["required"] is True
    assert workflow["data"]["permissions"] == {"contents": "read"}
    assert all("permissions" not in job for job in workflow["data"]["jobs"].values())


@then("it runs pubfleet board with the token as GITHUB_TOKEN")
def board_runs(workflow):
    steps = workflow["data"]["jobs"]["board"]["steps"]
    step = next(s for s in steps if "pubfleet board" in s.get("run", ""))
    assert step["env"]["GITHUB_TOKEN"] == "${{ secrets.token }}"
    assert step["shell"] == "bash"


@then(parsers.parse('it uploads board.json as the "{name}" artifact, kept 90 days, and nothing else runs'))
def board_artifact(workflow, name):
    steps = workflow["data"]["jobs"]["board"]["steps"]
    upload = steps[-1]
    assert upload["uses"].startswith("actions/upload-artifact@")
    assert upload["with"]["name"] == name and upload["with"]["retention-days"] == 90
    assert "site/board.json" in upload["with"]["path"]
    uses = [s["uses"].split("@")[0] for s in steps if "uses" in s]
    assert uses == ["actions/checkout", "actions/setup-python", "actions/upload-artifact"]
    assert list(workflow["data"]["jobs"]) == ["board"]
