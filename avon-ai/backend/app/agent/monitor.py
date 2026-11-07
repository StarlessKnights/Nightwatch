"""Cheap deterministic change detection; no model call on simulation ticks."""
import hashlib
import json

from .. import faults
from ..network import impact


def observe(session):
    state, topo = session.state, session.topo
    eff = faults.effective(state, topo)
    roots = {f.target for f in state.faults if faults.is_active(f, state.t_min)}
    roots.update(p for p, s in state.pumps.items() if not eff.pump_available[p] or eff.pump_cf[p] < .99 or s.run_state == "TRIPPED")
    roots.update(p for p, v in eff.pipeline_rf.items() if v < .99)
    roots.update(t for t, v in eff.treatment_if.items() if v < .99)
    roots.update(t for t, f in session.forecast.items() if f["status"] != "normal")
    roots.update(a.tag for a in state.alarms if a.state != "CLEARED")
    clusters = []
    for root in sorted(roots):
        if root not in topo.nodes:
            continue
        info = impact(topo, root)
        tanks = set([root] + info["upstream"]).intersection(topo.tanks)
        if root in topo.sources:
            tanks.add(topo.sources[root])
        group = {"roots": {root}, "tanks": tanks}
        merging = [c for c in clusters if c["tanks"] & tanks]
        for old in merging:
            group["roots"] |= old["roots"]
            group["tanks"] |= old["tanks"]
            clusters.remove(old)
        clusters.append(group)
    groups = [{"roots": sorted(c["roots"]), "tanks": sorted(c["tanks"])} for c in clusters]
    def deadline_bucket(value):
        return next((n for n in (0, 5, 15, 30, 60, 120, 480) if value is not None and value <= n), None)
    signature = {
        "run": session.run_id, "engine": session.engine_enabled,
        "pumps": [(p, s.run_state, eff.pump_available[p], round(eff.pump_cf[p], 1)) for p, s in state.pumps.items()],
        "pipeline": eff.pipeline_rf, "treatment": eff.treatment_if, "sources": eff.source_mult,
        "forecast": [(t, f["status"], deadline_bucket(f["time_to_HH"])) for t, f in session.forecast.items()],
        "alarms": [(a.id, a.state == "CLEARED") for a in state.alarms],
        "actions": [a.id for a in state.pending_actions],
        "faults": [(f.id, f.type, f.target) for f in state.faults if faults.is_active(f, state.t_min)],
        "config": session.cfg.model_dump(),
    }
    return hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest(), groups
