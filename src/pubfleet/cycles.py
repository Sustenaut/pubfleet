"""`pubfleet cycles`: the dependency graph of the repositories a repos file
names, test time included, and every cycle in it.

    pubfleet cycles --repos FILE [--replay FILE] [--record FILE]

It reads each repository through the board's github connector, so it reads
public and private ones with the same token (GITHUB_TOKEN or GH_TOKEN) and
replays a recording the same way. What a repository **is**: the names its
pyproject.toml, Cargo.toml, package.json and release.json give it. What it
**needs**, at run time and at test time:

- pyproject.toml's `dependencies` and `optional-dependencies`;
- tests/requirements.txt and tests/requirements-pubrules.txt: names (`name==`,
  `name>=`) and wheel URLs, whose repository is in the URL;
- Cargo.toml's `dependencies`, `dev-dependencies` and `build-dependencies`,
  a target's too, by name or by git URL;
- package.json's `dependencies` and `devDependencies`, by name or by a
  GitHub URL.

Two kinds of edge are left out, because every repository has them, the
tools' own repositories included, and counting them makes each a cycle with
pubrules: the toolchain line pubrules' managed requirements-pubrules.txt writes
(`pubrules==`), and workflow `uses:` pins. A repository whose code imports
pubrules declares it in pyproject.toml, and that edge counts.

tests/requirements.lock is read too: a package of these repositories in it
that no declared edge explains, directly or through another repository's, is
reported as an undeclared edge. It is not an edge of the graph.

Each cycle prints as `a -> b -> a`, each edge with the file and line it is
read from, and any cycle, or a repository that could not be read, exits 1.
"""

from __future__ import annotations

import json
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .board.connectors.base import Fact, Ledger, Network, Recording, Replay, Transport, now
from .board.connectors.github import GitHub
from .board.connectors.repos import Repos

# Where a repository says what it is and what it needs.
FILES = ("pyproject.toml", "Cargo.toml", "package.json", "release.json",
         "tests/requirements.txt", "tests/requirements-pubrules.txt", "tests/requirements.lock")
# The toolchain line of pubrules' managed requirements file: every repository has it.
MANAGED = "tests/requirements-pubrules.txt"
TOOLCHAIN = "pubrules"
# A requirement line: a name, extras, then a version, a marker or a URL.
REQUIREMENT = re.compile(r"^\s*(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(?P<rest>.*)$")
# A repository named in a URL: a release wheel, a git dependency, a GitHub shorthand.
GITHUB_REPO = re.compile(r"(?:github\.com[/:]|^github:)(?P<owner>[A-Za-z0-9][A-Za-z0-9-]*)/"
                         r"(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?(?=[/#@?\s]|$)")
LOCKED = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*(?:==|@)", re.M)


def normal(name: str) -> str:
    """A package name as indexes compare them (PEP 503): lower case, runs of -_. as one -."""
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass(frozen=True)
class Edge:
    """`source` needs `target`, as `where` (file:line) says."""
    source: str
    target: str
    where: str


@dataclass
class Repo:
    repo: str
    names: set[str] = field(default_factory=set)
    # (a package name, or "repo:OWNER/NAME" for one named by URL; where)
    needs: list[tuple[str, str]] = field(default_factory=list)
    locked: list[tuple[str, str]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def line_of(text: str, needle: str, after: str = "") -> int:
    """The first line of `text` holding `needle` past the first holding `after`,
    1 when none does."""
    start = text.find(after) if after else 0
    found = text.find(needle, max(start, 0))
    return text.count("\n", 0, found) + 1 if found >= 0 else 1


def by_url(value: str) -> str | None:
    m = GITHUB_REPO.search(value)
    return f"repo:{m['owner']}/{m['repo']}".lower() if m else None


def requirement(spec: str) -> str | None:
    """What a requirement names: its repository when a URL gives one, else its package."""
    m = REQUIREMENT.match(spec)
    if not m:
        return None
    return by_url(m["rest"]) or normal(m["name"])


def read_requirements(r: Repo, path: str, text: str) -> None:
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith(("#", "-")):
            continue
        m = REQUIREMENT.match(line)
        target = requirement(line)
        if target is None or m is None:
            continue
        if path == MANAGED and normal(m["name"]) == TOOLCHAIN:
            continue
        r.needs.append((target, f"{path}:{number}"))


def read_pyproject(r: Repo, text: str) -> None:
    data = tomllib.loads(text)
    project = data.get("project") or {}
    if isinstance(project.get("name"), str):
        r.names.add(normal(project["name"]))
    specs = list(project.get("dependencies") or [])
    for extra in (project.get("optional-dependencies") or {}).values():
        specs += list(extra or [])
    for spec in specs:
        if isinstance(spec, str) and (target := requirement(spec)):
            r.needs.append((target, f"pyproject.toml:{line_of(text, spec)}"))


def cargo_tables(data: dict) -> list[dict]:
    tables = [data.get(k) or {} for k in ("dependencies", "dev-dependencies", "build-dependencies")]
    for target in (data.get("target") or {}).values():
        tables += [target.get(k) or {} for k in ("dependencies", "dev-dependencies",
                                                 "build-dependencies")]
    return tables


def read_cargo(r: Repo, text: str) -> None:
    data = tomllib.loads(text)
    if isinstance((data.get("package") or {}).get("name"), str):
        r.names.add(normal(data["package"]["name"]))
    for table in cargo_tables(data):
        for name, spec in table.items():
            git = spec.get("git") if isinstance(spec, dict) else None
            package = spec.get("package", name) if isinstance(spec, dict) else name
            target = (by_url(git) if isinstance(git, str) else None) or normal(package)
            r.needs.append((target, f"Cargo.toml:{line_of(text, name, 'dependencies]')}"))


def read_package_json(r: Repo, text: str) -> None:
    data = json.loads(text)
    if isinstance(data.get("name"), str):
        r.names.add(normal(data["name"].rsplit("/", 1)[-1]))
        r.names.add(normal(data["name"]))
    for key in ("dependencies", "devDependencies"):
        for name, spec in (data.get(key) or {}).items():
            target = (by_url(spec) if isinstance(spec, str) else None) or normal(name)
            r.needs.append((target, f"package.json:{line_of(text, json.dumps(name), json.dumps(key))}"))


def read_lock(r: Repo, text: str) -> None:
    for m in LOCKED.finditer(text):
        number = text.count("\n", 0, m.start()) + 1
        r.locked.append((normal(m["name"]), f"tests/requirements.lock:{number}"))


def read(gh: GitHub, repo: str) -> Repo:
    """One repository's names, declared needs and lock, from GitHub."""
    r = Repo(repo)
    r.names.add(f"repo:{repo}".lower())
    readers = {"pyproject.toml": read_pyproject, "Cargo.toml": read_cargo,
               "package.json": read_package_json, "tests/requirements.lock": read_lock}
    for path in FILES:
        fact: Fact = gh.dependency_file(repo, path)
        if fact.value is None:
            if fact.note and fact.note != f"no {path}":
                r.problems.append(f"{repo}: {path} could not be read: {fact.note}")
            continue
        try:
            if path == "release.json":
                name = json.loads(fact.value).get("name")
                if isinstance(name, str):
                    r.names.add(normal(name))
            elif path.startswith("tests/requirements") and path != "tests/requirements.lock":
                read_requirements(r, path, fact.value)
            else:
                readers[path](r, fact.value)
        except (ValueError, tomllib.TOMLDecodeError, AttributeError) as e:
            r.problems.append(f"{repo}: {path} could not be parsed: {e}")
    return r


@dataclass
class Graph:
    repos: dict[str, Repo]
    edges: dict[str, list[Edge]]
    undeclared: list[str]

    def cycles(self) -> list[list[str]]:
        """Each strongly connected group of more than one repository, as one cycle
        through it, starting at its first repository by name."""
        index: dict[str, int] = {}
        low: dict[str, int] = {}
        stack: list[str] = []
        on: set[str] = set()
        groups: list[list[str]] = []

        def visit(node: str) -> None:
            index[node] = low[node] = len(index)
            stack.append(node)
            on.add(node)
            for edge in self.edges.get(node, []):
                if edge.target not in index:
                    visit(edge.target)
                    low[node] = min(low[node], low[edge.target])
                elif edge.target in on:
                    low[node] = min(low[node], index[edge.target])
            if low[node] == index[node]:
                group = []
                while True:
                    top = stack.pop()
                    on.discard(top)
                    group.append(top)
                    if top == node:
                        break
                if len(group) > 1:
                    groups.append(sorted(group))

        for node in sorted(self.repos):
            if node not in index:
                visit(node)
        return [self.path(group) for group in sorted(groups)]

    def path(self, group: list[str]) -> list[str]:
        """A cycle through `group`, from its first member back to it."""
        start, members = group[0], set(group)
        seen, trail = {start}, [start]

        def walk(node: str) -> bool:
            for edge in sorted(self.edges.get(node, []), key=lambda e: e.target):
                if edge.target == start and len(trail) > 1:
                    trail.append(start)
                    return True
                if edge.target in members and edge.target not in seen:
                    seen.add(edge.target)
                    trail.append(edge.target)
                    if walk(edge.target):
                        return True
                    trail.pop()
            return False

        walk(start)
        return trail

    def edge(self, source: str, target: str) -> Edge:
        return next(e for e in self.edges[source] if e.target == target)


def graph(read_repos: list[Repo]) -> Graph:
    owners: dict[str, str] = {}
    for r in read_repos:
        for name in r.names:
            owners.setdefault(name, r.repo)
    edges: dict[str, list[Edge]] = {}
    for r in read_repos:
        found = {}
        for target, where in r.needs:
            to = owners.get(target)
            if to and to != r.repo and to not in found:
                found[to] = Edge(r.repo, to, where)
        edges[r.repo] = sorted(found.values(), key=lambda e: e.target)
    g = Graph({r.repo: r for r in read_repos}, edges, [])

    def reach(start: str) -> set[str]:
        out, todo = set(), [start]
        while todo:
            for e in edges.get(todo.pop(), []):
                if e.target not in out:
                    out.add(e.target)
                    todo.append(e.target)
        return out

    for r in read_repos:
        reached = reach(r.repo)
        for name, where in r.locked:
            to = owners.get(name)
            if to and to != r.repo and to not in reached and name != TOOLCHAIN:
                g.undeclared.append(f"{r.repo}: {where} locks {name} ({to}), which nothing it "
                                    "declares needs")
    return g


def build(repos_file: Path, transport: Transport) -> tuple[Graph, list[str]]:
    ledger = Ledger(clock=now)
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or None
    listed = Repos(ledger, transport).listed(repos_file)
    if listed.value is None:
        raise SystemExit(f"pubfleet cycles: {listed.note}")
    gh = GitHub(ledger, transport, token)
    read_repos = [read(gh, entry["repo"]) for entry in listed.value]
    return graph(read_repos), [p for r in read_repos for p in r.problems]


def report(g: Graph, problems: list[str]) -> tuple[list[str], bool]:
    """The lines to print, and whether the check failed."""
    out = []
    cycles = g.cycles()
    for cycle in cycles:
        out.append("cycle: " + " -> ".join(cycle))
        for source, target in zip(cycle, cycle[1:], strict=False):
            out.append(f"  {source} needs {target} ({g.edge(source, target).where})")
    out += [f"undeclared: {line}" for line in g.undeclared]
    out += [f"unread: {line}" for line in problems]
    if not cycles:
        out.insert(0, f"No dependency cycle among {len(g.repos)} repositories "
                      f"({sum(map(len, g.edges.values()))} edges; the toolchain line and workflow "
                      "pins are not edges).")
    return out, bool(cycles or problems)


def run(repos_file: Path, replay: Path | None, record: Path | None) -> int:
    if replay:
        transport: Transport = Replay(replay)
    else:
        transport = Recording(Network()) if record else Network()
    g, problems = build(repos_file, transport)
    if record and isinstance(transport, Recording):
        transport.save(record, now())
    lines, failed = report(g, problems)
    for line in lines:
        print(line)
    return 1 if failed else 0
