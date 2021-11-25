#region IMPORTS
import logging
import discord
from discord.ext import commands

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
    @commands.command()
    @predicates.isMessageAuthorAdmin()
    @predicates.isMessageSentInGuild()
    async def config(self, ctx):
        serverConfig = config.queries.getAllServerValues(ctx.guild.id)
        embed = discord.Embed(color = discord.Color.blue(), title = 'GBot Configuration')
        embed.set_thumbnail(url = ctx.guild.icon_url)
        embed.add_field(name = 'Halo Functionality', value = f"`{serverConfig['toggle_halo']}`", inline = True)
        embed.add_field(name = '\u200B', value = '\u200B')
        embed.add_field(name = 'Halo Channel', value = utils.idToChannelStr(serverConfig['channel_halo']), inline = True)
        embed.add_field(name = 'Admin Role', value = utils.idToRoleStr(serverConfig['role_admin']), inline = True)
        embed.add_field(name = '\u200B', value = '\u200B')
        embed.add_field(name = 'Admin Channel', value = utils.idToChannelStr(serverConfig['channel_admin']), inline = True)
        embed.add_field(name = 'Prefix', value = f"`{serverConfig['prefix']}`", inline = False)
        await ctx.send(embed = embed)

    @commands.command()
    @predicates.isMessageAuthorAdmin()
    @predicates.isMessageSentInGuild()
    async def prefix(self, ctx, prefix):
        config.queries.setServerValue(ctx.guild.id, 'prefix', prefix)
        await ctx.send(f'Prefix set to: {prefix}')

    @commands.command()
    @predicates.isMessageAuthorAdmin()
    @predicates.isMessageSentInGuild()
    async def role(self, ctx, roleType, role: discord.Role):
        if roleType == 'admin':
            dbRole = 'role_admin'
            msgRole = 'Admin'
        config.queries.setServerValue(ctx.guild.id, dbRole, role.id)
        await ctx.send(f'{msgRole} role set to: {role.mention}')

    @commands.command()
    @predicates.isMessageAuthorAdmin()
    @predicates.isMessageSentInGuild()
    async def channel(self, ctx, channelType, channel: discord.TextChannel):
        if channelType == 'admin':
            dbChannel = 'channel_admin'
            msgChannel = 'Admin'
        if channelType == 'halo':
            dbChannel = 'channel_halo'
            msgChannel = 'Halo'
        config.queries.setServerValue(ctx.guild.id, dbChannel, channel.id)
        await ctx.send(f'{msgChannel} channel set to: {channel.mention}')

    @commands.command()
    @predicates.isMessageAuthorAdmin()
    @predicates.isMessageSentInGuild()
    async def toggle(self, ctx, switchType):
        if switchType == 'halo':
            dbSwitch = 'toggle_halo'
            msgSwitch = 'Halo'
        currentSwitchValue = config.queries.getServerValue(ctx.guild.id, dbSwitch)
        newSwitchValue = not currentSwitchValue
        config.queries.setServerValue(ctx.guild.id, dbSwitch, newSwitchValue)
        if newSwitchValue:
            await ctx.send(f'All {msgSwitch} functionality has been enabled.')
        else:
            await ctx.send(f'All {msgSwitch} functionality has been disabled.')

def setup(client):
    client.add_cog(Config(client))