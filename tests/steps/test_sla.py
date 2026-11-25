"""Steps for pubfleet.sla: the SLA block's shape, what pubfleet derives from it, its
budget, the variables it gives and the state check of it. `gh` is the fake of
test_variables.py, which answers pubrules.json files and variables from a JSON file."""

from __future__ import annotations

import json

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from pubfleet import sla, state as state_module

# The fake gh, for every scenario here.
from test_variables import _config, _edit, github  # noqa: F401

scenarios("sla.feature")

# The block the scenarios start from, which each changes a part of.
SOUND = {
    "version": 1,
    "tiers": {
        "tight": {"deadline_seconds": 30, "heartbeat_seconds": 60, "misses": 2, "uptime_minutes": 10},
        "idle": {"deadline_seconds": 28800, "heartbeat_seconds": 3600, "misses": 3},
        "on-demand": {"deadline_seconds": 120},
    },
    "services": {
        "one": {"senders": {"app": "tight", "job": "idle"}, "uptime": "tight",
                "address": "https://one.example.eu/healthz"},
        "two": {"senders": {"plan": "on-demand"}},
    },
}
ROLES = {"board": True, "protect": False, "govern": False}


@pytest.fixture
def block():
    return json.loads(json.dumps(SOUND))


@given("a sound SLA block")
def sound(block):
    return block


@given(parsers.parse("the SLA block '{text}'"), target_fixture="block")
def given_block(text):
    return json.loads(text)


@given(parsers.parse("its {part} '{name}' is '{text}'"))
def with_part(block, part, name, text):
    block[{"tier": "tiers", "service": "services"}[part]][name] = json.loads(text)


@given(parsers.parse("its {key} is '{text}'"))
def with_key(block, key, text):
    block[key] = json.loads(text)


@given(parsers.parse("its service '{name}' has no address"))
def no_address(block, name):
    block["services"][name].pop("address")


def state_of(block, repos=None, variables=None):
    repos = repos if repos is not None else ["one", "two", "observability", *block.get("services", {})]
    out = {"owner": "example-org", "repos": {name: dict(ROLES) for name in repos}, "SLA": block}
    for name, values in (variables or {}).items():
        out["repos"][name]["variables"] = values
    return out


@given("a state file with no SLA block")
def no_sla(repo):
    (repo / "state.json").write_text(json.dumps({"owner": "example-org", "repos": {}}))


@given(parsers.parse("its {count:d} services '{prefix}' each have their address checked by '{tier}'"))
def many_services(block, count, prefix, tier):
    for n in range(count):
        block["services"][f"{prefix}{n}"] = {"senders": {}, "uptime": tier, "address": f"https://{prefix}{n}.example.eu"}


@given("the state file holds it", target_fixture="state")
def state_file(repo, block):
    state = state_of(block)
    (repo / "state.json").write_text(json.dumps(state))
    return state


@given(parsers.parse("the state file holds it, and gives \"{name}\" the variables '{text}'"), target_fixture="state")
def state_file_with(repo, block, name, text):
    state = state_of(block, variables={name: json.loads(text)})
    (repo / "state.json").write_text(json.dumps(state))
    return state


@given(parsers.parse('the state file holds it, without the repository "{name}"'), target_fixture="state")
def state_file_without(repo, block, name):
    state = state_of(block, repos=[r for r in ("one", "two", "observability", *block["services"]) if r != name])
    (repo / "state.json").write_text(json.dumps(state))
    return state


@given(parsers.parse('"{slug}" deploys to the host "{host}"'))
def deploys_to(github, slug, host):  # noqa: F811 - the fixture of test_variables.py
    _config(github, slug, {"kind": "service", "deploy": {"host": host}})


@given(parsers.parse('"{slug}" declares the variables {names}'))
def declares_names(github, slug, names):  # noqa: F811
    _config(github, slug, {"kind": "service", "variables": {"names": json.loads(names), "deploy": "deploy.yml"}})


# test_variables.py's steps of the fake gh, which pytest-bdd keeps to the module that defines them.
@given(parsers.re(r'"(?P<slug>[^"]+)" has the pubrules.json "(?P<text>.+)"$'))
def has_config(github, slug, text):  # noqa: F811
    _config(github, slug, json.loads(text))


@given(parsers.re(r'GitHub holds "(?P<name>[^"]+)" in "(?P<slug>[^"]+)" as "(?P<value>.*)"$'))
def holds(github, name, slug, value):  # noqa: F811
    _edit(github, lambda state: state["variables"].setdefault(slug, {}).__setitem__(name, value))


@then(parsers.re(r'GitHub holds "(?P<name>[^"]+)" in "(?P<slug>[^"]+)" as "(?P<value>.*)" now$'))
def holds_now(github, name, slug, value):  # noqa: F811
    assert json.loads(github.read_text())["variables"][slug][name] == value


@when("pubfleet checks the SLA block")
def checks(pubtest_ctx, block):
    pubtest_ctx.attempt(lambda: sla.block_problems(block))


@when("pubfleet derives from it, offline")
def derives_offline(pubtest_ctx, block):
    pubtest_ctx.attempt(lambda: sla.derive(state_of(block), api=None))


@when("pubfleet reads its numbers")
def reads_numbers(pubtest_ctx, block):
    pubtest_ctx.attempt(lambda: sla.numbers(sla.read(block)))


@when("pubfleet reads it")
def reads(pubtest_ctx, block):
    pubtest_ctx.attempt(lambda: sla.read(block))


@when(parsers.parse("pubfleet counts its budget, with {replicas}"))
def counts_budget(pubtest_ctx, block, replicas):
    given = {} if replicas == "one replica each" else json.loads(replicas)
    pubtest_ctx.attempt(lambda: sla.budget(sla.numbers(sla.read(block), given)))


@when("pubfleet checks the state's shape")
def checks_shape(pubtest_ctx, state):
    pubtest_ctx.attempt(lambda: state_module.shape(state))


@then(parsers.parse('one problem is "{text}"'))
def one_problem(pubtest_ctx, text):
    assert pubtest_ctx.refused is None, pubtest_ctx.refused
    assert any(text in p for p in pubtest_ctx.result), pubtest_ctx.result


@then(parsers.parse('no problem names "{text}"'))
def no_problem(pubtest_ctx, text):
    assert pubtest_ctx.refused is None, pubtest_ctx.refused
    assert not any(text in p for p in pubtest_ctx.result), pubtest_ctx.result


@then(parsers.parse('the derived {key} are:'))
def derived_are(pubtest_ctx, key, docstring):
    assert pubtest_ctx.refused is None, pubtest_ctx.refused
    assert pubtest_ctx.result[key] == json.loads(docstring), pubtest_ctx.result[key]


@then(parsers.parse('the sender "{who}" is:'))
def sender_is(pubtest_ctx, who, docstring):
    assert pubtest_ctx.refused is None, pubtest_ctx.refused
    service, sender = who.split("/")
    (row,) = [s for s in pubtest_ctx.result["senders"] if (s["service"], s["sender"]) == (service, sender)]
    assert row == json.loads(docstring), row


@then(parsers.parse('the uptime check of "{service}" is:'))
def uptime_is(pubtest_ctx, service, docstring):
    assert pubtest_ctx.refused is None, pubtest_ctx.refused
    (row,) = [u for u in pubtest_ctx.result["uptime"] if u["service"] == service]
    assert row == json.loads(docstring), row
