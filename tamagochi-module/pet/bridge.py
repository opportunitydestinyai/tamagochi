"""Normalized Muse contract. No imports from F1–F9 and no personal text storage."""
from __future__ import annotations

import re
import secrets
import threading
import time
from contextlib import contextmanager

from .model import PetError, parse_time
from .security import AuthenticationError, SESSION_SECONDS, candidate_digest, token_digest

INPUT_EVENTS = frozenset({
    "CHAT_MESSAGE_SENT", "AGENT_TASK_STARTED", "AGENT_TASK_COMPLETED", "AGENT_TASK_FAILED",
    "GOAL_CREATED", "GOAL_COMPLETED", "APPROVAL_REQUIRED", "APPROVAL_GRANTED", "APPROVAL_REJECTED",
    "MEMORY_UPDATED", "TOOL_EXECUTION_COMPLETED", "MILESTONE_ACHIEVED",
})
OUTPUT_EVENTS = frozenset({
    "PET_MOOD_CHANGED", "PET_LEVEL_UP", "PET_EVOLUTION_UNLOCKED", "PET_ACTIVITY_STARTED",
    "PET_ACTIVITY_COMPLETED", "PET_BOND_CHANGED", "PET_REWARD_UNLOCKED",
})
IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:@-]{1,120}$")


def identifier(value, name):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise PetError(f"{name} deve ter 1–120 caracteres seguros (letras, números, . _ : @ -).")
    return value


def normalize_event(event: dict) -> dict:
    if not isinstance(event, dict) or set(event) != {"eventId", "eventType", "timestamp", "source", "payload"}:
        raise PetError("Envelope inválido; use eventId, eventType, timestamp, source e payload.")
    event_id = identifier(event["eventId"], "eventId")
    if event_id.startswith("auto:"):
        raise PetError("O prefixo auto: é reservado ao agendador interno.")
    event_type = event["eventType"]
    if event_type not in INPUT_EVENTS:
        raise PetError("Tipo de evento Muse desconhecido.")
    parse_time(event["timestamp"])
    source = identifier(event["source"], "source")
    raw = event["payload"]
    if not isinstance(raw, dict):
        raise PetError("payload deve ser um objeto.")
    # Explicit allowlists mean chat, task descriptions, personal memory and secrets
    # cannot accidentally be persisted by the bridge.
    allowed = {
        "CHAT_MESSAGE_SENT": {"meaningful"},
        "AGENT_TASK_STARTED": {"taskId"}, "AGENT_TASK_COMPLETED": {"taskId", "success"},
        "AGENT_TASK_FAILED": {"taskId"}, "GOAL_CREATED": {"goalId"},
        "GOAL_COMPLETED": {"goalId", "success"},
        "APPROVAL_REQUIRED": set(), "APPROVAL_GRANTED": set(), "APPROVAL_REJECTED": set(),
        "MEMORY_UPDATED": set(), "TOOL_EXECUTION_COMPLETED": {"skillId", "success", "isNew"},
        "MILESTONE_ACHIEVED": {"milestoneId", "confirmed"},
    }[event_type]
    # Reject extra fields instead of silently accepting data the caller thinks is used.
    if set(raw) - allowed:
        raise PetError("payload contém campos não permitidos; não envie textos ou dados pessoais.")
    payload = dict(raw)
    for key in ("taskId", "goalId", "skillId", "milestoneId"):
        if key in payload:
            identifier(payload[key], key)
    for key in ("success", "meaningful", "isNew", "confirmed"):
        if key in payload and not isinstance(payload[key], bool):
            raise PetError(f"{key} deve ser booleano.")
    required = {
        "AGENT_TASK_COMPLETED": ("taskId", "success"), "GOAL_COMPLETED": ("goalId", "success"),
        "TOOL_EXECUTION_COMPLETED": ("skillId", "success", "isNew"),
        "MILESTONE_ACHIEVED": ("milestoneId", "confirmed"),
    }.get(event_type, ())
    if any(key not in payload for key in required):
        raise PetError("Faltam identificador e/ou confirmação de conclusão no payload.")
    if event_type in {"AGENT_TASK_COMPLETED", "GOAL_COMPLETED", "TOOL_EXECUTION_COMPLETED"} and payload["success"] is not True:
        raise PetError("Conclusões exigem success=true; use evento de falha quando aplicável.")
    if event_type == "MILESTONE_ACHIEVED" and payload["confirmed"] is not True:
        raise PetError("O marco precisa estar confirmado.")
    return {"eventId": event_id, "eventType": event_type, "timestamp": event["timestamp"], "source": source, "payload": payload}


class BridgePolicy:
    """Independent capability and opt-in scopes, reset on restart and after 8h.

    Consent changes are administrative operations: callers of set_consent must
    authenticate the owner first. The lock serializes revocation with admitted
    bridge operations; responses already in flight cannot be recalled.
    """
    SCOPES = frozenset({"receiveEvents", "shareData"})

    def __init__(self, bridge_token, *, clock=time.monotonic):
        self._token_digest = token_digest(bridge_token)
        self._consent = {"receiveEvents": False, "shareData": False}
        self._expires_at = None
        self._clock = clock
        self._lock = threading.RLock()

    def _expire(self):
        if self._expires_at is not None and self._clock() >= self._expires_at:
            self._consent = {"receiveEvents": False, "shareData": False}
            self._expires_at = None

    def check_token(self, credential):
        digest = candidate_digest(credential)
        if digest is None or not secrets.compare_digest(digest, self._token_digest):
            raise AuthenticationError("Credencial inválida.")

    def consent(self):
        with self._lock:
            self._expire()
            return dict(self._consent)

    def set_consent(self, consent):
        if not isinstance(consent, dict) or set(consent) != self.SCOPES or any(type(v) is not bool for v in consent.values()):
            raise PetError("Informe receiveEvents e shareData como booleanos explícitos.")
        with self._lock:
            self._consent = dict(consent)
            self._expires_at = self._clock() + SESSION_SECONDS if any(consent.values()) else None
            return dict(self._consent)

    @contextmanager
    def authorized(self, credential, scope):
        self.check_token(credential)
        if scope not in self.SCOPES:
            raise ValueError("Escopo de consentimento desconhecido.")
        with self._lock:
            self._expire()
            if not self._consent[scope]:
                raise PermissionError("Consentimento da ponte não concedido para este escopo.")
            yield


class MusePetBridge:
    """External bridge adapter; a separate token and scoped consent are mandatory.

    This protects callers using this adapter. The service/repository remain
    trusted in-process APIs, not a sandbox against arbitrary local Python code.
    """
    def __init__(self, service, policy: BridgePolicy):
        self.service = service
        self.policy = policy

    def receive(self, envelope: dict, *, credential=None) -> dict:
        with self.policy.authorized(credential, "receiveEvents"):
            result = self.service.process_muse_event(normalize_event(envelope))
            # An input-only grant does not allow exporting the complete pet state.
            return {key: result[key] for key in ("duplicate", "duplicateKind", "xpAwarded")}

    def outgoing(self, after: int = 0, limit: int = 100, *, credential=None) -> list[dict]:
        with self.policy.authorized(credential, "shareData"):
            return self.service.events(after=after, limit=limit)

    def context(self, *, credential=None) -> dict:
        """A minimal, non-personal style hint, not a replacement for agent safety."""
        with self.policy.authorized(credential, "shareData"):
            state = self.service.snapshot()
            return {"petId": state["petId"], "mood": state["mood"], "traits": state["leadingTraits"],
                    "bond": state["bond"], "level": state["level"], "currentActivity": state["activity"]}
