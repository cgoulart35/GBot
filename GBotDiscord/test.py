#region IMPORTS
import unittest

from GBotDiscord.config.config_test import TestConfig
from GBotDiscord.gcoin.gcoin_test import TestGCoin
from GBotDiscord.gtrade.gtrade_test import TestGTrade
from GBotDiscord.halo.halo_test import TestHalo
from GBotDiscord.music.music_test import TestMusic

from GBotDiscord.quart_api.development_resource_test import TestDevelopmentResource
from GBotDiscord.quart_api.discord_resource_test import TestDiscordResource
from GBotDiscord.quart_api.halo_resource_test import TestHaloResource
#endregion

# to run all test suites, use the "Python: Current File" run configuration to run tests.py

configTests = unittest.TestLoader().loadTestsFromTestCase(TestConfig)
gcoinTests = unittest.TestLoader().loadTestsFromTestCase(TestGCoin)
gtradeTests = unittest.TestLoader().loadTestsFromTestCase(TestGTrade)
haloTests = unittest.TestLoader().loadTestsFromTestCase(TestHalo)
musicTests = unittest.TestLoader().loadTestsFromTestCase(TestMusic)

developmentResourceTests = unittest.TestLoader().loadTestsFromTestCase(TestDevelopmentResource)
discordResourceTests = unittest.TestLoader().loadTestsFromTestCase(TestDiscordResource)
haloResourceTests = unittest.TestLoader().loadTestsFromTestCase(TestHaloResource)

allTestsSuite = unittest.TestSuite([configTests, gcoinTests, gtradeTests, haloTests, musicTests,
                                    developmentResourceTests, discordResourceTests, haloResourceTests])

unittest.TextTestRunner().run(allTestsSuite)