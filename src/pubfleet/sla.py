"""The SLA block of a state file, and what pubfleet derives from it.

    pubfleet sla --derive [--state FILE] [--replicas SERVICE/SENDER=N ...] [--offline]
    pubfleet sla --budget [--state FILE] [--replicas SERVICE/SENDER=N ...]

The block holds the owner's tiers, once, and each service's tiers for its senders
and its address (block_problems, below, says what version 1 takes). pubfleet owns
it, and this is its one schema: a block of an older version is read through the
transformers (TRANSFORMS, one a version, chained to VERSION), checked, and from it
pubfleet derives:

- each sender's settings: its `deadline_seconds`, and, with a heartbeat, the window
  its absence alert waits, `misses` heartbeats and MARGIN_SECONDS;
- each address's uptime check: run every `period_seconds`, the longest period Cloud
  Monitoring offers that is at most half the tier's `uptime_minutes`, from REGIONS,
  alarming once FAILING_REGIONS of them fail CONSECUTIVE runs in a row, so a down
  address is found within the tier's minutes and one region's or one run's blip is not;
- the GitHub variables each service's repository is given: CALL_LOG_DEADLINE_SECONDS,
  and while observability judges silence (the transition), its OBSERVABILITY_SENDERS. A
  repository's variable holds one number, so it is the tightest of its senders': a sender
  sending sooner than its tier asks costs a little, and never misses its deadline. A
  tier's heartbeat_seconds is its Cloud Monitoring metric's, never the call log's file
  heartbeat (CALL_LOG_HEARTBEAT_SECONDS, a file in storage each time), which stays a
  plain variable of the state while there is one;
- the budget: uptime executions a month (each region's run is one) and the
  heartbeats' metric bytes (BYTES_PER_POINT a point, each replica its own), against
  Cloud Monitoring's free tiers. A block past either is refused.

`--derive` prints it all as JSON, for shared-infra's Terraform variable. An uptime
check's address is the service's `address`, or https:// and its deploy's host (its
pubrules.json, read through `gh`); `--offline` reads nothing, and refuses a service
with neither. `--budget` prints the budget alone, and fails past a free tier.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Callable

from pubrules.protect import Api, gh, remote_config

BLOCK = "SLA"
TIER = re.compile(r"[a-z][a-z0-9-]{0,39}")
SERVICE = re.compile(r"[A-Za-z0-9_.-]+")
SENDER = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
ADDRESS = re.compile(r"https://[A-Za-z0-9.-]+(?::\d+)?(?:/[^\s]*)?")
TIER_KEYS = ("deadline_seconds", "heartbeat_seconds", "misses", "uptime_minutes")
SERVICE_KEYS = ("senders", "uptime", "address")
MIN_MISSES = 2


def _number(value: Any) -> bool:
    """A count of seconds or minutes: finite, above 0, and no boolean."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def _tier_problems(name: str, tier: Any) -> list[str]:
    if not TIER.fullmatch(name):
        return [f"{json.dumps(name)} is not a tier's name: lower case letters, digits and -, starting with a letter"]
    if not isinstance(tier, dict):
        return [f"the tier {name} must be an object of {', '.join(TIER_KEYS)}"]
    out = [f"the tier {name}: {key} is not a setting; it takes {', '.join(TIER_KEYS)}"
           for key in sorted(tier.keys() - set(TIER_KEYS))]
    if "deadline_seconds" not in tier:
        out.append(f"the tier {name} needs deadline_seconds")
    for key in ("deadline_seconds", "heartbeat_seconds", "uptime_minutes"):
        if key in tier and not _number(tier[key]):
            out.append(f"the tier {name}'s {key} must be a number above 0, not {json.dumps(tier[key])}")
    if "misses" in tier:
        misses = tier["misses"]
        if "heartbeat_seconds" not in tier:
            out.append(f"the tier {name} has misses but no heartbeat_seconds to miss")
        elif not isinstance(misses, int) or isinstance(misses, bool) or misses < MIN_MISSES:
            out.append(f"the tier {name}'s misses must be a whole number, at least {MIN_MISSES}: "
                       f"one miss is a blip, not {json.dumps(misses)}")
    return out


def _service_problems(name: str, service: Any, tiers: dict) -> list[str]:
    if not SERVICE.fullmatch(name):
        return [f"{json.dumps(name)} is not a repository's name"]
    if not isinstance(service, dict):
        return [f"the service {name} must be an object of {', '.join(SERVICE_KEYS)}"]
    out = [f"the service {name}: {key} is not a setting; it takes {', '.join(SERVICE_KEYS)}"
           for key in sorted(service.keys() - set(SERVICE_KEYS))]
    senders = service.get("senders")
    if not isinstance(senders, dict):
        out.append(f"the service {name}'s senders must be an object, from each sender to its tier")
    else:
        for sender, tier in senders.items():
            if not SENDER.fullmatch(sender):
                out.append(f"the service {name}: {json.dumps(sender)} is not a sender's name: lower case "
                           f"letters, digits and -")
            elif tier not in tiers:
                out.append(f"the service {name}'s sender {sender} has the tier {json.dumps(tier)}, "
                           f"which the tiers don't define")
    if "uptime" in service:
        tier = service["uptime"]
        if tier not in tiers:
            out.append(f"the service {name}'s uptime is the tier {json.dumps(tier)}, which the tiers don't define")
        elif not isinstance(tiers[tier], dict) or "uptime_minutes" not in tiers[tier]:
            out.append(f"the service {name}'s uptime is the tier {tier}, which has no uptime_minutes")
    if "address" in service:
        if "uptime" not in service:
            out.append(f"the service {name} has an address but no uptime tier to check it by")
        if not isinstance(service["address"], str) or not ADDRESS.fullmatch(service["address"]):
            out.append(f"the service {name}'s address must be an https URL, not {json.dumps(service['address'])}")
    return out


def block_problems(block: Any) -> list[str]:
    """What is wrong with a state file's SLA block, version 1's shape: one phrase each."""
    if not isinstance(block, dict):
        return ["it must be an object, with version, tiers and services"]
    out = [f"{key} is not a setting; it takes version, tiers and services"
           for key in sorted(block.keys() - {"version", "tiers", "services"})]
    if block.get("version") != VERSION or isinstance(block.get("version"), bool):
        out.append(f"its version must be {VERSION}, not {json.dumps(block.get('version'))}")
    tiers = block.get("tiers")
    if not isinstance(tiers, dict) or not tiers:
        out.append('"tiers" must define at least one tier, from its name to its numbers')
        tiers = {}
    else:
        for name, tier in tiers.items():
            out += _tier_problems(name, tier)
    services = block.get("services", {})
    if not isinstance(services, dict):
        out.append('"services" must be an object, from each repository to its senders')
    else:
        for name, service in services.items():
            out += _service_problems(name, service, tiers)
    return out


VERSION = 1
# Each version's step to the next, so a block of any version is read as VERSION's.
TRANSFORMS: dict[int, Callable[[dict], dict]] = {}
# Past `misses` heartbeats, how long an absence alert waits more: a point's way into
# Cloud Monitoring and the alert's own evaluation.
MARGIN_SECONDS = 180
# Cloud Monitoring's absence alerts wait at least two minutes, and at most a day.
ABSENCE_LIMITS = (120, 86400)
# The periods Cloud Monitoring runs an uptime check at, in minutes.
PERIODS_MINUTES = (1, 5, 10, 15)
# Where each check runs from: three, the fewest Cloud Monitoring takes.
REGIONS = ("EUROPE", "USA_VIRGINIA", "ASIA_PACIFIC")
FAILING_REGIONS = 2
CONSECUTIVE = 2
BYTES_PER_POINT = 8
MONTH_SECONDS = 30 * 86400
FREE_EXECUTIONS = 1_000_000
FREE_BYTES = 150 * 1024 * 1024
# The repository whose variable lists every sender, while observability still judges silence.
OBSERVABILITY = "observability"


class SlaError(ValueError):
    pass


def upgrade(block: Any) -> dict:
    """The block at VERSION, through each version's transformer in turn."""
    if not isinstance(block, dict):
        raise SlaError("it must be an object, with version, tiers and services")
    version = block.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or not 1 <= version <= VERSION:
        raise SlaError(f"its version must be one of {', '.join(map(str, range(1, VERSION + 1)))}, "
                       f"not {json.dumps(version)}")
    while block["version"] < VERSION:
        block = TRANSFORMS[block["version"]](block)
    return block


def read(block: Any) -> dict:
    """A block, upgraded and checked; SlaError says what is wrong with it."""
    block = upgrade(block)
    if bad := block_problems(block):
        raise SlaError("; ".join(bad))
    return block


def period(detection_seconds: float) -> int | None:
    """The longest uptime check period, in seconds, at most half `detection_seconds`."""
    fits = [m * 60 for m in PERIODS_MINUTES if m * 60 <= detection_seconds / 2]
    return max(fits) if fits else None


def numbers(block: dict, replicas: dict[str, int] | None = None) -> dict:
    """The senders' settings and the uptime checks' timing, from a checked block."""
    tiers, out = block["tiers"], {"senders": [], "uptime": []}
    problems = []
    for service, given in block.get("services", {}).items():
        for sender, name in given["senders"].items():
            tier = tiers[name]
            row = {"service": service, "sender": sender, "tier": name,
                   "deadline_seconds": tier["deadline_seconds"], "heartbeat_seconds": None,
                   "misses": None, "absence_seconds": None,
                   "replicas": (replicas or {}).get(f"{service}/{sender}", 1)}
            if "heartbeat_seconds" in tier:
                misses = tier.get("misses", 2)
                absence = misses * tier["heartbeat_seconds"] + MARGIN_SECONDS
                low, high = ABSENCE_LIMITS
                if not low <= absence <= high:
                    problems.append(f"{service}/{sender}'s absence alert would wait {absence:g} s, which "
                                    f"Cloud Monitoring doesn't take ({low} to {high} s): the tier {name}'s "
                                    f"misses × heartbeat_seconds + {MARGIN_SECONDS}")
                row.update(heartbeat_seconds=tier["heartbeat_seconds"], misses=misses, absence_seconds=absence)
            out["senders"].append(row)
        if "uptime" in given:
            name = given["uptime"]
            detection = tiers[name]["uptime_minutes"] * 60
            every = period(detection)
            if every is None:
                problems.append(f"{service}'s uptime tier {name} asks for {detection / 60:g} minutes, and "
                                f"the shortest check period, {PERIODS_MINUTES[0]} minute, is more than half that")
                continue
            out["uptime"].append({"service": service, "tier": name, "address": given.get("address"),
                                  "detection_seconds": detection, "period_seconds": every,
                                  "regions": list(REGIONS), "failing_regions": FAILING_REGIONS,
                                  "consecutive": CONSECUTIVE})
    if problems:
        raise SlaError("; ".join(problems))
    return out


def budget(derived: dict) -> dict:
    """What the checks and the heartbeats spend a month, against the free tiers."""
    executions = sum(math.ceil(MONTH_SECONDS / u["period_seconds"]) * len(u["regions"]) for u in derived["uptime"])
    points = sum(math.ceil(MONTH_SECONDS / s["heartbeat_seconds"]) * s["replicas"]
                 for s in derived["senders"] if s["heartbeat_seconds"])
    used = {"uptime_executions": executions, "uptime_executions_free": FREE_EXECUTIONS,
            "metric_bytes": points * BYTES_PER_POINT, "metric_bytes_free": FREE_BYTES}
    used["within"] = executions <= FREE_EXECUTIONS and used["metric_bytes"] <= FREE_BYTES
    return used


def over(used: dict) -> list[str]:
    """The free tiers the budget goes past, one phrase each."""
    out = []
    if used["uptime_executions"] > used["uptime_executions_free"]:
        out.append(f"its uptime checks would run {used['uptime_executions']:,} times a month, past the free "
                   f"{used['uptime_executions_free']:,}: give a tier more uptime_minutes, or fewer services one")
    if used["metric_bytes"] > used["metric_bytes_free"]:
        out.append(f"its heartbeats would send {used['metric_bytes'] / 1048576:.1f} MiB a month, past the free "
                   f"{used['metric_bytes_free'] / 1048576:.0f} MiB: give a tier a longer heartbeat_seconds")
    return out


def variables(block: dict, derived: dict) -> dict[str, dict[str, Any]]:
    """The GitHub variables each repository is given from the block."""
    out: dict[str, dict[str, Any]] = {}
    for service in block.get("services", {}):
        own = [s for s in derived["senders"] if s["service"] == service]
        if not own:
            continue
        values = out.setdefault(service, {})
        values["CALL_LOG_DEADLINE_SECONDS"] = _seconds(min(s["deadline_seconds"] for s in own))
    senders: dict[str, dict[str, str]] = {}
    for s in derived["senders"]:
        senders.setdefault(s["service"].replace("-", "_"), {})[s["sender"]] = (
            s["tier"] if s["heartbeat_seconds"] else "on-demand")
    if senders:
        out.setdefault(OBSERVABILITY, {})["OBSERVABILITY_SENDERS"] = senders
    return out


def _seconds(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else repr(float(value))


def address_of(api: Api, owner: str, service: str) -> str:
    """https:// and the service's deploy host, from its pubrules.json."""
    try:
        config = remote_config(api, f"{owner}/{service}")
    except ValueError as e:
        raise SlaError(f"{service} has an uptime tier and no address, and {e}") from None
    host = (config.get("deploy") or {}).get("host") if isinstance(config, dict) else None
    if not isinstance(host, str) or not host:
        raise SlaError(f"{service} has an uptime tier and no address, and its pubrules.json's deploy "
                       f"block names no host: give it an address")
    return f"https://{host}/"


def derive(state: dict, replicas: dict[str, int] | None = None, api: Api | None = gh) -> dict:
    """Everything the block gives: the senders, the uptime checks with their addresses,
    the variables and the budget. With no `api`, every uptime service needs an address."""
    block = read(state[BLOCK])
    derived = numbers(block, replicas)
    for check in derived["uptime"]:
        if check["address"] is None:
            if api is None:
                raise SlaError(f"{check['service']} has an uptime tier and no address, which offline "
                               f"can't look up: give it one")
            check["address"] = address_of(api, state["owner"], check["service"])
    derived["variables"] = variables(block, derived)
    derived["budget"] = budget(derived)
    return {"version": VERSION, **derived}


def problems(state: dict) -> list[str]:
    """What is wrong with a state file's SLA block, upgraded and derived, offline: its
    shape, a service the state doesn't list, a number Cloud Monitoring can't take, and
    the free tiers it would go past."""
    if BLOCK not in state:
        return []
    try:
        block = read(state[BLOCK])
        derived = numbers(block)
    except SlaError as e:
        return [f"its {BLOCK} block: {e}"]
    out = [f"its {BLOCK} block names the service {name}, which the state doesn't list"
           for name in block.get("services", {}) if name not in state.get("repos", {})]
    out += [f"its {BLOCK} block: {p}" for p in over(budget(derived))]
    return out


REPLICA = re.compile(r"([A-Za-z0-9_.-]+/[a-z0-9][a-z0-9-]*)=([1-9][0-9]*)")


def parse_replicas(given: list[str]) -> dict[str, int]:
    out = {}
    for item in given:
        if not (m := REPLICA.fullmatch(item)):
            sys.exit(f"pubfleet sla: --replicas takes SERVICE/SENDER=N, not {item}")
        out[m.group(1)] = int(m.group(2))
    return out


def run(path: Path, what: str, replicas: list[str], offline: bool, api: Api = gh) -> int:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.exit(f"pubfleet sla: {path}: {e}")
    if not isinstance(state, dict) or BLOCK not in state:
        sys.exit(f"pubfleet sla: {path} has no {BLOCK} block")
    try:
        if what == "budget":
            used = budget(numbers(read(state[BLOCK]), parse_replicas(replicas)))
        else:
            derived = derive(state, parse_replicas(replicas), None if offline else api)
            used = derived["budget"]
    except SlaError as e:
        sys.exit(f"pubfleet sla: {path}: its {BLOCK} block: {e}")
    print(json.dumps(used if what == "budget" else derived, indent=2))
    for line in over(used):
        print(f"pubfleet sla: {path}: {line}", file=sys.stderr)
    return 1 if over(used) else 0
