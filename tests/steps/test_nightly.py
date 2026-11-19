"""Steps for the nightly's loop across repositories: nightly.yml, the script
it runs in each checkout (`pubrules nightly` makes the commits there), and
install.sh and pubrel-version.sh, which choose what it installs."""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml
from pubtest.steps.programs import run_command
from pytest_bdd import parsers, scenarios, then, when


scenarios("nightly.feature")

GITHUB = Path(__file__).resolve().parents[2] / ".github"
SCRIPT = GITHUB / "nightly" / "update.sh"


@when(parsers.parse('I parse the workflow "{name}"'), target_fixture="workflow")
def parse(name):
    text = (GITHUB / "workflows" / name).read_text()
    return {"text": text, "data": yaml.safe_load(text), "script": SCRIPT.read_text()}


@then("it runs by hand and when called, with no schedule of its own")
def scheduled(workflow):
    on = workflow["data"][True]
    assert "workflow_dispatch" in on and "workflow_call" in on
    assert "schedule" not in on


@then("neither it nor its script merges a pull request")
def merges_nothing(workflow):
    for text in (workflow["text"], workflow["script"]):
        assert not re.search(r"gh pr merge|--auto\b|automerge|enablePullRequestAutoMerge", text)


@then("its script updates an open pull request before opening one")
def updates_open(workflow):
    script = workflow["script"]
    assert script.index("gh pr list") < script.index("gh pr edit") < script.index("gh pr create")
    assert "--force origin" in script


@then("its script re-tests the pins alone when CI fails")
def retests(workflow):
    script = workflow["script"]
    assert '"$pins:$branch"' in script and '"${commits[0]}" = pins' in script
    assert script.index('wait_ci "$head"') < script.index('wait_ci "$pins"')


def _steps(workflow):
    return workflow["data"]["jobs"]["update"]["steps"]


@then("each repository's token comes from the Sustenaut nightly app, for that repository alone")
def app_token(workflow):
    app = next(s for s in _steps(workflow) if s.get("id") == "app")
    assert re.fullmatch(r"actions/create-github-app-token@[0-9a-f]{40}", app["uses"])
    assert app["if"] == "env.APP_ID != ''"
    update_job = workflow["data"]["jobs"]["update"]
    assert update_job["env"]["APP_ID"] == "${{ secrets.app-id || vars.NIGHTLY_APP_ID }}"
    given = app["with"]
    assert given["app-id"] == "${{ env.APP_ID }}"
    assert given["private-key"] == "${{ secrets.app-key || secrets.NIGHTLY_APP_KEY }}"
    assert given["owner"] == "${{ steps.where.outputs.owner }}"
    assert given["repositories"] == "${{ steps.where.outputs.name }}"
    update = next(s for s in _steps(workflow) if "update.sh" in s.get("run", ""))
    assert update["env"]["GH_TOKEN"] == "${{ steps.token.outputs.token }}"


@then("the token may write only contents, pull requests and workflows, and read actions")
def app_permissions(workflow):
    given = next(s for s in _steps(workflow) if s.get("id") == "app")["with"]
    asked = {k: v for k, v in given.items() if k.startswith("permission-")}
    assert asked == {"permission-contents": "write", "permission-pull-requests": "write",
                     "permission-workflows": "write", "permission-actions": "read"}


@then("without the app it falls back to PUBRULES_BUMP_TOKEN with a warning")
def fallback(workflow):
    token = next(s for s in _steps(workflow) if s.get("id") == "token")
    assert token["env"]["BUMP_TOKEN"] == "${{ secrets.PUBRULES_BUMP_TOKEN }}"
    assert "::warning::No app-id or NIGHTLY_APP_ID" in token["run"]
    assert token["run"].index("APP_TOKEN") < token["run"].index("BUMP_TOKEN")
    assert "GH_TOKEN" not in workflow["data"]["jobs"]["update"].get("env", {})


@then(parsers.parse('it can be called with the input "{name}" and the secrets "{secrets}"'))
def called(workflow, name, secrets):
    call = workflow["data"][True]["workflow_call"]
    assert call["inputs"][name]["required"] is True
    assert set(call["secrets"]) == set(secrets.split(", "))
    assert "NIGHTLY_APP" not in workflow["data"]["jobs"]["update"]["env"]["REPO"]


@then("run by hand it takes the same repos input")
def by_hand_repos(workflow):
    dispatch = workflow["data"][True]["workflow_dispatch"]["inputs"]
    assert dispatch["repos"]["required"] is True
    report = next(s for s in workflow["data"]["jobs"]["report"]["steps"] if s.get("id") == "report")
    assert "governed.json" not in report["run"]


@then("a repository it can't read for the report doesn't stop the others")
def private_report(workflow):
    report = next(s for s in workflow["data"]["jobs"]["report"]["steps"] if s.get("id") == "report")
    assert "can't be read for the report" in report["run"]
    assert 'if [ -n "$(ls repos)" ]' in report["run"]


@then("only what the repos input governs gets a pull request")
def only_governed(workflow):
    report = next(s for s in workflow["data"]["jobs"]["report"]["steps"] if s.get("id") == "report")
    assert "select(.govern)" in report["run"]
    assert report["env"]["REPOS"] == "${{ inputs.repos }}"
    assert workflow["data"]["jobs"]["update"]["if"] == "needs.report.outputs.repos != '[]'"


@then("it takes pubfleet's script and wheel from the same latest release, whichever repository calls it")
def same_release(workflow):
    assert workflow["data"]["env"]["PUBFLEET"] == "${{ inputs.pubfleet || github.repository }}"
    for job, tag in (("report", "${{ steps.wheel.outputs.tag }}"), ("update", "${{ needs.report.outputs.tag }}")):
        steps = workflow["data"]["jobs"][job]["steps"]
        checkout = next(s for s in steps if s.get("with", {}).get("path") == "pubfleet")
        assert checkout["with"]["repository"] == "${{ env.PUBFLEET }}"
        assert checkout["with"]["ref"] == tag
        assert any("pubfleet/.github/nightly/install.sh" in s.get("run", "") for s in steps)
    assert '$GITHUB_REPOSITORY' not in "".join(s.get("run", "") for s in _steps(workflow))


@then("the pubrules it installs is the one that release is tested with, unless the pubrules input names one")
def pubrules_input(workflow):
    on = workflow["data"][True]
    for trigger in ("workflow_call", "workflow_dispatch"):
        assert on[trigger]["inputs"]["pubrules"]["default"] == ""
    assert workflow["data"]["env"]["PUBRULES_TAG"] == "${{ inputs.pubrules }}"
    assert "releases/download" not in "".join(
        s.get("run", "") for job in workflow["data"]["jobs"].values() for s in job["steps"]
        if "pubrules-" in s.get("run", ""))


# Which pubrel the nightly takes, against pubtest's fake "crates" service.

@when(parsers.parse('I ask which pubrel to use for the release "{tag}"'))
def ask_pubrel(pubtest_ctx, monkeypatch, tag):
    monkeypatch.setenv("CRATES_API", os.environ["CRATES_URL"])
    run_command(pubtest_ctx, f"{GITHUB / 'nightly' / 'pubrel-version.sh'} {tag}", None)


@then("it chooses pubrel with pubrel-version.sh, and installs that version")
def chooses(workflow):
    steps = _steps(workflow)
    latest = next(s for s in steps if s.get("id") == "latest")
    assert 'pubrel=$(pubfleet/.github/nightly/pubrel-version.sh "$(latest Sustenaut/pubrel)")' in latest["run"]
    install = next(s for s in steps if "cargo install --locked pubrel" in s.get("run", ""))
    assert install["env"]["PUBREL"] == "${{ steps.latest.outputs.pubrel }}"


@when("I read the nightly's update script", target_fixture="script")
def update_script():
    return SCRIPT.read_text()


@then("it runs not-backwards.sh before pubrules nightly")
def guard_first(script):
    assert script.index("not-backwards.sh") < script.index("pubrules nightly")
