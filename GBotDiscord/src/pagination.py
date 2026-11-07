#region IMPORTS
import nextcord

from GBotDiscord.src.properties import GBotPropertiesManager

from GBotDiscord.src import presentation
#endregion

# GBot's buttons, in one place so every list and confirmation looks and behaves the same: paged
# lists (CustomButtonMenuPages), lists you pick from and act on (ListPicker), and a confirm step
# for anything that can't be undone (ConfirmView). Only whoever ran the command can press them.

NAV_STYLE = nextcord.ButtonStyle.secondary
SELECTION_LIMIT = 100

class ListPageSource:
    def __init__(self, entries, per_page):
        self.entries = list(entries)
        self.per_page = per_page

    def get_max_pages(self):
        return max(1, -(-len(self.entries) // self.per_page))

    def get_page(self, page):
        return self.entries[page * self.per_page:(page + 1) * self.per_page]

class FieldPageSource(ListPageSource):
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
        embed.set_footer(text = f'Page { menu.current_page + 1 } / { self.get_max_pages() } • {presentation.footerText()}')
        return embed

class DescriptionPageSource(ListPageSource):
    def __init__(self, data, title, color: nextcord.Color, thumbnailUrl, perPage, fields = None, empty = None):
        self.title = title
        self.color = color
        self.thumbnailUrl = thumbnailUrl
        self.perPage = perPage
        self.fields = fields
        self.empty = empty

        super().__init__(data, per_page = self.perPage)

    async def format_page(self, menu, entries):
        description = "\n".join(entries) if entries else self.empty
        embed = nextcord.Embed(color = self.color, title = self.title, description = description)
        if self.thumbnailUrl != None:
            embed.set_thumbnail(url = self.thumbnailUrl)
        if self.fields != None:
            for field in self.fields:
                embed.add_field(name = field['name'], value = field['value'], inline = False)
        embed.set_footer(text = f'Page { menu.current_page + 1 } / { self.get_max_pages() } • {presentation.footerText()}')
        return embed

def authorOf(context):
    return context.user if isinstance(context, nextcord.Interaction) else context.author

class OwnedView(nextcord.ui.View):
    # buttons that answer only whoever ran the command, and tidy themselves away when they time out
    def __init__(self, timeout = None):
        # resolved here rather than as a default argument, which would bind the property once at
        # import and ignore any later setProperty
        if timeout is None:
            timeout = GBotPropertiesManager.USER_RESPONSE_TIMEOUT_SECONDS
        super().__init__(timeout = timeout)
        self.ownerId = None
        self.message = None

    async def interaction_check(self, interaction: nextcord.Interaction):
        if interaction.user.id == self.ownerId:
            return True
        await interaction.response.send_message(f'Only <@{self.ownerId}> can use these buttons.', ephemeral = True)
        return False

    async def on_timeout(self):
        if self.message is not None:
            try:
                await self.message.edit(view = None)
            except nextcord.HTTPException:
                pass

    def button(self, emoji, callback, label = None, style = NAV_STYLE, row = 0, disabled = False):
        item = nextcord.ui.Button(style = style, label = label, emoji = emoji, row = row, disabled = disabled)
        item.callback = callback
        self.add_item(item)
        return item

    async def send(self, context, ephemeral, **kwargs):
        self.ownerId = authorOf(context).id
        if isinstance(context, nextcord.Interaction):
            kwargs['ephemeral'] = ephemeral
        self.message = await context.send(**kwargs)
        return self.message

class CustomButtonMenuPages(OwnedView):
    FIRST_PAGE = '⏮️'
    PREVIOUS_PAGE = '◀️'
    NEXT_PAGE = '▶️'
    LAST_PAGE = '⏭️'
    STOP = '✖️'

    def __init__(self, source, timeout = None):
        super().__init__(timeout = timeout)
        self.source = source
        self.current_page = 0
        self.ephemeral = False
        self.first = self.button(self.FIRST_PAGE, self.showFirst)
        self.previous = self.button(self.PREVIOUS_PAGE, self.showPrevious)
        self.next = self.button(self.NEXT_PAGE, self.showNext)
        self.last = self.button(self.LAST_PAGE, self.showLast)
        self.close = self.button(self.STOP, self.closePages)
        self.navigation = (self.first, self.previous, self.next, self.last)

    def isPaging(self):
        return self.source.get_max_pages() > 1

    def needsControls(self):
        return self.isPaging()

    async def render(self):
        lastPage = self.source.get_max_pages() - 1
        self.current_page = min(self.current_page, lastPage)
        # rebuilt each time, in a fixed order: the arrows only show when there's somewhere to go
        self.clear_items()
        for item in (self.navigation if self.isPaging() else ()) + (self.close,):
            self.add_item(item)
        self.first.disabled = self.previous.disabled = self.current_page == 0
        self.next.disabled = self.last.disabled = self.current_page == lastPage
        return await self.source.format_page(self, self.source.get_page(self.current_page))

    async def show(self, interaction: nextcord.Interaction):
        embed = await self.render()
        await interaction.response.edit_message(embed = embed, view = self)

    async def showFirst(self, interaction):
        self.current_page = 0
        await self.show(interaction)

    async def showPrevious(self, interaction):
        self.current_page = max(0, self.current_page - 1)
        await self.show(interaction)

    async def showNext(self, interaction):
        self.current_page = min(self.source.get_max_pages() - 1, self.current_page + 1)
        await self.show(interaction)

    async def showLast(self, interaction):
        self.current_page = self.source.get_max_pages() - 1
        await self.show(interaction)

    async def closePages(self, interaction):
        self.stop()
        # a private reply can't be deleted, so it keeps its last page without the buttons
        if self.ephemeral:
            await interaction.response.edit_message(view = None)
        else:
            await interaction.response.defer()
            await interaction.message.delete()

    async def start(self, context, ephemeral = False):
        self.ephemeral = isinstance(context, nextcord.Interaction) and ephemeral
        embed = await self.render()
        if self.needsControls():
            return await self.send(context, ephemeral, embed = embed, view = self)
        return await self.send(context, ephemeral, embed = embed)

async def startPages(context, pages, ephemeral = False):
    return await pages.start(context, ephemeral)

class Action:
    # one button under a ListPicker. Its callback gets the picker, the click and the chosen index.
    def __init__(self, label, emoji, style, callback, needsSelection = False, confirm = None):
        self.label = label
        self.emoji = emoji
        self.style = style
        self.callback = callback
        self.needsSelection = needsSelection
        # set for anything that can't be undone, which then asks again with this wording first
        self.confirm = confirm

class ListPicker(CustomButtonMenuPages):
    # a paged list with a dropdown to pick one entry and buttons to act on it, replacing the old
    # "reply with a number" questions, so nothing waits on the next message in the channel
    def __init__(self, source, choices, actions, placeholder, timeout = None):
        super().__init__(source, timeout = timeout)
        self.choices = list(choices)
        self.actions = actions
        self.placeholder = placeholder
        self.selected = None
        self.pending = None
        self.notice = None

    def needsControls(self):
        return True

    def replace(self, entries, choices):
        # after an add or delete, so numbering, pages and the dropdown match what is saved now
        self.source.entries = list(entries)
        self.choices = list(choices)
        self.selected = None
        self.pending = None

    async def render(self):
        embed = await super().render()
        start = self.current_page * self.source.per_page
        options = [
            nextcord.SelectOption(label = choice['label'][:SELECTION_LIMIT], description = (choice.get('description') or None) and choice['description'][:SELECTION_LIMIT], emoji = choice.get('emoji'), value = str(index), default = index == self.selected)
            for index, choice in enumerate(self.choices[start:start + self.source.per_page], start = start)
        ]
        if options:
            select = nextcord.ui.Select(placeholder = self.placeholder, options = options, row = 1)
            select.callback = self.choose
            self.add_item(select)
        if self.pending is not None:
            self.button('✅', self.confirmPending, label = self.pending.confirm, style = nextcord.ButtonStyle.danger, row = 2)
            self.button('↩️', self.cancelPending, label = 'Back', row = 2)
        else:
            for action in self.actions:
                self.button(action.emoji, self.actionCallback(action), label = action.label, style = action.style, row = 2, disabled = action.needsSelection and self.selected is None)
        if self.notice:
            embed.add_field(name = '​', value = self.notice, inline = False)
            self.notice = None
        return embed

    async def choose(self, interaction: nextcord.Interaction):
        self.selected = int(interaction.data['values'][0])
        await self.show(interaction)

    def actionCallback(self, action):
        async def callback(interaction):
            if action.confirm:
                self.pending = action
                await self.show(interaction)
                return
            await action.callback(self, interaction, self.selected)
        return callback

    async def confirmPending(self, interaction):
        action = self.pending
        self.pending = None
        await action.callback(self, interaction, self.selected)

    async def cancelPending(self, interaction):
        self.pending = None
        await self.show(interaction)

    async def refresh(self, interaction, notice = None):
        # every result shows on the list itself rather than as another message in the channel
        self.notice = notice
        await self.show(interaction)

class ConfirmView(OwnedView):
    # one red button for the thing that can't be undone, and Cancel
    def __init__(self, confirmLabel, confirmEmoji, timeout = None):
        super().__init__(timeout = timeout)
        self.confirmed = None
        self.button(confirmEmoji, self.confirmClicked, label = confirmLabel, style = nextcord.ButtonStyle.danger)
        self.button('✖️', self.cancelClicked, label = 'Cancel')

    async def confirmClicked(self, interaction):
        self.confirmed = True
        await interaction.response.defer()
        self.stop()

    async def cancelClicked(self, interaction):
        self.confirmed = False
        await interaction.response.defer()
        self.stop()

    async def finish(self, text):
        # the answer replaces the question on the same message, with no buttons left to press
        try:
            await self.message.edit(content = text, embed = None, view = None)
        except nextcord.HTTPException:
            pass

async def confirm(context, title, description, confirmLabel, confirmEmoji = '🗑️', feature = None):
    # asks, waits for the button, and returns (True, False or None for no answer, the view)
    view = ConfirmView(confirmLabel, confirmEmoji)
    await view.send(context, True, embed = presentation.warningEmbed(title = title, description = description, feature = feature), view = view)
    await view.wait()
    if view.confirmed is None:
        await view.finish('⌛ No answer, so nothing was changed.')
    elif not view.confirmed:
        await view.finish('🚫 Cancelled, so nothing was changed.')
    return view.confirmed, view
