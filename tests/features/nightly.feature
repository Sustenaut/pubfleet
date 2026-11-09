Feature: The nightly keeps every governed repository current, through a pull request
  nightly.yml checks out each repository the repos input governs and runs
  `pubkit nightly` there (.github/nightly/update.sh), which commits the moved
  pins and the updates and writes the pull request's body. The workflow keeps
  one pull request per repository and never merges it. It installs the pubkit
  the latest pubfleet release is tested with (.github/nightly/install.sh), so
  each repository moves to that pubkit.

  Background:
    Given an empty repository

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
    And without the app it falls back to PUBKIT_BUMP_TOKEN with a warning

  Scenario: A control plane calls the nightly with a repos input and neutral secrets
    When I parse the workflow "nightly.yml"
    Then it can be called with the input "repos" and the secrets "app-id, app-key, notify-token, notify-user"
    And run by hand it takes the same repos input
    And a repository it can't read for the report doesn't stop the others
    And only what the repos input governs gets a pull request
    And it takes pubfleet's script and wheel from the same latest release, whichever repository calls it
    And the pubkit it installs is the one that release is tested with, unless the pubkit input names one

  Scenario: The nightly takes pubrel's latest release when crates.io has it
    Given crates.io has pubrel "0.6.1, 0.6.2"
    When I ask which pubrel to use for the release "v0.6.2"
    Then it says "0.6.2", with no warning

  Scenario: A release not yet on crates.io gives way to the newest that is, with a warning
    Given crates.io has pubrel "0.6.0, 0.6.1"
    When I ask which pubrel to use for the release "v0.6.2"
    Then it says "0.6.1", warning "pubrel 0.6.2 is tagged but not on crates.io"

  Scenario: A yanked release gives way too
    Given crates.io has pubrel "0.6.1, 0.6.2", with "0.6.2" yanked
    When I ask which pubrel to use for the release "v0.6.2"
    Then it says "0.6.1", warning "not on crates.io"

  Scenario: Without crates.io it tries the latest release, saying so
    Given crates.io doesn't answer
    When I ask which pubrel to use for the release "v0.6.2"
    Then it says "0.6.2", warning "crates.io didn't answer"

  Scenario: The nightly asks crates.io before installing pubrel
    When I parse the workflow "nightly.yml"
    Then it chooses pubrel with pubrel-version.sh, and installs that version

  Scenario: The nightly installs the pubkit its pubfleet release's lock pins, by hash
    When the nightly installs pubfleet "v0.1.0"
    Then it installs the lock "tests/requirements.lock" with --require-hashes, wheels only
    And it installs pubfleet's wheel "v0.1.0/pubfleet-0.1.0-py3-none-any.whl" without dependencies
    And it installs no other pubkit

  Scenario: The pubkit input moves the repositories to that pubkit instead, with a warning
    When the nightly installs pubfleet "v0.1.0" with the pubkit input "v0.33.1"
    Then it installs pubkit's wheel "v0.33.1/pubkit-0.33.1-py3-none-any.whl" after the lock
    And the install warns "governed repositories move to pubkit v0.33.1"

  Scenario: A pubkit input that is not a release tag is refused
    When the nightly installs pubfleet "v0.1.0" with the pubkit input "main"
    Then the install fails, saying "must be a release tag"
