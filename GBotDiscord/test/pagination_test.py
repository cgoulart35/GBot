#region IMPORTS
import unittest
from unittest.mock import AsyncMock, Mock

import nextcord
import nextcord.ext.commands
import unittest.mock

from GBotDiscord.src import pagination
from GBotDiscord.test import isolation
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

class TestPagination(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(cls):
        print('\nExecuting pagination unit tests...\n')

    @classmethod
    def tearDownClass(cls):
        print('\n\nCompleted pagination unit tests.\n')

    def setUp(self):
        isolation.restorePagination()

    # region FieldPageSource.format_page

    async def test_FieldPageSource_format_page_with_thumbnail(self):
        data = [('n1', 'v1'), ('n2', 'v2')]
        src = pagination.FieldPageSource(data, 'http://thumb.png', 'Title', nextcord.Color.blue(), False, 2)
        menu = Mock()
        menu.current_page = 0
        embed = await src.format_page(menu, data)
        self.assertEqual(embed.title, 'Title')
        self.assertEqual(embed.color, nextcord.Color.blue())
        self.assertEqual(embed.thumbnail.url, 'http://thumb.png')
        self.assertEqual(len(embed.fields), 2)
        self.assertEqual(embed.fields[0].name, 'n1')
        self.assertEqual(embed.fields[0].value, 'v1')
        self.assertFalse(embed.fields[0].inline)
        self.assertEqual(embed.fields[1].name, 'n2')
        self.assertEqual(embed.fields[1].value, 'v2')
        self.assertEqual(embed.footer.text, 'Page 1 / 1 • GBot 8.0')

    async def test_FieldPageSource_format_page_no_thumbnail_inline_true(self):
        data = [('a', 'b'), ('c', 'd'), ('e', 'f')]
        src = pagination.FieldPageSource(data, None, 'T', nextcord.Color.red(), True, 2)
        # data of length 3 with per_page 2 → 2 max pages
        menu = Mock()
        menu.current_page = 1
        embed = await src.format_page(menu, [('e', 'f')])
        self.assertIsNone(embed.thumbnail.url)
        self.assertEqual(len(embed.fields), 1)
        self.assertTrue(embed.fields[0].inline)
        self.assertEqual(embed.footer.text, 'Page 2 / 2 • GBot 8.0')

    # endregion

    # region DescriptionPageSource.format_page

    async def test_DescriptionPageSource_format_page_full(self):
        data = ['a', 'b', 'c']
        fields = [{'name': 'fn', 'value': 'fv'}]
        src = pagination.DescriptionPageSource(data, 'D', nextcord.Color.green(), 'http://t.png', 3, fields=fields)
        menu = Mock()
        menu.current_page = 0
        embed = await src.format_page(menu, data)
        self.assertEqual(embed.title, 'D')
        self.assertEqual(embed.description, 'a\nb\nc')
        self.assertEqual(embed.color, nextcord.Color.green())
        self.assertEqual(embed.thumbnail.url, 'http://t.png')
        self.assertEqual(len(embed.fields), 1)
        self.assertEqual(embed.fields[0].name, 'fn')
        self.assertEqual(embed.fields[0].value, 'fv')
        self.assertFalse(embed.fields[0].inline)
        self.assertEqual(embed.footer.text, 'Page 1 / 1 • GBot 8.0')

    async def test_DescriptionPageSource_format_page_no_thumbnail_no_fields(self):
        data = ['x', 'y']
        src = pagination.DescriptionPageSource(data, 'D', nextcord.Color.green(), None, 2)
        menu = Mock()
        menu.current_page = 0
        embed = await src.format_page(menu, data)
        self.assertEqual(embed.description, 'x\ny')
        self.assertIsNone(embed.thumbnail.url)
        self.assertEqual(len(embed.fields), 0)
        self.assertEqual(embed.footer.text, 'Page 1 / 1 • GBot 8.0')

    # endregion

    # region pages

    def pages(self, count, perPage = 2):
        source = pagination.DescriptionPageSource([f'line {number}' for number in range(count)], 'T', nextcord.Color.blue(), None, perPage)
        return pagination.CustomButtonMenuPages(source)

    def interaction(self, userId = 1):
        interaction = Mock(spec = nextcord.Interaction)
        interaction.user = Mock(id = userId)
        interaction.response = Mock(edit_message = AsyncMock(), defer = AsyncMock(), send_message = AsyncMock(), send_modal = AsyncMock())
        interaction.message = Mock(delete = AsyncMock())
        interaction.data = {}
        return interaction

    def context(self):
        context = Mock(spec = nextcord.ext.commands.Context)
        context.author = Mock(id = 1)
        context.send = AsyncMock(return_value = Mock(edit = AsyncMock()))
        return context

    async def test_a_single_page_needs_no_buttons(self):
        context = self.context()
        await self.pages(2).start(context)
        self.assertNotIn('view', context.send.await_args.kwargs)

    async def test_more_pages_get_arrows_and_close_in_order(self):
        pages = self.pages(5)
        context = self.context()
        await pages.start(context)
        self.assertIs(context.send.await_args.kwargs['view'], pages)
        self.assertEqual([item.emoji.name for item in pages.children], ['⏮️', '◀️', '▶️', '⏭️', '✖️'])
        self.assertTrue(pages.first.disabled and pages.previous.disabled)
        self.assertFalse(pages.next.disabled or pages.last.disabled)

    async def test_paging_moves_and_stops_at_each_end(self):
        pages = self.pages(5)
        await pages.start(self.context())
        interaction = self.interaction()
        await pages.next.callback(interaction)
        self.assertEqual(pages.current_page, 1)
        await pages.last.callback(interaction)
        await pages.next.callback(interaction)
        self.assertEqual(pages.current_page, 2)
        self.assertTrue(pages.next.disabled)
        await pages.previous.callback(interaction)
        await pages.first.callback(interaction)
        await pages.previous.callback(interaction)
        self.assertEqual(pages.current_page, 0)
        self.assertIn('Page 1 / 3', interaction.response.edit_message.await_args.kwargs['embed'].footer.text)

    async def test_close_deletes_the_list_public_or_private(self):
        pages = self.pages(5)
        await pages.start(self.context())
        interaction = self.interaction()
        await pages.close.callback(interaction)
        interaction.message.delete.assert_awaited_once()
        private = self.pages(5)
        slash = self.interaction()
        slash.send = AsyncMock(return_value = Mock(edit = AsyncMock()))
        await private.start(slash, ephemeral = True)
        self.assertIs(slash.send.await_args.kwargs['ephemeral'], True)
        click = self.interaction()
        click.delete_original_message = AsyncMock()
        await private.close.callback(click)
        click.delete_original_message.assert_awaited_once()

    async def test_a_list_that_cannot_be_deleted_just_loses_its_buttons(self):
        pages = self.pages(5)
        await pages.start(self.context())
        interaction = self.interaction()
        interaction.message.delete.side_effect = nextcord.HTTPException(Mock(status = 403, reason = 'no'), 'no')
        interaction.edit_original_message = AsyncMock()
        await pages.close.callback(interaction)
        interaction.edit_original_message.assert_awaited_once_with(view = None)

    async def test_every_list_is_one_discord_accepts(self):
        # Discord refuses a whole message if any button or dropdown lacks an id, so check what it gets
        for view in (self.pages(5), self.picker(count = 5)):
            await view.start(self.context())
            view.selected = 0
            await view.show(self.interaction())
            for row in view.to_components():
                for component in row['components']:
                    self.assertTrue(component.get('custom_id'), component)
                    self.assertLessEqual(len(component['custom_id']), 100)
            self.assertLessEqual(len(view.to_components()), 5)
        confirmView = pagination.ConfirmView('Delete', '🗑️')
        self.assertTrue(all(component.get('custom_id') for row in confirmView.to_components() for component in row['components']))

    async def test_a_picker_puts_close_with_its_buttons(self):
        picker = self.picker(count = 2)
        await picker.start(self.context())
        rows = picker.to_components()
        self.assertEqual([component.get('label') for component in rows[-1]['components']], ['Add', 'Delete', 'Close'])
        self.assertEqual(len(rows), 2)

    async def test_only_whoever_ran_it_can_press(self):
        pages = self.pages(5)
        await pages.start(self.context())
        self.assertTrue(await pages.interaction_check(self.interaction(1)))
        stranger = self.interaction(2)
        self.assertFalse(await pages.interaction_check(stranger))
        self.assertIn('Only <@1>', stranger.response.send_message.await_args.args[0])

    async def test_a_timeout_removes_the_buttons(self):
        pages = self.pages(5)
        await pages.start(self.context())
        await pages.on_timeout()
        pages.message.edit.assert_awaited_once_with(view = None)
        pages.message.edit.side_effect = nextcord.HTTPException(Mock(status = 404, reason = 'gone'), 'gone')
        await pages.on_timeout()
        pages.message = None
        await pages.on_timeout()

    async def test_the_timeout_follows_the_property(self):
        with unittest.mock.patch.object(GBotPropertiesManager, 'USER_RESPONSE_TIMEOUT_SECONDS', 77):
            self.assertEqual(self.pages(1).timeout, 77)
        self.assertEqual(pagination.CustomButtonMenuPages(self.pages(1).source, timeout = 5).timeout, 5)

    async def test_startPages_starts_them(self):
        pages = Mock(start = AsyncMock())
        context = self.context()
        await pagination.startPages(context, pages, ephemeral = True)
        pages.start.assert_awaited_once_with(context, True)

    async def test_an_empty_list_says_so(self):
        source = pagination.DescriptionPageSource([], 'T', nextcord.Color.blue(), None, 2, empty = 'Nothing here.')
        embed = await source.format_page(Mock(current_page = 0), [])
        self.assertEqual(embed.description, 'Nothing here.')
        self.assertEqual(source.get_max_pages(), 1)

    # endregion

    # region list picker

    def picker(self, count = 3, perPage = 2):
        self.calls = []
        async def act(picker, interaction, index):
            self.calls.append(index)
        source = pagination.DescriptionPageSource([f'line {number}' for number in range(count)], 'T', nextcord.Color.blue(), None, perPage)
        choices = [{'label': f'choice {number}', 'description': 'd' * 150 if number == 0 else None, 'emoji': '📌'} for number in range(count)]
        actions = [pagination.Action('Add', '➕', nextcord.ButtonStyle.success, act), pagination.Action('Delete', '🗑️', nextcord.ButtonStyle.danger, act, needsSelection = True, confirm = 'Delete it')]
        return pagination.ListPicker(source, choices, actions, 'Pick one')

    def labels(self, view):
        return [item.label for item in view.children if isinstance(item, nextcord.ui.Button)]

    async def test_the_picker_always_shows_its_controls_and_a_dropdown_for_the_page(self):
        picker = self.picker()
        context = self.context()
        await picker.start(context)
        self.assertIs(context.send.await_args.kwargs['view'], picker)
        select = next(item for item in picker.children if isinstance(item, nextcord.ui.Select))
        self.assertEqual([option.label for option in select.options], ['choice 0', 'choice 1'])
        self.assertEqual(len(select.options[0].description), 100)
        self.assertEqual(self.labels(picker)[-3:], ['Add', 'Delete', 'Close'])
        delete = [item for item in picker.children if getattr(item, 'label', None) == 'Delete'][0]
        self.assertTrue(delete.disabled)

    async def test_choosing_enables_the_actions_that_need_a_choice(self):
        picker = self.picker()
        await picker.start(self.context())
        interaction = self.interaction()
        interaction.data = {'values': ['1']}
        select = next(item for item in picker.children if isinstance(item, nextcord.ui.Select))
        await select.callback(interaction)
        self.assertEqual(picker.selected, 1)
        delete = [item for item in picker.children if getattr(item, 'label', None) == 'Delete'][0]
        self.assertFalse(delete.disabled)
        self.assertTrue(next(item for item in picker.children if isinstance(item, nextcord.ui.Select)).options[1].default)

    async def test_an_action_without_confirmation_runs_straight_away(self):
        picker = self.picker()
        await picker.start(self.context())
        add = [item for item in picker.children if getattr(item, 'label', None) == 'Add'][0]
        await add.callback(self.interaction())
        self.assertEqual(self.calls, [None])

    async def test_a_destructive_action_asks_first_and_can_go_back(self):
        picker = self.picker()
        await picker.start(self.context())
        picker.selected = 0
        await picker.show(self.interaction())
        delete = [item for item in picker.children if getattr(item, 'label', None) == 'Delete'][0]
        await delete.callback(self.interaction())
        self.assertEqual(self.calls, [])
        self.assertEqual(self.labels(picker)[-2:], ['Delete it', 'Back'])
        back = [item for item in picker.children if getattr(item, 'label', None) == 'Back'][0]
        await back.callback(self.interaction())
        self.assertEqual(self.labels(picker)[-3:], ['Add', 'Delete', 'Close'])
        delete = [item for item in picker.children if getattr(item, 'label', None) == 'Delete'][0]
        await delete.callback(self.interaction())
        confirm = [item for item in picker.children if getattr(item, 'label', None) == 'Delete it'][0]
        await confirm.callback(self.interaction())
        self.assertEqual(self.calls, [0])

    async def test_a_choice_from_another_page_is_cleared(self):
        picker = self.picker(count = 5)
        await picker.start(self.context())
        picker.selected = 0
        picker.pending = picker.actions[1]
        await picker.next.callback(self.interaction())
        self.assertIsNone(picker.selected)
        self.assertIsNone(picker.pending)
        delete = [item for item in picker.children if getattr(item, 'label', None) == 'Delete'][0]
        self.assertTrue(delete.disabled)

    async def test_a_click_acknowledged_first_edits_through_that(self):
        pages = self.pages(5)
        await pages.start(self.context())
        interaction = self.interaction()
        interaction.response.is_done = Mock(return_value = True)
        interaction.edit_original_message = AsyncMock()
        await pages.show(interaction)
        interaction.edit_original_message.assert_awaited_once()
        interaction.response.edit_message.assert_not_awaited()

    async def test_replacing_the_list_and_showing_a_notice(self):
        picker = self.picker()
        await picker.start(self.context())
        picker.selected = 1
        picker.replace([], [])
        interaction = self.interaction()
        await picker.redraw(interaction, '🗑️ Deleted.')
        embed = interaction.response.edit_message.await_args.kwargs['embed']
        self.assertIn('🗑️ Deleted.', [field.value for field in embed.fields])
        self.assertIsNone(picker.selected)
        self.assertFalse(any(isinstance(item, nextcord.ui.Select) for item in picker.children))
        await picker.show(self.interaction())
        self.assertIsNone(picker.notice)

    # endregion

    # region confirm

    async def test_confirm_returns_the_choice_and_finishes_on_the_same_message(self):
        for button, expected in ((0, True), (1, False)):
            context = self.context()
            async def press(view = None, **kwargs):
                pass
            with unittest.mock.patch.object(pagination.ConfirmView, 'wait', autospec = True) as wait:
                async def clicked(view):
                    await view.children[button].callback(self.interaction())
                wait.side_effect = clicked
                confirmed, view = await pagination.confirm(context, 'Sure?', 'It goes for good.', 'Delete')
            self.assertIs(confirmed, expected)
            self.assertEqual(context.send.await_args.kwargs['embed'].title, 'Sure?')
            if not expected:
                view.message.edit.assert_awaited_once_with(content = '🚫 Cancelled, so nothing was changed.', embed = None, view = None)

    async def test_confirm_with_no_answer_changes_nothing(self):
        context = self.context()
        with unittest.mock.patch.object(pagination.ConfirmView, 'wait', AsyncMock()):
            confirmed, view = await pagination.confirm(context, 'Sure?', 'x', 'Delete')
        self.assertIsNone(confirmed)
        view.message.edit.assert_awaited_once_with(content = '⌛ No answer, so nothing was changed.', embed = None, view = None)
        view.message.edit.side_effect = nextcord.HTTPException(Mock(status = 404, reason = 'gone'), 'gone')
        await view.finish('x')

    async def test_a_slash_confirmation_is_private(self):
        interaction = self.interaction()
        interaction.send = AsyncMock(return_value = Mock(edit = AsyncMock()))
        with unittest.mock.patch.object(pagination.ConfirmView, 'wait', AsyncMock()):
            await pagination.confirm(interaction, 'Sure?', 'x', 'Delete')
        self.assertIs(interaction.send.await_args.kwargs['ephemeral'], True)

    # endregion

    # region pieces every card uses

    async def test_a_failing_press_answers_like_the_command_would(self):
        view = pagination.OwnedView()
        interaction = self.interaction()
        with unittest.mock.patch.object(pagination.presentation, 'sendInteractionError', AsyncMock()) as sendInteractionError:
            error = KeyError('x')
            await view.on_error(error, None, interaction)
        sendInteractionError.assert_awaited_once_with(interaction, error)

    async def test_links_and_discords_own_pickers(self):
        view = pagination.OwnedView()
        link = view.link('🔗', 'Website', 'https://gbot.stormerg.com/')
        self.assertEqual(link.url, 'https://gbot.stormerg.com/')
        chosen = []
        async def picked(interaction, value):
            chosen.append(value)
        member = view.picker(nextcord.ui.UserSelect, picked, 'Pick a member…')
        channel = view.picker(nextcord.ui.ChannelSelect, picked, 'Pick a channel…', row = 2, channelTypes = [nextcord.ChannelType.text])
        self.assertTrue(member.custom_id.startswith('pick:'))
        self.assertNotEqual(member.custom_id, channel.custom_id)
        self.assertEqual(channel.channel_types, [nextcord.ChannelType.text])
        with unittest.mock.patch.object(nextcord.ui.UserSelect, 'values', new_callable = unittest.mock.PropertyMock, return_value = ['someone']):
            await member.callback(self.interaction())
        self.assertEqual(chosen, ['someone'])
        for item in view.children:
            item.to_component_dict()

    async def test_a_form_hands_over_what_was_typed(self):
        submitted = []
        async def onSubmit(interaction, values):
            submitted.append(values)
        form = pagination.Form('A title that is far too long for what Discord allows', [
            pagination.Field('Name', placeholder = 'Sword', maxLength = 10),
            pagination.Field('Note', long = True, required = False, default = 'hi')], onSubmit)
        self.assertEqual(len(form.title), pagination.FORM_TITLE_LIMIT)
        self.assertEqual(form.inputs[0].max_length, 10)
        self.assertEqual(form.inputs[1].style, nextcord.TextInputStyle.paragraph)
        self.assertEqual(form.inputs[1].default_value, 'hi')
        form.inputs[0]._inputed_value = '  Shield '
        form.inputs[1]._inputed_value = None
        await form.callback(self.interaction())
        self.assertEqual(submitted, [['Shield', '']])
        # Discord takes spaces as filled in, and a blank name would be saved
        form.inputs[0]._inputed_value = '   '
        refused = self.interaction()
        refused.send = AsyncMock()
        await form.callback(refused)
        self.assertEqual(len(submitted), 1)
        self.assertIn('Please fill in **Name**', refused.send.await_args.kwargs['embed'].description)
        with unittest.mock.patch.object(pagination.presentation, 'sendInteractionError', AsyncMock()) as sendInteractionError:
            await form.on_error(KeyError('x'), self.interaction())
        sendInteractionError.assert_awaited_once()

    def prefixContext(self):
        context = self.context()
        context.author = Mock(id = 1, display_name = 'Stormer')
        context.message = Mock(delete = AsyncMock())
        return context

    async def test_a_slash_command_opens_a_private_card_straight_away(self):
        opened = []
        async def opener(context, author):
            opened.append((context, author))
        interaction = self.interaction()
        await pagination.openPrivately(interaction, '🤖', 'Agent settings', opener)
        self.assertEqual(opened, [(interaction, interaction.user)])

    async def test_a_prefix_command_posts_an_open_button_anyone_can_press(self):
        opened = []
        async def opener(context, author):
            opened.append(author.id)
        context = self.prefixContext()
        with unittest.mock.patch.object(pagination.predicates, 'recheck', AsyncMock()) as recheck:
            await pagination.openPrivately(context, '🤖', 'Agent settings', opener, feature = 'toggle_agent', admin = True)
            content = context.send.await_args.kwargs['content']
            self.assertEqual(content, '🤖 Agent settings for **Stormer**. Press 🔒 Open to see it privately.')
            view = context.send.await_args.kwargs['view']
            self.assertTrue(await view.interaction_check(self.interaction(2)))
            view.message.delete = AsyncMock()
            # someone else gets their own, and the one-liner stays for its owner
            other = self.interaction(2)
            await view.children[0].callback(other)
            other.response.defer.assert_awaited_once_with(ephemeral = True)
            recheck.assert_awaited_with(other, feature = 'toggle_agent', admin = True)
            view.message.delete.assert_not_awaited()
            # its owner gets theirs, and both messages go
            await view.children[0].callback(self.interaction(1))
        self.assertEqual(opened, [2, 1])
        view.message.delete.assert_awaited_once()
        context.message.delete.assert_awaited_once()
        self.assertTrue(view.is_finished())

    async def test_an_unopened_one_liner_tidies_away_even_without_permission(self):
        context = self.prefixContext()
        await pagination.openPrivately(context, '🤖', 'Agent settings', AsyncMock())
        view = context.send.await_args.kwargs['view']
        view.message.delete = AsyncMock()
        context.message.delete.side_effect = nextcord.Forbidden(Mock(status = 403, reason = 'no'), 'no')
        await view.on_timeout()
        view.message.delete.assert_awaited_once()

    async def test_persistent_buttons_say_what_they_are_for(self):
        button = pagination.persistentButton('Guess', '🎯', nextcord.ButtonStyle.primary, 'storms:guess:1')
        view = pagination.persistentView([button])
        self.assertFalse(view.auto_defer)
        self.assertIsNone(view.timeout)
        self.assertIs(pagination.stopped(view), view)
        self.assertTrue(view.is_finished())
        interaction = self.interaction()
        interaction.type = nextcord.InteractionType.component
        interaction.data = {'custom_id': 'storms:guess:1'}
        self.assertEqual(pagination.persistentParts(interaction, 'storms:'), ['guess', '1'])
        self.assertIsNone(pagination.persistentParts(interaction, 'gtrade:'))
        interaction.data = None
        self.assertIsNone(pagination.persistentParts(interaction, 'storms:'))
        interaction.type = nextcord.InteractionType.application_command
        self.assertIsNone(pagination.persistentParts(interaction, 'storms:'))

    # endregion

