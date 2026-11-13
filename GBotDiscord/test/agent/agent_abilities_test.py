#region IMPORTS
import asyncio
import unittest
import nextcord
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from GBotDiscord.src.agent import agent_abilities, agent_client
from GBotDiscord.src.agent.agent_abilities import AgentAbilities
from GBotDiscord.src.reminders import reminders_cog, when
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
        self.guild.name = 'My Server'
        self.guild.get_member = Mock(side_effect = lambda userId: {1: self.sender, 2: self.sam, 3: self.robot}.get(userId))
        self.guild.get_channel_or_thread = Mock(return_value = Mock(mention = '<#20>'))
        self.msg = Mock(guild = self.guild, author = self.sender, channel = Mock(id = 20))
        self.music = Mock()
        self.music.listenerProblem = Mock(return_value = None)
        self.music.updateCard = AsyncMock()
        self.music.postCard = AsyncMock()
        self.music.musicStates = {'10': {'card': Mock(), 'lastAction': None}}
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

    async def use(self, name, toolInput = None, isAdmin = False, actions = None, cards = None):
        # each call its own message, with its own cards, unless a test shares them
        return await self.abilities.run(name, toolInput or {}, self.msg, isAdmin, [] if actions is None else actions, [] if cards is None else cards)

    # read

    async def test_a_tool_behind_a_feature_that_is_off_says_so(self):
        self.toggles['toggle_gcoin'] = False
        self.assertEqual(await self.use(agent_client.TOOL_GET_WALLET, {'user': ''}), ('GCoin is turned off in this server.', True))
        self.toggles['toggle_gcoin'] = None
        self.assertTrue((await self.use(agent_client.TOOL_GET_WALLET, {'user': ''}))[1])

    async def test_a_time_zone_change_is_counted_and_behind_reminders(self):
        # it moves every reminder of theirs, so it's an action like any other
        agent = MagicMock(toolSetTimezone = AsyncMock(return_value = ('Set.', False)))
        self.client.get_cog.side_effect = lambda name: agent if name == 'Agent' else None
        actions = []
        self.assertEqual(await self.use(agent_client.TOOL_SET_TIMEZONE, {'zone': 'Europe/Berlin'}, actions = actions), ('Set.', False))
        agent.toolSetTimezone.assert_awaited_once_with({'zone': 'Europe/Berlin'}, self.msg)
        self.assertEqual(actions, [agent_client.TOOL_SET_TIMEZONE])
        self.assertEqual(await self.use(agent_client.TOOL_SET_TIMEZONE, {'zone': 'Europe/Berlin'}, actions = ['a', 'b', 'c']), (agent_abilities.CAPPED, True))
        self.toggles['toggle_reminders'] = False
        self.assertEqual(await self.use(agent_client.TOOL_SET_TIMEZONE, {'zone': 'Europe/Berlin'}), ('Reminders is turned off in this server.', True))
        agent.toolSetTimezone.assert_awaited_once()

    async def test_a_wallet_by_name_id_or_the_sender(self):
        balances = self.patch(agent_abilities.gcoin_queries, 'getUserBalance', MagicMock(side_effect = lambda userId: {1: '1250', 2: '5'}[userId]))
        self.assertEqual(await self.use(agent_client.TOOL_GET_WALLET, {'user': ''}), ('Chris: 1,250.00 GCoin', False))
        self.assertEqual(await self.use(agent_client.TOOL_GET_WALLET, {'user': '@sam'}), ('Sam: 5.00 GCoin', False))
        # a mention as it was typed, which is how Discord shows one in a message
        self.assertEqual(await self.use(agent_client.TOOL_GET_WALLET, {'user': '<@2>'}), ('Sam: 5.00 GCoin', False))
        self.assertEqual(await self.use(agent_client.TOOL_GET_WALLET, {'user': '<@!2>'}), ('Sam: 5.00 GCoin', False))
        self.assertEqual(await self.use(agent_client.TOOL_GET_WALLET, {'user': '2'}), ('Sam: 5.00 GCoin', False))
        for wanted in ('nobody', '3', None):
            with self.subTest(wanted = wanted):
                self.assertEqual(await self.use(agent_client.TOOL_GET_WALLET, {'user': wanted}), (agent_abilities.NOBODY, True))
        self.assertEqual(balances.call_count, 5)

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
        # every one, as "do I own it" has to see them all
        owned.return_value = {str(n): {'name': f'Item {n}', 'value': '1'} for n in range(27)}
        self.assertTrue((await self.use(agent_client.TOOL_GET_ITEMS, {'user': ''}))[0].endswith('Item 26: worth 1.00 GCoin'))
        self.assertEqual(await self.use(agent_client.TOOL_GET_ITEMS, {'user': 'nobody'}), (agent_abilities.NOBODY, True))

    async def test_the_queue_and_the_features(self):
        self.assertEqual(await self.use(agent_client.TOOL_GET_MUSIC_QUEUE), ('Nothing is playing.', False))
        self.music.describeForAgent.assert_called_once_with('10', agent_abilities.MAX_ROWS)
        with patch.object(agent_abilities.help_cog, 'isFeatureOn', side_effect = lambda feature, guild: feature.name == 'Music'):
            text, failed = await self.use(agent_client.TOOL_GET_FEATURES)
        self.assertIn('Music: on', text)
        self.assertIn('Storms: off', text)
        self.assertNotIn('Config', text)

    async def test_reminders_give_the_agent_only_the_senders_times(self):
        self.zone = 'America/New_York'
        stored = {'r1': {'userId': '1', 'channelId': '20', 'text': 'dentist', 'nextAt': '2026-11-10T14:00:00+00:00', 'repeat': 'once', 'where': 'here'},
                  'r2': {'userId': '2', 'channelId': '20', 'text': 'sams', 'nextAt': '2026-11-10T15:00:00+00:00', 'repeat': 'daily', 'where': 'dm'}}
        self.patch(agent_abilities.reminders_queries, 'getServerReminders', MagicMock(return_value = stored))
        text, failed = await self.use(agent_client.TOOL_GET_REMINDERS, {}, isAdmin = True)
        # ids and times, never what they say, which open_card shows privately
        self.assertEqual((text, failed), ('What they say is private, so to show them use open_card with Reminders. Their ids and times:\nid r1: Tue, Nov 10 at 9:00 AM', False))
        self.assertNotIn('dentist', text)
        # a snooze says so, as it sits beside its repeat
        stored['r1']['snoozeOf'] = 'r9'
        self.assertTrue((await self.use(agent_client.TOOL_GET_REMINDERS, {}))[0].endswith('id r1: Tue, Nov 10 at 9:00 AM (a snooze)'))
        agent_abilities.reminders_queries.getServerReminders.return_value = None
        self.assertEqual(await self.use(agent_client.TOOL_GET_REMINDERS, {}), ('They have no reminders here.', False))

    # safe

    async def test_at_most_three_actions_per_message(self):
        self.patch(agent_abilities.reminders_queries, 'getServerReminders', MagicMock(return_value = None))
        actions = []
        for _ in range(3):
            self.assertEqual(await self.use(agent_client.TOOL_DELETE_REMINDER, {'ids': []}, actions = actions), ('They have no reminders here.', True))
        self.assertEqual(await self.use(agent_client.TOOL_DELETE_REMINDER, {'ids': []}, actions = actions), (agent_abilities.CAPPED, True))
        # looking things up doesn't count
        self.assertEqual(len(actions), 3)

    async def test_a_members_admin_only_ask_uses_no_action(self):
        actions = []
        self.assertEqual(await self.use(agent_client.TOOL_REMIND_ROLE, {'when': 'x', 'what': 'y', 'repeat': 'once', 'days': [], 'role': 'all'}, actions = actions), ('Only admins can do that.', True))
        self.assertEqual(actions, [])

    async def test_gcoin_goes_to_one_person_per_message(self):
        # "send everyone 5 GCoin" offers the first send only
        actions = ['send_gcoin']
        self.assertEqual(await self.use(agent_client.TOOL_SEND_GCOIN, {'user': 'sam', 'amount': '5', 'note': ''}, actions = actions), (agent_abilities.ONE_SEND, True))
        self.assertEqual(actions, ['send_gcoin'])

    async def test_playing_music_goes_through_the_command_and_reports_on_the_card(self):
        async def play(reply, author, args):
            self.assertEqual((reply.guild, reply.author, reply.channel, author, args), (self.guild, self.sender, self.msg.channel, self.sender, ['lofi beats']))
            await reply.send('💿 Added to the queue (#2)')
        self.music.commonPlay = play
        cards = []
        # queued: the card comes down to the bottom with that on it, and is the whole reply
        self.assertEqual(await self.abilities.run(agent_client.TOOL_PLAY_MUSIC, {'query': ' lofi beats '}, self.msg, False, [], cards), ('Done: 💿 Added to the queue (#2) The music card, moved to the bottom with that on it, is your whole reply, so nothing you write is shown.', False))
        self.assertEqual(self.music.musicStates['10']['lastAction'], '💿 Added to the queue (#2) · Chris')
        self.music.postCard.assert_awaited_once_with('10', self.msg.channel, moveDown = True)
        self.assertEqual(cards, [self.msg])
        # with no card, as after a Stop, a few words say it
        self.music.musicStates['10']['card'] = None
        self.assertEqual(await self.use(agent_client.TOOL_PLAY_MUSIC, {'query': 'lofi beats'}), ('Done: 💿 Added to the queue (#2) Say so in a few words.', False))
        self.music.postCard.assert_awaited_once()
        # started: the now-playing card just posted is the whole reply
        self.music.commonPlay = AsyncMock()
        cards = []
        self.assertEqual(await self.abilities.run(agent_client.TOOL_PLAY_MUSIC, {'query': 'more'}, self.msg, False, [], cards), ('It is playing now. The now-playing card GBot posted is your whole reply, so nothing you write is shown.', False))
        self.assertEqual(cards, [self.msg])
        # a playlist started from idle: the engine has just posted the card, which only gets its line
        async def playlist(reply, author, args):
            self.music.musicStates['10']['card'] = Mock()
            await reply.send('💿 Added 12 songs to the queue.')
        self.music.commonPlay = playlist
        self.music.musicStates['10']['card'] = None
        text, failed = await self.use(agent_client.TOOL_PLAY_MUSIC, {'query': 'a playlist'})
        self.assertFalse(failed)
        self.music.postCard.assert_awaited_once()
        self.music.updateCard.assert_awaited_once_with('10')
        self.assertEqual(self.music.musicStates['10']['lastAction'], '💿 Added 12 songs to the queue. · Chris')
        # outside a run, nothing collects it
        self.music.commonPlay = AsyncMock()
        await self.use(agent_client.TOOL_PLAY_MUSIC, {'query': 'more'})
        self.music.musicStates['10']['card'] = Mock()
        self.music.commonPlay = play
        await self.use(agent_client.TOOL_PLAY_MUSIC, {'query': 'lofi beats'})

    async def test_music_refusals_go_back_to_the_model(self):
        for query in (None, 'x' * 301):
            with self.subTest(query = query):
                self.assertEqual(await self.use(agent_client.TOOL_PLAY_MUSIC, {'query': query}), ('That is not something to search for.', True))
        # "play" with nothing to search for resumes, under the card's rules
        async def resume(reply, author):
            await reply.send('▶️ Resumed.')
        self.music.commonResume = resume
        self.assertEqual((await self.use(agent_client.TOOL_PLAY_MUSIC, {'query': ' '}))[0].startswith('Done: ▶️ Resumed. The music card'), True)
        self.music.postCard.reset_mock()
        self.sender.voice = None
        self.assertTrue((await self.use(agent_client.TOOL_PLAY_MUSIC, {'query': 'x'}))[0].startswith('The sender has to be in a voice channel'))
        async def refuse(reply, author, args):
            await reply.send(embed = Mock(description = 'Please play songs shorter than 30 minutes.'))
        self.sender.voice = Mock()
        self.music.commonPlay = refuse
        self.assertEqual(await self.use(agent_client.TOOL_PLAY_MUSIC, {'query': 'x'}), ('Please play songs shorter than 30 minutes.', True))
        self.music.postCard.assert_not_awaited()
        self.music.commonPlay = AsyncMock(side_effect = RuntimeError('boom'))
        self.abilities.logger = MagicMock()
        self.assertEqual(await self.use(agent_client.TOOL_PLAY_MUSIC, {'query': 'x'}), ("That didn't work. Tell them to try /music.", True))
        self.abilities.logger.error.assert_called_once_with('GBot Agent failed a music action in server 10: RuntimeError')

    async def test_controlling_music_needs_the_sender_listening(self):
        async def skip(reply, author):
            await reply.send('⏭️ Skipped.')
        self.music.commonSkip = skip
        self.assertEqual((await self.use(agent_client.TOOL_CONTROL_MUSIC, {'action': 'skip'}))[1], False)
        self.assertEqual(self.music.musicStates['10']['lastAction'], '⏭️ Skipped. · Chris')
        self.music.postCard.assert_awaited_once_with('10', self.msg.channel, moveDown = True)
        self.music.listenerProblem.return_value = 'Join 🔊 **Lounge** to control the music.'
        self.assertEqual(await self.use(agent_client.TOOL_CONTROL_MUSIC, {'action': 'skip'}), ('Join 🔊 **Lounge** to control the music. So nothing happened. Tell them that.', True))
        self.assertEqual(await self.use(agent_client.TOOL_CONTROL_MUSIC, {'action': 'explode'}), ('That is not something you can do to the music.', True))

    async def test_setting_a_reminder_for_the_sender(self):
        self.patch(reminders_cog, 'utcNow', MagicMock(return_value = NOW))
        saved = self.patch(self.reminders, 'saveReminder', AsyncMock(return_value = 'r1'))
        values = {'when': 'tomorrow 9am', 'what': 'dentist', 'repeat': 'daily', 'where': 'dm'}
        self.assertEqual(await self.use(agent_client.TOOL_SET_REMINDER, values), ('They haven\'t set a time zone. Ask where they are, use set_timezone, then set the reminder.', True))
        self.zone = 'America/New_York'
        self.assertEqual(await self.use(agent_client.TOOL_SET_REMINDER, values), ('Set for Tue, Nov 10 at 9:00 AM in their time, every day at 9:00 AM, by DM. Tell them when.', False))
        self.assertEqual(saved.await_args.args[1]['userId'], '1')
        self.assertEqual((await self.use(agent_client.TOOL_SET_REMINDER, dict(values, where = 'here', repeat = 'once')))[0], 'Set for Tue, Nov 10 at 9:00 AM in their time, once, here. Tell them when.')
        self.assertEqual(await self.use(agent_client.TOOL_SET_REMINDER, dict(values, when = 'soonish')), ('Nothing was set: I couldn\'t read "soonish" as a time. Try "in 2 hours", "tomorrow 9am", "Thursday 8pm" or "Dec 25 10:00".', True))
        for bad in (dict(values, what = ' '), dict(values, repeat = 'hourly'), dict(values, where = 'there'), dict(values, when = None)):
            with self.subTest(bad = bad):
                self.assertEqual(await self.use(agent_client.TOOL_SET_REMINDER, bad), ('A reminder needs when, what, repeat and where.', True))
        # chosen days come as their own list, and a "days" repeat needs some
        result = await self.use(agent_client.TOOL_SET_REMINDER, dict(values, repeat = 'days', days = ['wed', 'mon', 'noday']))
        self.assertEqual(result, ('Set for Wed, Nov 11 at 9:00 AM in their time, every Mon and Wed at 9:00 AM, by DM. Tell them when.', False))
        self.assertEqual(saved.await_args.args[1]['repeat'], 'days:0,2')
        self.assertEqual((await self.use(agent_client.TOOL_SET_REMINDER, dict(values, repeat = 'days', days = None)))[0], f'Nothing was set: {reminders_cog.REPEAT_PROBLEM}')
        self.assertEqual((await self.use(agent_client.TOOL_SET_REMINDER, dict(values, repeat = 'monthly')))[0], 'Set for Tue, Nov 10 at 9:00 AM in their time, every month on the 10th at 9:00 AM, by DM. Tell them when.')

    async def test_changing_one_of_the_senders_own_reminders(self):
        self.patch(reminders_cog, 'utcNow', MagicMock(return_value = NOW))
        stored = {'r1': {'userId': '1', 'channelId': '20', 'text': 'dentist', 'nextAt': '2026-11-10T14:00:00+00:00', 'repeat': 'daily', 'where': 'dm'},
                  'r2': {'userId': '2', 'text': 'sams'},
                  'r3': {'userId': '1', 'text': 'raid', 'nextAt': '2026-11-10T14:00:00+00:00', 'repeat': 'once', 'target': 'everyone'},
                  'r4': {'userId': '1', 'text': 'later', 'nextAt': '2026-11-10T14:00:00+00:00', 'repeat': 'once', 'snoozed': True},
                  'r5': {'userId': '1', 'text': 'sent', 'nextAt': '2026-11-09T14:00:00+00:00', 'repeat': 'once', 'delivered': '2026-11-09T14:00:00+00:00'}}
        self.patch(agent_abilities.reminders_queries, 'getServerReminders', MagicMock(side_effect = lambda serverId: dict(stored)))
        updated = self.patch(agent_abilities.reminders_queries, 'updateReminder', MagicMock(return_value = True))
        woken = self.patch(self.reminders, 'wakeFor', Mock())
        notTheirs = ("That is not one of the sender's reminder ids. Use get_reminders for their ids, then try again.", True)
        for reminderId in ('r2', 'r5', 'nope', None):
            with self.subTest(reminderId = reminderId):
                self.assertEqual(await self.use(agent_client.TOOL_EDIT_REMINDER, {'id': reminderId, 'when': '10am', 'what': ''}), notTheirs)
        for reminderId in ('r3', 'r4'):
            with self.subTest(reminderId = reminderId):
                self.assertEqual(await self.use(agent_client.TOOL_EDIT_REMINDER, {'id': reminderId, 'when': '10am', 'what': ''}), ("A role's or everyone's reminder, or a snooze, can't be changed here. They can delete it and set it again.", True))
        self.assertEqual(await self.use(agent_client.TOOL_EDIT_REMINDER, {'id': 'r1', 'when': ' ', 'what': None}), ('Say what to change: when, what, or both.', True))
        self.assertEqual(await self.use(agent_client.TOOL_EDIT_REMINDER, {'id': 'r1', 'when': '10am', 'what': ''}), ("They haven't set a time zone. Ask where they are, use set_timezone, then try again.", True))
        self.zone = 'America/New_York'
        # a new time keeps its words, its repeat and where it goes
        self.assertEqual(await self.use(agent_client.TOOL_EDIT_REMINDER, {'id': 'r1', 'when': 'tomorrow 10am', 'what': ''}), ('Changed. It is now for Tue, Nov 10 at 10:00 AM in their time, every day at 10:00 AM. Tell them.', False))
        updated.assert_called_with(10, 'r1', {'nextAt': '2026-11-10T15:00:00+00:00', 'repeat': 'daily', 'text': 'dentist', 'timer': None})
        woken.assert_called_with(self.guild, 'r1', '2026-11-10T15:00:00+00:00')
        # new words keep its time
        self.assertEqual(await self.use(agent_client.TOOL_EDIT_REMINDER, {'id': 'r1', 'when': '', 'what': ' the dentist '}), ('Changed. It is now for Tue, Nov 10 at 9:00 AM in their time, every day at 9:00 AM. Tell them.', False))
        updated.assert_called_with(10, 'r1', {'text': 'the dentist'})
        # both, with a timer kept as one
        await self.use(agent_client.TOOL_EDIT_REMINDER, {'id': 'r1', 'when': 'in 2 hours', 'what': 'call'})
        self.assertEqual((updated.call_args.args[2]['text'], updated.call_args.args[2]['timer']), ('call', True))
        self.assertEqual((await self.use(agent_client.TOOL_EDIT_REMINDER, {'id': 'r1', 'when': 'soonish', 'what': ''}))[0], 'Nothing was changed: I couldn\'t read "soonish" as a time. Try "in 2 hours", "tomorrow 9am", "Thursday 8pm" or "Dec 25 10:00".')
        self.assertEqual(await self.use(agent_client.TOOL_EDIT_REMINDER, {'id': 'r1', 'when': '', 'what': 'x' * (self.reminders.MAX_TEXT + 1)}), (f'Nothing was changed: a reminder can be at most {self.reminders.MAX_TEXT} characters.', True))
        # deleted a moment before
        updated.return_value = False
        self.assertEqual(await self.use(agent_client.TOOL_EDIT_REMINDER, {'id': 'r1', 'when': '', 'what': 'x'}), ('That reminder is gone already.', True))

    async def test_looking_up_the_senders_open_trades(self):
        gtrade = agent_abilities.gtrade_cog.GTrade(Mock())
        self.client.get_cog = Mock(side_effect = lambda name: {'GTrade': gtrade}[name])
        pending = self.patch(agent_abilities.gtrade_queries, 'getAllServerPendingTradeTransactions', MagicMock(return_value = None))
        self.assertEqual(await self.use(agent_client.TOOL_GET_TRADES, {}), ('They have no open trades here.', False))
        pending.return_value = {'t1': {'trxType': 'market', 'sellerId': '1', 'item': {'name': 'Cup', 'value': '1'}},
                                't2': {'trxType': 'sell', 'sellerId': '2', 'buyerId': '1', 'item': {'name': 'Gem', 'value': '4'}},
                                't3': {'trxType': 'market', 'sellerId': '2', 'item': {'name': 'Not theirs', 'value': '9'}}}
        self.assertEqual(await self.use(agent_client.TOOL_GET_TRADES, {}), ('Their open trades, as they read them (⬅️ waits on them, ➡️ is their own request, 🏷️ is their listing):\n⬅️ Sam wants to sell you Gem · 4.00 GCoin\n🏷️ Cup is on the market · 1.00 GCoin', False))

    async def test_a_reminder_for_the_minute_it_is_goes_off_now(self):
        self.patch(reminders_cog, 'utcNow', MagicMock(return_value = NOW.replace(second = 40)))
        self.patch(self.reminders, 'saveReminder', AsyncMock(return_value = 'r1'))
        self.zone = 'UTC'
        clock = NOW.strftime('%H:%M')
        self.assertEqual(await self.use(agent_client.TOOL_SET_REMINDER, {'when': clock, 'what': 'clean', 'repeat': 'once', 'days': [], 'where': 'here'}),
                         ('Set for now, the minute they named, so it goes off right away, here. Tell them.', False))

    def test_the_tools_repeats_are_the_reminders_own(self):
        self.assertEqual(agent_client.REPEAT_CHOICES, list(when.REPEATS))

    async def test_deleting_only_the_senders_own_after_a_confirm(self):
        self.msg.reply = AsyncMock(return_value = Mock())
        stored = {'r1': {'userId': '1', 'text': 'dentist', 'nextAt': '2026-11-10T14:00:00+00:00', 'repeat': 'once'}, 'r2': {'userId': '2', 'text': 'sams'},
                  'r3': {'userId': '1', 'text': 'gym', 'nextAt': '2026-11-11T23:00:00+00:00', 'repeat': 'once'}}
        self.patch(agent_abilities.reminders_queries, 'getServerReminders', MagicMock(side_effect = lambda serverId: dict(stored)))
        removed = self.patch(agent_abilities.reminders_queries, 'removeReminder', MagicMock(side_effect = lambda serverId, reminderId: stored.pop(reminderId)))
        self.patch(agent_abilities.predicates, 'recheck', AsyncMock())
        self.zone = 'America/New_York'
        self.assertEqual(await self.use(agent_client.TOOL_DELETE_REMINDER, {'ids': ['r1']}), (agent_abilities.CONFIRM_POSTED, False))
        embed, view = self.posted()
        # its time only, as what it says is private
        self.assertEqual(embed.title, '🗑️ Delete your reminder for Tue, Nov 10 at 9:00 AM?')
        self.assertNotIn('dentist', embed.title + embed.description)
        removed.assert_not_called()
        interaction = self.press()
        await view.confirmed(interaction)
        removed.assert_called_once_with(10, 'r1')
        self.assertEqual(interaction.edit_original_message.await_args.kwargs['content'], '🗑️ Deleted your reminder for Tue, Nov 10 at 9:00 AM.')
        # gone by the press
        stored['r1'] = {'userId': '1', 'text': 'dentist', 'nextAt': '2026-11-10T14:00:00+00:00', 'repeat': 'once'}
        await self.use(agent_client.TOOL_DELETE_REMINDER, {'ids': ['r1']})
        embed, view = self.posted()
        del stored['r1']
        interaction = self.press()
        await view.confirmed(interaction)
        self.assertEqual(interaction.edit_original_message.await_args.kwargs['content'], '❌ That reminder is gone already.')
        removed.assert_called_once()
        for ids in (['r2'], ['r9'], [''], [None], None, 'r3'):
            with self.subTest(ids = ids):
                self.assertEqual(await self.use(agent_client.TOOL_DELETE_REMINDER, {'ids': ids}, isAdmin = True), ("None of those are the sender's reminder ids. Use get_reminders for their ids, then try again.", True))

    async def test_deleting_several_under_one_confirm(self):
        # "delete all my reminders": one card listing their times, and only the sender's
        self.msg.reply = AsyncMock(return_value = Mock())
        stored = {f'r{number}': {'userId': '1', 'text': 'secret', 'nextAt': f'2026-11-1{number}T14:00:00+00:00', 'repeat': 'once'} for number in range(1, 5)}
        stored['r9'] = {'userId': '2', 'text': 'sams'}
        # sent already, and kept a day only so it can be snoozed: not one of "all my reminders"
        stored['r8'] = {'userId': '1', 'text': 'sent', 'nextAt': '2026-11-09T14:00:00+00:00', 'repeat': 'once', 'delivered': '2026-11-09T14:00:00+00:00'}
        self.patch(agent_abilities.reminders_queries, 'getServerReminders', MagicMock(side_effect = lambda serverId: dict(stored)))
        removed = self.patch(agent_abilities.reminders_queries, 'removeReminder', MagicMock(side_effect = lambda serverId, reminderId: stored.pop(reminderId)))
        self.patch(agent_abilities.predicates, 'recheck', AsyncMock())
        self.zone = 'America/New_York'
        actions = []
        self.assertEqual(await self.use(agent_client.TOOL_DELETE_REMINDER, {'ids': ['r1', 'r2', 'r3', 'r4', 'r9', 'r1']}, actions = actions), (agent_abilities.CONFIRM_POSTED, False))
        self.assertEqual(actions, ['delete_reminder'])
        embed, view = self.posted()
        self.assertEqual(embed.title, '🗑️ Delete your 4 reminders?')
        self.assertEqual(embed.description, "• Wed, Nov 11 at 9:00 AM\n• Thu, Nov 12 at 9:00 AM\n• Fri, Nov 13 at 9:00 AM\n• Sat, Nov 14 at 9:00 AM\n\nThey can't be undone.")
        self.assertNotIn('secret', embed.description)
        # an empty list is all of theirs, and nobody else's, with no lookup first
        await self.use(agent_client.TOOL_DELETE_REMINDER, {'ids': []})
        self.assertEqual(self.posted()[0].title, '🗑️ Delete your 4 reminders?')
        # one deleted elsewhere meanwhile
        del stored['r4']
        interaction = self.press()
        await view.confirmed(interaction)
        self.assertEqual(interaction.edit_original_message.await_args.kwargs['content'], '🗑️ Deleted your 3 reminders. The rest were gone already.')
        self.assertEqual(list(stored), ['r9', 'r8'])
        for reminderId in ('r1', 'r2', 'r3', 'r4'):
            stored[reminderId] = {'userId': '1', 'nextAt': '2026-11-11T14:00:00+00:00', 'repeat': 'once'}
        await self.use(agent_client.TOOL_DELETE_REMINDER, {'ids': ['r1', 'r2', 'r3', 'r4']})
        embed, view = self.posted()
        stored.clear()
        interaction = self.press()
        await view.confirmed(interaction)
        self.assertEqual(interaction.edit_original_message.await_args.kwargs['content'], '❌ Those reminders are gone already.')
        stored.update({'r1': {'userId': '1', 'nextAt': '2026-11-11T14:00:00+00:00', 'repeat': 'once'}, 'r2': {'userId': '1', 'nextAt': '2026-11-12T14:00:00+00:00', 'repeat': 'once'}})
        await self.use(agent_client.TOOL_DELETE_REMINDER, {'ids': ['r1', 'r2']})
        embed, view = self.posted()
        interaction = self.press()
        await view.confirmed(interaction)
        self.assertEqual(interaction.edit_original_message.await_args.kwargs['content'], '🗑️ Deleted your 2 reminders.')

    # all

    def press(self, user = None):
        interaction = Mock(spec = nextcord.Interaction)
        interaction.user = user or self.sender
        interaction.guild = self.guild
        interaction.response = Mock(defer = AsyncMock(), edit_message = AsyncMock(), is_done = Mock(return_value = False))
        interaction.edit_original_message = AsyncMock()
        return interaction

    def posted(self):
        kwargs = self.msg.reply.await_args.kwargs
        return kwargs['embed'], kwargs['view']

    def setUpAll(self):
        self.msg.reply = AsyncMock(return_value = Mock())
        self.recheck = self.patch(agent_abilities.predicates, 'recheck', AsyncMock())

    async def test_sending_gcoin_posts_gcoins_own_confirm(self):
        self.setUpAll()
        gcoin = Mock(receiverProblem = Mock(return_value = None), checkSend = AsyncMock(return_value = (None, Decimal('5'), Decimal('120'))))
        self.client.get_cog = Mock(side_effect = lambda name: {'GCoin': gcoin}[name])
        self.assertEqual(await self.use(agent_client.TOOL_SEND_GCOIN, {'user': 'sam', 'amount': '5', 'note': ' lunch '}), (agent_abilities.CONFIRM_POSTED, False))
        embed, view = self.posted()
        self.assertEqual(embed.title, '💸 Send 5.00 GCoin to Sam?')
        self.assertIn("You'll have **120.00 GCoin** left.\n> lunch", embed.description)
        self.assertIsInstance(view, agent_abilities.AgentSendFlow)
        self.assertEqual((view.ownerId, view.receiver), (1, self.sam))
        self.assertIs(view.message, self.msg.reply.return_value)
        self.assertEqual(self.msg.reply.await_args.kwargs['allowed_mentions'].users, False)

    async def test_a_posted_card_is_collected_for_the_agents_words(self):
        self.setUpAll()
        self.client.get_cog = Mock(return_value = Mock())
        self.toggles['toggle_storms'] = False
        cards = []
        await self.abilities.run(agent_client.TOOL_SET_FEATURE, {'features': ['Storms'], 'setting': 'on'}, self.msg, True, [], cards)
        self.assertEqual(cards, [self.msg.reply.return_value])

    async def test_sending_gcoin_refusals(self):
        self.setUpAll()
        gcoin = Mock(receiverProblem = Mock(return_value = None), checkSend = AsyncMock(return_value = ('You do not have enough GCoin.', None, None)))
        self.client.get_cog = Mock(side_effect = lambda name: {'GCoin': gcoin}[name])
        self.assertEqual(await self.use(agent_client.TOOL_SEND_GCOIN, {'user': 'sam', 'amount': '999', 'note': None}), ('Nothing was sent: You do not have enough GCoin.', True))
        gcoin.receiverProblem.return_value = 'They are not in this server.'
        self.assertEqual((await self.use(agent_client.TOOL_SEND_GCOIN, {'user': 'sam', 'amount': 5, 'note': ''}))[0], 'Nothing was sent: They are not in this server.')
        self.assertEqual(await self.use(agent_client.TOOL_SEND_GCOIN, {'user': '', 'amount': '5', 'note': ''}), ("They can't send GCoin to themselves.", True))
        self.assertEqual(await self.use(agent_client.TOOL_SEND_GCOIN, {'user': 'nobody', 'amount': '5', 'note': ''}), (agent_abilities.NOBODY, True))
        self.msg.reply.assert_not_awaited()

    async def test_the_confirm_card(self):
        self.setUpAll()
        action = AsyncMock(return_value = '✅ It happened.')
        view = agent_abilities.AgentConfirm(1, 'toggle_x', True, action)
        self.assertEqual([item.label for item in view.children], ['Confirm', 'Cancel'])
        # a failing recheck leaves it to press again
        self.recheck.side_effect = RuntimeError('turned off')
        with self.assertRaises(RuntimeError):
            await view.confirmed(self.press())
        action.assert_not_awaited()
        self.recheck.side_effect = None
        pressed = self.press()
        await view.confirmed(pressed)
        self.recheck.assert_awaited_with(pressed, feature = 'toggle_x', admin = True)
        action.assert_awaited_once_with(pressed)
        pressed.edit_original_message.assert_awaited_once_with(content = '✅ It happened.', embed = None, view = None)
        # a second press does nothing
        await view.confirmed(self.press())
        action.assert_awaited_once()
        cancel = agent_abilities.AgentConfirm(1, None, False, action)
        cancelled = self.press()
        await cancel.cancelled(cancelled)
        cancelled.response.edit_message.assert_awaited_once_with(content = '🚫 Cancelled, so nothing happened.', embed = None, view = None)

    async def test_buying_an_item(self):
        self.setUpAll()
        gtrade = Mock(tradeLock = asyncio.Lock())
        async def buy(reply, author, item, owner):
            self.assertEqual((author, item, owner), (self.sender, 'Hat', self.sam))
            await reply.send('🛒 Bought.')
        gtrade.buyUnderLock = buy
        self.patch(agent_abilities.gtrade_queries, 'getPendingTradeTransaction', MagicMock(return_value = None))
        self.client.get_cog = Mock(side_effect = lambda name: {'GTrade': gtrade}[name])
        self.patch(agent_abilities.gtrade_queries, 'getAllUserItems', MagicMock(side_effect = lambda userId: {'i': {'name': 'Hat', 'value': '7'}} if userId == 2 else None))
        self.patch(agent_abilities.gcoin_queries, 'getUserBalance', MagicMock(return_value = Decimal('10')))
        # names are matched without caring about case, and GTrade gets the item's own
        self.assertEqual(await self.use(agent_client.TOOL_BUY_ITEM, {'item': ' hat ', 'owner': 'sam', 'action': 'buy'}), (agent_abilities.CONFIRM_POSTED, False))
        embed, view = self.posted()
        self.assertEqual(embed.title, '🛒 Buy Hat from Sam for 7.00 GCoin?')
        self.assertTrue(embed.description.startswith("You'll have **3.00 GCoin** left"))
        pressed = self.press()
        await view.confirmed(pressed)
        self.assertEqual(pressed.edit_original_message.await_args.kwargs['content'], '🛒 Bought.')
        self.assertEqual(await self.use(agent_client.TOOL_BUY_ITEM, {'item': 'Sword', 'owner': 'sam', 'action': 'buy'}), ('Sam has no item called that. Their items: Hat.', True))
        self.assertEqual(await self.use(agent_client.TOOL_BUY_ITEM, {'item': None, 'owner': 'sam', 'action': 'buy'}), ('Sam has no item called that. Their items: Hat.', True))
        self.assertEqual(await self.use(agent_client.TOOL_BUY_ITEM, {'item': ' ', 'owner': 'sam', 'action': 'buy'}), ('Sam has no item called that. Their items: Hat.', True))
        self.assertEqual(await self.use(agent_client.TOOL_BUY_ITEM, {'item': 'Hat', 'owner': '', 'action': 'buy'}), ('They already own it.', True))
        self.assertEqual(await self.use(agent_client.TOOL_BUY_ITEM, {'item': 'Hat', 'owner': 'nobody', 'action': 'buy'}), (agent_abilities.NOBODY, True))

    async def test_selling_an_item(self):
        self.setUpAll()
        gtrade = Mock(sellUnderLock = AsyncMock(), tradeLock = asyncio.Lock(), announceGathered = AsyncMock(), gather = Mock(side_effect = agent_abilities.gtrade_cog.Gathered))
        self.client.get_cog = Mock(side_effect = lambda name: {'GTrade': gtrade}[name])
        self.patch(agent_abilities.gtrade_queries, 'getAllUserItems', MagicMock(side_effect = lambda userId: {'i': {'name': 'Hat', 'value': '7'}} if userId == 1 else None))
        opened = {}
        self.patch(agent_abilities.gtrade_queries, 'getAllServerPendingTradeTransactions', MagicMock(side_effect = lambda guildId: dict(opened) or None))
        await self.use(agent_client.TOOL_SELL_ITEM, {'items': ['HAT'], 'buyer': '', 'action': 'sell'})
        self.assertEqual(self.posted()[0].title, '🏷️ Put Hat up for sale for 7.00 GCoin?')
        # theirs on the market, beside someone else's listing of the same name and their own offer of another
        opened.update({'t': {'trxType': 'market', 'sellerId': '1', 'item': {'name': 'Hat'}},
                       'u': {'trxType': 'market', 'sellerId': '2', 'item': {'name': 'Hat'}},
                       'v': {'trxType': 'sell', 'sellerId': '1', 'buyerId': '3', 'item': {'name': 'Hat'}}})
        await self.use(agent_client.TOOL_SELL_ITEM, {'items': ['Hat'], 'buyer': None, 'action': 'stop'})
        self.assertEqual(self.posted()[0].title, '🚫 Take Hat off the market?')
        # one already up is left alone rather than taken down
        self.assertEqual(await self.use(agent_client.TOOL_SELL_ITEM, {'items': ['Hat'], 'buyer': '', 'action': 'sell'}), ('Hat is already for sale.', True))
        # on the market, and offered to someone else, isn't offered to Sam
        self.assertEqual(await self.use(agent_client.TOOL_SELL_ITEM, {'items': ['Hat'], 'buyer': 'sam', 'action': 'stop'}), ('Hat is not offered to Sam.', True))
        opened.clear()
        await self.use(agent_client.TOOL_SELL_ITEM, {'items': ['Hat'], 'buyer': 'sam', 'action': 'sell'})
        embed, view = self.posted()
        self.assertEqual(embed.title, '🤝 Offer Hat to Sam for 7.00 GCoin?')
        self.assertEqual(embed.description, 'Its value sets the price.')
        pressed = self.press()
        await view.confirmed(pressed)
        self.assertEqual(gtrade.sellUnderLock.await_args.args[1:], (self.sender, 'Hat', self.sam))
        self.assertEqual(pressed.edit_original_message.await_args.kwargs['content'], '✅ Done.')
        self.assertEqual(await self.use(agent_client.TOOL_SELL_ITEM, {'items': ['Hat'], 'buyer': 'chris', 'action': 'sell'}), ("They can't sell to themselves.", True))
        self.assertEqual(await self.use(agent_client.TOOL_SELL_ITEM, {'items': ['Hat'], 'buyer': 'nobody', 'action': 'sell'}), (agent_abilities.NOBODY, True))
        self.assertEqual(await self.use(agent_client.TOOL_SELL_ITEM, {'items': ['Sword'], 'buyer': '', 'action': 'sell'}), ('Chris has no item called that. Their items: Hat.', True))
        self.assertEqual(await self.use(agent_client.TOOL_SELL_ITEM, {'items': 'Hat', 'buyer': '', 'action': 'sell'}), ('Chris has no item called that. Their items: Hat.', True))
        self.assertEqual(await self.use(agent_client.TOOL_SELL_ITEM, {'items': ['Hat'], 'buyer': '', 'action': 'maybe'}), ('Say whether to sell them or stop selling them.', True))

    def test_a_long_list_is_cut_at_a_line_and_says_how_many_more(self):
        self.assertEqual(agent_abilities.presentation.fitLines('short', 2000), 'short')
        cut = agent_abilities.presentation.fitLines('\n'.join(f'line {number}' for number in range(1000)), 2000)
        self.assertLessEqual(len(cut), 2000)
        kept = cut.split('\n')
        self.assertEqual(kept[-1], f'…and {1000 - (len(kept) - 1)} more.')
        self.assertEqual(kept[-2], f'line {len(kept) - 2}')
        # one line longer than everything allowed is cut where it is
        self.assertEqual(agent_abilities.presentation.fitLines('x' * 3000, 2000), 'x' * 1960 + '\n…and 1 more.')
        # a note added to one already cut is kept, and the count stays what it was plus what goes now
        again = agent_abilities.presentation.fitLines(cut, 2000, '\n-# 🚫 taken down')
        self.assertLessEqual(len(again), 2000)
        self.assertTrue(again.endswith('more.\n-# 🚫 taken down'))
        keptAgain = again.split('\n')
        self.assertEqual(keptAgain[-2], f'…and {1000 - (len(keptAgain) - 2)} more.')
        self.assertEqual(agent_abilities.presentation.fitLines('short', 2000, ' and its note'), 'short and its note')

    async def test_selling_all_items_lists_them_on_one_card_and_leaves_those_already_up(self):
        self.setUpAll()
        gtrade = Mock(tradeLock = asyncio.Lock(), announceGathered = AsyncMock(), gather = Mock(side_effect = agent_abilities.gtrade_cog.Gathered))
        async def sell(reply, author, name, buyer):
            if name == 'Cup':
                await reply.send(f"🚫 {name} is no longer for sale.")
        gtrade.sellUnderLock = AsyncMock(side_effect = sell)
        self.client.get_cog = Mock(side_effect = lambda name: {'GTrade': gtrade}[name])
        owned = {'a': {'name': 'Hat', 'value': '7'}, 'b': {'name': 'Cup', 'value': '2.5'}, 'c': {'name': 'Bow', 'value': '1'}}
        self.patch(agent_abilities.gtrade_queries, 'getAllUserItems', MagicMock(return_value = owned))
        up = {'Bow'}
        kind = ['market']
        table = self.patch(agent_abilities.gtrade_queries, 'getAllServerPendingTradeTransactions', MagicMock(side_effect = lambda guildId: {name: {'trxType': kind[0], 'sellerId': '1', 'buyerId': '2', 'item': {'name': name}} for name in up}))
        self.assertEqual(await self.use(agent_client.TOOL_SELL_ITEM, {'items': ['Hat', 'Cup', 'Bow'], 'buyer': '', 'action': 'sell'}), (agent_abilities.CONFIRM_POSTED, False))
        embed, view = self.posted()
        self.assertEqual(embed.title, '🏷️ Put 2 items up for sale?')
        # an empty list is all of theirs
        await self.use(agent_client.TOOL_SELL_ITEM, {'items': [], 'buyer': '', 'action': 'stop'})
        self.assertEqual(self.posted()[0].title, '🚫 Take Bow off the market?')
        await self.use(agent_client.TOOL_SELL_ITEM, {'items': [], 'buyer': '', 'action': 'sell'})
        embed, view = self.posted()
        self.assertEqual(embed.title, '🏷️ Put 2 items up for sale?')
        self.assertEqual(embed.description, "• Hat · 7.00 GCoin\n• Cup · 2.50 GCoin\n\nBow is already for sale, so it stays as it is.\n\nEach one's value sets its price.")
        # what is open is read once for them all, not once for each
        table.reset_mock()
        await self.use(agent_client.TOOL_SELL_ITEM, {'items': ['Hat', 'Cup', 'Bow'], 'buyer': '', 'action': 'sell'})
        table.assert_called_once()
        embed, view = self.posted()
        # by the press, Hat went up some other way, so only Cup is sold
        up.add('Hat')
        pressed = self.press()
        await view.confirmed(pressed)
        self.assertEqual([call.args[2] for call in gtrade.sellUnderLock.await_args_list], ['Cup'])
        # what they'd each have posted is gathered, and said in one message once the lock is free
        gathered, seller, buyer = gtrade.announceGathered.await_args.args
        # made by the cog, whose own copy of the module is the one that has to recognise it
        gtrade.gather.assert_called_once()
        self.assertEqual((seller, buyer), (self.sender, None))
        self.assertFalse(gtrade.tradeLock.locked())
        # what happened is said once for each kind, rather than GTrade's own line for every item
        self.assertEqual(pressed.edit_original_message.await_args.kwargs['content'], 'Left as they are: already for sale. (Hat)\n🏷️ Up for sale. (Cup)')
        # taking them all off, with two already off
        up.clear()
        up.add('Hat')
        self.assertEqual(await self.use(agent_client.TOOL_SELL_ITEM, {'items': ['Hat', 'Cup', 'Bow'], 'buyer': '', 'action': 'stop'}), (agent_abilities.CONFIRM_POSTED, False))
        self.assertEqual(self.posted()[0].title, '🚫 Take Hat off the market?')
        self.assertEqual(self.posted()[0].description, 'Cup and Bow are not for sale, so they stay as they are.')
        up.update({'Cup', 'Bow'})
        await self.use(agent_client.TOOL_SELL_ITEM, {'items': ['Hat', 'Cup', 'Bow'], 'buyer': '', 'action': 'stop'})
        self.assertEqual(self.posted()[0].title, '🚫 Take 3 items off the market?')
        self.assertEqual(self.posted()[0].description, '• Hat · 7.00 GCoin\n• Cup · 2.50 GCoin\n• Bow · 1.00 GCoin')
        up.clear()
        kind[0] = 'sell'
        await self.use(agent_client.TOOL_SELL_ITEM, {'items': ['Hat', 'Cup'], 'buyer': 'sam', 'action': 'sell'})
        self.assertEqual(self.posted()[0].title, '🤝 Offer 2 items to Sam?')
        up.update({'Hat', 'Cup'})
        await self.use(agent_client.TOOL_SELL_ITEM, {'items': ['Hat', 'Cup'], 'buyer': 'sam', 'action': 'stop'})
        self.assertEqual(self.posted()[0].title, '🚫 Stop offering 2 items to Sam?')
        await self.use(agent_client.TOOL_SELL_ITEM, {'items': ['Hat'], 'buyer': 'sam', 'action': 'stop'})
        self.assertEqual(self.posted()[0].title, '🚫 Stop offering Hat to Sam?')
        self.assertEqual(self.posted()[0].description, 'It can be put up again any time.')
        kind[0] = 'market'
        self.assertEqual(await self.use(agent_client.TOOL_SELL_ITEM, {'items': ['Hat', 'Cup'], 'buyer': '', 'action': 'sell'}), ('Hat and Cup are already for sale.', True))

    async def test_many_sold_or_taken_down_are_summed_up_rather_than_a_line_each(self):
        # nineteen offers cancelled was nineteen lines of "you are no longer requesting to sell"
        self.setUpAll()
        gtrade = Mock(tradeLock = asyncio.Lock(), announceGathered = AsyncMock(), gather = Mock(side_effect = agent_abilities.gtrade_cog.Gathered))
        async def sell(reply, author, name, buyer):
            if name == 'Bow':
                await reply.send(embed = Mock(description = 'Sorry, Sam already has an item with this name.'))
            elif name == 'Cup' and selling[0]:
                # Sam had asked to buy it, so offering it sold it
                reply.announced.append('🎉 sold')
            else:
                await reply.send(f"🚫 you are no longer requesting to sell '{name}'.")
        gtrade.sellUnderLock = AsyncMock(side_effect = sell)
        self.client.get_cog = Mock(side_effect = lambda name: {'GTrade': gtrade}[name])
        owned = {key: {'name': name, 'value': '1'} for key, name in (('a', 'Hat'), ('b', 'Cup'), ('c', 'Bow'), ('d', 'Axe'))}
        self.patch(agent_abilities.gtrade_queries, 'getAllUserItems', MagicMock(return_value = owned))
        up = set()
        self.patch(agent_abilities.gtrade_queries, 'getAllServerPendingTradeTransactions', MagicMock(side_effect = lambda guildId: {name: {'trxType': 'sell', 'sellerId': '1', 'buyerId': '2', 'item': {'name': name}} for name in up}))
        selling = [True]
        await self.use(agent_client.TOOL_SELL_ITEM, {'items': [], 'buyer': 'sam', 'action': 'sell'})
        pressed = self.press()
        await self.posted()[1].confirmed(pressed)
        self.assertEqual(pressed.edit_original_message.await_args.kwargs['content'], '🤝 Offered to Sam.\n• Hat\n• Axe\n🎉 Sold to Sam. (Cup)\n❌ Sorry, Sam already has an item with this name. (Bow)')
        selling[0] = False
        up.update({'Hat', 'Cup', 'Axe'})
        await self.use(agent_client.TOOL_SELL_ITEM, {'items': [], 'buyer': 'sam', 'action': 'stop'})
        pressed = self.press()
        await self.posted()[1].confirmed(pressed)
        self.assertEqual(pressed.edit_original_message.await_args.kwargs['content'], '🚫 No longer offered to Sam.\n• Hat\n• Cup\n• Axe')
        # and off the market
        self.patch(agent_abilities.gtrade_queries, 'getAllServerPendingTradeTransactions', MagicMock(side_effect = lambda guildId: {name: {'trxType': 'market', 'sellerId': '1', 'item': {'name': name}} for name in up}))
        await self.use(agent_client.TOOL_SELL_ITEM, {'items': ['Hat', 'Cup'], 'buyer': '', 'action': 'stop'})
        pressed = self.press()
        await self.posted()[1].confirmed(pressed)
        self.assertEqual(pressed.edit_original_message.await_args.kwargs['content'], '🚫 No longer for sale.\n• Hat\n• Cup')

    async def test_all_my_items_takes_them_as_they_are_even_two_names_apart_only_by_case(self):
        self.setUpAll()
        gtrade = Mock(tradeLock = asyncio.Lock(), announceGathered = AsyncMock(), gather = Mock(side_effect = agent_abilities.gtrade_cog.Gathered), sellUnderLock = AsyncMock())
        self.client.get_cog = Mock(side_effect = lambda name: {'GTrade': gtrade}[name])
        owned = self.patch(agent_abilities.gtrade_queries, 'getAllUserItems', MagicMock(return_value = {'a': {'name': 'Sword', 'value': '7'}, 'b': {'name': 'sword', 'value': '2'}}))
        self.patch(agent_abilities.gtrade_queries, 'getAllServerPendingTradeTransactions', MagicMock(return_value = None))
        # named, the two can't be told apart
        self.assertEqual((await self.use(agent_client.TOOL_SELL_ITEM, {'items': ['SWORD'], 'buyer': '', 'action': 'sell'}))[1], True)
        owned.reset_mock()
        await self.use(agent_client.TOOL_SELL_ITEM, {'items': [], 'buyer': '', 'action': 'sell'})
        self.assertEqual(self.posted()[0].description, "• Sword · 7.00 GCoin\n• sword · 2.00 GCoin\n\nEach one's value sets its price.")
        # and read once, not once for each
        owned.assert_called_once()

    async def test_a_long_confirm_keeps_its_warning_when_its_list_is_cut(self):
        view = agent_abilities.AgentConfirm(1, None, False, AsyncMock(), '💥 Destroy 300 items for good?', '\n'.join(f'• Item {number} · 1.00 GCoin' for number in range(300)) + "\n\nEach pays back its worth. This can't be undone.")
        description = view.embed().description
        self.assertLessEqual(len(description), 4096)
        self.assertTrue(description.endswith("more.\n\nEach pays back its worth. This can't be undone."))
        # only the items are counted, not the blank line and the warning
        shown = description.count('• Item')
        self.assertIn(f'…and {300 - shown} more.', description)
        # one with no list is as it was written
        self.assertEqual(agent_abilities.AgentConfirm(1, None, False, AsyncMock(), 'T', 'One line.').embed().description, 'One line.')
        self.assertIsNone(agent_abilities.AgentConfirm(1, None, False, AsyncMock(), 'T', None).embed().description or None)

    async def test_switching_a_feature_is_for_admins_through_configs_own_switch(self):
        self.setUpAll()
        config = Mock(toggleFeature = AsyncMock(return_value = '🌧️ **Storms** is now on.'))
        self.client.get_cog = Mock(side_effect = lambda name: {'Config': config}[name])
        self.toggles['toggle_storms'] = False
        # refused before it's counted, as every admin tool is
        actions = []
        self.assertEqual(await self.use(agent_client.TOOL_SET_FEATURE, {'features': ['Storms'], 'setting': 'on'}, actions = actions), ('Only admins can do that.', True))
        self.assertEqual(actions, [])
        self.assertEqual(await self.use(agent_client.TOOL_SET_FEATURE, {'features': ['Agent'], 'setting': 'off'}, isAdmin = True), ('That is not a feature the agent can switch.', True))
        self.assertEqual(await self.use(agent_client.TOOL_SET_FEATURE, {'features': ['Storms'], 'setting': 'maybe'}, isAdmin = True), ('That is not a feature the agent can switch.', True))
        self.assertEqual(await self.use(agent_client.TOOL_SET_FEATURE, {'features': ['Storms'], 'setting': 'off'}, isAdmin = True), ('Storms is already off.', True))
        self.assertEqual(await self.use(agent_client.TOOL_SET_FEATURE, {'features': ['Storms'], 'setting': 'on'}, isAdmin = True), (agent_abilities.CONFIRM_POSTED, False))
        embed, view = self.posted()
        self.assertEqual(embed.title, '🌧️ Turn on Storms?')
        pressed = self.press()
        await view.confirmed(pressed)
        self.recheck.assert_awaited_with(pressed, feature = None, admin = True)
        config.toggleFeature.assert_awaited_once_with(pressed, 'toggle_storms')
        self.assertEqual(pressed.edit_original_message.await_args.kwargs['content'], '🌧️ **Storms** is now on.')
        # someone turned it on meanwhile: pressing doesn't turn it back off
        await self.use(agent_client.TOOL_SET_FEATURE, {'features': ['Storms'], 'setting': 'on'}, isAdmin = True)
        self.toggles['toggle_storms'] = True
        late = self.press()
        await self.posted()[1].confirmed(late)
        config.toggleFeature.assert_awaited_once()
        self.assertEqual(late.edit_original_message.await_args.kwargs['content'], 'Storms is already on.')

    async def test_the_sent_card_becomes_the_announcement(self):
        self.setUpAll()
        gcoin = Mock(transfer = AsyncMock())
        async def transfer(channel, author, receiver, amount, note):
            await channel.send('💸 <@1> sent <@2> **5.00 GCoin**.')
        gcoin.transfer.side_effect = transfer
        flow = agent_abilities.AgentSendFlow(gcoin, self.guild, self.sender)
        flow.receiver, flow.amount, flow.note = self.sam, Decimal('5'), ''
        pressed = self.press()
        pressed.channel = Mock(id = 20)
        await flow.confirmed(pressed)
        pressed.edit_original_message.assert_awaited_once_with(content = '💸 <@1> sent <@2> **5.00 GCoin**.', embed = None, view = None)
        self.assertEqual(gcoin.transfer.await_args.args[0].id, 20)
        # a double click sends once
        await flow.confirmed(self.press())
        gcoin.transfer.assert_awaited_once()
        failing = agent_abilities.AgentSendFlow(Mock(transfer = AsyncMock(return_value = 'You do not have enough GCoin.')), self.guild, self.sender)
        failing.receiver, failing.amount, failing.note = self.sam, Decimal('5'), ''
        pressed = self.press()
        pressed.channel = Mock(id = 20)
        await failing.confirmed(pressed)
        pressed.edit_original_message.assert_awaited_once_with(content = '❌ You do not have enough GCoin.', embed = None, view = None)

    async def test_showing_an_item_is_its_card(self):
        self.setUpAll()
        gtrade = agent_abilities.gtrade_cog.GTrade(Mock())
        gtrade.itemEmbed = Mock(return_value = 'the item card')
        self.client.get_cog = Mock(return_value = gtrade)
        self.patch(agent_abilities.gtrade_queries, 'getAllUserItems', MagicMock(side_effect = lambda userId: {'i': {'name': 'Hat'}} if userId == 2 else None))
        cards = []
        self.assertEqual(await self.abilities.run(agent_client.TOOL_SHOW_ITEM, {'item': 'Hat', 'owner': 'sam'}, self.msg, False, [], cards), (agent_abilities.SHOWN, False))
        gtrade.itemEmbed.assert_called_once_with(self.sam, {'name': 'Hat'})
        self.assertEqual(self.msg.reply.await_args.kwargs['embed'], 'the item card')
        # GTrade's own Show, so it carries the ✖️ for whoever asked and whose it is
        self.assertEqual([button.custom_id for button in self.msg.reply.await_args.kwargs['view'].children], ['gtrade:closeitem:1-2'])
        self.assertEqual(cards, [self.msg.reply.return_value])
        self.assertEqual(await self.use(agent_client.TOOL_SHOW_ITEM, {'item': 'Hat', 'owner': ''}), ('Chris has no items.', True))
        self.assertEqual(await self.use(agent_client.TOOL_SHOW_ITEM, {'item': 'Hat', 'owner': 'nobody'}), (agent_abilities.NOBODY, True))

    async def test_item_names_are_matched_loosely(self):
        self.setUpAll()
        gtrade = agent_abilities.gtrade_cog.GTrade(Mock())
        gtrade.itemEmbed = Mock(return_value = 'card')
        self.client.get_cog = Mock(return_value = gtrade)
        items = {'a': {'name': 'The Communist Manifesto'}, 'b': {'name': 'Golden Sword'}, 'c': {'name': 'Wooden Sword'}, 'd': {'name': 'Sword'}}
        self.patch(agent_abilities.gtrade_queries, 'getAllUserItems', MagicMock(return_value = items))
        # what they typed, held in exactly one name
        await self.use(agent_client.TOOL_SHOW_ITEM, {'item': 'communist manifesto', 'owner': ''})
        self.assertEqual(gtrade.itemEmbed.call_args.args[1]['name'], 'The Communist Manifesto')
        # an exact name wins over the names holding it
        await self.use(agent_client.TOOL_SHOW_ITEM, {'item': 'sword', 'owner': ''})
        self.assertEqual(gtrade.itemEmbed.call_args.args[1]['name'], 'Sword')
        del items['d']
        self.assertEqual(await self.use(agent_client.TOOL_SHOW_ITEM, {'item': 'sword', 'owner': ''}), ("More than one of Chris's items matches that: Golden Sword, Wooden Sword. Ask which.", True))

    def stormOn(self, state = 2):
        self.msg.content = 'gbot guess 45, or bet 1,000 on 7, or 42'
        storms = Mock(commonStorms = AsyncMock(), stormStates = {'10': {'stormState': state}})
        self.client.get_cog = Mock(return_value = storms)
        self.msg.delete = AsyncMock()
        return storms

    async def test_a_guess_hides_the_number_and_its_result_is_the_reply(self):
        self.setUpAll()
        storms = self.stormOn()
        posted = Mock()
        self.msg.channel.send = AsyncMock(return_value = posted)
        async def guess(context, author, number, bet):
            self.assertEqual((context.guild, author, number, bet), (self.guild, self.sender, 45, None))
            await context.send('❌ **Chris** guessed wrong.', view = 'hint button')
        storms.commonStorms.side_effect = guess
        cards = []
        self.assertEqual(await self.abilities.run(agent_client.TOOL_GUESS_STORM, {'number': '45'}, self.msg, False, [], cards), (agent_abilities.GUESSED, False))
        self.msg.delete.assert_awaited_once()
        self.msg.channel.send.assert_awaited_once_with('❌ **Chris** guessed wrong.', view = 'hint button')
        self.assertEqual(cards, [posted])
        # without being able to delete it, the guess still goes
        self.msg.delete.side_effect = nextcord.HTTPException(Mock(status = 403), 'no')
        await self.use(agent_client.TOOL_GUESS_STORM, {'number': '45'})
        self.assertEqual(storms.commonStorms.await_count, 2)

    async def test_no_storm_or_no_number_posts_nothing(self):
        self.setUpAll()
        for state in (0, 1):
            with self.subTest(state = state):
                self.stormOn(state)
                self.assertEqual(await self.use(agent_client.TOOL_GUESS_STORM, {'number': '42'}), ('No Storm is on right now, so there is nothing to guess. Nothing was posted. Tell them.', True))
        self.msg.content = 'bet 5 on 42'
        self.client.get_cog = Mock(return_value = Mock(stormStates = {}))
        self.assertTrue((await self.use(agent_client.TOOL_BET_STORM, {'number': '42', 'bet': '5'}))[1])
        self.stormOn()
        for number in ('lots', None):
            self.assertEqual(await self.use(agent_client.TOOL_GUESS_STORM, {'number': number}), ('That is not a number to guess.', True))
        self.assertEqual(await self.use(agent_client.TOOL_BET_STORM, {'number': '42', 'bet': 'heaps'}), ('That is not an amount to bet.', True))
        self.assertEqual(await self.use(agent_client.TOOL_BET_STORM, {'number': '42', 'bet': None}), ('That is not an amount to bet.', True))
        # a number that isn't in their own message can't have been asked for by them
        self.assertEqual(await self.use(agent_client.TOOL_GUESS_STORM, {'number': '99'}), ('Their message has no such number, so nothing was done.', True))
        self.msg.reply.assert_not_awaited()
        self.msg.delete.assert_not_awaited()

    async def test_a_bet_is_confirmed_without_showing_the_number(self):
        self.setUpAll()
        storms = self.stormOn()
        self.msg.channel.send = AsyncMock(return_value = Mock())
        self.assertEqual(await self.use(agent_client.TOOL_BET_STORM, {'number': '7', 'bet': '1,000'}), (agent_abilities.CONFIRM_POSTED, False))
        self.msg.delete.assert_awaited_once()
        # not a reply: Discord refuses a reply to the message just deleted
        self.msg.reply.assert_not_awaited()
        kwargs = self.msg.channel.send.await_args.kwargs
        embed, view = kwargs['embed'], kwargs['view']
        self.assertTrue(embed.description.startswith('For **Chris**.'))
        self.assertEqual(embed.title, '🎲 Bet 1,000.00 GCoin on your guess?')
        self.assertNotIn('7', embed.title + embed.description)
        pressed = self.press()
        await view.confirmed(pressed)
        storms.commonStorms.assert_awaited_once_with(pressed, self.sender, 7, Decimal('1000'))
        self.assertEqual(pressed.edit_original_message.await_args.kwargs['content'], '🎲 Chris bet 1,000.00 GCoin.')
        # one Storms refused, as with the Storm over by the press or too little GCoin, isn't announced as placed
        storms.commonStorms.return_value = None
        await self.use(agent_client.TOOL_BET_STORM, {'number': '7', 'bet': '1,000'})
        pressed = self.press()
        await self.msg.channel.send.await_args.kwargs['view'].confirmed(pressed)
        self.assertEqual(pressed.edit_original_message.await_args.kwargs['content'], "❌ Chris's bet wasn't placed.")

    def test_the_levels_add_up(self):
        self.assertEqual(agent_client.toolsAllowed('off'), set())
        self.assertEqual(agent_client.toolsAllowed('read'), agent_client.READ_TOOLS)
        self.assertEqual(agent_client.toolsAllowed('safe'), agent_client.READ_TOOLS | agent_client.SAFE_TOOLS)
        self.assertEqual(agent_client.toolsAllowed('all'), agent_client.READ_TOOLS | agent_client.SAFE_TOOLS | agent_client.ALL_TOOLS)
        # nothing at read or safe moves GCoin or items, bets, pings or changes settings (a Storm's own
        # rewards to the sender, for a winning guess or the umbrella, are the game's, not a move)
        moves = {'send_gcoin', 'buy_item', 'sell_item', 'set_feature', 'bet_storm', 'craft_item', 'destroy_item', 'answer_trade',
                 'hype_change', 'remind_role', 'set_config', 'report', 'agent_setting', 'patreon_register'}
        self.assertEqual(moves, agent_client.ALL_TOOLS)
        self.assertFalse((agent_client.READ_TOOLS | agent_client.SAFE_TOOLS) & moves)

    def test_every_tool_has_a_toggle_unless_it_needs_none(self):
        for name in agent_client.READ_TOOLS | agent_client.ACTING_TOOLS:
            with self.subTest(name = name):
                # get_features reports on them all, and set_feature is Config's, behind the admin check
                # these sit behind the admin check or Patreon's own, as their commands do, or report on every feature
                self.assertTrue(name in agent_abilities.TOGGLES or name in (agent_client.TOOL_GET_FEATURES, agent_client.TOOL_SET_FEATURE, agent_client.TOOL_SET_CONFIG,
                                                                            agent_client.TOOL_REPORT, agent_client.TOOL_AGENT_SETTING, agent_client.TOOL_PATREON, agent_client.TOOL_OPEN_CARD))
