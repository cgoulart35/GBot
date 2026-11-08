#region IMPORTS
import ast
import pathlib
import re
import unittest
from unittest.mock import AsyncMock, Mock

import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context

from GBotDiscord.src import strings
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.agent.agent_cog import Agent
from GBotDiscord.src.config.config_cog import Config
from GBotDiscord.src.gcoin.gcoin_cog import GCoin
from GBotDiscord.src.gtrade.gtrade_cog import GTrade
from GBotDiscord.src.help.help_cog import Help
from GBotDiscord.src.hype.hype_cog import Hype
from GBotDiscord.src.music.music_cog import Music
from GBotDiscord.src.patreon.patreon_cog import Patreon
from GBotDiscord.src.storms.storms_cog import Storms
from GBotDiscord.src.whodis.whodis_cog import WhoDis
#endregion

# One command per feature (8.2): with no fields it opens the feature's card, and optional fields give a
# fast path where one is worth having. This suite is the guard on that shape: it fails if a feature
# grows subcommands again, if its slash and prefix halves drift apart, if an alias collides, or if a
# prefix command loses the checks its slash half has.

# feature command -> (its aliases, how many checks its prefix half carries). A prefix command is
# dispatched on its own, so a missing check is a way past subscription, the feature's toggle, the
# legacy-prefix toggle or the admin check. If a command's stack changes, this is meant to fail.
COMMANDS = {
    strings.AGENT_NAME: (strings.AGENT_ALIASES, 4),
    strings.CONFIG_NAME: (strings.CONFIG_ALIASES, 4),
    strings.GCOIN_NAME: (strings.GCOIN_ALIASES, 3),
    strings.GTRADE_NAME: (strings.GTRADE_ALIASES, 3),
    strings.HYPE_NAME: (strings.HYPE_ALIASES, 5),
    strings.MUSIC_NAME: (strings.MUSIC_ALIASES, 4),
    strings.PATREON_NAME: (strings.PATREON_ALIASES, 4),
    strings.STORMS_NAME: (strings.STORMS_ALIASES, 4),
    strings.WHODIS_NAME: (strings.WHODIS_ALIASES, 3),
}

# the right-click menus (Apps), by the kind of thing they're on. Discord allows 5 of each.
CONTEXT_MENUS = {
    strings.REPORT_MESSAGE_NAME: nextcord.ApplicationCommandType.message,
    strings.REPORT_MEMBER_NAME: nextcord.ApplicationCommandType.user,
    strings.GCOIN_VIEW_WALLET_NAME: nextcord.ApplicationCommandType.user,
    strings.GTRADE_VIEW_ITEMS_NAME: nextcord.ApplicationCommandType.user,
    strings.GTRADE_CRAFT_ITEM_NAME: nextcord.ApplicationCommandType.message,
}

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
        for cogClass in (Agent, Config, GCoin, GTrade, Help, Hype, Music, Patreon, Storms, WhoDis):
            self.client.add_cog(cogClass(self.client))

    def slashRoots(self):
        return {command.name: command for command in self.client.get_all_application_commands() if command.type == nextcord.ApplicationCommandType.chat_input}

    def test_one_command_per_feature(self):
        roots = self.slashRoots()
        self.assertEqual(set(roots), set(COMMANDS) | {strings.HELP_NAME})
        for name, root in roots.items():
            self.assertFalse(root.children, f'/{name} has subcommands again')

    def test_the_right_click_menus(self):
        menus = {command.name: command.type for command in self.client.get_all_application_commands() if command.type != nextcord.ApplicationCommandType.chat_input}
        self.assertEqual(menus, CONTEXT_MENUS)
        for kind in (nextcord.ApplicationCommandType.message, nextcord.ApplicationCommandType.user):
            self.assertLessEqual(list(menus.values()).count(kind), 5)

    def test_prefix_commands_have_the_slash_commands_shape(self):
        # Slash and prefix keep the same shape: the same name, aliases and arguments in the same order
        roots = self.slashRoots()
        for name, (aliases, _) in COMMANDS.items():
            with self.subTest(command = name):
                prefix = self.client.get_command(name)
                self.assertIsInstance(prefix, commands.Command)
                self.assertNotIsInstance(prefix, commands.Group)
                self.assertEqual(prefix.aliases, aliases)
                self.assertEqual(list(prefix.clean_params), list(roots[name].options))

    def test_names_and_aliases_do_not_collide(self):
        claimed = [strings.HELP_NAME]
        for name, (aliases, _) in COMMANDS.items():
            claimed += [name] + list(aliases)
        self.assertEqual(len(claimed), len(set(claimed)), f'two commands claim the same prefix token: {claimed}')
        for name, (aliases, _) in COMMANDS.items():
            for alias in aliases:
                self.assertEqual(self.client.get_command(alias).name, name)

    def test_prefix_commands_are_gated(self):
        for name, (_, expectedChecks) in COMMANDS.items():
            with self.subTest(command = name):
                self.assertEqual(len(self.client.get_command(name).checks), expectedChecks, f'.{name} no longer carries its checks')

    def test_commands_named_in_sent_text_exist(self):
        # Text the bot sends names commands as string literals ("Use '**/storms guess [number]**'"),
        # and no per-cog suite notices when a rename leaves one pointing at a command that is gone.
        # Comments are not literals, and Halo's archived strings are not sent.
        roots = self.slashRoots()
        source = pathlib.Path(__file__).resolve().parents[1] / 'src'
        named = re.compile(r"[`'*]/([a-zA-Z_]+)(?: ([a-zA-Z_]+))?")
        checked = 0
        for path in source.rglob('*.py'):
            if 'halo' in path.parts:
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    for root, leaf in named.findall(node.value):
                        checked += 1
                        self.assertIn(root, roots, f'{path.name}:{node.lineno} names /{root}, which does not exist')
                        if roots[root].children:
                            self.assertIn(leaf, roots[root].children, f'{path.name}:{node.lineno} names /{root} {leaf}, which does not exist')
                        elif leaf:
                            # a command of its own takes options, not subcommands: /config toggle is gone
                            self.assertIn(leaf, roots[root].options, f'{path.name}:{node.lineno} names /{root} {leaf}, but /{root} has no {leaf}')
        # the regex matching nothing at all would otherwise pass silently
        self.assertGreater(checked, 0)
