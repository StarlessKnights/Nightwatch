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
            "summary": rec.headline, "automatic": auto, "interpretations": [], "concerns": review(ctx, recommendation["id"]),
            "attention": "Review validated options; operator approval is required." if rec.ranked_option_ids else "Monitor protection and review rejected options; no available action has been established.",
            "source": "DETERMINISTIC", "question": None}
