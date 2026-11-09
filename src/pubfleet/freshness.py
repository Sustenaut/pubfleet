"""`pubfleet freshness`: keep every pub* repository on the latest pubkit, so
none sits on an old standard unnoticed.

`pubfleet freshness DIR...` reports, for each checked-out repository, the
pubkit its lock pins, whether it is the installed one, whether it conforms to
that pubkit's standard, and its open exceptions: one Markdown table, also
appended to the GitHub step summary when there is one. It reads; it changes
nothing. `pubfleet freshness --repos FILE [DIR]` reports instead the
repositories a repos file marks to govern, each checked out at DIR/<name>.
The installed pubkit is the latest, in the nightly that runs this; moving a
repository to it is `pubkit bump`'s, and the nightly's.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from pubkit import __version__
from pubkit.conform import run as conform
from pubkit.freshness import pinned
from pubkit.repos import read


def row(repo: Path) -> dict:
    config_path = repo / "pubkit.json"
    out = {"repo": repo.name, "pinned": pinned(repo) or "-", "latest": __version__}
    if not config_path.is_file():
        return {**out, "conforms": "no pubkit.json", "exceptions": []}
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("kind") != "rust":
        return {**out, "conforms": "not Rust", "exceptions": []}
    try:
        lines, problems = conform(repo, config)
    except Exception as e:  # noqa: BLE001 - report every repository, whatever fails
        return {**out, "conforms": f"could not check: {e}", "exceptions": []}
    exceptions = [line.removeprefix("open exception: ") for line in lines
                  if line.startswith("open exception: ")]
    # The workflow pin is checked against the pinned pubkit by `sync --check`
    # in the repository itself; here every rule is judged by the latest.
    problems = [p for p in problems if not p.startswith(".github/workflows/")]
    verdict = "yes" if not problems else f"no: {len(problems)} problem(s): " + "; ".join(problems)
    return {**out, "conforms": verdict, "exceptions": exceptions}


def table(rows: list[dict]) -> str:
    lines = [f"Every pub* repository against pubkit {__version__}.", "",
             "| Repository | Pins pubkit | Current | Conforms to the latest standard | Open exceptions |",
             "|---|---|---|---|---|"]
    for r in rows:
        current = "yes" if r["pinned"] == r["latest"] else "**no**"
        exceptions = "<br>".join(r["exceptions"]) or "-"
        lines.append(f"| {r['repo']} | {r['pinned']} | {current} | {r['conforms']} | {exceptions} |")
    return "\n".join(lines) + "\n"


def governed_rows(repos_file: Path, where: Path) -> list[dict]:
    """A row for each repository the repos file governs, checked out or not."""
    rows = []
    for entry in read(repos_file, "freshness"):
        if not entry["govern"]:
            continue
        name = entry["repo"].split("/", 1)[1]
        checkout = where / name
        rows.append(row(checkout.resolve()) if checkout.is_dir() else
                    {"repo": name, "pinned": "-", "latest": __version__,
                     "conforms": "not checked out", "exceptions": []})
    return rows


def freshness(dirs: list[Path], as_json: bool, repos_file: Path | None = None) -> int:
    if repos_file:
        if len(dirs) > 1:
            sys.exit("pubfleet freshness: --repos takes one directory, where the checkouts are")
        rows = governed_rows(repos_file, dirs[0] if dirs else Path("."))
    elif dirs:
        rows = [row(d.resolve()) for d in dirs]
    else:
        sys.exit("pubfleet freshness: name the checkouts, or pass --repos FILE")
    text = json.dumps(rows, indent=2) + "\n" if as_json else table(rows)
    print(text, end="")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and not as_json:
        with open(summary, "a", encoding="utf-8") as out:
            out.write(text)
    return 0
