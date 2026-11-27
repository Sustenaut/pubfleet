# pubfleet

What a control plane runs across many repositories at once: it grades them
(`pubfleet board`), publishes the grades (`pubfleet board-publish`), checks
and reads the owner's state file (`pubfleet state`), keeps their GitHub
variables (`pubfleet variables`), reports which pubrules each pins
(`pubfleet freshness`), and opens their nightly pull requests (the reusable
`nightly.yml`). Everything that runs inside one repository about itself
stays in [pubrules](https://github.com/Sustenaut/pubrules): `sync`, `protect`,
`bump`, and `pubrules nightly`, which makes the nightly's commits in each
checkout.

    pubfleet board --out DIR --repos FILE [--rules FILE] [--replay FILE] [--record FILE]
    pubfleet board-publish --url URL --tenant TENANT [--file FILE]
    pubfleet state --check | --repos-for board|govern|deploy | --discover [--body PATH] [FILE]
    pubfleet variables --check|--apply [--state FILE] [--repos FILE | REPO...]
    pubfleet freshness [--json] (DIR... | --repos FILE [DIR])
    pubfleet cycles --repos FILE [--replay FILE] [--record FILE]
    pubfleet pubrules-api --check
    pubfleet --version

## Installing

A control plane lists pubfleet's wheel beside pubrules' in its
`tests/requirements.txt`, and installs the hash-locked set:

    pubfleet @ https://github.com/Sustenaut/pubfleet/releases/download/vX.Y.Z/pubfleet-X.Y.Z-py3-none-any.whl

`pubrules lock` pins both by sha256. pubfleet declares the oldest pubrules it
works with (`pubrules>=` in pyproject.toml); its own `tests/requirements.lock`
pins the pubrules it is tested with.

## What pubfleet takes from pubrules

pubfleet uses pubrules as a library, and copies none of it: the board grades a
repository's protection against pubrules' own ruleset, and a copy would drift
from it. pubrules never imports pubfleet and names nothing of it. pubfleet
offers no `sustenaut.sync` or `sustenaut.bump` hook, so pubrules never loads it
into its own process.

It imports only from pubrules.api, the surface pubrules holds steady (pubrules'
own suite fails when that surface changes), never from pubrules' internal modules.
These are all the names it takes, which `tests/features/pubrules.feature`
holds it to, and which the installed pubrules.api must export:

- the standard's protection: `pubrules.api.protection_entry`, `pubrules.api.ruleset`,
  `pubrules.api.tag_ruleset`, `pubrules.api.ruleset_differences`,
  `pubrules.api.on_default_branch`, `pubrules.api.on_release_tags`,
  `pubrules.api.remote_protection_entry`;
- the GitHub calls: `pubrules.api.gh`, `pubrules.api.gh_set`,
  `pubrules.api.Api`, `pubrules.api.ApiError`,
  `pubrules.api.remote_config`;
- the repos file: `pubrules.api.read_repos`, `pubrules.api.repo_entries`;
- the variables block's shape and defaults: `pubrules.api.VARIABLES_BLOCK`,
  `pubrules.api.variables_problems`, `pubrules.api.variable_name_problem`,
  `pubrules.api.variable_defaults`;
- the pins the board and freshness read: `pubrules.api.ANY_OWNER`,
  `pubrules.api.AT`, `pubrules.api.VERSION`, `pubrules.api.RELEASE_PIN`,
  `pubrules.api.PUBRULES_LOCK_PIN`, `pubrules.api.pinned_pubrules`,
  `pubrules.api.PUBREL_VERSION_INPUT`;
- the standard freshness judges by: `pubrules.api.conform`, `pubrules.api.version`;
- `pubrules.api.confined`, for the files a command is given.

A name pubfleet wants beyond these is a sign the code belongs on one side or
the other, not a reason to widen the list.

`src/pubfleet/pubrules-api.txt` records the shape of each of these names in the
pubrules pubfleet is tested with (a function's signature, a class's bases and
public methods, a pattern's text and flags, a constant's value, as pubrules'
own `tests/fixtures/api.txt` writes them), and `tests/features/pubrules.feature` holds it to the
imports and to the locked pubrules.

    pubfleet pubrules-api --check

compares it with the pubrules installed beside pubfleet and fails on a name it
lacks or a shape that differs. pubrules' suite fails on a change to its api, but
a release can still carry one deliberately; this is what keeps the nightly from
running pubfleet on a pubrules it was not tested on.

## The release board

    pubfleet board --out DIR --repos FILE [--rules FILE]

grades every repository the repos file (or the two lists) names, public and private, A to E for
quality, security and delivery, and writes `DIR/board.json` and a static
`DIR/index.html`: no scripts, rows worst first, each grade a dot in
SonarQube's colours whose breakdown opens on hover or keyboard focus. It
only reads, and keeps nothing between builds. `GITHUB_TOKEN` (or
`GH_TOKEN`) is the token it reads GitHub with; `SONAR_TOKEN`, when set,
reads private SonarQube Cloud projects.

The rules are [`src/pubfleet/board/rules.json`](src/pubfleet/board/rules.json),
applied by `rules.py`; `--rules FILE` reads others, such as a client's.
Each grade is a starting letter less one letter per notch, never below E,
with every notch listed; the overall grade is the worst of the three.

- **Quality** starts at SonarQube Cloud's worse rating of reliability and
  maintainability, **Security** at its security rating. With no analysis,
  each starts at A and takes a notch. Then each other tool with findings
  takes one: a CI job on main's last run that failed (format and lint,
  tests, functional and browser tests, MSRV, fuzzing, cross builds and
  toolchains for Quality; the dependency audit, OSV-Scanner and dependency
  review for Security), open Dependabot, code scanning or secret scanning
  alerts, and an OpenSSF Scorecard under 7 for a public repository.
  Alerts that are switched off are listed with no notch.
- **Delivery** starts at A and takes a notch for each of: a pinned pubrules
  or pubrel behind its latest release; not integrated with pubrules
  (services) or with pubrules and pubrel (packages, which have a
  release.json); for a service, no observability (its health URL does not
  answer) and no continuous live testing (its live-test workflow not green
  in the last 24 hours); no release (a package's tag, a service's
  production deploy) in two months; any open issue (pull requests aside);
  no nightly (not governed, and no `nightly.yml` run in two days);
  protection that differs from what `pubrules protect --check` wants, or no
  ruleset at all on a private repository GitHub's plan gives none; and a
  red last CI run on main. A fact the board could not read takes its
  notch: a board that cannot see does not grade green.

A service declares what its observability and live testing are in its
`pubrules.json`:

```json
"live": { "health": "https://example.eu/health", "test": "live.yml", "deploy": "deploy.yml" }
```

`health` is the URL that must answer, `test` the scheduled workflow that
tests the live site, and `deploy` the workflow whose successful runs are
its production deploys (`deploy.yml` by default).

Each source has one connector in `src/pubfleet/board/connectors/`, and
nothing else reads it: `lists` (the two lists), `github` (the REST API:
visibility, pubrules.json, release.json, the lock and workflow pins,
rulesets, releases, issues and alerts), `actions` (runs and jobs on main,
nightly, live-test and deploy runs), `sonarcloud` (project `OWNER_REPO`),
`scorecard` (public repositories) and `live` (the health URLs). Each
query is a named method, and each call is recorded with its connector,
method, endpoint and time: board.json lists every call, and links every
fact and every notch to the calls it rests on, which the breakdown names.
`--record FILE` keeps every response, and `--replay FILE` builds from
such a file instead of the network.

[`board.yml`](.github/workflows/board.yml) is the reusable workflow: it
checks out the caller, installs what its `tests/requirements.lock` pins
(wheels only, by hash: the caller's own pubfleet and pubrules),
runs `pubfleet board` with the caller's read-only `token` and its `repos` input
(the repos file itself, as JSON), and uploads board.json and index.html as the `board` artifact, kept 90 days. It
deploys nothing.

## The repos file

Which repositories pubfleet and `pubrules protect` act on comes from outside them, in one file, whose format is pubrules' (`pubrules.repos`):

```json
{ "repositories": [
    { "repo": "example-org/some-tool", "protect": true, "govern": true, "project": "tools" },
    { "repo": "example-org/some-site", "protect": true, "govern": false }
] }
```

`protect` says it should carry pubrules' rulesets, and `govern` that a nightly
keeps it current; each is false when left out. `project`, optional, labels it on
the board. How a repository is protected stays in its own `pubrules.json`'s
protect block. `pubfleet board --repos FILE`, `pubrules protect [--check] --repos
FILE` and `pubfleet freshness --repos FILE [DIR]` read it (freshness reports the
governed ones, each checked out at `DIR/<name>`), and the reusable `board.yml`
and `nightly.yml` take its contents as a `repos` input.

    pubfleet board-publish --url URL --tenant TENANT [--file FILE]

keeps a board (by default `site/board.json`) in a storage tenant, for a job whose
logs must stay quiet: it prints no repository's name. It uploads only if a fact or a grade
differs from what the tenant's `board` head names, then moves the head, conditionally, so
a move by someone else fails the run. It signs in with the GitHub Actions job's OpenID
Connect token, for the audience that is the URL's host name, so the job needs `id-token:
write` and no secret, and the tenant must let that job write.

### State files

    pubrules state --check [FILE]
    pubrules state --repos-for board|govern|deploy [FILE]
    pubrules state --discover [--body PATH] [FILE]

`--check` checks a state repository's `state.json` (by default in the working directory),
which a control plane keeps for one GitHub owner, and `--repos-for` prints the repos file
for one of its roles:

```json
{ "owner": "example-org",
  "repos": {
    "some-tool": { "project": "tools", "board": true, "protect": true, "govern": true },
    "some-service": { "board": true, "protect": true, "govern": true, "deploy": true }
} }
```

`--discover` adds the owner's repositories the file does not list yet, archived ones
and forks left out: each on the board, protected when its own `pubrules.json` has a protect
block (which `--check` requires of protect), and not governed, with no project and no
deploy. It rewrites the file as state files are kept (two-space JSON, repositories in name
order), prints how many it added, and with `--body` writes a pull request's description:
each one added, its visibility and why protect is on or off, and the listed repositories
that are archived or gone, which it never removes. A state repository's nightly runs it
and opens that pull request for an operator to merge.

`deploy`, optional and false when left out, marks a repository the convergence
engine walks: the state says whether, and the repository's `pubrules.json` deploy
block says how.

It checks the file's shape, then through `gh` that each repository exists under
the owner, that each with `protect` has a sound protect block, and that each with
`deploy` has a deploy block. `gh` needs a
token that can read every repository named, which a workflow's own
`GITHUB_TOKEN` can't. It builds nothing, so it suits being a state repository's
one required check.

### Variables from a state file

    pubfleet variables --check|--apply [--state FILE] [--repos FILE | REPO...]

A repository's GitHub variables that aren't secret can live in the state file, so a
change to one is a reviewed pull request with a history. The repository's own
`pubrules.json` declares only their names (pubrules' `sync --check` checks that block's shape), and may name the workflow that reads them,
to run once one changes:

```json
"variables": { "names": ["SOME_SETTING", "SOME_MAP"], "deploy": "deploy.yml" }
```

The state file gives their values, under the repository:

```json
"some-tool": { "board": true, "protect": true, "govern": false,
  "variables": { "SOME_SETTING": "a string", "SOME_MAP": { "some-key": "some-value" } } }
```

A string goes to GitHub as it is; anything else is JSON, kept structured in the state
so that a diff shows the entry that changed, and sent compact, in the file's order. A
JSON value matches what GitHub holds if that parses to the same thing. `state --check`
refuses a name the repository doesn't declare, and an empty value.

`--check` changes nothing: it prints how each repository's variables differ, a diff of
the changed entries for JSON, and fails when one does, which suits a pull request's
plan and a nightly drift report. `--apply` sets those that differ, each value on
`gh`'s standard input, and then runs the repository's `deploy` workflow on its default
branch, once. Both act on every repository the state gives variables, those named, or
those a repos file lists, and neither touches a variable the state leaves out nor
removes one. The token needs to read the repositories' contents and variables, and for
`--apply` to write variables and run workflows (the Variables and Actions permissions,
for a GitHub App).

A repository's block of version 2 (pubrules 0.49.1) may give a name a `defaults`
entry, the constant its code falls back to when the variable is unset or empty. A
state value equal to that default is then satisfied with GitHub holding nothing, or
an empty value, so nothing is set; pubfleet says so as information only, never as a
failure, since the state need not give it. A null default is no value: a state value
for that name still has to be set. A default compares as the state's values do, as
GitHub would hold it.

### The SLA block of a state file

A state file may hold an `SLA` block: how soon each service's calls must reach the call
log, and how soon its silence or its address not answering is found. Its tiers are org
configuration, named by the owner and defined once; each service of the state names the
tier of each of its senders and of its address. pubfleet owns the block and is its one
schema (`pubfleet.sla`):

```json
"SLA": {"version": 1,
        "tiers": {"tight": {"deadline_seconds": 30, "heartbeat_seconds": 60, "misses": 2, "uptime_minutes": 10},
                  "idle": {"deadline_seconds": 28800, "heartbeat_seconds": 3600, "misses": 3},
                  "on-demand": {"deadline_seconds": 120}},
        "services": {"release-controlplane": {"senders": {"app": "tight"}, "uptime": "tight"},
                     "business-plan": {"senders": {"plan": "on-demand"}, "uptime": "tight",
                                       "address": "https://plan.example.eu/healthz"}}}
```

A tier has `deadline_seconds`, and maybe `heartbeat_seconds` (how often a quiet sender
says it is alive; a tier without one has no heartbeat and no alarm for silence), `misses`
(heartbeats missed in a row before the alarm, at least 2, 2 when left out) and
`uptime_minutes` (how soon an address not answering is found). A service's `uptime`
names a tier with `uptime_minutes`; its `address` is the https URL checked, else
https:// and its deploy's host. A block of an older version is read through the
transformers, one a version, chained to the latest.

From it pubfleet derives:

- each sender's absence alert: `misses` × `heartbeat_seconds` and a margin of 180 s;
- each address's uptime check: every 1, 5, 10 or 15 minutes, the longest at most half
  the tier's `uptime_minutes`, from three regions, alarming once two of them fail two
  runs in a row;
- the GitHub variables: each service's `CALL_LOG_DEADLINE_SECONDS`, the tightest of its
  senders', its `CALL_LOG_METRIC_SECONDS`, the tightest `heartbeat_seconds` of its senders
  that have one (the heartbeat metric's interval, integrations' `heartbeat`), and while
  observability judges silence, its `OBSERVABILITY_SENDERS` (a tier
  with no heartbeat as `on-demand`). A tier's `heartbeat_seconds` is its Cloud Monitoring
  metric's: the call log's file heartbeat, `CALL_LOG_HEARTBEAT_SECONDS`, a file in storage
  each time, is never derived, and stays a plain variable of the state while there is one.
  `pubfleet variables` gives them as it gives the state's own; the state may not set one
  of them beside the block, and a repository that doesn't declare one yet is not given it;
- the budget: uptime runs a month (each region's run is one) and the heartbeats' metric
  bytes (8 a point, each replica its own) against Cloud Monitoring's free 1 million runs
  and 150 MiB.

`pubfleet state --check` refuses a block of the wrong shape, one naming a service the
state doesn't list, numbers Cloud Monitoring can't take, and one past a free tier.
`pubfleet sla --derive` prints everything derived as JSON, for shared-infra's Terraform
variable (`--offline` reads no pubrules.json, so every uptime service needs an address),
and `pubfleet sla --budget` the budget alone, failing past a free tier. `--replicas
SERVICE/SENDER=N` counts a sender run N at once (1 by default).

## Dependency cycles

    pubfleet cycles --repos FILE [--replay FILE] [--record FILE]

reads every repository the repos file names, public and private, through the
board's github connector (`GITHUB_TOKEN` or `GH_TOKEN`, contents read), builds
their dependency graph, test time included, and fails on any cycle in it. What a
repository is: the names its pyproject.toml, Cargo.toml, package.json and
release.json give it. What it needs: pyproject.toml's `dependencies` and
`optional-dependencies`; `tests/requirements.txt` and
`tests/requirements-pubrules.txt`, by name or by release wheel URL; Cargo.toml's
`dependencies`, `dev-dependencies` and `build-dependencies`, by name or git URL;
package.json's `dependencies` and `devDependencies`, by name or GitHub URL.

Two kinds of edge are left out, because every repository has them, the tools'
own included, and counting them would make each a cycle with pubrules: the
`pubrules` line pubrules' managed `tests/requirements-pubrules.txt` writes, and
workflow `uses:` pins. A repository whose code imports pubrules declares it in
pyproject.toml, and that edge counts. `tests/requirements.lock` is read too: a
listed repository's package it pins that nothing declared explains is reported
as undeclared, but is not an edge. Each cycle prints as `a -> b -> a`, with the
file and line of each edge; a cycle, or a file that could not be read, exits 1.
`--record` and `--replay` work as the board's do.

## Freshness

    pubfleet freshness [--json] DIR...
    pubfleet freshness [--json] --repos FILE [DIR]

reports, for each checked-out repository, the pubrules its lock pins, whether it
is the installed one, whether it conforms to that pubrules' standard, and its
open exceptions: one Markdown table, also appended to the GitHub step summary
when there is one. With `--repos` it reports the repositories the file marks
to govern, each checked out at `DIR/<name>`, and says which are not checked
out. It reads; it changes nothing. Moving a repository to a pubrules is `pubrules
bump`'s, and the nightly's.

## The nightly

[`nightly.yml`](.github/workflows/nightly.yml) runs over the repositories its
`repos` input marks to govern, called from a control plane's own schedule. It
has no schedule of its own. Run by hand, it takes the same `repos` input. A
caller passes the secrets `client-id`, `app-key`, `notify-token` and
`notify-user`, and the `pubfleet` input names the repository whose latest
release supplies the wheel and the scripts in `.github/nightly/`.

Its report job checks each governed repository out and runs `pubfleet
freshness` into the summary. Its update job then keeps one pull request per
repository, on its `pubrules-nightly` branch (`.github/nightly/update.sh`): it
runs `pubrules nightly` in the checkout, which commits the moved pub* pins, the
audited crate updates, the npm updates and the re-locked Python requirements,
and writes the body. What those commits hold, and the `update` and `security`
settings a repository's `pubrules.json` gives them, are pubrules' (its README,
"The nightly"). An open pull request is updated, never a second one opened,
and left alone when the night brings nothing new. When its CI fails, the pins
are tested alone: if they pass, the dependency commits are dropped. Nothing
merges it: the Sustenaut bot sends a Slack DM when it is green or fails.

**Which pubrules.** The nightly installs pubrules' latest release, its wheel
checked against the sha256 GitHub gives for it, when `pubfleet pubrules-api
--check` says its `pubrules.api` has the names and shapes the latest pubfleet
release was tested on (see "What pubfleet takes from pubrules"). Otherwise it
goes back to the pubrules that release's `tests/requirements.lock` pins, by hash,
with a warning (`.github/nightly/install.sh`). `pubrules nightly` then moves each
repository to the pubrules it runs as. So a pubrules release reaches governed
repositories the next night with no pubfleet release in between, unless it
changed what pubfleet imports; then it waits for a pubfleet release tested on
it. The `pubrules` input, a pubrules release tag such as `v0.33.1`, installs
that pubrules instead, unchecked and with a warning, for a fix that must go out
at once.

**Dependency cycles.** The nightly's `cycles` job runs `pubfleet cycles` on every
repository the repos input names (see "Dependency cycles" below), reading them
with the nightly app's token for their owner, contents read only. A cycle fails
that job alone; the updates go ahead.

It pushes and opens the pull requests as the **Sustenaut nightly** GitHub
App, which is installed on each owner whose repositories it governs. For each
repository it mints a token for that repository alone, with contents,
pull-requests and workflows write and actions read, which expires within the
hour (`actions/create-github-app-token`). The repository variable
`NIGHTLY_APP_CLIENT_ID` (the app's client id) and secret `NIGHTLY_APP_KEY`
(its private key) set it up when run by hand, and `client-id` and `app-key`
when called. Without them it
falls back, with a warning, to a `PUBRULES_BUMP_TOKEN` secret, and with neither
it only reports.

`.github/nightly/pubrel-version.sh` chooses the pubrel it installs, and pins
each repository's release workflow to: its latest GitHub release if crates.io
has that version, else the newest crates.io has, with a warning.

## Developing

    make venv         # the hash-locked environment, this checkout installed editable
    make check        # what CI runs: ./pubrules sync --check and the suite

Releases are pubrel's: a code change records what it changes (`pubrel add`),
and `pubrel prepare` cuts the release pull request. `wheel.yml` attaches the
wheel once main has tagged it.

## Licence

Apache-2.0.
