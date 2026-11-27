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

  Scenario: The shapes pubfleet was tested on are recorded for every name it imports
    When I read every import of pubrules in src/pubfleet
    Then src/pubfleet/pubrules-api.txt records each of them and no other
    And each recorded shape is the installed pubrules.api's

  Scenario: The installed pubrules is the one pubfleet was tested on
    Given a scratch directory
    And the program under test is "pubfleet"
    When I run "pubfleet pubrules-api --check"
    Then it succeeds
    And it prints "api is the one pubfleet was tested on"

  Scenario: A pubrules whose api changed shape, or lost a name, is not the one pubfleet was tested on
    When the installed pubrules.api is compared with a record where "confined" takes other arguments and "gone" is a name
    Then the differences are "confined: tested on function(path) -> 'Path', installed is function(path: 'Path | str', what: 'str', also: 'tuple[Path, ...]' = ()) -> 'Path'" and "gone: pubrules.api has no such name"
