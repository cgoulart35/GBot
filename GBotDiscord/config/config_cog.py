#region IMPORTS
import os
import logging
import nextcord
from nextcord.abc import GuildChannel
from nextcord.ext import commands
from nextcord.ext.commands.errors import BadArgument
from nextcord.ext.commands.context import Context

from GBotDiscord import pagination
from GBotDiscord import predicates
from GBotDiscord import utils
from GBotDiscord.config import config_queries
from GBotDiscord.music.music_cog import Music
#endregion

class Config(commands.Cog):

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()
        self.VERSION = os.getenv("GBOT_VERSION")

    #Events
    @commands.Cog.listener()
    async def on_guild_join(self, guild: nextcord.Guild):
        self.logger.info(f'GBot was added to guild {guild.id} ({guild.name}).')
        config_queries.initServerValues(guild.id, self.VERSION)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: nextcord.Guild):
        self.logger.info(f'GBot was removed from guild {guild.id} ({guild.name}).')
        config_queries.clearServerValues(guild.id)

    @commands.Cog.listener()
    async def on_ready(self):
        currentBotVersion = self.VERSION
        servers = config_queries.getAllServers()
        for serverId, serverValues in servers.items():
            serverDatabaseVersion = serverValues['version']
            if float(serverDatabaseVersion) < float(currentBotVersion):
                self.logger.info(f"Upgrading server {serverId} database version from {serverDatabaseVersion} to {currentBotVersion}.")
                config_queries.upgradeServerValues(serverId, currentBotVersion)

    # Commands
    @commands.command(brief = "- Shows the server's current GBot configuration. (admin only)", description = "Shows the server's current GBot configuration. (admin only)")
    @predicates.isMessageAuthorAdmin()
    @predicates.isMessageSentInGuild()
    async def config(self, ctx: Context):
        serverConfig = config_queries.getAllServerValues(ctx.guild.id)
        prefix = serverConfig['prefix']
        toggleHalo = serverConfig['toggle_halo']
        toggleMusic = serverConfig['toggle_music']
        toggleGCoin = serverConfig['toggle_gcoin']
        toggleGTrade = serverConfig['toggle_gtrade']

        empty = '`empty`'
        if 'role_admin' not in serverConfig:
            roleAdmin = empty
        else:
            roleAdmin = utils.idToRoleStr(serverConfig['role_admin'])
        if 'role_halo_recent' not in serverConfig:
            roleHaloRecent = empty
        else:
            roleHaloRecent = utils.idToRoleStr(serverConfig['role_halo_recent'])
        if 'role_halo_most' not in serverConfig:
            roleHaloMost = empty
        else:
            roleHaloMost = utils.idToRoleStr(serverConfig['role_halo_most'])
        if 'channel_admin' not in serverConfig:
            channelAdmin = empty
        else:
            channelAdmin = utils.idToChannelStr(serverConfig['channel_admin'])
        if 'channel_halo_motd' not in serverConfig:
            channelHaloMotd = empty
        else:
            channelHaloMotd = utils.idToChannelStr(serverConfig['channel_halo_motd'])
        if 'channel_halo_competition' not in serverConfig:
            channelHaloCompetition = empty
        else:
            channelHaloCompetition = utils.idToChannelStr(serverConfig['channel_halo_competition'])

        fields = [
            ("\u200B", "\u200B"),
            ('Prefix', f"`{prefix}`"),
            ("Halo Functionality", f"`{toggleHalo}`"),
            ("Music Functionality", f"`{toggleMusic}`"),
            ("GCoin Functionality", f"`{toggleGCoin}`"),
            ("GTrade Functionality", f"`{toggleGTrade}`"),

            ("Admin Role", roleAdmin),
            ("Admin Channel", channelAdmin),
            ("Halo Competition Channel", channelHaloCompetition),
            ("Halo MOTD Channel", channelHaloMotd),
            ("Halo Weekly Winner Role", roleHaloRecent),
            ("Halo Most Wins Role", roleHaloMost),
        ]
        pages = pagination.CustomButtonMenuPages(source = pagination.FieldPageSource(fields, ctx.guild.icon.url, "GBot Configuration", nextcord.Color.blue(), False, 6))
        await pages.start(ctx)

    @commands.command(brief = "- Set the prefix for all GBot commands used in this server. (admin only)", description = "Set the prefix for all GBot commands used in this server. (admin only)")
    @predicates.isMessageAuthorAdmin()
    @predicates.isMessageSentInGuild()
    async def prefix(self, ctx: Context, prefix):
        config_queries.setServerValue(ctx.guild.id, 'prefix', prefix)
        await ctx.send(f'Prefix set to: {prefix}')

    @commands.command(brief = "- Set the role for a specific GBot feature in this server. (admin only)", description = "Set the role for a specific GBot feature in this server. (admin only)\nroleType options are: admin, halo-recent-win, halo-most-wins")
    @predicates.isMessageAuthorAdmin()
    @predicates.isMessageSentInGuild()
    async def role(self, ctx: Context, roleType, role: nextcord.Role):
        if roleType == 'admin':
            dbRole = 'role_admin'
            msgRole = 'Admin'
        elif roleType == 'halo-recent-win':
            dbRole = 'role_halo_recent'
            msgRole = 'Halo Weekly Winner'
        elif roleType == 'halo-most-wins':
            dbRole = 'role_halo_most'
            msgRole = 'Halo Most Wins'
        else:
            raise BadArgument(f'{roleType} is not a roleType')
        config_queries.setServerValue(ctx.guild.id, dbRole, str(role.id))
        await ctx.send(f'{msgRole} role set to: {role.mention}')

    @commands.command(brief = "- Set the channel for a specific GBot feature in this server. (admin only)", description = "Set the channel for a specific GBot feature in this server. (admin only)\nchannelType options are: admin, halo-motd, halo-competition")
    @predicates.isMessageAuthorAdmin()
    @predicates.isMessageSentInGuild()
    async def channel(self, ctx: Context, channelType, channel: GuildChannel):
        if channelType == 'admin':
            dbChannel = 'channel_admin'
            msgChannel = 'Admin'
        elif channelType == 'halo-motd':
            dbChannel = 'channel_halo_motd'
            msgChannel = 'Halo MOTD'
        elif channelType == 'halo-competition':
            dbChannel = 'channel_halo_competition'
            msgChannel = 'Halo Competition'
        else:
            raise BadArgument(f'{channelType} is not a channelType')
        config_queries.setServerValue(ctx.guild.id, dbChannel, str(channel.id))
        await ctx.send(f'{msgChannel} channel set to: {channel.mention}')

    @commands.command(brief = "- Turn on/off all functionality for a GBot feature in this server. (admin only)", description = "Turn on/off all functionality for a GBot feature in this server. (admin only)\nfeatureType options are: gcoin, gtrade, halo, music")
    @predicates.isMessageAuthorAdmin()
    @predicates.isMessageSentInGuild()
    async def toggle(self, ctx: Context, featureType):
        dependenciesDbSwitches = []
        dependentsDbSwitches = []
        dbSwitchMsgs = {
            'toggle_halo': 'Halo',
            'toggle_music': 'Music',
            'toggle_gcoin': 'GCoin',
            'toggle_gtrade': 'GTrade'
        }
        if featureType == 'halo':
            dbSwitch = 'toggle_halo'
        elif featureType == 'music':
            dbSwitch = 'toggle_music'
        elif featureType == 'gcoin':
            dbSwitch = 'toggle_gcoin'
            dependentsDbSwitches = ['toggle_gtrade']
        elif featureType == 'gtrade':
            dbSwitch = 'toggle_gtrade'
            dependenciesDbSwitches = ['toggle_gcoin']
        else:
            raise BadArgument(f'{featureType} is not a featureType')
        msgSwitch = dbSwitchMsgs[dbSwitch]

        serverId = ctx.guild.id
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
            await ctx.send(f'All {msgSwitch} functionality has been enabled.{msgDependencies}')
        else:
            await ctx.send(f'All {msgSwitch} functionality has been disabled.{msgDependents}')
            if featureType == 'music':
                music: Music = self.client.get_cog('Music')
                await music.disconnectAndClearQueue(str(serverId))

def setup(client: commands.Bot):
    client.add_cog(Config(client))