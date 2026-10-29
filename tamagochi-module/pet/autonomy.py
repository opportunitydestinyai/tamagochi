"""Small scheduling facade. Execution is opportunistic and entirely local."""
from .model import AUTONOMOUS_ACTIVITIES


class AutonomyScheduler:
    def __init__(self, engine):
        self.engine = engine

    def tick(self):
        """Process at most one due job. Safe after restart and multiple callers."""
        return self.engine.run_due()

    def run_local(self, activity, event_id):
        return self.engine.run_activity(activity, event_id)

    def history(self):
        return self.engine.autonomy_history()

    @property
    def activities(self):
        return AUTONOMOUS_ACTIVITIES
