"""Read-only shift handoff from the current run; no inference or rollout on the polling path."""

HANDOFF_TERMS = ("handoff", "handover", "shift", "what changed", "trend", "rundown", "run down",
                 "overview", "plant status", "with the plant", "plant doing", "going on", "plant summary")


def operator_read(ctx):
    """Build an explicitly rule-based assessment against the captured observation."""
    brief = ctx.brief
    fact = ctx.fact("get_shift_brief", "shift.brief", brief, "Plant conditions")
    limit = brief["first_limit"]
    if brief["unacknowledged"]:
        priority = "My first check would be the unacknowledged alarms. Review the highest-priority alarm and its asset."
    elif limit:
        priority = "I would watch the forecast crossing first and compare it with the measured level."
    else:
        priority = "No high-high crossing is forecast. I would continue monitoring for a change in trend."
    if limit:
        priority += f" {limit['tank']} is forecast to reach high-high at T+{limit['at_min']:g}, based on the forecast from T+{brief['forecast_as_of']}."
    trend = next(iter(brief["trends"]), None)
    if trend and len(trend["samples"]) > 1 and trend["change_bbl"] > 0:
        priority += f" Check whether heat load is exceeding heat removal at {trend['tank']}; its stored heat is rising."
    return fact, priority


def handoff_text(brief):
    count = brief["unacknowledged"]
    parts = [f"At T+{brief['t_min']}, {count} {'alarm needs' if count == 1 else 'alarms need'} acknowledgment."]
    if brief["trends"]:
        row = brief["trends"][0]
        if len(row["samples"]) > 1:
            delta = row["change_bbl"]
            direction = f"rose {delta:g} kWh" if delta > 0 else f"fell {abs(delta):g} kWh" if delta < 0 else "was unchanged"
            parts.append(f"{row['tank']} stored heat {direction} since T+{brief['from_min']}.")
        else:
            parts.append("Only the initial hall readings are available.")
    if brief["recent_events"]:
        last = brief["recent_events"][0]
        parts.append(f"Latest recorded change at T+{last['t_min']}: {last['text']}")
    return " ".join(parts)


def shift_brief(session):
    now = session.state.t_min
    points = [p for p in session.history[-31:] if now - 30 <= p["t"] <= now]
    trends = []
    for tank in session.state.tanks:
        samples = [{"t": p["t"], "bbl": p[tank]} for p in points if tank in p]
        if samples:
            trends.append({"tank": tank, "samples": samples,
                           "change_bbl": round(samples[-1]["bbl"] - samples[0]["bbl"], 2)})
    trends.sort(key=lambda r: -abs(r["change_bbl"]))
    limits = [(f["time_to_HH"], t) for t, f in session.forecast.items() if f["time_to_HH"] is not None]
    crossing, tank = min(limits) if limits else (None, None)
    alarms = [a for a in session.state.alarms if a.state == "ACTIVE_UNACK"]
    recent = [e for e in reversed(session.event_log) if now - 30 <= e["t_min"] <= now
              and e["tag"] in ("FAULT", "AUTO", "OPERATOR", "ALARM")][:4]
    return {"t_min": now, "run_id": session.run_id, "from_min": points[0]["t"] if points else now,
            "trends": trends, "recent_events": recent, "unacknowledged": len(alarms),
            "forecast_as_of": session.forecast_as_of_min, "horizon_min": session.cfg.time.horizon_min,
            "first_limit": {"tank": tank, "at_min": round(session.forecast_as_of_min + crossing, 2)}
            if tank is not None else None}
