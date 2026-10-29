"""Transactional application service for SL-001.

The public methods are synchronous and atomic. No network calls, LLM, or background
process is needed. Every input ID, XP grant, state update, memory and emitted event
is committed together, so a crash cannot award XP without also saving the state.
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import uuid
from datetime import timedelta
from zoneinfo import ZoneInfo

from .bridge import identifier, normalize_event
from .model import (ACTIONS, AUTONOMOUS_ACTIVITIES, ATTRIBUTES, ActivityEngine,
                    ConflictError, EvolutionEngine, ExperienceEngine, MoodEngine,
                    PersonalityEngine, PetError, clamp, iso, now_utc, parse_time, validate_config)
from .repository import dump

log = logging.getLogger("pet.service")

ACTION_COPY = {
    "PLAY": ("Hora de brincar", "Um momento de brincadeira deixou o habitat mais alegre."),
    "REST": ("Uma pausa tranquila", "SL-001 descansou e recuperou energia."),
    "EXPLORE": ("Uma pequena exploração", "SL-001 explorou um tema da coleção local."),
    "LEARN": ("Aprendizado do dia", "SL-001 praticou uma atividade de aprendizado local."),
    "CREATE": ("Um instante criativo", "SL-001 compôs uma pequena ideia usando combinações locais."),
    "CHAT": ("Um momento juntos", "Uma interação foi registrada, sem guardar o texto da conversa."),
}
ACTION_SIGNAL = {"PLAY": "EXCITED", "REST": "RESTING", "EXPLORE": "CURIOUS", "LEARN": "FOCUSED", "CREATE": "FOCUSED", "CHAT": None}
TOPICS = (
    ("Jardins de luz", "Uma coleção local de ideias sobre brilho, folhas e sombras."),
    ("Nuvens e formas", "Uma brincadeira local de imaginar formas no céu."),
    ("Pequenos mundos", "Uma coleção local de cenários em miniatura."),
    ("Cores do crepúsculo", "Uma paleta local de azul, lilás e dourado."),
)
LESSONS = (
    ("Luz do Sol", "A luz do Sol leva cerca de oito minutos para chegar à Terra."),
    ("Fases da Lua", "As fases da Lua dependem de como vemos sua metade iluminada pelo Sol."),
    ("Plantas", "Na fotossíntese, plantas usam luz para produzir açúcares."),
    ("Água", "A água pode ser encontrada na forma líquida, sólida ou gasosa."),
)
CREATIONS = (
    "Ideia local: um jardim lilás iluminado por estrelas de papel.",
    "Ideia local: uma pequena biblioteca com uma janela para as nuvens.",
    "Ideia local: uma coleção de pedras azuis numa caixa de madeira.",
    "Ideia local: um caminho de lanternas no jardim ao anoitecer.",
)


def _uid(prefix="evt"):
    return f"{prefix}-{uuid.uuid4().hex}"


def _fingerprint(value):
    return hashlib.sha256(dump(value).encode("utf-8")).hexdigest()


class PetEngine:
    def __init__(self, repository, *, clock=now_utc):
        self.repo = repository
        self.clock = clock

    def _begin(self, conn, event_id, event_type, fingerprint, now):
        row = conn.execute("SELECT fingerprint FROM processed_events WHERE event_id=?", (event_id,)).fetchone()
        if row:
            if row["fingerprint"] != fingerprint:
                raise ConflictError("Este eventId já foi utilizado com outro conteúdo.")
            return True
        conn.execute("INSERT INTO processed_events VALUES (?, ?, ?, ?)", (event_id, fingerprint, event_type, iso(now)))
        return False

    @staticmethod
    def _emit(conn, kind, payload, now):
        conn.execute("INSERT INTO pet_events(event_id,event_type,timestamp,source,payload_json) VALUES(?,?,?,?,?)",
                     (_uid("pet"), kind, iso(now), "pet-engine", dump(payload)))

    @staticmethod
    def _memory(conn, kind, title, body, now, event_id=None):
        conn.execute("INSERT INTO memories VALUES(?,?,?,?,?,?)", (_uid("mem"), kind, title, body, iso(now), event_id))

    @staticmethod
    def _signal(state, signal, config, now):
        if signal:
            state["recentSignal"] = {"type": signal, "expiresAt": iso(now + timedelta(minutes=config["signalMinutes"]))}

    @staticmethod
    def _reconcile(state, config, now):
        last = parse_time(state["lastUpdatedAt"])
        # A backwards clock must not turn a later correction into repeatable recovery.
        if now > last:
            hours = min((now - last).total_seconds() / 3600, config["maxElapsedHours"])
            state["energy"] = clamp(state["energy"] + hours * config["passiveEnergyPerHour"])
            state["lastUpdatedAt"] = iso(now)
        if state.get("recentSignal") and parse_time(state["recentSignal"]["expiresAt"]) <= now:
            state["recentSignal"] = None

    @staticmethod
    def _day(config, now):
        return now.astimezone(ZoneInfo(config["autonomy"]["timeZone"])).date().isoformat()

    def _grant(self, conn, state, config, event_id, reason, now, logical_key=None):
        day = self._day(config, now)
        if logical_key and conn.execute("SELECT 1 FROM xp_awards WHERE logical_key=?", (logical_key,)).fetchone():
            return 0
        count = conn.execute("SELECT COUNT(*) FROM xp_awards WHERE day=? AND reason=?", (day, reason)).fetchone()[0]
        total = conn.execute("SELECT COALESCE(SUM(amount),0) FROM xp_awards WHERE day=?", (day,)).fetchone()[0]
        if count >= config["xpDailyLimits"][reason]:
            return 0
        amount = min(config["xpGains"][reason], max(0, config["dailyXpCap"] - total))
        if amount <= 0:
            return 0
        conn.execute("INSERT INTO xp_awards(event_id,reason,amount,day,logical_key,created_at) VALUES(?,?,?,?,?,?)",
                     (event_id, reason, amount, day, logical_key, iso(now)))
        state["xp"] += amount
        return amount

    def _first_interaction(self, conn, state, config, event_id, now):
        return self._grant(conn, state, config, event_id, "FIRST_INTERACTION", now,
                           logical_key=f"first-interaction:{self._day(config, now)}")

    def _finish(self, conn, before, state, config, now):
        old_level = ExperienceEngine.level(before["xp"], config)
        new_level = ExperienceEngine.level(state["xp"], config)
        if new_level > old_level:
            self._emit(conn, "PET_LEVEL_UP", {"fromLevel": old_level, "level": new_level, "xp": state["xp"], "mediaKey": "milestone_video"}, now)
            self._memory(conn, "ACHIEVEMENT", "Um novo nível", f"SL-001 alcançou o nível {new_level}.", now)
            self._signal(state, "PROUD", config, now)
        for stage in EvolutionEngine.crossed_stages(old_level, new_level, config):
            payload = {"axis": "LEVEL", "stage": stage["key"], "name": stage["name"], "reward": stage["reward"], "mediaKey": "milestone_video"}
            self._emit(conn, "PET_EVOLUTION_UNLOCKED", payload, now)
            self._emit(conn, "PET_REWARD_UNLOCKED", {"reward": stage["reward"], "stage": stage["key"]}, now)
            self._memory(conn, "EVOLUTION", f"Evolução: {stage['name']}", f"Novo estágio e recompensa: {stage['reward']}.", now)
        specialty = EvolutionEngine.specialization(state, config["specializationThreshold"])
        if specialty != before.get("specialization"):
            state["specialization"] = specialty
            if specialty:
                self._emit(conn, "PET_EVOLUTION_UNLOCKED", {"axis": "SPECIALIZATION", "specialization": specialty}, now)
                self._memory(conn, "EVOLUTION", "Uma nova tendência", f"A tendência {specialty} se destacou nas atividades locais.", now)
        new_mood = MoodEngine.derive(state, now, config)
        if new_mood != before.get("mood"):
            self._emit(conn, "PET_MOOD_CHANGED", {"fromMood": before.get("mood"), "mood": new_mood}, now)
            self._memory(conn, "MOOD", "Mudança de humor", f"O humor do SL-001 agora é {new_mood}.", now)
        state["mood"] = new_mood
        if state["bond"] != before["bond"]:
            self._emit(conn, "PET_BOND_CHANGED", {"fromBond": before["bond"], "bond": state["bond"]}, now)
        self.repo.save(conn, state, config)

    @staticmethod
    def _public(state, config):
        result = copy.deepcopy(state)
        progress = ExperienceEngine.progress(state["xp"], config)
        result["level"] = progress["level"]
        result["progress"] = progress
        result["stage"] = EvolutionEngine.stage(result["level"], config)
        result["stages"] = EvolutionEngine.stages(config)
        result["leadingTraits"] = PersonalityEngine.leading_traits(state)
        result["rules"] = {"meaningfulChatMinChars": config["meaningfulChatMinChars"]}
        result["autonomy"] = {**config["autonomy"], **state["autonomyState"]}
        return result

    def snapshot(self, *, run_due=True):
        if run_due:
            self.run_due()
        now = self.clock()
        with self.repo.transaction() as conn:
            state, config = self.repo.load(conn)
            before = copy.deepcopy(state)
            self._reconcile(state, config, now)
            self._finish(conn, before, state, config, now)
            return self._public(state, config)

    def perform_action(self, action: str, event_id: str, *, meaningful=False):
        identifier(event_id, "eventId")
        if event_id.startswith("auto:"):
            raise PetError("O prefixo auto: é reservado ao agendador interno.")
        if action not in ACTIONS:
            raise PetError("Ação desconhecida.")
        if not isinstance(meaningful, bool) or (meaningful and action != "CHAT"):
            raise PetError("Indicador de conversa inválido.")
        now = self.clock()
        fingerprint = _fingerprint({"action": action, "meaningful": meaningful})
        with self.repo.transaction() as conn:
            state, config = self.repo.load(conn)
            before = copy.deepcopy(state)
            self._reconcile(state, config, now)
            duplicate = self._begin(conn, event_id, f"ACTION_{action}", fingerprint, now)
            gained = 0
            message = ACTION_COPY[action][1]
            if not duplicate:
                ActivityEngine.apply_effects(state, config["actionEffects"][action])
                self._emit(conn, "PET_ACTIVITY_STARTED", {"activity": action, "inputEventId": event_id}, now)
                PersonalityEngine.apply(state, action, config)
                self._signal(state, ACTION_SIGNAL[action], config, now)
                gained += self._first_interaction(conn, state, config, event_id, now)
                if action == "CHAT" and meaningful:
                    gained += self._grant(conn, state, config, event_id, "CONVERSATION", now)
                elif action == "LEARN":
                    gained += self._grant(conn, state, config, event_id, "LEARN", now)
                    lesson = LESSONS[(state["specializationScores"]["RESEARCHER"] - 1) % len(LESSONS)]
                    message = f"Aprendizado local — {lesson[0]}: {lesson[1]}"
                elif action == "CREATE":
                    gained += self._grant(conn, state, config, event_id, "CREATIVE", now)
                    message = CREATIONS[(state["specializationScores"]["CREATOR"] - 1) % len(CREATIONS)]
                elif action == "EXPLORE":
                    topic = TOPICS[(state["specializationScores"]["EXPLORER"] - 1) % len(TOPICS)]
                    message = f"Descoberta local: {topic[0]}. {topic[1]}"
                self._memory(conn, "INTERACTION" if action == "CHAT" else "ACTIVITY", ACTION_COPY[action][0], message, now, event_id)
                self._emit(conn, "PET_ACTIVITY_COMPLETED", {"activity": action, "inputEventId": event_id, "xpAwarded": gained}, now)
            self._finish(conn, before, state, config, now)
            return {"duplicate": duplicate, "xpAwarded": gained, "message": message if not duplicate else "Evento já processado.", "state": self._public(state, config)}

    def process_muse_event(self, event):
        event = normalize_event(event)
        event_id, kind, payload = event["eventId"], event["eventType"], event["payload"]
        now = self.clock()
        fingerprint = _fingerprint({"type": kind, "source": event["source"], "payload": payload, "timestamp": event["timestamp"]})
        with self.repo.transaction() as conn:
            state, config = self.repo.load(conn)
            before = copy.deepcopy(state)
            self._reconcile(state, config, now)
            duplicate = self._begin(conn, event_id, kind, fingerprint, now)
            logical_duplicate = False
            gained = 0
            # Protect one completed task/goal/skill/milestone even if an upstream
            # producer retries with a different event ID. IDs are scoped by source.
            logical_fields = {"AGENT_TASK_COMPLETED": "taskId", "GOAL_COMPLETED": "goalId",
                              "MILESTONE_ACHIEVED": "milestoneId"}
            if kind == "TOOL_EXECUTION_COMPLETED" and payload.get("isNew"):
                logical_fields[kind] = "skillId"
            if not duplicate and kind in logical_fields:
                logical_key = _fingerprint({"source": event["source"], "id": payload[logical_fields[kind]]})
                cursor = conn.execute("INSERT OR IGNORE INTO logical_events(event_type,logical_key) VALUES (?,?)", (kind, logical_key))
                logical_duplicate = cursor.rowcount == 0
            if not duplicate and not logical_duplicate:
                if kind == "CHAT_MESSAGE_SENT":
                    ActivityEngine.apply_effects(state, config["actionEffects"]["CHAT"])
                    PersonalityEngine.apply(state, "CHAT", config)
                    gained += self._first_interaction(conn, state, config, event_id, now)
                    if payload.get("meaningful"):
                        gained += self._grant(conn, state, config, event_id, "CONVERSATION", now)
                    self._memory(conn, "INTERACTION", "Um momento juntos", "A ponte recebeu uma interação; o texto não foi armazenado.", now, event_id)
                elif kind == "AGENT_TASK_STARTED":
                    self._signal(state, "FOCUSED", config, now)
                elif kind in {"AGENT_TASK_COMPLETED", "GOAL_COMPLETED", "MILESTONE_ACHIEVED"}:
                    reason = {"AGENT_TASK_COMPLETED": "TASK", "GOAL_COMPLETED": "GOAL", "MILESTONE_ACHIEVED": "MILESTONE"}[kind]
                    gained += self._grant(conn, state, config, event_id, reason, now)
                    PersonalityEngine.apply(state, "TASK", config)
                    self._signal(state, "PROUD", config, now)
                    self._memory(conn, "ACHIEVEMENT", "Conquista compartilhada", "Uma conclusão confirmada foi recebida pela ponte local.", now, event_id)
                    if kind == "MILESTONE_ACHIEVED":
                        self._emit(conn, "PET_REWARD_UNLOCKED", {"reward": "Marco compartilhado", "mediaKey": "milestone_video", "inputEventId": event_id}, now)
                elif kind == "TOOL_EXECUTION_COMPLETED" and payload.get("isNew"):
                    gained += self._grant(conn, state, config, event_id, "SKILL", now)
                    self._memory(conn, "ACHIEVEMENT", "Nova habilidade", "Uma nova habilidade confirmada foi utilizada.", now, event_id)
                # Approval rejection / failures never penalize the user or pet.
            self._finish(conn, before, state, config, now)
            return {"duplicate": duplicate or logical_duplicate, "duplicateKind": "eventId" if duplicate else ("logical" if logical_duplicate else None),
                    "xpAwarded": gained, "state": self._public(state, config)}

    def _perform_auto(self, conn, state, config, kind, event_id, now, *, scheduled):
        cost = config["autonomyEnergyCost"][kind]
        if state["energy"] < cost:
            raise ConflictError("Energia insuficiente para a atividade. Descanse antes de tentar.")
        state["energy"] = clamp(state["energy"] - cost)
        ActivityEngine.apply_effects(state, config["autonomyEffects"][kind])
        self._emit(conn, "PET_ACTIVITY_STARTED", {"activity": kind, "scheduled": scheduled, "inputEventId": event_id}, now)
        PersonalityEngine.apply(state, kind, config)
        gained = 0
        if kind == "DREAM":
            counts = conn.execute("SELECT COUNT(*) FROM memories WHERE kind IN ('ACTIVITY','INTERACTION','EVOLUTION','ACHIEVEMENT')").fetchone()[0]
            title, summary, memory_kind = "Um sonho tranquilo", f"Resumo local: {counts} registros de convivência e evolução foram encontrados. Nenhum fato sobre o usuário foi criado.", "DIARY"
            self._signal(state, "RESTING", config, now)
        elif kind == "EXPLORE":
            index = (state["specializationScores"]["EXPLORER"] - 1) % len(TOPICS)
            topic = TOPICS[index]
            title, summary, memory_kind = "Descoberta local", f"{topic[0]}: {topic[1]} Não houve pesquisa na internet.", "DISCOVERY"
            self._signal(state, "CURIOUS", config, now)
        elif kind == "EXPERIMENT":
            index = (state["specializationScores"]["CREATOR"] - 1) % len(CREATIONS)
            title, summary, memory_kind = "Experimento criativo", CREATIONS[index] + " Gerado por uma lista local, sem IA.", "ACTIVITY"
            gained += self._grant(conn, state, config, event_id, "CREATIVE", now)
            self._signal(state, "FOCUSED", config, now)
        else:
            title, summary, memory_kind = "Página do diário", f"Registro local: nível {ExperienceEngine.level(state['xp'], config)}, energia {round(state['energy'])} e vínculo {round(state['bond'])}.", "DIARY"
            self._signal(state, "FOCUSED", config, now)
        self._memory(conn, memory_kind, title, summary, now, event_id)
        conn.execute("INSERT INTO autonomy_history VALUES(?,?,?,?,?,?)", (_uid("run"), kind, "COMPLETED", summary, iso(now), int(scheduled)))
        self._emit(conn, "PET_ACTIVITY_COMPLETED", {"activity": kind, "scheduled": scheduled, "inputEventId": event_id, "xpAwarded": gained}, now)
        return summary, gained

    def run_activity(self, kind, event_id):
        identifier(event_id, "eventId")
        if event_id.startswith("auto:"):
            raise PetError("O prefixo auto: é reservado ao agendador interno.")
        if kind not in AUTONOMOUS_ACTIVITIES:
            raise PetError("Atividade autônoma desconhecida.")
        now = self.clock()
        with self.repo.transaction() as conn:
            state, config = self.repo.load(conn)
            before = copy.deepcopy(state)
            self._reconcile(state, config, now)
            duplicate = self._begin(conn, event_id, f"AUTO_{kind}", _fingerprint({"autonomy": kind}), now)
            summary, gained = "Evento já processado.", 0
            if not duplicate:
                summary, gained = self._perform_auto(conn, state, config, kind, event_id, now, scheduled=False)
            self._finish(conn, before, state, config, now)
            return {"duplicate": duplicate, "message": summary, "xpAwarded": gained, "state": self._public(state, config)}

    @staticmethod
    def _resting(config, now):
        auto = config["autonomy"]
        hour = now.astimezone(ZoneInfo(auto["timeZone"])).hour
        start, end = auto["restStartHour"], auto["restEndHour"]
        if start == end:  # equal means no rest window; avoids surprising 24h lockout
            return False
        return start <= hour < end if start < end else (hour >= start or hour < end)

    def run_due(self):
        """At most one missed activity; no background loop, no replay burst."""
        now = self.clock()
        try:
            with self.repo.transaction() as conn:
                state, config = self.repo.load(conn)
                auto = config["autonomy"]
                due = state["autonomyState"].get("nextRunAt")
                if not auto["enabled"] or not due or parse_time(due) > now or self._resting(config, now):
                    return False
                before = copy.deepcopy(state)
                self._reconcile(state, config, now)
                kind = AUTONOMOUS_ACTIVITIES[state["autonomyState"]["cursor"] % len(AUTONOMOUS_ACTIVITIES)]
                event_id = "auto:" + due
                duplicate = self._begin(conn, event_id, f"SCHEDULED_{kind}", _fingerprint({"due": due}), now)
                if not duplicate and state["energy"] >= config["autonomyEnergyCost"][kind]:
                    self._perform_auto(conn, state, config, kind, event_id, now, scheduled=True)
                elif not duplicate:
                    conn.execute("INSERT INTO autonomy_history VALUES(?,?,?,?,?,?)", (_uid("run"), kind, "SKIPPED", "Ciclo adiado por energia insuficiente.", iso(now), 1))
                state["autonomyState"]["lastRunAt"] = iso(now)
                state["autonomyState"]["nextRunAt"] = iso(now + timedelta(minutes=auto["intervalMinutes"]))
                state["autonomyState"]["cursor"] += 1
                self._finish(conn, before, state, config, now)
                return True
        except Exception as exc:
            # A transaction rollback leaves the original due intact. Best-effort
            # failure history and retry backoff; an unavailable DB may prevent both.
            log.exception("autonomy_cycle_failed")
            try:
                with self.repo.transaction() as conn:
                    state, config = self.repo.load(conn)
                    if config["autonomy"]["enabled"]:
                        conn.execute("INSERT INTO autonomy_history VALUES(?,?,?,?,?,?)", (_uid("run"), "SCHEDULED", "FAILED", "Falha local; uma nova tentativa foi agendada.", iso(now), 1))
                        state["autonomyState"]["nextRunAt"] = iso(now + timedelta(minutes=min(15, config["autonomy"]["intervalMinutes"])))
                        self.repo.save(conn, state, config)
            except Exception:
                log.exception("autonomy_failure_record_unavailable")
            raise exc

    def get_config(self):
        with self.repo.transaction() as conn:
            _, config = self.repo.load(conn)
            return config

    def update_config(self, proposed):
        config_new = validate_config(proposed)
        now = self.clock()
        with self.repo.transaction() as conn:
            state, config = self.repo.load(conn)
            if state["xp"] and (config_new["xpFormula"] != config["xpFormula"] or config_new["stageStarts"] != config["stageStarts"]):
                raise ConflictError("Fórmula e faixas ficam bloqueadas após ganhar XP para evitar perda arbitrária de níveis.")
            before = copy.deepcopy(state)
            self._reconcile(state, config, now)
            old_auto, new_auto = config["autonomy"], config_new["autonomy"]
            if not new_auto["enabled"]:
                state["autonomyState"]["nextRunAt"] = None  # cancellation of future work
            elif not old_auto["enabled"] or old_auto["intervalMinutes"] != new_auto["intervalMinutes"]:
                state["autonomyState"]["nextRunAt"] = iso(now + timedelta(minutes=new_auto["intervalMinutes"]))
            if old_auto["enabled"] != new_auto["enabled"]:
                self._memory(conn, "PREFERENCE", "Autonomia atualizada", "Atividades locais ativadas." if new_auto["enabled"] else "Atividades locais desativadas.", now)
            self._finish(conn, before, state, config_new, now)
            return {"config": config_new, "state": self._public(state, config_new)}

    def customize(self, patch):
        allowed = {"theme": {"LAVENDER", "SKY", "DUSK", "AURORA"}, "decoration": {"STARS", "LEAVES", "NONE", "HALO", "CONSTELLATION"}, "playerFit": {"FIT", "FILL"}}
        if not isinstance(patch, dict) or not patch or set(patch) - set(allowed):
            raise PetError("Personalização inválida.")
        if any(value not in allowed[key] for key, value in patch.items()):
            raise PetError("Opção de personalização desconhecida.")
        now = self.clock()
        with self.repo.transaction() as conn:
            state, config = self.repo.load(conn)
            level = ExperienceEngine.level(state["xp"], config)
            locks = {("theme", "AURORA"): "EXPLORER", ("decoration", "HALO"): "COMPANION", ("decoration", "CONSTELLATION"): "EVOLVED"}
            for (key, value), stage_key in locks.items():
                if patch.get(key) == value and level < config["stageStarts"][stage_key]:
                    raise ConflictError(f"Esta recompensa será desbloqueada no nível {config['stageStarts'][stage_key]}.")
            before = copy.deepcopy(state)
            self._reconcile(state, config, now)
            state["habitat"].update(patch)
            self._memory(conn, "PREFERENCE", "Habitat personalizado", "As camadas decorativas do habitat foram atualizadas; a mídia do personagem não foi alterada.", now)
            self._finish(conn, before, state, config, now)
            return self._public(state, config)

    def memories_page(self, *, limit=200, offset=0):
        """Read a memory page and its total from the same SQLite snapshot."""
        limit, offset = max(1, min(int(limit), 500)), max(0, int(offset))
        with self.repo.transaction() as conn:
            rows = conn.execute("SELECT id,kind,title,body,created_at AS createdAt FROM memories ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
            total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            return [dict(row) for row in rows], total

    def memories(self, *, limit=200, offset=0):
        return self.memories_page(limit=limit, offset=offset)[0]

    def memory_count(self):
        with self.repo.transaction() as conn:
            return conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

    def delete_memories(self, memory_id=None):
        if memory_id is not None:
            identifier(memory_id, "memoryId")
        with self.repo.transaction() as conn:
            result = conn.execute("DELETE FROM memories" if memory_id is None else "DELETE FROM memories WHERE id=?", () if memory_id is None else (memory_id,))
            return result.rowcount

    def event_cursor(self):
        """Mark the end of committed history without replaying every old event."""
        with self.repo.transaction() as conn:
            return conn.execute("SELECT COALESCE(MAX(seq), 0) FROM pet_events").fetchone()[0]

    def events(self, *, after=0, limit=100):
        after, limit = max(0, int(after)), max(1, min(int(limit), 500))
        with self.repo.transaction() as conn:
            rows = conn.execute("SELECT seq,event_id AS eventId,event_type AS eventType,timestamp,source,payload_json FROM pet_events WHERE seq>? ORDER BY seq ASC LIMIT ?", (after, limit)).fetchall()
            return [{**{k: row[k] for k in row.keys() if k != "payload_json"}, "payload": json.loads(row["payload_json"])} for row in rows]

    def awards_page(self, *, limit=100, offset=0):
        """Read a page and its total in one transaction, without changing the ledger."""
        limit, offset = max(1, min(int(limit), 501)), max(0, int(offset))
        with self.repo.transaction() as conn:
            rows = conn.execute("SELECT event_id AS eventId,reason,amount,day,created_at AS createdAt FROM xp_awards ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
            total = conn.execute("SELECT COUNT(*) FROM xp_awards").fetchone()[0]
            return [dict(row) for row in rows], total

    def awards(self, *, limit=100, offset=0):
        return self.awards_page(limit=limit, offset=offset)[0]

    def autonomy_history(self, *, limit=100, offset=0):
        limit, offset = max(1, min(int(limit), 501)), max(0, int(offset))
        with self.repo.transaction() as conn:
            rows = conn.execute("SELECT id,activity,status,summary,created_at AS createdAt,scheduled FROM autonomy_history ORDER BY rowid DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
            return [{**dict(row), "scheduled": bool(row["scheduled"])} for row in rows]
