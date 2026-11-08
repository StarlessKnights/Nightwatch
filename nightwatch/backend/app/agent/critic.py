"""Explicit assumptions attached to unchanged deterministic rankings."""


def review(ctx, evidence_id):
    concerns = [
        {
            "text": "Costs use illustrative coefficients and a fixed forecast horizon; this is not a reliability guarantee.",
            "evidence_ids": [evidence_id],
        },
        {
            "text": "Future unobserved faults are excluded. A currently available standby may still fail later.",
            "evidence_ids": [evidence_id],
        },
    ]
    if any(o.reason_codes for o in ctx.recommendation().options):
        concerns.append(
            {
                "text": "Rejected options and shared-capacity effects need review before choosing an alternative.",
                "evidence_ids": [evidence_id],
            }
        )
    return concerns
