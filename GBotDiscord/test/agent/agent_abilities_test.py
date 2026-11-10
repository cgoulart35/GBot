#region IMPORTS
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from GBotDiscord.src.agent import agent_abilities, agent_client
from GBotDiscord.src.agent.agent_abilities import AgentAbilities
from GBotDiscord.src.reminders import reminders_cog
#endregion

NOW = datetime(2026, 11, 10, 1, 14, tzinfo = timezone.utc)

def person(userId, name, bot = False):
    made = Mock(id = userId, display_name = name, bot = bot, voice = Mock())
    made.name = name.lower()
    return made

class TestAgentAbilities(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\n\nStarting agent abilities unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted agent abilities unit tests.\n')

    def setUp(self):
        self.sender = person(1, 'Chris')
        self.sam = person(2, 'Sam')
        self.robot = person(3, 'Robot', bot = True)
        self.guild = Mock(id = 10, members = [self.sender, self.sam, self.robot])
        self.guild.get_member = Mock(side_effect = lambda userId: {1: self.sender, 2: self.sam, 3: self.robot}.get(userId))
        self.guild.get_channel_or_thread = Mock(return_value = Mock(mention = '<#20>'))
        self.msg = Mock(guild = self.guild, author = self.sender, channel = Mock(id = 20))
        self.music = Mock()
        self.music.listenerProblem = Mock(return_value = None)
        self.music.updateCard = AsyncMock()
        self.music.describeForAgent = Mock(return_value = 'Nothing is playing.')
        self.reminders = reminders_cog.Reminders(Mock())
        self.client = Mock()
        self.client.get_cog = Mock(side_effect = lambda name: {'Music': self.music, 'Reminders': self.reminders}[name])
        self.abilities = AgentAbilities(self.client)
        self.toggles = {}
        self.patch(agent_abilities.config_queries, 'getServerValue', MagicMock(side_effect = lambda serverId, toggle: self.toggles.get(toggle, True)))
        self.zone = None
        self.patch(agent_abilities.reminders_queries, 'getTimezone', MagicMock(side_effect = lambda userId: self.zone))

    def patch(self, target, name, value):
        started = patch.object(target, name, value)
        started.start()
        self.addCleanup(started.stop)
        return value

    async def use(self, name, toolInput = None, isAdmin = False, actions = None):
        return await self.abilities.run(name, toolInput or {}, self.msg, isAdmin, [] if actions is None else actions)

    # read

    async def test_a_tool_behind_a_feature_that_is_off_says_so(self):
        self.toggles['toggle_gcoin'] = False
        self.assertEqual(await self.use(agent_client.TOOL_GET_WALLET, {'user': ''}), ('GCoin is turned off in this server.', True))
        self.toggles['toggle_gcoin'] = None
        self.assertTrue((await self.use(agent_client.TOOL_GET_WALLET, {'user': ''}))[1])

    async def test_a_wallet_by_name_id_or_the_sender(self):
        balances = self.patch(agent_abilities.gcoin_queries, 'getUserBalance', MagicMock(side_effect = lambda userId: {1: '1250', 2: '5'}[userId]))
        self.assertEqual(await self.use(agent_client.TOOL_GET_WALLET, {'user': ''}), ('Chris: 1,250.00 GCoin', False))
        self.assertEqual(await self.use(agent_client.TOOL_GET_WALLET, {'user': '@sam'}), ('Sam: 5.00 GCoin', False))
        self.assertEqual(await self.use(agent_client.TOOL_GET_WALLET, {'user': '2'}), ('Sam: 5.00 GCoin', False))
        for wanted in ('nobody', '3', None):
            with self.subTest(wanted = wanted):
                self.assertEqual(await self.use(agent_client.TOOL_GET_WALLET, {'user': wanted}), (agent_abilities.NOBODY, True))
        self.assertEqual(balances.call_count, 3)

    async def test_the_ranking_is_this_servers_members_only(self):
        self.patch(agent_abilities.leaderboards_queries, 'getLeaderboard', MagicMock(return_value = {
            '1': {'balance': '10', 'numStormWins': 2}, '2': {'balance': '50', 'numWhoDisWins': 1}, '99': {'balance': '1000'}}))
        text, failed = await self.use(agent_client.TOOL_GET_RANKING)
        self.assertEqual(text, 'Sam: 50.00 GCoin, 0 Storm wins, 1 Who Dis wins\nChris: 10.00 GCoin, 2 Storm wins, 0 Who Dis wins')
        agent_abilities.leaderboards_queries.getLeaderboard.return_value = None
        self.assertEqual(await self.use(agent_client.TOOL_GET_RANKING), ('Nobody here is on the ranking yet.', False))

    async def test_the_market_searched_by_name_and_price(self):
        def listing(name, value, sellerId, kind = 'market'):
            return {'trxType': kind, 'sellerId': str(sellerId), 'item': {'name': name, 'value': value}}
        trades = {'a': listing('Golden Sword', '12', 2), 'b': listing('Wooden Sword', '3', 99), 'c': listing('Hat', '1', 1), 'd': listing('Secret Sword', '1', 1, 'personal')}
        self.patch(agent_abilities.gtrade_queries, 'getAllServerPendingTradeTransactions', MagicMock(return_value = trades))
        self.assertEqual(await self.use(agent_client.TOOL_SEARCH_MARKET, {'text': 'sword', 'max_price': ''}),
                         ('Wooden Sword: 3.00 GCoin, sold by a former member\nGolden Sword: 12.00 GCoin, sold by Sam', False))
        self.assertEqual(await self.use(agent_client.TOOL_SEARCH_MARKET, {'text': '', 'max_price': '5'}),
                         ('Hat: 1.00 GCoin, sold by Chris\nWooden Sword: 3.00 GCoin, sold by a former member', False))
        self.assertEqual(await self.use(agent_client.TOOL_SEARCH_MARKET, {'text': 'shield', 'max_price': ''}), ('Nothing like that is for sale.', False))
        self.assertEqual(await self.use(agent_client.TOOL_SEARCH_MARKET, {'text': None, 'max_price': 'cheap'}), ('That is not a price.', True))
        # more than fits says how many more
        agent_abilities.gtrade_queries.getAllServerPendingTradeTransactions.return_value = {str(n): listing(f'Item {n}', '1', 1) for n in range(30)}
        text, _ = await self.use(agent_client.TOOL_SEARCH_MARKET, {'text': '', 'max_price': None})
        self.assertTrue(text.endswith('...and 5 more.'))
        agent_abilities.gtrade_queries.getAllServerPendingTradeTransactions.return_value = None
        self.assertEqual((await self.use(agent_client.TOOL_SEARCH_MARKET, {'text': '', 'max_price': ''}))[0], 'Nothing like that is for sale.')

    async def test_someones_items(self):
        owned = self.patch(agent_abilities.gtrade_queries, 'getAllUserItems', MagicMock(return_value = {'i': {'name': 'Hat', 'value': '2.5'}}))
        self.assertEqual(await self.use(agent_client.TOOL_GET_ITEMS, {'user': 'sam'}), ('Sam has Hat: worth 2.50 GCoin', False))
        owned.assert_called_with(2)
        owned.return_value = None
        self.assertEqual(await self.use(agent_client.TOOL_GET_ITEMS, {'user': ''}), ('Chris has no items.', False))
        owned.return_value = {str(n): {'name': f'Item {n}', 'value': '1'} for n in range(27)}
        self.assertTrue((await self.use(agent_client.TOOL_GET_ITEMS, {'user': ''}))[0].endswith('...and 2 more.'))
        self.assertEqual(await self.use(agent_client.TOOL_GET_ITEMS, {'user': 'nobody'}), (agent_abilities.NOBODY, True))

    async def test_the_queue_and_the_features(self):
        self.assertEqual(await self.use(agent_client.TOOL_GET_MUSIC_QUEUE), ('Nothing is playing.', False))
        self.music.describeForAgent.assert_called_once_with('10', agent_abilities.MAX_ROWS)
        with patch.object(agent_abilities.help_cog, 'isFeatureOn', side_effect = lambda feature, guild: feature.name == 'Music'):
            text, failed = await self.use(agent_client.TOOL_GET_FEATURES)
        self.assertIn('Music: on', text)
        self.assertIn('Storms: off', text)
        self.assertNotIn('Config', text)

    async def test_reminders_are_the_senders_own_unless_an_admin_asks(self):
        self.zone = 'America/New_York'
        stored = {'r1': {'userId': '1', 'channelId': '20', 'text': 'dentist', 'nextAt': '2026-11-10T14:00:00+00:00', 'repeat': 'once', 'where': 'here'},
                  'r2': {'userId': '2', 'channelId': '20', 'text': 'sams', 'nextAt': '2026-11-10T15:00:00+00:00', 'repeat': 'daily', 'where': 'dm'}}
        self.patch(agent_abilities.reminders_queries, 'getServerReminders', MagicMock(return_value = stored))
        self.assertEqual(await self.use(agent_client.TOOL_GET_REMINDERS, {'user': ''}), ("Chris's reminders, in the sender's time:\nid r1: Tue, Nov 10 at 9:00 AM, dentist (here in <#20>)", False))
        self.assertEqual(await self.use(agent_client.TOOL_GET_REMINDERS, {'user': 'sam'}), ("Only admins can see someone else's reminders.", True))
        self.assertEqual(await self.use(agent_client.TOOL_GET_REMINDERS, {'user': 'sam'}, isAdmin = True), ("Sam's reminders, in the sender's time:\nid r2: Every day at 10:00 AM, sams (DM)", False))
        agent_abilities.reminders_queries.getServerReminders.return_value = None
        self.assertEqual(await self.use(agent_client.TOOL_GET_REMINDERS, {'user': ''}), ('Chris has no reminders here.', False))
        self.assertEqual(await self.use(agent_client.TOOL_GET_REMINDERS, {'user': 'nobody'}), (agent_abilities.NOBODY, True))

    # safe

    async def test_at_most_three_actions_per_message(self):
        actions = []
        for _ in range(3):
            await self.use(agent_client.TOOL_DELETE_REMINDER, {'id': ''}, actions = actions)
        self.assertEqual(await self.use(agent_client.TOOL_DELETE_REMINDER, {'id': ''}, actions = actions), ('You can only do 3 things per message.', True))
        # looking things up doesn't count
        self.assertEqual(len(actions), 3)

    async def test_playing_music_goes_through_the_command_and_reports_on_the_card(self):
        async def play(reply, author, args):
            self.assertEqual((reply.guild, reply.author, reply.channel, author, args), (self.guild, self.sender, self.msg.channel, self.sender, ['lofi beats']))
            await reply.send('💿 Added to the queue (#2)')
        self.music.commonPlay = play
        self.assertEqual(await self.use(agent_client.TOOL_PLAY_MUSIC, {'query': ' lofi beats '}), ("Done. 💿 Added to the queue (#2) The music card shows it, so don't repeat it.", False))
        self.music.updateCard.assert_awaited_once_with('10', '💿 Added to the queue (#2) · Chris')
        # when it starts playing, the now-playing card is posted and nothing more is said
        self.music.commonPlay = AsyncMock()
        self.assertEqual(await self.use(agent_client.TOOL_PLAY_MUSIC, {'query': 'more'}), ("Done. It is playing now. The music card shows it, so don't repeat it.", False))

    async def test_music_refusals_go_back_to_the_model(self):
        for query in ('', None, 'x' * 301):
            with self.subTest(query = query):
                self.assertEqual(await self.use(agent_client.TOOL_PLAY_MUSIC, {'query': query}), ('That is not something to search for.', True))
        self.sender.voice = None
        self.assertTrue((await self.use(agent_client.TOOL_PLAY_MUSIC, {'query': 'x'}))[0].startswith('The sender has to be in a voice channel'))
        async def refuse(reply, author, args):
            await reply.send(embed = Mock(description = 'Please play songs shorter than 30 minutes.'))
        self.sender.voice = Mock()
        self.music.commonPlay = refuse
        self.assertEqual(await self.use(agent_client.TOOL_PLAY_MUSIC, {'query': 'x'}), ('Please play songs shorter than 30 minutes.', True))
        self.music.updateCard.assert_not_awaited()
        self.music.commonPlay = AsyncMock(side_effect = RuntimeError('boom'))
        self.abilities.logger = MagicMock()
        self.assertEqual(await self.use(agent_client.TOOL_PLAY_MUSIC, {'query': 'x'}), ("That didn't work. Tell them to try /music.", True))
        self.abilities.logger.error.assert_called_once_with('GBot Agent failed a music action in server 10: RuntimeError')

    async def test_controlling_music_needs_the_sender_listening(self):
        async def skip(reply, author):
            await reply.send('⏭️ Skipped.')
        self.music.commonSkip = skip
        self.assertEqual((await self.use(agent_client.TOOL_CONTROL_MUSIC, {'action': 'skip'}))[1], False)
        self.music.updateCard.assert_awaited_once_with('10', '⏭️ Skipped. · Chris')
        self.music.listenerProblem.return_value = 'Join 🔊 **Lounge** to control the music.'
        self.assertEqual(await self.use(agent_client.TOOL_CONTROL_MUSIC, {'action': 'skip'}), ('Join 🔊 **Lounge** to control the music. So nothing happened. Tell them that.', True))
        self.assertEqual(await self.use(agent_client.TOOL_CONTROL_MUSIC, {'action': 'explode'}), ('That is not something you can do to the music.', True))

    async def test_setting_a_reminder_for_the_sender(self):
        self.patch(reminders_cog, 'utcNow', MagicMock(return_value = NOW))
        saved = self.patch(self.reminders, 'saveReminder', AsyncMock(return_value = 'r1'))
        values = {'when': 'tomorrow 9am', 'what': 'dentist', 'repeat': 'daily', 'where': 'dm'}
        self.assertEqual(await self.use(agent_client.TOOL_SET_REMINDER, values), ('They haven\'t set a time zone. Ask where they are, use set_timezone, then set the reminder.', True))
        self.zone = 'America/New_York'
        self.assertEqual(await self.use(agent_client.TOOL_SET_REMINDER, values), ('Set for Tue, Nov 10 at 9:00 AM in their time, every day at 9:00 am, by DM. Tell them when.', False))
        self.assertEqual(saved.await_args.args[1]['userId'], '1')
        self.assertEqual((await self.use(agent_client.TOOL_SET_REMINDER, dict(values, where = 'here', repeat = 'once')))[0], 'Set for Tue, Nov 10 at 9:00 AM in their time, once, here. Tell them when.')
        self.assertEqual(await self.use(agent_client.TOOL_SET_REMINDER, dict(values, when = 'soonish')), ('Nothing was set: I couldn\'t read "soonish" as a time. Try "in 2 hours", "tomorrow 9am", "Thursday 8pm" or "Dec 25 10:00".', True))
        for bad in (dict(values, what = ' '), dict(values, repeat = 'hourly'), dict(values, where = 'there'), dict(values, when = None)):
            with self.subTest(bad = bad):
                self.assertEqual(await self.use(agent_client.TOOL_SET_REMINDER, bad), ('A reminder needs when, what, repeat and where.', True))

    async def test_deleting_only_the_senders_own(self):
        stored = {'r1': {'userId': '1', 'text': 'dentist'}, 'r2': {'userId': '2', 'text': 'sams'}}
        self.patch(agent_abilities.reminders_queries, 'getReminder', MagicMock(side_effect = lambda serverId, reminderId: stored.get(reminderId)))
        removed = self.patch(agent_abilities.reminders_queries, 'removeReminder', MagicMock())
        self.assertEqual(await self.use(agent_client.TOOL_DELETE_REMINDER, {'id': 'r1'}), ('Deleted the reminder for dentist.', False))
        removed.assert_called_once_with(10, 'r1')
        for reminderId in ('r2', 'r9', '', None):
            with self.subTest(reminderId = reminderId):
                self.assertEqual(await self.use(agent_client.TOOL_DELETE_REMINDER, {'id': reminderId}, isAdmin = True), ('The sender has no reminder with that id here.', True))
        removed.assert_called_once()

    def test_every_read_and_safe_tool_has_a_handler_and_a_toggle_or_none_needed(self):
        for name in agent_client.READ_TOOLS | agent_client.SAFE_TOOLS:
            with self.subTest(name = name):
                self.assertTrue(name in agent_abilities.TOGGLES or name == agent_client.TOOL_GET_FEATURES)
