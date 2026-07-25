#region IMPORTS
import unittest
from unittest.mock import MagicMock

import nextcord
from nextcord.ext.commands.context import Context

from GBotDiscord.src import predicates, utils
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.patreon import patreon_queries
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.exceptions import (
    MessageAuthorNotAdmin,
    MessageNotSentFromGuild,
    MessageNotSentFromPrivateMessage,
    FeatureNotEnabledForGuild,
    LegacyPrefixCommandsNotEnabledForGuild,
    NotSentFromPatreonGuild,
    NotAPatron,
    NotSubscribed,
)
#endregion

# Each factory in predicates.py returns either commands.check(predicate) or
# application_checks.check(predicate). Both store the inner async predicate
# on the decorator as `.predicate`, so we invoke that directly rather than
# going through the full check-application machinery.


def _slash_pred(decorator):
    return decorator.predicate


def _prefix_pred(decorator):
    return decorator.predicate


def _slash_ctx(guild=None, user=None):
    ctx = MagicMock(spec=nextcord.Interaction)
    ctx.guild = guild
    ctx.user = user
    return ctx


def _prefix_ctx(guild=None, author=None):
    ctx = MagicMock(spec=Context)
    ctx.guild = guild
    ctx.author = author
    return ctx


class TestPredicates(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(cls):
        print('\nExecuting predicates unit tests...\n')

    @classmethod
    def tearDownClass(cls):
        print('\n\nCompleted predicates unit tests.\n')

    def setUp(self):
        self._saved_isUserAdminOrOwner = utils.isUserAdminOrOwner
        self._saved_isUserAssignedRole = utils.isUserAssignedRole
        self._saved_getGuildsForPatreonToIgnore = utils.getGuildsForPatreonToIgnore
        self._saved_getServerValue = config_queries.getServerValue
        self._saved_getAllPatrons = patreon_queries.getAllPatrons
        self._saved_PATREON_GUILD_ID = GBotPropertiesManager.PATREON_GUILD_ID
        self._saved_PATRON_ROLE_ID = GBotPropertiesManager.PATRON_ROLE_ID

    def tearDown(self):
        utils.isUserAdminOrOwner = self._saved_isUserAdminOrOwner
        utils.isUserAssignedRole = self._saved_isUserAssignedRole
        utils.getGuildsForPatreonToIgnore = self._saved_getGuildsForPatreonToIgnore
        config_queries.getServerValue = self._saved_getServerValue
        patreon_queries.getAllPatrons = self._saved_getAllPatrons
        GBotPropertiesManager.PATREON_GUILD_ID = self._saved_PATREON_GUILD_ID
        GBotPropertiesManager.PATRON_ROLE_ID = self._saved_PATRON_ROLE_ID

    # region isMessageAuthorAdmin

    async def test_isMessageAuthorAdmin_slash_admin_passes(self):
        utils.isUserAdminOrOwner = MagicMock(return_value=True)
        guild = MagicMock()
        user = MagicMock()
        self.assertTrue(await _slash_pred(predicates.isMessageAuthorAdmin(True))(_slash_ctx(guild, user)))
        utils.isUserAdminOrOwner.assert_called_once_with(user, guild)

    async def test_isMessageAuthorAdmin_prefix_admin_passes(self):
        utils.isUserAdminOrOwner = MagicMock(return_value=True)
        guild = MagicMock()
        author = MagicMock()
        self.assertTrue(await _prefix_pred(predicates.isMessageAuthorAdmin(False))(_prefix_ctx(guild, author)))
        utils.isUserAdminOrOwner.assert_called_once_with(author, guild)

    async def test_isMessageAuthorAdmin_slash_non_admin_raises(self):
        utils.isUserAdminOrOwner = MagicMock(return_value=False)
        with self.assertRaises(MessageAuthorNotAdmin):
            await _slash_pred(predicates.isMessageAuthorAdmin(True))(_slash_ctx(MagicMock(), MagicMock()))

    async def test_isMessageAuthorAdmin_prefix_non_admin_raises(self):
        utils.isUserAdminOrOwner = MagicMock(return_value=False)
        with self.assertRaises(MessageAuthorNotAdmin):
            await _prefix_pred(predicates.isMessageAuthorAdmin())(_prefix_ctx(MagicMock(), MagicMock()))

    # endregion

    # region isMessageSentInGuild

    async def test_isMessageSentInGuild_slash_with_guild_passes(self):
        self.assertTrue(await _slash_pred(predicates.isMessageSentInGuild(True))(_slash_ctx(MagicMock())))

    async def test_isMessageSentInGuild_prefix_with_guild_passes(self):
        self.assertTrue(await _prefix_pred(predicates.isMessageSentInGuild())(_prefix_ctx(MagicMock())))

    async def test_isMessageSentInGuild_slash_none_raises(self):
        with self.assertRaises(MessageNotSentFromGuild):
            await _slash_pred(predicates.isMessageSentInGuild(True))(_slash_ctx(None))

    async def test_isMessageSentInGuild_prefix_none_raises(self):
        with self.assertRaises(MessageNotSentFromGuild):
            await _prefix_pred(predicates.isMessageSentInGuild())(_prefix_ctx(None))

    # endregion

    # region isMessageSentInPrivateMessage

    async def test_isMessageSentInPrivateMessage_slash_dm_passes(self):
        self.assertTrue(await _slash_pred(predicates.isMessageSentInPrivateMessage(True))(_slash_ctx(None)))

    async def test_isMessageSentInPrivateMessage_prefix_dm_passes(self):
        self.assertTrue(await _prefix_pred(predicates.isMessageSentInPrivateMessage())(_prefix_ctx(None)))

    async def test_isMessageSentInPrivateMessage_slash_in_guild_raises(self):
        with self.assertRaises(MessageNotSentFromPrivateMessage):
            await _slash_pred(predicates.isMessageSentInPrivateMessage(True))(_slash_ctx(MagicMock()))

    async def test_isMessageSentInPrivateMessage_prefix_in_guild_raises(self):
        with self.assertRaises(MessageNotSentFromPrivateMessage):
            await _prefix_pred(predicates.isMessageSentInPrivateMessage())(_prefix_ctx(MagicMock()))

    # endregion

    # region isFeatureEnabledForServer

    async def test_isFeatureEnabledForServer_dm_with_private_allowed_skips_db(self):
        config_queries.getServerValue = MagicMock()
        self.assertTrue(await _slash_pred(predicates.isFeatureEnabledForServer('toggle_x', True, True))(_slash_ctx(None)))
        config_queries.getServerValue.assert_not_called()

    async def test_isFeatureEnabledForServer_prefix_feature_on_passes(self):
        config_queries.getServerValue = MagicMock(return_value=True)
        guild = MagicMock()
        guild.id = 123
        self.assertTrue(await _prefix_pred(predicates.isFeatureEnabledForServer('toggle_x', False))(_prefix_ctx(guild)))
        config_queries.getServerValue.assert_called_once_with(123, 'toggle_x')

    async def test_isFeatureEnabledForServer_slash_feature_off_raises(self):
        config_queries.getServerValue = MagicMock(return_value=False)
        guild = MagicMock()
        guild.id = 123
        with self.assertRaises(FeatureNotEnabledForGuild):
            await _slash_pred(predicates.isFeatureEnabledForServer('toggle_x', False, True))(_slash_ctx(guild))

    async def test_isFeatureEnabledForServer_legacy_prefix_off_raises_specific(self):
        config_queries.getServerValue = MagicMock(return_value=False)
        guild = MagicMock()
        guild.id = 123
        with self.assertRaises(LegacyPrefixCommandsNotEnabledForGuild):
            await _prefix_pred(predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False))(_prefix_ctx(guild))

    async def test_isFeatureEnabledForServer_in_guild_private_allowed_still_checks(self):
        # privateMessagesAllowed=True short-circuits only when guild is None;
        # an in-guild call must still consult the DB.
        config_queries.getServerValue = MagicMock(return_value=False)
        guild = MagicMock()
        guild.id = 999
        with self.assertRaises(FeatureNotEnabledForGuild):
            await _slash_pred(predicates.isFeatureEnabledForServer('toggle_y', True, True))(_slash_ctx(guild))
        config_queries.getServerValue.assert_called_once_with(999, 'toggle_y')

    # endregion

    # region isAuthorAPatronInGBotPatreonServer

    async def test_isAuthorAPatron_wrong_guild_raises(self):
        GBotPropertiesManager.PATREON_GUILD_ID = 100
        GBotPropertiesManager.PATRON_ROLE_ID = 200
        guild = MagicMock()
        guild.id = 999
        with self.assertRaises(NotSentFromPatreonGuild):
            await _slash_pred(predicates.isAuthorAPatronInGBotPatreonServer(True))(_slash_ctx(guild, MagicMock()))

    async def test_isAuthorAPatron_right_guild_no_role_raises(self):
        GBotPropertiesManager.PATREON_GUILD_ID = 100
        GBotPropertiesManager.PATRON_ROLE_ID = 200
        utils.isUserAssignedRole = MagicMock(return_value=False)
        guild = MagicMock()
        guild.id = 100
        with self.assertRaises(NotAPatron):
            await _prefix_pred(predicates.isAuthorAPatronInGBotPatreonServer())(_prefix_ctx(guild, MagicMock()))

    async def test_isAuthorAPatron_right_guild_with_role_passes_slash(self):
        GBotPropertiesManager.PATREON_GUILD_ID = 100
        GBotPropertiesManager.PATRON_ROLE_ID = 200
        utils.isUserAssignedRole = MagicMock(return_value=True)
        guild = MagicMock()
        guild.id = 100
        user = MagicMock()
        self.assertTrue(await _slash_pred(predicates.isAuthorAPatronInGBotPatreonServer(True))(_slash_ctx(guild, user)))
        utils.isUserAssignedRole.assert_called_once_with(user, 200)

    async def test_isAuthorAPatron_right_guild_with_role_passes_prefix(self):
        GBotPropertiesManager.PATREON_GUILD_ID = 100
        GBotPropertiesManager.PATRON_ROLE_ID = 200
        utils.isUserAssignedRole = MagicMock(return_value=True)
        guild = MagicMock()
        guild.id = 100
        author = MagicMock()
        self.assertTrue(await _prefix_pred(predicates.isAuthorAPatronInGBotPatreonServer())(_prefix_ctx(guild, author)))
        utils.isUserAssignedRole.assert_called_once_with(author, 200)

    # endregion

    # region isGuildOrUserSubscribed

    async def test_isSubscribed_guild_in_ignore_list_passes(self):
        utils.getGuildsForPatreonToIgnore = MagicMock(return_value=[42, 43])
        patreon_queries.getAllPatrons = MagicMock(return_value=None)
        guild = MagicMock()
        guild.id = 42
        user = MagicMock()
        user.mutual_guilds = []
        self.assertTrue(await _slash_pred(predicates.isGuildOrUserSubscribed(True))(_slash_ctx(guild, user)))

    async def test_isSubscribed_dm_mutual_guild_in_ignore_list_passes(self):
        utils.getGuildsForPatreonToIgnore = MagicMock(return_value=[42])
        patreon_queries.getAllPatrons = MagicMock(return_value=None)
        mutual = MagicMock()
        mutual.id = 42
        user = MagicMock()
        user.mutual_guilds = [mutual]
        self.assertTrue(await _prefix_pred(predicates.isGuildOrUserSubscribed())(_prefix_ctx(None, user)))

    async def test_isSubscribed_subscribed_guild_via_patron_table(self):
        utils.getGuildsForPatreonToIgnore = MagicMock(return_value=[])
        patreon_queries.getAllPatrons = MagicMock(return_value={
            'p1': {'serverId': '500'},
            'p2': {'serverId': '600'},
        })
        guild = MagicMock()
        guild.id = 600
        user = MagicMock()
        user.mutual_guilds = []
        self.assertTrue(await _slash_pred(predicates.isGuildOrUserSubscribed(True))(_slash_ctx(guild, user)))

    async def test_isSubscribed_subscribed_via_mutual_in_dm(self):
        # The DM branch checks `serverId in mutualGuilds` — the cog code compares an int
        # to the mutual_guilds collection, so we have to make `__contains__` true for 500.
        utils.getGuildsForPatreonToIgnore = MagicMock(return_value=[])
        patreon_queries.getAllPatrons = MagicMock(return_value={'p1': {'serverId': '500'}})
        mutual_guilds = MagicMock()
        mutual_guilds.__contains__ = lambda self, x: x == 500
        # ensure it's not None and not in the ignore-list path
        mutual_guilds.__iter__ = lambda self: iter([])
        user = MagicMock()
        user.mutual_guilds = mutual_guilds
        self.assertTrue(await _prefix_pred(predicates.isGuildOrUserSubscribed())(_prefix_ctx(None, user)))

    async def test_isSubscribed_no_match_raises(self):
        utils.getGuildsForPatreonToIgnore = MagicMock(return_value=[])
        patreon_queries.getAllPatrons = MagicMock(return_value={'p1': {'serverId': '500'}})
        guild = MagicMock()
        guild.id = 123
        user = MagicMock()
        user.mutual_guilds = []
        with self.assertRaises(NotSubscribed):
            await _slash_pred(predicates.isGuildOrUserSubscribed(True))(_slash_ctx(guild, user))

    async def test_isSubscribed_no_patrons_and_no_ignore_match_raises(self):
        utils.getGuildsForPatreonToIgnore = MagicMock(return_value=None)
        patreon_queries.getAllPatrons = MagicMock(return_value=None)
        guild = MagicMock()
        guild.id = 1
        user = MagicMock()
        user.mutual_guilds = []
        with self.assertRaises(NotSubscribed):
            await _prefix_pred(predicates.isGuildOrUserSubscribed())(_prefix_ctx(guild, user))

    async def test_isSubscribed_dm_mutual_guilds_not_in_ignore_continues_to_patron_check(self):
        # Exercises the loop-continues branch of the mutual_guilds ignore-list scan:
        # mutual_guilds non-empty, none in the ignore list, falls through to the patron
        # table (which also misses) → NotSubscribed.
        utils.getGuildsForPatreonToIgnore = MagicMock(return_value=[42])
        patreon_queries.getAllPatrons = MagicMock(return_value={'p1': {'serverId': '500'}})
        mutual_a = MagicMock(); mutual_a.id = 1
        mutual_b = MagicMock(); mutual_b.id = 2
        user = MagicMock()
        user.mutual_guilds = [mutual_a, mutual_b]
        with self.assertRaises(NotSubscribed):
            await _prefix_pred(predicates.isGuildOrUserSubscribed())(_prefix_ctx(None, user))

    async def test_isSubscribed_dm_with_none_mutual_guilds_does_not_crash(self):
        # When in a DM the code iterates mutual_guilds only if it isn't None.
        utils.getGuildsForPatreonToIgnore = MagicMock(return_value=[42])
        patreon_queries.getAllPatrons = MagicMock(return_value=None)
        user = MagicMock()
        user.mutual_guilds = None
        with self.assertRaises(NotSubscribed):
            await _slash_pred(predicates.isGuildOrUserSubscribed(True))(_slash_ctx(None, user))

    # endregion


if __name__ == '__main__':
    unittest.main()
