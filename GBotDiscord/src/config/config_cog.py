#region IMPORTS
import logging
import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.errors import BadArgument
from nextcord.ext.commands.context import Context

from GBotDiscord.src import presentation
from GBotDiscord.src import strings
from GBotDiscord.src import pagination
from GBotDiscord.src import predicates
from GBotDiscord.src import utils
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.music.music_cog import Music
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.firebase import GBotFirebaseService
#endregion

class Config(commands.Cog):

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()

    #Events
    @commands.Cog.listener()
    async def on_guild_join(self, guild: nextcord.Guild):
        self.logger.info(f'GBot was added to guild {guild.id} ({guild.name}).')
        await GBotFirebaseService.run(config_queries.initServerValues, guild.id, GBotPropertiesManager.GBOT_VERSION)
        await presentation.sendWelcome(guild)

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
        servers = utils.filterGuildsForInstance(self.client, allServers)
        for serverId, serverValues in servers.items():
            serverDatabaseVersion = serverValues['version']
            if float(serverDatabaseVersion) < float(currentBotVersion):
                self.logger.info(f"Upgrading server {serverId} database version from {serverDatabaseVersion} to {currentBotVersion}.")
                config_queries.upgradeServerValues(serverId, currentBotVersion)

    # Commands
    # The two group roots. Discord never invokes a slash command that has subcommands, so the slash
    # root's body is unreachable in production — nextcord just needs a callback to hang the group on.
    @nextcord.slash_command(name = strings.CONFIG_GROUP_NAME, description = strings.CONFIG_GROUP_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    async def configSlashGroup(self, interaction: nextcord.Interaction):
        pass

    @commands.group(name = strings.CONFIG_GROUP_NAME, aliases = strings.CONFIG_GROUP_ALIASES, brief = "- " + strings.CONFIG_GROUP_BRIEF, description = strings.CONFIG_GROUP_DESCRIPTION, invoke_without_command = True)
    # invoke_without_command means these run ONLY for a bare ".config" — when a subcommand
    # matches, nextcord dispatches straight to it and the root's checks never fire. So this
    # is the group's own gate, not a second one on every leaf: it mirrors exactly the checks
    # every leaf here shares, or a bare root would be an ungated way into a gated cog.
    @predicates.isMessageAuthorAdmin()
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def configGroup(self, ctx: Context):
        # a bare ".config" names no subcommand; list what lives under the group instead of doing nothing
        await ctx.send_help(ctx.command)

    @configSlashGroup.subcommand(name = strings.CONFIG_SHOW_NAME, description = strings.CONFIG_SHOW_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isMessageAuthorAdmin(True)
    async def showSlash(self, interaction: nextcord.Interaction):
        await self.commonConfig(interaction)

    @configGroup.command(name = strings.CONFIG_SHOW_NAME, aliases = strings.CONFIG_SHOW_ALIASES, brief = "- " + strings.CONFIG_SHOW_BRIEF, description = strings.CONFIG_SHOW_DESCRIPTION)
    @predicates.isMessageAuthorAdmin()
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def show(self, ctx: Context):
        await self.commonConfig(ctx)

    async def commonConfig(self, context):
        serverConfig = await GBotFirebaseService.run(config_queries.getAllServerValues, context.guild.id)
        notSet = 'Not set'
        roleOrNotSet = lambda key: utils.idToRoleStr(serverConfig[key]) if key in serverConfig else notSet
        channelOrNotSet = lambda key: utils.idToChannelStr(serverConfig[key]) if key in serverConfig else notSet
        # DISCONTINUED toggle_halo, role_halo_recent, role_halo_most, channel_halo_motd, channel_halo_competition

        lines = []
        for toggle, emoji in strings.FEATURE_EMOJIS.items():
            name = 'Prefix commands' if toggle == 'toggle_legacy_prefix_commands' else strings.FEATURE_NAMES[toggle]
            lines.append(f"{'✅' if serverConfig[toggle] else '❌'} {emoji} {name}")
        # two inline fields keep the columns lined up, which spacing inside one field can't
        middle = (len(lines) + 1) // 2

        embed = presentation.brandEmbed(title = '⚙️ GBot Configuration', description = 'Change these with `/config toggle`, `/config channel`, `/config role` and `/config prefix`.', feature = 'Config')
        embed.add_field(name = 'Features', value = '\n'.join(lines[:middle]), inline = True)
        embed.add_field(name = '\u200B', value = '\n'.join(lines[middle:]), inline = True)
        embed.add_field(name = 'Channels', value = f"Storms: {channelOrNotSet('channel_storms')}\nAdmin: {channelOrNotSet('channel_admin')}", inline = False)
        embed.add_field(name = 'Roles', value = f"Admin: {roleOrNotSet('role_admin')}\nWho Dis: {roleOrNotSet('role_who_dis')}", inline = False)
        embed.add_field(name = 'Prefix', value = f"`{serverConfig['prefix']}`", inline = False)
        if context.guild.icon != None:
            embed.set_thumbnail(url = context.guild.icon.url)
        await presentation.sendReply(context, embed = embed)

    @configSlashGroup.subcommand(name = strings.CONFIG_PREFIX_NAME, description = strings.CONFIG_PREFIX_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isMessageAuthorAdmin(True)
    async def prefixSlash(self,
                          interaction: nextcord.Interaction,
                          prefix = nextcord.SlashOption(
                            name = 'prefix',
                            required = True,
                            description = strings.CONFIG_PREFIX_PREFIX_DESCRIPTION),
                          ):
        await self.commonPrefix(interaction, prefix)

    @configGroup.command(name = strings.CONFIG_PREFIX_NAME, aliases = strings.CONFIG_PREFIX_ALIASES, brief = "- " + strings.CONFIG_PREFIX_BRIEF, description = strings.CONFIG_PREFIX_DESCRIPTION)
    @predicates.isMessageAuthorAdmin()
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def prefix(self, ctx: Context, prefix):
        await self.commonPrefix(ctx, prefix)

    async def commonPrefix(self, context, prefix):
        await GBotFirebaseService.run(config_queries.setServerValue, context.guild.id, 'prefix', prefix)
        await context.send(f'⚙️ Prefix set to: {prefix}')

    @configSlashGroup.subcommand(name = strings.CONFIG_ROLE_NAME, description = strings.CONFIG_ROLE_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isMessageAuthorAdmin(True)
    async def roleSlash(self,
                        interaction: nextcord.Interaction,
                        role_type = nextcord.SlashOption(
                            name = 'role_type',
                            choices = ['admin', 'who dis'],
                            required = True,
                            description = strings.CONFIG_ROLE_TYPE_DESCRIPTION),
                        role: nextcord.Role = nextcord.SlashOption(
                            name = "role",
                            description = strings.CONFIG_ROLE_ROLE_DESCRIPTION)
                        ):
        await self.commonRole(interaction, role_type, role)

    @configGroup.command(name = strings.CONFIG_ROLE_NAME, aliases = strings.CONFIG_ROLE_ALIASES, brief = "- " + strings.CONFIG_ROLE_BRIEF, description = strings.CONFIG_ROLE_DESCRIPTION)
    @predicates.isMessageAuthorAdmin()
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def role(self, ctx: Context, role_type, role: nextcord.Role):
        await self.commonRole(ctx, role_type, role)

    async def commonRole(self, context, role_type, role: nextcord.Role):
        if role_type == 'admin':
            dbRole = 'role_admin'
            msgRole = 'Admin'
        elif role_type == 'whoDis' or role_type == 'whodis' or role_type == 'who dis':
            dbRole = 'role_who_dis'
            msgRole = 'Who Dis'
        # DISCONTINUED 
        # elif role_type == 'halo-recent-win':
        #     dbRole = 'role_halo_recent'
        #     msgRole = 'Halo Weekly Winner'
        # elif role_type == 'halo-most-wins':
        #     dbRole = 'role_halo_most'
        #     msgRole = 'Halo Most Wins'
        else:
            raise BadArgument(f'{role_type} is not a role_type')
        await GBotFirebaseService.run(config_queries.setServerValue, context.guild.id, dbRole, str(role.id))
        await context.send(f'⚙️ {msgRole} role set to: {role.mention}')

    @configSlashGroup.subcommand(name = strings.CONFIG_CHANNEL_NAME, description = strings.CONFIG_CHANNEL_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isMessageAuthorAdmin(True)
    async def channelSlash(self,
                        interaction: nextcord.Interaction,
                        channel_type = nextcord.SlashOption(
                            name = 'channel_type',
                            choices = ['admin', 'storms'],
                            required = True,
                            description = strings.CONFIG_CHANNEL_TYPE_DESCRIPTION),
                        channel: nextcord.TextChannel = nextcord.SlashOption(
                            name = "channel",
                            channel_types = [nextcord.ChannelType.text],
                            description = strings.CONFIG_CHANNEL_CHANNEL_DESCRIPTION)
                        ):
        await self.commonChannel(interaction, channel_type, channel)

    @configGroup.command(name = strings.CONFIG_CHANNEL_NAME, aliases = strings.CONFIG_CHANNEL_ALIASES, brief = "- " + strings.CONFIG_CHANNEL_BRIEF, description = strings.CONFIG_CHANNEL_DESCRIPTION)
    @predicates.isMessageAuthorAdmin()
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def channel(self, ctx: Context, channel_type, channel: nextcord.TextChannel):
        await self.commonChannel(ctx, channel_type, channel)

    async def commonChannel(self, context, channel_type, channel: nextcord.TextChannel):
        if channel_type == 'admin':
            dbChannel = 'channel_admin'
            msgChannel = 'Admin'
        # DISCONTINUED 
        # elif channelType == 'halo-motd':
        #     dbChannel = 'channel_halo_motd'
        #     msgChannel = 'Halo MOTD'
        # elif channelType == 'halo-competition':
        #     dbChannel = 'channel_halo_competition'
        #     msgChannel = 'Halo Competition'
        elif channel_type == 'storms':
            dbChannel = 'channel_storms'
            msgChannel = 'Storms'
        else:
            raise BadArgument(f'{channel_type} is not a channelType')
        await GBotFirebaseService.run(config_queries.setServerValue, context.guild.id, dbChannel, str(channel.id))
        await context.send(f'⚙️ {msgChannel} channel set to: {channel.mention}')

    @configSlashGroup.subcommand(name = strings.CONFIG_TOGGLE_NAME, description = strings.CONFIG_TOGGLE_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isMessageAuthorAdmin(True)
    async def toggleSlash(self,
                        interaction: nextcord.Interaction,
                        feature_type = nextcord.SlashOption(
                            name = 'feature_type',
                            choices = ['🎵 Music', '💰 GCoin', '🏪 GTrade', '↩️ Hype', '🌧️ Storms', '❓ Who Dis', '⌨️ Legacy Prefix Commands', '🤖 Agent'],
                            required = True,
                            description = strings.CONFIG_TOGGLE_FEATURE_TYPE_DESCRIPTION)
                        ):
        await self.commonToggle(interaction, feature_type)

    @configGroup.command(name = strings.CONFIG_TOGGLE_NAME, aliases = strings.CONFIG_TOGGLE_ALIASES, brief = "- " + strings.CONFIG_TOGGLE_BRIEF, description = strings.CONFIG_TOGGLE_DESCRIPTION)
    @predicates.isMessageAuthorAdmin()
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def toggle(self, ctx: Context, feature_type):
        await self.commonToggle(ctx, feature_type)

    async def commonToggle(self, context, feature_type):
        dependenciesDbSwitches = []
        dependentsDbSwitches = []
        # DISCONTINUED 
        # if feature_type == 'halo':
        #     dbSwitch = 'toggle_halo'
        if feature_type == 'music' or feature_type == '🎵 Music':
            dbSwitch = 'toggle_music'
        elif feature_type == 'gcoin' or feature_type == '💰 GCoin':
            dbSwitch = 'toggle_gcoin'
            # every switch that declares toggle_gcoin as a dependency must be listed here
            dependentsDbSwitches = ['toggle_gtrade', 'toggle_storms', 'toggle_who_dis']
        elif feature_type == 'gtrade' or feature_type == '🏪 GTrade':
            dbSwitch = 'toggle_gtrade'
            dependenciesDbSwitches = ['toggle_gcoin']
        elif feature_type == 'hype' or feature_type == '↩️ Hype':
            dbSwitch = 'toggle_hype'
        elif feature_type == 'agent' or feature_type == '🤖 Agent':
            dbSwitch = 'toggle_agent'
        elif feature_type == 'storms' or feature_type == '🌧️ Storms':
            dbSwitch = 'toggle_storms'
            dependenciesDbSwitches = ['toggle_gcoin']
        elif feature_type == 'whoDis' or feature_type == 'whodis' or feature_type == 'who dis' or feature_type == '❓ Who Dis':
            dbSwitch = 'toggle_who_dis'
            dependenciesDbSwitches = ['toggle_gcoin']
        elif feature_type == 'legacy prefix commands' or feature_type == '⌨️ Legacy Prefix Commands':
            dbSwitch = 'toggle_legacy_prefix_commands'
        else:
            raise BadArgument(f'{feature_type} is not a feature_type')
        msgSwitch = strings.FEATURE_NAMES[dbSwitch]

        serverId = context.guild.id
        newSwitchValue, msgDependencies, msgDependents = await GBotFirebaseService.run(self.applyToggle, serverId, dbSwitch, dependenciesDbSwitches, dependentsDbSwitches)
        if newSwitchValue:
            await context.send(f'✅ All {msgSwitch} functionality has been enabled.{msgDependencies}')
            # public on purpose: members have to be able to see their messages can leave Discord
            if dbSwitch == 'toggle_agent':
                await context.send(strings.AGENT_NOTICE)
        else:
            await context.send(f'❌ All {msgSwitch} functionality has been disabled.{msgDependents}')
            # keyed off the resolved switch, not feature_type — the slash choice is '🎵 Music'
            # while the legacy prefix form is 'music', and only the latter used to match here
            if dbSwitch == 'toggle_music':
                music: Music = self.client.get_cog('Music')
                await music.disconnectAndClearQueue(str(serverId))

    def applyToggle(self, serverId, dbSwitch, dependenciesDbSwitches, dependentsDbSwitches):
        # one step, so a second toggle can't land between reading the switches and writing them
        currentSwitchValue = config_queries.getServerValue(serverId, dbSwitch)
        newSwitchValue = not currentSwitchValue

        # if turning on, make sure all switch's dependencies are turned on too
        msgDependencies = ''
        for dependencyDbSwitch in dependenciesDbSwitches:
            currentDependencySwitchValue = config_queries.getServerValue(serverId, dependencyDbSwitch)
            if not currentDependencySwitchValue:
                if msgDependencies == '':  # pragma: no branch
                    msgDependencies = ' Dependencies enabled:'
                dependencyMsgSwitch = strings.FEATURE_NAMES[dependencyDbSwitch]
                msgDependencies += f' {dependencyMsgSwitch}'
                config_queries.setServerValue(serverId, dependencyDbSwitch, True)

        # if turning off, make sure all switch's dependents are turned off too
        msgDependents = ''
        for dependentDbSwitch in dependentsDbSwitches:
            currentDependentSwitchValue = config_queries.getServerValue(serverId, dependentDbSwitch)
            if currentDependentSwitchValue:
                if msgDependents == '':
                    msgDependents = ' Dependents disabled:'
                dependentMsgSwitch = strings.FEATURE_NAMES[dependentDbSwitch]
                msgDependents += f' {dependentMsgSwitch}'
                config_queries.setServerValue(serverId, dependentDbSwitch, False)

        config_queries.setServerValue(serverId, dbSwitch, newSwitchValue)
        return (newSwitchValue, msgDependencies, msgDependents)

def setup(client: commands.Bot):
    client.add_cog(Config(client))