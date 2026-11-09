#region IMPORTS
import sys
import unittest

from GBotDiscord.test.config.config_test import TestConfig
from GBotDiscord.test.config.config_queries_test import TestConfigQueries
from GBotDiscord.test.gcoin.gcoin_test import TestGCoin
from GBotDiscord.test.gcoin.gcoin_queries_test import TestGCoinQueries
from GBotDiscord.test.gtrade.gtrade_test import TestGTrade
from GBotDiscord.test.gtrade.gtrade_queries_test import TestGTradeQueries
# DISCONTINUED from GBotDiscord.test.halo.halo_test import TestHalo
from GBotDiscord.test.hype.hype_test import TestHype
from GBotDiscord.test.hype.hype_queries_test import TestHypeQueries
from GBotDiscord.test.music.music_test import TestMusic
from GBotDiscord.test.patreon.patreon_test import TestPatreon
from GBotDiscord.test.patreon.patreon_queries_test import TestPatreonQueries
from GBotDiscord.test.presence.presence_test import TestPresence
from GBotDiscord.test.storms.storms_test import TestStorms
from GBotDiscord.test.whodis.whodis_test import TestWhoDis

from GBotDiscord.test.quart_api.api_test import TestAPI
from GBotDiscord.test.quart_api.development_queries_test import TestDevelopmentQueries
from GBotDiscord.test.quart_api.development_resource_test import TestDevelopmentResource
from GBotDiscord.test.quart_api.discord_resource_test import TestDiscordResource
# DISCONTINUED from GBotDiscord.test.quart_api.halo_resource_test import TestHaloResource
from GBotDiscord.test.quart_api.leaderboards_resource_test import TestLeaderboardResource
from GBotDiscord.test.quart_api.storms_resource_test import TestStormsResource

from GBotDiscord.test.command_tree_test import TestCommandTree
from GBotDiscord.test.agent.agent_test import TestAgent
from GBotDiscord.test.agent.agent_client_test import TestAgentClient
from GBotDiscord.test.agent.agent_queries_test import TestAgentQueries
from GBotDiscord.test.site_drift_test import TestSiteDrift
from GBotDiscord.test.logging_setup_test import TestLoggingSetup
from GBotDiscord.test.help.help_test import TestHelp
from GBotDiscord.test.help.guides_test import TestGuides
from GBotDiscord.test.presentation_test import TestPresentation
from GBotDiscord.test.dave_patch_test import TestDavePatch
from GBotDiscord.test.dependencies_test import TestDependencies
from GBotDiscord.test.firebase_test import TestFirebase
from GBotDiscord.test.leaderboards.leaderboards_queries_test import TestLeaderboardsQueries
from GBotDiscord.test.pagination_test import TestPagination
from GBotDiscord.test.predicates_test import TestPredicates
from GBotDiscord.test.properties_test import TestProperties
from GBotDiscord.test.server_setup_test import TestServerSetup
from GBotDiscord.test.access_test import TestAccess
from GBotDiscord.test.reminders.when_test import TestWhen
from GBotDiscord.test.reminders.reminders_test import TestReminders
from GBotDiscord.test.reminders.reminders_queries_test import TestRemindersQueries
from GBotDiscord.test.utils_test import TestUtils
#endregion

# to run all test suites, use the "Python: Current File" run configuration to run tests.py

configTests = unittest.TestLoader().loadTestsFromTestCase(TestConfig)
configQueriesTests = unittest.TestLoader().loadTestsFromTestCase(TestConfigQueries)
gcoinTests = unittest.TestLoader().loadTestsFromTestCase(TestGCoin)
gcoinQueriesTests = unittest.TestLoader().loadTestsFromTestCase(TestGCoinQueries)
gtradeTests = unittest.TestLoader().loadTestsFromTestCase(TestGTrade)
gtradeQueriesTests = unittest.TestLoader().loadTestsFromTestCase(TestGTradeQueries)
# DISCONTINUED haloTests = unittest.TestLoader().loadTestsFromTestCase(TestHalo)
hypeTests = unittest.TestLoader().loadTestsFromTestCase(TestHype)
hypeQueriesTests = unittest.TestLoader().loadTestsFromTestCase(TestHypeQueries)
musicTests = unittest.TestLoader().loadTestsFromTestCase(TestMusic)
patreonTests = unittest.TestLoader().loadTestsFromTestCase(TestPatreon)
patreonQueriesTests = unittest.TestLoader().loadTestsFromTestCase(TestPatreonQueries)
presenceTests = unittest.TestLoader().loadTestsFromTestCase(TestPresence)
stormsTests = unittest.TestLoader().loadTestsFromTestCase(TestStorms)
whodisTests = unittest.TestLoader().loadTestsFromTestCase(TestWhoDis)

apiTests = unittest.TestLoader().loadTestsFromTestCase(TestAPI)
developmentQueriesTests = unittest.TestLoader().loadTestsFromTestCase(TestDevelopmentQueries)
developmentResourceTests = unittest.TestLoader().loadTestsFromTestCase(TestDevelopmentResource)
discordResourceTests = unittest.TestLoader().loadTestsFromTestCase(TestDiscordResource)
# DISCONTINUED haloResourceTests = unittest.TestLoader().loadTestsFromTestCase(TestHaloResource)
leaderboardResourceTests = unittest.TestLoader().loadTestsFromTestCase(TestLeaderboardResource)
stormsResourceTests = unittest.TestLoader().loadTestsFromTestCase(TestStormsResource)

commandTreeTests = unittest.TestLoader().loadTestsFromTestCase(TestCommandTree)
agentTests = unittest.TestLoader().loadTestsFromTestCase(TestAgent)
agentClientTests = unittest.TestLoader().loadTestsFromTestCase(TestAgentClient)
agentQueriesTests = unittest.TestLoader().loadTestsFromTestCase(TestAgentQueries)
siteDriftTests = unittest.TestLoader().loadTestsFromTestCase(TestSiteDrift)
loggingSetupTests = unittest.TestLoader().loadTestsFromTestCase(TestLoggingSetup)
helpTests = unittest.TestLoader().loadTestsFromTestCase(TestHelp)
guidesTests = unittest.TestLoader().loadTestsFromTestCase(TestGuides)
presentationTests = unittest.TestLoader().loadTestsFromTestCase(TestPresentation)
davePatchTests = unittest.TestLoader().loadTestsFromTestCase(TestDavePatch)
dependenciesTests = unittest.TestLoader().loadTestsFromTestCase(TestDependencies)
firebaseTests = unittest.TestLoader().loadTestsFromTestCase(TestFirebase)
leaderboardsQueriesTests = unittest.TestLoader().loadTestsFromTestCase(TestLeaderboardsQueries)
paginationTests = unittest.TestLoader().loadTestsFromTestCase(TestPagination)
predicatesTests = unittest.TestLoader().loadTestsFromTestCase(TestPredicates)
propertiesTests = unittest.TestLoader().loadTestsFromTestCase(TestProperties)
utilsTests = unittest.TestLoader().loadTestsFromTestCase(TestUtils)
serverSetupTests = unittest.TestLoader().loadTestsFromTestCase(TestServerSetup)
accessTests = unittest.TestLoader().loadTestsFromTestCase(TestAccess)
whenTests = unittest.TestLoader().loadTestsFromTestCase(TestWhen)
remindersTests = unittest.TestLoader().loadTestsFromTestCase(TestReminders)
remindersQueriesTests = unittest.TestLoader().loadTestsFromTestCase(TestRemindersQueries)

allTestsSuite = unittest.TestSuite([configTests, configQueriesTests, gcoinTests, gcoinQueriesTests, gtradeTests, gtradeQueriesTests, hypeTests, hypeQueriesTests, musicTests, patreonTests, patreonQueriesTests, presenceTests, stormsTests, whodisTests,
                                    apiTests, developmentQueriesTests, developmentResourceTests, discordResourceTests, leaderboardResourceTests, stormsResourceTests,
                                    commandTreeTests, siteDriftTests, agentTests, agentClientTests, agentQueriesTests, loggingSetupTests, helpTests, guidesTests, presentationTests, davePatchTests, dependenciesTests, firebaseTests, leaderboardsQueriesTests, paginationTests, predicatesTests, propertiesTests, utilsTests, serverSetupTests, accessTests, whenTests, remindersTests, remindersQueriesTests])

result = unittest.TextTestRunner().run(allTestsSuite)
sys.exit(0 if result.wasSuccessful() else 1)
