#region IMPORTS
import logging
import os
import unittest
from unittest.mock import MagicMock, patch

from GBotDiscord.src.exceptions import PropertyNotSpecified
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

# Snapshot every ALL_CAPS class attribute on GBotPropertiesManager at import time.
# Other suites may mutate these (and never restore) — restoring in setUp keeps
# TestProperties order-independent.
_PROPERTY_NAMES = [
    name for name in vars(GBotPropertiesManager)
    if name.isupper() and not name.startswith('_')
]


class TestProperties(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting properties unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted properties unit tests.\n')

    def setUp(self):
        self._saved = {name: getattr(GBotPropertiesManager, name) for name in _PROPERTY_NAMES}
        self._saved_logger = GBotPropertiesManager.logger

    def tearDown(self):
        for name, value in self._saved.items():
            setattr(GBotPropertiesManager, name, value)
        GBotPropertiesManager.logger = self._saved_logger

    # region getEnvProperty

    def test_getEnvProperty_value_present_coerced(self):
        with patch.dict(os.environ, {'API_PORT': '5005'}, clear=True):
            self.assertEqual(GBotPropertiesManager.getEnvProperty('API_PORT'), 5005)

    def test_getEnvProperty_value_present_string_passthrough(self):
        with patch.dict(os.environ, {'TZ': 'UTC'}, clear=True):
            self.assertEqual(GBotPropertiesManager.getEnvProperty('TZ'), 'UTC')

    def test_getEnvProperty_missing_returns_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(GBotPropertiesManager.getEnvProperty('TZ', 'America/New_York'), 'America/New_York')

    def test_getEnvProperty_default_returned_without_coercion(self):
        # Defaults bypass determineValue intentionally — string default is returned as-is
        # even for INT_PROPERTIES members.
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(GBotPropertiesManager.getEnvProperty('API_PORT', '5004'), '5004')

    def test_getEnvProperty_missing_no_default_raises_and_logs(self):
        GBotPropertiesManager.logger = MagicMock()
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(PropertyNotSpecified):
                GBotPropertiesManager.getEnvProperty('GBOT_VERSION')
        GBotPropertiesManager.logger.error.assert_called_once()
        self.assertIn('GBOT_VERSION', GBotPropertiesManager.logger.error.call_args[0][0])

    # endregion

    # region determineValue

    def test_determineValue_int_properties_all_coerced(self):
        for name in [
            "API_PORT",
            "PATREON_GUILD_ID",
            "PATRON_ROLE_ID",
            "USER_RESPONSE_TIMEOUT_SECONDS",
            "MUSIC_TIMEOUT_SECONDS",
            "MUSIC_CACHE_DELETION_TIMEOUT_MINUTES",
            "GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES",
            "GTRADE_MARKET_SALE_TIMEOUT_HOURS",
            "STORMS_MIN_TIME_BETWEEN_SECONDS",
            "STORMS_MAX_TIME_BETWEEN_SECONDS",
            "STORMS_DELETE_MESSAGES_AFTER_SECONDS",
            "WHODIS_TIMEOUT_MINUTES",
            "WHODIS_COOLDOWN_MINUTES",
        ]:
            with self.subTest(property=name):
                result = GBotPropertiesManager.determineValue(name, "42")
                self.assertEqual(result, 42)
                self.assertIsInstance(result, int)

    def test_determineValue_splittable_empty_string_returns_empty_list(self):
        self.assertEqual(GBotPropertiesManager.determineValue("PATREON_IGNORE_GUILDS", ""), [])
        self.assertEqual(GBotPropertiesManager.determineValue("SLASH_COMMAND_TEST_GUILDS", ""), [])

    def test_determineValue_splittable_csv_returns_int_list(self):
        self.assertEqual(
            GBotPropertiesManager.determineValue("PATREON_IGNORE_GUILDS", "1,2,3"),
            [1, 2, 3],
        )
        self.assertEqual(
            GBotPropertiesManager.determineValue("SLASH_COMMAND_TEST_GUILDS", "100,200"),
            [100, 200],
        )

    def test_determineValue_log_level_routed_through_getLogLevel(self):
        self.assertEqual(GBotPropertiesManager.determineValue("LOG_LEVEL", "DEBUG"), logging.DEBUG)

    def test_determineValue_default_branch_returns_raw(self):
        self.assertEqual(GBotPropertiesManager.determineValue("TZ", "UTC"), "UTC")
        self.assertEqual(GBotPropertiesManager.determineValue("DISCORD_TOKEN", "abc"), "abc")

    # endregion

    # region getLogLevel

    def test_getLogLevel_all_named_levels(self):
        cases = {
            "CRITICAL": logging.CRITICAL,
            "FATAL": logging.FATAL,
            "ERROR": logging.ERROR,
            "WARNING": logging.WARNING,
            "WARN": logging.WARN,
            "INFO": logging.INFO,
            "DEBUG": logging.DEBUG,
        }
        for level, expected in cases.items():
            with self.subTest(level=level):
                self.assertEqual(GBotPropertiesManager.getLogLevel(level), expected)

    def test_getLogLevel_unknown_returns_notset(self):
        self.assertEqual(GBotPropertiesManager.getLogLevel("UNKNOWN"), logging.NOTSET)
        self.assertEqual(GBotPropertiesManager.getLogLevel(""), logging.NOTSET)

    # endregion

    # region setProperty

    def test_setProperty_log_level_mutates_and_calls_logger_setLevel(self):
        GBotPropertiesManager.logger = MagicMock()
        result = GBotPropertiesManager.setProperty("LOG_LEVEL", "DEBUG")
        self.assertTrue(result)
        self.assertEqual(GBotPropertiesManager.LOG_LEVEL, "DEBUG")
        GBotPropertiesManager.logger.setLevel.assert_called_once_with(logging.DEBUG)

    def test_setProperty_every_mutable_property(self):
        # name -> value to set. LOG_LEVEL is covered separately because it has the side effect.
        cases = {
            "PATREON_URL": "https://patreon.example",
            "PATREON_GUILD_ID": 111,
            "PATRON_ROLE_ID": 222,
            "PATREON_IGNORE_GUILDS": [333, 444],
            "USER_RESPONSE_TIMEOUT_SECONDS": 60,
            "MUSIC_TIMEOUT_SECONDS": 120,
            "MUSIC_CACHE_DELETION_TIMEOUT_MINUTES": 30,
            "GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES": 7,
            "GTRADE_MARKET_SALE_TIMEOUT_HOURS": 12,
            "STORMS_MIN_TIME_BETWEEN_SECONDS": 1800,
            "STORMS_MAX_TIME_BETWEEN_SECONDS": 7200,
            "STORMS_DELETE_MESSAGES_AFTER_SECONDS": 90,
            "WHODIS_TIMEOUT_MINUTES": 8,
            "WHODIS_COOLDOWN_MINUTES": 15,
            "SLASH_COMMAND_TEST_GUILDS": [555, 666],
        }
        for name, value in cases.items():
            with self.subTest(property=name):
                result = GBotPropertiesManager.setProperty(name, value)
                self.assertTrue(result)
                self.assertEqual(getattr(GBotPropertiesManager, name), value)

    def test_setProperty_whodis_cooldown_does_not_clobber_timeout(self):
        # Regression: prior to fix, setting WHODIS_COOLDOWN_MINUTES wrote to
        # WHODIS_TIMEOUT_MINUTES instead — silently clobbering the active-game timer.
        GBotPropertiesManager.WHODIS_TIMEOUT_MINUTES = 5
        GBotPropertiesManager.WHODIS_COOLDOWN_MINUTES = 10
        GBotPropertiesManager.setProperty("WHODIS_COOLDOWN_MINUTES", 99)
        self.assertEqual(GBotPropertiesManager.WHODIS_COOLDOWN_MINUTES, 99)
        self.assertEqual(GBotPropertiesManager.WHODIS_TIMEOUT_MINUTES, 5)

    def test_setProperty_unknown_returns_false(self):
        self.assertFalse(GBotPropertiesManager.setProperty("DOES_NOT_EXIST", "x"))

    def test_setProperty_immutable_returns_false(self):
        # Properties intentionally NOT in the if/elif chain (DISCORD_TOKEN, GBOT_VERSION,
        # TZ, API_PORT, FIREBASE_CONFIG_JSON) must not be mutable via setProperty.
        for name in ["DISCORD_TOKEN", "GBOT_VERSION", "TZ", "API_PORT", "FIREBASE_CONFIG_JSON"]:
            with self.subTest(property=name):
                original = getattr(GBotPropertiesManager, name)
                self.assertFalse(GBotPropertiesManager.setProperty(name, "should-not-stick"))
                self.assertEqual(getattr(GBotPropertiesManager, name), original)

    # endregion

    # region startPropertyManager

    def test_startPropertyManager_all_env_set_populates_every_attribute(self):
        env = {
            "GBOT_VERSION": "1.2.3",
            "TZ": "UTC",
            "LOG_LEVEL": "DEBUG",
            "API_PORT": "5500",
            "PATREON_URL": "https://patreon.test",
            "DISCORD_TOKEN": "token-xyz",
            "FIREBASE_CONFIG_JSON": '{"a":1}',
            "PATREON_GUILD_ID": "111",
            "PATRON_ROLE_ID": "222",
            "PATREON_IGNORE_GUILDS": "10,20,30",
            "USER_RESPONSE_TIMEOUT_SECONDS": "100",
            "MUSIC_TIMEOUT_SECONDS": "200",
            "MUSIC_CACHE_DELETION_TIMEOUT_MINUTES": "300",
            "GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES": "5",
            "GTRADE_MARKET_SALE_TIMEOUT_HOURS": "3",
            "STORMS_MIN_TIME_BETWEEN_SECONDS": "60",
            "STORMS_MAX_TIME_BETWEEN_SECONDS": "120",
            "STORMS_DELETE_MESSAGES_AFTER_SECONDS": "30",
            "WHODIS_TIMEOUT_MINUTES": "5",
            "WHODIS_COOLDOWN_MINUTES": "10",
            "SLASH_COMMAND_TEST_GUILDS": "777,888",
        }
        with patch.dict(os.environ, env, clear=True):
            GBotPropertiesManager.startPropertyManager()

        self.assertEqual(GBotPropertiesManager.GBOT_VERSION, "1.2.3")
        self.assertEqual(GBotPropertiesManager.TZ, "UTC")
        self.assertEqual(GBotPropertiesManager.LOG_LEVEL, logging.DEBUG)
        self.assertEqual(GBotPropertiesManager.API_PORT, 5500)
        self.assertEqual(GBotPropertiesManager.PATREON_URL, "https://patreon.test")
        self.assertEqual(GBotPropertiesManager.DISCORD_TOKEN, "token-xyz")
        self.assertEqual(GBotPropertiesManager.FIREBASE_CONFIG_JSON, '{"a":1}')
        self.assertEqual(GBotPropertiesManager.PATREON_GUILD_ID, 111)
        self.assertEqual(GBotPropertiesManager.PATRON_ROLE_ID, 222)
        self.assertEqual(GBotPropertiesManager.PATREON_IGNORE_GUILDS, [10, 20, 30])
        self.assertEqual(GBotPropertiesManager.USER_RESPONSE_TIMEOUT_SECONDS, 100)
        self.assertEqual(GBotPropertiesManager.MUSIC_TIMEOUT_SECONDS, 200)
        self.assertEqual(GBotPropertiesManager.MUSIC_CACHE_DELETION_TIMEOUT_MINUTES, 300)
        self.assertEqual(GBotPropertiesManager.GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES, 5)
        self.assertEqual(GBotPropertiesManager.GTRADE_MARKET_SALE_TIMEOUT_HOURS, 3)
        self.assertEqual(GBotPropertiesManager.STORMS_MIN_TIME_BETWEEN_SECONDS, 60)
        self.assertEqual(GBotPropertiesManager.STORMS_MAX_TIME_BETWEEN_SECONDS, 120)
        self.assertEqual(GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS, 30)
        self.assertEqual(GBotPropertiesManager.WHODIS_TIMEOUT_MINUTES, 5)
        self.assertEqual(GBotPropertiesManager.WHODIS_COOLDOWN_MINUTES, 10)
        self.assertEqual(GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS, [777, 888])

    def test_startPropertyManager_only_required_uses_defaults(self):
        # Defaults bypass determineValue, so int-typed properties land as their string
        # defaults — this documents that quirk.
        env = {
            "GBOT_VERSION": "0.0.1",
            "PATREON_URL": "https://patreon.test",
            "DISCORD_TOKEN": "tok",
            "FIREBASE_CONFIG_JSON": "{}",
            "PATREON_GUILD_ID": "1",
            "PATRON_ROLE_ID": "2",
        }
        with patch.dict(os.environ, env, clear=True):
            GBotPropertiesManager.startPropertyManager()

        self.assertEqual(GBotPropertiesManager.TZ, "America/New_York")
        self.assertEqual(GBotPropertiesManager.LOG_LEVEL, "INFO")
        self.assertEqual(GBotPropertiesManager.API_PORT, "5004")
        self.assertEqual(GBotPropertiesManager.PATREON_IGNORE_GUILDS, "")
        self.assertEqual(GBotPropertiesManager.USER_RESPONSE_TIMEOUT_SECONDS, "300")
        self.assertEqual(GBotPropertiesManager.MUSIC_TIMEOUT_SECONDS, "300")
        self.assertEqual(GBotPropertiesManager.MUSIC_CACHE_DELETION_TIMEOUT_MINUTES, "180")
        self.assertEqual(GBotPropertiesManager.GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES, "5")
        self.assertEqual(GBotPropertiesManager.GTRADE_MARKET_SALE_TIMEOUT_HOURS, "3")
        self.assertEqual(GBotPropertiesManager.STORMS_MIN_TIME_BETWEEN_SECONDS, "3600")
        self.assertEqual(GBotPropertiesManager.STORMS_MAX_TIME_BETWEEN_SECONDS, "14400")
        self.assertEqual(GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS, "60")
        self.assertEqual(GBotPropertiesManager.WHODIS_TIMEOUT_MINUTES, "5")
        self.assertEqual(GBotPropertiesManager.WHODIS_COOLDOWN_MINUTES, "10")
        self.assertEqual(GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS, "")

    def test_startPropertyManager_missing_required_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(PropertyNotSpecified):
                GBotPropertiesManager.startPropertyManager()

    # endregion
