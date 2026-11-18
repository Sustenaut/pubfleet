Feature: The nightly keeps every governed repository current, through a pull request
  nightly.yml checks out each repository the repos input governs and runs
  `pubrules nightly` there (.github/nightly/update.sh), which commits the moved
  pins and the updates and writes the pull request's body. The workflow keeps
  one pull request per repository and never merges it. It installs the pubrules
  the latest pubfleet release is tested with (.github/nightly/install.sh), so
  each repository moves to that pubrules.

  Background:
    Given a scratch directory
    And the program under test is "pubfleet"

  Scenario: The nightly workflow updates one pull request and merges nothing
    When I parse the workflow "nightly.yml"
    Then it runs by hand and when called, with no schedule of its own
    And neither it nor its script merges a pull request
    And its script updates an open pull request before opening one
    And its script re-tests the pins alone when CI fails

  Scenario: The nightly pushes as its GitHub App, one repository at a time
    When I parse the workflow "nightly.yml"
    Then each repository's token comes from the Sustenaut nightly app, for that repository alone
    And the token may write only contents, pull requests and workflows, and read actions
    And without the app it falls back to PUBRULES_BUMP_TOKEN with a warning

  Scenario: A control plane calls the nightly with a repos input and neutral secrets
    When I parse the workflow "nightly.yml"
    Then it can be called with the input "repos" and the secrets "app-id, app-key, notify-token, notify-user"
    And run by hand it takes the same repos input
    And a repository it can't read for the report doesn't stop the others
    And only what the repos input governs gets a pull request
    And it takes pubfleet's script and wheel from the same latest release, whichever repository calls it
    And the pubrules it installs is the one that release is tested with, unless the pubrules input names one

  Scenario: The nightly takes pubrel's latest release when crates.io has it
    Given a fake "crates" service
    And the "crates" service answers "GET /crates/pubrel/0.6.2" with 200 and:
      """
      {"version": {"num": "0.6.2", "yanked": false}}
      """
    When I ask which pubrel to use for the release "v0.6.2"
    Then it succeeds
    And it prints:
      """
      0.6.2
      """
    And stderr is empty
    And the "crates" service was asked "GET /crates/pubrel/0.6.2" with the header "User-Agent" set to "pubfleet-nightly (https://github.com/Sustenaut/pubfleet)"

  Scenario: A release not yet on crates.io gives way to the newest that is, with a warning
    Given a fake "crates" service
    And the "crates" service answers "GET /crates/pubrel/0.6.2" with 404
    And the "crates" service answers "GET /crates/pubrel" with 200 and:
      """
      {"crate": {"max_stable_version": "0.6.1"}}
      """
    When I ask which pubrel to use for the release "v0.6.2"
    Then it succeeds
    And it prints:
      """
      0.6.1
      """
    And stderr mentions "::warning::"
    And stderr mentions "pubrel 0.6.2 is tagged but not on crates.io"
    And the "crates" service was asked "GET /crates/pubrel/0.6.2" with the header "User-Agent" set to "pubfleet-nightly (https://github.com/Sustenaut/pubfleet)"
    And the "crates" service was asked "GET /crates/pubrel" with the header "User-Agent" set to "pubfleet-nightly (https://github.com/Sustenaut/pubfleet)"

  Scenario: A yanked release gives way too
    Given a fake "crates" service
    And the "crates" service answers "GET /crates/pubrel/0.6.2" with 200 and:
      """
      {"version": {"num": "0.6.2", "yanked": true}}
      """
    And the "crates" service answers "GET /crates/pubrel" with 200 and:
      """
      {"crate": {"max_stable_version": "0.6.1"}}
      """
    When I ask which pubrel to use for the release "v0.6.2"
    Then it succeeds
    And it prints:
      """
      0.6.1
      """
    And stderr mentions "::warning::"
    And stderr mentions "not on crates.io"

  Scenario: Without crates.io it tries the latest release, saying so
    Given a fake "crates" service
    And the "crates" service answers "GET /crates/pubrel/0.6.2" with 503
    And the "crates" service answers "GET /crates/pubrel" with 503
    When I ask which pubrel to use for the release "v0.6.2"
    Then it succeeds
    And it prints:
      """
      0.6.2
      """
    And stderr mentions "::warning::"
    And stderr mentions "crates.io didn't answer"

  Scenario: The nightly asks crates.io before installing pubrel
    When I parse the workflow "nightly.yml"
    Then it chooses pubrel with pubrel-version.sh, and installs that version

  Scenario: The nightly installs the pubrules its pubfleet release's lock pins, by hash
    Given a stand-in "python"
    And a stand-in "pubfleet"
    And a stand-in "pubrules"
    And the environment does not set "PUBRULES_TAG"
    And a file ".github/nightly/install.sh" copied from ".github/nightly/install.sh"
    And the file ".github/nightly/install.sh" is executable
    When I run ".github/nightly/install.sh v0.1.0"
    Then it succeeds
    And "python" was run, in turn, with arguments matching:
      """
      -m pip install --quiet --only-binary :all: --require-hashes -r */scratch/tests/requirements.lock
      -m pip install --quiet --no-deps https://github.com/Sustenaut/pubfleet/releases/download/v0.1.0/pubfleet-0.1.0-py3-none-any.whl
      """
    And it does not print "::warning::"

  Scenario: The pubrules input moves the repositories to that pubrules instead, with a warning
    Given a stand-in "python"
    And a stand-in "pubfleet"
    And a stand-in "pubrules"
    And the environment sets "PUBRULES_TAG" to "v0.33.1"
    And a file ".github/nightly/install.sh" copied from ".github/nightly/install.sh"
    And the file ".github/nightly/install.sh" is executable
    When I run ".github/nightly/install.sh v0.1.0"
    Then it succeeds
    And "python" was run, in turn, with arguments matching:
      """
      -m pip install --quiet --only-binary :all: --require-hashes -r */scratch/tests/requirements.lock
      -m pip install --quiet --no-deps https://github.com/Sustenaut/pubfleet/releases/download/v0.1.0/pubfleet-0.1.0-py3-none-any.whl
      -m pip install --quiet --no-deps https://github.com/Sustenaut/pubrules/releases/download/v0.33.1/pubrules-0.33.1-py3-none-any.whl
      """
    And it prints "::warning::"
    And it prints "governed repositories move to pubrules v0.33.1"

  Scenario: A pubrules input that is not a release tag is refused
    Given a stand-in "python"
    And a stand-in "pubfleet"
    And a stand-in "pubrules"
    And the environment sets "PUBRULES_TAG" to "main"
    And a file ".github/nightly/install.sh" copied from ".github/nightly/install.sh"
    And the file ".github/nightly/install.sh" is executable
    When I run ".github/nightly/install.sh v0.1.0"
    Then it fails
    And stderr mentions "must be a release tag"
    And "python" was run, in turn, with arguments matching:
      """
      -m pip install --quiet --only-binary :all: --require-hashes -r */scratch/tests/requirements.lock
      -m pip install --quiet --no-deps https://github.com/Sustenaut/pubfleet/releases/download/v0.1.0/pubfleet-0.1.0-py3-none-any.whl
      """

  Scenario: The nightly never moves a repository to an older pubrules
    Given a file "pubrules" holding:
      """
      #!/usr/bin/env bash
      # Managed by pubrules 0.35.0: `pubrules sync` rewrites this file
      """
    And a stand-in "pubrules" that prints "pubrules 0.33.0"
    And a file "not-backwards.sh" copied from ".github/nightly/not-backwards.sh"
    And the file "not-backwards.sh" is executable
    When I run "./not-backwards.sh"
    Then the exit code is 1
    And it prints:
      """
      it runs pubrules 0.35.0, newer than tonight's 0.33.0: not moved back
      """

  Scenario Outline: The same or a newer pubrules goes on
    Given a file "pubrules" holding:
      """
      #!/usr/bin/env bash
      # Managed by pubrules <pinned>: `pubrules sync` rewrites this file
      """
    And a stand-in "pubrules" that prints "pubrules <installed>"
    And a file "not-backwards.sh" copied from ".github/nightly/not-backwards.sh"
    And the file "not-backwards.sh" is executable
    When I run "./not-backwards.sh"
    Then it succeeds

    Examples:
      | pinned | installed |
      | 0.33.0 | 0.36.0    |
      | 0.36.0 | 0.36.0    |
      | 0.9.9  | 0.10.0    |

  Scenario: A repository that pins no pubrules goes on
    Given a stand-in "pubrules" that prints "pubrules 0.33.0"
    And a file "not-backwards.sh" copied from ".github/nightly/not-backwards.sh"
    And the file "not-backwards.sh" is executable
    When I run "./not-backwards.sh"
    Then it succeeds

  Scenario: The update script checks before it moves anything
    When I read the nightly's update script
    Then it runs not-backwards.sh before pubrules nightly
