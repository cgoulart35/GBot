#region IMPORTS
import logging
import nextcord
from nextcord.abc import GuildChannel
from nextcord.ext import commands, tasks
from nextcord.ext.commands.errors import BadArgument
from nextcord.ext.commands.context import Context

from GBotDiscord.src import strings
from GBotDiscord.src import pagination
from GBotDiscord.src import predicates
from GBotDiscord.src import utils
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.music.music_cog import Music
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

class Config(commands.Cog):

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()
        self.presence_index = 0
        self.presence_activities = []

    #Events
    @commands.Cog.listener()
    async def on_guild_join(self, guild: nextcord.Guild):
        self.logger.info(f'GBot was added to guild {guild.id} ({guild.name}).')
        config_queries.initServerValues(guild.id, GBotPropertiesManager.GBOT_VERSION)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: nextcord.Guild):
        self.logger.info(f'GBot was removed from guild {guild.id} ({guild.name}).')
        config_queries.clearServerValues(guild.id)

    @commands.Cog.listener()
    async def on_ready(self):
        currentBotVersion = GBotPropertiesManager.GBOT_VERSION
        servers = utils.filterGuildsForInstance(self.client, config_queries.getAllServers())
        for serverId, serverValues in servers.items():
            serverDatabaseVersion = serverValues['version']
            if float(serverDatabaseVersion) < float(currentBotVersion):
                self.logger.info(f"Upgrading server {serverId} database version from {serverDatabaseVersion} to {currentBotVersion}.")
                config_queries.upgradeServerValues(serverId, currentBotVersion)
        self.presence_activities.append(nextcord.Game(f'GBot {GBotPropertiesManager.GBOT_VERSION}'))
        self.presence_activities.append(nextcord.Activity(type = nextcord.ActivityType.listening, name = "slash commands"))
        self.presence_activities.append(nextcord.Activity(type = nextcord.ActivityType.watching, name = "user messages"))
        try:
            self.loop_presence.start()
        except RuntimeError:
            self.logger.info('loop_presence task is already launched and is not completed.')

    # Tasks
    @tasks.loop(seconds=20)
    async def loop_presence(self):
        try:
            await self.client.change_presence(status = nextcord.Status.online, activity = self.presence_activities[self.presence_index])
            self.presence_index += 1
            if self.presence_index > len(self.presence_activities) - 1: self.presence_index = 0
        except Exception as e:
            self.logger.error(f'Error in Config.loop_presence(): {e}')

    # Commands
    @nextcord.slash_command(name = strings.CONFIG_NAME, description = strings.ROLE_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isMessageAuthorAdmin(True)
    async def configSlash(self, interaction: nextcord.Interaction):
        await self.commonConfig(interaction)

    @commands.command(aliases = strings.CONFIG_ALIASES, brief = "- " + strings.CONFIG_BRIEF, description = strings.CONFIG_DESCRIPTION)
    @predicates.isMessageAuthorAdmin()
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def config(self, ctx: Context):
        await self.commonConfig(ctx)

    async def commonConfig(self, context):
        serverConfig = config_queries.getAllServerValues(context.guild.id)
        prefix = serverConfig['prefix']
        # DISCONTINUED toggleHalo = serverConfig['toggle_halo']
        toggleMusic = serverConfig['toggle_music']
        toggleGCoin = serverConfig['toggle_gcoin']
        toggleGTrade = serverConfig['toggle_gtrade']
        toggleHype = serverConfig['toggle_hype']
        toggleStorms = serverConfig['toggle_storms']
        toggle_legacy_prefix_commands = serverConfig['toggle_legacy_prefix_commands']

        empty = '`empty`'
        if 'role_admin' not in serverConfig:
            roleAdmin = empty
        else:
            roleAdmin = utils.idToRoleStr(serverConfig['role_admin'])
        # DISCONTINUED 
        # if 'role_halo_recent' not in serverConfig:
        #     roleHaloRecent = empty
        # else:
        #     roleHaloRecent = utils.idToRoleStr(serverConfig['role_halo_recent'])
        # if 'role_halo_most' not in serverConfig:
        #     roleHaloMost = empty
        # else:
        #     roleHaloMost = utils.idToRoleStr(serverConfig['role_halo_most'])
        if 'channel_admin' not in serverConfig:
            channelAdmin = empty
        else:
            channelAdmin = utils.idToChannelStr(serverConfig['channel_admin'])
        # DISCONTINUED 
        # if 'channel_halo_motd' not in serverConfig:
        #     channelHaloMotd = empty
        # else:
        #     channelHaloMotd = utils.idToChannelStr(serverConfig['channel_halo_motd'])
        # if 'channel_halo_competition' not in serverConfig:
        #     channelHaloCompetition = empty
        # else:
        #     channelHaloCompetition = utils.idToChannelStr(serverConfig['channel_halo_competition'])
        if 'channel_storms' not in serverConfig:
            channelStorms = empty
        else:
            channelStorms = utils.idToChannelStr(serverConfig['channel_storms'])

        fields = [
            ("\u200B", "\u200B"),
            ('Prefix', f"`{prefix}`"),
            # DISCONTINUED ("Halo Functionality", f"`{toggleHalo}`"),
            ("Music Functionality", f"`{toggleMusic}`"),
            ("GCoin Functionality", f"`{toggleGCoin}`"),
            ("GTrade Functionality", f"`{toggleGTrade}`"),
            ("Hype Functionality", f"`{toggleHype}`"),
            ("Storms Functionality", f"`{toggleStorms}`"),
            ("Legacy Prefix Commands", f"`{toggle_legacy_prefix_commands}`"),

            ("\u200B", "\u200B"),
            ("Admin Role", roleAdmin),
            ("Admin Channel", channelAdmin),
            # DISCONTINUED 
            # ("Halo Competition Channel", channelHaloCompetition),
            # ("Halo MOTD Channel", channelHaloMotd),
            # ("Halo Weekly Winner Role", roleHaloRecent),
            # ("Halo Most Wins Role", roleHaloMost)
            ("Storms Channel", channelStorms)
        ]
        pages = pagination.CustomButtonMenuPages(source = pagination.FieldPageSource(fields, context.guild.icon.url if context.guild.icon != None else None, "GBot Configuration", nextcord.Color.blue(), False, 8))
        await pagination.startPages(context, pages)

    @nextcord.slash_command(name = strings.PREFIX_NAME, description = strings.PREFIX_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isMessageAuthorAdmin(True)
    async def prefixSlash(self,
                          interaction: nextcord.Interaction,
                          prefix = nextcord.SlashOption(
                            name = 'prefix',
                            required = True,
                            description = strings.PREFIX_PREFIX_DESCRIPTION),
                          ):
        await self.commonPrefix(interaction, prefix)

    @commands.command(aliases = strings.PREFIX_ALIASES, brief = "- " + strings.PREFIX_BRIEF, description = strings.PREFIX_DESCRIPTION)
    @predicates.isMessageAuthorAdmin()
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def prefix(self, ctx: Context, prefix):
        await self.commonPrefix(ctx, prefix)

    async def commonPrefix(self, context, prefix):
        config_queries.setServerValue(context.guild.id, 'prefix', prefix)
        await context.send(f'Prefix set to: {prefix}')

    @nextcord.slash_command(name = strings.ROLE_NAME, description = strings.ROLE_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isMessageAuthorAdmin(True)
    async def roleSlash(self,
                        interaction: nextcord.Interaction,
                        role_type = nextcord.SlashOption(
                            name = 'role_type',
                            choices = ['admin'],
                            required = True,
                            description = strings.ROLE_TYPE_DESCRIPTION),
                        role: nextcord.Role = nextcord.SlashOption(
                            name = "role",
                            description = strings.ROLE_ROLE_DESCRIPTION)
                        ):
        await self.commonRole(interaction, role_type, role)

    @commands.command(aliases = strings.ROLE_ALIASES, brief = "- " + strings.ROLE_BRIEF, description = strings.ROLE_DESCRIPTION)
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
        # DISCONTINUED 
        # elif role_type == 'halo-recent-win':
        #     dbRole = 'role_halo_recent'
        #     msgRole = 'Halo Weekly Winner'
        # elif role_type == 'halo-most-wins':
        #     dbRole = 'role_halo_most'
        #     msgRole = 'Halo Most Wins'
        else:
            raise BadArgument(f'{role_type} is not a role_type')
        config_queries.setServerValue(context.guild.id, dbRole, str(role.id))
        await context.send(f'{msgRole} role set to: {role.mention}')

    @nextcord.slash_command(name = strings.CHANNEL_NAME, description = strings.CHANNEL_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isMessageAuthorAdmin(True)
    async def channelSlash(self,
                        interaction: nextcord.Interaction,
                        channel_type = nextcord.SlashOption(
                            name = 'channel_type',
                            choices = ['admin', 'storms'],
                            required = True,
                            description = strings.CHANNEL_TYPE_DESCRIPTION),
                        channel: GuildChannel = nextcord.SlashOption(
                            name = "channel",
                            description = strings.CHANNEL_CHANNEL_DESCRIPTION)
                        ):
        await self.commonChannel(interaction, channel_type, channel)

    @commands.command(aliases = strings.CHANNEL_ALIASES, brief = "- " + strings.CHANNEL_BRIEF, description = strings.CHANNEL_DESCRIPTION)
    @predicates.isMessageAuthorAdmin()
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def channel(self, ctx: Context, channel_type, channel: GuildChannel):
        await self.commonChannel(ctx, channel_type, channel)

    async def commonChannel(self, context, channel_type, channel: GuildChannel):
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
        config_queries.setServerValue(context.guild.id, dbChannel, str(channel.id))
        await context.send(f'{msgChannel} channel set to: {channel.mention}')

    @nextcord.slash_command(name = strings.TOGGLE_NAME, description = strings.TOGGLE_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isMessageAuthorAdmin(True)
    async def toggleSlash(self,
                        interaction: nextcord.Interaction,
                        feature_type = nextcord.SlashOption(
                            name = 'feature_type',
                            choices = ['🎵 Music', '💰 GCoin', '🏪 GTrade', '↩ Hype', '⚡ Storms', '⚙ Legacy Prefix Commands'],
                            required = True,
                            description = strings.TOGGLE_FEATURE_TYPE_DESCRIPTION)
                        ):
        await self.commonToggle(interaction, feature_type)

    @commands.command(aliases = strings.TOGGLE_ALIASES, brief = "- " + strings.TOGGLE_BRIEF, description = strings.TOGGLE_DESCRIPTION)
    @predicates.isMessageAuthorAdmin()
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def toggle(self, ctx: Context, feature_type):
        await self.commonToggle(ctx, feature_type)

    async def commonToggle(self, context, feature_type):
        dependenciesDbSwitches = []
        dependentsDbSwitches = []
        dbSwitchMsgs = {
            # DISCONTINUED 'toggle_halo': 'Halo',
            'toggle_music': 'Music',
            'toggle_gcoin': 'GCoin',
            'toggle_gtrade': 'GTrade',
            'toggle_hype': 'Hype',
            'toggle_storms': 'Storms',
            'toggle_legacy_prefix_commands': 'Legacy Prefix Command'
        }
        # DISCONTINUED 
        # if feature_type == 'halo':
        #     dbSwitch = 'toggle_halo'
        if feature_type == 'music' or feature_type == '🎵 Music':
            dbSwitch = 'toggle_music'
        elif feature_type == 'gcoin' or feature_type == '💰 GCoin':
            dbSwitch = 'toggle_gcoin'
            dependentsDbSwitches = ['toggle_gtrade', 'toggle_storms']
        elif feature_type == 'gtrade' or feature_type == '🏪 GTrade':
            dbSwitch = 'toggle_gtrade'
            dependenciesDbSwitches = ['toggle_gcoin']
        elif feature_type == 'hype' or feature_type == '↩ Hype':
            dbSwitch = 'toggle_hype'
        elif feature_type == 'storms' or feature_type == '⚡ Storms':
            dbSwitch = 'toggle_storms'
            dependenciesDbSwitches = ['toggle_gcoin']
        if feature_type == 'legacy prefix commands' or feature_type == '⚙ Legacy Prefix Commands':
            dbSwitch = 'toggle_legacy_prefix_commands'
        else:
            raise BadArgument(f'{feature_type} is not a feature_type')
        msgSwitch = dbSwitchMsgs[dbSwitch]

        serverId = context.guild.id
        currentSwitchValue = config_queries.getServerValue(serverId, dbSwitch)
        newSwitchValue = not currentSwitchValue

        # if turning on, make sure all switch's dependencies are turned on too
        msgDependencies = ''
        for dependencyDbSwitch in dependenciesDbSwitches:
            currentDependencySwitchValue = config_queries.getServerValue(serverId, dependencyDbSwitch)
            if not currentDependencySwitchValue:
                if msgDependencies == '':
                    msgDependencies = ' Dependencies enabled:'
                dependencyMsgSwitch = dbSwitchMsgs[dependencyDbSwitch]
                msgDependencies += f' {dependencyMsgSwitch}'
                config_queries.setServerValue(serverId, dependencyDbSwitch, True)

        # if turning off, make sure all switch's dependents are turned off too
        msgDependents = ''
        for dependentDbSwitch in dependentsDbSwitches:
            currentDependentSwitchValue = config_queries.getServerValue(serverId, dependentDbSwitch)
            if currentDependentSwitchValue:
                if msgDependents == '':
                    msgDependents = ' Dependents disabled:'
                dependentMsgSwitch = dbSwitchMsgs[dependentDbSwitch]
                msgDependents += f' {dependentMsgSwitch}'
                config_queries.setServerValue(serverId, dependentDbSwitch, False)

        config_queries.setServerValue(serverId, dbSwitch, newSwitchValue)
        if newSwitchValue:
            await context.send(f'All {msgSwitch} functionality has been enabled.{msgDependencies}')
        else:
            await context.send(f'All {msgSwitch} functionality has been disabled.{msgDependents}')
            if feature_type == 'music':
                music: Music = self.client.get_cog('Music')
                await music.disconnectAndClearQueue(str(serverId))

def setup(client: commands.Bot):
    client.add_cog(Config(client))