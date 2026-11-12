#region IMPORTS
import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import nextcord

from GBotDiscord.src.agent import agent_abilities, agent_client
from GBotDiscord.src.agent.agent_abilities import AgentAbilities
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.reminders import reminders_cog
#endregion

# The agent covering everything (8.3, M5b): each feature's tools, at their level, through the
# feature's own engine, with the same checks as its command.

NOW = datetime(2026, 11, 10, 1, 14, tzinfo = timezone.utc)

def person(userId, name):
    made = Mock(id = userId, display_name = name, bot = False, voice = Mock(), mention = f'<@{userId}>', send = AsyncMock(return_value = Mock()))
    made.name = name.lower()
    return made

def named(kind, itemId, name, **extra):
    made = Mock(id = itemId, mention = f'<{kind}{itemId}>', **extra)
    made.name = name
    return made

class TestAgentCoverage(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\n\nStarting agent coverage unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted agent coverage unit tests.\n')

    def setUp(self):
        self.sender = person(1, 'Chris')
        self.sam = person(2, 'Sam')
        self.general = named('#', 20, 'general')
        self.raids = named('@&', 30, 'Raid Team')
        self.guild = Mock(id = 10, members = [self.sender, self.sam], text_channels = [self.general], roles = [self.raids])
        self.guild.name = 'My Server'
        self.guild.get_member = Mock(side_effect = lambda userId: {1: self.sender, 2: self.sam}.get(userId))
        self.msg = Mock(guild = self.guild, author = self.sender, channel = Mock(id = 20, mention = '<#20>', send = AsyncMock(return_value = Mock())), attachments = [], embeds = [], content = 'gbot do it')
        self.msg.reply = AsyncMock(return_value = Mock())
        self.msg.delete = AsyncMock()
        self.cogs = {}
        self.client = Mock()
        self.client.get_cog = Mock(side_effect = lambda name: self.cogs[name])
        self.abilities = AgentAbilities(self.client)
        self.patch(agent_abilities.config_queries, 'getServerValue', MagicMock(return_value = True))
        self.recheck = self.patch(agent_abilities.predicates, 'recheck', AsyncMock())

    def patch(self, target, name, value):
        started = patch.object(target, name, value)
        started.start()
        self.addCleanup(started.stop)
        return value

    async def use(self, name, toolInput, isAdmin = False, cards = None):
        # each call its own message, with its own cards, unless a test shares them
        return await self.abilities.run(name, toolInput, self.msg, isAdmin, [], [] if cards is None else cards)

    def press(self, user = None):
        interaction = Mock(spec = nextcord.Interaction)
        interaction.user = user or self.sender
        interaction.guild = self.guild
        interaction.channel = self.msg.channel
        interaction.response = Mock(defer = AsyncMock(), edit_message = AsyncMock(), send_modal = AsyncMock(), is_done = Mock(return_value = False))
        interaction.edit_original_message = AsyncMock()
        return interaction

    def posted(self):
        kwargs = self.msg.reply.await_args.kwargs
        return kwargs['embed'], kwargs['view']

    def opened(self):
        # the 🔒 Open one-liner posted in the channel
        kwargs = self.msg.channel.send.await_args.kwargs
        return kwargs['content'], kwargs['view']

    async def openAs(self, view, user = None):
        pressed = self.press(user)
        await view.open(pressed)
        return pressed

    async def confirm(self):
        _, view = self.posted()
        pressed = self.press()
        await view.confirmed(pressed)
        return pressed.edit_original_message.await_args.kwargs['content']

    async def test_admin_only_tools_say_so_to_members(self):
        for name in agent_abilities.ADMIN_TOOLS:
            with self.subTest(name = name):
                self.assertEqual(await self.use(name, {}), ('Only admins can do that.', True))

    # read

    async def test_history_opens_privately(self):
        gcoin = Mock(commonHistory = AsyncMock())
        self.cogs['GCoin'] = gcoin
        self.msg.channel.send.return_value = Mock(delete = AsyncMock())
        cards = []
        # /gcoin only shows history privately, so it's a 🔒 Open, never the channel or DMs
        self.assertEqual(await self.use(agent_client.TOOL_GET_HISTORY, {'user': ''}, cards = cards), (agent_abilities.OPENS, False))
        content, view = self.opened()
        self.assertEqual(content, '💰 GCoin history for **Chris**. Press 🔒 Open to see it privately.')
        self.assertEqual(cards, [self.msg.channel.send.return_value])
        pressed = await self.openAs(view)
        gcoin.commonHistory.assert_awaited_once_with(pressed, self.sender, None)
        self.sender.send.assert_not_awaited()
        self.assertEqual(await self.use(agent_client.TOOL_GET_HISTORY, {'user': 'sam'}), ("Only admins can see someone else's history.", True))
        await self.use(agent_client.TOOL_GET_HISTORY, {'user': 'sam'}, isAdmin = True)
        content, view = self.opened()
        self.assertEqual(content, "💰 Sam's GCoin history for **Chris**. Press 🔒 Open to see it privately.")
        pressed = await self.openAs(view)
        gcoin.commonHistory.assert_awaited_with(pressed, self.sender, self.sam)
        self.assertEqual(await self.use(agent_client.TOOL_GET_HISTORY, {'user': 'nobody'}), (agent_abilities.NOBODY, True))

    async def test_hype_lookup(self):
        hype = Mock(describeTest = Mock(return_value = '🧪 That message would match: gg'), listMatches = Mock(return_value = ([], ['**1.** gg'], [])))
        self.cogs['Hype'] = hype
        self.patch(agent_abilities.hype_queries, 'getAllServerMatches', MagicMock(return_value = {'m': {}}))
        self.assertEqual(await self.use(agent_client.TOOL_HYPE_LOOKUP, {'action': 'list', 'text': ''}, isAdmin = True), ('**1.** gg', False))
        self.assertEqual(await self.use(agent_client.TOOL_HYPE_LOOKUP, {'action': 'test', 'text': 'gg all'}, isAdmin = True), ('🧪 That message would match: gg\n(Hype matches from the start of a message, so a pattern fires anywhere in one only if it begins with .*)', False))
        hype.describeTest.assert_called_once_with(10, {'m': {}}, 'gg all')
        self.assertEqual(await self.use(agent_client.TOOL_HYPE_LOOKUP, {'action': 'test', 'text': None}, isAdmin = True), ('Give a message to test.', True))
        hype.listMatches.return_value = ([], [], [])
        self.assertEqual(await self.use(agent_client.TOOL_HYPE_LOOKUP, {'action': 'list', 'text': ''}, isAdmin = True), ('This server has no Hype matches.', False))

    async def test_storm_status_and_umbrella(self):
        storms = Mock(stormStates = {'10': {'stormState': 1}}, commonUmbrella = AsyncMock())
        self.cogs['Storms'] = storms
        self.assertEqual((await self.use(agent_client.TOOL_STORM_STATUS, {}))[0], 'A Storm is incoming: putting up the umbrella starts it.')
        async def umbrella(context, author):
            await context.send('☂️ Chris put up the umbrella.')
        storms.commonUmbrella.side_effect = umbrella
        cards = []
        self.assertFalse((await self.use(agent_client.TOOL_STORM_UMBRELLA, {}, cards = cards))[1])
        self.msg.channel.send.assert_awaited_once_with('☂️ Chris put up the umbrella.')
        self.assertEqual(cards, [self.msg.channel.send.return_value])
        # outside a run, nothing collects the post
        storms.commonUmbrella.reset_mock()
        await self.use(agent_client.TOOL_STORM_UMBRELLA, {})
        storms.stormStates['10']['stormState'] = 2
        self.assertEqual((await self.use(agent_client.TOOL_STORM_STATUS, {}))[0], 'A Storm is on: guess a number from 1 to 200.')
        self.assertTrue((await self.use(agent_client.TOOL_STORM_UMBRELLA, {}))[1])
        storms.stormStates = {}
        self.assertEqual((await self.use(agent_client.TOOL_STORM_STATUS, {}))[0], 'No Storm right now.')

    # safe

    async def test_who_dis_is_private(self):
        whoDis = Mock(openCardFromChannel = AsyncMock(return_value = True))
        self.cogs['WhoDis'] = whoDis
        cards = []
        # its message must be about Who Dis, as it goes
        self.assertEqual(await self.use(agent_client.TOOL_WHO_DIS, {'action': 'start', 'name': ''}), ('Their message is not about Who Dis, so nothing was done.', True))
        self.assertEqual(await self.use(agent_client.TOOL_WHO_DIS, {'action': 'guess', 'name': 'sam'}), ('Their message is not about Who Dis, so nothing was done.', True))
        whoDis.openCardFromChannel.assert_not_awaited()
        # no line in the channel at all: the card goes to their DMs
        self.msg.content = 'gbot start a who dis game'
        self.assertTrue((await self.use(agent_client.TOOL_WHO_DIS, {'action': 'start', 'name': ''}, cards = cards))[0].startswith('Done. Their message was deleted'))
        whoDis.openCardFromChannel.assert_awaited_once_with(self.msg, self.sender, self.guild)
        self.assertEqual(cards, [self.msg])
        self.msg.channel.send.assert_not_awaited()
        # a guess naming them, without the words Who Dis
        self.msg.content = 'gbot is it Sam?'
        self.assertFalse((await self.use(agent_client.TOOL_WHO_DIS, {'action': 'guess', 'name': ' sam '}))[1])
        whoDis.openCardFromChannel.return_value = False
        self.assertEqual(await self.use(agent_client.TOOL_WHO_DIS, {'action': 'guess', 'name': 'sam'}), ('Their DMs are closed, and GBot told them so. Write nothing.', False))
        self.assertEqual(await self.use(agent_client.TOOL_WHO_DIS, {'action': 'dance', 'name': None}), ('Say whether to start, end, leave or guess.', True))
        # open_card goes the same way, never a 🔒 line saying who asked
        whoDis.openCardFromChannel.return_value = True
        self.msg.content = 'gbot show my card'
        self.assertEqual(await self.use(agent_client.TOOL_OPEN_CARD, {'feature': 'Who Dis'}), ('Their message is not about Who Dis, so nothing was done.', True))
        self.msg.content = 'gbot show my who dis card'
        cards = []
        self.assertFalse((await self.use(agent_client.TOOL_OPEN_CARD, {'feature': 'Who Dis'}, cards = cards))[1])
        self.assertEqual(cards, [self.msg])
        self.msg.channel.send.assert_not_awaited()

    async def test_editing_the_music(self):
        music = Mock(listenerProblem = Mock(return_value = None), followProblem = Mock(return_value = None), updateCard = AsyncMock(), spotifySyncSessions = {}, musicStates = {})
        for name in ('commonRemove', 'commonMove', 'commonRestart', 'commonElevator', 'commonSpotify'):
            setattr(music, name, AsyncMock())
        self.cogs['Music'] = music
        cases = [({'action': 'remove', 'position': 2, 'to': 0, 'user': ''}, 'commonRemove', (self.sender, 2)),
                 ({'action': 'move', 'position': 3, 'to': 1, 'user': ''}, 'commonMove', (self.sender, 3, 1)),
                 ({'action': 'restart', 'position': 0, 'to': 0, 'user': ''}, 'commonRestart', (self.sender,)),
                 ({'action': 'elevator', 'position': 0, 'to': 0, 'user': '', 'on': True}, 'commonElevator', ()),
                 ({'action': 'follow_spotify', 'position': 0, 'to': 0, 'user': 'sam'}, 'commonSpotify', (self.sender, self.sam))]
        for toolInput, engine, args in cases:
            with self.subTest(action = toolInput['action']):
                self.assertFalse((await self.use(agent_client.TOOL_EDIT_MUSIC, toolInput))[1])
                self.assertEqual(getattr(music, engine).await_args.args[1:], args)
        for toolInput, expected in (({'action': 'remove', 'position': 'two'}, 'Give the queue position to remove.'),
                                    ({'action': 'move', 'position': 1, 'to': None}, 'Give the queue position to move, and where to.'),
                                    ({'action': 'follow_spotify', 'user': 'nobody'}, agent_abilities.NOBODY),
                                    ({'action': 'elevator'}, 'Say whether to turn elevator mode on or off.'),
                                    ({'action': 'elevator', 'on': False}, 'Elevator mode is already off, so nothing changed. Tell them.'),
                                    ({'action': 'dance'}, 'That is not something you can do to the music.')):
            with self.subTest(expected = expected):
                self.assertEqual(await self.use(agent_client.TOOL_EDIT_MUSIC, toolInput), (expected, True))
        # an empty user stops following whoever is followed, rather than following the sender
        music.spotifySyncSessions['10'] = {'userId': '2'}
        await self.use(agent_client.TOOL_EDIT_MUSIC, {'action': 'follow_spotify', 'position': 0, 'to': 0, 'user': ''})
        self.assertEqual(music.commonSpotify.await_args.args[1:], (self.sender, self.sam))
        # asked to follow who is already followed, which the button would take as a stop
        self.assertEqual(await self.use(agent_client.TOOL_EDIT_MUSIC, {'action': 'follow_spotify', 'position': 0, 'to': 0, 'user': 'sam'}), ("Already following Sam's Spotify, so nothing changed. Tell them.", True))
        music.spotifySyncSessions.clear()
        # elevator mode, already on, is left on, and turned off when that's what was asked
        music.musicStates['10'] = {'isElevatorMode': True, 'card': None}
        self.assertEqual(await self.use(agent_client.TOOL_EDIT_MUSIC, {'action': 'elevator', 'on': True}), ('Elevator mode is already on, so nothing changed. Tell them.', True))
        self.assertFalse((await self.use(agent_client.TOOL_EDIT_MUSIC, {'action': 'elevator', 'on': False}))[1])
        music.musicStates.clear()
        music.listenerProblem.return_value = 'Join 🔊 **Lounge** to control the music.'
        self.assertTrue((await self.use(agent_client.TOOL_EDIT_MUSIC, {'action': 'restart'}))[0].startswith('Join'))
        # following asks its own check, which lets it start the music from silence
        self.assertEqual((await self.use(agent_client.TOOL_EDIT_MUSIC, {'action': 'follow_spotify', 'position': 0, 'to': 0, 'user': 'sam'}))[1], False)
        music.followProblem.return_value = 'Join a voice channel first, so GBot knows where to play.'
        self.assertTrue((await self.use(agent_client.TOOL_EDIT_MUSIC, {'action': 'follow_spotify', 'position': 0, 'to': 0, 'user': 'sam'}))[0].startswith('Join a voice channel first'))

    async def test_renaming_an_item(self):
        async def rename(reply, author, item, name):
            await reply.send(f'✏️ Renamed {item} to {name}.')
        self.cogs['GTrade'] = Mock(commonRename = AsyncMock(side_effect = rename))
        self.patch(agent_abilities.gtrade_queries, 'getAllUserItems', MagicMock(return_value = {'i': {'name': 'Hat'}}))
        self.assertEqual(await self.use(agent_client.TOOL_RENAME_ITEM, {'item': 'hat', 'name': ' Crown '}), ('✏️ Renamed Hat to Crown.', False))
        self.assertEqual(await self.use(agent_client.TOOL_RENAME_ITEM, {'item': 'hat', 'name': ''}), ('Give the new name.', True))
        self.assertEqual(await self.use(agent_client.TOOL_RENAME_ITEM, {'item': 'shoe', 'name': 'x'}), ('Chris has no item called that. Their items: Hat.', True))
        async def refuse(reply, author, item, name):
            await reply.send(embed = Mock(description = 'That name is taken.'))
        self.cogs['GTrade'].commonRename.side_effect = refuse
        self.assertEqual(await self.use(agent_client.TOOL_RENAME_ITEM, {'item': 'hat', 'name': 'x'}), ('That name is taken.', True))
        self.cogs['GTrade'].commonRename.side_effect = None
        self.assertEqual(await self.use(agent_client.TOOL_RENAME_ITEM, {'item': 'hat', 'name': 'x'}), ('Renamed.', False))

    # all

    def hype(self, matches):
        hype = Mock(describeRegex = Mock(side_effect = lambda regex: f'`{regex}`'), describeResponses = Mock(side_effect = lambda responses: ', '.join(responses)),
                    patternProblem = Mock(return_value = None), readResponses = Mock(side_effect = lambda text, isReaction, guild: (text.split(), None) if text else (None, 'Please give at least one.')))
        self.cogs['Hype'] = hype
        self.patch(agent_abilities.hype_queries, 'getAllServerMatches', MagicMock(return_value = matches))
        for name in ('createMatch', 'updateMatch', 'removeMatch'):
            self.patch(agent_abilities.hype_queries, name, MagicMock())
        return hype

    async def test_hype_add_edit_delete(self):
        hype = self.hype({'m1': {'regex': 'gg', 'responses': ['🔥'], 'isReaction': True}})
        await self.use(agent_client.TOOL_HYPE_CHANGE, {'action': 'add', 'number': 0, 'pattern': 'nice', 'kind': 'reply', 'responses': 'yes'}, isAdmin = True)
        embed, _ = self.posted()
        self.assertEqual((embed.title, embed.description), ('↩️ Add this Hype match?', '**Matches:** `nice`\n**Replies with one of:** yes'))
        self.assertEqual(await self.confirm(), '↩️ Saved the Hype match `nice`.')
        agent_abilities.hype_queries.createMatch.assert_called_once_with(10, 'nice', ['yes'], False)
        await self.use(agent_client.TOOL_HYPE_CHANGE, {'action': 'edit', 'number': 1, 'pattern': 'gg+', 'kind': 'reply', 'responses': '🎉'}, isAdmin = True)
        # an edit says which match it replaces
        self.assertEqual(self.posted()[0].description, '**Matches:** `gg+`\n**Reacts with one of:** 🎉\n**Replaces:** `gg` → 🔥')
        await self.confirm()
        agent_abilities.hype_queries.updateMatch.assert_called_once_with(10, 'm1', 'gg+', ['🎉'])
        # deleted before the press: nothing is written, as half a match would be
        await self.use(agent_client.TOOL_HYPE_CHANGE, {'action': 'edit', 'number': 1, 'pattern': 'gg+', 'kind': 'reply', 'responses': '🎉'}, isAdmin = True)
        agent_abilities.hype_queries.updateMatch.return_value = False
        self.assertEqual(await self.confirm(), '❌ That Hype match is gone, so nothing was changed.')
        agent_abilities.hype_queries.getAllServerMatches.return_value = {'m1': {'regex': 'gg', 'responses': ['🔥'], 'isReaction': True}}
        await self.use(agent_client.TOOL_HYPE_CHANGE, {'action': 'delete', 'number': 1}, isAdmin = True)
        self.assertEqual(self.posted()[0].title, '↩️ Delete this Hype match?')
        self.assertEqual(await self.confirm(), '↩️ Deleted the Hype match `gg`.')
        agent_abilities.hype_queries.removeMatch.assert_called_once_with(10, 'm1')
        self.assertEqual(await self.use(agent_client.TOOL_HYPE_CHANGE, {'action': 'delete', 'number': 5}, isAdmin = True), ('There is no match number 5. Use hype_lookup for their numbers.', True))
        self.assertEqual(await self.use(agent_client.TOOL_HYPE_CHANGE, {'action': 'dance'}, isAdmin = True), ('Say whether to add, edit or delete.', True))
        self.assertEqual(await self.use(agent_client.TOOL_HYPE_CHANGE, {'action': 'add', 'pattern': ' ', 'responses': 'x'}, isAdmin = True), ('Give a pattern.', True))
        # the form's own limits
        for toolInput in ({'action': 'add', 'pattern': 'x' * 301, 'responses': 'x'}, {'action': 'add', 'pattern': 'x', 'responses': 'x' * 2001}):
            self.assertEqual(await self.use(agent_client.TOOL_HYPE_CHANGE, toolInput, isAdmin = True), ('A pattern can be at most 300 characters, and the replies 2000.', True))
        self.assertEqual(await self.use(agent_client.TOOL_HYPE_CHANGE, {'action': 'add', 'pattern': 'x', 'responses': None}, isAdmin = True), ('Please give at least one.', True))
        hype.patternProblem.return_value = '`(` is not valid'
        self.assertEqual(await self.use(agent_client.TOOL_HYPE_CHANGE, {'action': 'add', 'pattern': '(', 'responses': 'x'}, isAdmin = True), ('`(` is not valid', True))

    async def test_crafting_from_an_attached_image(self):
        self.assertEqual(await self.use(agent_client.TOOL_CRAFT_ITEM, {'name': 'Hat', 'value': '5'}), ('Crafting needs an image attached to their message, or a link to one in it. Nothing was posted. Tell them.', True))
        image = Mock(content_type = 'image/png', url = 'https://cdn/hat.png')
        self.msg.attachments = [Mock(content_type = 'text/plain'), image]
        self.assertEqual(await self.use(agent_client.TOOL_CRAFT_ITEM, {'name': ' ', 'value': '5'}), ('Give the item a name and a value.', True))
        gtrade = Mock(commonCraft = AsyncMock())
        self.cogs['GTrade'] = gtrade
        await self.use(agent_client.TOOL_CRAFT_ITEM, {'name': ' Hat ', 'value': '5'})
        embed, _ = self.posted()
        self.assertEqual((embed.title, embed.image.url), ('⚒️ Craft Hat worth 5 GCoin?', 'https://cdn/hat.png'))
        self.assertEqual(await self.confirm(), '⚒️ Crafted.')
        self.assertEqual(gtrade.commonCraft.await_args.args[1:], (self.sender, 'Hat', '5', image, None))
        # or a link in the message
        self.msg.attachments = []
        self.msg.content = 'gbot craft https://t3.ftcdn.net/cat.jpg as Lucky Cat'
        await self.use(agent_client.TOOL_CRAFT_ITEM, {'name': 'Lucky Cat', 'value': '5'})
        self.assertEqual(self.posted()[0].image.url, 'https://t3.ftcdn.net/cat.jpg')
        await self.confirm()
        self.assertEqual(gtrade.commonCraft.await_args.args[4:], (None, 'https://t3.ftcdn.net/cat.jpg'))

    async def test_one_message_gets_one_confirm_card(self):
        # "turn on storms and delete hype match 1": the second joins the first's card, and one press does both
        self.patch(agent_abilities.config_queries, 'getServerValue', MagicMock(side_effect = lambda serverId, toggle: toggle != 'toggle_storms'))
        config = Mock(toggleFeature = AsyncMock(return_value = '🌧️ **Storms** is now on.'))
        hype = Mock(describeRegex = Mock(side_effect = lambda regex: f'`{regex}`'), describeResponses = Mock(side_effect = lambda responses: ', '.join(responses)))
        self.cogs.update({'Config': config, 'Hype': hype})
        self.patch(agent_abilities.hype_queries, 'getAllServerMatches', MagicMock(return_value = {'m1': {'regex': 'hi', 'responses': ['yo']}}))
        removed = self.patch(agent_abilities.hype_queries, 'removeMatch', MagicMock())
        cards = []
        self.assertEqual(await self.use(agent_client.TOOL_SET_FEATURE, {'features': ['Storms'], 'setting': 'on'}, isAdmin = True, cards = cards), (agent_abilities.CONFIRM_POSTED, False))
        embed, view = self.posted()
        view.message = self.msg.reply.return_value
        view.message.edit = AsyncMock()
        self.assertEqual(await self.use(agent_client.TOOL_HYPE_CHANGE, {'action': 'delete', 'number': 1, 'numbers': [], 'pattern': '', 'kind': 'reply', 'responses': ''}, isAdmin = True, cards = cards), (agent_abilities.CONFIRM_ADDED, False))
        self.msg.reply.assert_awaited_once()
        edited = view.message.edit.await_args.kwargs['embed']
        self.assertEqual((edited.title, edited.description), ('Confirm these 2?', '**🌧️ Turn on Storms?**\nFeatures that depend on each other switch together, as in `/config`.\n\n**↩️ Delete this Hype match?**\n`hi` → yo'))
        # from two features, so its footer is the agent's
        self.assertEqual(view.feature, 'Agent')
        # one refused when pressed doesn't stop the rest
        self.recheck.side_effect = [None, agent_abilities.predicates.FeatureNotEnabledForGuild('x', 'Hype')]
        pressed = self.press()
        await view.confirmed(pressed)
        self.assertEqual(pressed.edit_original_message.await_args.kwargs['content'], "🌧️ **Storms** is now on.\n❌ Sorry <@1>, Hype is turned off in this server. An admin can turn it on in `/config`.")
        removed.assert_not_called()
        # a card already pressed takes nothing more: the next confirm posts its own
        self.recheck.side_effect = None
        await self.use(agent_client.TOOL_HYPE_CHANGE, {'action': 'delete', 'number': 1, 'numbers': [], 'pattern': '', 'kind': 'reply', 'responses': ''}, isAdmin = True, cards = cards)
        self.assertEqual(self.msg.reply.await_count, 2)

    async def test_several_at_once_where_all_of_them_is_natural(self):
        hype = Mock(describeRegex = Mock(side_effect = lambda regex: f'`{regex}`'), describeResponses = Mock(side_effect = lambda responses: ', '.join(responses)))
        config = Mock(toggleFeature = AsyncMock(side_effect = lambda interaction, toggle: f'{toggle} is now off.'))
        self.cogs.update({'Hype': hype, 'Config': config})
        self.patch(agent_abilities.hype_queries, 'getAllServerMatches', MagicMock(return_value = {'m1': {'regex': 'hi', 'responses': ['yo']}, 'm2': {'regex': 'gm', 'responses': ['☀️']}}))
        removed = self.patch(agent_abilities.hype_queries, 'removeMatch', MagicMock())
        # every Hype match
        await self.use(agent_client.TOOL_HYPE_CHANGE, {'action': 'delete', 'number': 0, 'numbers': [1, 2, 1], 'pattern': '', 'kind': 'reply', 'responses': ''}, isAdmin = True)
        embed, view = self.posted()
        self.assertEqual((embed.title, embed.description), ('↩️ Delete these 2 Hype matches?', '• `hi` → yo\n• `gm` → ☀️'))
        pressed = self.press()
        await view.confirmed(pressed)
        self.assertEqual([call.args[1] for call in removed.call_args_list], ['m1', 'm2'])
        self.assertEqual(pressed.edit_original_message.await_args.kwargs['content'], '↩️ Deleted the Hype match `hi`.\n↩️ Deleted the Hype match `gm`.')
        # no number at all is every match, with no lookup first
        everything = {'action': 'delete', 'number': 0, 'numbers': [], 'pattern': '', 'kind': 'reply', 'responses': ''}
        await self.use(agent_client.TOOL_HYPE_CHANGE, everything, isAdmin = True)
        self.assertEqual(self.posted()[0].title, '↩️ Delete these 2 Hype matches?')
        agent_abilities.hype_queries.getAllServerMatches.return_value = None
        self.assertEqual(await self.use(agent_client.TOOL_HYPE_CHANGE, everything, isAdmin = True), ('This server has no Hype matches.', True))
        agent_abilities.hype_queries.getAllServerMatches.return_value = {'m1': {'regex': 'hi', 'responses': ['yo']}, 'm2': {'regex': 'gm', 'responses': ['☀️']}}
        for numbers in ([1, 3], ['one']):
            with self.subTest(numbers = numbers):
                self.assertEqual((await self.use(agent_client.TOOL_HYPE_CHANGE, {'action': 'delete', 'number': 0, 'numbers': numbers, 'pattern': '', 'kind': 'reply', 'responses': ''}, isAdmin = True))[1], True)
        # several features, leaving out any already so, and one switched since by another's dependency
        states = {'toggle_music': True, 'toggle_storms': True, 'toggle_hype': False}
        self.patch(agent_abilities.config_queries, 'getServerValue', MagicMock(side_effect = lambda serverId, toggle: states[toggle]))
        await self.use(agent_client.TOOL_SET_FEATURE, {'features': ['Music', 'Storms', 'Hype'], 'setting': 'off'}, isAdmin = True)
        embed, view = self.posted()
        self.assertEqual(embed.title, '⚙️ Turn off Music and Storms?')
        states['toggle_storms'] = False
        pressed = self.press()
        await view.confirmed(pressed)
        self.assertEqual(pressed.edit_original_message.await_args.kwargs['content'], 'toggle_music is now off.\nStorms is already off.')
        self.assertEqual(await self.use(agent_client.TOOL_SET_FEATURE, {'features': ['Hype', 'Storms'], 'setting': 'off'}, isAdmin = True), ('Hype and Storms are already off.', True))
        self.assertEqual(await self.use(agent_client.TOOL_SET_FEATURE, {'features': [], 'setting': 'off'}, isAdmin = True), ('That is not a feature the agent can switch.', True))
        # songs from the last, so each position means the song it did
        music = Mock(listenerProblem = Mock(return_value = None), commonRemove = AsyncMock(), musicStates = {})
        self.cogs['Music'] = music
        await self.use(agent_client.TOOL_EDIT_MUSIC, {'action': 'remove', 'position': 0, 'positions': [2, 4, 3, 4], 'to': 0, 'user': ''})
        self.assertEqual([call.args[2] for call in music.commonRemove.await_args_list], [4, 3, 2])
        self.assertEqual(await self.use(agent_client.TOOL_EDIT_MUSIC, {'action': 'remove', 'position': 0, 'positions': ['two'], 'to': 0, 'user': ''}), ('Give the queue position to remove.', True))

    async def test_two_from_one_feature_keep_its_footer_and_a_card_outside_a_run_is_nobodys(self):
        view = agent_abilities.AgentConfirm(1, 'toggle_hype', True, AsyncMock(), '↩️ One', 'a', 'Hype')
        view.add('↩️ Two', 'b', 'toggle_hype', True, AsyncMock(), 'Hype')
        self.assertEqual(view.feature, 'Hype')
        # posted outside an agent's run, as a command's is: nothing collects it
        token = agent_abilities.CARDS.set(None)
        agent_abilities.addCard(Mock())
        self.assertIsNone(agent_abilities.CARDS.get())
        agent_abilities.CARDS.reset(token)

    async def test_crafting_shows_its_picture_while_it_is_the_cards_only_one(self):
        gtrade = Mock()
        self.cogs['GTrade'] = gtrade
        self.patch(agent_abilities.gtrade_cog, 'imageIn', Mock(return_value = (None, 'https://example.com/cat.png')))
        await self.use(agent_client.TOOL_CRAFT_ITEM, {'name': 'Cat', 'value': '5'})
        embed, view = self.posted()
        self.assertEqual((embed.title, embed.image.url), ('⚒️ Craft Cat worth 5 GCoin?', 'https://example.com/cat.png'))

    async def test_a_card_still_posts_once_their_message_is_gone(self):
        self.msg.reply = AsyncMock(side_effect = nextcord.HTTPException(Mock(status = 400), 'Unknown message'))
        self.patch(agent_abilities.config_queries, 'getServerValue', MagicMock(return_value = False))
        self.cogs['Config'] = Mock()
        await self.use(agent_client.TOOL_SET_FEATURE, {'features': ['Storms'], 'setting': 'on'}, isAdmin = True)
        self.assertEqual(self.msg.channel.send.await_args.kwargs['embed'].title, '🌧️ Turn on Storms?')

    async def test_the_price_on_a_buy_card_is_the_price_paid(self):
        gtrade = Mock(buyUnderLock = AsyncMock(), tradeLock = asyncio.Lock())
        self.cogs['GTrade'] = gtrade
        items = {'i': {'name': 'Hat', 'value': '7'}}
        self.patch(agent_abilities.gtrade_queries, 'getAllUserItems', MagicMock(return_value = items))
        self.patch(agent_abilities.gtrade_queries, 'getPendingTradeTransaction', MagicMock(return_value = None))
        self.patch(agent_abilities.gcoin_queries, 'getUserBalance', MagicMock(return_value = Decimal('10')))
        await self.use(agent_client.TOOL_BUY_ITEM, {'item': 'hat', 'owner': 'sam', 'action': 'buy'})
        # the owner raised the price before it was pressed
        items['i']['value'] = '500'
        self.assertEqual(await self.confirm(), '⌛ Hat changed since this was asked, so nothing was bought. Ask again for its current price.')
        gtrade.buyUnderLock.assert_not_awaited()

    async def test_buying_twice_does_not_take_the_request_back_and_cancelling_is_its_own_ask(self):
        gtrade = Mock(buyUnderLock = AsyncMock(), tradeLock = asyncio.Lock())
        self.cogs['GTrade'] = gtrade
        self.patch(agent_abilities.gtrade_queries, 'getAllUserItems', MagicMock(return_value = {'i': {'name': 'Hat', 'value': '7'}}))
        self.patch(agent_abilities.gcoin_queries, 'getUserBalance', MagicMock(return_value = Decimal('10')))
        pending = {}
        self.patch(agent_abilities.gtrade_queries, 'getPendingTradeTransaction', MagicMock(side_effect = lambda guildId, kind, item, *who: pending.get(kind)))
        removed = self.patch(agent_abilities.gtrade_queries, 'removePendingTradeTransaction', MagicMock())
        buy = {'item': 'hat', 'owner': 'sam', 'action': 'buy'}
        cancel = {'item': 'hat', 'owner': 'sam', 'action': 'cancel'}
        self.assertEqual(await self.use(agent_client.TOOL_BUY_ITEM, {'item': 'hat', 'owner': 'sam', 'action': 'maybe'}), ('Say whether to buy it or cancel their request to.', True))
        self.assertEqual(await self.use(agent_client.TOOL_BUY_ITEM, cancel), ('They have no request to buy Hat from Sam waiting.', True))
        # asked already by the time it's pressed, so GTrade's buy, which would take it back, isn't run
        await self.use(agent_client.TOOL_BUY_ITEM, buy)
        pending['buy'] = ('t1', {})
        self.assertEqual(await self.confirm(), 'Hat is already asked for, and Sam has yet to answer.')
        gtrade.buyUnderLock.assert_not_awaited()
        self.assertEqual(await self.use(agent_client.TOOL_BUY_ITEM, buy), ('They already asked to buy Hat from Sam, who has yet to answer. Nothing was posted. Tell them.', True))
        # once Sam offers it, or lists it, buying takes that up, so it goes ahead
        pending['market'] = ('t2', {})
        await self.use(agent_client.TOOL_BUY_ITEM, buy)
        self.assertEqual(await self.confirm(), '✅ Done.')
        self.assertEqual(gtrade.buyUnderLock.await_args.args[1:], (self.sender, 'Hat', self.sam))
        self.assertEqual(await self.use(agent_client.TOOL_BUY_ITEM, cancel), ('They have no request to buy Hat from Sam waiting.', True))
        del pending['market']
        await self.use(agent_client.TOOL_BUY_ITEM, cancel)
        self.assertEqual(self.posted()[0].title, '🚫 Cancel your request to buy Hat from Sam?')
        self.assertEqual(await self.confirm(), "🚫 You're no longer asking to buy Hat from Sam.")
        removed.assert_called_once_with(10, 't1')
        await self.use(agent_client.TOOL_BUY_ITEM, cancel)
        del pending['buy']
        self.assertEqual(await self.confirm(), '⌛ Your request to buy Hat is no longer waiting.')

    async def test_destroying_an_item(self):
        gtrade = Mock(tradeLock = AsyncMock(), destroyUnderLock = AsyncMock(side_effect = lambda author, name: f"💥 <@1>, you destroyed your item '{name}' for 7.00 GCoin."))
        gtrade.tradeLock.__aenter__ = AsyncMock()
        gtrade.tradeLock.__aexit__ = AsyncMock(return_value = False)
        self.cogs['GTrade'] = gtrade
        owned = {'i': {'name': 'Hat', 'value': '7'}, 'j': {'name': 'Sword', 'value': '3.5'}}
        self.patch(agent_abilities.gtrade_queries, 'getAllUserItems', MagicMock(side_effect = lambda userId: owned))
        await self.use(agent_client.TOOL_DESTROY_ITEM, {'items': ['hat']})
        self.assertEqual(self.posted()[0].title, '💥 Destroy Hat for good?')
        self.assertEqual(await self.confirm(), "💥 <@1>, you destroyed your item 'Hat' for 7.00 GCoin.")
        gtrade.destroyUnderLock.assert_awaited_once_with(self.sender, 'Hat')
        # several, under one confirm listing each and its worth, each its own result
        await self.use(agent_client.TOOL_DESTROY_ITEM, {'items': ['hat', 'sword', 'Hat']})
        embed = self.posted()[0]
        self.assertEqual((embed.title, embed.description), ('💥 Destroy 2 items for good?', "• Hat · 7.00 GCoin\n• Sword · 3.50 GCoin\n\nEach pays back its worth. This can't be undone."))
        self.assertEqual(await self.confirm(), "💥 <@1>, you destroyed your item 'Hat' for 7.00 GCoin.\n💥 <@1>, you destroyed your item 'Sword' for 7.00 GCoin.")
        self.assertEqual(await self.use(agent_client.TOOL_DESTROY_ITEM, {'items': ['shoe']}), ('Chris has no item called that. Their items: Hat, Sword.', True))
        self.assertEqual(await self.use(agent_client.TOOL_DESTROY_ITEM, {'items': None}), ('Chris has no item called that. Their items: Hat, Sword.', True))
        # an empty list is all of theirs, with no lookup first
        await self.use(agent_client.TOOL_DESTROY_ITEM, {'items': []})
        self.assertEqual(self.posted()[0].title, '💥 Destroy 2 items for good?')
        owned.clear()
        self.assertEqual(await self.use(agent_client.TOOL_DESTROY_ITEM, {'items': []}), ('Chris has no items.', True))

    async def test_answering_a_trade(self):
        gtrade = Mock(tradeLock = AsyncMock(), sellUnderLock = AsyncMock(), buyUnderLock = AsyncMock())
        gtrade.tradeLock.__aenter__ = AsyncMock()
        gtrade.tradeLock.__aexit__ = AsyncMock(return_value = False)
        self.cogs['GTrade'] = gtrade
        offers = {'t1': {'trxType': 'buy', 'sellerId': '1', 'buyerId': '2', 'item': {'name': 'Hat', 'value': '7'}},
                  't2': {'trxType': 'sell', 'sellerId': '2', 'buyerId': '1', 'item': {'name': 'Sword', 'value': '3'}}}
        self.patch(agent_abilities.gtrade_queries, 'getAllServerPendingTradeTransactions', MagicMock(return_value = offers))
        still = self.patch(agent_abilities.gtrade_queries, 'getPendingTradeTransactionWithId', MagicMock(return_value = {}))
        removed = self.patch(agent_abilities.gtrade_queries, 'removePendingTradeTransaction', MagicMock())
        await self.use(agent_client.TOOL_ANSWER_TRADE, {'action': 'accept', 'item': 'hat', 'other': 'sam'})
        self.assertEqual(self.posted()[0].title, "✅ Accept Sam's offer to buy Hat for 7.00 GCoin?")
        self.assertEqual(await self.confirm(), '✅ Done.')
        self.assertEqual(gtrade.sellUnderLock.await_args.args[1:], (self.sender, 'Hat', self.sam))
        await self.use(agent_client.TOOL_ANSWER_TRADE, {'action': 'accept', 'item': 'sword', 'other': 'sam'})
        self.assertEqual(self.posted()[0].title, "✅ Accept Sam's offer to sell you Sword for 3.00 GCoin?")
        await self.confirm()
        self.assertEqual(gtrade.buyUnderLock.await_args.args[1:], (self.sender, 'Sword', self.sam))
        await self.use(agent_client.TOOL_ANSWER_TRADE, {'action': 'decline', 'item': 'hat', 'other': 'sam'})
        self.assertEqual(await self.confirm(), "❌ Declined Sam's offer for Hat.")
        removed.assert_called_once_with(10, 't1')
        # with no item named, every offer Sam made them, on one card
        await self.use(agent_client.TOOL_ANSWER_TRADE, {'action': 'decline', 'item': '', 'other': 'sam'})
        embed = self.posted()[0]
        self.assertEqual((embed.title, embed.description), ("❌ Decline Sam's 2 offers?", '• To buy Hat · 7.00 GCoin\n• To sell you Sword · 3.00 GCoin\n\nGTrade checks each again when you press.'))
        still.side_effect = lambda guildId, trxId: None if trxId == 't1' else {}
        self.assertEqual(await self.confirm(), "⌛ The offer for Hat is no longer available.\n❌ Declined Sam's offer for Sword.")
        still.side_effect = None
        removed.reset_mock()
        await self.use(agent_client.TOOL_ANSWER_TRADE, {'action': 'decline', 'item': 'hat', 'other': 'sam'})
        self.assertEqual(await self.confirm(), "❌ Declined Sam's offer for Hat.")
        await self.use(agent_client.TOOL_ANSWER_TRADE, {'action': 'decline', 'item': 'hat', 'other': 'sam'})
        still.return_value = None
        self.assertEqual(await self.confirm(), '⌛ This trade is no longer available.')
        # accepting someone who has left since
        still.return_value = {}
        await self.use(agent_client.TOOL_ANSWER_TRADE, {'action': 'accept', 'item': 'hat', 'other': 'sam'})
        self.guild.get_member.side_effect = lambda userId: {1: self.sender}.get(userId)
        self.assertEqual(await self.confirm(), '⌛ This trade is no longer available, as the other person left.')
        self.guild.get_member.side_effect = lambda userId: {1: self.sender, 2: self.sam}.get(userId)
        self.assertEqual(await self.use(agent_client.TOOL_ANSWER_TRADE, {'action': 'accept', 'item': 'boots', 'other': 'sam'}), ('Sam has no offer like that open to them.', True))
        self.assertEqual(await self.use(agent_client.TOOL_ANSWER_TRADE, {'action': 'accept', 'item': None, 'other': ''}), ('Say whether to accept or decline, and whose offer.', True))

    async def test_reminding_a_role(self):
        self.patch(reminders_cog, 'utcNow', MagicMock(return_value = NOW))
        zone = self.patch(agent_abilities.reminders_queries, 'getTimezone', MagicMock(return_value = None))
        reminders = reminders_cog.Reminders(Mock())
        saved = self.patch(reminders, 'saveReminder', AsyncMock(return_value = 'r1'))
        self.cogs['Reminders'] = reminders
        values = {'when': 'tomorrow 9am', 'what': 'raid', 'repeat': 'weekly', 'role': 'raid team'}
        self.assertTrue((await self.use(agent_client.TOOL_REMIND_ROLE, values, isAdmin = True))[0].startswith("They haven't set a time zone."))
        zone.return_value = 'America/New_York'
        await self.use(agent_client.TOOL_REMIND_ROLE, values, isAdmin = True)
        embed, _ = self.posted()
        self.assertEqual(embed.title, '🔔 Remind Raid Team?')
        self.assertIn('pinging <@&30> here:\n> raid', embed.description)
        self.assertTrue((await self.confirm()).startswith('🔔 Reminder set for <t:'))
        self.assertEqual(saved.await_args.args[1]['target'], '30')
        await self.use(agent_client.TOOL_REMIND_ROLE, dict(values, role = '@everyone', repeat = 'hourly'), isAdmin = True)
        self.assertEqual(self.posted()[0].title, '🔔 Remind everyone?')
        saved.side_effect = reminders_cog.ReminderProblem('you have 25 reminders here already.')
        self.assertEqual(await self.confirm(), '❌ you have 25 reminders here already.')
        self.assertEqual(await self.use(agent_client.TOOL_REMIND_ROLE, dict(values, role = 'nobody'), isAdmin = True), ('There is no role by that name here.', True))
        self.assertTrue((await self.use(agent_client.TOOL_REMIND_ROLE, dict(values, when = None), isAdmin = True))[0].startswith('Nothing was set:'))
        # an admin can't lend themselves GBot's own Mention Everyone
        self.msg.channel.permissions_for = Mock(return_value = Mock(mention_everyone = False))
        self.raids.mentionable = False
        self.guild.get_role = Mock(side_effect = lambda roleId: self.raids if roleId == 30 else None)
        self.assertTrue((await self.use(agent_client.TOOL_REMIND_ROLE, values, isAdmin = True))[0].startswith("They can't mention that role here themselves"))

    async def test_a_role_reminder_is_read_again_when_its_confirmed(self):
        # "in 2 minutes" is from the press, and the ping one they can still make
        now = self.patch(reminders_cog, 'utcNow', MagicMock(return_value = NOW))
        self.patch(agent_abilities.reminders_queries, 'getTimezone', MagicMock(return_value = 'America/New_York'))
        reminders = reminders_cog.Reminders(Mock())
        saved = self.patch(reminders, 'saveReminder', AsyncMock(return_value = 'r1'))
        self.cogs['Reminders'] = reminders
        await self.use(agent_client.TOOL_REMIND_ROLE, {'when': 'in 2 minutes', 'what': 'raid', 'repeat': 'once', 'days': [], 'role': 'raid team'}, isAdmin = True)
        # a timer's card says it counts from the press, rather than a time that goes stale
        self.assertTrue(self.posted()[0].description.startswith('2 minutes after you press Confirm, once, pinging'))
        now.return_value = NOW + timedelta(minutes = 5)
        await self.confirm()
        self.assertEqual(saved.await_args.args[1]['nextAt'], (NOW + timedelta(minutes = 7)).isoformat())
        # a role deleted between the ask and the press
        getRole = self.guild.get_role
        await self.use(agent_client.TOOL_REMIND_ROLE, {'when': 'in 2 minutes', 'what': 'raid', 'repeat': 'once', 'days': [], 'role': 'raid team'}, isAdmin = True)
        self.guild.get_role = Mock(return_value = None)
        self.assertEqual(await self.confirm(), '❌ That role is gone, so nothing was set.')
        self.guild.get_role = getRole
        await self.use(agent_client.TOOL_REMIND_ROLE, {'when': 'in 2 minutes', 'what': 'raid', 'repeat': 'once', 'days': [], 'role': 'raid team'}, isAdmin = True)
        self.msg.channel.permissions_for = Mock(return_value = Mock(mention_everyone = False))
        self.raids.mentionable = False
        self.guild.get_role = Mock(side_effect = lambda roleId: self.raids if roleId == 30 else None)
        self.assertTrue((await self.confirm()).startswith("❌ You can't mention that role here yourself"))
        saved.assert_awaited_once()

    async def test_a_press_runs_only_what_the_card_showed(self):
        # one added while the card was being edited isn't run by a press on what was shown before
        ran = []
        first = AsyncMock(side_effect = lambda interaction: ran.append('first') or 'first done')
        second = AsyncMock(side_effect = lambda interaction: ran.append('second') or 'second done')
        cards = []
        self.cogs['Config'] = Mock()
        self.patch(agent_abilities.config_queries, 'getServerValue', MagicMock(return_value = False))
        await self.abilities.confirmCard(self.msg, 'One?', 'a', 'Config', None, first)
        view = agent_abilities.CONFIRM.get()
        pressedEarly = self.press()
        async def editWhilePressed(**kwargs):
            await view.confirmed(pressedEarly)
        view.message = Mock(edit = AsyncMock(side_effect = editWhilePressed))
        await self.abilities.confirmCard(self.msg, 'Two?', 'b', 'Config', None, second)
        self.assertEqual(ran, ['first'])
        self.assertEqual(pressedEarly.edit_original_message.await_args.kwargs['content'], 'first done')

    async def test_one_confirmed_action_failing_leaves_the_rest_their_turn(self):
        view = agent_abilities.AgentConfirm(1, None, False, AsyncMock(side_effect = RuntimeError('down')), '⚙️ Turn off Music?', 'a', 'Config')
        view.add('↩️ Delete this Hype match?', 'b', None, False, AsyncMock(return_value = '↩️ Deleted.'), 'Hype')
        view.shown = 2
        pressed = self.press()
        await view.confirmed(pressed)
        self.assertEqual(pressed.edit_original_message.await_args.kwargs['content'], "❌ ⚙️ Turn off Music didn't work. Try its command instead.\n↩️ Deleted.")

    async def test_setting_config(self):
        setValue = self.patch(agent_abilities.config_queries, 'setServerValue', MagicMock())
        self.patch(agent_abilities.server_setup, 'roleProblem', Mock(return_value = None))
        await self.use(agent_client.TOOL_SET_CONFIG, {'setting': 'storms_channel', 'value': '#General'}, isAdmin = True)
        self.assertEqual(self.posted()[0].title, '⚙️ Set the Storms channel?')
        self.assertEqual(await self.confirm(), '⚙️ The Storms channel is now <#20>.')
        setValue.assert_called_once_with(10, 'channel_storms', '20')
        await self.use(agent_client.TOOL_SET_CONFIG, {'setting': 'who_dis_role', 'value': '<@&30>'}, isAdmin = True)
        await self.confirm()
        setValue.assert_called_with(10, 'role_who_dis', '30')
        await self.use(agent_client.TOOL_SET_CONFIG, {'setting': 'prefix', 'value': ' ! '}, isAdmin = True)
        self.assertEqual(await self.confirm(), '⚙️ The prefix is now !.')
        # what's gone, or can't be given out any more, by the time it's pressed
        setValue.reset_mock()
        getChannel, getRole = self.guild.get_channel, self.guild.get_role
        await self.use(agent_client.TOOL_SET_CONFIG, {'setting': 'storms_channel', 'value': '#General'}, isAdmin = True)
        self.guild.get_channel = Mock(return_value = None)
        self.assertEqual(await self.confirm(), '❌ That channel is gone, so nothing was changed.')
        await self.use(agent_client.TOOL_SET_CONFIG, {'setting': 'who_dis_role', 'value': '<@&30>'}, isAdmin = True)
        self.guild.get_role = Mock(return_value = None)
        self.assertEqual(await self.confirm(), '❌ That role is gone, so nothing was changed.')
        await self.use(agent_client.TOOL_SET_CONFIG, {'setting': 'who_dis_role', 'value': '<@&30>'}, isAdmin = True)
        self.guild.get_role = Mock(return_value = self.raids)
        agent_abilities.server_setup.roleProblem.return_value = "GBot can't give out <@&30>."
        self.assertEqual(await self.confirm(), "❌ GBot can't give out <@&30>.")
        agent_abilities.server_setup.roleProblem.return_value = None
        setValue.assert_not_called()
        self.guild.get_channel, self.guild.get_role = getChannel, getRole
        # the admin role: never @everyone or a bot's own, which /config's picker can't choose either
        self.raids.is_default = Mock(return_value = False)
        self.raids.managed = False
        await self.use(agent_client.TOOL_SET_CONFIG, {'setting': 'admin_role', 'value': 'raid team'}, isAdmin = True)
        await self.confirm()
        setValue.assert_called_with(10, 'role_admin', '30')
        for default, managed in ((True, False), (False, True)):
            self.raids.is_default.return_value, self.raids.managed = default, managed
            self.assertEqual(await self.use(agent_client.TOOL_SET_CONFIG, {'setting': 'admin_role', 'value': 'raid team'}, isAdmin = True),
                             ("The admin role can't be @everyone or a bot's own role. Pick a role that only admins have.", True))
        agent_abilities.server_setup.roleProblem.return_value = "GBot can't give out <@&30>."
        cases = [({'setting': 'who_dis_role', 'value': 'raid team'}, "GBot can't give out <@&30>."),
                 ({'setting': 'admin_role', 'value': 'nobody'}, 'There is no role by that name here.'),
                 ({'setting': 'admin_channel', 'value': 'nowhere'}, 'There is no text channel by that name here.'),
                 ({'setting': 'prefix', 'value': 'x' * 11}, 'A prefix is 1 to 10 characters.'),
                 ({'setting': 'key', 'value': None}, 'That is not a setting the agent can change.')]
        for toolInput, expected in cases:
            with self.subTest(expected = expected):
                self.assertEqual(await self.use(agent_client.TOOL_SET_CONFIG, toolInput, isAdmin = True), (expected, True))

    async def test_reporting_is_private(self):
        config = Mock(captureMessages = AsyncMock(return_value = ['m']), fileReport = AsyncMock(return_value = True))
        self.cogs['Config'] = config
        self.msg.channel.send.return_value = Mock(delete = AsyncMock())
        # nobody can be reported unless the sender's own message names them
        self.assertEqual(await self.use(agent_client.TOOL_REPORT, {'user': 'sam', 'what': ''}), ('Their message does not name who to report, so nothing was done.', True))
        self.msg.delete.assert_not_awaited()
        self.msg.content = 'gbot report Sam for spamming'
        cards = []
        self.assertEqual(await self.use(agent_client.TOOL_REPORT, {'user': 'sam', 'what': ' spam '}, cards = cards), (agent_abilities.OPENS, False))
        self.msg.delete.assert_awaited_once()
        # the one-liner names nobody, not even the reporter, whose message just went
        content, view = self.opened()
        self.assertEqual(content, '🔒 A private card. Press 🔒 Open to see it privately.')
        self.assertNotIn('Sam', content)
        self.assertNotIn('Chris', content)
        self.assertEqual(cards, [self.msg.channel.send.return_value])
        # only the sender can open it
        other = await self.openAs(view, self.sam)
        # without saying whose it is, so pressing it doesn't tell Sam either
        self.assertEqual(other.send.await_args.kwargs['embed'].description, "Sorry <@2>, this isn't yours to open.")
        pressed = await self.openAs(view)
        # their message, already hidden, isn't deleted again when the one-liner is tidied
        self.assertIsNone(view.command)
        self.msg.delete.assert_awaited_once()
        kwargs = pressed.send.await_args.kwargs
        self.assertEqual((kwargs['embed'].title, kwargs['ephemeral']), ('🚩 Report Sam to the admins of My Server?', True))
        confirm = kwargs['view']
        confirmPress = self.press()
        await confirm.confirmed(confirmPress)
        self.recheck.assert_awaited_with(confirmPress, feature = None, admin = False)
        config.fileReport.assert_awaited_once_with(self.guild, self.sender, self.sam, '<#20>', ['m'], 'spam')
        self.assertEqual(confirmPress.edit_original_message.await_args.kwargs['content'], '🚩 Sent to the admins. Thanks for letting them know.')
        config.fileReport.return_value = False
        await self.use(agent_client.TOOL_REPORT, {'user': 'sam', 'what': None})
        pressed = await self.openAs(self.opened()[1])
        confirmPress = self.press()
        await pressed.send.await_args.kwargs['view'].confirmed(confirmPress)
        self.assertTrue(confirmPress.edit_original_message.await_args.kwargs['content'].startswith("❌ This report wasn't sent"))
        self.assertEqual(await self.use(agent_client.TOOL_REPORT, {'user': '', 'what': ''}), ("They can't report themselves.", True))
        self.assertEqual(await self.use(agent_client.TOOL_REPORT, {'user': 'nobody', 'what': ''}), (agent_abilities.NOBODY, True))
        self.sender.send.assert_not_awaited()

    async def test_agent_settings(self):
        agent = Mock(commonSettings = AsyncMock(), commonInstructions = AsyncMock(), keyForm = Mock(return_value = 'the key form'))
        self.cogs['Agent'] = agent
        # what /agent would refuse is said before any card goes up
        agent.settingProblem = Mock(return_value = 'tone is not a setting.')
        self.assertEqual(await self.use(agent_client.TOOL_AGENT_SETTING, {'setting': 'tone', 'value': 'friendly', 'channel': ''}, isAdmin = True), ('Nothing was posted: tone is not a setting.', True))
        agent.settingProblem.assert_called_once_with('tone', 'friendly', None)
        self.msg.reply.assert_not_awaited()
        agent.settingProblem.return_value = None
        await self.use(agent_client.TOOL_AGENT_SETTING, {'setting': ' Abilities ', 'value': 'all', 'channel': 'general'}, isAdmin = True)
        self.assertEqual(self.posted()[0].title, '🤖 Set my abilities to all in #general?')
        self.assertEqual(await self.confirm(), '🤖 Done.')
        self.assertEqual(agent.commonSettings.await_args.args[1:], ('abilities', 'all', self.general))
        await self.use(agent_client.TOOL_AGENT_SETTING, {'setting': 'instructions', 'value': 'Be brief.', 'channel': ''}, isAdmin = True)
        self.assertEqual(self.posted()[0].description, '> Be brief.')
        await self.confirm()
        self.assertEqual(agent.commonInstructions.await_args.args[1:], ('Be brief.', None))
        await self.use(agent_client.TOOL_AGENT_SETTING, {'setting': 'instructions', 'value': '', 'channel': ''}, isAdmin = True)
        self.assertEqual(self.posted()[0].description, 'Clear them.')
        # a key never through chat: its card opens the private form
        self.assertEqual(await self.use(agent_client.TOOL_AGENT_SETTING, {'setting': 'key', 'value': 'sk-ant-oops', 'channel': ''}, isAdmin = True), (agent_abilities.CONFIRM_POSTED, False))
        embed, view = self.posted()
        self.assertNotIn('sk-ant', embed.title + embed.description)
        pressed = self.press()
        await view.children[0].callback(pressed)
        pressed.response.send_modal.assert_awaited_once_with('the key form')
        self.assertEqual(await self.use(agent_client.TOOL_AGENT_SETTING, {'setting': None, 'value': '', 'channel': 'nowhere'}, isAdmin = True), ('There is no text channel by that name here.', True))

    def test_the_agents_key_form(self):
        from GBotDiscord.src.agent.agent_cog import Agent, AgentKeyModal
        with patch('nextcord.ui.Modal.__init__', return_value = None), patch('nextcord.ui.Modal.add_item'):
            form = Agent.keyForm(Mock())
        self.assertIsInstance(form, AgentKeyModal)

    async def test_opening_a_card(self):
        music = Mock(musicStates = {'10': {'voiceClient': None}}, postCard = AsyncMock())
        self.cogs['Music'] = music
        self.assertEqual(await self.use(agent_client.TOOL_OPEN_CARD, {'feature': 'Music'}), ('Nothing is playing, so there is no music card. Tell them.', True))
        music.musicStates['10']['voiceClient'] = Mock()
        cards = []
        self.assertFalse((await self.use(agent_client.TOOL_OPEN_CARD, {'feature': 'Music'}, cards = cards))[1])
        music.postCard.assert_awaited_once_with('10', self.msg.channel, moveDown = True)
        self.assertEqual(cards, [self.msg])
        await self.use(agent_client.TOOL_OPEN_CARD, {'feature': 'Music'})
        # GCoin and Storms are public, as their prefix commands are
        wallet = Mock(commonWallet = AsyncMock())
        storms = Mock(commonStatus = AsyncMock())
        self.cogs.update({'GCoin': wallet, 'Storms': storms})
        async def show(context, author, user):
            await context.send(embed = 'the wallet')
        wallet.commonWallet.side_effect = show
        cards = []
        self.assertEqual(await self.use(agent_client.TOOL_OPEN_CARD, {'feature': 'GCoin'}, cards = cards), ('Posted it. It is your whole reply, so nothing you write is shown.', False))
        context, author, user = wallet.commonWallet.await_args.args
        self.assertEqual((context.guild, context.channel, context.author, context.message, author, user), (self.guild, self.msg.channel, self.sender, self.msg, self.sender, None))
        self.msg.channel.send.assert_awaited_once_with(None, embed = 'the wallet')
        self.assertEqual(cards, [self.msg.channel.send.return_value])
        await self.use(agent_client.TOOL_OPEN_CARD, {'feature': 'Storms'})
        self.assertIs(storms.commonStatus.await_args.args[0].guild, self.guild)
        # any other card is private, so it's a 🔒 Open button for the sender
        reminders = Mock(openCard = AsyncMock())
        self.cogs['Reminders'] = reminders
        self.msg.channel.send.return_value = Mock(delete = AsyncMock())
        cards = []
        self.assertEqual(await self.use(agent_client.TOOL_OPEN_CARD, {'feature': 'Reminders'}, cards = cards), (agent_abilities.OPENS, False))
        content, view = self.opened()
        self.assertEqual(content, '🔔 Reminders for **Chris**. Press 🔒 Open to see it privately.')
        self.assertEqual((view.ownerId, view.feature, view.admin), (1, 'toggle_reminders', False))
        self.assertEqual(cards, [self.msg.channel.send.return_value])
        pressed = await self.openAs(view)
        reminders.openCard.assert_awaited_once_with(pressed, self.sender)
        # the button and the message asking for it go once it's opened
        self.msg.delete.assert_awaited_once()
        await self.use(agent_client.TOOL_OPEN_CARD, {'feature': 'Reminders'})
        self.assertEqual(await self.use(agent_client.TOOL_OPEN_CARD, {'feature': 'Nope'}), ('There is no feature by that name.', True))
        # a feature that's off shows nothing, as its command would refuse
        agent_abilities.config_queries.getServerValue.return_value = False
        sends = self.msg.channel.send.await_count
        for feature in ('GCoin', 'Storms', 'Music', 'Reminders'):
            with self.subTest(feature = feature):
                self.assertEqual(await self.use(agent_client.TOOL_OPEN_CARD, {'feature': feature}), (f'{feature} is turned off in this server.', True))
        self.assertEqual(self.msg.channel.send.await_count, sends)

    async def test_patreon(self):
        GBotPropertiesManager.PATREON_GUILD_ID = 99
        GBotPropertiesManager.PATRON_ROLE_ID = 5
        self.assertEqual(await self.use(agent_client.TOOL_PATREON, {'server_id': '123'}), ('That only works in the GBot Patreon server.', True))
        self.guild.id = 99
        hasRole = self.patch(agent_abilities.utils, 'isUserAssignedRole', Mock(return_value = False))
        self.assertEqual(await self.use(agent_client.TOOL_PATREON, {'server_id': '123'}), ('Only GBot patrons can do that.', True))
        hasRole.return_value = True
        self.assertEqual(await self.use(agent_client.TOOL_PATREON, {'server_id': 'abc'}), ('Give the server ID, a long number.', True))
        patreon = Mock(commonPatreon = AsyncMock())
        self.cogs['Patreon'] = patreon
        await self.use(agent_client.TOOL_PATREON, {'server_id': ' 123 '})
        self.assertEqual(self.posted()[0].title, '⭐ Enable GBot in server 123?')
        self.assertEqual(await self.confirm(), '⭐ Done.')
        self.assertEqual(patreon.commonPatreon.await_args.args[1:], (1, 123))
