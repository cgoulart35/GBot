#region IMPORTS
import secrets

import nextcord

from GBotDiscord.src.properties import GBotPropertiesManager

from GBotDiscord.src import presentation
from GBotDiscord.src import predicates
#endregion

# GBot's buttons, in one place so every card, list and confirmation looks and behaves the same:
# paged lists (CustomButtonMenuPages), lists you pick from and act on (ListPicker), a confirm step
# for anything that can't be undone (ConfirmView), forms (Form), the one-liner a prefix command
# posts for a private card (openPrivately), and buttons that outlive a restart (persistentButton).
# Only whoever ran the command can press a card's buttons.

NAV_STYLE = nextcord.ButtonStyle.secondary
SELECTION_LIMIT = 100
# Discord's limits for a form: its title and each box's label
FORM_TITLE_LIMIT = 45
FORM_LABEL_LIMIT = 45

def newId(kind):
    # Discord refuses a dropdown without an id, unlike a button, which nextcord gives one
    return f'{kind}:{secrets.token_hex(8)}'

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
        self.ephemeral = False

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

    async def on_error(self, error, item, interaction):
        # a press's refusal (a re-check failing) reads the same as the command's would
        await presentation.sendInteractionError(interaction, error)

    def button(self, emoji, callback, label = None, style = NAV_STYLE, row = 0, disabled = False):
        item = nextcord.ui.Button(style = style, label = label, emoji = emoji, row = row, disabled = disabled)
        item.callback = callback
        self.add_item(item)
        return item

    def closeButton(self, row = 0):
        # every card has one, as a long list always had
        return self.button(CustomButtonMenuPages.STOP, self.closeCard, row = row)

    async def closeCard(self, interaction):
        self.stop()
        await interaction.response.defer()
        try:
            # a private reply is deleted through the click, as only Discord's own Dismiss reaches it otherwise
            if self.ephemeral:
                await interaction.delete_original_message()
            else:
                await interaction.message.delete()
        except nextcord.HTTPException:
            await interaction.edit_original_message(view = None)

    def link(self, emoji, label, url, row = 0):
        # opens a web page, so Discord answers it and there is nothing to call back
        item = nextcord.ui.Button(style = nextcord.ButtonStyle.link, label = label, emoji = emoji, url = url, row = row)
        self.add_item(item)
        return item

    def picker(self, kind, callback, placeholder, row = 1, channelTypes = None):
        # Discord's own member, channel and role lists, which search the whole server as you type
        if kind is nextcord.ui.ChannelSelect:
            item = kind(custom_id = newId('pick'), placeholder = placeholder, row = row, channel_types = channelTypes)
        else:
            item = kind(custom_id = newId('pick'), placeholder = placeholder, row = row)
        item.callback = lambda interaction: callback(interaction, item.values[0])
        self.add_item(item)
        return item

    async def send(self, context, ephemeral, **kwargs):
        self.ownerId = authorOf(context).id
        if isinstance(context, nextcord.Interaction):
            kwargs['ephemeral'] = ephemeral
        self.ephemeral = isinstance(context, nextcord.Interaction) and ephemeral
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
        self.first = self.button(self.FIRST_PAGE, self.showFirst)
        self.previous = self.button(self.PREVIOUS_PAGE, self.showPrevious)
        self.next = self.button(self.NEXT_PAGE, self.showNext)
        self.last = self.button(self.LAST_PAGE, self.showLast)
        self.close = self.button(self.STOP, self.closeCard)
        self.navigation = (self.first, self.previous, self.next, self.last)
        # a picker puts Close with its own buttons, and plain pages keep it beside the arrows
        self.closeRow = 0

    def isPaging(self):
        return self.source.get_max_pages() > 1

    def needsControls(self):
        return self.isPaging()

    async def render(self):
        lastPage = self.source.get_max_pages() - 1
        self.current_page = min(self.current_page, lastPage)
        # rebuilt each time, in a fixed order: the arrows only show when there's somewhere to go
        self.clear_items()
        for item in self.navigation if self.isPaging() else ():
            self.add_item(item)
        self.close.row = self.closeRow
        if self.closeRow == 0:
            self.add_item(self.close)
        self.first.disabled = self.previous.disabled = self.current_page == 0
        self.next.disabled = self.last.disabled = self.current_page == lastPage
        return await self.source.format_page(self, self.source.get_page(self.current_page))

    async def show(self, interaction: nextcord.Interaction):
        embed = await self.render()
        # a click that had to wait on the database was acknowledged first, so it edits through that
        if interaction.response.is_done() is True:
            await interaction.edit_original_message(embed = embed, view = self)
        else:
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
    def __init__(self, label, emoji, style, callback, needsSelection = False, confirm = None, row = 2):
        self.label = label
        # 2 is the row Close sits on, so at most four there. A second row of actions goes on 3.
        self.row = row
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
        self.closeRow = 2
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
        # a choice from another page would let Edit or Delete act on something that isn't on screen
        if self.selected is not None and not start <= self.selected < start + self.source.per_page:
            self.selected = None
            self.pending = None
        options = [
            nextcord.SelectOption(label = choice['label'][:SELECTION_LIMIT], description = (choice.get('description') or None) and choice['description'][:SELECTION_LIMIT], emoji = choice.get('emoji'), value = str(index), default = index == self.selected)
            for index, choice in enumerate(self.choices[start:start + self.source.per_page], start = start)
        ]
        if options:
            select = nextcord.ui.Select(custom_id = newId('pick'), placeholder = self.placeholder, options = options, row = 1)
            select.callback = self.choose
            self.add_item(select)
        if self.pending is not None:
            self.button('✅', self.confirmPending, label = self.pending.confirm, style = nextcord.ButtonStyle.danger, row = 2)
            self.button('↩️', self.cancelPending, label = 'Back', row = 2)
        else:
            for action in self.actions:
                self.button(action.emoji, self.actionCallback(action), label = action.label, style = action.style, row = action.row, disabled = action.needsSelection and self.selected is None)
            self.close.label = 'Close'
            self.add_item(self.close)
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

    async def redraw(self, interaction, notice = None):
        # every result shows on the list itself rather than as another message in the channel. Not
        # called refresh: nextcord's View has its own, which it calls whenever the message changes.
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


class CardReply:
    # Runs a command's own code from a card's button: what it would have sent becomes the card's
    # notice instead, so every check and message stays in the one place it's written.
    def __init__(self, interaction):
        self.guild = interaction.guild
        self.author = interaction.user
        self.channel = interaction.channel
        self.notices = []

    async def send(self, content = None, embed = None, **kwargs):
        self.notices.append(content if content is not None else f'❌ {embed.description}')

    @property
    def notice(self):
        return '\n'.join(self.notices) or None

class Field:
    # one box on a Form
    def __init__(self, label, placeholder = None, default = None, long = False, required = True, maxLength = None):
        self.label = label
        self.placeholder = placeholder
        self.default = default
        self.long = long
        self.required = required
        self.maxLength = maxLength

class Form(nextcord.ui.Modal):
    # A form opened by a button, for anything typed. onSubmit gets the submit and each box's text in
    # order, with an empty optional box as ''. A form can't follow a deferral, so whatever opens one
    # has to do it first, and leaves its checks to onSubmit.
    def __init__(self, title, fields, onSubmit):
        super().__init__(title = title[:FORM_TITLE_LIMIT], timeout = GBotPropertiesManager.USER_RESPONSE_TIMEOUT_SECONDS)
        self.onSubmit = onSubmit
        self.inputs = []
        for field in fields:
            kwargs = {'max_length': field.maxLength} if field.maxLength else {}
            box = nextcord.ui.TextInput(label = field.label[:FORM_LABEL_LIMIT], style = nextcord.TextInputStyle.paragraph if field.long else nextcord.TextInputStyle.short, placeholder = field.placeholder, default_value = field.default, required = field.required, **kwargs)
            self.inputs.append(box)
            self.add_item(box)

    async def callback(self, interaction: nextcord.Interaction):
        values = [(box.value or '').strip() for box in self.inputs]
        # Discord takes spaces as filled in, and a blank name or pattern would be saved
        blank = next((box.label for box, value in zip(self.inputs, values) if box.required and not value), None)
        if blank:
            await presentation.sendReply(interaction, embed = presentation.errorEmbed(description = f'Please fill in **{blank}**, with more than spaces.'), ephemeral = True)
            return
        await self.onSubmit(interaction, values)

    async def on_error(self, error, interaction):
        await presentation.sendInteractionError(interaction, error)

class OpenView(OwnedView):
    # The one-liner a prefix command posts for a private card. Discord only allows a private reply to
    # an interaction, and a prefix command is a plain message, so the press is what makes it private.
    # Anyone can press it: its owner gets their card and the one-liner tidies itself away, and anyone
    # else gets their own version, as if they had typed the command themselves.
    def __init__(self, opener, feature, admin):
        super().__init__()
        self.opener = opener
        self.feature = feature
        self.admin = admin
        self.command = None
        self.button('🔒', self.open, label = 'Open', style = nextcord.ButtonStyle.primary)

    async def interaction_check(self, interaction):
        return True

    async def open(self, interaction: nextcord.Interaction):
        await interaction.response.defer(ephemeral = True)
        await predicates.recheck(interaction, feature = self.feature, admin = self.admin)
        await self.opener(interaction, interaction.user)
        if interaction.user.id == self.ownerId:
            self.stop()
            await self.tidy()

    async def on_timeout(self):
        await self.tidy()

    async def tidy(self):
        # the prefix message goes too, where GBot may manage messages
        for message in (self.message, self.command):
            try:
                await message.delete()
            except nextcord.HTTPException:
                pass

async def openPrivately(context, emoji, what, opener, feature = None, admin = False):
    # Opens a private card: straight away for a slash command, which can be private, or through a
    # one-liner for a prefix one. opener(context, author) sends the card, ephemeral where it can be.
    if isinstance(context, nextcord.Interaction):
        await opener(context, context.user)
        return
    view = OpenView(opener, feature, admin)
    view.command = context.message
    await view.send(context, False, content = f'{emoji} {what} for **{context.author.display_name}**. Press 🔒 Open to see it privately.', view = view)

def persistentButton(label, emoji, style, customId, disabled = False):
    # A button on a message that lives on: its id says what it is for, and a cog's on_interaction
    # answers it, so it keeps working after a restart. See sendPersistent.
    return nextcord.ui.Button(label = label, emoji = emoji, style = style, custom_id = customId, disabled = disabled)

def persistentView(buttons):
    # not auto-deferred, as the cog's listener answers every press
    view = nextcord.ui.View(timeout = None, auto_defer = False)
    for button in buttons:
        view.add_item(button)
    return view

def stopped(view):
    # Stopped once sent or edited onto a message, so it never sits in nextcord's view store, where it
    # would answer first and stay until a restart.
    view.stop()
    return view

def persistentParts(interaction, prefix):
    # the rest of a pressed persistent button's id, split on ':', or None if it isn't one of prefix's
    if interaction.type != nextcord.InteractionType.component:
        return None
    customId = (interaction.data or {}).get('custom_id', '')
    if not customId.startswith(prefix):
        return None
    return customId[len(prefix):].split(':')
