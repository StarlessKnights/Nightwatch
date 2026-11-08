"""The ONE place prose lives. Everything else returns codes and fields."""
from __future__ import annotations

EVENT_TEMPLATES = {
    "FAULT_ACTIVE": "Fault {type} on {asset} is now active",
    "FAULT_ENDED": "Fault {type} on {asset} ended",
    "FAULT_INJECTED": "Fault injected: {type} on {asset}",
    "FAULT_CLEARED": "Fault cleared: {type} on {asset}",
    "STANDBY_AUTOSTART": "{asset} auto-started after {duty} {reason_text} (running in {delay_min} min)",
    "STANDBY_AUTOSTOP": "{asset} auto-stopped; {duty} restored",
    "DUTY_AUTORESTART": "{asset} auto-restarting (running in {delay_min} min)",
    "PUMP_RUNNING": "{asset} is now running",
    "INTERLOCK_HH_TRIP": "HH protection: IT load on {asset} shed at {level} kWh (limit {limit})",
    "INTERLOCK_HH_RESET": "HH protection on {asset} released at {level} kWh (reset {reset})",
    "INTERLOCK_LL_TRIP": "LL interlock: chiller pumps on {asset} tripped at {level} kWh (limit {limit})",
    "INTERLOCK_LL_RESET": "LL interlock on {asset} released at {level} kWh (reset {reset})",
    "OVERFLOW": "THERMAL EVENT at {asset}: {bbl} kWh of heat above capacity this minute",
    "ALARM_RAISED": "Alarm {condition} on {asset} (priority {priority})",
    "ALARM_CLEARED": "Alarm {condition} on {asset} cleared",
    "ALARM_ACK": "Acknowledged {condition} on {asset}",
    "RECOMMENDATION": "NIGHTWATCH recommends {label}. {headline}",
    "RECOMMENDATION_NONE": "NIGHTWATCH: {headline}",
    "ACTION_APPROVED": "Operator approved {label} (effective in {lead_min} min)",
    "ACTION_EFFECTIVE": "{label} is now in effect",
    "ACTION_SKIPPED": "{label} could not be applied: {why}",
    "ASSET_PATCHED": "Operator set {asset}: {change}",
    "CONFIG_CHANGED": "Configuration changed: {change}",
    "SCENARIO_LOADED": "Scenario loaded: {name}",
    "ENGINE_TOGGLED": "Decision engine {state}",
    "TRUCK_LOAD": "Portable chiller removed {bbl} kWh from {asset}",
}
_REASONS = {"trip": "tripped", "unavailable": "became unavailable", "low_flow": "low-flow"}

REASON_TEXT = {
    "ASSET_UNAVAILABLE": "The asset is unavailable (maintenance or lockout).",
    "ASSET_TRIPPED": "The standby asset is tripped and must be repaired before it can start.",
    "ASSET_DEGRADED": "The standby asset is degraded and must be repaired before it can start.",
    "PRECONDITION_FAILED": "A precondition is not met (e.g. already running, already curtailed, no portable chiller available).",
    "LEAD_TIME_EXCEEDS_DEADLINE": "It takes longer to take effect than the time left before HH.",
    "PIPELINE_CAP_EXCEEDED": "The cooling loop is already at its flow cap; extra pump flow would add nothing.",
    "TREATMENT_CAP_EXCEEDED": "Heat rejection is already at capacity; extra pump flow would add nothing.",
    "STILL_REACHES_HH": "The simulated trajectory still reaches the HH limit.",
    "INSUFFICIENT_MARGIN": "It avoids HH but leaves less than the minimum safety margin.",
    "DURATION_NOT_SUSTAINABLE": "It prevents the breach only temporarily; the level breaches HH later in the horizon.",
    "MOVES_PROBLEM_DOWNSTREAM": "It relieves this hall by pushing another hall closer to its limit.",
}

HEADLINES = {
    "NO_RISK": "All halls are within thermal limits across the {horizon_h}-hour forecast. No action needed.",
    "REACHES_HH": "{tank} reaches HH in {minutes} min. Act by {act_by}.",
    "REACHES_HH_NO_DEADLINE": "{tank} reaches HH in {minutes} min. Lead times already exceed the deadline.",
    "WATCH": "{tank} is trending toward its high limit but stays within the forecast margin.",
    "NO_FEASIBLE": "{tank} reaches HH in {minutes} min and no modelled action prevents it; the HH protection will act.",
    "ALREADY_HH": "{tank} is at or above HH. The interlock is acting; no modelled action can undo that.",
    "ENGINE_OFF": "Decision engine disabled. Only automatic layers (control, alarms, interlock) are active.",
}


def render_event(code: str, asset: str | None, params: dict) -> str:
    p = dict(params)
    p["asset"] = asset
    if "reason" in p:
        p["reason_text"] = _REASONS.get(p["reason"], p["reason"])
    try:
        return EVENT_TEMPLATES.get(code, code).format_map(_Safe(p))
    except Exception:
        return code


DIAGNOSIS_TEXT = {
    "PUMP_WEAR": "Pump wear likely (w={w}, r={r})",
    "RESTRICTION": "Loop restriction likely (r={r})",
    "COMPOUND": "Pump wear and loop restriction likely (w={w}, r={r})",
    "NONE": "No fault signature (w={w}, r={r})",
    "FLOW_TOO_LOW": "Not enough flow to diagnose",
}


def diagnosis_text(code: str, w: float | None, r: float | None) -> str:
    f = lambda x: "?" if x is None else f"{x:.2f}" if x < 2 else f"{x:.1f}"  # noqa: E731
    return DIAGNOSIS_TEXT.get(code, code).format(w=f(w), r=f(r))


def reason_text(code: str) -> str:
    return REASON_TEXT.get(code, code)


def headline(code: str, **kw) -> str:
    return HEADLINES[code].format_map(_Safe(kw))


def fmt_clock(t_min: float, start_clock: str = "00:00") -> str:
    h, m = (int(x) for x in start_clock.split(":"))
    total = int(round(h * 60 + m + t_min))
    return f"{(total // 60) % 24:02d}:{total % 60:02d}"


class _Safe(dict):
    def __missing__(self, key):
        return "?"
