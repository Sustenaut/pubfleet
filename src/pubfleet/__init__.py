"""pubfleet: what a control plane runs across many repositories: grade
them (board), publish the grades (board-publish), check and read the owner's
state file (state), keep their GitHub variables (variables), and report
which pubkit each pins (freshness). Its reusable workflows grade them
(board.yml) and open their nightly pull requests (nightly.yml, which runs
`pubkit nightly` in each checkout).

It uses pubkit as a library, for the standard it grades against and the
GitHub calls pubkit makes; pubkit never imports it.
"""

from __future__ import annotations


def _version() -> str:
    from importlib.metadata import PackageNotFoundError, version  # noqa: PLC0415
    try:
        return version("pubfleet")
    except PackageNotFoundError:
        return "0+source"


__version__ = _version()
