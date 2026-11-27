"""Steps for `pubfleet cycles`: repositories made of the files a scenario gives
them, served as recorded GitHub responses, and the command replaying them."""

from __future__ import annotations

import base64
import json

import pytest
from pubtest.steps.programs import run_command
from pubtest.steps.result import Current
from pytest_bdd import given, parsers, scenarios, when

from pubfleet.cycles import FILES

scenarios("cycles.feature")

API = "https://api.github.com/repos"


@pytest.fixture
def listed():
    """Each repository the scenario names: its files, or None when it can't be read."""
    return {}


@given(parsers.parse('the repository "{repo}" has "{path}":'))
def has_file(listed, repo, path, docstring):
    listed.setdefault(repo, {})[path] = docstring + "\n"


@given(parsers.parse('the repository "{repo}" can\'t be read'))
def unreadable(listed, repo):
    listed[repo] = None


@when("I check the listed repositories for cycles", target_fixture="result")
def check(listed, repo, pubtest_ctx):
    responses = {}
    for name, files in listed.items():
        for path in FILES:
            url = f"{API}/{name}/contents/{path}"
            if files is None:
                responses[url] = {"status": 403, "json": {"message": "Not Found for this token"}}
            elif path in files:
                content = base64.b64encode(files[path].encode("utf-8")).decode("ascii")
                responses[url] = {"status": 200, "json": {"type": "file", "content": content}}
            else:
                responses[url] = {"status": 404, "json": {"message": "Not Found"}}
    (repo / "repos.json").write_text(json.dumps({"repositories": [
        {"repo": name, "protect": False, "govern": False} for name in listed]}), encoding="utf-8")
    (repo / "recorded.json").write_text(json.dumps({"recorded": "2026-11-27T00:00:00Z",
                                                    "responses": responses}), encoding="utf-8")
    run_command(pubtest_ctx, "pubfleet cycles --repos repos.json --replay recorded.json", None)
    return Current(pubtest_ctx)
