from uuid import uuid4

from .critic import review


def briefing(ctx, group):
    rec = ctx.recommendation()
    evidence_ids = []
    affected = set(group["roots"] + group["tanks"])
    for root in group["roots"]:
        evidence_ids.append(ctx.asset(root)["id"])
        paths = ctx.related(root)
        affected.update(paths["upstream"] + paths["downstream"] + paths["shared_capacity_assets"])
        evidence_ids.append(ctx.fact("get_impact", f"impact.{root}", paths)["id"])
    forecasts = {t: rec.forecast[t].model_dump(exclude={"series"}) for t in group["tanks"]}
    evidence_ids.append(ctx.fact("get_forecast", "incident.forecasts", forecasts, "Forecast and time to limit (minutes)")["id"])
    auto = [e for e in ctx.events if e["tag"] == "AUTO" and e["asset"] in affected][-8:]
    for event in auto:
        evidence_ids.append(ctx.fact("get_event_history", f"events.{event['id']}", event, event["text"])["id"])
    trend = next((row for row in ctx.brief["trends"] if row["tank"] in group["tanks"]), None)
    summary = rec.headline
    if trend and len(trend["samples"]) > 1:
        delta = trend["change_bbl"]
        direction = f"rose {delta:g} bbl" if delta > 0 else f"fell {abs(delta):g} bbl" if delta < 0 else "was unchanged"
        summary = f"{trend['tank']} volume {direction} from T+{ctx.brief['from_min']} to T+{ctx.state.t_min}."
        evidence_ids.append(ctx.fact("get_shift_brief", "shift.brief", ctx.brief, "Observed tank trends")["id"])
    recommendation = ctx.fact("get_recommendations", "recommendation", {
        "ranked_option_ids": rec.ranked_option_ids, "best_option_id": rec.best_option_id,
        "do_nothing_cost": rec.do_nothing_cost, "horizon_min": ctx.cfg.time.horizon_min,
        "cost_basis": "illustrative configuration", "future_scripted_faults_included": False,
        "options": [ctx.option_summary(o) for o in rec.options]}, "Deterministic decision and assumptions")
    evidence_ids.append(recommendation["id"])
    severity = max((rec.forecast[t].status for t in group["tanks"]),
                   key=["normal", "watch", "warning", "critical"].index, default="watch")
    if severity == "normal":
        severity = "watch"
    return {"id": uuid4().hex, "run_id": ctx.run_id, "revision": ctx.revision, "t_min": ctx.state.t_min,
            "first_seen_min": ctx.state.t_min, "status": "active", "severity": severity,
            "title": "Network condition: " + ", ".join(group["roots"]), "roots": group["roots"],
            "tanks": group["tanks"], "affected_assets": sorted(affected), "evidence_ids": evidence_ids,
            "summary": summary, "automatic": auto, "interpretations": [], "concerns": review(ctx, recommendation["id"]),
            "attention": ("Check whether tank levels stabilize after the automatic response." if auto
                          else "Compare observed tank levels with the forecast and check the affected equipment."),
            "source": "DETERMINISTIC", "question": None}
