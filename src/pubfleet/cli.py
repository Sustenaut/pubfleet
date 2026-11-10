"""pubfleet: what a control plane runs across many repositories.

    pubfleet board --out DIR --repos FILE [--rules FILE] [--replay FILE] [--record FILE]
    pubfleet board-publish --url URL --tenant TENANT [--file FILE]
    pubfleet state --check | --repos-for board|govern|deploy [FILE]
    pubfleet variables --check|--apply [--state FILE] [--repos FILE | REPO...]
    pubfleet freshness [--json] (DIR... | --repos FILE [DIR])

Each reads GitHub through `gh`, with a token the command's help names, and
judges by the pubkit installed beside it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pubkit.paths import confined

from . import __version__


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pubfleet", description=__doc__.split("\n")[0])
    parser.add_argument("--version", action="version", version=f"pubfleet {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("board", help="grade every listed repository A to E into "
                                          "board.json and a static index.html")
    p.add_argument("--out", type=Path, required=True, help="the directory to write them to")
    p.add_argument("--repos", type=Path, metavar="FILE", required=True,
                   help="the repos file: grade what it names")
    p.add_argument("--rules", type=Path, help="other rules than the ones pubfleet ships")
    p.add_argument("--replay", type=Path,
                   help="read recorded responses from this file instead of the network")
    p.add_argument("--record", type=Path,
                   help="also keep every response in this file, for --replay")
    p = commands.add_parser("board-publish", help="keep a new board.json in storage, if a fact or "
                                                  "a grade changed, from a GitHub Actions job")
    p.add_argument("--url", required=True, help="the storage service's address")
    p.add_argument("--tenant", required=True, help="the storage tenant whose board head it moves")
    p.add_argument("--file", type=Path, default=Path("site/board.json"), metavar="FILE",
                   help="the board (default: site/board.json)")
    p = commands.add_parser("state", help="check a state repository's state.json, or make a "
                                          "repos file from it")
    what = p.add_mutually_exclusive_group(required=True)
    what.add_argument("--check", action="store_true",
                      help="check its shape, that each repository exists, and each protected one's block")
    what.add_argument("--repos-for", choices=("board", "govern", "deploy"), metavar="ROLE",
                      help="print the repos file for a role, board or govern")
    p.add_argument("file", nargs="?", type=Path, default=Path("state.json"), metavar="FILE")
    p = commands.add_parser("variables", help="keep repositories' GitHub variables to the values "
                                              "a state file gives them")
    what = p.add_mutually_exclusive_group(required=True)
    what.add_argument("--check", action="store_true",
                      help="change nothing: print how each differs, and fail when one does")
    what.add_argument("--apply", action="store_true",
                      help="set those that differ, then run each changed repository's deploy workflow")
    p.add_argument("--state", type=Path, default=Path("state.json"), metavar="FILE",
                   help="the state file (default: state.json)")
    p.add_argument("--repos", dest="repos_file", type=Path, metavar="FILE",
                   help="the repos file: act on those it lists that the state gives variables")
    p.add_argument("repos", nargs="*", metavar="REPO",
                   help="NAME or OWNER/NAME; by default every repository the state gives variables")
    p = commands.add_parser("freshness",
                            help="report which pinned pubkit and standard each repository meets")
    p.add_argument("--json", action="store_true", help="JSON rows instead of a Markdown table")
    p.add_argument("--repos", type=Path, metavar="FILE",
                   help="report the repositories this repos file governs, checked out in DIR")
    p.add_argument("dirs", nargs="*", metavar="DIR", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0911 - one branch per command
    args = parser().parse_args(argv)
    if args.command == "freshness":
        from .freshness import freshness  # noqa: PLC0415
        repos_file = confined(args.repos, "the --repos file") if args.repos else None
        return freshness(args.dirs, args.json, repos_file)
    if args.command == "variables":
        from .variables import run as variables  # noqa: PLC0415
        if args.repos_file and args.repos:
            sys.exit("pubfleet variables: --repos takes the place of naming them")
        repos_file = confined(args.repos_file, "the --repos file") if args.repos_file else None
        return variables(confined(args.state, "the state file"), args.repos, args.apply, repos_file)
    if args.command == "state":
        from .state import check, repos_for  # noqa: PLC0415
        if args.repos_for:
            return repos_for(confined(args.file, "the state file"), args.repos_for)
        return check(confined(args.file, "the state file"))
    if args.command == "board-publish":
        from .board_publish import run as publish  # noqa: PLC0415
        return publish(args.url, args.tenant, confined(args.file, "the --file file"))
    from .board import run as board  # noqa: PLC0415
    files = {name: confined(path, f"the --{name} file") if path else None
             for name, path in (("rules", args.rules), ("replay", args.replay),
                                ("record", args.record), ("repos", args.repos))}
    return board(confined(args.out, "the --out directory"),
                 files["rules"], files["replay"], files["record"], files["repos"])


if __name__ == "__main__":
    sys.exit(main())
