#region IMPORTS
import logging
import nextcord
from nextcord.ext import commands, tasks
from nextcord.ext.commands.context import Context

from GBotDiscord.src import utils
from GBotDiscord.src import predicates
from GBotDiscord.src.patreon import patreon_queries
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

class Patreon(commands.Cog):

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()
        self.PATREON_GUILD_ID = GBotPropertiesManager.PATREON_GUILD_ID
        self.PATRON_ROLE_ID = GBotPropertiesManager.PATRON_ROLE_ID

        self.guildsToIgnore = utils.getGuildsForPatreonToIgnore()

    # Events
    @commands.Cog.listener()
    async def on_ready(self):
        try:
            self.patreon_validation.start()
        except RuntimeError:
            self.logger.info('patreon_validation task is already launched and is not completed.')

    # Tasks
    @tasks.loop(hours=24)
    async def patreon_validation(self):
        # every 24 hours, check if all patreon members still have the patron role
        allPatronMembers = patreon_queries.getAllPatrons()
        if allPatronMembers != None:
            patreonGuild = await self.client.fetch_guild(self.PATREON_GUILD_ID)
            for userId, values in allPatronMembers.items():
                serverId = int(values['serverId'])
                if serverId in self.guildsToIgnore:
                    break
                user = await patreonGuild.fetch_member(int(userId))

                # if member does not have the role, remove the entry
                if not utils.isUserAssignedRole(user, self.PATRON_ROLE_ID):
                    patreon_queries.removePatronEntry(userId)
                    self.logger.info(f'GBot Patreon has removed the patron entry for userId {userId}: {serverId}')
        
        # remove any out of sync servers that are not being tracked
        allPatronMembers = patreon_queries.getAllPatrons()
        subscribedServerIds = []
        if allPatronMembers != None:
            for server in allPatronMembers.values(): 
                subscribedServerIds.append(int(server['serverId']))
        for guild in self.client.guilds:
            if guild.id not in self.guildsToIgnore and guild.id not in subscribedServerIds:
                try:
                    await guild.leave()
                    self.logger.info(f'GBot Patreon has left unsubscribed server {guild.id}.')
                except:
                    self.logger.error(f'GBot Patreon failed to leave unsubscribed server {guild.id}.')

    # Commands
    @commands.command(aliases=['pt'], brief = "- In the GBot Patreon server, specify a server's ID to enable GBot functionality in that server. (patrons only)", description = "In the GBot Patreon server, specify a server's ID to enable GBot functionality in that server. (patrons only)")
    @predicates.isAuthorAPatronInGBotPatreonServer()
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def patreon(self, ctx: Context, serverId):
        # add serverId to the patreon member table with specified server (override if already set)
        patreon_queries.addPatronEntry(ctx.author.id, serverId)
        await ctx.send(f'GBot is now accessible in the specified server. Thank you for subscribing and enjoy!')

def setup(client: commands.Bot):
    client.add_cog(Patreon(client))