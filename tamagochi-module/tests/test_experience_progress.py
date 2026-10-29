"""Regression coverage for the XP values consumed by the progress display."""
import copy
import unittest

from pet.model import DEFAULT_CONFIG, ExperienceEngine


class ExperienceProgressTests(unittest.TestCase):
    def assert_progress(self, xp, expected, config=None):
        progress = ExperienceEngine.progress(xp, config)
        self.assertEqual(progress, dict(zip(
            ('level', 'currentThreshold', 'nextThreshold', 'intoLevel', 'neededInLevel', 'percent'),
            expected,
        )))
        self.assertEqual(progress['currentThreshold'] + progress['intoLevel'], xp)
        self.assertEqual(progress['nextThreshold'] - progress['currentThreshold'], progress['neededInLevel'])
        self.assertEqual(progress['neededInLevel'] - progress['intoLevel'], progress['nextThreshold'] - xp)

    def test_default_level_boundaries_and_midpoint(self):
        cases = (
            (0,   (1, 0,   100,  0,   100,   0.0)),
            (5,   (1, 0,   100,  5,   100,   5.0)),
            (99,  (1, 0,   100,  99,  100,  99.0)),
            (100, (2, 100, 283,  0,   183,   0.0)),
            (150, (2, 100, 283,  50,  183,  27.3)),
            (282, (2, 100, 283,  182, 183,  99.5)),
            (283, (3, 283, 520,  0,   237,   0.0)),
            (799, (4, 520, 800,  279, 280,  99.6)),
            (800, (5, 800, 1118, 0,   318,   0.0)),
        )
        for xp, expected in cases:
            with self.subTest(xp=xp):
                self.assert_progress(xp, expected)

    def test_percentage_never_rounds_to_complete_before_next_level(self):
        custom = copy.deepcopy(DEFAULT_CONFIG)
        custom['xpFormula']['scale'] = 1000
        for level, config in ((180, None), (3, custom)):
            with self.subTest(level=level, config=config):
                threshold = ExperienceEngine.threshold(level + 1, config)
                progress = ExperienceEngine.progress(threshold - 1, config)
                self.assertEqual(progress['level'], level)
                self.assertEqual(progress['neededInLevel'] - progress['intoLevel'], 1)
                self.assertEqual(progress['percent'], 99.9)
                next_progress = ExperienceEngine.progress(threshold, config)
                self.assertEqual(next_progress['level'], level + 1)
                self.assertEqual(next_progress['intoLevel'], 0)
                self.assertEqual(next_progress['percent'], 0.0)

    def test_configured_formula_uses_configured_thresholds(self):
        config = copy.deepcopy(DEFAULT_CONFIG)
        config['xpFormula']['scale'] = 200
        for xp, expected in (
            (0,   (1, 0,   200, 0,   200,  0.0)),
            (199, (1, 0,   200, 199, 200, 99.5)),
            (200, (2, 200, 566, 0,   366,  0.0)),
            (350, (2, 200, 566, 150, 366, 41.0)),
            (565, (2, 200, 566, 365, 366, 99.7)),
            (566, (3, 566, 1039, 0,  473,  0.0)),
        ):
            with self.subTest(xp=xp):
                self.assert_progress(xp, expected, config)


if __name__ == '__main__':
    unittest.main()
