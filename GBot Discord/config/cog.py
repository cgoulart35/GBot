#region IMPORTS
import logging
import discord
from discord.ext import commands

import predicates
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
        embed.add_field(name = 'Prefix', value = f"`{serverConfig['prefix']}`", inline = False)
        await ctx.send(embed = embed)

    @commands.command()
    @predicates.isMessageAuthorAdmin()
    @predicates.isMessageSentInGuild()
    async def prefix(self, ctx, prefix):
        config.queries.setServerValue(ctx.guild.id, 'prefix', prefix)
        await ctx.send(f'Prefix updated to: {prefix}')

def setup(client):
    client.add_cog(Config(client))