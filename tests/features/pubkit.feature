Feature: pubfleet uses pubkit as a library, through the names its README lists
  pubfleet grades against pubkit's standard and calls GitHub as pubkit does,
  so it imports pubkit rather than copying it. pubkit never imports pubfleet,
  and names nothing of it. The names pubfleet takes are listed here, and in
  the README, so a pubkit change that drops one fails this suite first.

  Scenario: pubfleet imports from pubkit only the names its README lists
    When I read every import of pubkit in src/pubfleet
    Then each is one the README lists under "What pubfleet takes from pubkit"
    And the README lists none that pubfleet does not import

  Scenario: Every name pubfleet takes from pubkit is in the pubkit installed
    When I read every import of pubkit in src/pubfleet
    Then the installed pubkit has each of them

  Scenario: pubfleet says its version
    When I run pubfleet "--version"
    Then it succeeds
    And it prints "pubfleet "
