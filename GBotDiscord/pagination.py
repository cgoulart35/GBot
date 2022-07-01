import os
import nextcord
from nextcord.ext import menus
from nextcord.ext.commands.context import Context

class FieldPageSource(menus.ListPageSource):
    def __init__(self, data, ctx: Context, title, color: nextcord.Color):
        self.icon = ctx.guild.icon.url
        self.title = title
        self.color = color
        super().__init__(data, per_page = 9)

    async def format_page(self, menu, entries):
        embed = nextcord.Embed(color = self.color, title = self.title)
        embed.set_thumbnail(url = self.icon)
        for entry in entries:
            embed.add_field(name = entry[0], value = entry[1], inline = True)
        embed.set_footer(text = f'Page { menu.current_page + 1 } / { self.get_max_pages() }')
        return embed

class DescriptionPageSource(menus.ListPageSource):
    def __init__(self, data, title, color):
        self.title = title
        self.color = color
        super().__init__(data, per_page = 8) 

    async def format_page(self, menu, entries):
        embed = nextcord.Embed(color = self.color, title = self.title, description = "\n".join(entries))
        embed.set_footer(text = f'Page { menu.current_page + 1 } / { self.get_max_pages() }')
        return embed

class NoStopButtonMenuPages(menus.ButtonMenuPages, inherit_buttons = False):
    def __init__(self, source, timeout = int(os.getenv("USER_RESPONSE_TIMEOUT_SECONDS"))):
        super().__init__(source, timeout = timeout)

        self.add_item(menus.MenuPaginationButton(emoji = self.FIRST_PAGE))
        self.add_item(menus.MenuPaginationButton(emoji = self.PREVIOUS_PAGE))
        self.add_item(menus.MenuPaginationButton(emoji = self.NEXT_PAGE))
        self.add_item(menus.MenuPaginationButton(emoji = self.LAST_PAGE))

        self._disable_unavailable_buttons()