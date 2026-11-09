"""Steps for `pubfleet freshness`: the rows, with pubkit's conform check stood in
for where a scenario needs a Rust repository's verdict."""

from __future__ import annotations

from pytest_bdd import given, parsers, scenarios, then, when

from pubfleet import freshness

scenarios("freshness.feature")


@given(parsers.re(r'a Rust checkout whose conform check finds (?:nothing|"(?P<first>[^"]+)" and '
                  r'"(?P<second>[^"]+)", with the open exception "(?P<exception>[^"]+)")$'),
       target_fixture="checkout")
def rust_checkout(repo, monkeypatch, first, second, exception):
    (repo / "pubkit.json").write_text('{"kind": "rust", "bin": "thing"}\n')
    problems = [p for p in (first, second) if p]
    lines = [f"open exception: {exception}"] if exception else []
    monkeypatch.setattr(freshness, "conform", lambda root, config: (lines, problems))
    return repo


@when("its freshness row is read", target_fixture="row")
def read_row(checkout):
    return freshness.row(checkout)


@then(parsers.parse('it conforms "{verdict}"'))
def conforms(row, verdict):
    assert row["conforms"] == verdict


@then(parsers.parse('its exceptions are "{exceptions}"'))
def exceptions_are(row, exceptions):
    assert row["exceptions"] == exceptions.split(", ")


@given("a job summary file")
def job_summary(tmp_path, env):
    env["GITHUB_STEP_SUMMARY"] = str(tmp_path / "summary.md")


@then(parsers.parse('the job summary has the table, with "{line}"'))
def summary_has(env, line):
    from pathlib import Path  # noqa: PLC0415
    text = Path(env["GITHUB_STEP_SUMMARY"]).read_text()
    assert "| Repository | Pins pubkit |" in text and line in text
