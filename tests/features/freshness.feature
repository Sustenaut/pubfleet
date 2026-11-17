Feature: pubfleet freshness reports which pubrules each repository pins, and whether it meets the standard
  It reads each checkout and changes nothing. The standard is the installed
  pubrules', the one the nightly moves repositories to.

  Scenario: Repositories pubrules cannot judge say why, as a table and as JSON
    Given the file "a/README.md" reads "no pubrules.json here"
    And the file "b/pubrules.json" reads "{"kind": "utility"}"
    And the file "b/tests/requirements.lock" reads "pubrules @ https://x/download/v0.1.0/pubrules-0.1.0-py3-none-any.whl"
    When I run pubfleet "freshness" "--json" "a" "b"
    Then it succeeds
    And it prints ""conforms": "no pubrules.json""
    And it prints ""conforms": "not Rust""
    And it prints ""pinned": "0.1.0""

  Scenario: A Rust repository is judged by the standard, its own workflow pins aside, with its open exceptions
    Given a Rust checkout whose conform check finds "RS-DOC-01: no README" and ".github/workflows/ci.yml: pins pubrules 0.1.0", with the open exception "RS-SUP-05 until 2027-01-01"
    When its freshness row is read
    Then it conforms "no: 1 problem(s): RS-DOC-01: no README"
    And its exceptions are "RS-SUP-05 until 2027-01-01"

  Scenario: A Rust repository with nothing wrong conforms
    Given a Rust checkout whose conform check finds nothing
    When its freshness row is read
    Then it conforms "yes"

  Scenario: The table goes to the job summary too, when there is one
    Given the file "b/pubrules.json" reads "{"kind": "utility"}"
    And a job summary file
    When I run pubfleet "freshness" "b"
    Then it succeeds
    And the job summary has the table, with "| b | - | **no** | not Rust | - |"
