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
from GBotDiscord.src.gcoin import gcoin_cog, gcoin_queries
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
}
CONFIRM_POSTED = 'Posted a card with the button they press, and nothing happens until they press it. The card is your whole reply, so nothing you write is shown.'
GUESSED = 'Guessed. GBot posted the result, which is your whole reply, so nothing you write is shown.'
SHOWN = 'Shown. The item\'s card is your whole reply, so nothing you write is shown.'

NOBODY = 'There is nobody by that name here.'
# the cards posted as the reply to one message, which then stand for the agent's words: per task, as several messages are answered at once
CARDS = contextvars.ContextVar('cards', default = None)

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
    def __init__(self, ownerId, toggle, admin, action):
        super().__init__()
        self.ownerId = ownerId
        self.toggle = toggle
        self.admin = admin
        # action(interaction) does it and returns what to say
        self.action = action
        self.pressed = False
        self.button('✅', self.confirmed, label = 'Confirm', style = nextcord.ButtonStyle.success)
        self.button('❌', self.cancelled, label = 'Cancel')

    async def confirmed(self, interaction):
        # before anything is awaited: a double click is dispatched before the view could stop
        if self.pressed:
            await interaction.response.defer()
            return
        self.pressed = True
        await interaction.response.defer()
        try:
            await predicates.recheck(interaction, feature = self.toggle, admin = self.admin)
        except Exception:
            self.pressed = False
            raise
        self.stop()
        text = await self.action(interaction)
        await interaction.edit_original_message(content = text, embed = None, view = None)

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
        if name in agent_client.ACTING_TOOLS:
            if len(actions) >= MAX_ACTIONS_PER_REPLY:
                return f'You can only do {MAX_ACTIONS_PER_REPLY} things per message.', True
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
        }[name]
        # set every time, so a run without a list never adds to an earlier one's
        CARDS.set(cards)
        return await handler(toolInput, msg, isAdmin)

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

    async def reminders(self, toolInput, msg, isAdmin):
        # only the sender's own: the reply is public, and admins see everyone's privately in /remind
        zone = reminders_cog.zoneOrUtc(await GBotFirebaseService.run(reminders_queries.getTimezone, msg.author.id))
        found = [(reminderId, reminder) for reminderId, reminder in reminders_cog.soonest(await GBotFirebaseService.run(reminders_queries.getServerReminders, msg.guild.id)) if reminder['userId'] == str(msg.author.id)]
        lines = [f"id {reminderId}: {reminders_cog.describeWhen(reminder, zone)}, {reminder['text']} ({reminders_cog.describeWhere(reminder, msg.guild)})" for reminderId, reminder in found[:MAX_ROWS]]
        return "Their reminders, in their time:\n" + '\n'.join(lines) if lines else 'They have no reminders here.', False

    # safe

    def musicContext(self, msg):
        # what the music card's buttons pass its engines, so the agent goes through their checks and
        # locks, and what they'd have said shows on the now-playing card rather than as a new message
        return SimpleNamespace(guild = msg.guild, user = msg.author, channel = msg.channel)

    async def runMusic(self, msg, engine):
        reply = pagination.CardReply(self.musicContext(msg))
        music = self.client.get_cog('Music')
        try:
            await engine(music, reply)
        except Exception as e:
            self.logger.error(f'GBot Agent failed a music action in server {msg.guild.id}: {type(e).__name__}')
            return 'That didn\'t work. Tell them to try /music.', True
        notice = reply.notice or ''
        if notice.startswith('❌'):
            return notice[2:], True
        if notice:
            await music.updateCard(str(msg.guild.id), f'{notice} · {msg.author.display_name}')
        return f"Done. {notice or 'It is playing now.'} The music card shows it, so don't repeat it.", False

    async def playMusic(self, toolInput, msg, isAdmin):
        query = toolInput.get('query')
        if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_CHARACTERS:
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
        zoneName = await GBotFirebaseService.run(reminders_queries.getTimezone, msg.author.id)
        if zoneName is None:
            return f'They haven\'t set a time zone. Ask where they are, use {agent_client.TOOL_SET_TIMEZONE}, then set the reminder.', True
        reminders = self.client.get_cog('Reminders')
        try:
            reminder = reminders.makeReminder(msg.author, msg.channel.id, ZoneInfo(zoneName), *values, None)
            await reminders.saveReminder(msg.guild.id, reminder)
        except reminders_cog.ReminderProblem as problem:
            return f'Nothing was set: {problem}', True
        moment = reminders_cog.momentOf(reminder['nextAt'])
        return f"Set for {when.formatMoment(moment, ZoneInfo(zoneName))} in their time, {when.describeRepeat(moment, values[2], ZoneInfo(zoneName)).lower()}, {'by DM' if values[3] == reminders_cog.DM else 'here'}. Tell them when.", False

    async def deleteReminder(self, toolInput, msg, isAdmin):
        reminderId = toolInput.get('id')
        reminder = await GBotFirebaseService.run(reminders_queries.getReminder, msg.guild.id, reminderId) if isinstance(reminderId, str) and reminderId else None
        # only the sender's own, whoever asked
        if reminder is None or reminder['userId'] != str(msg.author.id):
            return 'The sender has no reminder with that id here.', True
        await GBotFirebaseService.run(reminders_queries.removeReminder, msg.guild.id, reminderId)
        return f"Deleted the reminder for {reminder['text']}.", False

    # all: each only posts a confirm card

    async def postConfirm(self, msg, embed, view, asReply = True):
        view.message = await self.postCard(msg, embed, view, asReply)
        return CONFIRM_POSTED, False

    async def postCard(self, msg, embed, view = None, asReply = True):
        # The card is the whole reply: one message, so the agent's words aren't sent beside it. Not as a
        # reply once the message has been deleted, as Discord refuses a reply to one that's gone.
        if asReply:
            posted = await msg.reply(embed = embed, view = view, allowed_mentions = nextcord.AllowedMentions.none())
        else:
            posted = await msg.channel.send(embed = embed, view = view, allowed_mentions = nextcord.AllowedMentions.none())
        cards = CARDS.get()
        if cards is not None:
            cards.append(posted)
        return posted

    async def confirmCard(self, msg, title, description, feature, toggle, action, admin = False, asReply = True):
        embed = presentation.warningEmbed(title = title, description = description, feature = feature)
        return await self.postConfirm(msg, embed, AgentConfirm(msg.author.id, toggle, admin, action), asReply)

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
        return await self.confirmCard(msg, f"🛒 Buy {item} from {owner.display_name} for {presentation.formatGCoin(price)} GCoin?",
                                      f"You'll have **{presentation.formatGCoin(balance - price)} GCoin** left, once they accept or if it's on the market.", 'GTrade', 'toggle_gtrade',
                                      self.gtradeAction(self.client.get_cog('GTrade').commonBuy, item, owner))

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
        if not isAdmin:
            return 'Only admins can turn features on or off.', True
        toggle = next((toggle for toggle, name in strings.FEATURE_NAMES.items() if name == toolInput.get('feature') and name in agent_client.SWITCHABLE_FEATURES), None)
        setting = toolInput.get('setting')
        if toggle is None or setting not in ('on', 'off'):
            return 'That is not a feature the agent can switch.', True
        current = await GBotFirebaseService.run(config_queries.getServerValue, msg.guild.id, toggle)
        if bool(current) == (setting == 'on'):
            return f'{strings.FEATURE_NAMES[toggle]} is already {setting}.', True
        config = self.client.get_cog('Config')
        async def action(interaction):
            # Config's own switch, so what a feature needs, or what needs it, switches with it
            stillThere = await GBotFirebaseService.run(config_queries.getServerValue, interaction.guild.id, toggle)
            if bool(stillThere) == (setting == 'on'):
                return f'{strings.FEATURE_NAMES[toggle]} is already {setting}.'
            return await config.toggleFeature(interaction, toggle)
        return await self.confirmCard(msg, f"{strings.FEATURE_EMOJIS[toggle]} Turn {setting} {strings.FEATURE_NAMES[toggle]}?", 'Features that depend on each other switch together, as in `/config`.', 'Config', None, action, admin = True)

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

    def stormProblem(self, toolInput, msg):
        number = toolInput.get('number')
        if not isinstance(number, str) or not number.strip().isdecimal():
            return 'That is not a number to guess.'
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
        async def send(content = None, **kwargs):
            # Storms' prefix answer, posted in the channel as the agent's whole reply
            posted = await msg.channel.send(content, **kwargs)
            cards = CARDS.get()
            if cards is not None:
                cards.append(posted)
            return posted
        await self.client.get_cog('Storms').commonStorms(SimpleNamespace(guild = msg.guild, channel = msg.channel, send = send), msg.author, int(toolInput['number']), None)
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

