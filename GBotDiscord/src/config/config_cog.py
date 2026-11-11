#region IMPORTS
import datetime
import logging
import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context

from GBotDiscord.src import presentation
from GBotDiscord.src import strings
from GBotDiscord.src import pagination
from GBotDiscord.src import predicates
from GBotDiscord.src import access
from GBotDiscord.src import server_setup
from GBotDiscord.src import utils
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.music.music_cog import Music
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.firebase import GBotFirebaseService
#endregion

# the toggles in the order the card shows them, which is strings.FEATURE_EMOJIS's
# DISCONTINUED 'toggle_halo' would be one of them, with strings.FEATURE_EMOJIS and FEATURE_NAMES
TOGGLES = list(strings.FEATURE_EMOJIS)
TOGGLE_LABELS = {'toggle_legacy_prefix_commands': 'Prefix commands'}
# a feature that needs another turns it on with itself, and turning that one off turns it off too
DEPENDENCIES = {
    'toggle_gtrade': ['toggle_gcoin'],
    'toggle_storms': ['toggle_gcoin'],
    'toggle_who_dis': ['toggle_gcoin']
}
TOGGLES_PER_ROW = 5
MAX_REPORT_LIST_CHARACTERS = 500

MAIN = 'main'
ROLES = 'roles'
REPORTS = 'reports'

REPORT_BUTTON_PREFIX = 'report:'
REPORT_HANDLED = 'handled'
REPORT_DISMISSED = 'dismissed'
REPORT_HISTORY = 'history'

def dependentsOf(toggle):
    return [dependent for dependent, needs in DEPENDENCIES.items() if toggle in needs]

def toggleName(toggle):
    return TOGGLE_LABELS.get(toggle, strings.FEATURE_NAMES[toggle])

def channelName(guild, channelId):
    channel = guild.get_channel(int(channelId)) if channelId else None
    return f'#{channel.name}' if channel is not None else 'Not set'

def roleName(guild, roleId):
    role = guild.get_role(int(roleId)) if roleId else None
    return f'@{role.name}' if role is not None else 'Not set'

def mentionOrNotSet(serverConfig, key, kind):
    return f'<{kind}{serverConfig[key]}>' if serverConfig.get(key) else 'Not set'

def timestampOf(isoTime):
    return int(datetime.datetime.fromisoformat(isoTime).timestamp())

def describeReport(report):
    outcome = ''
    if report.get('outcome') == REPORT_HANDLED:
        outcome = f" · ✅ handled by <@{report['outcomeBy']}>"
    elif report.get('outcome') == REPORT_DISMISSED:
        outcome = f" · 🚫 not an issue, said <@{report['outcomeBy']}>"
    # cut short, as a page of five has to fit in one embed
    text = ' '.join(report.get('what', '').split())
    if len(text) > MAX_REPORT_LIST_CHARACTERS:
        text = text[:MAX_REPORT_LIST_CHARACTERS] + '…'
    what = f"\n> {text}" if text else ''
    return f"**<t:{timestampOf(report['when'])}:d>** · by <@{report['reporterId']}> · {report['where']}{outcome}{what}"

def capturedText(messages, limit = 1024):
    # The reported messages, quoted with their times, as the evidence an admin reads. Each gets an
    # even share of the field, so one long message can't push the others off the card.
    if not messages:
        return 'None could be captured.'
    share = limit // len(messages) - 1
    lines = []
    for message in messages:
        text = ' '.join(message.content.split()) if message.content else ''
        extras = [attachment.url for attachment in message.attachments] + [sticker.url for sticker in message.stickers]
        if extras:
            text = f"{text} 📎 {' '.join(extras)}".strip()
        line = f'> <t:{int(message.created_at.timestamp())}:t> {text or "*(nothing but an embed)*"}'
        if len(line) > share:
            line = line[:share - 1] + '…'
        lines.append(line)
    return '\n'.join(lines)

def versionOrder(version):
    # "8.10" comes after "8.9", which as plain numbers it wouldn't
    return tuple(int(part) for part in str(version).split('.'))

class ConfigCard(pagination.OwnedView):
    # /config: the server's settings on one card, changed with its buttons and pickers. Admins only,
    # checked again on every press.
    REPORTS_PER_PAGE = 5

    def __init__(self, cog, guild):
        super().__init__()
        self.cog = cog
        self.guild = guild
        self.screen = MAIN
        self.notice = None
        self.prefix = '.'
        self.member = None
        self.reports = []
        self.page = 0
        self.trialEnds = None

    async def render(self):
        serverConfig = await GBotFirebaseService.run(config_queries.getAllServerValues, self.guild.id) or {}
        self.prefix = serverConfig.get('prefix', '.')
        self.trialEnds = await GBotFirebaseService.run(access.trialEnding, self.guild.id)
        self.clear_items()
        if self.screen == ROLES:
            embed = self.renderRoles(serverConfig)
        elif self.screen == REPORTS:
            embed = self.renderReports()
        else:
            embed = self.renderMain(serverConfig)
        if self.notice:
            embed.add_field(name = '​', value = self.notice, inline = False)
            self.notice = None
        return embed

    def renderMain(self, serverConfig):
        # DISCONTINUED toggle_halo, role_halo_recent, role_halo_most, channel_halo_motd, channel_halo_competition
        embed = presentation.brandEmbed(title = '⚙️ GBot Configuration', description = 'Press a feature to turn it on or off: green is on. Pick the channels below.', feature = 'Config')
        embed.add_field(name = 'Channels', value = f"Storms: {mentionOrNotSet(serverConfig, 'channel_storms', '#')}\nAdmin: {mentionOrNotSet(serverConfig, 'channel_admin', '#')}", inline = True)
        embed.add_field(name = 'Roles', value = f"Admin: {mentionOrNotSet(serverConfig, 'role_admin', '@&')}\nWho Dis: {mentionOrNotSet(serverConfig, 'role_who_dis', '@&')}", inline = True)
        embed.add_field(name = 'Prefix', value = f'`{self.prefix}`', inline = True)
        problems = server_setup.setupProblems(self.guild, serverConfig)
        if problems:
            text = '\n'.join(f'• {problem}' for problem in problems)
            embed.add_field(name = '⚠️ Setup', value = text if len(text) <= 1024 else text[:1023] + '…', inline = False)
        if self.trialEnds is not None:
            embed.add_field(name = '🎁 Free trial', value = f"Ends {access.timestamp(self.trialEnds, 'R')}. {access.howToSubscribe(self.guild.id)}", inline = False)
        if self.guild.icon is not None:
            embed.set_thumbnail(url = self.guild.icon.url)
        for index, toggle in enumerate(TOGGLES):
            # get: a field added in this version may not have reached this server yet
            style = nextcord.ButtonStyle.success if serverConfig.get(toggle) == True else nextcord.ButtonStyle.secondary
            self.button(strings.FEATURE_EMOJIS[toggle], self.toggleCallback(toggle), label = toggleName(toggle), style = style, row = index // TOGGLES_PER_ROW)
        text = [nextcord.ChannelType.text]
        self.picker(nextcord.ui.ChannelSelect, self.channelCallback('channel_storms', 'Storms'), f"🌧️ Storms channel: {channelName(self.guild, serverConfig.get('channel_storms'))}", row = 2, channelTypes = text)
        self.picker(nextcord.ui.ChannelSelect, self.channelCallback('channel_admin', 'Admin'), f"🛡️ Admin channel: {channelName(self.guild, serverConfig.get('channel_admin'))}", row = 3, channelTypes = text)
        # DISCONTINUED
        # self.picker(nextcord.ui.ChannelSelect, self.channelCallback('channel_halo_motd', 'Halo MOTD'), ...)
        # self.picker(nextcord.ui.ChannelSelect, self.channelCallback('channel_halo_competition', 'Halo Competition'), ...)
        self.button('👥', self.openRoles, label = 'Roles', style = nextcord.ButtonStyle.primary, row = 4)
        self.button('✏️', self.openPrefix, label = 'Prefix', style = nextcord.ButtonStyle.primary, row = 4)
        self.button('🚩', self.openReports, label = 'Reports', style = nextcord.ButtonStyle.primary, row = 4)
        self.button('🤖', self.openAgent, label = 'Agent settings', row = 4)
        self.closeButton(row = 4)
        return embed

    def renderRoles(self, serverConfig):
        embed = presentation.brandEmbed(title = '👥 Roles', description = 'The server owner, and anyone with the admin role, counts as a GBot admin. Who Dis pairs up members with its role.', feature = 'Config')
        embed.add_field(name = 'Admin', value = mentionOrNotSet(serverConfig, 'role_admin', '@&'), inline = True)
        embed.add_field(name = 'Who Dis', value = mentionOrNotSet(serverConfig, 'role_who_dis', '@&'), inline = True)
        self.picker(nextcord.ui.RoleSelect, self.roleCallback('role_admin', 'Admin'), f"🛡️ Admin role: {roleName(self.guild, serverConfig.get('role_admin'))}", row = 0)
        self.picker(nextcord.ui.RoleSelect, self.roleCallback('role_who_dis', 'Who Dis'), f"❓ Who Dis role: {roleName(self.guild, serverConfig.get('role_who_dis'))}", row = 1)
        # DISCONTINUED
        # self.picker(nextcord.ui.RoleSelect, self.roleCallback('role_halo_recent', 'Halo Weekly Winner'), ...)
        # self.picker(nextcord.ui.RoleSelect, self.roleCallback('role_halo_most', 'Halo Most Wins'), ...)
        self.button('↩️', self.back, label = 'Back', row = 2)
        self.closeButton(row = 2)
        return embed

    def renderReports(self):
        if self.member is None:
            embed = presentation.brandEmbed(title = '🚩 Reports', description = 'Pick a member to see the reports on them.\n\nAnyone can report a message or a member to the admins: right-click it, then **Apps**.', feature = 'Config')
        else:
            pages = max(1, -(-len(self.reports) // self.REPORTS_PER_PAGE))
            self.page = min(self.page, pages - 1)
            shown = self.reports[self.page * self.REPORTS_PER_PAGE:(self.page + 1) * self.REPORTS_PER_PAGE]
            description = '\n\n'.join(describeReport(report) for report in shown) or f'No reports on {self.member.mention}.'
            embed = presentation.brandEmbed(title = f'🚩 Reports on {self.member.display_name} · {len(self.reports)}', description = description, feature = 'Config')
            embed.set_footer(text = f'Page {self.page + 1} / {pages} • {presentation.footerText("Config")}')
            if pages > 1:
                self.button('◀️', self.previousPage, row = 1, disabled = self.page == 0)
                self.button('▶️', self.nextPage, row = 1, disabled = self.page == pages - 1)
        self.picker(nextcord.ui.UserSelect, self.pickMember, 'Pick a member…', row = 0)
        self.button('↩️', self.back, label = 'Back', row = 1)
        self.closeButton(row = 1)
        return embed

    async def acknowledge(self, interaction):
        # Discord allows 3 seconds, and what follows waits on the database
        if interaction.response.is_done() is not True:
            await interaction.response.defer()
        await predicates.recheck(interaction, admin = True)

    async def show(self, interaction):
        embed = await self.render()
        await interaction.edit_original_message(embed = embed, view = self)

    def toggleCallback(self, toggle):
        async def callback(interaction):
            await self.acknowledge(interaction)
            self.notice = await self.cog.toggleFeature(interaction, toggle)
            await self.show(interaction)
        return callback

    def channelCallback(self, key, label):
        async def callback(interaction, channel):
            await self.acknowledge(interaction)
            await GBotFirebaseService.run(config_queries.setServerValue, self.guild.id, key, str(channel.id))
            self.notice = f'⚙️ {label} channel set to {channel.mention}.'
            await self.show(interaction)
        return callback

    def roleCallback(self, key, label):
        async def callback(interaction, role):
            await self.acknowledge(interaction)
            # Who Dis gives its role out, so GBot has to be able to
            problem = server_setup.roleProblem(self.guild, role) if key == 'role_who_dis' else None
            if problem is not None:
                self.notice = f'❌ {problem}'
                await self.show(interaction)
                return
            await GBotFirebaseService.run(config_queries.setServerValue, self.guild.id, key, str(role.id))
            self.notice = f'⚙️ {label} role set to {role.mention}.'
            await self.show(interaction)
        return callback

    async def openRoles(self, interaction):
        await self.acknowledge(interaction)
        self.screen = ROLES
        await self.show(interaction)

    async def openReports(self, interaction):
        await self.acknowledge(interaction)
        self.screen = REPORTS
        self.member = None
        await self.show(interaction)

    async def back(self, interaction):
        await self.acknowledge(interaction)
        self.screen = MAIN
        await self.show(interaction)

    async def pickMember(self, interaction, member):
        await self.acknowledge(interaction)
        self.member = member
        self.page = 0
        self.reports = await GBotFirebaseService.run(config_queries.getReportsOn, self.guild.id, member.id)
        await self.show(interaction)

    async def previousPage(self, interaction):
        await self.acknowledge(interaction)
        self.page = max(0, self.page - 1)
        await self.show(interaction)

    async def nextPage(self, interaction):
        await self.acknowledge(interaction)
        self.page += 1
        await self.show(interaction)

    async def openPrefix(self, interaction):
        # a form has to be the press's first answer, so its checks wait for the submit
        form = pagination.Form('Command prefix', [pagination.Field('Prefix for prefix commands', default = self.prefix, maxLength = 10)], self.savePrefix)
        await interaction.response.send_modal(form)

    async def savePrefix(self, interaction, values):
        await self.acknowledge(interaction)
        prefix = values[0]
        if prefix:
            await GBotFirebaseService.run(config_queries.setServerValue, self.guild.id, 'prefix', prefix)
            self.notice = f'⚙️ Prefix set to `{prefix}`.'
        else:
            self.notice = '❌ A prefix needs at least one character that isn\'t a space.'
        await self.show(interaction)

    async def openAgent(self, interaction):
        await self.acknowledge(interaction)
        await self.cog.client.get_cog('Agent').openCard(interaction, interaction.user)

class Config(commands.Cog):

    NUM_MESSAGES_TO_REPORT = 5
    MAX_HISTORY_TO_SEARCH = 100
    RECENT_REPORT_DAYS = 30

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()

    #Events
    @commands.Cog.listener()
    async def on_guild_join(self, guild: nextcord.Guild):
        self.logger.info(f'GBot was added to guild {guild.id} ({guild.name}).')
        await GBotFirebaseService.run(config_queries.initServerValues, guild.id, GBotPropertiesManager.GBOT_VERSION)
        trialEnds = await GBotFirebaseService.run(access.startTrial, guild.id)
        await presentation.sendWelcome(guild, trialEnds)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: nextcord.Guild):
        self.logger.info(f'GBot was removed from guild {guild.id} ({guild.name}).')
        await GBotFirebaseService.run(config_queries.clearServerValues, guild.id)

    @commands.Cog.listener()
    async def on_ready(self):
        await GBotFirebaseService.run(self.prepareServers)

    def prepareServers(self):
        currentBotVersion = GBotPropertiesManager.GBOT_VERSION
        allServers = config_queries.getAllServers() or {}
        # a server that added the bot while it was offline never gets a join event, only a place in
        # client.guilds. Only ever fills a missing entry, so it can't wipe anything the other bot uses.
        for guild in self.client.guilds:
            if str(guild.id) not in allServers:
                self.logger.info(f'GBot was added to guild {guild.id} ({guild.name}) while offline.')
                config_queries.initServerValues(guild.id, currentBotVersion)
                access.startTrial(guild.id)
        servers = utils.filterGuildsForInstance(self.client, allServers)
        for serverId, serverValues in servers.items():
            serverDatabaseVersion = serverValues['version']
            if versionOrder(serverDatabaseVersion) < versionOrder(currentBotVersion):
                self.logger.info(f"Upgrading server {serverId} database version from {serverDatabaseVersion} to {currentBotVersion}.")
                config_queries.upgradeServerValues(serverId, currentBotVersion)

    # Commands
    @nextcord.slash_command(name = strings.CONFIG_NAME, description = strings.CONFIG_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isMessageAuthorAdmin(True)
    async def configSlash(self, interaction: nextcord.Interaction):
        await self.commonConfig(interaction)

    @commands.command(name = strings.CONFIG_NAME, aliases = strings.CONFIG_ALIASES, brief = "- " + strings.CONFIG_BRIEF, description = strings.CONFIG_DESCRIPTION)
    @predicates.isMessageAuthorAdmin()
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def config(self, ctx: Context):
        await self.commonConfig(ctx)

    async def commonConfig(self, context):
        # private: it names the admin channel and roles, and only admins can use it
        await pagination.openPrivately(context, '⚙️', 'GBot settings', self.openCard, admin = True)

    async def openCard(self, context, author):
        card = ConfigCard(self, context.guild)
        await card.send(context, True, embed = await card.render(), view = card)

    async def toggleFeature(self, interaction, toggle):
        serverId = interaction.guild.id
        newValue, enabled, disabled = await GBotFirebaseService.run(self.applyToggle, serverId, toggle, DEPENDENCIES.get(toggle, []), dependentsOf(toggle))
        notice = f"{strings.FEATURE_EMOJIS[toggle]} **{toggleName(toggle)}** is now {'on' if newValue else 'off'}."
        if enabled:
            notice += f" Also turned on, as it needs them: {', '.join(enabled)}."
        if disabled:
            notice += f" Also turned off, as they need it: {', '.join(disabled)}."
        if newValue and toggle == 'toggle_agent':
            # public on purpose: members have to be able to see their messages can leave Discord
            await interaction.channel.send(strings.AGENT_NOTICE)
        if not newValue and toggle == 'toggle_music':
            music: Music = self.client.get_cog('Music')
            await music.disconnectAndClearQueue(str(serverId))
        return notice

    def applyToggle(self, serverId, toggle, dependencies, dependents):
        # one step, so a second press can't land between reading the switches and writing them
        newValue = not config_queries.getServerValue(serverId, toggle)
        changed = []
        # turning on turns on what it needs, and turning off turns off what needs it
        for other in (dependencies if newValue else dependents):
            if bool(config_queries.getServerValue(serverId, other)) != newValue:
                config_queries.setServerValue(serverId, other, newValue)
                changed.append(toggleName(other))
        config_queries.setServerValue(serverId, toggle, newValue)
        return (newValue, changed if newValue else [], [] if newValue else changed)

    #region REPORTS
    # Reporting is always on: it needs only the admin channel and role this cog manages, and it
    # works whether or not Who Dis is on. Right-click a message or a member, then Apps.
    @nextcord.message_command(name = strings.REPORT_MESSAGE_NAME, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    async def reportMessage(self, interaction: nextcord.Interaction, message: nextcord.Message):
        await self.askWhatHappened(interaction, message.author, message)

    @nextcord.user_command(name = strings.REPORT_MEMBER_NAME, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    async def reportMember(self, interaction: nextcord.Interaction, member: nextcord.Member):
        await self.askWhatHappened(interaction, member, None)

    async def askWhatHappened(self, interaction, target, message):
        if target.id == interaction.user.id:
            await presentation.sendError(interaction, f"Sorry {interaction.user.mention}, you can't report yourself.", feature = 'Config')
            return
        async def submit(submitted, values):
            await self.submitReport(submitted, target, message, values[0])
        form = pagination.Form(f'Report {target.display_name}', [pagination.Field('What happened? (optional)', placeholder = 'Anything the admins should know', long = True, required = False, maxLength = 1000)], submit)
        await interaction.response.send_modal(form)

    async def submitReport(self, interaction, target, message, what):
        # private, or the channel learns that someone reported someone
        await interaction.response.defer(ephemeral = True)
        captured = await self.captureMessages(interaction.channel, target, message)
        if await self.fileReport(interaction.guild, interaction.user, target, interaction.channel.mention, captured, what):
            await presentation.sendReply(interaction, content = '🚩 Sent to the admins. Thanks for letting them know.', ephemeral = True)
        else:
            await presentation.sendError(interaction, "This report wasn't sent, as this server has no admin channel GBot can post in. An admin can set one in `/config`.", feature = 'Config')

    async def captureMessages(self, channel, target, message):
        # the message reported, if one was, then the target's latest before it in the same channel
        captured = [message] if message is not None else []
        try:
            async for earlier in channel.history(limit = self.MAX_HISTORY_TO_SEARCH, before = message):
                if len(captured) >= self.NUM_MESSAGES_TO_REPORT:
                    break
                if earlier.author.id == target.id:
                    captured.append(earlier)
        except nextcord.HTTPException as e:
            self.logger.error(f'GBot could not read channel {channel.id} for a report: {e}')
        return sorted(captured, key = lambda captured: captured.created_at)

    async def fileReport(self, guild, reporter, target, where, messages, what):
        # Posts the report card in the admin channel and keeps the report for its member's history.
        # Who Dis files its games' reports here too. False if there was nowhere to post it.
        channelId = await GBotFirebaseService.run(config_queries.getServerValue, guild.id, 'channel_admin')
        channel = guild.get_channel(int(channelId)) if channelId else None
        if channel is None:
            return False
        report = {'targetId': str(target.id), 'reporterId': str(reporter.id), 'where': where, 'when': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'what': what}
        reportId, recent = await GBotFirebaseService.run(self.storeReport, guild.id, report)
        description = f'**Reported:** {target.mention}\n**By:** {reporter.mention} in {where}'
        if what:
            description += f'\n**What happened:** {what}'
        embed = presentation.warningEmbed(title = f'🚩 Report: {target.display_name}', description = description, feature = 'Config')
        embed.add_field(name = 'Captured messages', value = capturedText(messages), inline = False)
        embed.add_field(name = 'History', value = f'{presentation.ordinal(recent)} report on {target.mention} in the last {self.RECENT_REPORT_DAYS} days.', inline = False)
        view = self.reportButtons(reportId, target.id)
        try:
            await channel.send(embed = embed, view = view)
        except nextcord.HTTPException as e:
            self.logger.error(f'GBot could not post a report in the admin channel of guild {guild.id}: {e}')
            await GBotFirebaseService.run(GBotFirebaseService.remove, ['reports', guild.id, reportId])
            return False
        finally:
            pagination.stopped(view)
        return True

    def storeReport(self, serverId, report):
        reportId = config_queries.addReport(serverId, report)
        since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days = self.RECENT_REPORT_DAYS)
        # one an admin said was not an issue doesn't count against them, though History still lists it
        recent = sum(1 for earlier in config_queries.getReportsOn(serverId, report['targetId']) if datetime.datetime.fromisoformat(earlier['when']) >= since and earlier.get('outcome') != REPORT_DISMISSED)
        return reportId, recent

    def reportButtons(self, reportId, targetId, decided = False):
        # their ids say which report and member they are for, so they keep working after a restart
        buttons = []
        if not decided:
            buttons.append(pagination.persistentButton('Handled', '✅', nextcord.ButtonStyle.success, f'{REPORT_BUTTON_PREFIX}{REPORT_HANDLED}:{reportId}:{targetId}'))
            buttons.append(pagination.persistentButton('Not an issue', '🚫', nextcord.ButtonStyle.secondary, f'{REPORT_BUTTON_PREFIX}{REPORT_DISMISSED}:{reportId}:{targetId}'))
        buttons.append(pagination.persistentButton('History', '📋', nextcord.ButtonStyle.primary, f'{REPORT_BUTTON_PREFIX}{REPORT_HISTORY}:{targetId}'))
        return pagination.persistentView(buttons)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: nextcord.Interaction):
        parts = pagination.persistentParts(interaction, REPORT_BUTTON_PREFIX)
        if parts is None:
            return
        try:
            if parts[0] == REPORT_HISTORY:
                await self.showReportHistory(interaction, int(parts[1]))
            elif parts[0] in (REPORT_HANDLED, REPORT_DISMISSED):
                await self.decideReport(interaction, parts[0], parts[1], parts[2])
        except Exception as e:
            await presentation.sendInteractionError(interaction, e)

    async def showReportHistory(self, interaction, targetId):
        await interaction.response.defer(ephemeral = True)
        await predicates.recheck(interaction, admin = True)
        reports = await GBotFirebaseService.run(config_queries.getReportsOn, interaction.guild.id, targetId)
        member = interaction.guild.get_member(targetId)
        name = member.display_name if member is not None else 'a former member'
        source = pagination.DescriptionPageSource([describeReport(report) + '\n' for report in reports], f'🚩 Reports on {name} · {len(reports)}', presentation.BRAND_COLOR, None, ConfigCard.REPORTS_PER_PAGE, empty = 'No reports.')
        await pagination.startPages(interaction, pagination.CustomButtonMenuPages(source), ephemeral = True)

    async def decideReport(self, interaction, outcome, reportId, targetId):
        await interaction.response.defer()
        await predicates.recheck(interaction, admin = True)
        await GBotFirebaseService.run(config_queries.setReportOutcome, interaction.guild.id, reportId, outcome, str(interaction.user.id))
        embed = interaction.message.embeds[0]
        text = f'✅ Handled by {interaction.user.mention}' if outcome == REPORT_HANDLED else f'🚫 Not an issue, said {interaction.user.mention}'
        embed.add_field(name = 'Outcome', value = text, inline = False)
        if outcome == REPORT_HANDLED:
            embed.color = presentation.BRAND_COLOR
        view = self.reportButtons(reportId, targetId, decided = True)
        try:
            await interaction.message.edit(embed = embed, view = view)
        finally:
            pagination.stopped(view)
    #endregion

def setup(client: commands.Bot):
    client.add_cog(Config(client))
