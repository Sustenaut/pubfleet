"""Steps for pubfleet's use of pubrules: the names it imports, which its README
lists and the installed pubrules must have."""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

from pytest_bdd import parsers, scenarios, then, when

scenarios("pubrules.feature")

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "pubfleet"


@when("I read every import of pubrules in src/pubfleet", target_fixture="imported")
def imports():
    found = set()
    for path in sorted(SOURCE.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module \
                    and node.module.split(".")[0] == "pubrules":
                found |= {f"{node.module}.{a.name}" for a in node.names}
            elif isinstance(node, ast.Import):
                assert not any(a.name.split(".")[0] == "pubrules" for a in node.names), \
                    f"{path}: import pubrules names nothing; take the names with from"
    assert found
    return found


def listed():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    section = text.split("## What pubfleet takes from pubrules", 1)[1].split("\n## ", 1)[0]
    return set(re.findall(r"`(pubrules(?:\.[A-Za-z_]+)+)`", section))


@then(parsers.parse('each is one the README lists under "{heading}"'))
def all_listed(imported, heading):
    missing = imported - listed()
    assert not missing, f"imported from pubrules but not listed under {heading}: {sorted(missing)}"


@then("the README lists none that pubfleet does not import")
def none_extra(imported):
    extra = listed() - imported
    assert not extra, f"listed but not imported: {sorted(extra)}"


@then("the installed pubrules has each of them")
def installed(imported):
    for name in sorted(imported):
        module, _, attr = name.rpartition(".")
        assert hasattr(importlib.import_module(module), attr), f"pubrules has no {name}"
