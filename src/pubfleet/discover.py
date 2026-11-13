"""`pubfleet state --discover [FILE] [--body PATH]`: add the owner's repositories
a state file does not list yet.

It lists the owner's repositories, leaving out archived ones and forks, and gives
each one the file lacks an entry: on the board, protected when its own
pubkit.json has a protect block (`state --check` refuses protect without one), and
not governed, so its nightly waits until someone turns it on. No project and no
deploy. It rewrites the file as state files are kept (two-space JSON, repositories
in name order), writes a pull request's description to --body when given (what it
added, why protect is on or off, and the repositories the file lists that are
archived or gone, which it never removes), and prints how many it added.

`listing` and `entry` are the pieces a workflow that makes a repository reuses to
add the one it made.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pubkit.protect import Api, ApiError, gh, remote_config

from .state import shape

PAGE = 100


def listing(owner: str, api: Api = gh) -> list[dict]:
    """Every repository of the owner, archived ones and forks included, each
    as GitHub's repository object."""
    out: list[dict] = []
    page = 1
    while True:
        batch = api("GET", f"orgs/{owner}/repos?type=all&per_page={PAGE}&page={page}", None) or []
        out += batch
        if len(batch) < PAGE:
            return out
        page += 1


def entry(owner: str, name: str, api: Api = gh) -> dict:
    """A new repository's entry: on the board, protected only where its own
    pubkit.json says how, not governed."""
    try:
        config = remote_config(api, f"{owner}/{name}")
    except ValueError:
        config = None
    return {"board": True, "protect": isinstance(config, dict) and "protect" in config, "govern": False}


def discover(state: dict, listed: list[dict], entry_for) -> tuple[dict, list[str], list[str]]:
    """`state` with an entry for each live repository it lacks, the names added,
    and the names it lists that are archived or no longer there."""
    live = {r["name"] for r in listed if not r.get("archived") and not r.get("fork")}
    known = {r["name"] for r in listed}
    archived = {r["name"] for r in listed if r.get("archived")}
    repos = dict(state["repos"])
    added = sorted(name for name in live if name not in repos)
    for name in added:
        repos[name] = entry_for(name)
    gone = sorted(n for n in state["repos"] if n in archived or n not in known)
    return {**state, "repos": dict(sorted(repos.items()))}, added, gone


def body(state: dict, added: list[str], gone: list[str], listed: list[dict]) -> str:
    """The description of the pull request that adds them."""
    visibility = {r["name"]: r.get("visibility", "unknown") for r in listed}
    lines = ["Repositories `state.json` did not list yet, found by `pubfleet state --discover`. "
             "Each is on the board and not governed; protect is on where its own "
             "`pubkit.json` has a protect block.", "",
             "| Repository | Visibility | protect |", "|---|---|---|"]
    for name in added:
        why = ("on: its pubkit.json has a protect block" if state["repos"][name]["protect"]
               else "off: no protect block in its pubkit.json")
        lines.append(f"| {name} | {visibility.get(name, 'unknown')} | {why} |")
    lines += ["", "Merging puts them on the board and, where protect is on, brings their "
              "rulesets in line with pubkit's (`state / apply`). Set `govern`, `project` or "
              "`deploy` here first if one should have them."]
    if gone:
        lines += ["", "Listed, but archived or no longer there (never removed by this): "
                  + ", ".join(f"`{n}`" for n in gone) + "."]
    return "\n".join(lines) + "\n"


def run(path: Path, body_path: Path | None = None, api: Api = gh) -> int:
    """Add the missing repositories to the state file at `path`."""
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"pubfleet: {path} can't be read ({e})", file=sys.stderr)
        return 2
    if problems := shape(state):
        print(f"pubfleet: {path}: {'; '.join(problems)}", file=sys.stderr)
        return 2
    owner = state["owner"]
    try:
        listed = listing(owner, api)
    except ApiError as e:
        print(f"pubfleet: GitHub would not list {owner}'s repositories ({e})", file=sys.stderr)
        return 2
    new, added, gone = discover(state, listed, lambda name: entry(owner, name, api))
    if added:
        path.write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if body_path is not None and added:
        body_path.write_text(body(new, added, gone, listed), encoding="utf-8")
    print(len(added))
    return 0

