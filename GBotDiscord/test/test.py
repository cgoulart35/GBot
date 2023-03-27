#region IMPORTS
import unittest

from GBotDiscord.test.config.config_test import TestConfig
from GBotDiscord.test.gcoin.gcoin_test import TestGCoin
from GBotDiscord.test.gtrade.gtrade_test import TestGTrade
# DISCONTINUED from GBotDiscord.test.halo.halo_test import TestHalo
from GBotDiscord.test.hype.hype_test import TestHype
from GBotDiscord.test.music.music_test import TestMusic
from GBotDiscord.test.patreon.patreon_test import TestPatreon
from GBotDiscord.test.storms.storms_test import TestStorms

from GBotDiscord.test.quart_api.development_resource_test import TestDevelopmentResource
from GBotDiscord.test.quart_api.discord_resource_test import TestDiscordResource
# DISCONTINUED from GBotDiscord.test.quart_api.halo_resource_test import TestHaloResource
from GBotDiscord.test.quart_api.storms_resource_test import TestStormsResource

from GBotDiscord.test.predicates_test import TestPredicates
#endregion

# to run all test suites, use the "Python: Current File" run configuration to run tests.py

configTests = unittest.TestLoader().loadTestsFromTestCase(TestConfig)
gcoinTests = unittest.TestLoader().loadTestsFromTestCase(TestGCoin)
gtradeTests = unittest.TestLoader().loadTestsFromTestCase(TestGTrade)
# DISCONTINUED haloTests = unittest.TestLoader().loadTestsFromTestCase(TestHalo)
hypeTests = unittest.TestLoader().loadTestsFromTestCase(TestHype)
musicTests = unittest.TestLoader().loadTestsFromTestCase(TestMusic)
patreonTests = unittest.TestLoader().loadTestsFromTestCase(TestPatreon)
stormsTests = unittest.TestLoader().loadTestsFromTestCase(TestStorms)

developmentResourceTests = unittest.TestLoader().loadTestsFromTestCase(TestDevelopmentResource)
discordResourceTests = unittest.TestLoader().loadTestsFromTestCase(TestDiscordResource)
# DISCONTINUED haloResourceTests = unittest.TestLoader().loadTestsFromTestCase(TestHaloResource)
stormsResourceTests = unittest.TestLoader().loadTestsFromTestCase(TestStormsResource)

predicatesTests = unittest.TestLoader().loadTestsFromTestCase(TestPredicates)

allTestsSuite = unittest.TestSuite([configTests, gcoinTests, gtradeTests, hypeTests, musicTests, patreonTests, stormsTests,
                                    developmentResourceTests, discordResourceTests, stormsResourceTests,
                                    predicatesTests])

unittest.TextTestRunner().run(allTestsSuite)