#region IMPORTS
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import nextcord
from nextcord.ext import commands, tasks
from nextcord.ext.commands.context import Context

from GBotDiscord.src import access
from GBotDiscord.src import pagination
from GBotDiscord.src import predicates
from GBotDiscord.src import presentation
from GBotDiscord.src import strings
from GBotDiscord.src import utils
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.help import guides
from GBotDiscord.src.reminders import reminders_queries, when
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.firebase import GBotFirebaseService
#endregion

# /remind: reminders for yourself, here or by DM, once or repeating, in your own time zone, and
# for admins a role or everyone too. One engine behind the command, its card and the delivered
# reminder's buttons, which carry their reminder in their ids so they work after a restart.

FEATURE = 'Reminders'
TOGGLE = 'toggle_reminders'
EMOJI = strings.FEATURE_EMOJIS[TOGGLE]

HERE = 'here'
DM = 'dm'
WHERES = (HERE, DM)
EVERYONE = 'everyone'

BUTTON_PREFIX = 'remind:'
SNOOZE_MINUTES = 'snooze10'
SNOOZE_HOUR = 'snooze60'
SNOOZE_TOMORROW = 'snoozetomorrow'
SKIP = 'skip'
STOP = 'stop'
# Done and ✖️ name whoever set it, as a sent one-off's record goes after a day and the message stays
DONE = 'done'
DISMISS = 'dismiss'
# what a press writes on a sent reminder: its latest only, and the "next" its repeat shows, kept true
STATUS_EMOJI = ('💤', '⏭️', '🛑', '✅')
NEXT_PART = re.compile(r' · next <t:\d+:R>')
SKIPPED = re.compile(r'⏭️ Skipped (one|\d+)\.')
KEEP_NEXT = object()

# what ends a sent reminder's buttons, so its line replaces every other
FINAL_EMOJI = ('✅', '🛑')

def showStatus(embed, line, nextAt = KEEP_NEXT):
    # What's been pressed, each kind kept current rather than piling up: a snooze and a skip can
    # stand together, and Done or Stop, being final, replaces both. nextAt moves the repeat's "next"
    # to it, or None takes it away, once it's stopped.
    replaces = STATUS_EMOJI if line.startswith(FINAL_EMOJI) else tuple(emoji for emoji in STATUS_EMOJI if line.startswith(emoji))
    kept = [(field.name, field.value, field.inline) for field in embed.fields if not field.value.startswith(replaces)]
    embed.clear_fields()
    for name, value, inline in kept:
        if nextAt is None:
            value = NEXT_PART.sub('', value)
        elif nextAt is not KEEP_NEXT:
            value = NEXT_PART.sub(f" · next {stamp(nextAt, 'R')}", value)
        embed.add_field(name = name, value = value, inline = inline)
    embed.add_field(name = '​', value = line, inline = False)
    return embed

def removeSnoozes(serverId, reminderId):
    # on the database worker: a repeat's pending snoozes, removed; whether there were any
    snoozes = [snoozeId for snoozeId, snooze in (reminders_queries.getServerReminders(serverId) or {}).items() if snooze.get('snoozeOf') == reminderId and isPending(snooze)]
    for snoozeId in snoozes:
        reminders_queries.removeReminder(serverId, snoozeId)
    return bool(snoozes)

def skippedSoFar(embed):
    # how many skips its status line already counts
    for field in embed.fields:
        if found := SKIPPED.match(field.value):
            return 1 if found.group(1) == 'one' else int(found.group(1))
    return 0

LIST = 'list'
SERVER = 'server'
DRAFT = 'draft'
ZONE = 'zone'

# what a prefix command's free text may say for where (and for repeat, when.readRepeat)
WHERE_WORDS = {'here': HERE, 'channel': HERE, 'dm': DM, 'dms': DM}
EXAMPLES = '"in 2 hours", "tomorrow 9am", "Thursday 8pm" or "Dec 25 10:00"'
MAX_YEARS_AHEAD = 10
TOO_FAR = f'a reminder can be at most {MAX_YEARS_AHEAD} years ahead.'
REPEAT_PROBLEM = '`repeat` can be once, daily, weekdays, weekly, monthly, yearly or days like `mon,wed,fri`.'

# Defined in when.py, which is only ever imported. load_extension runs this module again as a copy of
# its own, so a class defined here would be a different one to the agent, which imports this module,
# and its `except ReminderProblem` would miss what the loaded cog raises.
ReminderProblem = when.ReminderProblem

def utcNow():
    return datetime.now(timezone.utc)

def momentOf(text):
    return datetime.fromisoformat(text)

def stamp(moment, style = 'f'):
    return access.timestamp(moment, style)

def zoneOrUtc(zoneName):
    return ZoneInfo(zoneName) if zoneName else ZoneInfo('UTC')

def isPending(reminder):
    # a one-off already sent stays a day so it can be snoozed, but isn't anyone's reminder any more
    return not reminder.get('delivered')

def isSnoozed(reminder):
    # a repeat's snooze is a copy naming it; a one-off's is itself, moved later
    return bool(reminder.get('snoozeOf') or reminder.get('snoozed'))

def soonest(reminders):
    return sorted(((reminderId, reminder) for reminderId, reminder in (reminders or {}).items() if isPending(reminder)), key = lambda item: item[1]['nextAt'])

def describeTarget(reminder, guild):
    target = reminder.get('target')
    if target == EVERYONE:
        return 'pings @everyone'
    if target:
        role = guild.get_role(int(target)) if guild is not None else None
        return f'pings {role.mention}' if role is not None else 'pings a deleted role'
    return None

def describeWhere(reminder, guild):
    if reminder.get('where') == DM:
        return 'DM'
    channel = guild.get_channel_or_thread(int(reminder['channelId'])) if guild is not None else None
    return f'here in {channel.mention}' if channel is not None else 'in a deleted channel'

def describeWhen(reminder, zone):
    moment = momentOf(reminder['nextAt'])
    if reminder.get('repeat', when.ONCE) == when.ONCE:
        return when.formatMoment(moment, zone, utcNow())
    return when.describeRepeat(moment, reminder['repeat'], zone)

def mayPing(member, channel, target, guild):
    # Discord's own rule for whoever set it: @everyone and a role that isn't mentionable need Mention
    # Everyone in the channel. GBot has that permission itself, so it mustn't lend it to anyone.
    if not target:
        return True
    if channel is not None and channel.permissions_for(member).mention_everyone:
        return True
    if target == EVERYONE:
        return False
    role = guild.get_role(int(target))
    return role is not None and role.mentionable

NO_PING = "you can't mention that role here yourself, so GBot won't for you. It needs Mention Everyone in this channel, or a role anyone can mention."

def shorten(text, limit):
    return text if len(text) <= limit else text[:limit - 1] + '…'

def changeZone(userId, zoneName):
    # Sets someone's time zone, and moves their reminders in every server with them, so a reminder
    # for 9am stays at 9am in the new zone. Runs on the database worker; the agent sets it this way too.
    oldName = reminders_queries.getTimezone(userId)
    reminders_queries.setTimezone(userId, zoneName)
    if oldName is None or oldName == zoneName:
        return
    old, new = ZoneInfo(oldName), ZoneInfo(zoneName)
    for serverId, reminders in (reminders_queries.getAllReminders() or {}).items():
        for reminderId, reminder in (reminders or {}).items():
            if reminder['userId'] == str(userId) and isPending(reminder):
                moved = when.moveToZone(momentOf(reminder['nextAt']), old, new)
                reminders_queries.updateReminder(serverId, reminderId, {'nextAt': moved.astimezone(timezone.utc).isoformat()})

class RemindersCard(pagination.OwnedView):
    # /remind with no fields: your reminders here, a draft being set, your time zone, or for admins
    # everyone's. Private, and checked again on every press.
    def __init__(self, cog, guild, author, isAdmin):
        super().__init__()
        self.cog = cog
        self.guild = guild
        self.author = author
        self.isAdmin = isAdmin
        self.screen = LIST
        self.notice = None
        self.selected = None
        self.zoneName = None
        self.reminders = []
        # a reminder being made: its fields, before it's saved
        self.draft = None
        # the when and what of a reminder waiting for a time zone to be picked
        self.waiting = None
        # where the card was opened, which is where a reminder set from it goes
        self.originChannelId = None

    @property
    def zone(self):
        return zoneOrUtc(self.zoneName)

    async def render(self):
        self.zoneName, everything = await GBotFirebaseService.run(self.cog.cardFacts, self.author.id, self.guild.id)
        mine = [(reminderId, reminder) for reminderId, reminder in everything if reminder['userId'] == str(self.author.id)]
        self.reminders = everything if self.screen == SERVER else mine
        if self.selected not in [reminderId for reminderId, _ in self.reminders]:
            self.selected = None
        self.clear_items()
        if self.screen == DRAFT:
            embed = self.renderDraft()
        elif self.screen == ZONE:
            embed = self.renderZone()
        else:
            embed = self.renderList()
        if self.notice:
            embed.add_field(name = '​', value = self.notice[:1024], inline = False)
            self.notice = None
        return embed

    def renderList(self):
        server = self.screen == SERVER
        title = f"{EMOJI} This server's reminders" if server else f'{EMOJI} Your reminders'
        if not self.reminders:
            description = 'Nobody has a reminder here.' if server else 'No reminders here yet. Press ➕ New to set one.'
        elif server:
            description = f'{len(self.reminders)} here, soonest first, in your time.'
        else:
            description = f'{len(self.reminders)} of {Reminders.MAX_PER_PERSON}, soonest first.'
        if self.zoneName:
            description += f'\nTimes in **{when.zoneLabel(self.zoneName)}** ({when.formatClock(utcNow().astimezone(self.zone))} now).'
        elif not server:
            description += '\nPick your time zone with 🌍 Time zone, so "9am" means your 9am.'
        embed = presentation.brandEmbed(title = title, description = description, feature = FEATURE)
        for number, (reminderId, reminder) in enumerate(self.reminders[:Reminders.MAX_PER_PERSON], start = 1):
            details = [describeWhere(reminder, self.guild)]
            target = describeTarget(reminder, self.guild)
            if target:
                details.append(target)
            if server:
                details.append(f"by <@{reminder['userId']}>")
            # a snooze is marked, as a repeat's sits in the list beside the repeat, with the same words
            snoozed = '💤 Snoozed · ' if isSnoozed(reminder) else ''
            embed.add_field(name = f'{number}. {describeWhen(reminder, self.zone)}', value = f"{snoozed}{shorten(reminder['text'], 150)} · {' · '.join(details)}", inline = False)
        if self.reminders:
            options = [nextcord.SelectOption(label = shorten(f"{number}. {'💤 ' if isSnoozed(reminder) else ''}{describeWhen(reminder, self.zone)}", 100), description = shorten(reminder['text'], 100), value = reminderId, default = reminderId == self.selected)
                       for number, (reminderId, reminder) in enumerate(self.reminders[:Reminders.MAX_PER_PERSON], start = 1)]
            select = nextcord.ui.Select(custom_id = pagination.newId('pick'), placeholder = 'Pick a reminder…', options = options, row = 0)
            select.callback = self.choose(select)
            self.add_item(select)
        if server:
            self.button('🗑️', self.delete, label = 'Delete', style = nextcord.ButtonStyle.danger, row = 1, disabled = self.selected is None)
            self.button('↩️', self.back, label = 'Back', row = 1)
            self.closeButton(row = 1)
            return embed
        self.button('➕', self.new, label = 'New', style = nextcord.ButtonStyle.success, row = 1)
        self.button('🗑️', self.delete, label = 'Delete', style = nextcord.ButtonStyle.danger, row = 1, disabled = self.selected is None)
        self.button('🌍', self.openZone, label = 'Time zone', row = 1)
        if self.isAdmin:
            self.button('👥', self.openServer, label = "Server's", row = 1)
        self.button('📖', self.howItWorks, label = 'How it works', row = 2)
        self.closeButton(row = 2)
        return embed

    def renderDraft(self):
        draft = self.draft
        moment = momentOf(draft['nextAt'])
        embed = presentation.brandEmbed(title = f'{EMOJI} New reminder', feature = FEATURE)
        embed.add_field(name = 'When', value = f"{stamp(moment, 'F')} ({stamp(moment, 'R')})", inline = False)
        embed.add_field(name = 'What', value = shorten(draft['text'], 1024), inline = False)
        embed.add_field(name = 'Repeats', value = when.describeRepeat(moment, draft['repeat'], self.zone), inline = True)
        embed.add_field(name = 'Where', value = describeWhere(draft, self.guild), inline = True)
        if self.isAdmin:
            embed.add_field(name = 'Pings', value = describeTarget(draft, self.guild)[len('pings '):] if draft.get('target') else 'You', inline = True)
        days = when.daysOf(draft['repeat']) if when.kindOf(draft['repeat']) == when.DAYS else (moment.astimezone(self.zone).weekday(),)
        def label(kind):
            return 'On days you choose…' if kind == when.DAYS else when.describeRepeat(moment, when.makeRepeat(kind, moment, self.zone), self.zone)
        repeats = nextcord.ui.Select(custom_id = pagination.newId('pick'), row = 0, options = [
            nextcord.SelectOption(label = label(kind), value = kind, emoji = '🔁', default = kind == when.kindOf(draft['repeat'])) for kind in when.REPEATS])
        repeats.callback = self.setRepeat(repeats, days)
        self.add_item(repeats)
        if when.kindOf(draft['repeat']) == when.DAYS:
            # any of the week's days, on the row the buttons leave free
            picker = nextcord.ui.Select(custom_id = pagination.newId('pick'), row = 4, min_values = 1, max_values = 7, placeholder = 'Pick the days…', options = [
                nextcord.SelectOption(label = name, value = str(number), default = number in days) for number, name in enumerate(when.WEEKDAY_NAMES)])
            picker.callback = self.setDays(picker)
            self.add_item(picker)
        channel = self.guild.get_channel_or_thread(int(draft['channelId']))
        here = f'Here in #{channel.name}' if channel is not None else 'Here'
        where = nextcord.ui.Select(custom_id = pagination.newId('pick'), row = 1, options = [
            nextcord.SelectOption(label = here, value = HERE, emoji = '📍', default = draft['where'] == HERE),
            nextcord.SelectOption(label = 'By DM', value = DM, emoji = '✉️', default = draft['where'] == DM)])
        where.callback = self.setWhere(where)
        self.add_item(where)
        if self.isAdmin:
            self.picker(nextcord.ui.RoleSelect, self.setRole, '👥 Ping a role instead of you…', row = 2)
        self.button('✅', self.save, label = 'Set it', style = nextcord.ButtonStyle.success, row = 3)
        self.button('✏️', self.edit, label = 'Edit', row = 3)
        if self.isAdmin:
            self.button('📣', self.pingEveryone, label = 'Everyone', row = 3, disabled = draft.get('target') == EVERYONE)
            self.button('🙋', self.pingMe, label = 'Just me', row = 3, disabled = not draft.get('target'))
        self.button('↩️', self.back, label = 'Back', row = 3)
        return embed

    def renderZone(self):
        now = utcNow()
        if self.zoneName:
            description = f"**{when.zoneLabel(self.zoneName)}** · {when.formatClock(now.astimezone(self.zone))} now. Pick another to change it, and your reminders move with you: 9am stays your 9am."
        else:
            description = 'Not set yet. Reminders need it, so "9am" means your 9am. It follows you to every server.'
        embed = presentation.brandEmbed(title = '🌍 Your time zone', description = description, feature = FEATURE)
        embed.add_field(name = 'Pick the one showing your time now', value = 'Not listed? Press ✏️ Other zone and type its name, like `Europe/Berlin`.', inline = False)
        options = [nextcord.SelectOption(label = f'{when.formatClock(now.astimezone(ZoneInfo(name)))} · {label}', description = cities, value = name, default = name == self.zoneName) for name, label, cities in when.ZONES]
        select = nextcord.ui.Select(custom_id = pagination.newId('pick'), placeholder = 'Pick your time zone…', options = options, row = 0)
        select.callback = self.pickZone(select)
        self.add_item(select)
        self.button('✏️', self.otherZone, label = 'Other zone', row = 1)
        self.button('↩️', self.back, label = 'Back', row = 1)
        self.closeButton(row = 1)
        return embed

    async def acknowledge(self, interaction, admin = False):
        if interaction.response.is_done() is not True:
            await interaction.response.defer()
        await predicates.recheck(interaction, feature = TOGGLE, admin = admin)

    async def show(self, interaction):
        embed = await self.render()
        await interaction.edit_original_message(embed = embed, view = self)

    def choose(self, select):
        async def callback(interaction):
            await self.acknowledge(interaction)
            self.selected = select.values[0]
            await self.show(interaction)
        return callback

    async def back(self, interaction):
        await self.acknowledge(interaction)
        self.screen = LIST
        self.draft = None
        self.waiting = None
        await self.show(interaction)

    async def openServer(self, interaction):
        await self.acknowledge(interaction, admin = True)
        self.screen = SERVER
        self.selected = None
        await self.show(interaction)

    async def openZone(self, interaction):
        await self.acknowledge(interaction)
        self.screen = ZONE
        await self.show(interaction)

    async def howItWorks(self, interaction):
        await self.acknowledge(interaction)
        self.notice = guides.reminders()
        await self.show(interaction)

    async def delete(self, interaction):
        await self.acknowledge(interaction, admin = self.screen == SERVER)
        reminder = dict(self.reminders).get(self.selected)
        if reminder is not None:
            await GBotFirebaseService.run(reminders_queries.removeReminder, self.guild.id, self.selected)
            self.notice = f"🗑️ Deleted \"{shorten(reminder['text'], 100)}\"."
        self.selected = None
        await self.show(interaction)

    def whenForm(self, text = '', what = ''):
        fields = [pagination.Field('When', placeholder = 'in 2 hours, tomorrow 9am, Thursday 8pm, Dec 25 10:00', default = text or None, maxLength = 100),
                  pagination.Field('What', placeholder = 'take out the trash', default = what or None, long = True, maxLength = Reminders.MAX_TEXT)]
        return pagination.Form('New reminder', fields, self.submitted)

    async def new(self, interaction):
        # a form has to be the press's first answer, so its checks wait for the submit
        await interaction.response.send_modal(self.whenForm())

    async def edit(self, interaction):
        await interaction.response.send_modal(self.whenForm(self.draft['whenText'], self.draft['text']))

    async def submitted(self, interaction, values):
        await self.acknowledge(interaction)
        await self.startDraft(values[0], values[1])
        await self.show(interaction)

    async def startDraft(self, whenText, text, repeat = when.ONCE, where = HERE, target = None):
        # the draft keeps the choices already made, so ✏️ Edit only changes the when and the what
        if self.draft is not None:
            repeat, where, target = self.draft['repeat'], self.draft['where'], self.draft.get('target')
        if self.zoneName is None:
            self.waiting = (whenText, text, repeat, where, target)
            self.screen = ZONE
            self.notice = f'🌍 Pick your time zone first, so "{shorten(whenText, 100)}" means your time.'
            return
        try:
            self.draft = self.cog.makeReminder(self.author, self.channelId, self.zone, whenText, text, repeat, where, target)
            self.screen = DRAFT
        except ReminderProblem as problem:
            self.notice = f'❌ {problem}'
            self.screen = DRAFT if self.draft is not None else LIST

    @property
    def channelId(self):
        return self.draft['channelId'] if self.draft is not None else self.originChannelId

    def setRepeat(self, select, days):
        async def callback(interaction):
            await self.acknowledge(interaction)
            self.redraft((select.values[0], days if select.values[0] == when.DAYS else None))
            await self.show(interaction)
        return callback

    def setDays(self, select):
        async def callback(interaction):
            await self.acknowledge(interaction)
            self.redraft((when.DAYS, [int(value) for value in select.values]))
            await self.show(interaction)
        return callback

    def redraft(self, repeat):
        # made again from what was typed, as a repeat by weekday can move its first time to one of its days
        draft = self.draft
        try:
            self.draft = self.cog.makeReminder(self.author, draft['channelId'], self.zone, draft['whenText'], draft['text'], repeat, draft['where'], draft.get('target'))
        except ReminderProblem as problem:
            self.notice = f'❌ {problem}'

    def setWhere(self, select):
        async def callback(interaction):
            await self.acknowledge(interaction)
            self.draft['where'] = select.values[0]
            await self.show(interaction)
        return callback

    async def setRole(self, interaction, role):
        await self.acknowledge(interaction, admin = True)
        self.draft['target'] = EVERYONE if role.is_default() else str(role.id)
        await self.show(interaction)

    async def pingEveryone(self, interaction):
        await self.acknowledge(interaction, admin = True)
        self.draft['target'] = EVERYONE
        await self.show(interaction)

    async def pingMe(self, interaction):
        await self.acknowledge(interaction)
        self.draft.pop('target', None)
        await self.show(interaction)

    async def save(self, interaction):
        await self.acknowledge(interaction, admin = bool(self.draft.get('target')))
        channel = self.guild.get_channel_or_thread(int(self.draft['channelId']))
        if not mayPing(interaction.user, channel, self.draft.get('target'), self.guild):
            self.notice = f'❌ {NO_PING[0].upper()}{NO_PING[1:]}'
            await self.show(interaction)
            return
        try:
            await self.cog.saveReminder(self.guild.id, self.draft)
            self.notice = f"{EMOJI} Reminder set for {stamp(momentOf(self.draft['nextAt']), 'F')}."
            self.screen = LIST
            self.draft = None
        except ReminderProblem as problem:
            self.notice = f'❌ {problem}'
        await self.show(interaction)

    def pickZone(self, select):
        async def callback(interaction):
            await self.acknowledge(interaction)
            await self.setZone(select.values[0])
            await self.show(interaction)
        return callback

    async def otherZone(self, interaction):
        await interaction.response.send_modal(pagination.Form('Your time zone', [pagination.Field('Time zone name', placeholder = 'Europe/Berlin, Asia/Kolkata, America/Denver', maxLength = 60)], self.typedZone))

    async def typedZone(self, interaction, values):
        await self.acknowledge(interaction)
        zone = when.zoneNamed(values[0])
        if zone is None:
            self.notice = f'❌ "{shorten(values[0], 60)}" isn\'t a time zone name. Try one like `Europe/Berlin` or `America/Denver`.'
        else:
            await self.setZone(zone.key)
        await self.show(interaction)

    async def setZone(self, zoneName):
        await GBotFirebaseService.run(changeZone, self.author.id, zoneName)
        self.zoneName = zoneName
        self.notice = f'🌍 Time zone set to **{when.zoneLabel(zoneName)}**.'
        if self.waiting is not None:
            waiting, self.waiting = self.waiting, None
            await self.startDraft(*waiting)
        else:
            self.screen = LIST

class SetReply(pagination.OwnedView):
    # the fast path's reply: ↩️ Undo, or the card
    def __init__(self, cog, serverId, reminderId):
        super().__init__()
        self.cog = cog
        self.serverId = serverId
        self.reminderId = reminderId
        self.button('↩️', self.undo, label = 'Undo')
        self.button(EMOJI, self.openCard, label = 'My reminders', style = nextcord.ButtonStyle.primary)

    async def undo(self, interaction):
        await interaction.response.defer()
        await predicates.recheck(interaction, feature = TOGGLE)
        await GBotFirebaseService.run(reminders_queries.removeReminder, self.serverId, self.reminderId)
        self.stop()
        await interaction.edit_original_message(content = '↩️ Reminder removed.', view = None)

    async def openCard(self, interaction):
        await interaction.response.defer(ephemeral = True)
        await predicates.recheck(interaction, feature = TOGGLE)
        await self.cog.openCard(interaction, interaction.user)

class Reminders(commands.Cog):

    MAX_PER_PERSON = 25
    MAX_TEXT = 500
    # more than this past due counts as sent late, not on time
    # past the minute between looks, so only one missed while GBot was offline says it's late
    LATE_AFTER = timedelta(minutes = 2)
    # how long a sent one-off can still be snoozed
    SNOOZE_KEEP = timedelta(days = 1)

    # How it sends on time without reading the database every second: it looks once a minute, and
    # each reminder due before the next look gets its own wake-up at its exact second. A little past
    # a minute, so one due right at the next look can't fall between the two.
    WAKE_AHEAD = timedelta(seconds = 65)

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()
        # (serverId, reminderId, nextAt) -> its wake-up, held so it isn't collected before it runs
        self.waking = {}

    def cog_unload(self):
        for task in self.waking.values():
            task.cancel()

    # Events
    @commands.Cog.listener()
    async def on_ready(self):
        try:
            self.reminder_loop.start()
        except RuntimeError:
            self.logger.info('reminder_loop task is already launched and is not completed.')

    # Commands
    @nextcord.slash_command(name = strings.REMINDERS_NAME, description = strings.REMINDERS_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer(TOGGLE, False, True)
    async def remindSlash(self,
                          interaction: nextcord.Interaction,
                          when: str = nextcord.SlashOption(name = 'when', required = False, max_length = 100, description = strings.REMINDERS_WHEN_DESCRIPTION),
                          what: str = nextcord.SlashOption(name = 'what', required = False, max_length = 500, description = strings.REMINDERS_WHAT_DESCRIPTION),
                          repeat: str = nextcord.SlashOption(name = 'repeat', required = False, choices = {'Once': 'once', 'Every day': 'daily', 'Every weekday': 'weekdays', 'Every week': 'weekly', 'Every month': 'monthly', 'Every year': 'yearly'}, description = strings.REMINDERS_REPEAT_DESCRIPTION),
                          where: str = nextcord.SlashOption(name = 'where', required = False, choices = {'Here': 'here', 'By DM': 'dm'}, description = strings.REMINDERS_WHERE_DESCRIPTION),
                          role: nextcord.Role = nextcord.SlashOption(name = 'role', required = False, description = strings.REMINDERS_ROLE_DESCRIPTION)):
        await self.commonRemind(interaction, interaction.user, when, what, repeat, where, role)

    @commands.command(name = strings.REMINDERS_NAME, aliases = strings.REMINDERS_ALIASES, brief = "- " + strings.REMINDERS_BRIEF, description = strings.REMINDERS_DESCRIPTION)
    @predicates.isFeatureEnabledForServer(TOGGLE, False)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def remind(self, ctx: Context, when: str = None, what: str = None, repeat: str = None, where: str = None, role: nextcord.Role = None):
        await self.commonRemind(ctx, ctx.author, when, what, repeat, where, role)

    async def commonRemind(self, context, author, whenText, what, repeat, where, role):
        if not any((whenText, what, repeat, where, role)):
            await pagination.openPrivately(context, EMOJI, 'Reminders', self.openCard, feature = TOGGLE)
            return
        if not whenText or not what:
            await presentation.sendError(context, f'Sorry {author.mention}, a reminder needs both `when` and `what`. Or use `/remind` on its own to see yours.', feature = FEATURE)
            return
        repeatChoice = when.readRepeat(repeat or when.ONCE)
        whereChoice = WHERE_WORDS.get((where or 'here').lower())
        if repeatChoice is None or whereChoice is None:
            await presentation.sendError(context, f'Sorry {author.mention}, {REPEAT_PROBLEM[:-1]}, and `where` here or dm.', feature = FEATURE)
            return
        target = None
        if role is not None:
            if not await GBotFirebaseService.run(utils.isUserAdminOrOwner, author, context.guild):
                await presentation.sendError(context, f'Sorry {author.mention}, only admins can remind a role.', feature = FEATURE)
                return
            target = EVERYONE if role.is_default() else str(role.id)
            if not mayPing(author, context.channel, target, context.guild):
                await presentation.sendError(context, f'Sorry {author.mention}, {NO_PING}', feature = FEATURE)
                return
        await presentation.deferIfSlash(context, ephemeral = True)
        zoneName = await GBotFirebaseService.run(reminders_queries.getTimezone, author.id)
        if zoneName is None:
            # the card asks for a time zone, then shows the reminder to set
            async def opener(opened, user):
                card = await self.newCard(opened, user)
                card.waiting = (whenText, what, repeatChoice, whereChoice, target)
                card.screen = ZONE
                card.notice = f'🌍 Pick your time zone first, so "{shorten(whenText, 100)}" means your time.'
                await card.send(opened, True, embed = await card.render(), view = card)
            await pagination.openPrivately(context, '🌍', 'Your time zone', opener, feature = TOGGLE)
            return
        try:
            reminder = self.makeReminder(author, context.channel.id, ZoneInfo(zoneName), whenText, what, repeatChoice, whereChoice, target)
            reminderId = await self.saveReminder(context.guild.id, reminder)
        except ReminderProblem as problem:
            await presentation.sendError(context, f'Sorry {author.mention}, {problem}', feature = FEATURE)
            return
        moment = momentOf(reminder['nextAt'])
        place = 'by DM' if whereChoice == DM else 'here'
        repeats = '' if reminder['repeat'] == when.ONCE else f", repeating {when.repeatPhrase(moment, reminder['repeat'], ZoneInfo(zoneName))}"
        view = SetReply(self, context.guild.id, reminderId)
        # one named for the minute it is goes off now, rather than "set for 40 seconds ago"
        shown = 'now, going off right away' if moment <= utcNow() else f"**{stamp(moment, 'F')}** ({stamp(moment, 'R')})"
        await view.send(context, True, content = f"{EMOJI} Reminder set for {shown}, {place}{repeats}.", view = view)

    async def newCard(self, context, author):
        isAdmin = await GBotFirebaseService.run(utils.isUserAdminOrOwner, author, context.guild)
        card = RemindersCard(self, context.guild, author, isAdmin)
        card.originChannelId = context.channel.id
        return card

    async def openCard(self, context, author):
        card = await self.newCard(context, author)
        await card.send(context, True, embed = await card.render(), view = card)

    def cardFacts(self, userId, serverId):
        # one step on the database worker: the person's time zone and this server's reminders
        return reminders_queries.getTimezone(userId), soonest(reminders_queries.getServerReminders(serverId))

    def makeReminder(self, author, channelId, zone, whenText, text, repeat, where, target):
        # Reads and checks a reminder, without saving it. Raises ReminderProblem with what to say.
        now = utcNow().astimezone(zone)
        try:
            moment, timer = when.readWhen(whenText, now)
        except when.WhenInThePast:
            raise ReminderProblem(f'"{shorten(whenText, 100)}" has already gone. Pick a time still to come.')
        except when.WhenNotUnderstood:
            raise ReminderProblem(f'I couldn\'t read "{shorten(whenText, 100)}" as a time. Try {EXAMPLES}.')
        except when.WhenTooFar:
            raise ReminderProblem(TOO_FAR)
        # a repeat comes as a kind, a kind with its days, or one already made exact, as a draft's is
        kind, days = repeat if isinstance(repeat, tuple) else (when.kindOf(repeat), when.daysOf(repeat) if when.kindOf(repeat) == when.DAYS else None)
        try:
            repeat = when.makeRepeat(kind, moment, zone, days)
        except when.RepeatNotUnderstood:
            raise ReminderProblem(REPEAT_PROBLEM)
        # a repeat by weekday starts on one of its days, unless a timer said when it starts
        if not timer:
            moment = when.onOrAfter(moment, repeat, zone)
        # calendar years, so the last day fits when a year has a Feb 29
        if moment > when.addMonths(now, 12 * MAX_YEARS_AHEAD):
            raise ReminderProblem(TOO_FAR)
        text = text.strip()
        if len(text) > self.MAX_TEXT:
            raise ReminderProblem(f'a reminder can be at most {self.MAX_TEXT} characters.')
        reminder = {'userId': str(author.id), 'channelId': str(channelId), 'text': text, 'nextAt': moment.astimezone(timezone.utc).isoformat(),
                    'repeat': repeat, 'where': where, 'whenText': whenText}
        if target:
            reminder['target'] = target
        return reminder

    async def saveReminder(self, serverId, reminder):
        # the count and the write in one step, so two at once can't pass the limit
        def save():
            existing = [item for item in (reminders_queries.getServerReminders(serverId) or {}).values() if item['userId'] == reminder['userId'] and isPending(item)]
            if len(existing) >= self.MAX_PER_PERSON:
                return None
            return reminders_queries.addReminder(serverId, {key: value for key, value in reminder.items() if key != 'whenText'})
        reminderId = await GBotFirebaseService.run(save)
        if reminderId is None:
            raise ReminderProblem(f'you have {self.MAX_PER_PERSON} reminders here already. Delete one in `/remind` first.')
        # one due before the next look, like "in 30 seconds", gets its wake-up now
        guild = self.client.get_guild(int(serverId))
        if guild is not None:
            self.wakeFor(guild, reminderId, reminder['nextAt'])
        return reminderId

    # Tasks
    @tasks.loop(seconds = 60)
    async def reminder_loop(self):
        try:
            everything = await GBotFirebaseService.run(reminders_queries.getAllReminders) or {}
            now = utcNow()
            # only the servers this bot is in: the other bot sharing the database sends its own
            guilds = {str(guild.id): guild for guild in self.client.guilds}
            for serverId, reminders in everything.items():
                guild = guilds.get(serverId)
                if guild is None:
                    continue
                due = [(reminderId, reminder) for reminderId, reminder in (reminders or {}).items() if self.isDue(reminder, now)]
                for reminderId, reminder in (reminders or {}).items():
                    if isPending(reminder) and not self.isDue(reminder, now):
                        self.wakeFor(guild, reminderId, reminder['nextAt'])
                if due and await GBotFirebaseService.run(self.mayDeliver, guild.id):
                    for reminderId, reminder in due:
                        # one reminder's failure stays its own
                        try:
                            await self.fire(guild, reminderId, reminder, now)
                        except Exception as e:
                            self.logger.error(f'Reminder {reminderId} in server {serverId} failed: {e}')
                for reminderId, reminder in (reminders or {}).items():
                    if reminder.get('delivered') and now - momentOf(reminder['delivered']) > self.SNOOZE_KEEP:
                        await GBotFirebaseService.run(reminders_queries.removeReminder, serverId, reminderId)
        except Exception as e:
            self.logger.error(f'Error in Reminders.reminder_loop(): {e}')

    def isDue(self, reminder, now):
        return isPending(reminder) and momentOf(reminder['nextAt']) <= now

    def wakeFor(self, guild, reminderId, nextAt):
        # a wake-up at its exact second, for one due before the next look
        key = (str(guild.id), reminderId, nextAt)
        if key in self.waking or momentOf(nextAt) - utcNow() > self.WAKE_AHEAD:
            return
        self.waking[key] = asyncio.create_task(self.wake(guild, reminderId, nextAt, key))

    async def wake(self, guild, reminderId, nextAt, key):
        try:
            # until its second, by the wall clock it's due by
            while (left := (momentOf(nextAt) - utcNow()).total_seconds()) > 0:
                await asyncio.sleep(left)
            reminder = await GBotFirebaseService.run(reminders_queries.getReminder, guild.id, reminderId)
            # deleted, snoozed or moved since, it isn't this wake-up's any more
            if reminder is None or reminder.get('nextAt') != nextAt or not isPending(reminder):
                return
            if await GBotFirebaseService.run(self.mayDeliver, guild.id):
                await self.fire(guild, reminderId, reminder, utcNow())
        except Exception as e:
            self.logger.error(f'Reminder {reminderId} in server {guild.id} failed: {e}')
        finally:
            self.waking.pop(key, None)

    def claim(self, serverId, reminderId, nextAt, changes):
        # One step on the database worker: still due as it was read, then moved on. A wake-up and a
        # look can both find a reminder due, and only the first to claim it sends it.
        current = reminders_queries.getReminder(serverId, reminderId)
        if current is None or not isPending(current) or current.get('nextAt') != nextAt:
            return False
        reminders_queries.updateReminder(serverId, reminderId, changes)
        return True

    def mayDeliver(self, serverId):
        # turned off, or a trial over: kept, and sent once it's back on, late
        return config_queries.getServerValue(serverId, TOGGLE) == True and access.isActive(serverId)

    async def fire(self, guild, reminderId, reminder, now):
        member = guild.get_member(int(reminder['userId']))
        if member is None:
            # whoever set it has left the server
            await GBotFirebaseService.run(reminders_queries.removeReminder, guild.id, reminderId)
            return
        dueAt = momentOf(reminder['nextAt'])
        zone = zoneOrUtc(await GBotFirebaseService.run(reminders_queries.getTimezone, member.id))
        repeat = reminder.get('repeat', when.ONCE)
        # moved on before sending, so a failure part way can't send it twice
        if repeat == when.ONCE:
            changes = {'delivered': now.isoformat()}
            nextAt = None
        else:
            nextAt = when.nextAfter(dueAt, repeat, zone, now)
            changes = {'nextAt': nextAt.astimezone(timezone.utc).isoformat()}
        if not await GBotFirebaseService.run(self.claim, guild.id, reminderId, reminder['nextAt'], changes):
            return
        await self.deliver(guild, member, reminderId, reminder, dueAt, nextAt, now - dueAt > self.LATE_AFTER, zone)

    def deliveredEmbed(self, guild, member, reminder, dueAt, nextAt, late, zone, inDm):
        lines = []
        if reminder.get('target'):
            lines.append(f'From {member.mention}')
        if inDm:
            lines.append(f'From **{guild.name}**')
        if nextAt is not None:
            lines.append(f"{when.describeRepeat(nextAt, reminder['repeat'], zone)} · next {stamp(nextAt, 'R')}")
        if late:
            lines.append(f"Late: this was due {stamp(dueAt, 'f')}, while GBot was offline.")
        build = presentation.warningEmbed if late else presentation.brandEmbed
        embed = build(title = f'{EMOJI} Reminder', description = reminder['text'], feature = FEATURE)
        if lines:
            embed.add_field(name = '​', value = '\n'.join(lines), inline = False)
        return embed

    def deliveredButtons(self, serverId, reminderId, reminder, snoozed = False):
        # Snoozing, Done and ✖️ are for this one; Skip and Stop for the whole repeat. Once snoozed,
        # the snooze buttons go: the snooze arrives as its own message, which is where to snooze again.
        def button(label, emoji, action, style = nextcord.ButtonStyle.secondary):
            return pagination.persistentButton(label, emoji, style, f'{BUTTON_PREFIX}{action}:{serverId}:{reminderId}')
        def tidy(label, emoji, action, style = nextcord.ButtonStyle.secondary):
            return pagination.persistentButton(label, emoji, style, f"{BUTTON_PREFIX}{action}:{serverId}:{reminderId}:{reminder['userId']}")
        if reminder.get('repeat', when.ONCE) == when.ONCE:
            buttons = [] if snoozed else [button('10 min', '💤', SNOOZE_MINUTES), button('1 hour', '💤', SNOOZE_HOUR), button('Tomorrow', '💤', SNOOZE_TOMORROW)]
        else:
            buttons = ([] if snoozed else [button('10 min', '💤', SNOOZE_MINUTES)]) + [button('Skip next', '⏭️', SKIP), button('Stop repeating', '🛑', STOP, nextcord.ButtonStyle.danger)]
        buttons.append(tidy('Done', '✅', DONE, nextcord.ButtonStyle.success))
        # deleting it is only for one that's theirs alone: a role's or everyone's is for others too
        if reminder.get('where') == DM or not reminder.get('target'):
            buttons.append(tidy(None, pagination.CustomButtonMenuPages.STOP, DISMISS))
        return pagination.persistentView(buttons)

    async def deliver(self, guild, member, reminderId, reminder, dueAt, nextAt, late, zone):
        view = pagination.stopped(self.deliveredButtons(guild.id, reminderId, reminder))
        if reminder.get('where') == DM:
            try:
                await member.send(embed = self.deliveredEmbed(guild, member, reminder, dueAt, nextAt, late, zone, True), view = view)
                return
            except nextcord.HTTPException:
                # DMs closed: the channel it was set in instead, saying so
                reminder = dict(reminder, text = f"{reminder['text']}\n\n-# Couldn't DM you, so it's here.")
        channel = guild.get_channel_or_thread(int(reminder['channelId']))
        if channel is None:
            self.logger.info(f'Reminder {reminderId} in server {guild.id} had nowhere to go.')
            return
        target = reminder.get('target')
        if not mayPing(member, channel, target, guild):
            # whoever set it can't make that ping any more, so it reminds only them
            target = None
        role = guild.get_role(int(target)) if target and target != EVERYONE else None
        if target == EVERYONE:
            content, allowed = '@everyone', nextcord.AllowedMentions(everyone = True, roles = False, users = False)
        elif role is not None:
            content, allowed = role.mention, nextcord.AllowedMentions(everyone = False, roles = [role], users = False)
        else:
            content, allowed = member.mention, nextcord.AllowedMentions(everyone = False, roles = False, users = [member])
        await channel.send(content = content, embed = self.deliveredEmbed(guild, member, reminder, dueAt, nextAt, late, zone, False), view = view, allowed_mentions = allowed)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: nextcord.Interaction):
        parts = pagination.persistentParts(interaction, BUTTON_PREFIX)
        if parts is None:
            return
        try:
            if parts[0] in (DONE, DISMISS):
                await self.tidyDelivered(interaction, *parts)
            else:
                await self.pressDelivered(interaction, parts[0], parts[1], parts[2])
        except Exception as e:
            await presentation.sendInteractionError(interaction, e)

    async def tidyDelivered(self, interaction, action, serverId, reminderId, userId):
        # ✅ Done says no more from it: a snooze is cancelled, though a repeat carries on. ✖️ only
        # clears the message, as dismissing a notification does, so a snooze still comes. No re-check
        # of access: tidying away your own message needs none, even after a trial ends.
        await interaction.response.defer()
        if str(interaction.user.id) != userId:
            await interaction.send(f'Only <@{userId}> can use these buttons.', ephemeral = True)
            return
        def finish():
            # Returns whether a snooze was cancelled. A sent one-off can't be snoozed once its message
            # is gone, so either button ends it then; only Done ends one snoozed, or a repeat's snooze.
            reminder = reminders_queries.getReminder(serverId, reminderId)
            once = reminder is not None and reminder.get('repeat', when.ONCE) == when.ONCE
            if once and (reminder.get('delivered') or action == DONE):
                reminders_queries.removeReminder(serverId, reminderId)
            if action != DONE:
                return False
            # a one-off still pending was snoozed; a repeat's snoozes are copies naming it
            snoozedItself = once and not reminder.get('delivered')
            return removeSnoozes(serverId, reminderId) or snoozedItself
        cancelled = await GBotFirebaseService.run(finish)
        if action == DISMISS:
            try:
                await interaction.message.delete()
                return
            except nextcord.HTTPException:
                pass
        embed = showStatus(interaction.message.embeds[0], '✅ Done, and its snooze cancelled.' if cancelled else '✅ Done.')
        await interaction.edit_original_message(embed = embed, view = self.keptButtons(interaction, DISMISS))

    def keptButtons(self, interaction, *actions):
        # When a press clears the others, these stay where they were offered: ✖️, so one marked done
        # or stopped can still be deleted.
        kept = [item for row in interaction.message.components for item in getattr(row, 'children', [])
                if any((getattr(item, 'custom_id', None) or '').startswith(f'{BUTTON_PREFIX}{action}:') for action in actions)]
        if not kept:
            return None
        return pagination.stopped(pagination.persistentView([pagination.persistentButton(item.label or None, item.emoji, item.style, item.custom_id) for item in kept]))

    async def pressDelivered(self, interaction, action, serverId, reminderId):
        await interaction.response.defer()
        reminder = await GBotFirebaseService.run(reminders_queries.getReminder, serverId, reminderId)
        if reminder is None:
            await interaction.edit_original_message(view = None)
            await interaction.send('That reminder is gone.', ephemeral = True)
            return
        if str(interaction.user.id) != reminder['userId']:
            await interaction.send(f"Only <@{reminder['userId']}> can use these buttons.", ephemeral = True)
            return
        await predicates.recheck(interaction, feature = TOGGLE, privateMessagesAllowed = True)
        zone = zoneOrUtc(await GBotFirebaseService.run(reminders_queries.getTimezone, interaction.user.id))
        now = utcNow()
        repeat = reminder.get('repeat', when.ONCE)
        keepButtons = False
        embed = interaction.message.embeds[0]
        nextShown = KEEP_NEXT
        if action in (SNOOZE_MINUTES, SNOOZE_HOUR, SNOOZE_TOMORROW):
            if action == SNOOZE_TOMORROW:
                # the time it went off, a day on
                moment = when.nextAfter(when.advance(momentOf(reminder['nextAt']), when.DAILY, zone), when.DAILY, zone, now)
            else:
                moment = now + timedelta(minutes = 10 if action == SNOOZE_MINUTES else 60)
            nextAt = moment.astimezone(timezone.utc).isoformat()
            if repeat == when.ONCE:
                await GBotFirebaseService.run(reminders_queries.updateReminder, serverId, reminderId, {'nextAt': nextAt, 'delivered': None, 'snoozed': True})
            else:
                # a repeat stays as it is, with a one-off copy for the snooze
                snoozed = {key: value for key, value in reminder.items() if key not in ('delivered',)}
                # it names its repeat, so Done and 🛑 Stop can cancel it
                await GBotFirebaseService.run(reminders_queries.addReminder, serverId, dict(snoozed, nextAt = nextAt, repeat = when.ONCE, snoozeOf = reminderId))
            line = f"💤 Snoozed until {stamp(moment, 't')}."
            # not final: Done can cancel it, and a repeat can still be skipped or stopped
            keepButtons = True
        elif action == SKIP:
            moment = when.advance(momentOf(reminder['nextAt']), repeat, zone)
            await GBotFirebaseService.run(reminders_queries.updateReminder, serverId, reminderId, {'nextAt': moment.astimezone(timezone.utc).isoformat()})
            skipped = skippedSoFar(embed) + 1
            line = f"⏭️ Skipped {'one' if skipped == 1 else skipped}. Next {stamp(moment, 'f')}."
            keepButtons = True
            nextShown = moment
        else:
            # everything from it, a snooze included: Stop means no more
            def stop():
                reminders_queries.removeReminder(serverId, reminderId)
                return removeSnoozes(serverId, reminderId)
            line = '🛑 Stopped repeating, and its snooze.' if await GBotFirebaseService.run(stop) else '🛑 Stopped repeating.'
            nextShown = None
        embed = showStatus(embed, line, nextShown)
        if keepButtons:
            snoozed = any(field.value.startswith('💤') for field in embed.fields)
            view = pagination.stopped(self.deliveredButtons(serverId, reminderId, reminder, snoozed))
        else:
            # stopped, only ✖️
            view = self.keptButtons(interaction, DISMISS)
        await interaction.edit_original_message(embed = embed, view = view)

def setup(client: commands.Bot):
    client.add_cog(Reminders(client))
