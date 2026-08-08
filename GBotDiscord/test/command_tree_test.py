#region IMPORTS
import unittest
from unittest.mock import AsyncMock, Mock

import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context

from GBotDiscord.src import strings
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.config.config_cog import Config
from GBotDiscord.src.gcoin.gcoin_cog import GCoin
from GBotDiscord.src.gtrade.gtrade_cog import GTrade
from GBotDiscord.src.hype.hype_cog import Hype
from GBotDiscord.src.music.music_cog import Music
from GBotDiscord.src.patreon.patreon_cog import Patreon
from GBotDiscord.src.storms.storms_cog import Storms
from GBotDiscord.src.whodis.whodis_cog import WhoDis
#endregion

# Every command lives under its cog's group (E-PR1). This suite is the guard on that shape: it
# fails if a future command is added flat, if the slash and prefix halves drift apart, or if an
# alias chain stops resolving. Those are exactly the mistakes the suite could not otherwise catch,
# because a flat command works perfectly well in isolation — it just re-pollutes the global
# namespace the grouping exists to keep clean.

# cog class -> (group name, group aliases, checks on the prefix root). Patreon is deliberately
# absent: it has one command and grouping it would only ever yield "/patreon patreon".
#
# The check counts are the point of test_prefix_group_roots_are_gated below. A bare ".music" is
# dispatched as its own command (see that test), so a root without checks is a way into a gated cog
# that skips subscription, the feature toggle and the legacy-prefix toggle. Each count is the number
# of checks every leaf in that group shares; if a leaf's stack changes, this is meant to fail.
GROUPED_COGS = {
    Config: (strings.CONFIG_GROUP_NAME, strings.CONFIG_GROUP_ALIASES, 4),
    GCoin: (strings.GCOIN_GROUP_NAME, strings.GCOIN_GROUP_ALIASES, 3),
    GTrade: (strings.GTRADE_GROUP_NAME, strings.GTRADE_GROUP_ALIASES, 3),
    Hype: (strings.HYPE_GROUP_NAME, strings.HYPE_GROUP_ALIASES, 5),
    Music: (strings.MUSIC_GROUP_NAME, strings.MUSIC_GROUP_ALIASES, 4),
    Storms: (strings.STORMS_GROUP_NAME, strings.STORMS_GROUP_ALIASES, 4),
    WhoDis: (strings.WHODIS_GROUP_NAME, strings.WHODIS_GROUP_ALIASES, 3),
}

UNGROUPED_COMMANDS = {strings.PATREON_NAME}

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/command_tree_test.py
#   - or use the "Python: Current File" run configuration to run command_tree_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestCommandTree(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting command tree unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted command tree unit tests.\n')

    def setUp(self):
        # an unset property would be passed to nextcord as guild_ids = None
        GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS = []
        # intents mirror main.py's; without message content nextcord warns on every prefix command
        self.client: nextcord.Client = commands.Bot(command_prefix = '.', intents = nextcord.Intents.all())
        self.cogs = {}
        for cogClass in list(GROUPED_COGS) + [Patreon]:
            cog = cogClass(self.client)
            self.cogs[cogClass] = cog
            self.client.add_cog(cog)

    def slashRoots(self):
        return {command.name: command for command in self.client.get_all_application_commands()}

    def test_every_slash_command_is_grouped_under_its_cog(self):
        roots = self.slashRoots()
        expected = {name for name, *_ in GROUPED_COGS.values()} | UNGROUPED_COMMANDS
        self.assertEqual(set(roots), expected)
        for groupName, *_ in GROUPED_COGS.values():
            self.assertTrue(roots[groupName].children,
                            f'/{groupName} registered no subcommands, so it is not invocable at all')

    def test_slash_namespace_stays_eight_names_wide(self):
        roots = self.slashRoots()
        invocable = sum(len(root.children) or 1 for root in roots.values())
        # the point of the exercise: many commands, few global names
        self.assertEqual(len(roots), 8)
        self.assertEqual(invocable, 36)

    def test_prefix_tree_mirrors_the_slash_tree(self):
        roots = self.slashRoots()
        for groupName, aliases, _ in GROUPED_COGS.values():
            group = self.client.get_command(groupName)
            self.assertIsInstance(group, commands.Group, f'.{groupName} is not a prefix group')
            self.assertEqual(group.aliases, aliases)
            self.assertEqual({command.name for command in group.commands},
                             set(roots[groupName].children),
                             f'.{groupName} and /{groupName} expose different subcommands')

    def test_group_and_leaf_aliases_resolve(self):
        # a group alias plus a leaf alias has to compose, or ".m p" stops being a usable shorthand
        for groupAlias, leafAlias, expected in (('m', 'p', 'music play'),
                                                ('c', 's', 'config show'),
                                                ('gc', 'sd', 'gcoin send'),
                                                ('gt', 'by', 'gtrade buy'),
                                                ('hy', 'rm', 'hype remove'),
                                                ('s', 'u', 'storms umbrella'),
                                                ('wd', 'g', 'whodis guess')):
            self.assertEqual(self.client.get_command(groupAlias).get_command(leafAlias).qualified_name, expected)

    def test_group_names_and_aliases_do_not_collide(self):
        claimed = []
        for groupName, aliases, _ in GROUPED_COGS.values():
            claimed += [groupName] + list(aliases)
        claimed += list(UNGROUPED_COMMANDS) + list(strings.PATREON_ALIASES)
        self.assertEqual(len(claimed), len(set(claimed)), f'two groups claim the same prefix token: {claimed}')

    def test_leaf_names_and_aliases_are_unique_within_each_group(self):
        for groupName, *_ in GROUPED_COGS.values():
            claimed = []
            for command in self.client.get_command(groupName).commands:
                claimed += [command.name] + list(command.aliases)
            self.assertEqual(len(claimed), len(set(claimed)),
                             f'.{groupName} has a leaf name/alias collision: {claimed}')

    async def test_slash_group_roots_are_inert(self):
        # Discord never invokes a slash command that owns subcommands, so these bodies only exist to
        # give nextcord something to hang the group on. Called directly to prove they do nothing.
        interaction: nextcord.Interaction = Mock(spec = nextcord.Interaction)
        for cogClass, (groupName, _, _) in GROUPED_COGS.items():
            cog = self.cogs[cogClass]
            root = getattr(cog, f'{groupName}SlashGroup')
            self.assertIsNone(await root(interaction))

    def test_prefix_group_roots_are_gated(self):
        # A bare ".music" is dispatched as its own command: invoke_without_command means nextcord
        # skips the root's prepare() when a subcommand matched, and falls back to Command.invoke —
        # which does run can_run() — when none did. So an unchecked root would answer in a guild
        # that is unsubscribed, has the feature switched off, or has legacy prefix commands
        # disabled, none of which any leaf in the group would answer in.
        for groupName, _, expectedChecks in GROUPED_COGS.values():
            group = self.client.get_command(groupName)
            self.assertEqual(len(group.checks), expectedChecks,
                             f'.{groupName} root no longer carries the checks its leaves share')

    async def test_prefix_group_roots_send_the_group_help(self):
        # a bare ".music" names no subcommand; silence would read as the bot being broken.
        # These cogs are registered with add_cog, so nextcord injects the cog into the callback
        # itself — unlike the per-cog suites, which never add the cog and pass it by hand.
        for cogClass, (groupName, _, _) in GROUPED_COGS.items():
            cog = self.cogs[cogClass]
            ctx: Context = Mock(spec = Context)
            ctx.send_help = AsyncMock()
            ctx.command = self.client.get_command(groupName)
            await getattr(cog, f'{groupName}Group')(ctx)
            ctx.send_help.assert_awaited_once_with(ctx.command)
