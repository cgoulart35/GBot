#region IMPORTS
import unittest
from unittest.mock import patch

from GBotDiscord.src.help import guides
from GBotDiscord.src.help.help_cog import FEATURES
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

SETTINGS = {
    'STORMS_MIN_TIME_BETWEEN_SECONDS': 3600,
    'STORMS_MAX_TIME_BETWEEN_SECONDS': 14400,
    'STORMS_DELETE_MESSAGES_AFTER_SECONDS': 60,
    'WHODIS_TIMEOUT_MINUTES': 5,
    'WHODIS_COOLDOWN_MINUTES': 10,
    'GTRADE_MARKET_SALE_TIMEOUT_HOURS': 3,
    'GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES': 5,
    'MUSIC_MAX_DURATION_MINUTES': 180,
    'MUSIC_MAX_PLAYLIST_SONGS': 50,
    'MUSIC_MAX_QUEUE_SONGS': 200,
    'MUSIC_TIMEOUT_SECONDS': 300
}

class TestGuides(unittest.TestCase):

    def setUp(self):
        for name, value in SETTINGS.items():
            patcher = patch.object(GBotPropertiesManager, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_every_feature_in_help_has_a_guide_that_fits_one_embed_field(self):
        self.assertEqual(set(guides.GUIDES), {feature.name for feature in FEATURES})
        for name in guides.GUIDES:
            text = guides.guideFor(name)
            self.assertLessEqual(len(text), 1024, name)
            self.assertTrue(text.strip(), name)

    def test_the_numbers_come_from_the_settings_and_the_cogs(self):
        storms = guides.guideFor('Storms')
        for expected in ('Every 1 to 4 hours', '**0.25 GCoin**', '**1.00 GCoin**', '10x on your first guess', 'after 60 seconds'):
            self.assertIn(expected, storms)
        whodis = guides.guideFor('Who Dis')
        for expected in ('**50.00 GCoin** for every member online', 'up to 1,000,000.00', 'after 5 minutes', '10 minutes after starting the last'):
            self.assertIn(expected, whodis)
        gtrade = guides.guideFor('GTrade')
        for expected in ('up to 100 items', 'for 3 hours', 'last 5 minutes'):
            self.assertIn(expected, gtrade)
        music = guides.guideFor('Music')
        for expected in ('up to 180 minutes', 'first 50 songs', 'holds 200', 'after 5 minutes'):
            self.assertIn(expected, music)

    def test_a_changed_setting_changes_the_guide(self):
        with patch.object(GBotPropertiesManager, 'WHODIS_COOLDOWN_MINUTES', 30):
            self.assertIn('30 minutes after starting the last', guides.guideFor('Who Dis'))

    def test_hours_reads_cleanly(self):
        self.assertEqual(guides.hours(5400), '1.5')
        self.assertEqual(guides.hours(7200), '2')

if __name__ == '__main__':
    unittest.main()
