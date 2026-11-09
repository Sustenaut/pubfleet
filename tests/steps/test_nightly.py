"""Steps for the nightly's loop across repositories: nightly.yml, the script
it runs in each checkout (`pubkit nightly` makes the commits there), and
install.sh and pubrel-version.sh, which choose what it installs."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import yaml
import pytest
from pytest_bdd import given, parsers, scenarios, then, when


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


@then("without the app it falls back to PUBKIT_BUMP_TOKEN with a warning")
def fallback(workflow):
    token = next(s for s in _steps(workflow) if s.get("id") == "token")
    assert token["env"]["BUMP_TOKEN"] == "${{ secrets.PUBKIT_BUMP_TOKEN }}"
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


@then("the pubkit it installs is the one that release is tested with, unless the pubkit input names one")
def pubkit_input(workflow):
    on = workflow["data"][True]
    for trigger in ("workflow_call", "workflow_dispatch"):
        assert on[trigger]["inputs"]["pubkit"]["default"] == ""
    assert workflow["data"]["env"]["PUBKIT_TAG"] == "${{ inputs.pubkit }}"
    assert "releases/download" not in "".join(
        s.get("run", "") for job in workflow["data"]["jobs"].values() for s in job["steps"]
        if "pubkit-" in s.get("run", ""))


# Which pubrel the nightly takes, against a crates.io answered here.

@pytest.fixture
def crates():
    """What the fake crates.io has: version -> yanked; None when it doesn't answer."""
    return {"versions": {}}


@given(parsers.re(r'crates\.io has pubrel "(?P<versions>[^"]+)"(?:, with "(?P<yanked>[^"]+)" yanked)?$'))
def crates_has(crates, versions, yanked):
    crates["versions"] = {v: v == yanked for v in versions.split(", ")}


@given("crates.io doesn't answer")
def crates_down(crates):
    crates["versions"] = None


@when(parsers.parse('I ask which pubrel to use for the release "{tag}"'), target_fixture="asked")
def ask_pubrel(crates, tag):
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    held = crates["versions"]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            assert "pubfleet-nightly" in self.headers["User-Agent"]
            if held is None:
                self.send_response(503)
                self.end_headers()
                return
            path = self.path.removeprefix("/crates/pubrel")
            if path == "":
                stable = [v for v, yanked in held.items() if not yanked]
                body = {"crate": {"max_stable_version": max(stable, key=lambda v: tuple(map(int, v.split("."))))}}
            elif path[1:] in held:
                body = {"version": {"num": path[1:], "yanked": held[path[1:]]}}
            else:
                self.send_response(404)
                self.end_headers()
                return
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        return subprocess.run([str(GITHUB / "nightly" / "pubrel-version.sh"), tag], capture_output=True,
                              text=True, check=False, timeout=30,
                              env={**os.environ, "CRATES_API": f"http://127.0.0.1:{server.server_port}"})
    finally:
        server.shutdown()


@then(parsers.re(r'it says "(?P<version>[^"]+)", (?:with no warning|warning "(?P<warning>[^"]+)")$'))
def says(asked, version, warning):
    assert asked.returncode == 0, asked.stderr
    assert asked.stdout.strip() == version
    if warning:
        assert warning in asked.stderr and "::warning::" in asked.stderr
    else:
        assert asked.stderr == ""


@then("it chooses pubrel with pubrel-version.sh, and installs that version")
def chooses(workflow):
    steps = _steps(workflow)
    latest = next(s for s in steps if s.get("id") == "latest")
    assert 'pubrel=$(pubfleet/.github/nightly/pubrel-version.sh "$(latest Sustenaut/pubrel)")' in latest["run"]
    install = next(s for s in steps if "cargo install --locked pubrel" in s.get("run", ""))
    assert install["env"]["PUBREL"] == "${{ steps.latest.outputs.pubrel }}"


# What install.sh installs, with python, pubfleet and pubkit stood in for.

FAKE = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$CALLS"
"""


@when(parsers.re(r'the nightly installs pubfleet "(?P<tag>[^"]+)"(?: with the pubkit input "(?P<pubkit>[^"]+)")?$'),
      target_fixture="installed")
def install(tmp_path, tag, pubkit):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("python", "pubfleet", "pubkit"):
        (bin_dir / name).write_text(FAKE)
        (bin_dir / name).chmod(0o755)
    calls = tmp_path / "calls"
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "CALLS": str(calls)}
    env.pop("PUBKIT_TAG", None)
    if pubkit:
        env["PUBKIT_TAG"] = pubkit
    done = subprocess.run([str(GITHUB / "nightly" / "install.sh"), tag], capture_output=True, text=True,
                          env=env, check=False, timeout=30)
    lines = calls.read_text().splitlines() if calls.is_file() else []
    return {"done": done, "pip": [line for line in lines if line.startswith("-m pip install")]}


@then(parsers.parse('it installs the lock "{lock}" with --require-hashes, wheels only'))
def installs_lock(installed, lock):
    assert installed["done"].returncode == 0, installed["done"].stderr
    first = installed["pip"][0]
    assert "--require-hashes" in first and "--only-binary :all:" in first
    assert first.endswith(f"-r {GITHUB.parent / lock}")


@then(parsers.parse('it installs pubfleet\'s wheel "{wheel}" without dependencies'))
def installs_pubfleet(installed, wheel):
    assert installed["pip"][1].endswith(
        f"--no-deps https://github.com/Sustenaut/pubfleet/releases/download/{wheel}")


@then("it installs no other pubkit")
def no_other_pubkit(installed):
    assert len(installed["pip"]) == 2
    assert "::warning::" not in installed["done"].stdout


@then(parsers.parse('it installs pubkit\'s wheel "{wheel}" after the lock'))
def installs_pubkit(installed, wheel):
    assert installed["done"].returncode == 0, installed["done"].stderr
    assert len(installed["pip"]) == 3
    assert installed["pip"][2].endswith(
        f"--no-deps https://github.com/Sustenaut/pubkit/releases/download/{wheel}")


@then(parsers.parse('the install warns "{text}"'))
def install_warns(installed, text):
    assert "::warning::" in installed["done"].stdout and text in installed["done"].stdout


@then(parsers.parse('the install fails, saying "{text}"'))
def install_fails(installed, text):
    assert installed["done"].returncode != 0
    assert text in installed["done"].stderr
    assert len(installed["pip"]) == 2
