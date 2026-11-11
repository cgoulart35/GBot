#region IMPORTS
import contextvars
import logging
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import nextcord

from GBotDiscord.src import pagination
from GBotDiscord.src import predicates
from GBotDiscord.src import utils
from GBotDiscord.src import presentation
from GBotDiscord.src import strings
from GBotDiscord.src.agent import agent_client
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.firebase import GBotFirebaseService
from GBotDiscord.src import access
from GBotDiscord.src import server_setup
from GBotDiscord.src.gcoin import gcoin_cog, gcoin_queries
from GBotDiscord.src.gtrade import gtrade_cog
from GBotDiscord.src.hype import hype_cog, hype_queries
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.gtrade import gtrade_queries
from GBotDiscord.src.help import help_cog
from GBotDiscord.src.leaderboards import leaderboards_queries
from GBotDiscord.src.reminders import reminders_cog, reminders_queries, when
#endregion

# What the agent can look up and do for the sender, at its channel's abilities level. Each tool shows
# or does only what the sender could see or do with the command, behind the same feature toggle, and
# checked here in code whatever the model asked for. Nothing here moves GCoin or items, or changes
# anyone else's things below `all`, where each of those only posts a confirm card for the sender.

MAX_ROWS = 25
# per message, as a chat message is easier to set off by accident than a command
MAX_ACTIONS_PER_REPLY = 3
# what the agent is told when a message asks for more than it does from one: the sender hears it too
CAPPED = f'You can only do {MAX_ACTIONS_PER_REPLY} things per message.'
ONE_SEND = 'GCoin goes to one person per message, so this one was not offered.'
MAX_QUERY_CHARACTERS = 300

# the toggle each tool sits behind, as its command does
TOGGLES = {
    agent_client.TOOL_GET_WALLET: 'toggle_gcoin',
    agent_client.TOOL_GET_RANKING: 'toggle_gcoin',
    agent_client.TOOL_SEARCH_MARKET: 'toggle_gtrade',
    agent_client.TOOL_GET_ITEMS: 'toggle_gtrade',
    agent_client.TOOL_SHOW_ITEM: 'toggle_gtrade',
    agent_client.TOOL_GET_MUSIC_QUEUE: 'toggle_music',
    agent_client.TOOL_GET_REMINDERS: 'toggle_reminders',
    agent_client.TOOL_PLAY_MUSIC: 'toggle_music',
    agent_client.TOOL_CONTROL_MUSIC: 'toggle_music',
    agent_client.TOOL_SET_REMINDER: 'toggle_reminders',
    agent_client.TOOL_DELETE_REMINDER: 'toggle_reminders',
    agent_client.TOOL_GUESS_STORM: 'toggle_storms',
    agent_client.TOOL_BET_STORM: 'toggle_storms',
    agent_client.TOOL_SEND_GCOIN: 'toggle_gcoin',
    agent_client.TOOL_BUY_ITEM: 'toggle_gtrade',
    agent_client.TOOL_SELL_ITEM: 'toggle_gtrade',
    agent_client.TOOL_GET_HISTORY: 'toggle_gcoin',
    agent_client.TOOL_HYPE_LOOKUP: 'toggle_hype',
    agent_client.TOOL_STORM_STATUS: 'toggle_storms',
    agent_client.TOOL_STORM_UMBRELLA: 'toggle_storms',
    agent_client.TOOL_WHO_DIS: 'toggle_who_dis',
    agent_client.TOOL_EDIT_MUSIC: 'toggle_music',
    agent_client.TOOL_RENAME_ITEM: 'toggle_gtrade',
    agent_client.TOOL_HYPE_CHANGE: 'toggle_hype',
    agent_client.TOOL_CRAFT_ITEM: 'toggle_gtrade',
    agent_client.TOOL_DESTROY_ITEM: 'toggle_gtrade',
    agent_client.TOOL_ANSWER_TRADE: 'toggle_gtrade',
    agent_client.TOOL_REMIND_ROLE: 'toggle_reminders',
    agent_client.TOOL_SET_TIMEZONE: 'toggle_reminders',
}
# for admins only, as their commands are
ADMIN_TOOLS = {agent_client.TOOL_HYPE_LOOKUP, agent_client.TOOL_HYPE_CHANGE, agent_client.TOOL_REMIND_ROLE, agent_client.TOOL_SET_CONFIG, agent_client.TOOL_AGENT_SETTING, agent_client.TOOL_SET_FEATURE}
OPENS = 'Posted the 🔒 Open button, which shows it to them privately, as this is private. It is your whole reply, so nothing you write is shown.'
CONFIRM_POSTED = 'Posted a card with the button they press, and nothing happens until they press it. The card is your whole reply, so nothing you write is shown.'
CONFIRM_ADDED = 'Added to the confirm card already posted for this message, which now lists it too: one press does them all. The card is your whole reply, so nothing you write is shown.'
GUESSED = 'Guessed. GBot posted the result, which is your whole reply, so nothing you write is shown.'
SHOWN = 'Shown. The item\'s card is your whole reply, so nothing you write is shown.'

NOBODY = 'There is nobody by that name here.'
# a message about Who Dis, which is deleted as who plays is the secret
WHO_DIS_WORDS = ('who dis', 'whodis', 'who-dis')
# the cards a prefix command posts in the channel rather than privately, so the agent does too
PUBLIC_CARDS = {
    'GCoin': lambda cog, context, author: cog.commonWallet(context, author, None),
    'Storms': lambda cog, context, author: cog.commonStatus(context),
}
# the cards posted as the reply to one message, which then stand for the agent's words: per task, as several messages are answered at once
CARDS = contextvars.ContextVar('cards', default = None)
# that message's confirm card, which any further confirm joins, so one message gets one card to press
CONFIRM = contextvars.ContextVar('confirm', default = None)

def addCard(posted):
    # a message that stands for the agent's reply, so its words aren't also sent; outside a run, nothing collects it
    cards = CARDS.get()
    if cards is not None:
        cards.append(posted)

def findMember(guild, text):
    # an id from <people>, or a name that matches exactly one member
    if text.isdecimal():
        return guild.get_member(int(text))
    wanted = text.lstrip('@').casefold()
    matches = [member for member in guild.members if wanted in (member.name.casefold(), member.display_name.casefold())]
    return matches[0] if len(matches) == 1 else None

class AgentConfirm(pagination.OwnedView):
    # The confirm card for anything at the `all` level, posted by code rather than written by the model.
    # Only the sender can press it, it times out, and the press is checked again as the command would be.
    # Several asked for in one message share one card: each is listed, and one press does them all.
    def __init__(self, ownerId, toggle, admin, action, title = None, description = None, feature = None, image = None):
        super().__init__()
        self.ownerId = ownerId
        # shown while it's the card's only one, as crafting's picture is
        self.image = image
        # (title, description, toggle, admin, action), where action(interaction) does it and says what happened
        self.entries = [(title, description, toggle, admin, action)]
        # how many the card shows: a press runs only those, never one added while it was being edited
        self.shown = 1
        self.feature = feature
        self.pressed = False
        self.button('✅', self.confirmed, label = 'Confirm', style = nextcord.ButtonStyle.success)
        self.button('❌', self.cancelled, label = 'Cancel')

    def add(self, title, description, toggle, admin, action, feature):
        self.entries.append((title, description, toggle, admin, action))
        if feature != self.feature:
            self.feature = 'Agent'

    def embed(self):
        if len(self.entries) == 1:
            title, description, *_ = self.entries[0]
            embed = presentation.warningEmbed(title = title, description = description, feature = self.feature)
            if self.image:
                embed.set_image(url = self.image)
            return embed
        listed = '\n\n'.join(f'**{title}**\n{description}' for title, description, *_ in self.entries)
        return presentation.warningEmbed(title = f'Confirm these {len(self.entries)}?', description = listed[:4096], feature = self.feature)

    async def confirmed(self, interaction):
        # before anything is awaited: a double click is dispatched before the view could stop
        if self.pressed:
            await interaction.response.defer()
            return
        self.pressed = True
        await interaction.response.defer()
        entries = self.entries[:self.shown]
        if len(entries) == 1:
            _, _, toggle, admin, action = entries[0]
            try:
                await predicates.recheck(interaction, feature = toggle, admin = admin)
            except Exception:
                self.pressed = False
                raise
            self.stop()
            text = await action(interaction)
        else:
            self.stop()
            # each checked again as its own command would be: one refused doesn't stop the rest
            results = []
            for title, _, toggle, admin, action in entries:
                try:
                    await predicates.recheck(interaction, feature = toggle, admin = admin)
                except Exception as e:
                    results.append(f"❌ {presentation.describeCommandError(e, interaction.user.mention) or 'That was refused.'}")
                    continue
                try:
                    results.append(await action(interaction))
                except Exception as e:
                    # one failing doesn't cost the rest their turn, or the card its answer
                    logging.getLogger().error(f'GBot Agent failed a confirmed action ({title}): {type(e).__name__}')
                    results.append(f"❌ {title.rstrip('?')} didn't work. Try its command instead.")
            text = '\n'.join(results)
        await interaction.edit_original_message(content = text[:2000], embed = None, view = None)

    async def cancelled(self, interaction):
        self.stop()
        await interaction.response.edit_message(content = '🚫 Cancelled, so nothing happened.', embed = None, view = None)

class AgentSendFlow(gcoin_cog.SendFlow):
    # GCoin's send, posted in the channel rather than privately: the card itself becomes the public
    # announcement once sent, rather than saying "You sent" with the announcement beside it
    async def confirmed(self, interaction):
        if self.sent:
            await interaction.response.defer()
            return
        self.sent = True
        self.stop()
        await interaction.response.defer()
        await predicates.recheck(interaction, feature = 'toggle_gcoin')
        async def announce(text):
            await interaction.edit_original_message(content = text, embed = None, view = None)
        problem = await self.cog.transfer(SimpleNamespace(send = announce, id = interaction.channel.id), self.author, self.receiver, self.amount, self.note)
        if problem:
            await interaction.edit_original_message(content = f'❌ {problem}', embed = None, view = None)

class AgentAbilities:

    def __init__(self, client):
        self.client = client
        self.logger = logging.getLogger()


    async def run(self, name, toolInput, msg, isAdmin, actions, cards = None):
        toggle = TOGGLES.get(name)
        if toggle is not None and await GBotFirebaseService.run(config_queries.getServerValue, msg.guild.id, toggle) is not True:
            return f'{strings.FEATURE_NAMES[toggle]} is turned off in this server.', True
        # refused before it's counted, so a member's admin-only ask doesn't use up an action
        if name in ADMIN_TOOLS and not isAdmin:
            return 'Only admins can do that.', True
        if name in agent_client.ACTING_TOOLS:
            if len(actions) >= MAX_ACTIONS_PER_REPLY:
                return CAPPED, True
            # money to one person at a time: "send everyone 5 GCoin" is what a misread message could do
            if name == agent_client.TOOL_SEND_GCOIN and name in actions:
                return ONE_SEND, True
            actions.append(name)
        handler = {
            agent_client.TOOL_GET_WALLET: self.wallet,
            agent_client.TOOL_GET_RANKING: self.ranking,
            agent_client.TOOL_SEARCH_MARKET: self.market,
            agent_client.TOOL_GET_ITEMS: self.items,
            agent_client.TOOL_SHOW_ITEM: self.showItem,
            agent_client.TOOL_GET_MUSIC_QUEUE: self.musicQueue,
            agent_client.TOOL_GET_FEATURES: self.features,
            agent_client.TOOL_GET_REMINDERS: self.reminders,
            agent_client.TOOL_PLAY_MUSIC: self.playMusic,
            agent_client.TOOL_CONTROL_MUSIC: self.controlMusic,
            agent_client.TOOL_SET_REMINDER: self.setReminder,
            agent_client.TOOL_DELETE_REMINDER: self.deleteReminder,
            agent_client.TOOL_SEND_GCOIN: self.sendGCoin,
            agent_client.TOOL_BUY_ITEM: self.buyItem,
            agent_client.TOOL_SELL_ITEM: self.sellItem,
            agent_client.TOOL_SET_FEATURE: self.setFeature,
            agent_client.TOOL_GUESS_STORM: self.guessStorm,
            agent_client.TOOL_BET_STORM: self.betStorm,
            agent_client.TOOL_GET_HISTORY: self.history,
            agent_client.TOOL_OPEN_CARD: self.openCard,
            agent_client.TOOL_HYPE_LOOKUP: self.hypeLookup,
            agent_client.TOOL_STORM_STATUS: self.stormStatus,
            agent_client.TOOL_STORM_UMBRELLA: self.stormUmbrella,
            agent_client.TOOL_WHO_DIS: self.whoDis,
            agent_client.TOOL_EDIT_MUSIC: self.editMusic,
            agent_client.TOOL_RENAME_ITEM: self.renameItem,
            agent_client.TOOL_HYPE_CHANGE: self.hypeChange,
            agent_client.TOOL_CRAFT_ITEM: self.craftItem,
            agent_client.TOOL_DESTROY_ITEM: self.destroyItem,
            agent_client.TOOL_ANSWER_TRADE: self.answerTrade,
            agent_client.TOOL_REMIND_ROLE: self.remindRole,
            agent_client.TOOL_SET_CONFIG: self.setConfig,
            agent_client.TOOL_REPORT: self.report,
            agent_client.TOOL_AGENT_SETTING: self.agentSetting,
            agent_client.TOOL_PATREON: self.patreon,
            agent_client.TOOL_SET_TIMEZONE: self.setTimezone,
        }[name]
        # set every time, so a run without a list never adds to an earlier one's, and a new
        # message's confirms start a card of their own
        if CARDS.get() is not cards:
            CONFIRM.set(None)
        CARDS.set(cards)
        return await handler(toolInput, msg, isAdmin)

    async def setTimezone(self, toolInput, msg, isAdmin):
        # the Agent cog's, which its own tests cover; here so it's counted and behind Reminders like the rest
        return await self.client.get_cog('Agent').toolSetTimezone(toolInput, msg)

    def member(self, toolInput, msg, key = 'user'):
        wanted = toolInput.get(key)
        if not isinstance(wanted, str):
            return None
        member = findMember(msg.guild, wanted.strip()) if wanted.strip() else msg.author
        return None if member is None or member.bot else member

    # read

    async def wallet(self, toolInput, msg, isAdmin):
        member = self.member(toolInput, msg)
        if member is None:
            return NOBODY, True
        balance = await GBotFirebaseService.run(gcoin_queries.getUserBalance, member.id)
        return f'{member.display_name}: {presentation.formatGCoin(balance)} GCoin', False

    async def ranking(self, toolInput, msg, isAdmin):
        # the table covers every server, and only this server's members are this server's business
        table = await GBotFirebaseService.run(leaderboards_queries.getLeaderboard) or {}
        rows = []
        for userId, row in table.items():
            member = msg.guild.get_member(int(userId))
            if member is not None:
                rows.append((Decimal(row.get('balance', '0')), member.display_name, row))
        rows.sort(key = lambda found: found[0], reverse = True)
        lines = [f"{name}: {presentation.formatGCoin(balance)} GCoin, {row.get('numStormWins', 0)} Storm wins, {row.get('numWhoDisWins', 0)} Who Dis wins" for balance, name, row in rows[:MAX_ROWS]]
        return '\n'.join(lines) or 'Nobody here is on the ranking yet.', False

    async def market(self, toolInput, msg, isAdmin):
        text = toolInput.get('text') if isinstance(toolInput.get('text'), str) else ''
        maxPrice = toolInput.get('max_price') if isinstance(toolInput.get('max_price'), str) else ''
        try:
            limit = presentation.parseGCoin(maxPrice) if maxPrice.strip() else None
        except InvalidOperation:
            return 'That is not a price.', True
        pending = await GBotFirebaseService.run(gtrade_queries.getAllServerPendingTradeTransactions, msg.guild.id) or {}
        found = []
        for trade in pending.values():
            # requests between two people are theirs: only the open market is for everyone
            if trade['trxType'] != 'market':
                continue
            item = trade['item']
            value = Decimal(str(item['value']))
            if text.strip().casefold() not in item['name'].casefold() or (limit is not None and value > limit):
                continue
            seller = msg.guild.get_member(int(trade['sellerId']))
            found.append((value, f"{item['name']}: {presentation.formatGCoin(value)} GCoin, sold by {seller.display_name if seller is not None else 'a former member'}"))
        found.sort(key = lambda entry: entry[0])
        lines = [line for _, line in found[:MAX_ROWS]]
        if len(found) > MAX_ROWS:
            lines.append(f'...and {len(found) - MAX_ROWS} more.')
        return '\n'.join(lines) or 'Nothing like that is for sale.', False

    async def items(self, toolInput, msg, isAdmin):
        member = self.member(toolInput, msg)
        if member is None:
            return NOBODY, True
        owned = await GBotFirebaseService.run(gtrade_queries.getAllUserItems, member.id) or {}
        lines = [f"{item['name']}: worth {presentation.formatGCoin(Decimal(str(item['value'])))} GCoin" for item in list(owned.values())[:MAX_ROWS]]
        if len(owned) > MAX_ROWS:
            lines.append(f'...and {len(owned) - MAX_ROWS} more.')
        return f"{member.display_name} has " + ('\n'.join(lines) if lines else 'no items.'), False

    async def musicQueue(self, toolInput, msg, isAdmin):
        return self.client.get_cog('Music').describeForAgent(str(msg.guild.id), MAX_ROWS), False

    async def features(self, toolInput, msg, isAdmin):
        lines = []
        for feature in help_cog.FEATURES:
            if feature.toggle is not None:
                isOn = await GBotFirebaseService.run(help_cog.isFeatureOn, feature, msg.guild)
                lines.append(f"{feature.name}: {'on' if isOn else 'off'}")
        return '\n'.join(lines), False

    async def openPrivately(self, msg, title, opener, toggle, admin = False, onlySender = False, named = True):
        # named = False: an anonymous one-liner for a message already hidden, as a report's is
        # What a prefix command shows only privately, it offers through its 🔒 Open one-liner, as only a
        # press can be answered privately. So does the agent, rather than DMs. opener(interaction, user)
        if onlySender:
            inner = opener
            async def opener(interaction, user):
                # a report is only ever the sender's to make
                if user.id != msg.author.id:
                    await presentation.sendError(interaction, f'Sorry {user.mention}, this is only for {msg.author.display_name}.' if named else f"Sorry {user.mention}, this isn't yours to open.")
                    return
                await inner(interaction, user)
        view = pagination.OpenView(opener, toggle, admin)
        # tidied away with the button once they open it, as a prefix command's is, unless already hidden
        view.command = msg if named else None
        posted = await view.send(SimpleNamespace(author = msg.author, send = msg.channel.send), False, content = (f'{title} for **{msg.author.display_name}**' if named else title) + '. Press 🔒 Open to see it privately.', view = view)
        addCard(posted)
        return OPENS, False

    def channelContext(self, msg):
        # what a prefix command in this channel passes its engine: its public answer is the agent's whole reply
        async def send(content = None, **kwargs):
            posted = await msg.channel.send(content, **kwargs)
            addCard(posted)
            return posted
        return SimpleNamespace(guild = msg.guild, channel = msg.channel, author = msg.author, message = msg, send = send)

    async def reminders(self, toolInput, msg, isAdmin):
        # only the sender's own, and only their ids and times: what they say is private, as /remind
        # shows them privately, so showing them is open_card's 🔒 Open
        zone = reminders_cog.zoneOrUtc(await GBotFirebaseService.run(reminders_queries.getTimezone, msg.author.id))
        found = [(reminderId, reminder) for reminderId, reminder in reminders_cog.soonest(await GBotFirebaseService.run(reminders_queries.getServerReminders, msg.guild.id)) if reminder['userId'] == str(msg.author.id)]
        if not found:
            return 'They have no reminders here.', False
        ids = '\n'.join(f"id {reminderId}: {reminders_cog.describeWhen(reminder, zone)}{' (a snooze)' if reminders_cog.isSnoozed(reminder) else ''}" for reminderId, reminder in found[:MAX_ROWS])
        return f'What they say is private, so to show them use {agent_client.TOOL_OPEN_CARD} with Reminders. Their ids and times:\n{ids}', False

    # safe

    def musicContext(self, msg):
        # what the music card's buttons pass its engines, so the agent goes through their checks and
        # locks, and what they'd have said shows on the now-playing card rather than as a new message
        return SimpleNamespace(guild = msg.guild, user = msg.author, channel = msg.channel)

    async def runMusic(self, msg, engine):
        reply = pagination.CardReply(self.musicContext(msg))
        music = self.client.get_cog('Music')
        serverId = str(msg.guild.id)
        # what the card was before, so a card the engine has just posted isn't posted again
        before = (music.musicStates.get(serverId) or {}).get('card')
        try:
            await engine(music, reply)
        except Exception as e:
            self.logger.error(f'GBot Agent failed a music action in server {msg.guild.id}: {type(e).__name__}')
            return 'That didn\'t work. Tell them to try /music.', True
        notice = reply.notice or ''
        if notice.startswith('❌'):
            return notice[2:], True
        if not notice:
            # it started playing, so the now-playing card just posted is the whole reply
            addCard(msg)
            return 'It is playing now. The now-playing card GBot posted is your whole reply, so nothing you write is shown.', False
        musicState = music.musicStates.get(serverId) or {}
        if musicState.get('card') is None:
            # the session ended, as a Stop does, so there is no card to show it on
            return f'Done: {notice} Say so in a few words.', False
        # as a typed command does: the card comes down to the bottom with what happened on it
        musicState['lastAction'] = f'{notice} · {msg.author.display_name}'
        if musicState['card'] is before:
            await music.postCard(serverId, msg.channel, moveDown = True)
        else:
            # already new at the bottom, as a playlist started from idle posts it: only its line changes
            await music.updateCard(serverId)
        addCard(msg)
        return f'Done: {notice} The music card, moved to the bottom with that on it, is your whole reply, so nothing you write is shown.', False

    async def playMusic(self, toolInput, msg, isAdmin):
        query = toolInput.get('query')
        if isinstance(query, str) and not query.strip():
            # "play" with nothing to search for carries on with what is paused
            return await self.controlMusic({'action': 'resume'}, msg, isAdmin)
        if not isinstance(query, str) or len(query) > MAX_QUERY_CHARACTERS:
            return 'That is not something to search for.', True
        if msg.author.voice is None:
            return 'The sender has to be in a voice channel for this, so nothing happened. Tell them that.', True
        return await self.runMusic(msg, lambda music, reply: music.commonPlay(reply, msg.author, [query.strip()]))

    async def controlMusic(self, toolInput, msg, isAdmin):
        action = toolInput.get('action')
        if action not in agent_client.MUSIC_ACTIONS:
            return 'That is not something you can do to the music.', True
        # as the music card's buttons: only someone listening can change it
        problem = self.client.get_cog('Music').listenerProblem(self.musicContext(msg))
        if problem:
            return f'{problem} So nothing happened. Tell them that.', True
        return await self.runMusic(msg, lambda music, reply: getattr(music, f'common{action.capitalize()}')(reply, msg.author))

    async def setReminder(self, toolInput, msg, isAdmin):
        values = [toolInput.get(key) for key in ('when', 'what', 'repeat', 'where')]
        if not all(isinstance(value, str) and value.strip() for value in values) or values[2] not in when.REPEATS or values[3] not in reminders_cog.WHERES:
            return 'A reminder needs when, what, repeat and where.', True
        values[2] = self.repeatOf(toolInput)
        zoneName = await GBotFirebaseService.run(reminders_queries.getTimezone, msg.author.id)
        if zoneName is None:
            return f'They haven\'t set a time zone. Ask where they are, use {agent_client.TOOL_SET_TIMEZONE}, then set the reminder.', True
        reminders = self.client.get_cog('Reminders')
        try:
            reminder = reminders.makeReminder(msg.author, msg.channel.id, ZoneInfo(zoneName), *values, None)
            await reminders.saveReminder(msg.guild.id, reminder)
        except when.ReminderProblem as problem:
            return f'Nothing was set: {problem}', True
        moment = reminders_cog.momentOf(reminder['nextAt'])
        if moment <= reminders_cog.utcNow():
            return f"Set for now, the minute they named, so it goes off right away, {'by DM' if values[3] == reminders_cog.DM else 'here'}. Tell them.", False
        return f"Set for {when.formatMoment(moment, ZoneInfo(zoneName), reminders_cog.utcNow())} in their time, {when.repeatPhrase(moment, reminder['repeat'], ZoneInfo(zoneName))}, {'by DM' if values[3] == reminders_cog.DM else 'here'}. Tell them when.", False

    def repeatOf(self, toolInput):
        # a "days" repeat carries the weekdays it goes off on; makeReminder refuses one without any
        if toolInput.get('repeat') != when.DAYS:
            return toolInput['repeat']
        days = toolInput.get('days') if isinstance(toolInput.get('days'), list) else []
        return when.DAYS, [agent_client.WEEKDAY_CHOICES.index(day) for day in days if day in agent_client.WEEKDAY_CHOICES]

    async def deleteReminder(self, toolInput, msg, isAdmin):
        # any number of the sender's own, under one confirm, as "delete all my reminders" asks
        ids = [reminderId for reminderId in dict.fromkeys(toolInput.get('ids') or []) if isinstance(reminderId, str) and reminderId] if isinstance(toolInput.get('ids'), list) else []
        everything = await GBotFirebaseService.run(reminders_queries.getServerReminders, msg.guild.id) or {}
        # only the sender's own, whoever asked
        mine = [(reminderId, everything[reminderId]) for reminderId in ids if reminderId in everything and everything[reminderId]['userId'] == str(msg.author.id)]
        if not mine:
            return f'None of those are the sender\'s reminder ids. Use {agent_client.TOOL_GET_REMINDERS} for their ids, then try again.', True
        zone = reminders_cog.zoneOrUtc(await GBotFirebaseService.run(reminders_queries.getTimezone, msg.author.id))
        times = [reminders_cog.describeWhen(reminder, zone) for _, reminder in mine]
        async def delete(interaction):
            # those still theirs, and still there, in one step
            def remove():
                current = reminders_queries.getServerReminders(interaction.guild.id) or {}
                gone = [reminderId for reminderId, _ in mine if reminderId in current and current[reminderId]['userId'] == str(interaction.user.id)]
                for reminderId in gone:
                    reminders_queries.removeReminder(interaction.guild.id, reminderId)
                return len(gone)
            removed = await GBotFirebaseService.run(remove)
            if removed == 0:
                return '❌ That reminder is gone already.' if len(mine) == 1 else '❌ Those reminders are gone already.'
            if len(mine) == 1:
                return f'🗑️ Deleted your reminder for {times[0]}.'
            return f'🗑️ Deleted your {removed} reminders.' + ('' if removed == len(mine) else ' The rest were gone already.')
        # a deletion can't be undone, so it's confirmed. Only their times show, as what they say is private.
        if len(mine) == 1:
            return await self.confirmCard(msg, f'🗑️ Delete your reminder for {times[0]}?', 'It can\'t be undone.', 'Reminders', reminders_cog.TOGGLE, delete)
        listed = '\n'.join(f'• {time}' for time in times)
        return await self.confirmCard(msg, f'🗑️ Delete your {len(mine)} reminders?', f"{listed}\n\nThey can't be undone.", 'Reminders', reminders_cog.TOGGLE, delete)

    # all: each only posts a confirm card

    async def postConfirm(self, msg, embed, view, asReply = True):
        view.message = await self.postCard(msg, embed, view, asReply)
        return CONFIRM_POSTED, False

    async def postCard(self, msg, embed, view = None, asReply = True):
        # The card is the whole reply: one message, so the agent's words aren't sent beside it. Not as a
        # reply once the message has been deleted, as Discord refuses a reply to one that's gone.
        posted = None
        if asReply:
            try:
                posted = await msg.reply(embed = embed, view = view, allowed_mentions = nextcord.AllowedMentions.none())
            except nextcord.HTTPException:
                # an earlier tool in this reply deleted their message, so it can't be replied to
                posted = None
        if posted is None:
            posted = await msg.channel.send(embed = embed, view = view, allowed_mentions = nextcord.AllowedMentions.none())
        addCard(posted)
        return posted

    async def confirmCard(self, msg, title, description, feature, toggle, action, admin = False, asReply = True, image = None):
        # One message, one card: a further confirm joins the card already posted for it
        posted = CONFIRM.get()
        if posted is not None and not posted.pressed and not posted.is_finished():
            posted.add(title, description, toggle, admin, action, feature)
            await posted.message.edit(embed = posted.embed(), view = posted)
            posted.shown = len(posted.entries)
            return CONFIRM_ADDED, False
        view = AgentConfirm(msg.author.id, toggle, admin, action, title, description, feature, image)
        result = await self.postConfirm(msg, view.embed(), view, asReply)
        CONFIRM.set(view)
        return result

    async def sendGCoin(self, toolInput, msg, isAdmin):
        member = self.member(toolInput, msg)
        amount = toolInput.get('amount')
        note = toolInput.get('note') if isinstance(toolInput.get('note'), str) else ''
        if member is None or member.id == msg.author.id:
            return NOBODY if member is None else 'They can\'t send GCoin to themselves.', True
        gcoin = self.client.get_cog('GCoin')
        problem = gcoin.receiverProblem(msg.author, member, msg.guild)
        if problem is None:
            problem = (await gcoin.checkSend(msg.author, member, amount if isinstance(amount, str) else ''))[0]
        if problem:
            return f'Nothing was sent: {problem}', True
        # GCoin's own send flow, from its confirm on: the same card, checks and transfer as 💸 Send
        flow = AgentSendFlow(gcoin, msg.guild, msg.author)
        flow.receiver = member
        embed = await flow.prepare([amount, note.strip()])
        return await self.postConfirm(msg, embed, flow)

    def gtradeAction(self, engine, item, other):
        async def action(interaction):
            reply = pagination.CardReply(interaction)
            await engine(reply, interaction.user, item, other)
            return reply.notice or '✅ Done.'
        return action

    async def ownedItem(self, owner, item):
        # (the item, or None, and what to say when it's None). People type names loosely: the exact name
        # whatever its case, or else the one item whose name holds what they typed. GTrade gets the
        # item's own name. A miss lists the names, so the agent can try again without a lookup.
        owned = list((await GBotFirebaseService.run(gtrade_queries.getAllUserItems, owner.id) or {}).values())
        wanted = item.strip().casefold() if isinstance(item, str) else ''
        if wanted:
            exact = [found for found in owned if found['name'].casefold() == wanted]
            close = exact or [found for found in owned if wanted in found['name'].casefold()]
            if len(close) == 1:
                return close[0], None
            if close:
                return None, f"More than one of {owner.display_name}'s items matches that: {', '.join(found['name'] for found in close[:MAX_ROWS])}. Ask which."
        names = ', '.join(found['name'] for found in owned[:MAX_ROWS])
        return None, f"{owner.display_name} has no item called that. Their items: {names}." if names else f'{owner.display_name} has no items.'

    async def buyItem(self, toolInput, msg, isAdmin):
        owner = self.member(toolInput, msg, 'owner')
        if owner is None or owner.id == msg.author.id:
            return NOBODY if owner is None else 'They already own it.', True
        found, problem = await self.ownedItem(owner, toolInput.get('item'))
        if found is None:
            return problem, True
        item = found['name']
        price = utils.roundDecimalPlaces(found['value'], 2)
        balance = await GBotFirebaseService.run(gcoin_queries.getUserBalance, msg.author.id)
        buy = self.gtradeAction(self.client.get_cog('GTrade').commonBuy, item, owner)
        async def buyAtThatPrice(interaction):
            # the item is found by name when pressed, so a rename or a new price since would buy something else
            still, _ = await self.ownedItem(owner, item)
            if still is None or still['name'] != item or utils.roundDecimalPlaces(still['value'], 2) != price:
                return f'⌛ {item} changed since this was asked, so nothing was bought. Ask again for its current price.'
            return await buy(interaction)
        return await self.confirmCard(msg, f"🛒 Buy {item} from {owner.display_name} for {presentation.formatGCoin(price)} GCoin?",
                                      f"You'll have **{presentation.formatGCoin(balance - price)} GCoin** left, once they accept or if it's on the market.", 'GTrade', 'toggle_gtrade', buyAtThatPrice)

    async def sellItem(self, toolInput, msg, isAdmin):
        found, problem = await self.ownedItem(msg.author, toolInput.get('item'))
        if found is None:
            return problem, True
        item = found['name']
        price = presentation.formatGCoin(utils.roundDecimalPlaces(found['value'], 2))
        buyerText = toolInput.get('buyer') if isinstance(toolInput.get('buyer'), str) else ''
        buyer = None
        if buyerText.strip():
            buyer = self.member(toolInput, msg, 'buyer')
            if buyer is None or buyer.id == msg.author.id:
                return NOBODY if buyer is None else 'They can\'t sell to themselves.', True
            title = f'🤝 Offer {item} to {buyer.display_name} for {price} GCoin?'
        elif await GBotFirebaseService.run(gtrade_queries.getPendingTradeTransaction, msg.guild.id, 'market', item, msg.author.id) is not None:
            title = f'🚫 Take {item} off the market?'
        else:
            title = f'🏷️ Put {item} up for sale for {price} GCoin?'
        return await self.confirmCard(msg, title, 'Its value sets the price.', 'GTrade', 'toggle_gtrade', self.gtradeAction(self.client.get_cog('GTrade').commonSell, item, buyer))

    async def setFeature(self, toolInput, msg, isAdmin):
        # any number of them, as "turn off music and storms" asks, under one confirm
        wanted = toolInput.get('features') if isinstance(toolInput.get('features'), list) else []
        toggles = list(dict.fromkeys(next((toggle for toggle, name in strings.FEATURE_NAMES.items() if name == feature and name in agent_client.SWITCHABLE_FEATURES), None) for feature in wanted))
        setting = toolInput.get('setting')
        if not toggles or None in toggles or setting not in ('on', 'off'):
            return 'That is not a feature the agent can switch.', True
        current = [(toggle, await GBotFirebaseService.run(config_queries.getServerValue, msg.guild.id, toggle)) for toggle in toggles]
        toggles = [toggle for toggle, value in current if bool(value) != (setting == 'on')]
        if not toggles:
            return f"{' and '.join(strings.FEATURE_NAMES[toggle] for toggle, _ in current)} {'is' if len(current) == 1 else 'are'} already {setting}.", True
        config = self.client.get_cog('Config')
        async def action(interaction):
            # Config's own switch, so what a feature needs, or what needs it, switches with it
            lines = []
            for toggle in toggles:
                stillThere = await GBotFirebaseService.run(config_queries.getServerValue, interaction.guild.id, toggle)
                if bool(stillThere) == (setting == 'on'):
                    lines.append(f'{strings.FEATURE_NAMES[toggle]} is already {setting}.')
                else:
                    lines.append(await config.toggleFeature(interaction, toggle))
            return '\n'.join(lines)
        names = [strings.FEATURE_NAMES[toggle] for toggle in toggles]
        title = f'{strings.FEATURE_EMOJIS[toggles[0]]} Turn {setting} {names[0]}?' if len(names) == 1 else f"⚙️ Turn {setting} {', '.join(names[:-1])} and {names[-1]}?"
        return await self.confirmCard(msg, title, 'Features that depend on each other switch together, as in `/config`.', 'Config', None, action, admin = True)

    async def showItem(self, toolInput, msg, isAdmin):
        owner = self.member(toolInput, msg, 'owner')
        if owner is None:
            return NOBODY, True
        found, problem = await self.ownedItem(owner, toolInput.get('item'))
        if found is None:
            return problem, True
        await self.postCard(msg, self.client.get_cog('GTrade').itemEmbed(owner, found))
        return SHOWN, False

    # Storms: a typed number would hand everyone a free hint, so the sender's message goes, as a
    # prefix guess's does, and only "guessed wrong" with a private hint button is posted

    def said(self, msg, *words):
        # Whether the sender's own message holds one of these. Anything that deletes their message, or
        # acts in a private game, needs it, so words planted earlier in the channel can't set it off.
        content = (msg.content or '').casefold()
        return any(str(word).casefold() in content for word in words if word)

    def stormProblem(self, toolInput, msg):
        number = toolInput.get('number')
        if not isinstance(number, str) or not number.strip().isdecimal():
            return 'That is not a number to guess.'
        if not self.said(msg, str(int(number))):
            return 'Their message has no such number, so nothing was done.'
        # checked now, so there's nothing posted for a Storm that isn't on
        if self.client.get_cog('Storms').stormStates.get(str(msg.guild.id), {}).get('stormState') != 2:
            return 'No Storm is on right now, so there is nothing to guess. Nothing was posted. Tell them.'
        return None

    async def hideGuess(self, msg):
        try:
            await msg.delete()
        except nextcord.HTTPException:
            pass

    async def guessStorm(self, toolInput, msg, isAdmin):
        problem = self.stormProblem(toolInput, msg)
        if problem:
            return problem, True
        await self.hideGuess(msg)
        # Storms' prefix answer, posted in the channel as the agent's whole reply
        await self.client.get_cog('Storms').commonStorms(self.channelContext(msg), msg.author, int(toolInput['number']), None)
        return GUESSED, False

    async def betStorm(self, toolInput, msg, isAdmin):
        problem = self.stormProblem(toolInput, msg)
        if problem:
            return problem, True
        bet = toolInput.get('bet') if isinstance(toolInput.get('bet'), str) else ''
        try:
            amount = presentation.parseGCoin(bet)
        except InvalidOperation:
            return 'That is not an amount to bet.', True
        number = int(toolInput['number'])
        await self.hideGuess(msg)
        storms = self.client.get_cog('Storms')
        async def action(interaction):
            # Storms' own bet: the hint comes privately to whoever pressed, as a typed bet's does
            await storms.commonStorms(interaction, interaction.user, number, amount)
            return f'🎲 {interaction.user.display_name} bet {presentation.formatGCoin(amount)} GCoin.'
        # the number stays off the card, which everyone can see
        # posted to the channel, as their message is gone, so it says whose bet it is
        return await self.confirmCard(msg, f'🎲 Bet {presentation.formatGCoin(amount)} GCoin on your guess?', f'For **{msg.author.display_name}**. Your number stays hidden, and your hint comes just to you.', 'Storms', 'toggle_storms', action, asReply = False)

    # helpers for what M5b added

    def reply(self, msg):
        # what a command's engine sends becomes a notice, as on a card's button
        return pagination.CardReply(SimpleNamespace(guild = msg.guild, user = msg.author, channel = msg.channel))

    def reported(self, reply, done):
        notice = reply.notice or ''
        if notice.startswith('❌'):
            return notice[2:], True
        return notice or done, False

    def channelNamed(self, guild, text):
        wanted = (text or '').strip().strip('<#>').casefold()
        return next((channel for channel in guild.text_channels if channel.name.casefold() == wanted or str(channel.id) == wanted), None)

    def roleNamed(self, guild, text):
        wanted = (text or '').strip().strip('<@&>').casefold()
        return next((role for role in guild.roles if role.name.casefold().lstrip('@') == wanted or str(role.id) == wanted), None)

    # read

    async def history(self, toolInput, msg, isAdmin):
        member = self.member(toolInput, msg)
        if member is None:
            return NOBODY, True
        if member.id != msg.author.id and not isAdmin:
            return "Only admins can see someone else's history.", True
        gcoin = self.client.get_cog('GCoin')
        other = None if member.id == msg.author.id else member
        title = f"{strings.FEATURE_EMOJIS['toggle_gcoin']} {member.display_name}'s GCoin history" if other else f"{strings.FEATURE_EMOJIS['toggle_gcoin']} GCoin history"
        # private, as /gcoin's History is: whoever presses gets it as its button would give it them
        return await self.openPrivately(msg, title, lambda interaction, user: gcoin.commonHistory(interaction, user, other), 'toggle_gcoin')

    async def hypeLookup(self, toolInput, msg, isAdmin):
        hype = self.client.get_cog('Hype')
        matches = await GBotFirebaseService.run(hype_queries.getAllServerMatches, msg.guild.id)
        if toolInput.get('action') == 'test':
            text = toolInput.get('text') if isinstance(toolInput.get('text'), str) else ''
            if not text.strip():
                return 'Give a message to test.', True
            # a pattern is matched from the start of a message, as Hype does, so the agent can say why
            return f"{hype.describeTest(msg.guild.id, matches, text)}\n(Hype matches from the start of a message, so a pattern fires anywhere in one only if it begins with .*)", False
        lines = hype.listMatches(matches)[1]
        return '\n'.join(lines[:MAX_ROWS]) or 'This server has no Hype matches.', False

    async def openCard(self, toolInput, msg, isAdmin):
        feature = help_cog.featureNamed(toolInput.get('feature'))
        if feature is None:
            return 'There is no feature by that name.', True
        # the feature's switch first, as typing its command checks it
        if feature.toggle is not None and await GBotFirebaseService.run(config_queries.getServerValue, msg.guild.id, feature.toggle) is not True:
            return f'{feature.name} is turned off in this server.', True
        if feature.name == 'Music':
            music = self.client.get_cog('Music')
            serverId = str(msg.guild.id)
            if music.musicStates.get(serverId, {}).get('voiceClient') is None:
                return 'Nothing is playing, so there is no music card. Tell them.', True
            # the same move as when a song starts: the card comes down to the bottom of the channel
            await music.postCard(serverId, msg.channel, moveDown = True)
            addCard(msg)
            return 'Moved the music card to the bottom. It is your whole reply, so nothing you write is shown.', False
        if feature.name == 'Who Dis':
            # to their DMs, with no line in the channel, as who plays is the secret. Only shown: a game
            # starts with the card's own button, as at any level.
            if not self.said(msg, *WHO_DIS_WORDS):
                return 'Their message is not about Who Dis, so nothing was done.', True
            return await self.whoDisCard(msg)
        if feature.name in PUBLIC_CARDS:
            # public, as its prefix command is, so it can be shown off
            await PUBLIC_CARDS[feature.name](self.client.get_cog(feature.cog), self.channelContext(msg), msg.author)
            return 'Posted it. It is your whole reply, so nothing you write is shown.', False
        # anything else is private, which only a press can open: the 🔒 Open a prefix command posts
        return await self.openPrivately(msg, f'{feature.emoji} {feature.name}', lambda interaction, user: feature.open(self.client.get_cog(feature.cog), interaction, user), feature.toggle, feature.adminOnly)

    async def stormStatus(self, toolInput, msg, isAdmin):
        state = self.client.get_cog('Storms').stormStates.get(str(msg.guild.id), {}).get('stormState')
        return {2: 'A Storm is on: guess a number from 1 to 200.', 1: 'A Storm is incoming: putting up the umbrella starts it.'}.get(state, 'No Storm right now.'), False

    # safe

    async def stormUmbrella(self, toolInput, msg, isAdmin):
        storms = self.client.get_cog('Storms')
        if storms.stormStates.get(str(msg.guild.id), {}).get('stormState') != 1:
            return 'No Storm is incoming, so there is no umbrella to put up. Nothing was posted. Tell them.', True
        await storms.commonUmbrella(self.channelContext(msg), msg.author)
        return 'Done. GBot posted the result, which is your whole reply, so nothing you write is shown.', False

    async def whoDis(self, toolInput, msg, isAdmin):
        action = toolInput.get('action')
        name = toolInput.get('name') if isinstance(toolInput.get('name'), str) else ''
        if action not in ('start', 'end', 'leave', 'guess'):
            return 'Say whether to start, end, leave or guess.', True
        # their message goes, so it needs to be about Who Dis, and a guess to name who
        if not self.said(msg, *WHO_DIS_WORDS) and not (action == 'guess' and name.strip() and self.said(msg, name.strip())):
            return 'Their message is not about Who Dis, so nothing was done.', True
        return await self.whoDisCard(msg)

    async def whoDisCard(self, msg):
        # stands for the reply: nothing is posted where their message was
        addCard(msg)
        # Not even a 🔒 Open line: one saying who asked would tell their partner when the game began.
        # The message goes and the card comes to their DMs, where the game is played and guessed.
        if await self.client.get_cog('WhoDis').openCardFromChannel(msg, msg.author, msg.guild):
            return 'Done. Their message was deleted and their Who Dis card sent to their DMs, where they start, leave or guess, and a game\'s own card there ends it, as who plays is a secret. Write nothing.', False
        return 'Their DMs are closed, and GBot told them so. Write nothing.', False

    async def editMusic(self, toolInput, msg, isAdmin):
        action = toolInput.get('action')
        music = self.client.get_cog('Music')
        # following from silence joins the sender's voice channel, as the "Nothing is playing" card's 🎧 does
        problem = (music.followProblem if action == 'follow_spotify' else music.listenerProblem)(self.musicContext(msg))
        if problem:
            return f'{problem} So nothing happened. Tell them that.', True
        position, to = toolInput.get('position'), toolInput.get('to')
        if action == 'remove':
            # any number of them, from the last, so each position still means the song it did
            positions = toolInput.get('positions') if isinstance(toolInput.get('positions'), list) and toolInput.get('positions') else [position]
            positions = sorted(set(positions), reverse = True) if all(isinstance(each, int) for each in positions) else None
            if not positions:
                return 'Give the queue position to remove.', True
            async def remove(cog, reply):
                for each in positions:
                    await cog.commonRemove(reply, msg.author, each)
            return await self.runMusic(msg, remove)
        if action == 'move':
            if not isinstance(position, int) or not isinstance(to, int):
                return 'Give the queue position to move, and where to.', True
            return await self.runMusic(msg, lambda cog, reply: cog.commonMove(reply, msg.author, position, to))
        if action == 'restart':
            return await self.runMusic(msg, lambda cog, reply: cog.commonRestart(reply, msg.author))
        if action == 'elevator':
            return await self.runMusic(msg, lambda cog, reply: cog.commonElevator(reply))
        if action == 'follow_spotify':
            session = self.client.get_cog('Music').spotifySyncSessions.get(str(msg.guild.id))
            wanted = toolInput.get('user')
            if session is not None and isinstance(wanted, str) and not wanted.strip():
                # an empty user stops following, as pressing Follow again does for whoever is followed
                followed = msg.guild.get_member(int(session['userId']))
            else:
                followed = self.member(toolInput, msg)
            if followed is None:
                return NOBODY, True
            return await self.runMusic(msg, lambda cog, reply: cog.commonSpotify(reply, msg.author, followed))
        return 'That is not something you can do to the music.', True

    async def renameItem(self, toolInput, msg, isAdmin):
        found, problem = await self.ownedItem(msg.author, toolInput.get('item'))
        if found is None:
            return problem, True
        name = toolInput.get('name')
        if not isinstance(name, str) or not name.strip():
            return 'Give the new name.', True
        reply = self.reply(msg)
        await self.client.get_cog('GTrade').commonRename(reply, msg.author, found['name'], name.strip())
        return self.reported(reply, 'Renamed.')

    # all

    async def hypeChange(self, toolInput, msg, isAdmin):
        hype = self.client.get_cog('Hype')
        action = toolInput.get('action')
        matches = await GBotFirebaseService.run(hype_queries.getAllServerMatches, msg.guild.id) or {}
        matchIds = list(matches)
        matchId = current = None
        # delete takes any number of them, as "delete all the matches" asks; edit one
        numbers = toolInput.get('numbers') if action == 'delete' and isinstance(toolInput.get('numbers'), list) and toolInput.get('numbers') else [toolInput.get('number')]
        if action in ('edit', 'delete'):
            numbers = list(dict.fromkeys(numbers))
            missing = next((number for number in numbers if not isinstance(number, int) or not 1 <= number <= len(matchIds)), None) if numbers else None
            if missing is not None or not numbers:
                return f'There is no match number {missing}. Use hype_lookup for their numbers.', True
            matchId = matchIds[numbers[0] - 1]
            current = matches[matchId]
        if action == 'delete':
            chosen = [(matchIds[number - 1], matches[matchIds[number - 1]]) for number in numbers]
            async def delete(interaction):
                lines = []
                for chosenId, match in chosen:
                    await GBotFirebaseService.run(hype_queries.removeMatch, interaction.guild.id, chosenId)
                    lines.append(f"↩️ Deleted the Hype match {hype.describeRegex(match['regex'])}.")
                return '\n'.join(lines)
            described = [f"{hype.describeRegex(match['regex'])} → {hype.describeResponses(match.get('responses', []))}" for _, match in chosen]
            if len(chosen) == 1:
                return await self.confirmCard(msg, '↩️ Delete this Hype match?', described[0], 'Hype', 'toggle_hype', delete, admin = True)
            return await self.confirmCard(msg, f'↩️ Delete these {len(chosen)} Hype matches?', '\n'.join(f'• {line}' for line in described), 'Hype', 'toggle_hype', delete, admin = True)
        if action not in ('add', 'edit'):
            return 'Say whether to add, edit or delete.', True
        # stripped and capped as the Hype form does
        pattern = toolInput.get('pattern').strip() if isinstance(toolInput.get('pattern'), str) else ''
        responsesText = toolInput.get('responses') if isinstance(toolInput.get('responses'), str) else ''
        if len(pattern) > hype_cog.MAX_PATTERN_CHARACTERS or len(responsesText) > hype_cog.MAX_RESPONSES_CHARACTERS:
            return f'A pattern can be at most {hype_cog.MAX_PATTERN_CHARACTERS} characters, and the replies {hype_cog.MAX_RESPONSES_CHARACTERS}.', True
        isReaction = current['isReaction'] if current is not None else toolInput.get('kind') == 'reaction'
        problem = hype.patternProblem(pattern) if pattern else 'Give a pattern.'
        responses, responseProblem = hype.readResponses(responsesText, isReaction, msg.guild)
        if problem or responseProblem:
            return problem or responseProblem, True
        async def save(interaction):
            if matchId is None:
                await GBotFirebaseService.run(hype_queries.createMatch, interaction.guild.id, pattern, responses, isReaction)
            else:
                # the match it changes, still there: an update to one deleted meanwhile would leave half a match
                def update():
                    if (hype_queries.getAllServerMatches(interaction.guild.id) or {}).get(matchId) is None:
                        return False
                    hype_queries.updateMatch(interaction.guild.id, matchId, pattern, responses)
                    return True
                if not await GBotFirebaseService.run(update):
                    return '❌ That Hype match is gone, so nothing was changed.'
            return f'↩️ Saved the Hype match {hype.describeRegex(pattern)}.'
        verb = 'Reacts with one of' if isReaction else 'Replies with one of'
        # an edit says which match it replaces, so a wrong number shows before it's pressed
        replaces = '' if current is None else f"\n**Replaces:** {hype.describeRegex(current['regex'])} → {hype.describeResponses(current.get('responses', []))}"
        return await self.confirmCard(msg, f"↩️ {'Add' if matchId is None else 'Change'} this Hype match?", f'**Matches:** {hype.describeRegex(pattern)}\n**{verb}:** {hype.describeResponses(responses)}{replaces}', 'Hype', 'toggle_hype', save, admin = True)

    async def craftItem(self, toolInput, msg, isAdmin):
        image, imageUrl = gtrade_cog.imageIn(msg)
        if image is None and imageUrl is None:
            return 'Crafting needs an image attached to their message, or a link to one in it. Nothing was posted. Tell them.', True
        name, value = toolInput.get('name'), toolInput.get('value')
        if not isinstance(name, str) or not name.strip() or not isinstance(value, str) or not value.strip():
            return 'Give the item a name and a value.', True
        gtrade = self.client.get_cog('GTrade')
        async def craft(interaction):
            reply = pagination.CardReply(interaction)
            await gtrade.commonCraft(reply, interaction.user, name.strip(), value.strip(), image, imageUrl)
            return reply.notice or '⚒️ Crafted.'
        return await self.confirmCard(msg, f'⚒️ Craft {name.strip()} worth {value.strip()} GCoin?', 'From the image in their message.', 'GTrade', 'toggle_gtrade', craft, image = image.url if image is not None else imageUrl)

    async def destroyItem(self, toolInput, msg, isAdmin):
        # any number of the sender's own, under one confirm listing each and what it pays back
        wanted = toolInput.get('items') if isinstance(toolInput.get('items'), list) else []
        found = {}
        for item in wanted:
            match, problem = await self.ownedItem(msg.author, item)
            if match is None:
                return problem, True
            found[match['name']] = match
        if not found:
            return (await self.ownedItem(msg.author, ''))[1], True
        gtrade = self.client.get_cog('GTrade')
        names = list(found)
        async def destroy(interaction):
            # as the card's 💥 Destroy, under the trade lock, each looked up again
            async with gtrade.tradeLock:
                return '\n'.join([await gtrade.destroyUnderLock(interaction.user, name) for name in names])
        if len(names) == 1:
            return await self.confirmCard(msg, f'💥 Destroy {names[0]} for good?', "This can't be undone.", 'GTrade', 'toggle_gtrade', destroy)
        listed = '\n'.join(f"• {name} · {presentation.formatGCoin(utils.roundDecimalPlaces(found[name]['value'], 2))} GCoin" for name in names)
        return await self.confirmCard(msg, f'💥 Destroy {len(names)} items for good?', f"{listed}\n\nEach pays back its worth. This can't be undone.", 'GTrade', 'toggle_gtrade', destroy)

    async def answerTrade(self, toolInput, msg, isAdmin):
        action = toolInput.get('action')
        other = self.member(toolInput, msg, 'other')
        item = toolInput.get('item') if isinstance(toolInput.get('item'), str) else ''
        if action not in ('accept', 'decline') or other is None or other.id == msg.author.id:
            return 'Say whether to accept or decline, and whose offer.', True
        pending = await GBotFirebaseService.run(gtrade_queries.getAllServerPendingTradeTransactions, msg.guild.id) or {}
        me, them = str(msg.author.id), str(other.id)
        # an offer made to the sender: someone's request to buy their item, or to sell them one
        offer = next(((trxId, trx) for trxId, trx in pending.items() if item.strip().casefold() in trx['item']['name'].casefold()
                      and ((trx['trxType'] == 'buy' and trx['sellerId'] == me and trx.get('buyerId') == them) or (trx['trxType'] == 'sell' and trx.get('buyerId') == me and trx['sellerId'] == them))), None)
        if offer is None:
            return f'{other.display_name} has no offer like that open to them.', True
        trxId, trx = offer
        gtrade = self.client.get_cog('GTrade')
        name = trx['item']['name']
        async def answer(interaction):
            # what the trade's own buttons do, under the trade lock
            async with gtrade.tradeLock:
                if await GBotFirebaseService.run(gtrade_queries.getPendingTradeTransactionWithId, interaction.guild.id, trxId) is None:
                    return '⌛ This trade is no longer available.'
                if action == 'decline':
                    # The offer's own message keeps its buttons, as where it is isn't stored with the
                    # trade, and a press on them says it's gone and takes them away.
                    await GBotFirebaseService.run(gtrade_queries.removePendingTradeTransaction, interaction.guild.id, trxId)
                    return f"❌ Declined {other.display_name}'s offer for {name}."
                if interaction.guild.get_member(other.id) is None:
                    return '⌛ This trade is no longer available, as the other person left.'
                reply = pagination.CardReply(interaction)
                if trx['trxType'] == 'buy':
                    await gtrade.sellUnderLock(reply, interaction.user, name, other, accepting = True)
                else:
                    await gtrade.buyUnderLock(reply, interaction.user, name, other)
                return reply.notice or '✅ Done.'
        price = presentation.formatGCoin(utils.roundDecimalPlaces(trx['item']['value'], 2))
        title = f"{'✅ Accept' if action == 'accept' else '❌ Decline'} {other.display_name}'s offer to {'buy' if trx['trxType'] == 'buy' else 'sell you'} {name} for {price} GCoin?"
        return await self.confirmCard(msg, title, 'GTrade checks everything again when you press.', 'GTrade', 'toggle_gtrade', answer)

    async def remindRole(self, toolInput, msg, isAdmin):
        roleText = toolInput.get('role') if isinstance(toolInput.get('role'), str) else ''
        everyone = roleText.strip().lstrip('@').casefold() == 'everyone'
        role = None if everyone else self.roleNamed(msg.guild, roleText)
        if not everyone and role is None:
            return 'There is no role by that name here.', True
        zoneName = await GBotFirebaseService.run(reminders_queries.getTimezone, msg.author.id)
        if zoneName is None:
            return f"They haven't set a time zone. Ask where they are, use {agent_client.TOOL_SET_TIMEZONE}, then try again.", True
        target = reminders_cog.EVERYONE if everyone else str(role.id)
        if not reminders_cog.mayPing(msg.author, msg.channel, target, msg.guild):
            return "They can't mention that role here themselves, so GBot won't for them: it needs Mention Everyone in this channel, or a role anyone can mention.", True
        reminders = self.client.get_cog('Reminders')
        repeat = self.repeatOf(toolInput) if toolInput.get('repeat') in when.REPEATS else when.ONCE
        whenText = toolInput.get('when') if isinstance(toolInput.get('when'), str) else ''
        what = toolInput.get('what') if isinstance(toolInput.get('what'), str) else ''
        try:
            reminder = reminders.makeReminder(msg.author, msg.channel.id, ZoneInfo(zoneName), whenText, what, repeat, reminders_cog.HERE, target)
        except when.ReminderProblem as problem:
            return f'Nothing was set: {problem}', True
        async def save(interaction):
            # Read again at the press, so "in 2 minutes" is from the press rather than from when it
            # was asked, and the ping is one they can still make
            if not reminders_cog.mayPing(interaction.user, msg.channel, target, interaction.guild):
                return f'❌ {reminders_cog.NO_PING[0].upper()}{reminders_cog.NO_PING[1:]}'
            try:
                pressed = reminders.makeReminder(interaction.user, msg.channel.id, ZoneInfo(zoneName), whenText, what, repeat, reminders_cog.HERE, target)
                await reminders.saveReminder(interaction.guild.id, pressed)
            except when.ReminderProblem as problem:
                return f'❌ {problem}'
            return f"🔔 Reminder set for {access.timestamp(reminders_cog.momentOf(pressed['nextAt']), 'F')}."
        moment = reminders_cog.momentOf(reminder['nextAt'])
        who = '@everyone' if everyone else role.mention
        # a timer counts from the press, so the card says that rather than a time that goes stale
        shown = reminders_cog.timerPhrase(whenText).replace('Set it', 'Confirm') if reminder['timer'] else access.timestamp(moment, 'F')
        return await self.confirmCard(msg, f"🔔 Remind {'everyone' if everyone else role.name}?", f"{shown}, {when.repeatPhrase(moment, reminder['repeat'], ZoneInfo(zoneName))}, pinging {who} here:\n> {reminder['text']}", 'Reminders', 'toggle_reminders', save, admin = True)

    async def setConfig(self, toolInput, msg, isAdmin):
        setting = toolInput.get('setting')
        value = toolInput.get('value') if isinstance(toolInput.get('value'), str) else ''
        labels = {'storms_channel': ('channel_storms', 'Storms channel'), 'admin_channel': ('channel_admin', 'admin channel'), 'admin_role': ('role_admin', 'admin role'), 'who_dis_role': ('role_who_dis', 'Who Dis role'), 'prefix': ('prefix', 'prefix')}
        if setting not in labels:
            return 'That is not a setting the agent can change.', True
        key, label = labels[setting]
        if setting.endswith('channel'):
            found = self.channelNamed(msg.guild, value)
            if found is None:
                return 'There is no text channel by that name here.', True
            stored, shown = str(found.id), found.mention
        elif setting.endswith('role'):
            found = self.roleNamed(msg.guild, value)
            if found is None:
                return 'There is no role by that name here.', True
            # Who Dis gives its role out, so GBot has to be able to, as in /config
            problem = server_setup.roleProblem(msg.guild, found) if key == 'role_who_dis' else None
            if key == 'role_admin' and (found.is_default() or found.managed):
                # everyone holds @everyone, so it would make every member an admin, and /config's picker can't choose it
                problem = "The admin role can't be @everyone or a bot's own role. Pick a role that only admins have."
            if problem:
                return problem, True
            stored, shown = str(found.id), found.mention
        else:
            if not value.strip() or len(value.strip()) > 10:
                return 'A prefix is 1 to 10 characters.', True
            stored = shown = value.strip()
        async def save(interaction):
            await GBotFirebaseService.run(config_queries.setServerValue, interaction.guild.id, key, stored)
            return f'⚙️ The {label} is now {shown}.'
        return await self.confirmCard(msg, f'⚙️ Set the {label}?', f'To {shown}.', 'Config', None, save, admin = True)

    async def report(self, toolInput, msg, isAdmin):
        target = self.member(toolInput, msg)
        if target is None or target.id == msg.author.id:
            return (NOBODY if target is None else "They can't report themselves."), True
        if not self.said(msg, target.display_name, target.name, str(target.id)):
            return 'Their message does not name who to report, so nothing was done.', True
        config = self.client.get_cog('Config')
        # captured before their message goes, as Config's own report does
        captured = await config.captureMessages(msg.channel, target, None)
        what = toolInput.get('what') if isinstance(toolInput.get('what'), str) else ''
        # their message goes, so the channel doesn't see who reported whom
        await self.hideGuess(msg)
        async def file(interaction):
            if await config.fileReport(msg.guild, interaction.user, target, msg.channel.mention, captured, what.strip()):
                return '🚩 Sent to the admins. Thanks for letting them know.'
            return "❌ This report wasn't sent, as the server has no admin channel GBot can post in."
        embed = presentation.warningEmbed(title = f'🚩 Report {target.display_name} to the admins of {msg.guild.name}?', description = f'With their last messages in {msg.channel.mention}.' + (f'\n> {what.strip()}' if what.strip() else ''), feature = 'Config')
        async def confirm(interaction, user):
            view = AgentConfirm(msg.author.id, None, False, file)
            await view.send(interaction, True, embed = embed, view = view)
        # the one-liner names nobody, not even who it's for, and the confirm opens privately
        return await self.openPrivately(msg, '🔒 A private card', confirm, None, onlySender = True, named = False)

    async def agentSetting(self, toolInput, msg, isAdmin):
        agent = self.client.get_cog('Agent')
        setting = toolInput.get('setting').strip().lower() if isinstance(toolInput.get('setting'), str) else ''
        value = toolInput.get('value') if isinstance(toolInput.get('value'), str) else ''
        channelText = toolInput.get('channel') if isinstance(toolInput.get('channel'), str) else ''
        channel = self.channelNamed(msg.guild, channelText) if channelText.strip() else None
        if channelText.strip() and channel is None:
            return 'There is no text channel by that name here.', True
        if setting == 'key':
            # never from chat: the card's button opens /agent's own private form
            view = KeyCard(msg.author.id, agent)
            view.message = await self.postCard(msg, presentation.warningEmbed(title = '🔑 Enter the Claude API key?', description = 'Press the button to paste it in a private form. Never post a key in a channel.', feature = 'Agent'), view)
            return CONFIRM_POSTED, False
        where = f' in #{channel.name}' if channel else ''
        if setting == 'instructions':
            async def instruct(interaction):
                reply = pagination.CardReply(interaction)
                await agent.commonInstructions(reply, value, channel)
                return reply.notice or '🤖 Done.'
            return await self.confirmCard(msg, f'🤖 Set my instructions{where}?', f'> {value[:900]}' if value.strip() else 'Clear them.', 'Agent', 'toggle_agent', instruct, admin = True)
        problem = agent.settingProblem(setting, value, channel)
        if problem:
            return f'Nothing was posted: {problem}', True
        async def change(interaction):
            reply = pagination.CardReply(interaction)
            await agent.commonSettings(reply, setting, value, channel)
            return reply.notice or '🤖 Done.'
        return await self.confirmCard(msg, f'🤖 Set my {setting} to {value.strip()}{where}?', 'The same checks as /agent run when you press.', 'Agent', 'toggle_agent', change, admin = True)

    async def patreon(self, toolInput, msg, isAdmin):
        if msg.guild.id != GBotPropertiesManager.PATREON_GUILD_ID:
            return 'That only works in the GBot Patreon server.', True
        if not utils.isUserAssignedRole(msg.author, GBotPropertiesManager.PATRON_ROLE_ID):
            return 'Only GBot patrons can do that.', True
        serverId = toolInput.get('server_id')
        if not isinstance(serverId, str) or not serverId.strip().isdecimal():
            return 'Give the server ID, a long number.', True
        async def register(interaction):
            reply = pagination.CardReply(interaction)
            await self.client.get_cog('Patreon').commonPatreon(reply, interaction.user.id, int(serverId.strip()))
            return reply.notice or '⭐ Done.'
        return await self.confirmCard(msg, f'⭐ Enable GBot in server {serverId.strip()}?', 'Your subscription covers that server from now on.', 'Patreon', None, register)

class KeyCard(pagination.OwnedView):
    # the agent's key, through /agent's own private form, never typed in chat
    def __init__(self, ownerId, agent):
        super().__init__()
        self.ownerId = ownerId
        self.agent = agent
        self.button('🔑', self.open, label = 'Enter key', style = nextcord.ButtonStyle.primary)

    async def open(self, interaction):
        await interaction.response.send_modal(self.agent.keyForm())
