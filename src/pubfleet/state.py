"""`pubfleet state --check`: is a state repository's state.json sound?
`pubfleet state --repos-for ROLE`: the repos file for one of its roles.

    {"owner": "OWNER",
     "repos": {"NAME": {"project": "some-group", "board": true, "protect": true, "govern": false,
                        "deploy": true, "variables": {"SOME_SETTING": "a value"}}},
     "SLA": {"version": 1, "tiers": {...}, "services": {...}}}

One file per GitHub owner says which of its repositories are graded, protected
and governed. This checks its shape, that each repository exists under the
owner, and that each one with `protect` has a protect block in its pubrules.json,
since that block is what says how, that each one with `deploy` (optional, false
when left out: the convergence engine walks the repositories that have it) has a
deploy block there, for the same reason, and that the repository has reported every check
the block requires, since a ruleset requiring one it never reports stops anything
merging. A repository's `variables` (optional) are the values of its GitHub variables,
which `pubfleet variables` keeps them to: each a string or JSON, and each one its own
pubrules.json declares in its variables block. Its `SLA` block (optional; pubfleet.sla)
must be sound as pubrules reads it, name only repositories the file lists, take numbers
Cloud Monitoring takes, stay within its free tiers, and not be set beside a variable it
derives. The protect check is the best it can be: it looks at the default branch's newest
commit and a few recent pull requests, and says nothing when it can't read them. It is the state repository's one required
check, so it builds nothing and takes seconds. It reads GitHub through `gh`,
with a token that can read every repository the file names. The one exception is
the repository the check runs in (`GITHUB_REPOSITORY`, which Actions sets) when the
file names it: its pubrules.json is the one beside the state file, the change under
review, so a pull request that moves its own block is checked against itself.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from pubrules.api import Api, ApiError, gh, remote_config, remote_protection_entry

from . import variables

OWNER = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*")
OWN = "pubrules.json"
NAME = re.compile(r"[A-Za-z0-9_.-]+")
ROLES = ("board", "protect", "govern")
# Roles a repository may leave out, as false.
OPTIONAL = ("deploy",)
RECENT_PULLS = 5


def shape(state: Any) -> list[str]:
    """What is wrong with the file's shape, one phrase each."""
    if not isinstance(state, dict):
        return [f"it is {json.dumps(state)}, not an object"]
    from . import sla  # noqa: PLC0415 - sla imports pubrules' block, as this does variables

    out = [f"{key} is not a setting; it takes owner, repos and {sla.BLOCK}"
           for key in sorted(state.keys() - {"owner", "repos", sla.BLOCK})]
    if not OWNER.fullmatch(str(state.get("owner", ""))) or not isinstance(state.get("owner"), str):
        out.append('"owner" must be a GitHub owner')
    repos = state.get("repos")
    if not isinstance(repos, dict):
        return [*out, '"repos" must be an object, from each repository\'s name to its roles']
    for name, roles in repos.items():
        if not NAME.fullmatch(name):
            out.append(f"{name} is not a repository's name")
        if not isinstance(roles, dict):
            out.append(f"{name}: its roles must be an object, not {json.dumps(roles)}")
            continue
        for key in sorted(roles.keys() - {"project", variables.BLOCK, *ROLES, *OPTIONAL}):
            out.append(f"{name}: {key} is not a setting; it takes project, board, protect, govern, "
                       f"deploy and variables")
        if variables.BLOCK in roles:
            out += [f"{name}: {p}" for p in variables.value_problems(roles[variables.BLOCK])]
        for role in ROLES:
            if not isinstance(roles.get(role), bool):
                out.append(f"{name}: \"{role}\" must be true or false")
        for role in OPTIONAL:
            if not isinstance(roles.get(role, False), bool):
                out.append(f"{name}: \"{role}\" must be true or false")
        if not isinstance(roles.get("project", ""), str) or roles.get("project") == "":
            out.append(f"{name}: \"project\" must be a name")
    out += sla.problems(state)
    if sla.BLOCK in state and not any(p.startswith(f"its {sla.BLOCK} block") for p in out):
        set_twice = {name: sorted(set(repos[name].get(variables.BLOCK) or {}) & set(given))
                     for name, given in variables.derived(state).items()
                     if isinstance(repos.get(name), dict)}
        out += [f"{name}: its variables give {', '.join(both)}, which the {sla.BLOCK} block sets: drop them here"
                for name, both in set_twice.items() if both]
    return out


def reported(api: Api, slug: str, branch: str) -> set[str] | None:
    """Every check `slug` has reported lately on `branch` and its recent pull
    requests, or None if they can't be read."""
    try:
        pulls = api("GET", f"repos/{slug}/pulls?state=closed&per_page={RECENT_PULLS}", None) or []
        names: set[str] = set()
        for ref in [branch, *(p["head"]["sha"] for p in pulls)]:
            runs = api("GET", f"repos/{slug}/commits/{ref}/check-runs?per_page=100", None) or {}
            names |= {run["name"] for run in runs.get("check_runs", [])}
            statuses = api("GET", f"repos/{slug}/commits/{ref}/status", None) or {}
            names |= {status["context"] for status in statuses.get("statuses", [])}
    except (ApiError, KeyError, TypeError):
        return None
    return names


def on_github(api: Api, owner: str, repos: dict) -> list[str]:
    """What GitHub says is wrong: a repository missing, moved or unreadable,
    one to protect that has no sound protect block, or one given variables its
    pubrules.json doesn't declare."""
    out = []
    for name, roles in repos.items():
        slug = f"{owner}/{name}"
        try:
            found = api("GET", f"repos/{slug}", None) or {}
        except ApiError as e:
            out.append(f"{slug} does not exist" if e.status == 404 else f"{slug}: {e}")
            continue
        # GitHub answers for a renamed or transferred repository's old name.
        if found.get("full_name", slug).lower() != slug.lower():
            out.append(f"{slug} is now {found['full_name']}")
            continue
        if roles["protect"]:
            try:
                entry = remote_protection_entry(api, slug)
            except ValueError as e:
                out.append(f"{slug} has \"protect\" on, but {e}")
                continue
            seen = reported(api, slug, found.get("default_branch", "main"))
            for check in [] if seen is None else entry["checks"]:
                if check not in seen:
                    out.append(f"{slug} requires the check \"{check}\", which it hasn't reported "
                               f"lately, so nothing could merge there")
        if roles.get("deploy"):
            try:
                config = remote_config(api, slug)
            except ValueError as e:
                out.append(f"{slug} has \"deploy\" on, but {e}")
            else:
                if not isinstance(config, dict) or not isinstance(config.get("deploy"), dict):
                    out.append(f"{slug} has \"deploy\" on, but its pubrules.json has no deploy block")
        if values := roles.get(variables.BLOCK):
            try:
                block = variables.declared(api, slug)
            except ValueError as e:
                out.append(f"{slug} has variables in the state, but {e}")
                continue
            if names := variables.undeclared(block, values):
                out.append(f"{slug}: its pubrules.json doesn't declare {', '.join(names)}, "
                           f"which the state gives it")
    return out


def repos_file(state: dict, role: str) -> dict:
    """The repos file pubrules' other commands read: the repositories with `role` on, in the
    file's order. Nothing else reads a state file's roles."""
    entries = []
    for name, roles in state["repos"].items():
        if roles.get(role, False):
            entry = {"repo": f"{state['owner']}/{name}", "protect": roles["protect"],
                     "govern": roles["govern"]}
            if roles.get("project"):
                entry["project"] = roles["project"]
            entries.append(entry)
    return {"repositories": entries}


def repos_for(path: Path, role: str) -> int:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.exit(f"pubfleet state: {path}: {e}")
    if bad := shape(state):
        sys.exit(f"pubfleet state: {path}: {'; '.join(bad)}")
    print(json.dumps(repos_file(state, role), separators=(",", ":")))
    return 0


def here(api: Api, path: Path) -> Api:
    """`api`, but answering the checked-out repository's own pubrules.json from the copy
    beside `path`, when Actions names that repository and the copy is there."""
    slug = os.environ.get("GITHUB_REPOSITORY", "")
    own = path.parent / OWN
    if not slug or not own.is_file():
        return api
    wanted = f"repos/{slug}/contents/{OWN}".lower()

    def answer(method: str, url: str, body: object) -> object:
        if method == "GET" and url.lower() == wanted:
            return {"type": "file", "encoding": "base64",
                    "content": base64.b64encode(own.read_bytes()).decode("ascii")}
        return api(method, url, body)
    return answer


def check(path: Path, api: Api = gh) -> int:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.exit(f"pubfleet state: {path}: {e}")
    bad = shape(state) or on_github(here(api, path), state["owner"], state["repos"])
    for line in bad:
        print(f"{path}: {line}")
    if bad:
        return 1
    print(f"{path}: {len(state['repos'])} repositories of {state['owner']}, all sound")
    return 0
