#region IMPORTS
import unittest
from unittest.mock import Mock
import nextcord

from GBotDiscord.src import server_setup
#endregion

def role(roleId, position, managed = False, default = False):
    made = Mock(id = roleId, mention = f'<@&{roleId}>', position = position, managed = managed)
    made.is_default = Mock(return_value = default)
    return made

def without(*names):
    permissions = nextcord.Permissions.all()
    permissions.update(**{name: False for name in names})
    return permissions

def granted(names):
    return nextcord.Permissions(**{name: True for name in names}).value

class TestServerSetup(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\n\nStarting server setup unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted server setup unit tests.\n')

    def setUp(self):
        self.top = role(1, 50)
        self.top.name = 'GBot'
        self.guild = Mock()
        self.guild.me = Mock(guild_permissions = nextcord.Permissions.all(), top_role = self.top)
        self.whoDis = role(444, 10)
        self.storms = Mock(mention = '<#222>', permissions_for = Mock(return_value = nextcord.Permissions.all()))
        self.admin = Mock(mention = '<#111>', permissions_for = Mock(return_value = nextcord.Permissions.all()))
        self.guild.get_channel = Mock(side_effect = lambda channelId: {222: self.storms, 111: self.admin}.get(channelId))
        self.guild.get_role = Mock(side_effect = lambda roleId: self.whoDis if roleId == 444 else None)
        self.config = {'toggle_storms': True, 'channel_storms': '222', 'channel_admin': '111', 'toggle_who_dis': True, 'role_who_dis': '444',
                       'toggle_music': True, 'toggle_hype': True, 'toggle_agent': True}

    def test_intents_are_only_those_used(self):
        intents = server_setup.gatewayIntents()
        used = {'guilds', 'members', 'presences', 'message_content', 'guild_messages', 'dm_messages', 'voice_states', 'emojis', 'guild_reactions', 'dm_reactions'}
        self.assertEqual({name for name, on in intents if on}, used)

    def test_the_invite_asks_for_exactly_what_features_need(self):
        permissions = server_setup.PERMISSIONS
        self.assertFalse(permissions.administrator)
        self.assertFalse(permissions.manage_guild)
        self.assertFalse(permissions.manage_channels)
        self.assertFalse(permissions.kick_members or permissions.ban_members)
        # every permission a check names is in the invite, and the invite holds nothing else but Mention Everyone
        checked = set(server_setup.BASICS + server_setup.STORMS_CHANNEL + server_setup.ADMIN_CHANNEL).union(*server_setup.FEATURE_PERMISSIONS.values())
        self.assertEqual(permissions.value, granted(checked | {'connect', 'speak', 'mention_everyone'}))
        self.assertEqual(granted(server_setup.PERMISSION_NAMES), granted(checked | {'connect', 'speak'}))
        url = server_setup.inviteUrl(123)
        self.assertIn('client_id=123', url)
        self.assertIn(f'permissions={permissions.value}', url)
        self.assertIn('scope=bot+applications.commands', url)

    def test_a_working_server_has_no_problems(self):
        self.assertEqual(server_setup.setupProblems(self.guild, self.config), [])

    def test_features_that_are_off_are_not_checked(self):
        self.guild.me.guild_permissions = without('connect', 'speak', 'add_reactions', 'manage_roles')
        self.assertEqual(server_setup.setupProblems(self.guild, {'toggle_music': False}), [])

    def test_missing_basics_and_feature_permissions(self):
        self.guild.me.guild_permissions = without('embed_links', 'connect', 'speak', 'add_reactions')
        self.assertEqual(server_setup.setupProblems(self.guild, dict(self.config, toggle_who_dis = False)), [
            'GBot is missing **Embed Links** server-wide.',
            '🎵 Music needs **Connect**, **Speak**.',
            '↩️ Hype needs **Add Reactions**.',
            '🤖 Agent needs **Add Reactions**.'
        ])

    def test_storms_channel(self):
        config = {'toggle_storms': True}
        self.assertEqual(server_setup.setupProblems(self.guild, config), ['Storms needs a channel. Pick one below.'])
        config['channel_storms'] = '999'
        self.assertEqual(server_setup.setupProblems(self.guild, config), ['The Storms channel was deleted. Pick a new one below.'])
        config['channel_storms'] = '222'
        self.storms.permissions_for.return_value = without('manage_messages', 'send_messages')
        self.assertEqual(server_setup.setupProblems(self.guild, config), ['GBot is missing **Send Messages**, **Manage Messages** in <#222>.'])
        self.storms.permissions_for.assert_called_with(self.guild.me)

    def test_admin_channel_is_checked_when_set(self):
        self.admin.permissions_for.return_value = without('view_channel')
        self.assertEqual(server_setup.setupProblems(self.guild, {'channel_admin': '111'}), ['GBot is missing **View Channels** in <#111>.'])
        self.assertEqual(server_setup.setupProblems(self.guild, {}), [])

    def test_who_dis_role(self):
        config = {'toggle_who_dis': True}
        self.assertEqual(server_setup.setupProblems(self.guild, config), ['Who Dis needs a role. Pick one in 👥 Roles.'])
        config['role_who_dis'] = '555'
        self.assertEqual(server_setup.setupProblems(self.guild, config), ['Who Dis needs a role. Pick one in 👥 Roles.'])
        config['role_who_dis'] = '444'
        self.whoDis.position = 60
        self.assertEqual(server_setup.setupProblems(self.guild, config), ["GBot can't give out <@&444>, as it's above GBot's own role. Move **GBot** above it in Server Settings → Roles."])
        # without Manage Roles, that's the one line, not two
        self.guild.me.guild_permissions = without('manage_roles')
        self.assertEqual(server_setup.setupProblems(self.guild, config), ['❓ Who Dis needs **Manage Roles**.'])

    def test_role_problem(self):
        self.assertIsNone(server_setup.roleProblem(self.guild, self.whoDis))
        self.assertEqual(server_setup.roleProblem(self.guild, self.top), "GBot can't give out <@&1>, as it's above GBot's own role. Move **GBot** above it in Server Settings → Roles.")
        self.assertEqual(server_setup.roleProblem(self.guild, role(2, 5, managed = True)), "<@&2> can't be given out by anyone, so pick another role.")
        self.assertEqual(server_setup.roleProblem(self.guild, role(3, 0, default = True)), "<@&3> can't be given out by anyone, so pick another role.")
        self.guild.me.guild_permissions = without('manage_roles')
        self.assertEqual(server_setup.roleProblem(self.guild, self.whoDis), 'GBot needs the **Manage Roles** permission to give out <@&444>.')
