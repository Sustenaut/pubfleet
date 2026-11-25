"""`pubfleet variables --check | --apply`: keep repositories' GitHub variables to a state file.

A repository's pubrules.json names the variables it reads, never their values, and
may name the workflow that takes them in, to run once one changes:

    "variables": {"names": ["SOME_SETTING", "SOME_MAP"], "deploy": "deploy.yml"}

Their values are in the owner's state file, under each repository, so a change to one
is a pull request there, with its history:

    "some-repo": {"board": true, "protect": true, "govern": false,
                  "variables": {"SOME_SETTING": "a string", "SOME_MAP": {"a": "b"}}}

A string goes to GitHub as it is. Anything else is JSON, kept structured in the state
so a diff shows the entry that changed, and sent compact, in the file's order. A JSON
value matches what GitHub holds when that parses to the same thing, however spaced.

`--check` changes nothing: it prints how each repository's variables differ from the
state, and fails when one does. `--apply` sets those that differ, and then runs the
repository's `deploy` workflow on its default branch, once, if it set any. Neither
touches a variable the state leaves out, nor removes one: dropping a variable is a
deliberate step by hand. Each acts on every repository in the state with variables,
or those named (NAME or OWNER/NAME), or those a repos file lists. It reads through
`gh`, with a token that can read the repositories' pubrules.json and variables, and,
for --apply, write their variables and run their workflows.

A state with an SLA block (pubfleet.sla) also gives repositories the variables derived
from it: each service's CALL_LOG_DEADLINE_SECONDS, while the call log's heartbeats are
files its CALL_LOG_HEARTBEAT_SECONDS, and observability's OBSERVABILITY_SENDERS. The
state may not give one of those itself, as the block is where it is set. A repository
whose pubrules.json doesn't declare a derived one yet is not given it, and says so: a
service declares them when its deploy passes them to its pods.
"""

from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path
from typing import Any

from pubrules.protect import Api, ApiError, gh, gh_set, remote_config
from pubrules.repos import read
from pubrules.variables import BLOCK, block_problems, name_problem

PAGE = 30


def value_problems(values: Any) -> list[str]:
    """What is wrong with one repository's variables in a state file: one phrase each."""
    if not isinstance(values, dict):
        return ["its variables must be an object, from each name to its value"]
    out = [p for n in values if (p := name_problem(n))]
    for name, value in values.items():
        if value is None or value == "":
            out.append(f"{name} has no value; GitHub keeps no empty variable")
    return out


def serialise(value: Any) -> str:
    """What GitHub holds for a value from the state."""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def same(want: Any, have: str) -> bool:
    if isinstance(want, str):
        return want == have
    try:
        return canonical(json.loads(have)) == canonical(want)
    except ValueError:
        return False


def pretty(value: Any) -> list[str]:
    return json.dumps(value, ensure_ascii=False, indent=2).splitlines()


def difference(name: str, want: Any, have: str | None) -> list[str]:
    """How one variable differs, as lines: a diff of the entries for JSON."""
    if have is None:
        return [f"  {name} is not set; the state has:", *(f"    + {line}" for line in
                                                           pretty(want) if not isinstance(want, str)),
                *([f"    + {want}"] if isinstance(want, str) else [])]
    if isinstance(want, str):
        return [f"  {name}:", f"    - {have}", f"    + {want}"]
    try:
        before = pretty(json.loads(have))
    except ValueError:
        before = [have]
    lines = difflib.unified_diff(before, pretty(want), "on GitHub", "in the state", lineterm="", n=0)
    return [f"  {name}:", *(f"    {line}" for line in lines)]


def live(api: Api, slug: str) -> dict[str, str]:
    """Every variable `slug` holds, by name."""
    out: dict[str, str] = {}
    page = 1
    while True:
        found = api("GET", f"repos/{slug}/actions/variables?per_page={PAGE}&page={page}", None) or {}
        batch = found.get("variables", [])
        out |= {v["name"]: v["value"] for v in batch}
        if len(batch) < PAGE:
            return out
        page += 1


def declared(api: Api, slug: str) -> dict:
    """`slug`'s variables block, from the pubrules.json on its default branch."""
    config = remote_config(api, slug)
    if not isinstance(config, dict) or BLOCK not in config:
        raise ValueError(f"its pubrules.json declares no variables; add "
                         f'"{BLOCK}": {{"names": [...]}} to it')
    if bad := block_problems(config[BLOCK]):
        raise ValueError(f"its pubrules.json's {BLOCK} block: {'; '.join(bad)}")
    return config[BLOCK]


def undeclared(block: dict, values: dict) -> list[str]:
    return [n for n in values if n not in block["names"]]


def derived(state: dict) -> dict[str, dict[str, Any]]:
    """The variables the state's SLA block gives each repository, by name."""
    from . import sla  # noqa: PLC0415 - sla reads pubrules' block, which state checks first

    if sla.BLOCK not in state:
        return {}
    block = sla.read(state[sla.BLOCK])
    return sla.variables(block, sla.numbers(block))


def wanted(state: dict) -> dict[str, tuple[dict[str, Any], set[str]]]:
    """Each repository's variables, the state's and the SLA block's, with the names derived."""
    out: dict[str, tuple[dict[str, Any], set[str]]] = {}
    from_sla = derived(state)
    for name, roles in state["repos"].items():
        given = dict(roles.get(BLOCK) or {})
        extra = from_sla.get(name, {})
        if given or extra:
            out[name] = ({**given, **extra}, set(extra))
    return out


def chosen(state: dict, names: list[str], repos_file: Path | None) -> list[str]:
    """The repositories to act on, by name within the state's owner."""
    owner = state["owner"]
    if repos_file:
        names = [e["repo"] for e in read(repos_file, "variables")]
    has = wanted(state)
    if not names:
        return [n for n in state["repos"] if n in has]
    out = []
    for name in names:
        own, _, short = name.rpartition("/")
        if own and own.lower() != owner.lower():
            sys.exit(f"pubfleet variables: {name} is not one of {owner}'s, as the state is")
        if short not in state["repos"]:
            sys.exit(f"pubfleet variables: the state names no repository {short}")
        if short in has:
            out.append(short)
        elif not repos_file:
            sys.exit(f"pubfleet variables: the state gives {short} no variables")
    return out


def one(api: Api, slug: str, values: dict, apply: bool, setter,
        derived_names: set[str] | None = None) -> tuple[list[str], bool, bool]:
    """Lines for one repository, whether it differs, and whether something failed.
    `derived_names` are those its SLA block gives, left alone while undeclared."""
    derived_names = derived_names or set()
    notes = []
    try:
        block = declared(api, slug)
    except ValueError as e:
        if values.keys() <= derived_names:
            return [f"{slug}: the SLA block gives it {', '.join(sorted(values))}, which it doesn't "
                    f"declare yet, so they are left alone"], False, False
        return [f"{slug}: {e}"], False, True
    if waiting := sorted(n for n in undeclared(block, values) if n in derived_names):
        notes = [f"{slug}: the SLA block gives it {', '.join(waiting)}, which its pubrules.json doesn't "
                 f"declare yet, so they are left alone"]
        values = {k: v for k, v in values.items() if k not in waiting}
        if not values:
            return notes, False, False
    if names := undeclared(block, values):
        return [f"{slug}: its pubrules.json doesn't declare {', '.join(names)}, "
                f"which the state gives it"], False, True
    try:
        have = live(api, slug)
    except ApiError as e:
        return [f"{slug}: its variables can't be read ({e})"], False, True
    differs = [n for n, v in values.items() if n not in have or not same(v, have[n])]
    if not differs:
        return [*notes, f"{slug}: {len(values)} variables as the state says"], False, False
    lines = [*notes, f"{slug}: {len(differs)} of {len(values)} variables differ from the state"]
    for name in differs:
        lines += difference(name, values[name], have.get(name))
    if not apply:
        return lines, True, False
    failed = False
    for name in differs:
        if (refused := setter("variable", name, slug, serialise(values[name]))) is not None:
            lines.append(f"  FAILED   {name}: {refused}")
            failed = True
        else:
            lines.append(f"  set      {name}")
    if workflow := block.get("deploy"):
        try:
            branch = (api("GET", f"repos/{slug}", None) or {}).get("default_branch", "main")
            api("POST", f"repos/{slug}/actions/workflows/{workflow}/dispatches", {"ref": branch})
            lines.append(f"  ran      {workflow} on {branch}")
        except ApiError as e:
            lines.append(f"  FAILED   to run {workflow}: {e}")
            failed = True
    return lines, True, failed


def run(path: Path, names: list[str], apply: bool, repos_file: Path | None = None,
        api: Api = gh, setter=gh_set) -> int:
    from .state import shape  # noqa: PLC0415 - state reads this module's value_problems
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.exit(f"pubfleet variables: {path}: {e}")
    if bad := shape(state):
        sys.exit(f"pubfleet variables: {path}: {'; '.join(bad)}")
    repos = chosen(state, names, repos_file)
    if not repos:
        print(f"{path}: no repository of {state['owner']} has variables")
        return 0
    has = wanted(state)
    differs = failed = False
    for name in repos:
        values, names_derived = has[name]
        lines, d, f = one(api, f"{state['owner']}/{name}", values, apply, setter, names_derived)
        print("\n".join(lines))
        differs, failed = differs or d, failed or f
    return 1 if failed or (differs and not apply) else 0
