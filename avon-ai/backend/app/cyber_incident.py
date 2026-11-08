"""Winstead Cyber Incident Command Core.

Implements NIST SP 800-61 computer security incident handling lifecycle,
hardware-authenticated access control, air-gap isolation protocol,
asset compromise scope tracking, and out-of-band communication feeds.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field


class NISTStage(str, Enum):
    """NIST SP 800-61 Rev 2 incident lifecycle stages."""
    DETECTION = "DETECTION"
    CONTAINMENT = "CONTAINMENT"
    ERADICATION = "ERADICATION"
    RECOVERY = "RECOVERY"


class AssetCategory(str, Enum):
    """Critical industrial & data center cyber-physical asset categories."""
    COMPUTE_POD_A = "COMPUTE_POD_A"
    STORAGE_SAN = "STORAGE_SAN"
    CHILLED_WATER_LOOP = "CHILLED_WATER_LOOP"
    EXTERNAL_WAN = "EXTERNAL_WAN"


class AssetCompromiseStatus(str, Enum):
    """Compromise and threat level per asset category."""
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    LOCKED_RANSOMWARE = "LOCKED_RANSOMWARE"
    DATA_EXFILTRATED = "DATA_EXFILTRATED"


class ResponderRole(str, Enum):
    """Winstead command authorization roles."""
    ADMIN = "admin"
    OPERATOR = "operator"
    INCIDENT_COMMANDER = "incident_commander"


VALID_ROLES = {r.value for r in ResponderRole}
VALID_STAGES = {s.value for s in NISTStage}
VALID_ASSETS = {a.value for a in AssetCategory}
VALID_STATUSES = {st.value for st in AssetCompromiseStatus}

ROLE_BADGES: dict[str, str] = {
    "admin": "ADMIN-AUTH",
    "operator": "OPS-STATION",
    "incident_commander": "INCIDENT-COMMAND",
}


# --- Request & Data Models ---

class AirgapRequest(BaseModel):
    engaged: bool
    source: str = "operator"


class ScopeUpdateRequest(BaseModel):
    asset: str
    status: str
    notes: Optional[str] = ""
    actor: Optional[str] = "operator"


class CommsMessageRequest(BaseModel):
    author: str
    role: str
    message: str


class ResponderCreateRequest(BaseModel):
    name: str
    role: str
    verified: bool = True
    hardware_token: Optional[str] = None


class StageUpdateRequest(BaseModel):
    stage: str
    source: str = "operator"


# --- Manager Implementation ---

class CyberIncidentManager:
    """Manages cyber incident response, isolation, access control, and telemetry."""

    def __init__(self) -> None:
        self.airgap_engaged: bool = False
        self.quarantined_egress: bool = False
        self.incident_level: str = "CRITICAL"
        self.stage: str = NISTStage.DETECTION.value
        self.responders: dict[str, dict[str, Any]] = {}
        self.scope: dict[str, dict[str, Any]] = {}
        self.event_log: list[dict[str, Any]] = []
        self.comms_feed: list[dict[str, Any]] = []
        self._event_counter: int = 0
        self._comms_counter: int = 0
        self._init_scope()

    def _init_scope(self) -> None:
        """Initialize all critical asset categories to nominal healthy state."""
        now_ts = datetime.now(timezone.utc).isoformat()
        self.scope = {
            asset.value: {
                "asset": asset.value,
                "status": AssetCompromiseStatus.HEALTHY.value,
                "notes": "Nominal operations",
                "updated_at": now_ts,
                "last_actor": "system",
            }
            for asset in AssetCategory
        }

    def reset(self) -> None:
        """Reset incident state to initial baseline."""
        self.airgap_engaged = False
        self.quarantined_egress = False
        self.incident_level = "CRITICAL"
        self.stage = NISTStage.DETECTION.value
        self.responders.clear()
        self._init_scope()
        self.event_log.clear()
        self.comms_feed.clear()
        self._event_counter = 0
        self._comms_counter = 0

    # ---------- Winstead #1: Secure & Isolated (Air-Gap) ----------

    def toggle_airgap(self, engaged: bool, source: str = "operator") -> dict[str, Any]:
        """Toggles isolation status. When engaged, external API egress is severed/quarantined."""
        self.airgap_engaged = bool(engaged)
        self.quarantined_egress = bool(engaged)

        action = "AIRGAP_ENGAGED" if engaged else "AIRGAP_DISENGAGED"
        event = self.log_event(
            action=action,
            actor=source,
            details={
                "engaged": self.airgap_engaged,
                "quarantined_egress": self.quarantined_egress,
                "external_egress": "SEVERED/QUARANTINED" if engaged else "NORMAL",
            },
        )

        return {
            "airgap_engaged": self.airgap_engaged,
            "quarantined_egress": self.quarantined_egress,
            "source": source,
            "timestamp": event["timestamp"],
        }

    def is_egress_allowed(self) -> bool:
        """Returns True if external egress is permitted (air-gap not engaged)."""
        return not self.airgap_engaged

    def assert_egress_allowed(self) -> None:
        """Raises PermissionError if air-gap is engaged, severing external communication."""
        if self.airgap_engaged:
            raise PermissionError("External API egress is severed/quarantined under active air-gap protocol.")

    # ---------- Winstead #2: Access Control & Hardware Auth ----------

    def add_responder(
        self,
        name: str,
        role: str,
        verified: bool = True,
        hardware_token: Optional[str] = None,
    ) -> dict[str, Any]:
        """Registers a responder with verified credentials and hardware authentication token."""
        clean_role = role.strip().lower()
        if clean_role not in VALID_ROLES:
            raise ValueError(f"Invalid role '{role}'. Must be one of: {sorted(VALID_ROLES)}")
        if not name.strip():
            raise ValueError("Responder name cannot be empty.")

        resp_id = f"RESP-{uuid.uuid4().hex[:8].upper()}"
        badge = ROLE_BADGES.get(clean_role, clean_role.upper())
        token = hardware_token or f"HW-AUTH-{uuid.uuid4().hex[:6].upper()}"
        now_ts = datetime.now(timezone.utc).isoformat()

        responder = {
            "id": resp_id,
            "name": name.strip(),
            "role": clean_role,
            "role_badge": badge,
            "verified": bool(verified),
            "hardware_token": token,
            "created_at": now_ts,
        }
        self.responders[resp_id] = responder

        self.log_event(
            action="RESPONDER_REGISTERED",
            actor=name.strip(),
            details={
                "id": resp_id,
                "role": clean_role,
                "role_badge": badge,
                "verified": bool(verified),
                "hardware_token": token,
            },
        )
        return responder

    def verify_responder(self, responder_id: str) -> bool:
        """Checks if a responder is registered and verified."""
        resp = self.responders.get(responder_id)
        if not resp:
            return False
        return bool(resp.get("verified", False))

    def get_responders(self) -> list[dict[str, Any]]:
        """Returns list of registered incident responders."""
        return list(self.responders.values())

    def get_responder(self, responder_id: str) -> Optional[dict[str, Any]]:
        """Finds responder by ID."""
        return self.responders.get(responder_id)

    @property
    def responder_count(self) -> int:
        """Total number of registered responders."""
        return len(self.responders)

    # ---------- Winstead #3: Incident Documentation & Lifecycle ----------

    def set_stage(self, stage: str, source: str = "operator") -> dict[str, Any]:
        """Transitions NIST SP 800-61 lifecycle stage."""
        clean_stage = stage.strip().upper()
        if clean_stage not in VALID_STAGES:
            raise ValueError(f"Invalid NIST stage '{stage}'. Must be one of: {sorted(VALID_STAGES)}")

        old_stage = self.stage
        self.stage = clean_stage
        self.log_event(
            action="STAGE_TRANSITION",
            actor=source,
            details={"previous_stage": old_stage, "new_stage": clean_stage},
        )
        return {"stage": self.stage, "previous_stage": old_stage, "source": source}

    def set_incident_level(self, level: str, source: str = "operator") -> dict[str, Any]:
        """Updates active incident threat level (e.g. CRITICAL, ELEVATED, NORMAL)."""
        old_level = self.incident_level
        self.incident_level = level.strip().upper()
        self.log_event(
            action="INCIDENT_LEVEL_CHANGED",
            actor=source,
            details={"previous_level": old_level, "new_level": self.incident_level},
        )
        return {"level": self.incident_level, "previous_level": old_level}

    def log_event(self, action: str, actor: str, details: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Appends a timestamped action to the real-time event log."""
        self._event_counter += 1
        now_ts = datetime.now(timezone.utc).isoformat()
        event = {
            "id": self._event_counter,
            "timestamp": now_ts,
            "action": action,
            "actor": actor,
            "details": details or {},
        }
        self.event_log.append(event)
        return event

    def get_events(self, limit: Optional[int] = None) -> list[dict[str, Any]]:
        """Returns recorded event log."""
        if limit and limit > 0:
            return self.event_log[-limit:]
        return list(self.event_log)

    # ---------- Winstead #4: Compromised Scope Definitions ----------

    def update_asset_scope(
        self,
        asset: str,
        status: str,
        notes: str = "",
        actor: str = "operator",
    ) -> dict[str, Any]:
        """Updates compromise status for a defined asset category."""
        clean_asset = asset.strip().upper()
        clean_status = status.strip().upper()

        if clean_asset not in VALID_ASSETS:
            raise ValueError(f"Invalid asset category '{asset}'. Must be one of: {sorted(VALID_ASSETS)}")
        if clean_status not in VALID_STATUSES:
            raise ValueError(f"Invalid compromise status '{status}'. Must be one of: {sorted(VALID_STATUSES)}")

        prev_status = self.scope[clean_asset]["status"]
        now_ts = datetime.now(timezone.utc).isoformat()

        updated_entry = {
            "asset": clean_asset,
            "status": clean_status,
            "notes": notes.strip(),
            "updated_at": now_ts,
            "last_actor": actor,
        }
        self.scope[clean_asset] = updated_entry

        self.log_event(
            action="ASSET_SCOPE_UPDATED",
            actor=actor,
            details={
                "asset": clean_asset,
                "previous_status": prev_status,
                "status": clean_status,
                "notes": notes.strip(),
            },
        )

        return {
            "ok": True,
            "asset": clean_asset,
            "status": clean_status,
            "notes": notes.strip(),
            "scope": self.get_scope(),
        }

    def get_scope(self) -> dict[str, dict[str, Any]]:
        """Returns compromised scope definitions for all assets."""
        return {k: dict(v) for k, v in self.scope.items()}

    # ---------- Winstead #5: Out-of-Band Real-Time Comms ----------

    def post_comms_message(self, author: str, role: str, message: str) -> dict[str, Any]:
        """Appends an out-of-band communication message to the incident feed."""
        clean_role = role.strip().lower()
        if clean_role not in VALID_ROLES:
            raise ValueError(f"Invalid role '{role}'. Must be one of: {sorted(VALID_ROLES)}")
        if not message.strip():
            raise ValueError("Message cannot be empty.")
        if not author.strip():
            raise ValueError("Author cannot be empty.")

        self._comms_counter += 1
        now_ts = datetime.now(timezone.utc).isoformat()
        badge = ROLE_BADGES.get(clean_role, clean_role.upper())

        entry = {
            "id": self._comms_counter,
            "timestamp": now_ts,
            "author": author.strip(),
            "role": clean_role,
            "role_badge": badge,
            "message": message.strip(),
        }
        self.comms_feed.append(entry)

        self.log_event(
            action="COMMS_MESSAGE_POSTED",
            actor=author.strip(),
            details={
                "id": entry["id"],
                "role": clean_role,
                "role_badge": badge,
            },
        )
        return entry

    def get_comms_feed(self) -> list[dict[str, Any]]:
        """Returns in-memory append-only incident communication feed."""
        return list(self.comms_feed)

    # ---------- Status Summary ----------

    def get_status(self) -> dict[str, Any]:
        """Returns overall incident command status."""
        return {
            "airgap_engaged": self.airgap_engaged,
            "quarantined_egress": self.quarantined_egress,
            "active_incident_level": self.incident_level,
            "stage": self.stage,
            "responder_count": len(self.responders),
            "scope": {asset: data["status"] for asset, data in self.scope.items()},
            "scope_summary": {
                "healthy": sum(1 for d in self.scope.values() if d["status"] == AssetCompromiseStatus.HEALTHY.value),
                "degraded": sum(1 for d in self.scope.values() if d["status"] == AssetCompromiseStatus.DEGRADED.value),
                "locked_ransomware": sum(1 for d in self.scope.values() if d["status"] == AssetCompromiseStatus.LOCKED_RANSOMWARE.value),
                "data_exfiltrated": sum(1 for d in self.scope.values() if d["status"] == AssetCompromiseStatus.DATA_EXFILTRATED.value),
            },
            "events_count": len(self.event_log),
            "comms_count": len(self.comms_feed),
        }
