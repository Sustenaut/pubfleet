Feature: The reusable workflows parse as GitHub reads them
  pubfleet's own CI runs neither board.yml nor nightly.yml, so a malformed one
  would first fail in a control plane. Every workflow it ships is parsed here
  instead.

  Scenario Outline: A reusable workflow declares well-formed inputs
    When I parse the workflow "<workflow>"
    Then it is called with workflow_call
    And every input has only a type, a default, a description or required
    And every job the workflow runs uses only its declared inputs

    Examples:
      | workflow    |
      | board.yml   |
      | nightly.yml |

  Scenario: board.yml grades with the caller's token, keeps board.json and deploys nothing
    When I parse the workflow "board.yml"
    Then it takes a required "token" secret and reads the repository's contents only
    And it runs pubfleet board with the token as GITHUB_TOKEN
    And it uploads board.json as the "board" artifact, kept 90 days, and nothing else runs

  Scenario Outline: Every action a workflow uses is pinned to a commit
    When I parse the workflow "<workflow>"
    Then every action it uses is pinned to a full commit hash, with its version in a comment

    Examples:
      | workflow    |
      | board.yml   |
      | nightly.yml |
      | wheel.yml   |
