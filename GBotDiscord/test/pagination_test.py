#region IMPORTS
import unittest
from unittest.mock import AsyncMock, Mock

import nextcord
from nextcord.ext import menus

from GBotDiscord.src import pagination
#endregion

# Snapshot the real __init__ methods and startPages function at import time. Other suites
# (e.g. gcoin_test, config_test, hype_test) replace `pagination.FieldPageSource.__init__`
# or `pagination.startPages` with mocks and never restore — without this snapshot, our tests
# run against the stub instead of the real implementation. The default-timeout binding for
# CustomButtonMenuPages is also captured here from __defaults__ at import time (it's
# evaluated once at function definition).
_ORIGINAL_FIELD_INIT = pagination.FieldPageSource.__init__
_ORIGINAL_DESC_INIT = pagination.DescriptionPageSource.__init__
_ORIGINAL_CUSTOM_INIT = pagination.CustomButtonMenuPages.__init__
_ORIGINAL_START_PAGES = pagination.startPages
_DEFAULT_TIMEOUT_AT_IMPORT = pagination.CustomButtonMenuPages.__init__.__defaults__[0]


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
        self.assertEqual(embed.footer.text, 'Page 1 / 1')

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
        self.assertEqual(embed.footer.text, 'Page 2 / 2')

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
        self.assertEqual(embed.footer.text, 'Page 1 / 1')

    async def test_DescriptionPageSource_format_page_no_thumbnail_no_fields(self):
        data = ['x', 'y']
        src = pagination.DescriptionPageSource(data, 'D', nextcord.Color.green(), None, 2)
        menu = Mock()
        menu.current_page = 0
        embed = await src.format_page(menu, data)
        self.assertEqual(embed.description, 'x\ny')
        self.assertIsNone(embed.thumbnail.url)
        self.assertEqual(len(embed.fields), 0)
        self.assertEqual(embed.footer.text, 'Page 1 / 1')

    # endregion

    # region CustomButtonMenuPages.__init__

    # async — nextcord.ui.View.__init__ calls asyncio.get_running_loop()
    async def test_CustomButtonMenuPages_init_sets_flags_and_adds_buttons(self):
        # Use a real FieldPageSource as the source so super().__init__ has a valid PageSource.
        src = pagination.FieldPageSource([('a', 'b')], None, 'T', nextcord.Color.blue(), False, 1)
        cb = pagination.CustomButtonMenuPages(src)

        # delete_message_after set, STOP overridden to ❌
        self.assertTrue(cb.delete_message_after)
        self.assertEqual(cb.STOP, "❌")

        # Five MenuPaginationButtons added via add_item, in the right order.
        buttons = [c for c in cb.children if isinstance(c, menus.MenuPaginationButton)]
        self.assertEqual(len(buttons), 5)
        emojis = [str(b.emoji) for b in buttons]
        self.assertEqual(emojis, [
            str(cb.FIRST_PAGE),
            str(cb.PREVIOUS_PAGE),
            str(cb.NEXT_PAGE),
            str(cb.LAST_PAGE),
            "❌",
        ])

    async def test_CustomButtonMenuPages_init_uses_default_timeout_from_properties(self):
        src = pagination.FieldPageSource([], None, 'T', nextcord.Color.blue(), False, 1)
        cb = pagination.CustomButtonMenuPages(src)
        # Default param is bound to USER_RESPONSE_TIMEOUT_SECONDS at module import time
        # (not re-evaluated on each call), so compare to the snapshot captured at import.
        self.assertEqual(cb.timeout, _DEFAULT_TIMEOUT_AT_IMPORT)

    async def test_CustomButtonMenuPages_init_uses_explicit_timeout(self):
        src = pagination.FieldPageSource([], None, 'T', nextcord.Color.blue(), False, 1)
        cb = pagination.CustomButtonMenuPages(src, timeout=42)
        self.assertEqual(cb.timeout, 42)

    # endregion

    # region startPages

    async def test_startPages_with_interaction(self):
        ctx = Mock(spec=nextcord.Interaction)
        pages = Mock()
        pages.start = AsyncMock()
        await pagination.startPages(ctx, pages)
        pages.start.assert_awaited_once_with(interaction=ctx)

    async def test_startPages_with_context(self):
        ctx = Mock()  # not an Interaction
        pages = Mock()
        pages.start = AsyncMock()
        await pagination.startPages(ctx, pages)
        pages.start.assert_awaited_once_with(ctx)

    # endregion


if __name__ == '__main__':
    unittest.main()
