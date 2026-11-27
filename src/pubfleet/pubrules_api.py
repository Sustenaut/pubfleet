"""The pubrules.api pubfleet was tested on: the names it imports and their
shapes, kept in pubrules-api.txt beside this module.

    pubfleet pubrules-api --check

compares them with the pubrules installed beside pubfleet and exits 1 on a
name it lacks or a shape that differs. The nightly's install.sh runs it after
installing pubrules' latest release, and falls back to the pubrules pubfleet's
lock pins when it fails: pubrules' own suite fails on a change to its api, but
a release can still carry one, and pubfleet was not tested on it.

A shape is what pubrules' tests/steps/test_api.py records: a function's
signature, a class's bases and public methods, a pattern's text and flags, a
constant's value.
"""

from __future__ import annotations

import importlib
import inspect
import re
import sys
from importlib import resources

FIXTURE = "pubrules-api.txt"


def shape(value: object) -> str:
    """What pubfleet relies on in `value`, as pubrules' test_api.py writes it."""
    if isinstance(value, re.Pattern):
        return f"pattern {value.pattern!r} flags={int(value.flags)}"
    if inspect.isclass(value):
        bases = ", ".join(b.__name__ for b in value.__bases__)
        own = [f"{name}{inspect.signature(member)}" for name, member in sorted(vars(value).items())
               if inspect.isfunction(member) and (name == "__init__" or not name.startswith("_"))]
        return f"class({bases}) " + "; ".join(own)
    if inspect.isfunction(value):
        return f"function{inspect.signature(value)}"
    if isinstance(value, (str, int, float, bool)):
        return f"constant {value!r}"
    return f"type {value!r}"


def shape_of(name: str) -> str | None:
    """The installed pubrules.api's shape of `name`; None when it lacks it."""
    api = importlib.import_module("pubrules.api")
    if name not in getattr(api, "__all__", ()):
        return None
    if name == "version":
        # It moves every release; what pubfleet relies on is that it is a str.
        return "str, the installed version" if isinstance(api.version, str) else shape(api.version)
    return shape(getattr(api, name))


def recorded(text: str | None = None) -> dict[str, str]:
    """The fixture: name to shape, its # comment lines left out."""
    if text is None:
        text = (resources.files("pubfleet") / FIXTURE).read_text(encoding="utf-8")
    out = {}
    for line in text.splitlines():
        if line and not line.startswith("#"):
            name, _, rest = line.partition(": ")
            out[name] = rest
    return out


def differences(fixture: dict[str, str] | None = None) -> list[str]:
    """Each name of the fixture the installed pubrules.api lacks, or holds in another shape."""
    out = []
    for name, want in sorted((fixture if fixture is not None else recorded()).items()):
        have = shape_of(name)
        if have is None:
            out.append(f"{name}: pubrules.api has no such name")
        elif have != want:
            out.append(f"{name}: tested on {want}, installed is {have}")
    return out


def check() -> int:
    found = differences()
    version = getattr(importlib.import_module("pubrules.api"), "version", "?")
    if found:
        print(f"pubfleet pubrules-api: pubrules {version}'s api is not the one pubfleet was tested on:",
              file=sys.stderr)
        for line in found:
            print(f"  {line}", file=sys.stderr)
        return 1
    print(f"pubrules {version}'s api is the one pubfleet was tested on.")
    return 0
