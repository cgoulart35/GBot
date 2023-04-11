#region IMPORTS
import nextcord
from nextcord.ext import menus

from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

class FieldPageSource(menus.ListPageSource):
    def __init__(self, data, thumbnailUrl, title, color: nextcord.Color, inline, perPage):
        self.thumbnailUrl = thumbnailUrl
        self.title = title
        self.color = color
        self.inline = inline
        self.perPage = perPage
        super().__init__(data, per_page = self.perPage)

    async def format_page(self, menu, entries):
        embed = nextcord.Embed(color = self.color, title = self.title)
        if self.thumbnailUrl != None:
            embed.set_thumbnail(url = self.thumbnailUrl)
        for entry in entries:
            embed.add_field(name = entry[0], value = entry[1], inline = self.inline)
        embed.set_footer(text = f'Page { menu.current_page + 1 } / { self.get_max_pages() }')
        return embed

class DescriptionPageSource(menus.ListPageSource):
    def __init__(self, data, title, color: nextcord.Color, thumbnailUrl, perPage, fields = None):
        self.title = title
        self.color = color
        self.thumbnailUrl = thumbnailUrl
        self.perPage = perPage
        self.fields = fields

        super().__init__(data, per_page = self.perPage) 

    async def format_page(self, menu, entries):
        embed = nextcord.Embed(color = self.color, title = self.title, description = "\n".join(entries))
        if self.thumbnailUrl != None:
            embed.set_thumbnail(url = self.thumbnailUrl)
        if self.fields != None:
            for field in self.fields:
                embed.add_field(name = field['name'], value = field['value'], inline = False)
        embed.set_footer(text = f'Page { menu.current_page + 1 } / { self.get_max_pages() }')
        return embed

class CustomButtonMenuPages(menus.ButtonMenuPages, inherit_buttons = False):
    def __init__(self, source, timeout = GBotPropertiesManager.USER_RESPONSE_TIMEOUT_SECONDS):
        super().__init__(source, timeout = timeout)

        self.delete_message_after = True
        self.STOP = "❌"

        self.add_item(menus.MenuPaginationButton(emoji = self.FIRST_PAGE))
        self.add_item(menus.MenuPaginationButton(emoji = self.PREVIOUS_PAGE))
        self.add_item(menus.MenuPaginationButton(emoji = self.NEXT_PAGE))
        self.add_item(menus.MenuPaginationButton(emoji = self.LAST_PAGE))
        self.add_item(menus.MenuPaginationButton(emoji = self.STOP))

async def startPages(context, pages):
    if isinstance(context, nextcord.Interaction):
        await pages.start(interaction = context)
    else:
        await pages.start(context)