Feature: pubfleet cycles fails on a dependency cycle among the listed repositories
  The graph is read from each repository's pyproject.toml, Cargo.toml, package.json,
  release.json and test requirements, through the board's github connector, so a
  recording replays it. Test-time needs count. The toolchain line pubrules' managed
  requirements file writes into every repository does not, nor do workflow pins.

  Background:
    Given a scratch directory
    And the program under test is "pubfleet"

  Scenario: Two repositories that need each other at test time are a cycle
    Given the repository "example-org/alpha" has "pyproject.toml":
      """
      [project]
      name = "alpha"
      """
    And the repository "example-org/alpha" has "tests/requirements.txt":
      """
      beta==1.2.0
      """
    And the repository "example-org/beta" has "pyproject.toml":
      """
      [project]
      name = "beta"
      dependencies = ["alpha>=0.3"]
      """
    When I check the listed repositories for cycles
    Then it fails
    And it prints "cycle: example-org/alpha -> example-org/beta -> example-org/alpha"
    And it prints "example-org/alpha needs example-org/beta (tests/requirements.txt:1)"
    And it prints "example-org/beta needs example-org/alpha (pyproject.toml:3)"

  Scenario: A cycle through three repositories, by wheel URL, Cargo git URL and package.json
    Given the repository "example-org/alpha" has "tests/requirements-pubrules.txt":
      """
      beta @ https://github.com/example-org/beta/releases/download/v0.1.0/beta-0.1.0-py3-none-any.whl
      """
    And the repository "example-org/beta" has "Cargo.toml":
      """
      [package]
      name = "beta"

      [dev-dependencies]
      gamma-core = { git = "https://github.com/example-org/gamma", tag = "v1.0.0" }
      """
    And the repository "example-org/gamma" has "package.json":
      """
      {"name": "@example-org/gamma", "devDependencies": {"alpha": "github:example-org/alpha#v2.0.0"}}
      """
    When I check the listed repositories for cycles
    Then it fails
    And it prints "cycle: example-org/alpha -> example-org/beta -> example-org/gamma -> example-org/alpha"

  Scenario: The toolchain line of the managed requirements file is not an edge
    Given the repository "example-org/pubrules" has "pyproject.toml":
      """
      [project]
      name = "pubrules"
      """
    And the repository "example-org/pubrules" has "tests/requirements.txt":
      """
      harness==0.4.0
      """
    And the repository "example-org/harness" has "pyproject.toml":
      """
      [project]
      name = "harness"
      """
    And the repository "example-org/harness" has "tests/requirements-pubrules.txt":
      """
      pubrules==0.50.1
      """
    When I check the listed repositories for cycles
    Then it succeeds
    And it prints "No dependency cycle among 2 repositories (1 edges"

  Scenario: A repository that imports pubrules declares it, and that edge counts
    Given the repository "example-org/pubrules" has "pyproject.toml":
      """
      [project]
      name = "pubrules"
      """
    And the repository "example-org/pubrules" has "tests/requirements.txt":
      """
      fleet==0.2.2
      """
    And the repository "example-org/fleet" has "pyproject.toml":
      """
      [project]
      name = "fleet"
      dependencies = ["pubrules>=0.50.1"]
      """
    When I check the listed repositories for cycles
    Then it fails
    And it prints "cycle: example-org/fleet -> example-org/pubrules -> example-org/fleet"

  Scenario: A locked package nothing declared needs is reported, but is no edge
    Given the repository "example-org/alpha" has "pyproject.toml":
      """
      [project]
      name = "alpha"
      """
    And the repository "example-org/alpha" has "tests/requirements.lock":
      """
      pytest==9.0.3 \
          --hash=sha256:00
      some-beta==1.0.0 \
          --hash=sha256:00
      """
    And the repository "example-org/beta" has "release.json":
      """
      {"name": "some_beta"}
      """
    When I check the listed repositories for cycles
    Then it succeeds
    And it prints "undeclared: example-org/alpha: tests/requirements.lock:3 locks some-beta (example-org/beta), which nothing it declares needs"

  Scenario: A repository that can't be read fails the check, saying why
    Given the repository "example-org/alpha" has "pyproject.toml":
      """
      [project]
      name = "alpha"
      """
    And the repository "example-org/hidden" can't be read
    When I check the listed repositories for cycles
    Then it fails
    And it prints "unread: example-org/hidden: pyproject.toml could not be read: Not Found for this token (HTTP 403)"
