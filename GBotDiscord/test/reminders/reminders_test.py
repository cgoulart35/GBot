#region IMPORTS
import copy
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from zoneinfo import ZoneInfo

import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context

from GBotDiscord.src.reminders import reminders_cog, reminders_queries, when
from GBotDiscord.src.reminders.reminders_cog import Reminders, RemindersCard, ReminderProblem, SetReply
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.test import isolation
#endregion

NEW_YORK = ZoneInfo('America/New_York')
# Monday 9 November 2026, 8:14 PM in New York
NOW = datetime(2026, 11, 10, 1, 14, tzinfo = timezone.utc)
SERVER = 10
# the real clock, before setUp patches it
REAL_UTC_NOW = reminders_cog.utcNow
CHANNEL = 20
ME = 1
OTHER = 2

def iso(moment):
    return moment.astimezone(timezone.utc).isoformat()

def inNewYork(day, hour, minute = 0):
    return datetime(2026, 11, day, hour, minute, tzinfo = NEW_YORK)

class FakeDatabase:
    # reminders and time zones in memory, read as copies, as the real database returns
    def __init__(self):
        self.reminders = {}
        self.zones = {}
        self.count = 0

    def install(self, test):
        for name, function in (('getAllReminders', lambda: copy.deepcopy(self.reminders) or None),
                               ('getServerReminders', lambda serverId: copy.deepcopy(self.reminders.get(str(serverId))) or None),
                               ('getReminder', lambda serverId, reminderId: copy.deepcopy(self.reminders.get(str(serverId), {}).get(reminderId))),
                               ('addReminder', self.add),
                               ('updateReminder', self.update),
                               ('removeReminder', lambda serverId, reminderId: self.reminders.get(str(serverId), {}).pop(reminderId, None)),
                               ('getTimezone', lambda userId: self.zones.get(str(userId))),
                               ('setTimezone', lambda userId, zone: self.zones.__setitem__(str(userId), zone))):
            started = patch.object(reminders_queries, name, MagicMock(side_effect = function))
            started.start()
            test.addCleanup(started.stop)

    def add(self, serverId, reminder):
        self.count += 1
        reminderId = f'r{self.count}'
        self.reminders.setdefault(str(serverId), {})[reminderId] = copy.deepcopy(reminder)
        return reminderId

    def update(self, serverId, reminderId, changes):
        reminder = self.reminders[str(serverId)][reminderId]
        for key, value in changes.items():
            if value is None:
                reminder.pop(key, None)
            else:
                reminder[key] = value

    def mine(self, **fields):
        reminder = dict({'userId': str(ME), 'channelId': str(CHANNEL), 'text': 'call the dentist', 'nextAt': iso(inNewYork(10, 9)), 'repeat': 'once', 'where': 'here'}, **fields)
        return self.add(SERVER, reminder)

class TestReminders(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\n\nStarting reminders unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted reminders unit tests.\n')

    def setUp(self):
        isolation.restorePagination()
        GBotPropertiesManager.USER_RESPONSE_TIMEOUT_SECONDS = 300
        GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS = []
        self.db = FakeDatabase()
        self.db.install(self)
        self.db.zones[str(ME)] = 'America/New_York'
        for target, name, value in ((reminders_cog, 'utcNow', MagicMock(return_value = NOW)),
                                    (reminders_cog.predicates, 'recheck', AsyncMock()),
                                    (reminders_cog.utils, 'isUserAdminOrOwner', MagicMock(return_value = False))):
            started = patch.object(target, name, value)
            started.start()
            self.addCleanup(started.stop)
        self.isAdmin = reminders_cog.utils.isUserAdminOrOwner
        self.client = commands.Bot()
        self.cog = Reminders(self.client)
        self.channel = Mock(id = CHANNEL, mention = f'<#{CHANNEL}>', send = AsyncMock())
        self.channel.name = 'general'
        self.role = Mock(id = 30, mention = '<@&30>')
        self.role.is_default = Mock(return_value = False)
        self.everyoneRole = Mock(id = SERVER, mention = '@everyone')
        self.everyoneRole.is_default = Mock(return_value = True)
        self.member = Mock(id = ME, mention = f'<@{ME}>', send = AsyncMock())
        self.member.display_name = 'Chris'
        self.guild = Mock(id = SERVER)
        self.guild.name = 'My Server'
        self.guild.get_channel_or_thread = Mock(side_effect = lambda channelId: self.channel if channelId == CHANNEL else None)
        self.guild.get_role = Mock(side_effect = lambda roleId: self.role if roleId == 30 else None)
        self.guild.get_member = Mock(side_effect = lambda userId: self.member if userId == ME else None)

    # helpers

    def slash(self, user = None):
        interaction = Mock(spec = nextcord.Interaction)
        interaction.guild = self.guild
        interaction.channel = self.channel
        interaction.user = user or self.member
        interaction.send = AsyncMock()
        interaction.response = Mock(is_done = Mock(return_value = False), defer = AsyncMock(), send_modal = AsyncMock())
        interaction.edit_original_message = AsyncMock()
        return interaction

    def prefix(self):
        ctx = Mock(spec = Context)
        ctx.guild = self.guild
        ctx.channel = self.channel
        ctx.author = self.member
        ctx.message = Mock()
        ctx.send = AsyncMock()
        return ctx

    async def card(self, admin = False):
        self.isAdmin.return_value = admin
        context = self.slash()
        await self.cog.openCard(context, self.member)
        kwargs = context.send.await_args.kwargs
        return kwargs['view'], kwargs['embed']

    def labelled(self, view, label):
        return next(item for item in view.children if getattr(item, 'label', None) == label)

    def selects(self, view):
        return [item for item in view.children if isinstance(item, nextcord.ui.StringSelect)]

    async def pick(self, select, value):
        select._selected_values = [value]
        interaction = self.slash()
        await select.callback(interaction)
        return interaction

    async def press(self, view, label):
        interaction = self.slash()
        await self.labelled(view, label).callback(interaction)
        return interaction

    def shown(self, interaction):
        return interaction.edit_original_message.await_args.kwargs['embed']

    def notice(self, embed):
        return embed.fields[-1].value

    # the command

    async def test_with_no_fields_it_opens_the_card(self):
        interaction = self.slash()
        await self.cog.remindSlash(interaction, None, None, None, None, None)
        kwargs = interaction.send.await_args.kwargs
        self.assertTrue(kwargs['ephemeral'])
        self.assertIsInstance(kwargs['view'], RemindersCard)
        ctx = self.prefix()
        await self.cog.remind(self.cog, ctx)
        self.assertIn('Press 🔒 Open', ctx.send.await_args.kwargs['content'])

    async def test_the_fast_path_sets_it_and_says_when(self):
        interaction = self.slash()
        await self.cog.commonRemind(interaction, self.member, 'tomorrow 9am', 'call the dentist', None, None, None)
        saved = self.db.reminders[str(SERVER)]['r1']
        self.assertEqual(saved, {'userId': str(ME), 'channelId': str(CHANNEL), 'text': 'call the dentist', 'nextAt': iso(inNewYork(10, 9)), 'repeat': 'once', 'where': 'here'})
        kwargs = interaction.send.await_args.kwargs
        stamp = int(inNewYork(10, 9).timestamp())
        self.assertEqual(kwargs['content'], f'🔔 Reminder set for **<t:{stamp}:F>** (<t:{stamp}:R>), here.')
        self.assertTrue(kwargs['ephemeral'])
        self.assertIsInstance(kwargs['view'], SetReply)

    async def test_the_fast_path_with_repeat_where_and_a_role(self):
        self.isAdmin.return_value = True
        ctx = self.prefix()
        await self.cog.remind(self.cog, ctx, 'Thursday 8pm', 'raid night', 'WEEKLY', 'dm', self.role)
        saved = self.db.reminders[str(SERVER)]['r1']
        self.assertEqual((saved['repeat'], saved['where'], saved['target']), ('weekly', 'dm', '30'))
        self.assertIn('by DM, repeating every Thursday at 8:00 PM.', ctx.send.await_args.kwargs['content'])
        await self.cog.commonRemind(self.prefix(), self.member, 'in 2 hours', 'everyone up', None, None, self.everyoneRole)
        self.assertEqual(self.db.reminders[str(SERVER)]['r2']['target'], 'everyone')

    async def test_the_fast_path_refuses_what_it_cannot_set(self):
        cases = [
            (('tomorrow', None, None, None, None), 'a reminder needs both `when` and `what`'),
            (('tomorrow', 'x', 'hourly', None, None), '`repeat` can be once, daily, weekdays, weekly, monthly, yearly or days like `mon,wed,fri`'),
            (('tomorrow', 'x', None, 'there', None), '`repeat` can be once, daily, weekdays, weekly, monthly, yearly or days like `mon,wed,fri`, and `where` here or dm'),
            (('tomorrow', 'x', None, None, self.role), 'only admins can remind a role'),
            (('soonish', 'x', None, None, None), 'I couldn\'t read "soonish" as a time. Try "in 2 hours"'),
            (('today 9am', 'x', None, None, None), '"today 9am" has already gone'),
            (('Dec 25 2037', 'x', None, None, None), 'at most 10 years ahead'),
            (('tomorrow', 'x' * 501, None, None, None), 'at most 500 characters'),
        ]
        for args, expected in cases:
            with self.subTest(expected = expected):
                interaction = self.slash()
                await self.cog.commonRemind(interaction, self.member, *args)
                embed = interaction.send.await_args.kwargs['embed']
                self.assertIn(expected, embed.description)
                self.assertTrue(embed.description.startswith('Sorry <@1>,'))
        self.assertEqual(self.db.reminders, {})

    def test_a_ping_follows_discords_own_rule_for_whoever_sets_it(self):
        allowed = Mock(mention_everyone = True)
        denied = Mock(mention_everyone = False)
        self.channel.permissions_for = Mock(return_value = denied)
        self.role.mentionable = True
        self.assertTrue(reminders_cog.mayPing(self.member, self.channel, None, self.guild))
        self.assertTrue(reminders_cog.mayPing(self.member, self.channel, '30', self.guild))
        self.assertFalse(reminders_cog.mayPing(self.member, self.channel, 'everyone', self.guild))
        self.assertFalse(reminders_cog.mayPing(self.member, self.channel, '99', self.guild))
        self.role.mentionable = False
        self.assertFalse(reminders_cog.mayPing(self.member, self.channel, '30', self.guild))
        self.channel.permissions_for.return_value = allowed
        self.assertTrue(reminders_cog.mayPing(self.member, self.channel, 'everyone', self.guild))
        self.assertTrue(reminders_cog.mayPing(self.member, None, None, self.guild))
        self.assertFalse(reminders_cog.mayPing(self.member, None, 'everyone', self.guild))

    def deniedPings(self):
        self.channel.permissions_for = Mock(return_value = Mock(mention_everyone = False))
        self.role.mentionable = False

    async def test_an_admin_cannot_lend_themselves_gbots_ping(self):
        self.isAdmin.return_value = True
        self.deniedPings()
        interaction = self.slash()
        await self.cog.commonRemind(interaction, self.member, 'tomorrow', 'x', None, None, self.role)
        self.assertIn("you can't mention that role here yourself", interaction.send.await_args.kwargs['embed'].description)
        self.assertEqual(self.db.reminders, {})
        view, _ = await self.card(admin = True)
        await view.submitted(self.slash(), ['tomorrow', 'raid'])
        await self.press(view, 'Everyone')
        shown = await self.press(view, 'Set it')
        self.assertTrue(self.notice(self.shown(shown)).startswith("❌ You can't mention that role here yourself"))
        self.assertEqual(self.db.reminders, {})

    async def test_a_ping_its_setter_can_no_longer_make_reminds_only_them(self):
        self.deliverable()
        self.db.mine(nextAt = iso(NOW), target = '30')
        self.deniedPings()
        await self.run_loop()
        self.assertEqual(self.channel.send.await_args.kwargs['content'], '<@1>')

    async def test_too_far_ahead_however_it_is_written(self):
        interaction = self.slash()
        await self.cog.commonRemind(interaction, self.member, 'in 99999999999 days', 'x', None, None, None)
        self.assertIn('at most 10 years ahead', interaction.send.await_args.kwargs['embed'].description)

    async def test_ten_years_ahead_are_calendar_years(self):
        await self.cog.commonRemind(self.slash(), self.member, 'in 10 years', 'x', None, None, None)
        self.assertEqual(len(self.db.reminders[str(SERVER)]), 1)
        interaction = self.slash()
        await self.cog.commonRemind(interaction, self.member, 'in 10 years and 1 minute', 'x', None, None, None)
        self.assertIn('at most 10 years ahead', interaction.send.await_args.kwargs['embed'].description)

    async def test_the_fast_path_stops_at_the_limit(self):
        for _ in range(Reminders.MAX_PER_PERSON):
            self.db.mine()
        # a sent one-off doesn't count
        self.db.mine(delivered = iso(NOW))
        self.db.reminders[str(SERVER)]['other'] = {'userId': str(OTHER), 'channelId': str(CHANNEL), 'text': 't', 'nextAt': iso(NOW), 'repeat': 'once', 'where': 'here'}
        interaction = self.slash()
        await self.cog.commonRemind(interaction, self.member, 'tomorrow', 'one more', None, None, None)
        self.assertIn('you have 25 reminders here already', interaction.send.await_args.kwargs['embed'].description)

    async def test_with_no_time_zone_the_fast_path_asks_for_one_first(self):
        del self.db.zones[str(ME)]
        interaction = self.slash()
        await self.cog.commonRemind(interaction, self.member, 'tomorrow 9am', 'call the dentist', 'daily', None, None)
        card = interaction.send.await_args.kwargs['view']
        self.assertEqual(card.screen, reminders_cog.ZONE)
        embed = interaction.send.await_args.kwargs['embed']
        self.assertEqual(embed.title, '🌍 Your time zone')
        self.assertIn('Pick your time zone first', self.notice(embed))
        # picking one carries on to the draft, with what was asked for
        shown = await self.pick(self.selects(card)[0], 'America/Denver')
        self.assertEqual(card.screen, reminders_cog.DRAFT)
        self.assertEqual(card.draft['repeat'], 'daily')
        self.assertEqual(card.draft['nextAt'], iso(datetime(2026, 11, 10, 9, tzinfo = ZoneInfo('America/Denver'))))
        self.assertEqual(self.db.zones[str(ME)], 'America/Denver')
        self.assertEqual(self.shown(shown).title, '🔔 New reminder')

    async def test_undo_and_my_reminders(self):
        interaction = self.slash()
        await self.cog.commonRemind(interaction, self.member, 'tomorrow 9am', 'call the dentist', None, None, None)
        reply = interaction.send.await_args.kwargs['view']
        opened = await self.press(reply, 'My reminders')
        self.assertIsInstance(opened.send.await_args.kwargs['view'], RemindersCard)
        undone = await self.press(reply, 'Undo')
        self.assertEqual(self.db.reminders[str(SERVER)], {})
        self.assertEqual(undone.edit_original_message.await_args.kwargs, {'content': '↩️ Reminder removed.', 'view': None})

    # the card

    async def test_a_snooze_is_marked_in_the_list(self):
        # a repeat's sits beside the repeat with the same words, so it says it's a snooze
        self.db.mine(text = 'stretch', repeat = 'daily', nextAt = iso(inNewYork(11, 9)))
        self.db.mine(text = 'stretch', snoozeOf = 'r1', nextAt = iso(inNewYork(10, 9)))
        view, embed = await self.card()
        self.assertEqual([field.value for field in embed.fields], ['💤 Snoozed · stretch · here in <#20>', 'stretch · here in <#20>'])
        self.assertEqual([option.label for option in self.selects(view)[0].options], ['1. 💤 Tue, Nov 10 at 9:00 AM', '2. Every day at 9:00 AM'])
        # a one-off snoozed is flagged so
        self.db.mine(delivered = iso(NOW))
        await self.cog.on_interaction(self.delivered('snooze10', reminderId = 'r3'))
        self.assertTrue(reminders_cog.isSnoozed(self.db.reminders[str(SERVER)]['r3']))

    async def test_the_card_lists_yours_soonest_first(self):
        view, embed = await self.card()
        self.assertEqual(embed.title, '🔔 Your reminders')
        self.assertIn('No reminders here yet', embed.description)
        self.assertIn('Times in **Eastern Time** (8:14 PM now).', embed.description)
        self.assertEqual(self.selects(view), [])
        self.db.mine(text = 'later', nextAt = iso(inNewYork(12, 20)), repeat = 'weekly', where = 'dm')
        self.db.mine(text = 'sooner')
        self.db.mine(text = 'role ping', nextAt = iso(inNewYork(11, 8)), target = '30')
        self.db.mine(text = 'everyone ping', nextAt = iso(inNewYork(11, 9)), target = 'everyone', channelId = '999')
        self.db.reminders[str(SERVER)]['theirs'] = {'userId': str(OTHER), 'channelId': str(CHANNEL), 'text': 'not mine', 'nextAt': iso(inNewYork(10, 8)), 'repeat': 'once', 'where': 'here'}
        view, embed = await self.card()
        self.assertEqual(embed.description.split('\n')[0], '4 of 25, soonest first.')
        self.assertEqual([(field.name, field.value) for field in embed.fields], [
            ('1. Tue, Nov 10 at 9:00 AM', 'sooner · here in <#20>'),
            ('2. Wed, Nov 11 at 8:00 AM', 'role ping · here in <#20> · pings <@&30>'),
            ('3. Wed, Nov 11 at 9:00 AM', 'everyone ping · in a deleted channel · pings @everyone'),
            ('4. Every Thursday at 8:00 PM', 'later · DM'),
        ])
        self.assertEqual([option.label for option in self.selects(view)[0].options][0], '1. Tue, Nov 10 at 9:00 AM')
        self.assertTrue(self.labelled(view, 'Delete').disabled)
        self.assertNotIn("Server's", [getattr(item, 'label', None) for item in view.children])

    async def test_the_card_without_a_time_zone_says_to_pick_one(self):
        del self.db.zones[str(ME)]
        _, embed = await self.card()
        self.assertIn('Pick your time zone with 🌍 Time zone', embed.description)

    async def test_picking_and_deleting(self):
        self.db.mine()
        view, _ = await self.card()
        await self.pick(self.selects(view)[0], 'r1')
        self.assertFalse(self.labelled(view, 'Delete').disabled)
        shown = await self.press(view, 'Delete')
        self.assertEqual(self.db.reminders[str(SERVER)], {})
        self.assertEqual(self.notice(self.shown(shown)), '🗑️ Deleted "call the dentist".')
        # nothing picked any more: Delete does nothing
        await self.press(view, 'Delete')

    async def test_admins_see_everyones_and_can_delete_them(self):
        self.db.reminders[str(SERVER)] = {'theirs': {'userId': str(OTHER), 'channelId': str(CHANNEL), 'text': 'a role ping', 'nextAt': iso(inNewYork(10, 8)), 'repeat': 'once', 'where': 'here', 'target': '99'}}
        view, _ = await self.card(admin = True)
        shown = await self.press(view, "Server's")
        embed = self.shown(shown)
        self.assertEqual(embed.title, "🔔 This server's reminders")
        self.assertEqual(embed.fields[0].value, 'a role ping · here in <#20> · pings a deleted role · by <@2>')
        reminders_cog.predicates.recheck.assert_awaited_with(shown, feature = 'toggle_reminders', admin = True)
        await self.pick(self.selects(view)[0], 'theirs')
        await self.press(view, 'Delete')
        self.assertEqual(self.db.reminders[str(SERVER)], {})
        back = await self.press(view, 'Back')
        self.assertEqual(self.shown(back).title, '🔔 Your reminders')
        self.db.reminders[str(SERVER)] = {}
        await self.press(view, "Server's")
        self.assertEqual(view.screen, reminders_cog.SERVER)

    async def test_an_empty_server_list(self):
        view, _ = await self.card(admin = True)
        shown = await self.press(view, "Server's")
        self.assertEqual(self.shown(shown).description, 'Nobody has a reminder here.\nTimes in **Eastern Time** (8:14 PM now).')

    async def test_new_opens_a_form_then_a_draft(self):
        view, _ = await self.card()
        interaction = await self.press(view, 'New')
        form = interaction.response.send_modal.await_args.args[0]
        self.assertEqual([box.label for box in form.children], ['When', 'What'])
        submit = self.slash()
        await form.onSubmit(submit, ['Thursday 8pm', 'raid night'])
        embed = self.shown(submit)
        stamp = int(inNewYork(12, 20).timestamp())
        self.assertEqual([(field.name, field.value) for field in embed.fields], [
            ('When', f'<t:{stamp}:F> (<t:{stamp}:R>)'), ('What', 'raid night'), ('Repeats', 'Once'), ('Where', 'here in <#20>')])
        repeats, where = self.selects(view)
        self.assertEqual([option.label for option in repeats.options], ['Once', 'Every day at 8:00 PM', 'Every weekday at 8:00 PM', 'Every Thursday at 8:00 PM', 'Every month on the 12th at 8:00 PM', 'Every year on Nov 12 at 8:00 PM', 'On days you choose…'])
        self.assertEqual([option.label for option in where.options], ['Here in #general', 'By DM'])
        await self.pick(repeats, 'weekly')
        await self.pick(where, 'dm')
        shown = await self.press(view, 'Set it')
        self.assertEqual(self.db.reminders[str(SERVER)]['r1']['repeat'], 'weekly')
        self.assertEqual(self.db.reminders[str(SERVER)]['r1']['where'], 'dm')
        self.assertNotIn('whenText', self.db.reminders[str(SERVER)]['r1'])
        self.assertEqual(self.notice(self.shown(shown)), f'🔔 Reminder set for <t:{stamp}:F>.')
        self.assertEqual(view.screen, reminders_cog.LIST)

    async def test_a_draft_that_cannot_be_read_or_saved(self):
        view, _ = await self.card()
        submit = self.slash()
        await view.submitted(submit, ['soonish', 'x'])
        self.assertEqual(view.screen, reminders_cog.LIST)
        self.assertIn('❌ I couldn\'t read "soonish"', self.notice(self.shown(submit)))
        await view.submitted(self.slash(), ['tomorrow', 'x'])
        # ✏️ Edit keeps the choices made, and a bad edit stays on the draft
        await self.pick(self.selects(view)[0], 'daily')
        edit = await self.press(view, 'Edit')
        form = edit.response.send_modal.await_args.args[0]
        self.assertEqual([box.default_value for box in form.children], ['tomorrow', 'x'])
        await view.submitted(self.slash(), ['soonish', 'x'])
        self.assertEqual(view.screen, reminders_cog.DRAFT)
        await view.submitted(self.slash(), ['in 2 hours', 'y'])
        self.assertEqual((view.draft['repeat'], view.draft['text']), ('daily', 'y'))
        for _ in range(Reminders.MAX_PER_PERSON):
            self.db.mine()
        shown = await self.press(view, 'Set it')
        self.assertIn('❌ you have 25 reminders here already', self.notice(self.shown(shown)))
        self.assertEqual(view.screen, reminders_cog.DRAFT)

    async def test_admins_pick_who_it_pings(self):
        view, _ = await self.card(admin = True)
        await view.submitted(self.slash(), ['tomorrow', 'raid'])
        embed = await view.render()
        self.assertEqual(embed.fields[-1].value, 'You')
        self.assertTrue(self.labelled(view, 'Just me').disabled)
        picker = next(item for item in view.children if isinstance(item, nextcord.ui.RoleSelect))
        await view.setRole(self.slash(), self.role)
        self.assertEqual(view.draft['target'], '30')
        self.assertEqual((await view.render()).fields[-1].value, '<@&30>')
        await view.setRole(self.slash(), self.everyoneRole)
        self.assertEqual(view.draft['target'], 'everyone')
        await self.press(view, 'Just me')
        self.assertNotIn('target', view.draft)
        await self.press(view, 'Everyone')
        self.assertEqual(view.draft['target'], 'everyone')
        self.assertTrue(self.labelled(view, 'Everyone').disabled)
        saved = await self.press(view, 'Set it')
        reminders_cog.predicates.recheck.assert_awaited_with(saved, feature = 'toggle_reminders', admin = True)
        self.assertIsNotNone(picker)

    async def test_the_time_zone_screen(self):
        view, _ = await self.card()
        shown = await self.press(view, 'Time zone')
        embed = self.shown(shown)
        self.assertEqual(embed.title, '🌍 Your time zone')
        self.assertTrue(embed.description.startswith('**Eastern Time** · 8:14 PM now.'))
        options = self.selects(view)[0].options
        self.assertEqual(len(options), len(when.ZONES))
        self.assertIn('8:14 PM · Eastern Time', [option.label for option in options])
        self.assertIn('6:14 PM · Mountain Time', [option.label for option in options])
        picked = await self.pick(self.selects(view)[0], 'Europe/London')
        self.assertEqual(self.notice(self.shown(picked)), '🌍 Time zone set to **UK and Ireland**.')
        self.assertEqual(view.screen, reminders_cog.LIST)

    async def test_any_other_zone_can_be_typed(self):
        view, _ = await self.card()
        await self.press(view, 'Time zone')
        other = await self.press(view, 'Other zone')
        form = other.response.send_modal.await_args.args[0]
        bad = self.slash()
        await form.onSubmit(bad, ['Mars/Olympus'])
        self.assertIn('isn\'t a time zone name', self.notice(self.shown(bad)))
        good = self.slash()
        await form.onSubmit(good, ['asia/kathmandu'])
        self.assertEqual(self.db.zones[str(ME)], 'Asia/Kathmandu')
        self.assertEqual(self.notice(self.shown(good)), '🌍 Time zone set to **Asia/Kathmandu**.')

    async def test_a_first_time_zone_says_it_is_not_set(self):
        del self.db.zones[str(ME)]
        view, _ = await self.card()
        shown = await self.press(view, 'Time zone')
        self.assertTrue(self.shown(shown).description.startswith('Not set yet.'))

    async def test_how_it_works_and_back(self):
        view, _ = await self.card()
        shown = await self.press(view, 'How it works')
        self.assertTrue(self.notice(self.shown(shown)).startswith('`/remind` on its own lists your reminders here'))
        await self.press(view, 'Time zone')
        await self.press(view, 'Back')
        self.assertEqual(view.screen, reminders_cog.LIST)

    # time zones

    def test_changing_zone_moves_your_reminders_with_you(self):
        self.db.mine()
        self.db.mine(delivered = iso(NOW))
        self.db.reminders['77'] = {'x': {'userId': str(ME), 'channelId': '5', 'text': 'elsewhere', 'nextAt': iso(inNewYork(11, 9)), 'repeat': 'daily', 'where': 'here'},
                                   'y': {'userId': str(OTHER), 'channelId': '5', 'text': 'not mine', 'nextAt': iso(inNewYork(11, 9)), 'repeat': 'once', 'where': 'here'}}
        denver = ZoneInfo('America/Denver')
        reminders_cog.changeZone(ME, 'America/Denver')
        self.assertEqual(self.db.reminders[str(SERVER)]['r1']['nextAt'], iso(datetime(2026, 11, 10, 9, tzinfo = denver)))
        self.assertEqual(self.db.reminders[str(SERVER)]['r2']['nextAt'], iso(inNewYork(10, 9)))
        self.assertEqual(self.db.reminders['77']['x']['nextAt'], iso(datetime(2026, 11, 11, 9, tzinfo = denver)))
        self.assertEqual(self.db.reminders['77']['y']['nextAt'], iso(inNewYork(11, 9)))
        # the same zone again, or a first one, moves nothing
        reminders_queries.updateReminder.reset_mock()
        reminders_cog.changeZone(ME, 'America/Denver')
        reminders_cog.changeZone(OTHER, 'America/Denver')
        reminders_queries.updateReminder.assert_not_called()

    # delivery

    def run_loop(self):
        return self.cog.reminder_loop.coro(self.cog)

    def deliverable(self, toggle = True, active = True):
        self.client._connection._guilds = {SERVER: self.guild}
        for target, name, value in ((reminders_cog.config_queries, 'getServerValue', MagicMock(return_value = toggle)),
                                    (reminders_cog.access, 'isActive', MagicMock(return_value = active))):
            started = patch.object(target, name, value)
            started.start()
            self.addCleanup(started.stop)

    async def test_a_due_one_off_is_sent_once_with_snooze(self):
        self.deliverable()
        self.db.mine(nextAt = iso(NOW - timedelta(seconds = 20)))
        self.db.mine(text = 'not yet', nextAt = iso(NOW + timedelta(minutes = 5)))
        self.db.reminders['555'] = {'z': {'userId': str(ME), 'channelId': '5', 'text': "another bot's server", 'nextAt': iso(NOW), 'repeat': 'once', 'where': 'here'}}
        await self.run_loop()
        self.channel.send.assert_awaited_once()
        kwargs = self.channel.send.await_args.kwargs
        self.assertEqual(kwargs['content'], '<@1>')
        self.assertEqual(kwargs['allowed_mentions'].users, [self.member])
        self.assertFalse(kwargs['allowed_mentions'].everyone)
        self.assertEqual((kwargs['embed'].title, kwargs['embed'].description), ('🔔 Reminder', 'call the dentist'))
        self.assertEqual(kwargs['embed'].fields, [])
        self.assertEqual([(button.label, button.custom_id) for button in kwargs['view'].children], [
            ('10 min', 'remind:snooze10:10:r1'), ('1 hour', 'remind:snooze60:10:r1'), ('Tomorrow', 'remind:snoozetomorrow:10:r1'),
            ('Done', 'remind:done:10:r1:1'), (nextcord.utils.MISSING, 'remind:dismiss:10:r1:1')])
        self.assertEqual(self.db.reminders[str(SERVER)]['r1']['delivered'], iso(NOW))
        await self.run_loop()
        self.channel.send.assert_awaited_once()

    async def test_a_repeat_moves_on_and_one_missed_arrives_late(self):
        self.deliverable()
        self.db.mine(nextAt = iso(inNewYork(8, 9)), repeat = 'daily', target = '30')
        await self.run_loop()
        kwargs = self.channel.send.await_args.kwargs
        self.assertEqual(kwargs['content'], '<@&30>')
        self.assertEqual(kwargs['allowed_mentions'].roles, [self.role])
        self.assertEqual(kwargs['embed'].colour, reminders_cog.presentation.WARNING_COLOR)
        nextStamp = int(inNewYork(10, 9).timestamp())
        dueStamp = int(inNewYork(8, 9).timestamp())
        self.assertEqual(kwargs['embed'].fields[0].value, f'From <@1>\nEvery day at 9:00 AM · next <t:{nextStamp}:R>\nLate: this was due <t:{dueStamp}:f>, while GBot was offline.')
        # a role's is for others too, so it can be marked done but not deleted
        self.assertEqual([button.label for button in kwargs['view'].children], ['10 min', 'Skip next', 'Stop repeating', 'Done'])
        self.assertEqual(self.db.reminders[str(SERVER)]['r1']['nextAt'], iso(inNewYork(10, 9)))

    async def test_everyone_and_a_deleted_role(self):
        self.deliverable()
        self.db.mine(nextAt = iso(NOW), target = 'everyone')
        self.db.mine(nextAt = iso(NOW), target = '99')
        await self.run_loop()
        everyone, deletedRole = [call.kwargs for call in self.channel.send.await_args_list]
        self.assertEqual(everyone['content'], '@everyone')
        self.assertTrue(everyone['allowed_mentions'].everyone)
        self.assertEqual(deletedRole['content'], '<@1>')

    async def test_by_dm_or_the_channel_if_dms_are_closed(self):
        self.deliverable()
        self.db.mine(nextAt = iso(NOW), where = 'dm')
        await self.run_loop()
        embed = self.member.send.await_args.kwargs['embed']
        self.assertEqual(embed.fields[0].value, 'From **My Server**')
        self.channel.send.assert_not_awaited()
        self.member.send = AsyncMock(side_effect = nextcord.HTTPException(Mock(status = 403), 'closed'))
        self.db.mine(nextAt = iso(NOW), where = 'dm')
        await self.run_loop()
        self.assertTrue(self.channel.send.await_args.kwargs['embed'].description.endswith("-# Couldn't DM you, so it's here."))

    async def test_nowhere_to_go_someone_who_left_and_old_sent_ones(self):
        self.deliverable()
        self.cog.logger = MagicMock()
        self.db.mine(nextAt = iso(NOW), channelId = '999')
        self.db.mine(nextAt = iso(NOW), userId = str(OTHER))
        self.db.mine(delivered = iso(NOW - timedelta(days = 2)))
        self.db.mine(delivered = iso(NOW - timedelta(hours = 2)))
        await self.run_loop()
        self.cog.logger.info.assert_called_once_with('Reminder r1 in server 10 had nowhere to go.')
        self.assertEqual(sorted(self.db.reminders[str(SERVER)]), ['r1', 'r4'])

    async def test_nothing_is_sent_while_turned_off_or_not_subscribed(self):
        for toggle, active in ((False, True), (None, True), (True, False)):
            with self.subTest(toggle = toggle, active = active):
                self.deliverable(toggle, active)
                self.db.mine(nextAt = iso(NOW))
                await self.run_loop()
                self.channel.send.assert_not_awaited()

    async def test_one_failure_stays_its_own_and_the_loop_survives(self):
        self.deliverable()
        self.cog.logger = MagicMock()
        self.db.mine(nextAt = iso(NOW))
        self.channel.send = AsyncMock(side_effect = Exception('boom'))
        await self.run_loop()
        self.cog.logger.error.assert_called_once_with('Reminder r1 in server 10 failed: boom')
        reminders_queries.getAllReminders.side_effect = Exception('down')
        await self.run_loop()
        self.cog.logger.error.assert_called_with('Error in Reminders.reminder_loop(): down')

    # on time: a look once a minute, and a wake-up at its second for each due before the next

    def clockMovesTo(self, moment):
        # asyncio.sleep, standing in: the wall clock is where it slept until
        async def sleep(seconds):
            reminders_cog.utcNow.return_value = moment
        started = patch.object(reminders_cog.asyncio, 'sleep', AsyncMock(side_effect = sleep))
        self.addCleanup(started.stop)
        return started.start()

    async def wakeUps(self):
        for task in list(self.cog.waking.values()):
            await task

    async def test_one_due_before_the_next_look_wakes_on_its_second(self):
        self.deliverable()
        soon = NOW + timedelta(seconds = 30)
        self.db.mine(nextAt = iso(soon))
        self.db.mine(text = 'later', nextAt = iso(NOW + timedelta(minutes = 5)))
        sleep = self.clockMovesTo(soon)
        await self.run_loop()
        self.channel.send.assert_not_awaited()
        self.assertEqual(list(self.cog.waking), [(str(SERVER), 'r1', iso(soon))])
        await self.wakeUps()
        sleep.assert_awaited_once_with(30.0)
        self.channel.send.assert_awaited_once()
        kwargs = self.channel.send.await_args.kwargs
        self.assertEqual((kwargs['embed'].description, kwargs['embed'].colour), ('call the dentist', reminders_cog.presentation.BRAND_COLOR))
        self.assertEqual(self.cog.waking, {})
        # the one five minutes off is left to a later look
        self.assertNotIn('delivered', self.db.reminders[str(SERVER)]['r2'])

    async def test_a_wake_up_and_a_look_send_it_once(self):
        # both can find it due, and only the first to claim it sends it
        self.deliverable()
        self.db.mine(nextAt = iso(NOW))
        self.cog.wakeFor(self.guild, 'r1', iso(NOW))
        self.cog.wakeFor(self.guild, 'r1', iso(NOW))
        self.assertEqual(len(self.cog.waking), 1)
        await self.run_loop()
        await self.wakeUps()
        self.channel.send.assert_awaited_once()
        # a look working from a copy read before the send claims nothing
        stale = dict(self.db.reminders[str(SERVER)]['r1'], nextAt = iso(NOW))
        stale.pop('delivered')
        await self.cog.fire(self.guild, 'r1', stale, NOW)
        self.channel.send.assert_awaited_once()

    async def test_a_wake_up_for_one_changed_since_sends_nothing(self):
        self.deliverable()
        soon = iso(NOW + timedelta(seconds = 10))
        self.clockMovesTo(NOW + timedelta(seconds = 10))
        self.db.mine(nextAt = soon)
        self.db.mine(nextAt = soon)
        self.db.mine(nextAt = soon)
        for reminderId in ('r1', 'r2', 'r3', 'gone'):
            self.cog.wakeFor(self.guild, reminderId, soon)
        # snoozed, deleted and sent since
        self.db.update(SERVER, 'r1', {'nextAt': iso(NOW + timedelta(minutes = 10))})
        self.db.reminders[str(SERVER)].pop('r2')
        self.db.update(SERVER, 'r3', {'delivered': iso(NOW)})
        await self.wakeUps()
        self.channel.send.assert_not_awaited()

    async def test_a_wake_up_waits_while_reminders_are_off_and_its_failure_is_logged(self):
        self.deliverable(toggle = False)
        self.db.mine(nextAt = iso(NOW))
        self.cog.wakeFor(self.guild, 'r1', iso(NOW))
        await self.wakeUps()
        self.channel.send.assert_not_awaited()
        self.assertNotIn('delivered', self.db.reminders[str(SERVER)]['r1'])
        self.cog.logger = MagicMock()
        reminders_queries.getReminder.side_effect = Exception('down')
        self.cog.wakeFor(self.guild, 'r1', iso(NOW))
        await self.wakeUps()
        self.cog.logger.error.assert_called_once_with('Reminder r1 in server 10 failed: down')
        self.assertEqual(self.cog.waking, {})

    async def test_one_set_due_soon_wakes_at_once(self):
        # "in 30 seconds" can't wait for the next look
        with patch.object(self.client, 'get_guild', Mock(return_value = self.guild)):
            await self.cog.commonRemind(self.slash(), self.member, 'in 30 seconds', 'stretch', None, None, None)
            self.assertEqual(list(self.cog.waking), [(str(SERVER), 'r1', iso(NOW + timedelta(seconds = 30)))])
            await self.cog.commonRemind(self.slash(), self.member, 'in 2 minutes', 'later', None, None, None)
            self.assertEqual(len(self.cog.waking), 1)
        for task in self.cog.waking.values():
            task.cancel()
        self.cog.waking.clear()
        # GBot no longer in the server: nothing to wake for
        await self.cog.commonRemind(self.slash(), self.member, 'in 30 seconds', 'stretch', None, None, None)
        self.assertEqual(self.cog.waking, {})

    async def test_a_time_named_for_the_minute_it_is_goes_off_now(self):
        # "at 8:14pm" said at 8:14:40, sent at once rather than tomorrow
        self.deliverable()
        reminders_cog.utcNow.return_value = NOW + timedelta(seconds = 40)
        ctx = self.prefix()
        with patch.object(self.client, 'get_guild', Mock(return_value = self.guild)):
            await self.cog.commonRemind(ctx, self.member, 'at 8:14pm', 'clean', None, None, None)
        self.assertEqual(ctx.send.await_args.kwargs['content'], '🔔 Reminder set for now, going off right away, here.')
        await self.wakeUps()
        self.assertEqual(self.channel.send.await_args.kwargs['embed'].description, 'clean')
        self.assertEqual(self.channel.send.await_args.kwargs['embed'].colour, reminders_cog.presentation.BRAND_COLOR)

    async def test_a_timer_starts_a_repeat_when_it_said(self):
        # "in 30 seconds" on a Tuesday, then Mondays at that minute
        ctx = self.prefix()
        await self.cog.commonRemind(ctx, self.member, 'in 30 seconds', 'trash', 'mon', None, None)
        saved = self.db.reminders[str(SERVER)]['r1']
        self.assertEqual((saved['repeat'], saved['nextAt']), ('days:0', iso(NOW + timedelta(seconds = 30))))
        self.assertIn('repeating every Mon at 8:14 PM.', ctx.send.await_args.kwargs['content'])

    async def test_one_a_look_finds_a_little_late_is_not_called_late(self):
        # moved between looks, say by a time zone change: late only once GBot was away
        self.deliverable()
        self.db.mine(nextAt = iso(NOW - timedelta(seconds = 90)))
        await self.run_loop()
        self.assertEqual(self.channel.send.await_args.kwargs['embed'].colour, reminders_cog.presentation.BRAND_COLOR)

    def test_unloading_cancels_the_wake_ups(self):
        task = Mock()
        self.cog.waking[('10', 'r1', 'x')] = task
        self.cog.cog_unload()
        task.cancel.assert_called_once()

    async def test_on_ready_starts_the_loop_once(self):
        self.cog.reminder_loop = MagicMock()
        await self.cog.on_ready()
        self.cog.reminder_loop.start.assert_called_once()
        self.cog.reminder_loop.start.side_effect = RuntimeError()
        self.cog.logger = MagicMock()
        await self.cog.on_ready()
        self.cog.logger.info.assert_called_once_with('reminder_loop task is already launched and is not completed.')

    # the delivered reminder's buttons

    def delivered(self, action, reminderId = 'r1', user = None, inDm = False, setter = None):
        # Done's and ✖️'s ids end with whoever set it
        interaction = self.slash(user)
        interaction.type = nextcord.InteractionType.component
        interaction.data = {'custom_id': f'remind:{action}:{SERVER}:{reminderId}' + (f':{setter}' if setter else '')}
        interaction.guild = None if inDm else self.guild
        # the buttons it was sent with, as Discord gives them back
        sent = self.cog.deliveredButtons(SERVER, reminderId, {'userId': str(setter or ME), 'repeat': 'once', 'where': 'here'})
        interaction.message = Mock(embeds = [reminders_cog.presentation.brandEmbed(title = '🔔 Reminder', description = 'call the dentist')], components = [Mock(children = sent.children)])
        return interaction

    async def test_done_marks_it_and_the_cross_deletes_it(self):
        # either way a sent one-off can't be snoozed after, and a repeat carries on
        self.db.mine(delivered = iso(NOW))
        done = self.delivered('done', setter = 1)
        await self.cog.on_interaction(done)
        self.assertNotIn('r1', self.db.reminders[str(SERVER)])
        kwargs = done.edit_original_message.await_args.kwargs
        self.assertEqual(kwargs['embed'].fields[-1].value, '✅ Done.')
        # its ✖️ stays, so it can still be deleted
        self.assertEqual([item.custom_id for item in kwargs['view'].children], ['remind:dismiss:10:r1:1'])
        # and one sent without it, a role's, is left with nothing to press
        roles = self.delivered('done', setter = 1)
        roles.message.components = [Mock(children = self.cog.deliveredButtons(SERVER, 'r1', {'userId': '1', 'repeat': 'once', 'where': 'here', 'target': '30'}).children)]
        await self.cog.on_interaction(roles)
        self.assertIsNone(roles.edit_original_message.await_args.kwargs['view'])
        self.db.mine(repeat = 'daily')
        dismiss = self.delivered('dismiss', reminderId = 'r2', setter = 1)
        dismiss.message.delete = AsyncMock()
        await self.cog.on_interaction(dismiss)
        dismiss.message.delete.assert_awaited_once()
        self.assertIn('r2', self.db.reminders[str(SERVER)])
        dismiss.edit_original_message.assert_not_awaited()
        # one GBot can't delete is marked done instead, and one whose record has gone still works
        failing = self.delivered('dismiss', reminderId = 'gone', setter = 1)
        failing.message.delete = AsyncMock(side_effect = nextcord.HTTPException(Mock(status = 403), 'no'))
        await self.cog.on_interaction(failing)
        self.assertEqual(failing.edit_original_message.await_args.kwargs['embed'].fields[-1].value, '✅ Done.')
        # only whoever set it, even once its record has gone
        other = self.delivered('done', reminderId = 'gone', user = Mock(id = OTHER), setter = 1)
        await self.cog.on_interaction(other)
        other.send.assert_awaited_once_with('Only <@1> can use these buttons.', ephemeral = True)
        other.edit_original_message.assert_not_awaited()

    async def test_done_cancels_a_snooze_and_the_cross_leaves_it(self):
        # ✖️ clears the message, as dismissing a notification does; ✅ Done says no more
        self.db.mine()
        snoozed = self.delivered('snooze10')
        await self.cog.on_interaction(snoozed)
        dismiss = self.delivered('dismiss', setter = 1)
        dismiss.message.delete = AsyncMock()
        await self.cog.on_interaction(dismiss)
        self.assertEqual(self.db.reminders[str(SERVER)]['r1']['nextAt'], iso(NOW + timedelta(minutes = 10)))
        done = self.delivered('done', setter = 1)
        await self.cog.on_interaction(done)
        self.assertNotIn('r1', self.db.reminders[str(SERVER)])
        self.assertEqual(done.edit_original_message.await_args.kwargs['embed'].fields[-1].value, '✅ Done, and its snooze cancelled.')
        # a repeat's: Done cancels its snooze and the repeat carries on
        self.db.mine(repeat = 'daily')
        self.db.mine(repeat = 'once', snoozeOf = 'r2', nextAt = iso(NOW + timedelta(minutes = 10)))
        self.db.mine(repeat = 'once', snoozeOf = 'r2', delivered = iso(NOW))
        done = self.delivered('done', reminderId = 'r2', setter = 1)
        await self.cog.on_interaction(done)
        self.assertEqual(sorted(self.db.reminders[str(SERVER)]), ['r2', 'r4'])
        self.assertEqual(done.edit_original_message.await_args.kwargs['embed'].fields[-1].value, '✅ Done, and its snooze cancelled.')
        # with nothing snoozed, it's only done
        done = self.delivered('done', reminderId = 'r2', setter = 1)
        await self.cog.on_interaction(done)
        self.assertEqual(done.edit_original_message.await_args.kwargs['embed'].fields[-1].value, '✅ Done.')
        self.assertIn('r2', self.db.reminders[str(SERVER)])

    async def test_a_dm_reminder_can_always_be_deleted(self):
        self.assertEqual(self.cog.deliveredButtons(SERVER, 'r1', {'userId': '1', 'where': 'dm', 'target': 'everyone'}).children[-1].custom_id, 'remind:dismiss:10:r1:1')

    async def test_typed_repeats_and_their_days(self):
        await self.cog.commonRemind(self.prefix(), self.member, 'Saturday 9am', 'standup', 'weekdays', None, None)
        saved = self.db.reminders[str(SERVER)]['r1']
        # a weekday repeat begins on a weekday
        self.assertEqual((saved['repeat'], saved['nextAt']), ('weekdays', iso(inNewYork(16, 9))))
        ctx = self.prefix()
        await self.cog.commonRemind(ctx, self.member, 'tomorrow 6pm', 'gym', 'mon,wed,fri', None, None)
        self.assertEqual(self.db.reminders[str(SERVER)]['r2']['repeat'], 'days:0,2,4')
        self.assertIn('repeating every Mon, Wed and Fri at 6:00 PM.', ctx.send.await_args.kwargs['content'])
        await self.cog.commonRemind(self.prefix(), self.member, 'Dec 31 9am', 'pay rent', 'monthly', None, None)
        self.assertEqual(self.db.reminders[str(SERVER)]['r3']['repeat'], 'monthly:31')

    async def test_the_card_picks_days(self):
        view, _ = await self.card()
        submit = self.slash()
        await view.submitted(submit, ['Thursday 8pm', 'gym'])
        repeats = self.selects(view)[0]
        await self.pick(repeats, 'days')
        # starts with its own day, and a picker for the rest
        self.assertEqual(view.draft['repeat'], 'days:3')
        picker = self.selects(view)[1]
        self.assertEqual(([option.label for option in picker.options], [option.default for option in picker.options], picker.max_values),
                         (['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'], [False, False, False, True, False, False, False], 7))
        picker._selected_values = ['0', '4']
        await picker.callback(self.slash())
        # the first time moves to the first of its days
        self.assertEqual((view.draft['repeat'], view.draft['nextAt']), ('days:0,4', iso(inNewYork(13, 20))))
        # switching reads what was typed again: Thursday the 12th
        await self.pick(self.selects(view)[0], 'monthly')
        self.assertEqual(view.draft['repeat'], 'monthly:12')
        self.assertEqual(len(self.selects(view)), 2)
        # a draft whose time has gone since says so, and stays as it was
        view.draft['whenText'] = 'today 1am'
        await self.pick(self.selects(view)[0], 'yearly')
        self.assertEqual(view.draft['repeat'], 'monthly:12')

    async def test_snoozing_a_one_off(self):
        self.db.mine(delivered = iso(NOW))
        for action, minutes in (('snooze10', 10), ('snooze60', 60)):
            with self.subTest(action = action):
                interaction = self.delivered(action)
                await self.cog.on_interaction(interaction)
                saved = self.db.reminders[str(SERVER)]['r1']
                self.assertEqual(saved['nextAt'], iso(NOW + timedelta(minutes = minutes)))
                self.assertNotIn('delivered', saved)
                kwargs = interaction.edit_original_message.await_args.kwargs
                self.assertEqual(kwargs['embed'].fields[-1].value, f'💤 Snoozed until <t:{int((NOW + timedelta(minutes = minutes)).timestamp())}:t>.')
                # snoozed, its snooze buttons go, as the snooze arrives as its own message; Done can cancel it
                self.assertEqual([item.custom_id for item in kwargs['view'].children], ['remind:done:10:r1:1', 'remind:dismiss:10:r1:1'])
        # went off at 8 PM tonight: tomorrow at 8 PM
        self.db.mine(nextAt = iso(inNewYork(9, 20)), delivered = iso(NOW))
        interaction = self.delivered('snoozetomorrow', reminderId = 'r2', inDm = True)
        await self.cog.on_interaction(interaction)
        self.assertEqual(self.db.reminders[str(SERVER)]['r2']['nextAt'], iso(inNewYork(10, 20)))
        reminders_cog.predicates.recheck.assert_awaited_with(interaction, feature = 'toggle_reminders', privateMessagesAllowed = True)

    async def test_a_repeat_snoozes_as_a_copy_skips_and_stops(self):
        self.db.mine(nextAt = iso(inNewYork(10, 22)), repeat = 'daily')
        snooze = self.delivered('snooze10')
        await self.cog.on_interaction(snooze)
        # snoozed, it can't be snoozed again from here, and can still be skipped or stopped
        self.assertEqual([button.label for button in snooze.edit_original_message.await_args.kwargs['view'].children], ['Skip next', 'Stop repeating', 'Done', nextcord.utils.MISSING])
        copy = self.db.reminders[str(SERVER)]['r2']
        self.assertEqual((copy['repeat'], copy['nextAt'], copy['text'], copy['snoozeOf']), ('once', iso(NOW + timedelta(minutes = 10)), 'call the dentist', 'r1'))
        self.assertEqual(self.db.reminders[str(SERVER)]['r1']['repeat'], 'daily')
        skip = self.delivered('skip')
        await self.cog.on_interaction(skip)
        self.assertEqual(self.db.reminders[str(SERVER)]['r1']['nextAt'], iso(inNewYork(11, 22)))
        kwargs = skip.edit_original_message.await_args.kwargs
        self.assertEqual(kwargs['embed'].fields[-1].value, f'⏭️ Skipped one. Next <t:{int(inNewYork(11, 22).timestamp())}:f>.')
        self.assertEqual([button.label for button in kwargs['view'].children], ['10 min', 'Skip next', 'Stop repeating', 'Done', nextcord.utils.MISSING])
        stop = self.delivered('stop')
        await self.cog.on_interaction(stop)
        # Stop means no more: its snooze goes with it
        self.assertEqual(self.db.reminders[str(SERVER)], {})
        self.assertEqual(stop.edit_original_message.await_args.kwargs['embed'].fields[-1].value, '🛑 Stopped repeating, and its snooze.')
        # the other buttons go, and its ✖️ stays, so it can still be deleted
        self.assertEqual([item.custom_id for item in stop.edit_original_message.await_args.kwargs['view'].children], ['remind:dismiss:10:r1:1'])

    async def test_a_sent_repeat_shows_what_was_pressed_and_its_next_as_it_is(self):
        # skipping again counts, rather than adding a line each time, and moves its "next" along
        self.db.mine(nextAt = iso(inNewYork(11, 9)), repeat = 'daily')
        sent = self.cog.deliveredEmbed(self.guild, self.member, self.db.reminders[str(SERVER)]['r1'], inNewYork(10, 9), inNewYork(11, 9), False, NEW_YORK, False)
        def press(action):
            interaction = self.delivered(action)
            interaction.message.embeds = [sent]
            return interaction
        for count, day in (('one', 12), ('2', 13)):
            skip = press('skip')
            await self.cog.on_interaction(skip)
            sent = skip.edit_original_message.await_args.kwargs['embed']
            nextStamp = int(inNewYork(day, 9).timestamp())
            self.assertEqual([field.value for field in sent.fields], [f'Every day at 9:00 AM · next <t:{nextStamp}:R>', f'⏭️ Skipped {count}. Next <t:{nextStamp}:f>.'])
        # a snooze leaves its next as it was, and stands beside the skips
        snooze = press('snooze10')
        await self.cog.on_interaction(snooze)
        sent = snooze.edit_original_message.await_args.kwargs['embed']
        snoozedLine = f"💤 Snoozed until <t:{int((NOW + timedelta(minutes = 10)).timestamp())}:t>."
        self.assertEqual([field.value for field in sent.fields], [f'Every day at 9:00 AM · next <t:{nextStamp}:R>', f'⏭️ Skipped 2. Next <t:{nextStamp}:f>.', snoozedLine])
        # skipped again once snoozed: still no snooze buttons, and both lines, the skips counted on
        skip = press('skip')
        await self.cog.on_interaction(skip)
        sent = skip.edit_original_message.await_args.kwargs['embed']
        nextStamp = int(inNewYork(14, 9).timestamp())
        self.assertEqual([field.value for field in sent.fields], [f'Every day at 9:00 AM · next <t:{nextStamp}:R>', snoozedLine, f'⏭️ Skipped 3. Next <t:{nextStamp}:f>.'])
        self.assertEqual([button.label for button in skip.edit_original_message.await_args.kwargs['view'].children], ['Skip next', 'Stop repeating', 'Done', nextcord.utils.MISSING])
        # stopped, there is no next
        stop = press('stop')
        await self.cog.on_interaction(stop)
        self.assertEqual([field.value for field in stop.edit_original_message.await_args.kwargs['embed'].fields], ['Every day at 9:00 AM', '🛑 Stopped repeating, and its snooze.'])

    async def test_only_its_person_can_press_and_a_gone_one_says_so(self):
        self.db.mine()
        other = Mock(id = OTHER)
        interaction = self.delivered('stop', user = other)
        await self.cog.on_interaction(interaction)
        interaction.send.assert_awaited_once_with('Only <@1> can use these buttons.', ephemeral = True)
        self.assertIn('r1', self.db.reminders[str(SERVER)])
        gone = self.delivered('stop', reminderId = 'missing')
        await self.cog.on_interaction(gone)
        gone.send.assert_awaited_once_with('That reminder is gone.', ephemeral = True)
        gone.edit_original_message.assert_awaited_once_with(view = None)

    async def test_other_buttons_are_ignored_and_a_failing_press_is_answered(self):
        interaction = self.slash()
        interaction.type = nextcord.InteractionType.component
        interaction.data = {'custom_id': 'music:skip'}
        await self.cog.on_interaction(interaction)
        interaction.response.defer.assert_not_awaited()
        self.db.mine()
        failing = self.delivered('stop')
        reminders_cog.predicates.recheck.side_effect = reminders_cog.predicates.FeatureNotEnabledForGuild('x', 'Reminders')
        with patch.object(reminders_cog.presentation, 'sendInteractionError', AsyncMock()) as answered:
            await self.cog.on_interaction(failing)
        answered.assert_awaited_once()
        self.assertIn('r1', self.db.reminders[str(SERVER)])

    def test_the_clock_is_utc(self):
        self.assertEqual(REAL_UTC_NOW().tzinfo, timezone.utc)

    async def test_new_from_the_card_without_a_time_zone_asks_for_one_first(self):
        del self.db.zones[str(ME)]
        view, _ = await self.card()
        submit = self.slash()
        # a press Discord already has an answer for isn't answered twice
        submit.response.is_done.return_value = True
        await view.submitted(submit, ['tomorrow 9am', 'call the dentist'])
        submit.response.defer.assert_not_awaited()
        self.assertEqual(view.screen, reminders_cog.ZONE)
        self.assertIn('Pick your time zone first, so "tomorrow 9am" means your time.', self.notice(self.shown(submit)))

    async def test_an_admins_server_list_without_a_time_zone(self):
        del self.db.zones[str(ME)]
        view, _ = await self.card(admin = True)
        shown = await self.press(view, "Server's")
        self.assertEqual(self.shown(shown).description, 'Nobody has a reminder here.')

    def test_setup_adds_the_cog(self):
        client = Mock()
        reminders_cog.setup(client)
        self.assertIsInstance(client.add_cog.call_args.args[0], Reminders)
