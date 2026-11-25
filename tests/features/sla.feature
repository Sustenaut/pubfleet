Feature: The SLA block of a state file: tiers once, each service's, and what pubfleet derives
  Tiers are org configuration, named by the owner and defined once; each service of
  the state names the tier of each of its senders and of its address. pubfleet owns
  the block: it checks its shape, reads an older version through its transformers,
  and derives the senders' settings, the uptime checks, the GitHub variables and the
  budget against Cloud Monitoring's free tiers. The sound block has a tight tier
  (30 s deadline, 60 s heartbeat, 2 misses, uptime in 10 minutes), an idle one (8 h,
  1 h, 3 misses) and an on-demand one (no heartbeat); service one has a tight app, an
  idle job and a tight address, and two an on-demand plan.

  Background:
    Given a scratch directory
    And the program under test is "pubfleet"

  # --- Its shape ---------------------------------------------------------------------

  Scenario: A sound block has no problems
    Given a sound SLA block
    When pubfleet checks the SLA block
    Then the result is "[]"

  Scenario: A tier may be any name, and a service no sender
    Given the SLA block '{"version": 1, "tiers": {"gold-2": {"deadline_seconds": 5, "uptime_minutes": 2}}, "services": {"site": {"senders": {}, "uptime": "gold-2"}}}'
    When pubfleet checks the SLA block
    Then the result is "[]"

  Scenario: A block with no services yet is sound
    Given the SLA block '{"version": 1, "tiers": {"t": {"deadline_seconds": 30}}}'
    When pubfleet checks the SLA block
    Then the result is "[]"

  Scenario Outline: A block of the wrong shape: <fault>
    Given the SLA block '<block>'
    When pubfleet checks the SLA block
    Then one problem is "<problem>"

    Examples:
      | fault             | block                                                              | problem                                         |
      | not an object     | ["tight"]                                                          | it must be an object                            |
      | no version        | {"tiers": {"t": {"deadline_seconds": 1}}}                          | its version must be 1, not null                 |
      | another version   | {"version": 2, "tiers": {"t": {"deadline_seconds": 1}}}            | its version must be 1, not 2                    |
      | a boolean version | {"version": true, "tiers": {"t": {"deadline_seconds": 1}}}         | its version must be 1, not true                 |
      | no tiers          | {"version": 1, "services": {}}                                     | "tiers" must define at least one tier           |
      | services a list   | {"version": 1, "tiers": {"t": {"deadline_seconds": 1}}, "services": []} | "services" must be an object               |
      | another setting   | {"version": 1, "tiers": {"t": {"deadline_seconds": 1}}, "other": 1} | other is not a setting; it takes version, tiers and services |

  Scenario Outline: A tier of the wrong shape: <fault>
    Given a sound SLA block
    And its tier '<name>' is '<tier>'
    When pubfleet checks the SLA block
    Then one problem is "<problem>"

    Examples:
      | fault                   | name  | tier                                                       | problem                                                   |
      | a name in capitals      | Tight | {"deadline_seconds": 30}                                   | "Tight" is not a tier's name                              |
      | not an object           | t     | 30                                                         | the tier t must be an object                              |
      | no deadline             | t     | {"heartbeat_seconds": 60}                                  | the tier t needs deadline_seconds                         |
      | a deadline of 0         | t     | {"deadline_seconds": 0}                                    | the tier t's deadline_seconds must be a number above 0, not 0 |
      | a heartbeat as a string | t     | {"deadline_seconds": 30, "heartbeat_seconds": "60"}        | the tier t's heartbeat_seconds must be a number above 0, not "60" |
      | uptime as a boolean     | t     | {"deadline_seconds": 30, "uptime_minutes": true}           | the tier t's uptime_minutes must be a number above 0, not true |
      | one miss                | t     | {"deadline_seconds": 30, "heartbeat_seconds": 60, "misses": 1} | misses must be a whole number, at least 2: one miss is a blip |
      | misses not whole        | t     | {"deadline_seconds": 30, "heartbeat_seconds": 60, "misses": 2.5} | misses must be a whole number, at least 2             |
      | misses, no heartbeat    | t     | {"deadline_seconds": 30, "misses": 2}                      | the tier t has misses but no heartbeat_seconds to miss    |
      | another setting         | t     | {"deadline_seconds": 30, "window": 5}                      | the tier t: window is not a setting                       |

  Scenario Outline: A service of the wrong shape: <fault>
    Given a sound SLA block
    And its service '<name>' is '<service>'
    When pubfleet checks the SLA block
    Then one problem is "<problem>"

    Examples:
      | fault                        | name  | service                                                        | problem                                                          |
      | not a repository's name      | a/b   | {"senders": {}}                                                | "a/b" is not a repository's name                                 |
      | not an object                | s     | "tight"                                                        | the service s must be an object                                  |
      | no senders                   | s     | {"uptime": "tight"}                                            | the service s's senders must be an object                        |
      | a sender's name in capitals  | s     | {"senders": {"App": "tight"}}                                  | "App" is not a sender's name                                     |
      | a sender's tier not defined  | s     | {"senders": {"app": "gold"}}                                   | the service s's sender app has the tier "gold", which the tiers don't define |
      | an uptime tier not defined   | s     | {"senders": {}, "uptime": "gold"}                              | the service s's uptime is the tier "gold", which the tiers don't define |
      | an uptime tier with no check | s     | {"senders": {}, "uptime": "idle"}                              | the service s's uptime is the tier idle, which has no uptime_minutes |
      | an address with no uptime    | s     | {"senders": {}, "address": "https://s.example.eu"}             | the service s has an address but no uptime tier to check it by   |
      | an address over http         | s     | {"senders": {}, "uptime": "tight", "address": "http://s.example.eu"} | the service s's address must be an https URL                 |
      | another setting              | s     | {"senders": {}, "replicas": 2}                                 | the service s: replicas is not a setting                         |

  Scenario Outline: A version pubfleet doesn't know is refused before its shape is read
    Given the SLA block '<block>'
    When pubfleet reads it
    Then it is refused, saying "<message>"

    Examples:
      | block                                | message                           |
      | {"version": 0, "tiers": {}}          | its version must be one of 1, not 0 |
      | {"version": 2, "tiers": {}}          | its version must be one of 1, not 2 |
      | {"version": "1", "tiers": {}}        | its version must be one of 1, not "1" |
      | ["tight"]                            | it must be an object              |

  # --- What it derives ---------------------------------------------------------------

  Scenario: A sender with a heartbeat waits misses heartbeats and the margin before its alarm
    Given a sound SLA block
    When pubfleet derives from it, offline
    Then the sender "one/app" is:
      """
      {"service": "one", "sender": "app", "tier": "tight", "deadline_seconds": 30, "heartbeat_seconds": 60,
       "misses": 2, "absence_seconds": 300, "replicas": 1}
      """
    And the sender "one/job" is:
      """
      {"service": "one", "sender": "job", "tier": "idle", "deadline_seconds": 28800, "heartbeat_seconds": 3600,
       "misses": 3, "absence_seconds": 10980, "replicas": 1}
      """

  Scenario: A sender of a tier with no heartbeat has no alarm
    Given a sound SLA block
    When pubfleet derives from it, offline
    Then the sender "two/plan" is:
      """
      {"service": "two", "sender": "plan", "tier": "on-demand", "deadline_seconds": 120, "heartbeat_seconds": null,
       "misses": null, "absence_seconds": null, "replicas": 1}
      """

  Scenario: A tier's heartbeat with no misses misses two
    Given a sound SLA block
    And its tier 'idle' is '{"deadline_seconds": 600, "heartbeat_seconds": 900}'
    When pubfleet derives from it, offline
    Then the result's "senders.1.misses" is "2"
    And the result's "senders.1.absence_seconds" is "1980"

  Scenario: An uptime check runs at half the tier's minutes, from three regions, alarming on two of them twice
    Given a sound SLA block
    When pubfleet derives from it, offline
    Then the uptime check of "one" is:
      """
      {"service": "one", "tier": "tight", "address": "https://one.example.eu/healthz", "detection_seconds": 600,
       "period_seconds": 300, "regions": ["EUROPE", "USA_VIRGINIA", "ASIA_PACIFIC"], "failing_regions": 2,
       "consecutive": 2}
      """

  Scenario Outline: The period is the longest Cloud Monitoring runs at that is at most half the tier's minutes
    Given a sound SLA block
    And its tier 'tight' is '{"deadline_seconds": 30, "uptime_minutes": <minutes>}'
    When pubfleet reads its numbers
    Then the result's "uptime.0.period_seconds" is "<period>"

    Examples:
      | minutes | period |
      | 2       | 60     |
      | 9       | 60     |
      | 10      | 300    |
      | 25      | 600    |
      | 60      | 900    |

  Scenario: A tier asking for an address to be found sooner than a check can run is refused
    Given a sound SLA block
    And its tier 'tight' is '{"deadline_seconds": 30, "uptime_minutes": 1.5}'
    When pubfleet reads its numbers
    Then it is refused, saying "one's uptime tier tight asks for 1.5 minutes, and the shortest check period, 1 minute, is more than half that"

  Scenario Outline: An absence Cloud Monitoring can't wait for is refused: <case>
    Given a sound SLA block
    And its tier 'idle' is '<tier>'
    When pubfleet reads its numbers
    Then it is refused, saying "one/job's absence alert would wait"

    Examples:
      | case      | tier                                                                   |
      | too long  | {"deadline_seconds": 60, "heartbeat_seconds": 43200, "misses": 2}      |

  Scenario: The variables: each service's tightest deadline, and observability's senders; never a file heartbeat
    Given a sound SLA block
    When pubfleet derives from it, offline
    Then the derived variables are:
      """
      {"one": {"CALL_LOG_DEADLINE_SECONDS": "30", "CALL_LOG_METRIC_SECONDS": "60"},
       "two": {"CALL_LOG_DEADLINE_SECONDS": "120"},
       "observability": {"OBSERVABILITY_SENDERS": {"one": {"app": "tight", "job": "idle"}, "two": {"plan": "on-demand"}}}}
      """

  Scenario: A service's name in observability's senders has _ for -
    Given a sound SLA block
    And its service 'release-controlplane' is '{"senders": {"app": "tight"}}'
    When pubfleet derives from it, offline
    Then the result's "variables.observability.OBSERVABILITY_SENDERS.release_controlplane.app" is "tight"

  Scenario: Offline, an uptime service needs an address
    Given a sound SLA block
    And its service 'one' has no address
    When pubfleet derives from it, offline
    Then it is refused, saying "one has an uptime tier and no address, which offline can't look up"

  Scenario: An uptime service with no address is checked at its deploy's host
    Given a sound SLA block
    And its service 'one' has no address
    And the state file holds it
    And "example-org/one" deploys to the host "one.example.eu"
    When I run "pubfleet sla --derive"
    Then it succeeds
    And the JSON it prints has "uptime.0.address" equal to "https://one.example.eu/"

  Scenario: A service with no address and no deploy host is refused
    Given a sound SLA block
    And its service 'one' has no address
    And the state file holds it
    And "example-org/one" has the pubrules.json "{"kind": "service"}"
    When I run "pubfleet sla --derive"
    Then the exit code is 1
    And stderr mentions "its pubrules.json's deploy block names no host: give it an address"

  Scenario: --derive prints the whole, offline when every uptime service has an address
    Given a sound SLA block
    And the state file holds it
    When I run "pubfleet sla --derive --offline"
    Then it succeeds
    And the JSON it prints has "version" equal to "1"
    And the JSON it prints has "budget.within" equal to "true"
    And the JSON it prints has "senders.0.absence_seconds" equal to "300"

  # --- The budget --------------------------------------------------------------------

  Scenario: The budget counts each region's run and each replica's points, against the free tiers
    Given a sound SLA block
    When pubfleet counts its budget, with {"one/app": 3}
    Then the result is:
      """
      {"uptime_executions": 25920, "uptime_executions_free": 1000000,
       "metric_bytes": 1042560, "metric_bytes_free": 157286400, "within": true}
      """

  Scenario: Uptime checks past a million runs a month are refused
    Given a sound SLA block
    And its tier 'tight' is '{"deadline_seconds": 30, "uptime_minutes": 2}'
    And its 7 services 'site' each have their address checked by 'tight'
    And the state file holds it
    When I run "pubfleet sla --budget"
    Then the exit code is 1
    And stderr mentions "its uptime checks would run 1,036,800 times a month, past the free 1,000,000"

  Scenario: Heartbeats past 150 MiB a month are refused
    Given a sound SLA block
    And its tier 'tight' is '{"deadline_seconds": 30, "heartbeat_seconds": 1, "uptime_minutes": 10}'
    And the state file holds it
    When I run "pubfleet sla --budget --replicas one/app=8"
    Then the exit code is 1
    And stderr mentions "past the free 150 MiB"

  Scenario: A malformed --replicas is refused
    Given a sound SLA block
    And the state file holds it
    When I run "pubfleet sla --budget --replicas one=2"
    Then the exit code is 1
    And stderr mentions "--replicas takes SERVICE/SENDER=N, not one=2"

  Scenario: A state file with no SLA block has nothing to derive
    Given a state file with no SLA block
    When I run "pubfleet sla --derive --offline"
    Then the exit code is 1
    And stderr mentions "has no SLA block"

  # --- The state check ---------------------------------------------------------------

  Scenario: The state check takes a sound SLA block
    Given a sound SLA block
    And the state file holds it
    When pubfleet checks the state's shape
    Then the result is "[]"

  Scenario: The state check refuses a block naming a service the state doesn't list
    Given a sound SLA block
    And the state file holds it, without the repository "two"
    When pubfleet checks the state's shape
    Then one problem is "its SLA block names the service two, which the state doesn't list"

  Scenario: The state check refuses a block of the wrong shape
    Given a sound SLA block
    And its tier 'tight' is '{"deadline_seconds": 30, "heartbeat_seconds": 60, "misses": 1}'
    And the state file holds it
    When pubfleet checks the state's shape
    Then one problem is "its SLA block: the tier tight's misses must be a whole number"

  Scenario: The state check refuses a variable the SLA block derives, set beside it
    Given a sound SLA block
    And the state file holds it, and gives "one" the variables '{"CALL_LOG_DEADLINE_SECONDS": "15", "OTHER": "x"}'
    When pubfleet checks the state's shape
    Then one problem is "one: its variables give CALL_LOG_DEADLINE_SECONDS, which the SLA block sets: drop them here"

  Scenario: The state check refuses a block past a free tier
    Given a sound SLA block
    And its tier 'tight' is '{"deadline_seconds": 30, "heartbeat_seconds": 1, "uptime_minutes": 10}'
    And its service 'two' is '{"senders": {"a": "tight", "b": "tight", "c": "tight", "d": "tight", "e": "tight", "f": "tight", "g": "tight"}}'
    And the state file holds it
    When pubfleet checks the state's shape
    Then one problem is "past the free 150 MiB"

  # --- The variables it gives --------------------------------------------------------

  Scenario: --apply sets the variables the SLA block derives, beside the state's own
    Given a sound SLA block
    And the state file holds it, and gives "one" the variables '{"OTHER": "x"}'
    And "example-org/one" declares the variables ["OTHER", "CALL_LOG_DEADLINE_SECONDS", "CALL_LOG_METRIC_SECONDS"]
    And "example-org/two" declares the variables ["CALL_LOG_DEADLINE_SECONDS"]
    And "example-org/observability" declares the variables ["OBSERVABILITY_SENDERS"]
    When I run "pubfleet variables --apply"
    Then it succeeds
    And GitHub holds "CALL_LOG_DEADLINE_SECONDS" in "example-org/one" as "30" now
    And GitHub holds "CALL_LOG_METRIC_SECONDS" in "example-org/one" as "60" now
    And GitHub holds "OTHER" in "example-org/one" as "x" now
    And GitHub holds "CALL_LOG_DEADLINE_SECONDS" in "example-org/two" as "120" now
    And GitHub holds "OBSERVABILITY_SENDERS" in "example-org/observability" as "{"one":{"app":"tight","job":"idle"},"two":{"plan":"on-demand"}}" now

  Scenario: A derived variable a repository doesn't declare yet is left alone, and fails nothing
    Given a sound SLA block
    And the state file holds it, and gives "one" the variables '{"OTHER": "x"}'
    And "example-org/one" declares the variables ["OTHER"]
    And "example-org/two" has the pubrules.json "{"kind": "service"}"
    And "example-org/observability" declares the variables ["OBSERVABILITY_SENDERS"]
    When I run "pubfleet variables --apply"
    Then it succeeds
    And it prints "example-org/one: the SLA block gives it CALL_LOG_DEADLINE_SECONDS, CALL_LOG_METRIC_SECONDS, which its pubrules.json doesn't declare yet, so they are left alone"
    And it prints "example-org/two: the SLA block gives it CALL_LOG_DEADLINE_SECONDS, which it doesn't declare yet, so they are left alone"
    And GitHub holds "OTHER" in "example-org/one" as "x" now

  Scenario: --check names the derived variables that differ
    Given a sound SLA block
    And the state file holds it
    And "example-org/one" declares the variables ["CALL_LOG_DEADLINE_SECONDS"]
    And "example-org/two" declares the variables ["CALL_LOG_DEADLINE_SECONDS"]
    And "example-org/observability" declares the variables ["OBSERVABILITY_SENDERS"]
    And GitHub holds "CALL_LOG_DEADLINE_SECONDS" in "example-org/one" as "60"
    When I run "pubfleet variables --check one"
    Then it fails
    And it prints "CALL_LOG_DEADLINE_SECONDS:"

  Scenario: A file heartbeat the state gives a service stays the state's, beside the derived deadline
    Given a sound SLA block
    And the state file holds it, and gives "one" the variables '{"CALL_LOG_HEARTBEAT_SECONDS": "300"}'
    When pubfleet checks the state's shape
    Then the result is "[]"

  Scenario: A pubrules.json that can't be read fails, and says so, not that it doesn't declare them
    Given a sound SLA block
    And the state file holds it
    And "example-org/two" declares the variables ["CALL_LOG_DEADLINE_SECONDS"]
    And "example-org/observability" declares the variables ["OBSERVABILITY_SENDERS"]
    When I run "pubfleet variables --apply one"
    Then the exit code is 1
    And it prints "example-org/one: its pubrules.json can't be read for its variables, so none is set"
    And it does not print "doesn't declare yet"

  Scenario: A service's heartbeat metric beats at the tightest heartbeat of its senders
    Given a sound SLA block
    And its service 'two' is '{"senders": {"a": "idle", "b": "tight", "c": "on-demand"}}'
    When pubfleet derives from it, offline
    Then the result's "variables.two.CALL_LOG_METRIC_SECONDS" is "60"

  Scenario: A service with no sender that has a heartbeat gets no metric interval
    Given a sound SLA block
    When pubfleet derives from it, offline
    Then the result's "variables.two" is "{"CALL_LOG_DEADLINE_SECONDS": "120"}"
