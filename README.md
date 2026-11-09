# pubfleet

What a control plane runs across many repositories at once: it grades them
(`pubfleet board`), publishes the grades (`pubfleet board-publish`), checks
and reads the owner's state file (`pubfleet state`), keeps their GitHub
variables (`pubfleet variables`), reports which pubkit each pins
(`pubfleet freshness`), and opens their nightly pull requests (the reusable
`nightly.yml`). Everything that runs inside one repository about itself
stays in [pubkit](https://github.com/Sustenaut/pubkit): `sync`, `protect`,
`bump`, and `pubkit nightly`, which makes the nightly's commits in each
checkout.

    pubfleet board --out DIR --repos FILE [--rules FILE] [--replay FILE] [--record FILE]
    pubfleet board-publish --url URL --tenant TENANT [--file FILE]
    pubfleet state --check | --repos-for board|govern [FILE]
    pubfleet variables --check|--apply [--state FILE] [--repos FILE | REPO...]
    pubfleet freshness [--json] (DIR... | --repos FILE [DIR])
    pubfleet --version

## Installing

A control plane lists pubfleet's wheel beside pubkit's in its
`tests/requirements.txt`, and installs the hash-locked set:

    pubfleet @ https://github.com/Sustenaut/pubfleet/releases/download/vX.Y.Z/pubfleet-X.Y.Z-py3-none-any.whl

`pubkit lock` pins both by sha256. pubfleet declares the oldest pubkit it
works with (`pubkit>=` in pyproject.toml); its own `tests/requirements.lock`
pins the pubkit it is tested with.

## What pubfleet takes from pubkit

pubfleet uses pubkit as a library, and copies none of it: the board grades a
repository's protection against pubkit's own ruleset, and a copy would drift
from it. pubkit never imports pubfleet and names nothing of it. pubfleet
offers no `sustenaut.sync` or `sustenaut.bump` hook, so pubkit never loads it
into its own process.

These are all the names it takes, which `tests/features/pubkit.feature`
holds it to, and which the installed pubkit must have:

- the standard's protection: `pubkit.protect.entry`, `pubkit.protect.ruleset`,
  `pubkit.protect.tag_ruleset`, `pubkit.protect.differences`,
  `pubkit.protect.on_default_branch`, `pubkit.protect.on_release_tags`,
  `pubkit.protect.remote`;
- the GitHub calls: `pubkit.protect.gh`, `pubkit.protect.gh_set`,
  `pubkit.protect.Api`, `pubkit.protect.ApiError`,
  `pubkit.protect.remote_config`;
- the repos file: `pubkit.repos.read`, `pubkit.repos.entries`;
- the variables block's shape: `pubkit.variables.BLOCK`,
  `pubkit.variables.block_problems`, `pubkit.variables.name_problem`;
- the pins the board and freshness read: `pubkit.refs.ANY_OWNER`,
  `pubkit.refs.AT`, `pubkit.refs.VERSION`, `pubkit.refs.RELEASE_PIN`,
  `pubkit.freshness.PIN`, `pubkit.freshness.pinned`,
  `pubkit.nightly.PUBREL_VERSION`;
- the standard freshness judges by: `pubkit.conform.run`, `pubkit.__version__`;
- `pubkit.paths.confined`, for the files a command is given.

A name pubfleet wants beyond these is a sign the code belongs on one side or
the other, not a reason to widen the list.

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
- **Delivery** starts at A and takes a notch for each of: a pinned pubkit
  or pubrel behind its latest release; not integrated with pubkit
  (services) or with pubkit and pubrel (packages, which have a
  release.json); for a service, no observability (its health URL does not
  answer) and no continuous live testing (its live-test workflow not green
  in the last 24 hours); no release (a package's tag, a service's
  production deploy) in two months; any open issue (pull requests aside);
  no nightly (not governed, and no `nightly.yml` run in two days);
  protection that differs from what `pubkit protect --check` wants, or no
  ruleset at all on a private repository GitHub's plan gives none; and a
  red last CI run on main. A fact the board could not read takes its
  notch: a board that cannot see does not grade green.

A service declares what its observability and live testing are in its
`pubkit.json`:

```json
"live": { "health": "https://example.eu/health", "test": "live.yml", "deploy": "deploy.yml" }
```

`health` is the URL that must answer, `test` the scheduled workflow that
tests the live site, and `deploy` the workflow whose successful runs are
its production deploys (`deploy.yml` by default).

Each source has one connector in `src/pubfleet/board/connectors/`, and
nothing else reads it: `lists` (the two lists), `github` (the REST API:
visibility, pubkit.json, release.json, the lock and workflow pins,
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
(wheels only, by hash: the caller's own pubfleet and pubkit),
runs `pubfleet board` with the caller's read-only `token` and its `repos` input
(the repos file itself, as JSON), and uploads board.json and index.html as the `board` artifact, kept 90 days. It
deploys nothing.

## The repos file

Which repositories pubfleet and `pubkit protect` act on comes from outside them, in one file, whose format is pubkit's (`pubkit.repos`):

```json
{ "repositories": [
    { "repo": "example-org/some-tool", "protect": true, "govern": true, "project": "tools" },
    { "repo": "example-org/some-site", "protect": true, "govern": false }
] }
```

`protect` says it should carry pubkit's rulesets, and `govern` that a nightly
keeps it current; each is false when left out. `project`, optional, labels it on
the board. How a repository is protected stays in its own `pubkit.json`'s
protect block. `pubfleet board --repos FILE`, `pubkit protect [--check] --repos
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

    pubkit state --check [FILE]
    pubkit state --repos-for board|govern [FILE]

`--check` checks a state repository's `state.json` (by default in the working directory),
which a control plane keeps for one GitHub owner, and `--repos-for` prints the repos file
for one of its roles:

```json
{ "owner": "example-org",
  "repos": {
    "some-tool": { "project": "tools", "board": true, "protect": true, "govern": true }
} }
```

It checks the file's shape, then through `gh` that each repository exists under
the owner, and that each with `protect` has a sound protect block. `gh` needs a
token that can read every repository named, which a workflow's own
`GITHUB_TOKEN` can't. It builds nothing, so it suits being a state repository's
one required check.

### Variables from a state file

    pubfleet variables --check|--apply [--state FILE] [--repos FILE | REPO...]

A repository's GitHub variables that aren't secret can live in the state file, so a
change to one is a reviewed pull request with a history. The repository's own
`pubkit.json` declares only their names (pubkit's `sync --check` checks that block's shape), and may name the workflow that reads them,
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

## Freshness

    pubfleet freshness [--json] DIR...
    pubfleet freshness [--json] --repos FILE [DIR]

reports, for each checked-out repository, the pubkit its lock pins, whether it
is the installed one, whether it conforms to that pubkit's standard, and its
open exceptions: one Markdown table, also appended to the GitHub step summary
when there is one. With `--repos` it reports the repositories the file marks
to govern, each checked out at `DIR/<name>`, and says which are not checked
out. It reads; it changes nothing. Moving a repository to a pubkit is `pubkit
bump`'s, and the nightly's.

## The nightly

[`nightly.yml`](.github/workflows/nightly.yml) runs over the repositories its
`repos` input marks to govern, called from a control plane's own schedule. It
has no schedule of its own. Run by hand, it takes the same `repos` input. A
caller passes the secrets `app-id`, `app-key`, `notify-token` and
`notify-user`, and the `pubfleet` input names the repository whose latest
release supplies the wheel and the scripts in `.github/nightly/`.

Its report job checks each governed repository out and runs `pubfleet
freshness` into the summary. Its update job then keeps one pull request per
repository, on its `pubkit-nightly` branch (`.github/nightly/update.sh`): it
runs `pubkit nightly` in the checkout, which commits the moved pub* pins, the
audited crate updates, the npm updates and the re-locked Python requirements,
and writes the body. What those commits hold, and the `update` and `security`
settings a repository's `pubkit.json` gives them, are pubkit's (its README,
"The nightly"). An open pull request is updated, never a second one opened,
and left alone when the night brings nothing new. When its CI fails, the pins
are tested alone: if they pass, the dependency commits are dropped. Nothing
merges it: the Sustenaut bot sends a Slack DM when it is green or fails.

**Which pubkit.** The nightly installs the pubkit that the latest pubfleet
release's `tests/requirements.lock` pins, by hash
(`.github/nightly/install.sh`), and `pubkit nightly` moves each repository to
the pubkit it runs as. So a pubkit release reaches governed repositories
once pubfleet's own nightly has moved its lock to it and a pubfleet release
carries it: a night later than pubkit's release, and only once pubfleet's
suite has passed with it. The `pubkit` input, a pubkit release tag such as
`v0.33.1`, installs that pubkit instead, with a warning, for a fix that must
go out at once.

It pushes and opens the pull requests as the **Sustenaut nightly** GitHub
App, which is installed on each owner whose repositories it governs. For each
repository it mints a token for that repository alone, with contents,
pull-requests and workflows write and actions read, which expires within the
hour (`actions/create-github-app-token`). The repository variable
`NIGHTLY_APP_ID` and secret `NIGHTLY_APP_KEY` (the app's private key) set it
up when run by hand, and `app-id` and `app-key` when called. Without them it
falls back, with a warning, to a `PUBKIT_BUMP_TOKEN` secret, and with neither
it only reports.

`.github/nightly/pubrel-version.sh` chooses the pubrel it installs, and pins
each repository's release workflow to: its latest GitHub release if crates.io
has that version, else the newest crates.io has, with a warning.

## Developing

    make venv         # the hash-locked environment, this checkout installed editable
    make check        # what CI runs: ./pubkit sync --check and the suite

Releases are pubrel's: a code change records what it changes (`pubrel add`),
and `pubrel prepare` cuts the release pull request. `wheel.yml` attaches the
wheel once main has tagged it.

## Licence

Apache-2.0.
