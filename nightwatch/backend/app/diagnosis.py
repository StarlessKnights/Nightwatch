"""Invert (Q, P) into pump health w and restriction r, then classify. Pure; returns codes and numbers."""
from __future__ import annotations

from .models import Config
from .pump_model import _a, operating_point


def invert(q: float, p: float, s: float, cfg: Config) -> tuple[float, float] | None:
    """(w_est, r_est), or None when flow is too low to be meaningful (never NaN)."""
    pm, d = cfg.pump_model, cfg.diagnosis
    if q < d.min_flow_for_diagnosis or s <= 0:
        return None
    denom = s * s * pm.H0 - _a(pm) * q * q
    if denom <= 0:
        return None
    return p / denom, (p - pm.Hs) / (pm.k * q * q)


def classify(w_est: float, r_est: float, cfg: Config) -> str:
    d = cfg.diagnosis
    if w_est < d.wear_w_max and r_est > d.restriction_r_min:
        return "COMPOUND"
    if w_est < d.wear_w_max and r_est < d.wear_r_max:
        return "PUMP_WEAR"
    if r_est > d.restriction_r_min and w_est >= d.restriction_w_min:
        return "RESTRICTION"
    return "NONE"


def diagnose(samples: list[dict], cfg: Config) -> dict:
    """samples: [{Q, P, s}] (most recent last). Averages the last window_min samples, then inverts.
    TODO(phase3): the LLM layer consumes this dict as-is."""
    win = samples[-cfg.diagnosis.window_min:]
    if not win:
        return {"code": "FLOW_TOO_LOW", "w_est": None, "r_est": None, "evidence": []}
    q = sum(x["Q"] for x in win) / len(win)
    p = sum(x["P"] for x in win) / len(win)
    s = sum(x.get("s", 1.0) for x in win) / len(win)
    est = invert(q, p, s, cfg)
    if est is None:
        return {"code": "FLOW_TOO_LOW", "w_est": None, "r_est": None, "evidence": [{"field": "Q", "value": round(q, 1)}]}
    w, r = est
    return {"code": classify(w, r, cfg), "w_est": round(w, 3), "r_est": round(r, 3),
            "evidence": [{"field": "Q", "value": round(q, 1)}, {"field": "P", "value": round(p, 1)},
                         {"field": "w_est", "value": round(w, 3)}, {"field": "r_est", "value": round(r, 3)}]}


def diagnose_instant(w: float, s: float, r: float, cfg: Config) -> dict:
    """Diagnosis from an instantaneous operating point (stateless; used by the recommendation)."""
    q, p = operating_point(w, s, r, cfg.pump_model)
    return diagnose([{"Q": q, "P": p, "s": s}], cfg)
