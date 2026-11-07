#region IMPORTS
import unittest
from unittest.mock import AsyncMock, Mock

import nextcord
import nextcord.ext.commands
import unittest.mock

from GBotDiscord.src import pagination
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

# Snapshot the real __init__ methods and startPages function at import time. Other suites
# (e.g. gcoin_test, config_test, hype_test) replace `pagination.FieldPageSource.__init__`
# or `pagination.startPages` with mocks and never restore — without this snapshot, our tests
# run against the stub instead of the real implementation.
_ORIGINAL_FIELD_INIT = pagination.FieldPageSource.__init__
_ORIGINAL_DESC_INIT = pagination.DescriptionPageSource.__init__
_ORIGINAL_CUSTOM_INIT = pagination.CustomButtonMenuPages.__init__
_ORIGINAL_START_PAGES = pagination.startPages


class TestPagination(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(cls):
        print('\nExecuting pagination unit tests...\n')

    @classmethod
    def tearDownClass(cls):
        print('\n\nCompleted pagination unit tests.\n')

    def setUp(self):
        pagination.FieldPageSource.__init__ = _ORIGINAL_FIELD_INIT
        pagination.DescriptionPageSource.__init__ = _ORIGINAL_DESC_INIT
        pagination.CustomButtonMenuPages.__init__ = _ORIGINAL_CUSTOM_INIT
        pagination.startPages = _ORIGINAL_START_PAGES

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

    async def test_close_deletes_a_public_list_and_strips_a_private_one(self):
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
        await private.close.callback(click)
        click.response.edit_message.assert_awaited_once_with(view = None)

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
        self.assertEqual(self.labels(picker)[-2:], ['Add', 'Delete'])
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
        self.assertEqual(self.labels(picker)[-2:], ['Add', 'Delete'])
        delete = [item for item in picker.children if getattr(item, 'label', None) == 'Delete'][0]
        await delete.callback(self.interaction())
        confirm = [item for item in picker.children if getattr(item, 'label', None) == 'Delete it'][0]
        await confirm.callback(self.interaction())
        self.assertEqual(self.calls, [0])

    async def test_replacing_the_list_and_showing_a_notice(self):
        picker = self.picker()
        await picker.start(self.context())
        picker.selected = 1
        picker.replace([], [])
        interaction = self.interaction()
        await picker.refresh(interaction, '🗑️ Deleted.')
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

