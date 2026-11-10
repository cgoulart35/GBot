#region IMPORTS
import logging
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from GBotDiscord.src import pagination
from GBotDiscord.src import presentation
from GBotDiscord.src import strings
from GBotDiscord.src.agent import agent_client
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.firebase import GBotFirebaseService
from GBotDiscord.src.gcoin import gcoin_queries
from GBotDiscord.src.gtrade import gtrade_queries
from GBotDiscord.src.help import help_cog
from GBotDiscord.src.leaderboards import leaderboards_queries
from GBotDiscord.src.reminders import reminders_cog, reminders_queries, when
#endregion

# What the agent can look up and do for the sender, at its channel's abilities level. Each tool shows
# or does only what the sender could see or do with the command, behind the same feature toggle, and
# checked here in code whatever the model asked for. Nothing here moves GCoin or items, or changes
# anyone else's things: that waits for the `all` level and its confirm button.

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
    agent_client.TOOL_GET_MUSIC_QUEUE: 'toggle_music',
    agent_client.TOOL_GET_REMINDERS: 'toggle_reminders',
    agent_client.TOOL_PLAY_MUSIC: 'toggle_music',
    agent_client.TOOL_CONTROL_MUSIC: 'toggle_music',
    agent_client.TOOL_SET_REMINDER: 'toggle_reminders',
    agent_client.TOOL_DELETE_REMINDER: 'toggle_reminders',
}

NOBODY = 'There is nobody by that name here.'

def findMember(guild, text):
    # an id from <people>, or a name that matches exactly one member
    if text.isdecimal():
        return guild.get_member(int(text))
    wanted = text.lstrip('@').casefold()
    matches = [member for member in guild.members if wanted in (member.name.casefold(), member.display_name.casefold())]
    return matches[0] if len(matches) == 1 else None

class AgentAbilities:

    def __init__(self, client):
        self.client = client
        self.logger = logging.getLogger()

    async def run(self, name, toolInput, msg, isAdmin, actions):
        toggle = TOGGLES.get(name)
        if toggle is not None and await GBotFirebaseService.run(config_queries.getServerValue, msg.guild.id, toggle) is not True:
            return f'{strings.FEATURE_NAMES[toggle]} is turned off in this server.', True
        if name in agent_client.SAFE_TOOLS:
            if len(actions) >= MAX_ACTIONS_PER_REPLY:
                return f'You can only do {MAX_ACTIONS_PER_REPLY} things per message.', True
            actions.append(name)
        handler = {
            agent_client.TOOL_GET_WALLET: self.wallet,
            agent_client.TOOL_GET_RANKING: self.ranking,
            agent_client.TOOL_SEARCH_MARKET: self.market,
            agent_client.TOOL_GET_ITEMS: self.items,
            agent_client.TOOL_GET_MUSIC_QUEUE: self.musicQueue,
            agent_client.TOOL_GET_FEATURES: self.features,
            agent_client.TOOL_GET_REMINDERS: self.reminders,
            agent_client.TOOL_PLAY_MUSIC: self.playMusic,
            agent_client.TOOL_CONTROL_MUSIC: self.controlMusic,
            agent_client.TOOL_SET_REMINDER: self.setReminder,
            agent_client.TOOL_DELETE_REMINDER: self.deleteReminder,
        }[name]
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
        member = self.member(toolInput, msg)
        if member is None:
            return NOBODY, True
        if member.id != msg.author.id and not isAdmin:
            return "Only admins can see someone else's reminders.", True
        zone = reminders_cog.zoneOrUtc(await GBotFirebaseService.run(reminders_queries.getTimezone, msg.author.id))
        found = [(reminderId, reminder) for reminderId, reminder in reminders_cog.soonest(await GBotFirebaseService.run(reminders_queries.getServerReminders, msg.guild.id)) if reminder['userId'] == str(member.id)]
        lines = [f"id {reminderId}: {reminders_cog.describeWhen(reminder, zone)}, {reminder['text']} ({reminders_cog.describeWhere(reminder, msg.guild)})" for reminderId, reminder in found[:MAX_ROWS]]
        return f"{member.display_name}'s reminders, in the sender's time:\n" + '\n'.join(lines) if lines else f'{member.display_name} has no reminders here.', False

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
