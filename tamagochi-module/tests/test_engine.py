from __future__ import annotations

import copy
import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path
from unittest.mock import patch

from pet.bridge import BridgePolicy, INPUT_EVENTS, OUTPUT_EVENTS, MusePetBridge, normalize_event
from pet.model import (ATTRIBUTES, DEFAULT_CONFIG, ConflictError, EvolutionEngine,
                       ExperienceEngine, MoodEngine, PetError, clamp, iso, validate_config)
from pet.repository import PetRepository
from pet.service import PetEngine

FIXTURES = Path(__file__).parent / 'fixtures'


class FakeClock:
    def __init__(self):
        self.now = datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc)
    def __call__(self):
        return self.now
    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'pet.sqlite3'
        self.clock = FakeClock()
        self.repo = PetRepository(self.path, clock=self.clock)
        self.engine = PetEngine(self.repo, clock=self.clock)
        # Contract tests deliberately enable both scopes using an isolated test key.
        self.bridge_token = 'B' * 43
        policy = BridgePolicy(self.bridge_token)
        policy.set_consent({'receiveEvents': True, 'shareData': True})
        self.bridge = MusePetBridge(self.engine, policy)
        self.receive = partial(self.bridge.receive, credential=self.bridge_token)
        self.outgoing = partial(self.bridge.outgoing, credential=self.bridge_token)
        self.context = partial(self.bridge.context, credential=self.bridge_token)

    def tearDown(self):
        self.temp.cleanup()

    def state(self):
        return self.engine.snapshot(run_due=False)

    def modify_state(self, **fields):
        with self.repo.transaction() as conn:
            state, config = self.repo.load(conn)
            state.update(fields)
            self.repo.save(conn, state, config)

    def event(self, kind='AGENT_TASK_COMPLETED', id='event-1', payload=None, source='muse-agent'):
        return {'eventId':id, 'eventType':kind, 'timestamp':iso(self.clock()), 'source':source,
                'payload':payload if payload is not None else {'taskId':'task-1','success':True}}

    def enable_auto(self, *, interval=15, rest_start=22, rest_end=8):
        config = self.engine.get_config()
        config['autonomy'].update(enabled=True, intervalMinutes=interval, restStartHour=rest_start, restEndHour=rest_end)
        self.engine.update_config(config)

    def test_01_creation_values_and_schema(self):
        state = self.state()
        self.assertEqual((state['petId'], state['xp'], state['level'], state['mood'], state['activity']), ('SL-001', 0, 1, 'CALM', 'IDLE'))
        self.assertEqual({a: state[a] for a in ATTRIBUTES}, DEFAULT_CONFIG['initialAttributes'])
        self.assertEqual(state['stage']['key'], 'AWAKENING')
        self.assertEqual(self.repo.integrity(), 'ok')
        with self.repo.connect() as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], 2)

    def test_01b_versioned_config_migration_preserves_state(self):
        self.engine.perform_action('PLAY','before-upgrade')
        with self.repo.connect() as conn:
            row = conn.execute("SELECT config_json FROM pet WHERE pet_id='SL-001'").fetchone()
            config = json.loads(row['config_json'])
            del config['meaningfulChatMinChars']
            conn.execute("UPDATE pet SET config_json=? WHERE pet_id='SL-001'",(json.dumps(config),))
            conn.execute('PRAGMA user_version=1')
        upgraded=PetEngine(PetRepository(self.path,clock=self.clock),clock=self.clock)
        self.assertEqual(upgraded.get_config()['meaningfulChatMinChars'],30)
        self.assertEqual(upgraded.snapshot(run_due=False)['xp'],5)
        with upgraded.repo.connect() as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],2)

    def test_02_persist_and_restart(self):
        self.engine.perform_action('PLAY', 'play-1')
        self.engine.customize({'theme':'SKY','decoration':'LEAVES','playerFit':'FILL'})
        restarted = PetEngine(PetRepository(self.path, clock=self.clock), clock=self.clock)
        self.assertEqual(restarted.snapshot(run_due=False)['xp'], 5)
        self.assertEqual(restarted.snapshot(run_due=False)['habitat']['theme'], 'SKY')
        self.assertEqual(restarted.perform_action('PLAY', 'play-1')['duplicate'], True)
        self.assertGreater(len(restarted.memories()), 0)

    def test_02b_chat_state_survives_restart_and_mood_signal_expires(self):
        # Same private database, fixed test clock; no message content enters the engine.
        self.engine.perform_action('PLAY', 'session-play')
        before = self.engine.perform_action('CHAT', 'session-chat', meaningful=True)['state']
        self.assertEqual((before['xp'], before['level'], before['stage']['key'], before['mood']), (7, 1, 'AWAKENING', 'EXCITED'))
        self.assertEqual(tuple(before[key] for key in ATTRIBUTES), (85, 70, 50, 10, 25, 52))
        self.assertEqual(before['recentSignal']['type'], 'EXCITED')

        restarted = PetEngine(PetRepository(self.path, clock=self.clock), clock=self.clock)
        restored = restarted.snapshot(run_due=False)
        for key in (*ATTRIBUTES, 'xp', 'level', 'stage', 'mood', 'recentSignal', 'traits', 'specializationScores'):
            self.assertEqual(restored[key], before[key], f'{key} preserved across engine instances')
        self.assertEqual({(item['reason'], item['amount']) for item in restarted.awards()}, {('FIRST_INTERACTION', 5), ('CONVERSATION', 2)})
        memory_count = len(restarted.memories())
        self.assertTrue(any(item['title'] == 'Um momento juntos' for item in restarted.memories()))
        retry = restarted.perform_action('CHAT', 'session-chat', meaningful=True)
        self.assertTrue(retry['duplicate'])
        self.assertEqual(retry['xpAwarded'], 0)
        self.assertEqual(retry['state']['bond'], before['bond'])
        self.assertEqual(len(restarted.memories()), memory_count)

        # A transient mood is recalculated rather than frozen forever after login.
        self.clock.advance(minutes=21)
        later = restarted.snapshot(run_due=False)
        self.assertEqual((later['mood'], later['recentSignal']), ('CALM', None))
        self.assertEqual(later['energy'], 70.175)
        self.assertEqual(tuple(later[key] for key in ('happiness', 'curiosity', 'knowledge', 'bond', 'trust', 'xp')), (85, 50, 10, 25, 52, 7))

    def test_02c_latest_ui_event_cursor_tracks_only_committed_events(self):
        self.assertEqual(self.engine.event_cursor(), 0)
        self.engine.perform_action('PLAY', 'cursor-play')
        first = self.engine.event_cursor()
        self.assertGreater(first, 0)
        self.assertEqual(first, self.engine.events()[-1]['seq'])
        self.assertTrue(self.engine.perform_action('PLAY', 'cursor-play')['duplicate'])
        self.assertEqual(self.engine.event_cursor(), first)
        self.engine.perform_action('REST', 'cursor-rest')
        later = self.engine.events(after=first)
        self.assertTrue(later)
        self.assertEqual(self.engine.event_cursor(), later[-1]['seq'])
        self.assertTrue(all(event['seq'] > first for event in later))

    def test_03_mood_is_derived_and_stable(self):
        original = self.state()
        self.assertEqual([MoodEngine.derive(original, self.clock()) for _ in range(10)], ['CALM'] * 10)
        self.modify_state(energy=20)
        self.assertEqual(self.state()['mood'], 'TIRED')
        self.engine.perform_action('REST', 'rest-1')
        self.assertEqual(self.state()['mood'], 'RESTING')
        self.clock.advance(minutes=21)
        self.assertEqual(self.state()['mood'], 'CALM')
        self.assertTrue(any(e['eventType']=='PET_MOOD_CHANGED' for e in self.engine.events()))

    def test_04_play_consumes_and_rest_recovers(self):
        p = self.engine.perform_action('PLAY','p1')['state']
        self.assertEqual((p['energy'], p['happiness'], p['bond']), (70, 83, 23))
        r = self.engine.perform_action('REST','r1')['state']
        self.assertEqual(r['energy'], 90)
        self.assertEqual(r['mood'], 'RESTING')

    def test_05_attribute_bounds_and_no_death(self):
        self.modify_state(happiness=99, bond=99, trust=99, energy=100, curiosity=99, knowledge=99)
        self.engine.perform_action('PLAY','p1')
        self.engine.perform_action('REST','r1')
        self.engine.perform_action('LEARN','l1')
        result = self.state()
        for attribute in ATTRIBUTES:
            self.assertGreaterEqual(result[attribute], 0)
            self.assertLessEqual(result[attribute], 100)
        self.assertEqual(result['petId'],'SL-001')
        self.assertEqual(clamp(-10),0)
        self.assertEqual(clamp(300),100)

    def test_06_insufficient_energy_rolls_back_and_retry_works(self):
        self.modify_state(energy=1)
        self.state()  # reconcile the deliberately edited state first
        baseline = self.engine.events()
        with self.assertRaises(ConflictError):
            self.engine.perform_action('PLAY','same-id')
        self.assertEqual(self.state()['xp'],0)
        self.assertEqual(self.engine.events(),baseline)
        self.engine.perform_action('REST','rest')
        self.assertFalse(self.engine.perform_action('PLAY','same-id')['duplicate'])

    def test_07_xp_formula_and_levels(self):
        self.assertEqual([ExperienceEngine.threshold(n) for n in range(1,7)], [0,100,283,520,800,1118])
        for xp, level in [(0,1),(99,1),(100,2),(282,2),(283,3),(519,3),(520,4),(800,5),(10**8,10001)]:
            with self.subTest(xp=xp):
                self.assertEqual(ExperienceEngine.level(xp),level)
        self.assertEqual(ExperienceEngine.progress(150)['intoLevel'],50)
        with self.assertRaises(PetError): ExperienceEngine.level(-1)

    def test_08_first_interaction_once_per_local_day(self):
        self.assertEqual(self.engine.perform_action('REST','one')['xpAwarded'],5)
        self.assertEqual(self.engine.perform_action('REST','two')['xpAwarded'],0)
        self.clock.advance(days=1)
        self.assertEqual(self.engine.perform_action('REST','three')['xpAwarded'],5)
        self.assertEqual(len(self.engine.awards()),2)

    def test_09_repeat_xp_caps(self):
        for i in range(10):
            self.engine.perform_action('REST',f'r-{i}')
            self.engine.perform_action('LEARN',f'l-{i}')
        awards = self.engine.awards()
        self.assertEqual(sum(a['reason']=='LEARN' for a in awards),5)
        self.assertEqual(self.state()['xp'],45)  # first interaction + five learning awards

    def test_10_total_daily_cap_and_partial_award(self):
        config=self.engine.get_config(); config['dailyXpCap']=12; self.engine.update_config(config)
        result=self.engine.perform_action('LEARN','learn')
        self.assertEqual(result['xpAwarded'],12)
        self.assertEqual(self.engine.perform_action('CREATE','create')['xpAwarded'],0)
        self.assertEqual(self.state()['xp'],12)

    def test_11_meaningful_chat_cap_and_no_text(self):
        for i in range(6):
            self.engine.perform_action('CHAT',f'chat-{i}',meaningful=True)
        self.assertEqual(self.state()['xp'],11)
        self.assertEqual(sum(a['reason']=='CONVERSATION' for a in self.engine.awards()),3)
        self.assertIn('sem guardar o texto', ' '.join(x['body'] for x in self.engine.memories()))

    def test_12_event_idempotency_and_conflicting_reuse(self):
        e=self.event(); first=self.receive(e); again=self.receive(e)
        self.assertEqual(first['xpAwarded'],15)
        self.assertTrue(again['duplicate'])
        self.assertEqual(again['xpAwarded'],0)
        other=copy.deepcopy(e); other['payload']['taskId']='task-2'
        with self.assertRaises(ConflictError): self.receive(other)
        self.assertEqual(self.state()['xp'],15)

    def test_13_logical_idempotency_across_distinct_event_ids(self):
        self.receive(self.event(id='event-1'))
        repeated=self.receive(self.event(id='event-2'))
        self.assertEqual(repeated['duplicateKind'],'logical')
        self.assertEqual(self.state()['xp'],15)
        # Identifiers with colons are unambiguous across source and entity ID.
        self.receive(self.event(id='event-3', source='a:b', payload={'taskId':'c','success':True}))
        self.receive(self.event(id='event-4', source='a', payload={'taskId':'b:c','success':True}))
        self.assertEqual(self.state()['xp'],45)

    def test_14_concurrent_duplicate_is_atomic(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda _: self.engine.perform_action('LEARN','one-concurrent-id'), range(20)))
        self.assertEqual(sum(not r['duplicate'] for r in results),1)
        self.assertEqual(self.state()['xp'],13)
        self.assertEqual(len(self.engine.awards()),2)
        self.assertEqual(self.repo.integrity(),'ok')

    def test_15_completion_requires_explicit_success(self):
        with self.assertRaises(PetError): self.receive(self.event(payload={'taskId':'x','success':False}))
        with self.assertRaises(PetError): self.receive(self.event(payload={'taskId':'x'}))
        with self.assertRaises(PetError): self.receive(self.event('MILESTONE_ACHIEVED', payload={'milestoneId':'m','confirmed':False}))
        self.assertEqual(self.state()['xp'],0)

    def test_16_stage_evolution_and_milestone_outbox(self):
        self.modify_state(xp=799)
        self.receive(self.event())
        self.assertEqual(self.state()['level'],5)
        self.assertEqual(self.state()['stage']['key'],'DISCOVERY')
        events=self.engine.events()
        self.assertTrue(any(e['eventType']=='PET_LEVEL_UP' and e['payload']['mediaKey']=='milestone_video' for e in events))
        self.assertTrue(any(e['eventType']=='PET_EVOLUTION_UNLOCKED' and e['payload']['stage']=='DISCOVERY' for e in events))
        self.assertTrue(any(e['eventType']=='PET_REWARD_UNLOCKED' for e in events))
        self.assertTrue(any(m['kind']=='EVOLUTION' for m in self.engine.memories()))
        restarted=PetEngine(PetRepository(self.path,clock=self.clock),clock=self.clock)
        self.assertEqual(restarted.snapshot(run_due=False)['stage']['key'],'DISCOVERY')
        self.assertTrue(restarted.process_muse_event(self.event())['duplicate'])
        self.assertEqual(len([e for e in restarted.events() if e['eventType']=='PET_LEVEL_UP']),1)

    def test_17_specialization_independent_of_level(self):
        for i in range(3): self.engine.perform_action('EXPLORE',f'e-{i}')
        self.assertEqual(self.state()['specialization'],'EXPLORER')
        for i in range(3): self.engine.perform_action('CREATE',f'c-{i}')
        self.assertEqual(self.state()['specialization'],'EXPLORER')  # stable tie
        self.engine.perform_action('CREATE','c-4')
        self.assertEqual(self.state()['specialization'],'CREATOR')
        self.assertEqual(self.state()['level'],1)
        self.assertEqual(len([e for e in self.engine.events() if e['eventType']=='PET_EVOLUTION_UNLOCKED' and e['payload']['axis']=='SPECIALIZATION']),2)

    def test_18_autonomy_activities_local_and_persistent(self):
        with patch('socket.create_connection', side_effect=AssertionError('network forbidden')):
            for activity in ('DREAM','EXPLORE','EXPERIMENT','JOURNAL'):
                self.assertFalse(self.engine.run_activity(activity, f'auto-{activity}')['duplicate'])
        history=self.engine.autonomy_history()
        self.assertEqual(len(history),4)
        self.assertTrue(all(h['status']=='COMPLETED' and not h['scheduled'] for h in history))
        self.assertTrue(any('sem IA' in m['body'] for m in self.engine.memories()))
        self.assertTrue(any('Nenhum fato sobre o usuário' in m['body'] for m in self.engine.memories()))
        self.assertTrue(self.engine.run_activity('DREAM','auto-DREAM')['duplicate'])
        self.assertEqual(len(PetEngine(PetRepository(self.path,clock=self.clock),clock=self.clock).autonomy_history()),4)

    def test_19_autonomy_scheduler_respects_rest_and_runs_one_after_absence(self):
        self.enable_auto(rest_start=13,rest_end=14)
        self.clock.advance(hours=1)  # 13:00 Fortaleza, in rest window
        self.assertFalse(self.engine.run_due())
        self.clock.advance(days=15,hours=1)  # 14:00, far overdue
        self.assertTrue(self.engine.run_due())
        self.assertFalse(self.engine.run_due())
        self.assertEqual(len(self.engine.autonomy_history()),1)
        self.assertTrue(self.engine.autonomy_history()[0]['scheduled'])

    def test_20_disable_cancels_future_cycle(self):
        self.enable_auto(); self.clock.advance(minutes=16)
        config=self.engine.get_config(); config['autonomy']['enabled']=False; self.engine.update_config(config)
        self.assertFalse(self.engine.run_due())
        self.assertIsNone(self.state()['autonomy']['nextRunAt'])
        self.assertEqual(self.engine.autonomy_history(),[])

    def test_21_low_energy_scheduler_records_skip(self):
        self.enable_auto(); self.modify_state(energy=0)
        self.clock.advance(minutes=16)
        self.assertTrue(self.engine.run_due())
        self.assertEqual(self.engine.autonomy_history()[0]['status'],'SKIPPED')
        self.assertEqual(self.state()['xp'],0)

    def test_22_failure_rolls_back_and_scheduler_retries(self):
        self.enable_auto(); self.clock.advance(minutes=16)
        with patch.object(self.engine,'_perform_auto',side_effect=RuntimeError('simulated crash')):
            with self.assertLogs('pet.service',level='ERROR'):
                with self.assertRaises(RuntimeError): self.engine.run_due()
        self.assertEqual(self.engine.autonomy_history()[0]['status'],'FAILED')
        self.assertEqual(self.state()['xp'],0)
        self.clock.advance(minutes=16)
        self.assertTrue(self.engine.run_due())
        self.assertEqual([h['status'] for h in self.engine.autonomy_history()],['COMPLETED','FAILED'])

    def test_23_abrupt_interruption_rolls_back_and_replays_due(self):
        self.enable_auto(); self.clock.advance(minutes=16)
        due=self.state()['autonomy']['nextRunAt']
        with patch.object(self.engine,'_perform_auto',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.engine.run_due()
        self.assertEqual(self.state()['autonomy']['nextRunAt'],due)
        self.assertTrue(self.engine.run_due())
        self.assertEqual(len(self.engine.autonomy_history()),1)

    def test_24_storage_failure_does_not_commit_partial_event(self):
        with patch.object(self.repo,'save',side_effect=sqlite3.OperationalError('disk full')):
            with self.assertRaises(sqlite3.OperationalError): self.engine.perform_action('LEARN','retry-me')
        self.assertEqual(self.state()['xp'],0)
        self.assertEqual(self.engine.awards(),[])
        self.assertEqual(self.engine.events(),[])
        self.assertFalse(self.engine.perform_action('LEARN','retry-me')['duplicate'])
        self.assertEqual(self.state()['xp'],13)

    def test_25_long_absence_is_bounded_and_nonpunitive(self):
        self.modify_state(energy=10,happiness=75,bond=20)
        self.clock.advance(days=3650)
        after=self.state()
        self.assertEqual(after['energy'],22)
        self.assertEqual((after['happiness'],after['bond']), (75,20))
        self.assertEqual(after['petId'],'SL-001')
        self.assertEqual(self.state()['energy'],22)

    def test_26_clock_reversal_cannot_farm_energy(self):
        self.modify_state(energy=10)
        self.clock.advance(hours=2); self.assertEqual(self.state()['energy'],11)
        self.clock.advance(hours=-1); self.assertEqual(self.state()['energy'],11)
        self.clock.advance(hours=1); self.assertEqual(self.state()['energy'],11)
        self.clock.advance(hours=1); self.assertEqual(self.state()['energy'],11.5)

    def test_27_configuration_is_persisted_and_validated(self):
        config=self.engine.get_config(); config['xpGains']['LEARN']=9; config['passiveEnergyPerHour']=1
        self.engine.update_config(config)
        self.assertEqual(PetEngine(PetRepository(self.path,clock=self.clock),clock=self.clock).get_config()['xpGains']['LEARN'],9)
        self.assertEqual(self.engine.perform_action('LEARN','l')['xpAwarded'],14)
        with self.assertRaises(ConflictError):
            config['xpFormula']['scale']=200; self.engine.update_config(config)
        invalid=copy.deepcopy(DEFAULT_CONFIG); invalid['autonomy']['intervalMinutes']=1
        with self.assertRaises(PetError): validate_config(invalid)
        invalid=copy.deepcopy(DEFAULT_CONFIG); invalid['xpGains']['LEARN']=float('nan')
        with self.assertRaises(PetError): validate_config(invalid)

    def test_28_formula_and_stages_are_configurable_before_xp(self):
        config=self.engine.get_config(); config['xpFormula']['scale']=200; config['stageStarts']['DISCOVERY']=6
        self.engine.update_config(config)
        self.assertEqual(self.state()['progress']['nextThreshold'],200)
        self.assertEqual(EvolutionEngine.stage(5,config)['key'],'AWAKENING')

    def test_28b_custom_initial_configuration_and_reserved_ids(self):
        custom = copy.deepcopy(DEFAULT_CONFIG)
        custom['initialAttributes']['energy'] = 37
        custom['xpFormula']['scale'] = 200
        path = Path(self.temp.name) / 'custom.sqlite3'
        custom_repo = PetRepository(path, clock=self.clock, initial_config=custom)
        custom_engine = PetEngine(custom_repo, clock=self.clock)
        self.assertEqual(custom_engine.snapshot(run_due=False)['energy'], 37)
        self.assertEqual(custom_engine.snapshot(run_due=False)['progress']['nextThreshold'], 200)
        reopened = PetRepository(path, clock=self.clock, initial_config=DEFAULT_CONFIG)
        self.assertEqual(PetEngine(reopened,clock=self.clock).get_config()['xpFormula']['scale'], 200)
        with self.assertRaises(PetError): self.engine.perform_action('REST','auto:reserved')
        with self.assertRaises(PetError): self.receive(self.event(id='auto:reserved'))

    def test_29_customization_is_persisted_and_validated(self):
        self.engine.customize({'theme':'DUSK','decoration':'NONE','playerFit':'FILL'})
        self.assertEqual(self.state()['habitat'], {'theme':'DUSK','decoration':'NONE','playerFit':'FILL'})
        with self.assertRaises(PetError): self.engine.customize({'theme':'NEW_CHARACTER'})
        self.assertEqual(self.state()['petId'],'SL-001')

    def test_29b_real_reward_unlocks_and_local_lesson(self):
        with self.assertRaises(ConflictError): self.engine.customize({'theme':'AURORA'})
        with self.assertRaises(ConflictError): self.engine.customize({'decoration':'HALO'})
        lesson = self.engine.perform_action('LEARN','lesson-1')
        self.assertIn('Aprendizado local', lesson['message'])
        self.assertIn('Sol', lesson['message'])
        self.modify_state(xp=ExperienceEngine.threshold(35))
        self.assertEqual(self.engine.customize({'theme':'AURORA','decoration':'HALO'})['habitat']['theme'], 'AURORA')
        with self.assertRaises(ConflictError): self.engine.customize({'decoration':'CONSTELLATION'})
        self.modify_state(xp=ExperienceEngine.threshold(50))
        self.assertEqual(self.engine.customize({'decoration':'CONSTELLATION'})['habitat']['decoration'],'CONSTELLATION')

    def test_30_memory_deletion_preserves_dedup_ledger(self):
        event=self.event(); self.receive(event); self.engine.perform_action('PLAY','p')
        memory=self.engine.memories()[0]
        self.assertEqual(self.engine.delete_memories(memory['id']),1)
        self.assertGreater(self.engine.delete_memories(),0)
        self.assertEqual(self.engine.memories(),[])
        self.assertTrue(self.receive(event)['duplicate'])
        self.assertGreater(self.state()['xp'],0)

    def test_31_all_muse_contract_fixtures(self):
        events=json.loads((FIXTURES/'muse_events.json').read_text())
        self.assertEqual({e['eventType'] for e in events},INPUT_EVENTS)
        for e in events:
            self.assertFalse(self.receive(e)['duplicate'])
        self.assertEqual(self.state()['xp'],87)  # chat 7 + task 15 + goal 30 + skill 10 + milestone 25

    def test_32_private_payload_rejected_and_context_minimal(self):
        e=self.event('CHAT_MESSAGE_SENT',payload={'meaningful':True,'text':'secret-do-not-store'})
        with self.assertRaises(PetError): self.receive(e)
        self.assertNotIn('secret-do-not-store', self.path.read_bytes().decode('latin1',errors='ignore'))
        context=self.context()
        self.assertEqual(set(context), {'petId','mood','traits','bond','level','currentActivity'})
        self.assertEqual(context['petId'],'SL-001')

    def test_33_milestone_output_confirmed_and_idempotent(self):
        e=self.event('MILESTONE_ACHIEVED',payload={'milestoneId':'m-1','confirmed':True})
        self.assertEqual(self.receive(e)['xpAwarded'],25)
        self.assertTrue(self.receive(e)['duplicate'])
        self.assertTrue(any(x['eventType']=='PET_REWARD_UNLOCKED' and x['payload'].get('mediaKey')=='milestone_video' for x in self.outgoing()))

    def test_34_output_events_contract_and_cursor(self):
        self.engine.perform_action('PLAY','play')
        events=self.outgoing()
        self.assertTrue({e['eventType'] for e in events}.issubset(OUTPUT_EVENTS))
        self.assertEqual(self.outgoing(after=events[-1]['seq']),[])
        self.assertEqual(set(events[0]),{'seq','eventId','eventType','timestamp','source','payload'})

    def test_35_failures_and_rejections_do_not_penalize(self):
        before=self.state()
        self.receive(self.event('APPROVAL_REJECTED',payload={}))
        self.receive(self.event('AGENT_TASK_FAILED',id='failure',payload={'taskId':'task'}))
        after=self.state()
        self.assertEqual({a:before[a] for a in ATTRIBUTES}, {a:after[a] for a in ATTRIBUTES})
        self.assertEqual(after['xp'],0)


if __name__ == '__main__':
    unittest.main()
