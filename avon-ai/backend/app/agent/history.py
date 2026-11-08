"""Provenance-preserving observations, never inferred reliability inputs to physics."""
from collections import defaultdict


def signals(audit):
    rows = audit.read(limit=500)
    failures = defaultdict(list)
    notes = []
    for row in rows:
        data = row["data"]
        if row["kind"] == "note":
            notes.append(row)
        if row["kind"] == "event" and data.get("code") in ("FAULT_ACTIVE", "FAULT_INJECTED") and data.get("params", {}).get("type") in ("PUMP_TRIP", "PUMP_DEGRADE"):
            failures[data["asset"]].append(row)
    return {"signals": [{"asset_id": asset, "observed_fault_events": len(items), "sources": items,
                         "interpretation": "Observed simulated fault events in retained history; not a failure probability or MTBF estimate."}
                        for asset, items in failures.items()], "notes": notes[:30],
            "coverage": "Latest 500 retained event/note records; scenarios may be replayed."}
