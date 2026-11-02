#region IMPORTS
import json
import pathlib
import re
import unittest

import nextcord
from nextcord.ext import commands

from GBotDiscord.src import presentation
from GBotDiscord.src import strings
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.config.config_cog import Config
from GBotDiscord.src.gcoin.gcoin_cog import GCoin
from GBotDiscord.src.gtrade.gtrade_cog import GTrade
from GBotDiscord.src.help.help_cog import FEATURES, Help
from GBotDiscord.src.hype.hype_cog import Hype
from GBotDiscord.src.music.music_cog import Music
from GBotDiscord.src.patreon.patreon_cog import Patreon
from GBotDiscord.src.storms.storms_cog import Storms
from GBotDiscord.src.whodis.whodis_cog import WhoDis
#endregion

# The website and the README describe the bot by hand, so nothing else notices when a command or
# version changes and they don't. This suite compares them with the real thing: it fails when a
# command is added, renamed or reworded without updating site/_data/commands.json and the README.

ROOT = pathlib.Path(__file__).resolve().parents[2]
SITE = ROOT / 'site'
README = (ROOT / 'README.md').read_text()

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/site_drift_test.py
#   - or use the "Python: Current File" run configuration to run site_drift_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestSiteDrift(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting site drift unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted site drift unit tests.\n')

    def setUp(self):
        GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS = []
        self.client = commands.Bot(command_prefix = '.', intents = nextcord.Intents.all())
        for cogClass in (Config, GCoin, GTrade, Help, Hype, Music, Patreon, Storms, WhoDis):
            self.client.add_cog(cogClass(self.client))
        self.roots = {command.name: command for command in self.client.get_all_application_commands()}
        self.groups = json.loads((SITE / '_data' / 'commands.json').read_text())
        self.documented = {command['name']: (group, command) for group in self.groups for command in group['commands']}

    def realCommands(self):
        # every invocable command, as (full name, its slash half, its prefix half)
        for rootName, root in self.roots.items():
            prefixRoot = self.client.get_command(rootName)
            if root.children:
                for leafName, leaf in root.children.items():
                    yield f'{rootName} {leafName}', leaf, prefixRoot.get_command(leafName)
            else:
                yield rootName, root, prefixRoot

    def slashSyntax(self, name, slash):
        arguments = [f'<{option}>' if details.required else f'[{option}]' for option, details in slash.options.items()]
        return ' '.join([f'/{name}'] + arguments)

    def prefixSyntax(self, prefix):
        parts = ['[' + '|'.join([part.name] + list(part.aliases)) + ']' for part in prefix.parents[::-1] + [prefix]]
        return ('.' + ' '.join(parts + [prefix.signature])).rstrip()

    def test_every_real_command_is_documented_and_nothing_else_is(self):
        self.assertEqual(set(self.documented), {name for name, *_ in self.realCommands()})

    def test_documented_commands_match_the_real_ones(self):
        for name, slash, prefix in self.realCommands():
            _, command = self.documented[name]
            with self.subTest(command = name):
                self.assertEqual(command['aliases'], list(prefix.aliases))
                self.assertEqual(command['summary'], slash.description)
                self.assertEqual(command['slash'], self.slashSyntax(name, slash))
                # .help is the one prefix command with no description of its own, and its argument
                # is free text rather than a typed signature, so there is nothing real to compare
                if name != strings.HELP_NAME:
                    self.assertEqual(command['description'], prefix.description)
                    self.assertEqual(command['prefix'], self.prefixSyntax(prefix))
                choices = [{'option': option, 'choices': list(details.choices)} for option, details in slash.options.items() if details.choices]
                self.assertEqual(command['choices'], choices)

    def test_group_aliases_match(self):
        for group in self.groups:
            self.assertEqual(group['aliases'], list(self.client.get_command(group['key']).aliases))

    def test_examples_run_the_command_they_sit_under(self):
        for name, (_, command) in self.documented.items():
            self.assertTrue(command['examples'], f'{name} has no example')
            for example in command['examples']:
                with self.subTest(example = example):
                    tokens = example.split()
                    if tokens[0].startswith('/'):
                        self.assertEqual(tokens[0][1:], name.split()[0])
                        continue
                    resolved = self.client.get_command(tokens[0][1:])
                    if isinstance(resolved, commands.Group):
                        resolved = resolved.get_command(tokens[1])
                    self.assertEqual(resolved.qualified_name, name)

    def test_shorthands_run_their_command(self):
        for name, (_, command) in self.documented.items():
            tokens = command['shorthand'][1:].split()
            resolved = self.client.get_command(tokens[0])
            if len(tokens) > 1:
                resolved = resolved.get_command(tokens[1])
            self.assertEqual(resolved.qualified_name, name)

    def test_readme_lists_every_command(self):
        rows = re.findall(r'^\| `/([^`]+)` \| `([^`]+)` \| (.+) \|$', README, re.MULTILINE)
        self.assertEqual({row[0] for row in rows}, set(self.documented))
        for name, shorthand, summary in rows:
            _, command = self.documented[name]
            with self.subTest(command = name):
                self.assertEqual(shorthand, command['shorthand'])
                self.assertEqual(summary, command['summary'])

    def test_version_matches_everywhere(self):
        version = re.search(r'^GBOT_VERSION=(.+)$', (ROOT / 'Shared' / 'gbot.env.example').read_text(), re.MULTILINE).group(1)
        self.assertIn(f'version: "{version}"', (SITE / '_config.yml').read_text())
        self.assertIn(f'<h1 align="center">GBot {version}</h1>', README)
        changelog = (SITE / '_includes' / 'changelog.md').read_text()
        self.assertTrue(changelog.startswith(f'#### GBot {version}\n'))

    def test_feature_emoji_match_the_bot(self):
        features = json.loads((SITE / '_data' / 'features.json').read_text())
        self.assertEqual({feature['toggle']: feature['emoji'] for feature in features},
                         {toggle: emoji for toggle, emoji in strings.FEATURE_EMOJIS.items() if toggle != 'toggle_legacy_prefix_commands'})
        real = {feature.group: feature.emoji for feature in FEATURES}
        for group in self.groups:
            if group['key'] in real:
                self.assertEqual(group['emoji'], real[group['key']], group['key'])

    def test_brand_color_matches_everywhere(self):
        color = f'{presentation.BRAND_COLOR.value:06X}'
        self.assertIn(f'--accent: #{color.lower()};', (SITE / 'assets' / 'css' / 'site.css').read_text())
        self.assertEqual(set(re.findall(r'badge/[^"]*-([0-9A-F]{6})\?style', README)), {color})

    def test_readme_features_match_the_site(self):
        for feature in json.loads((SITE / '_data' / 'features.json').read_text()):
            self.assertIn(f"| {feature['emoji']} **{feature['name']}** | {feature['blurb']} |", README)

    def test_changelogs_match(self):
        section = README[README.index('## Changelog\n') + len('## Changelog\n'):README.index('## Setup Guide')]
        self.assertEqual(section.strip(), (SITE / '_includes' / 'changelog.md').read_text().strip())
