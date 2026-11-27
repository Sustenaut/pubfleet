Feature: pubfleet uses pubrules as a library, through pubrules.api only
  pubfleet grades against pubrules' standard and calls GitHub as pubrules does,
  so it imports pubrules rather than copying it. pubrules never imports pubfleet,
  and names nothing of it. pubfleet imports only from pubrules.api, the surface
  pubrules holds steady, and its README lists the names it takes, so a pubrules
  change that drops one fails this suite first.

  Scenario: pubfleet imports from pubrules only pubrules.api
    When I read every import of pubrules in src/pubfleet
    Then each is from pubrules.api

  Scenario: pubfleet imports from pubrules only the names its README lists
    When I read every import of pubrules in src/pubfleet
    Then each is one the README lists under "What pubfleet takes from pubrules"
    And the README lists none that pubfleet does not import

  Scenario: Every name pubfleet takes from pubrules is in the pubrules installed
    When I read every import of pubrules in src/pubfleet
    Then the installed pubrules.api exports each of them

  Scenario: pubfleet says its version
    Given a scratch directory
    And the program under test is "pubfleet"
    When I run "pubfleet --version"
    Then it succeeds
    And it prints "pubfleet "
