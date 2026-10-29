"""Direct contract tests for the autonomy facade over the real SQLite engine."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pet.autonomy import AutonomyScheduler
from pet.model import AUTONOMOUS_ACTIVITIES, ConflictError, PetError
from pet.repository import PetRepository
from pet.service import PetEngine


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


class AutonomyFacadeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.path = Path(self.tmp.name) / 'pet.sqlite3'
        self.repo = PetRepository(self.path, clock=self.clock)
        self.engine = PetEngine(self.repo, clock=self.clock)
        self.scheduler = AutonomyScheduler(self.engine)

    def tearDown(self):
        self.tmp.cleanup()

    def test_manual_activity_and_history_are_persistent_and_idempotent(self):
        self.assertEqual(self.scheduler.activities, AUTONOMOUS_ACTIVITIES)
        self.assertFalse(self.scheduler.tick())  # disabled by default
        first = self.scheduler.run_local('JOURNAL', 'facade-journal-1')
        self.assertFalse(first['duplicate'])
        self.assertTrue(self.scheduler.run_local('JOURNAL', 'facade-journal-1')['duplicate'])
        self.assertEqual(len(self.scheduler.history()), 1)
        restarted = AutonomyScheduler(PetEngine(PetRepository(self.path, clock=self.clock), clock=self.clock))
        self.assertEqual(restarted.history()[0]['activity'], 'JOURNAL')
        self.assertEqual(restarted.history()[0]['status'], 'COMPLETED')

    def test_tick_runs_one_scheduled_activity_and_respects_cancellation(self):
        config = self.engine.get_config()
        config['autonomy'].update(enabled=True, intervalMinutes=15)
        self.engine.update_config(config)
        self.assertFalse(self.scheduler.tick())
        self.clock.now += timedelta(minutes=16)
        self.assertTrue(self.scheduler.tick())
        self.assertFalse(self.scheduler.tick())
        self.assertEqual(len(self.scheduler.history()), 1)
        self.assertTrue(self.scheduler.history()[0]['scheduled'])
        config['autonomy']['enabled'] = False
        self.engine.update_config(config)
        self.clock.now += timedelta(hours=2)
        self.assertFalse(self.scheduler.tick())
        self.assertIsNone(self.engine.snapshot(run_due=False)['autonomy']['nextRunAt'])

    def test_invalid_activity_and_insufficient_energy_do_not_create_history(self):
        with self.assertRaises(PetError):
            self.scheduler.run_local('UNKNOWN', 'invalid-1')
        with self.repo.transaction() as conn:
            state, config = self.repo.load(conn)
            state['energy'] = 0
            self.repo.save(conn, state, config)
        with self.assertRaises(ConflictError):
            self.scheduler.run_local('EXPERIMENT', 'no-energy-1')
        self.assertEqual(self.scheduler.history(), [])
        # Failed work was rolled back and its ID is safe to retry after resting.
        self.engine.perform_action('REST', 'rest-before-retry')
        self.assertFalse(self.scheduler.run_local('EXPERIMENT', 'no-energy-1')['duplicate'])
        self.assertEqual(len(self.scheduler.history()), 1)


if __name__ == '__main__':
    unittest.main()
