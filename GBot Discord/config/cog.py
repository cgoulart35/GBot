#region IMPORTS
import logging
import discord
from discord.ext import commands
from discord.ext.commands.errors import BadArgument

import predicates
import utils
import config.queries
from properties import botConfig
#endregion

class Config(commands.Cog):

    def __init__(self, client):
        self.client = client
        self.logger = logging.getLogger()

    #Events
    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        self.logger.info(f'GBot was added to guild {guild.id} ({guild.name}).')
        config.queries.initServerValues(guild.id, botConfig['properties']['version'])

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        self.logger.info(f'GBot was removed from guild {guild.id} ({guild.name}).')
        config.queries.clearServerValues(guild.id)

    @commands.Cog.listener()
    async def on_ready(self):
        currentBotVersion = botConfig['properties']['version']
        servers = config.queries.getAllServers()
        for serverId, serverValues in servers.items():
            serverDatabaseVersion = serverValues['version']
            if serverDatabaseVersion < currentBotVersion:
                self.logger.info(f"Upgrading server {serverId} database version from {serverDatabaseVersion} to {currentBotVersion}.")
                config.queries.upgradeServerValues(serverId, currentBotVersion)

    # Commands
    @commands.command(brief = "- Shows the server's current GBot configuration. (admin only)", description = "Shows the server's current GBot configuration. (admin only)")
    @predicates.isMessageAuthorAdmin()
    @predicates.isMessageSentInGuild()
    async def config(self, ctx):
        serverConfig = config.queries.getAllServerValues(ctx.guild.id)
        prefix = serverConfig['prefix']
        toggleHalo = serverConfig['toggle_halo']

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

        embed = discord.Embed(color = discord.Color.blue(), title = 'GBot Configuration')
        embed.set_thumbnail(url = ctx.guild.icon_url)

        embed.add_field(name = 'Prefix', value = f"`{prefix}`", inline = False)

        embed.add_field(name = 'Admin Role', value = roleAdmin, inline = True)
        embed.add_field(name = '\u200B', value = '\u200B')
        embed.add_field(name = 'Admin Channel', value = channelAdmin, inline = True)

        embed.add_field(name = '\u200B', value = '\u200B')
        embed.add_field(name = '\u200B', value = '\u200B')
        embed.add_field(name = '\u200B', value = '\u200B')

        embed.add_field(name = 'Halo Functionality', value = f"`{toggleHalo}`", inline = False)

        embed.add_field(name = 'Halo MOTD Channel', value = channelHaloMotd, inline = True)
        embed.add_field(name = '\u200B', value = '\u200B')
        embed.add_field(name = 'Halo Competition Channel', value = channelHaloCompetition, inline = True)

        embed.add_field(name = 'Halo Weekly Winner Role', value = roleHaloRecent, inline = True)
        embed.add_field(name = '\u200B', value = '\u200B')
        embed.add_field(name = 'Halo Most Wins Role', value = roleHaloMost, inline = True)
        
        await ctx.send(embed = embed)

    @commands.command(brief = "- Set the prefix for all GBot commands used in this server. (admin only)", description = "Set the prefix for all GBot commands used in this server. (admin only)")
    @predicates.isMessageAuthorAdmin()
    @predicates.isMessageSentInGuild()
    async def prefix(self, ctx, prefix):
        config.queries.setServerValue(ctx.guild.id, 'prefix', prefix)
        await ctx.send(f'Prefix set to: {prefix}')

    @commands.command(brief = "- Set the admin role for GBot in this server. (admin only)", description = "Set the admin role for GBot in this server. (admin only)\nroleType options are: admin, halo-recent-win, halo-most-wins")
    @predicates.isMessageAuthorAdmin()
    @predicates.isMessageSentInGuild()
    async def role(self, ctx, roleType, role: discord.Role):
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
        config.queries.setServerValue(ctx.guild.id, dbRole, role.id)
        await ctx.send(f'{msgRole} role set to: {role.mention}')

    @commands.command(brief = "- Set the channel for a specific GBot feature in this server. (admin only)", description = "Set the channel for a specific GBot feature in this server. (admin only)\nchannelType options are: admin, halo-motd, halo-competition")
    @predicates.isMessageAuthorAdmin()
    @predicates.isMessageSentInGuild()
    async def channel(self, ctx, channelType, channel: discord.TextChannel):
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
        config.queries.setServerValue(ctx.guild.id, dbChannel, channel.id)
        await ctx.send(f'{msgChannel} channel set to: {channel.mention}')

    @commands.command(brief = "- Turn on/off all functionality for a GBot feature in this server. (admin only)", description = "Turn on/off all functionality for a GBot feature in this server. (admin only)\nfeatureType options are: halo")
    @predicates.isMessageAuthorAdmin()
    @predicates.isMessageSentInGuild()
    async def toggle(self, ctx, featureType):
        if featureType == 'halo':
            dbSwitch = 'toggle_halo'
            msgSwitch = 'Halo'
        else:
            raise BadArgument(f'{featureType} is not a featureType')
        currentSwitchValue = config.queries.getServerValue(ctx.guild.id, dbSwitch)
        newSwitchValue = not currentSwitchValue
        config.queries.setServerValue(ctx.guild.id, dbSwitch, newSwitchValue)
        if newSwitchValue:
            await ctx.send(f'All {msgSwitch} functionality has been enabled.')
        else:
            await ctx.send(f'All {msgSwitch} functionality has been disabled.')

def setup(client):
    client.add_cog(Config(client))