"""SL-001's deterministic rules and validated, persistable configuration.

These are original prototype rules, not TamAGI's formulas.
"""
from __future__ import annotations

import copy
import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class PetError(ValueError):
    """An invalid request which should not change persisted state."""


class ConflictError(PetError):
    """An event ID was reused with different content or energy is insufficient."""


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise PetError("O horário precisa incluir fuso horário.")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError("timezone required")
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError) as exc:
        raise PetError("Horário inválido: use ISO 8601 com fuso horário.") from exc


def clamp(value: float) -> float:
    return round(max(0.0, min(100.0, float(value))), 4)


ATTRIBUTES = ("happiness", "energy", "curiosity", "knowledge", "bond", "trust")
TRAITS = ("PLAYFUL", "CURIOUS", "CREATIVE", "ORGANIZED", "SOCIAL", "REFLECTIVE", "HELPFUL")
SPECIALIZATIONS = ("EXPLORER", "CREATOR", "RESEARCHER", "ORGANIZER", "COMPANION")
ACTIONS = ("PLAY", "REST", "EXPLORE", "LEARN", "CREATE", "CHAT")
AUTONOMOUS_ACTIVITIES = ("DREAM", "EXPLORE", "EXPERIMENT", "JOURNAL")
XP_REASONS = ("FIRST_INTERACTION", "CONVERSATION", "TASK", "GOAL", "SKILL", "LEARN", "CREATIVE", "MILESTONE")

DEFAULT_CONFIG = {
    "initialAttributes": {"happiness": 75, "energy": 80, "curiosity": 50, "knowledge": 10, "bond": 20, "trust": 50},
    "initialTraits": {"PLAYFUL": 50, "CURIOUS": 55, "CREATIVE": 50, "ORGANIZED": 50, "SOCIAL": 50, "REFLECTIVE": 50, "HELPFUL": 50},
    "actionEffects": {
        "PLAY": {"happiness": 8, "energy": -10, "bond": 3, "trust": 1},
        "REST": {"energy": 20},
        "EXPLORE": {"curiosity": 5, "energy": -8, "happiness": 2},
        "LEARN": {"knowledge": 4, "energy": -7, "curiosity": 2},
        "CREATE": {"happiness": 3, "energy": -7, "curiosity": 2},
        "CHAT": {"happiness": 2, "bond": 2, "trust": 1},
    },
    "autonomyEnergyCost": {"DREAM": 2, "EXPLORE": 5, "EXPERIMENT": 5, "JOURNAL": 2},
    "autonomyEffects": {"DREAM": {}, "EXPLORE": {"curiosity": 2}, "EXPERIMENT": {"happiness": 2}, "JOURNAL": {}},
    "xpGains": {"FIRST_INTERACTION": 5, "CONVERSATION": 2, "TASK": 15, "GOAL": 30, "SKILL": 10, "LEARN": 8, "CREATIVE": 8, "MILESTONE": 25},
    "xpDailyLimits": {"FIRST_INTERACTION": 1, "CONVERSATION": 3, "TASK": 5, "GOAL": 3, "SKILL": 3, "LEARN": 5, "CREATIVE": 5, "MILESTONE": 3},
    "dailyXpCap": 120,
    "xpFormula": {"scale": 100, "exponent": 1.5},
    "stageStarts": {"AWAKENING": 1, "DISCOVERY": 5, "LEARNING": 10, "COMPANION": 20, "EXPLORER": 35, "EVOLVED": 50},
    "moodThresholds": {"tiredEnergy": 25, "happyHappiness": 90, "happyEnergy": 60, "curiousCuriosity": 75, "boredHappiness": 30},
    "traitStep": 2,
    "meaningfulChatMinChars": 30,
    "passiveEnergyPerHour": 0.5,
    "maxElapsedHours": 24,
    "signalMinutes": 20,
    "specializationThreshold": 3,
    "autonomy": {"enabled": False, "intervalMinutes": 60, "restStartHour": 22, "restEndHour": 8, "timeZone": "America/Fortaleza"},
}

# The level bands and labels are new product hypotheses, not TamAGI's.
STAGES = (
    {"start": 1, "key": "AWAKENING", "name": "Despertar", "reward": "Habitat básico e interações"},
    {"start": 5, "key": "DISCOVERY", "name": "Descoberta", "reward": "Moldura de descoberta"},
    {"start": 10, "key": "LEARNING", "name": "Aprendizado", "reward": "Emblema de aprendizado"},
    {"start": 20, "key": "COMPANION", "name": "Companheiro", "reward": "Decoração halo"},
    {"start": 35, "key": "EXPLORER", "name": "Explorador", "reward": "Ambiente Aurora"},
    {"start": 50, "key": "EVOLVED", "name": "Evoluído", "reward": "Constelação e emblema"},
)

ACTION_TRAITS = {
    "PLAY": ("PLAYFUL", "COMPANION"), "REST": ("REFLECTIVE", None),
    "EXPLORE": ("CURIOUS", "EXPLORER"), "LEARN": ("CURIOUS", "RESEARCHER"),
    "CREATE": ("CREATIVE", "CREATOR"), "CHAT": ("SOCIAL", "COMPANION"),
    "DREAM": ("REFLECTIVE", None), "EXPERIMENT": ("CREATIVE", "CREATOR"),
    "JOURNAL": ("ORGANIZED", "ORGANIZER"), "TASK": ("HELPFUL", "ORGANIZER"),
}


def _number(value, lo, hi, name, *, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise PetError(f"{name} deve ser um número válido.")
    if value < lo or value > hi or (integer and int(value) != value):
        raise PetError(f"{name} deve estar entre {lo} e {hi}.")


def validate_config(config: dict) -> dict:
    """Accept an entire known schema, reject typos and unsafe/unbounded values."""
    if not isinstance(config, dict) or set(config) != set(DEFAULT_CONFIG):
        raise PetError("A configuração deve conter exatamente as seções documentadas.")
    for name, template in (("initialAttributes", DEFAULT_CONFIG["initialAttributes"]),
                           ("initialTraits", DEFAULT_CONFIG["initialTraits"])):
        obj = config[name]
        if not isinstance(obj, dict) or set(obj) != set(template):
            raise PetError(f"Campos inválidos em {name}.")
        for key, value in obj.items():
            _number(value, 0, 100, f"{name}.{key}")
    effects = config["actionEffects"]
    if not isinstance(effects, dict) or set(effects) != set(ACTIONS):
        raise PetError("Ações inválidas em actionEffects.")
    for action, changes in effects.items():
        if not isinstance(changes, dict) or not set(changes).issubset(ATTRIBUTES):
            raise PetError(f"Atributos inválidos em {action}.")
        for key, value in changes.items():
            _number(value, -30, 30, f"actionEffects.{action}.{key}")
    auto_effects = config["autonomyEffects"]
    if not isinstance(auto_effects, dict) or set(auto_effects) != set(AUTONOMOUS_ACTIVITIES):
        raise PetError("Atividades inválidas em autonomyEffects.")
    for activity, changes in auto_effects.items():
        if not isinstance(changes, dict) or not set(changes).issubset(set(ATTRIBUTES) - {"energy"}):
            raise PetError(f"Efeitos inválidos em {activity}.")
        for key, value in changes.items():
            _number(value, -30, 30, f"autonomyEffects.{activity}.{key}")
    for name, keys, maximum in (("autonomyEnergyCost", AUTONOMOUS_ACTIVITIES, 30),
                                ("xpGains", XP_REASONS, 100), ("xpDailyLimits", XP_REASONS, 100)):
        obj = config[name]
        if not isinstance(obj, dict) or set(obj) != set(keys):
            raise PetError(f"Campos inválidos em {name}.")
        for key, value in obj.items():
            _number(value, 0, maximum, f"{name}.{key}", integer=True)
    _number(config["dailyXpCap"], 0, 1000, "dailyXpCap", integer=True)
    formula = config["xpFormula"]
    if not isinstance(formula, dict) or set(formula) != {"scale", "exponent"}:
        raise PetError("Fórmula de XP inválida.")
    _number(formula["scale"], 10, 5000, "xpFormula.scale", integer=True)
    _number(formula["exponent"], 1, 3, "xpFormula.exponent")
    starts = config["stageStarts"]
    keys = list(DEFAULT_CONFIG["stageStarts"])
    if not isinstance(starts, dict) or set(starts) != set(keys):
        raise PetError("Faixas de evolução inválidas.")
    for key in keys:
        _number(starts[key], 1, 10000, f"stageStarts.{key}", integer=True)
    if starts[keys[0]] != 1 or any(starts[a] >= starts[b] for a, b in zip(keys, keys[1:])):
        raise PetError("Os estágios devem começar em 1 e ter níveis crescentes.")
    thresholds = config["moodThresholds"]
    if not isinstance(thresholds, dict) or set(thresholds) != set(DEFAULT_CONFIG["moodThresholds"]):
        raise PetError("Limiares de humor inválidos.")
    for key, value in thresholds.items():
        _number(value, 0, 100, f"moodThresholds.{key}")
    _number(config["traitStep"], 0, 10, "traitStep")
    _number(config["meaningfulChatMinChars"], 1, 500, "meaningfulChatMinChars", integer=True)
    _number(config["passiveEnergyPerHour"], 0, 5, "passiveEnergyPerHour")
    _number(config["maxElapsedHours"], 1, 48, "maxElapsedHours")
    _number(config["signalMinutes"], 1, 240, "signalMinutes", integer=True)
    _number(config["specializationThreshold"], 1, 100, "specializationThreshold", integer=True)
    auto = config["autonomy"]
    if not isinstance(auto, dict) or set(auto) != set(DEFAULT_CONFIG["autonomy"]):
        raise PetError("Configuração de autonomia inválida.")
    if not isinstance(auto["enabled"], bool):
        raise PetError("autonomy.enabled deve ser verdadeiro ou falso.")
    _number(auto["intervalMinutes"], 15, 1440, "autonomy.intervalMinutes", integer=True)
    _number(auto["restStartHour"], 0, 23, "autonomy.restStartHour", integer=True)
    _number(auto["restEndHour"], 0, 23, "autonomy.restEndHour", integer=True)
    if not isinstance(auto["timeZone"], str) or len(auto["timeZone"]) > 80:
        raise PetError("Fuso horário inválido.")
    try:
        ZoneInfo(auto["timeZone"])
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise PetError("Fuso horário desconhecido; use um nome IANA, por exemplo America/Fortaleza.") from exc
    return copy.deepcopy(config)


def initial_state(config: dict, now: datetime) -> dict:
    return {
        "petId": "SL-001", "xp": 0, **copy.deepcopy(config["initialAttributes"]),
        "activity": "IDLE", "mood": "CALM", "recentSignal": None,
        "traits": copy.deepcopy(config["initialTraits"]),
        "specializationScores": {key: 0 for key in SPECIALIZATIONS}, "specialization": None,
        "habitat": {"theme": "LAVENDER", "decoration": "STARS", "playerFit": "FIT"},
        "autonomyState": {"nextRunAt": None, "lastRunAt": None, "cursor": 0},
        "createdAt": iso(now), "lastUpdatedAt": iso(now),
    }


class ExperienceEngine:
    @staticmethod
    def threshold(level: int, config: dict | None = None) -> int:
        if isinstance(level, bool) or not isinstance(level, int) or level < 1:
            raise PetError("Nível inválido.")
        formula = (config or DEFAULT_CONFIG)["xpFormula"]
        return int(math.floor(formula["scale"] * (level - 1) ** formula["exponent"] + 0.5))

    @classmethod
    def level(cls, xp: int, config: dict | None = None) -> int:
        if isinstance(xp, bool) or not isinstance(xp, int) or xp < 0:
            raise PetError("XP inválido.")
        lo, hi = 1, 2
        while cls.threshold(hi, config) <= xp:
            lo, hi = hi, hi * 2
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if cls.threshold(mid, config) <= xp:
                lo = mid
            else:
                hi = mid
        return lo

    @classmethod
    def progress(cls, xp: int, config: dict | None = None) -> dict:
        level = cls.level(xp, config)
        current, following = cls.threshold(level, config), cls.threshold(level + 1, config)
        # The interval is [current, following): never round the displayed
        # percentage to 100 while the next level still requires XP.
        percent = min(99.9, round(100 * (xp - current) / (following - current), 1))
        return {"level": level, "currentThreshold": current, "nextThreshold": following,
                "intoLevel": xp - current, "neededInLevel": following - current,
                "percent": percent}


class MoodEngine:
    @staticmethod
    def derive(state: dict, now: datetime, config: dict | None = None) -> str:
        limits = (config or DEFAULT_CONFIG)["moodThresholds"]
        if state["activity"] == "RESTING":
            return "RESTING"
        if state["energy"] <= limits["tiredEnergy"]:
            return "TIRED"
        signal = state.get("recentSignal")
        if signal and parse_time(signal["expiresAt"]) > now:
            if signal["type"] in {"RESTING", "PROUD", "FOCUSED", "EXCITED", "CURIOUS"}:
                return signal["type"]
        if state["happiness"] >= limits["happyHappiness"] and state["energy"] >= limits["happyEnergy"]:
            return "HAPPY"
        if state["curiosity"] >= limits["curiousCuriosity"]:
            return "CURIOUS"
        if state["happiness"] < limits["boredHappiness"]:
            return "BORED"
        return "CALM"


class PersonalityEngine:
    @staticmethod
    def apply(state: dict, action: str, config: dict | None = None) -> None:
        trait, specialty = ACTION_TRAITS.get(action, (None, None))
        if trait:
            state["traits"][trait] = clamp(state["traits"][trait] + (config or DEFAULT_CONFIG)["traitStep"])
        if specialty:
            state["specializationScores"][specialty] += 1

    @staticmethod
    def leading_traits(state: dict) -> list[str]:
        return sorted(TRAITS, key=lambda key: (-state["traits"][key], TRAITS.index(key)))[:2]


class EvolutionEngine:
    @staticmethod
    def stages(config: dict | None = None) -> list[dict]:
        starts = (config or DEFAULT_CONFIG)["stageStarts"]
        return [{**stage, "start": starts[stage["key"]]} for stage in STAGES]

    @classmethod
    def stage(cls, level: int, config: dict | None = None) -> dict:
        return next(stage for stage in reversed(cls.stages(config)) if level >= stage["start"])

    @classmethod
    def crossed_stages(cls, old_level: int, new_level: int, config: dict | None = None) -> list[dict]:
        return [stage for stage in cls.stages(config) if old_level < stage["start"] <= new_level]

    @staticmethod
    def specialization(state: dict, threshold: int) -> str | None:
        scores = state["specializationScores"]
        best = max(scores.values())
        if best < threshold:
            return None
        current = state.get("specialization")
        if current and scores[current] == best:  # stable tie: no spurious evolution
            return current
        return next(key for key in SPECIALIZATIONS if scores[key] == best)


class ActivityEngine:
    @staticmethod
    def apply_effects(state: dict, changes: dict) -> None:
        cost = -min(0, changes.get("energy", 0))
        if state["energy"] < cost:
            raise ConflictError("Energia insuficiente. Descanse um pouco antes de continuar.")
        for attribute, delta in changes.items():
            state[attribute] = clamp(state[attribute] + delta)
