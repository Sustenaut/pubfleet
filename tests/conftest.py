"""pubfleet's suite, on pubtest's steps (its GRAMMAR.md): the scratch
directory, files, the environment, stand-ins and fake services, and `When I
run "pubfleet ..."` with `Given the program under test is "pubfleet"`, which
runs the pubfleet installed beside the Python running this suite (`make
venv`'s), unless PUBFLEET_BIN_DIR names another.

What more than one steps module uses lives here: pytest-bdd registers a step
only in the module that defines it, or in a conftest.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from pubtest.steps.standins import standins
from pytest_bdd import parsers, then

os.environ.setdefault("PUBFLEET_BIN_DIR", str(Path(sys.executable).parent))


@pytest.fixture(autouse=True)
def offline_pubrel(tmp_path, monkeypatch):
    """No scenario reads pubrel's tags from GitHub: its repository is one
    that is not there (pubrules' refs.py, which the freshness rows read
    through)."""
    monkeypatch.setenv("PUBRULES_PUBREL_REMOTE", str(tmp_path / "no-pubrel"))
    monkeypatch.delenv("PUBRULES_RELEASE_COMMIT", raising=False)


@pytest.fixture
def repo(pubtest_ctx):
    """The scenario's scratch directory (pubtest's `Given a scratch directory`)."""
    assert pubtest_ctx.directory is not None, "the scenario needs `Given a scratch directory` first"
    return pubtest_ctx.directory


def fake_program(pubtest_ctx, tmp_path, monkeypatch, name, script):
    """A fake program among pubtest's stand-ins, written by the suite since it
    answers from a state of its own. It logs each run to the stand-ins' log
    (FAKE_LOG), as pubtest's stand-ins do, so their steps read its runs."""
    found = standins(pubtest_ctx, tmp_path)
    (found.bin / name).write_text(script)
    (found.bin / name).chmod(0o755)
    monkeypatch.setenv("FAKE_LOG", str(found.log))
    return found


@then("stderr is empty")
def stderr_empty(result):
    assert result.stderr == "", result.stderr


@then(parsers.parse('the refusal is a "{kind}"'))
def refusal_is(pubtest_ctx, kind):
    """The refusal is of the class named, or of one made from it, by its name or
    its module's dotted name."""
    assert pubtest_ctx.refused is not None, f"it was not refused: the result is {pubtest_ctx.result!r}"
    kinds = type(pubtest_ctx.refused.error).__mro__
    assert any(kind in (k.__name__, f"{k.__module__}.{k.__qualname__}") for k in kinds), repr(pubtest_ctx.refused.error)


@then(parsers.parse('"{name}" was run, in turn, with arguments matching:'))
def runs_in_turn(pubtest_ctx, name, docstring):
    """Every run of the stand-in, in order: one pattern a line (`*` for anything)."""
    from pubtest.core import matches  # noqa: PLC0415
    runs = [" ".join(args) for args in pubtest_ctx.standins.runs(name)]
    want = [line.strip() for line in docstring.splitlines() if line.strip()]
    assert len(runs) == len(want) and all(matches(p, r) for p, r in zip(want, runs)), runs
