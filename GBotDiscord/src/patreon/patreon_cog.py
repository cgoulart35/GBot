#region IMPORTS
import logging
import nextcord
from nextcord.ext import commands, tasks
from nextcord.ext.commands.context import Context

from GBotDiscord.src import strings
from GBotDiscord.src import utils
from GBotDiscord.src import predicates
from GBotDiscord.src.patreon import patreon_queries
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

class Patreon(commands.Cog):

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()

        self.guildsToIgnore = utils.getGuildsForPatreonToIgnore()

    def getAllGuilds(self):
        return self.client.guilds

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
        try:
            # every 24 hours, check if all patreon members still have the patron role
            allPatronMembers = patreon_queries.getAllPatrons()
            if allPatronMembers != None:
                patreonGuild = await self.client.fetch_guild(GBotPropertiesManager.PATREON_GUILD_ID)
                for userId, values in allPatronMembers.items():
                    serverId = int(values['serverId'])
                    if serverId in self.guildsToIgnore:
                        break
                    user = await patreonGuild.fetch_member(int(userId))

                    # if member does not have the role, remove the entry
                    if not utils.isUserAssignedRole(user, GBotPropertiesManager.PATRON_ROLE_ID):
                        patreon_queries.removePatronEntry(userId)
                        self.logger.info(f'GBot Patreon has removed the patron entry for userId {userId}: {serverId}')
            
            # remove any out of sync servers that are not being tracked
            allPatronMembers = patreon_queries.getAllPatrons()
            subscribedServerIds = []
            if allPatronMembers != None:
                for server in allPatronMembers.values(): 
                    subscribedServerIds.append(int(server['serverId']))
            for guild in self.getAllGuilds():
                if guild.id not in self.guildsToIgnore and guild.id not in subscribedServerIds:
                    try:
                        await guild.leave()
                        self.logger.info(f'GBot Patreon has left unsubscribed server {guild.id}.')
                    except:
                        self.logger.error(f'GBot Patreon failed to leave unsubscribed server {guild.id}.')
        except Exception as e:
            self.logger.error(f'Error in Patreon.patreon_validation(): {e}')

    # Commands
    @nextcord.slash_command(name = strings.PATREON_NAME, description = strings.PATREON_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isAuthorAPatronInGBotPatreonServer(True)
    async def patreonSlash(self,
                           interaction: nextcord.Interaction,
                           server_id = nextcord.SlashOption(
                               name = "server_id",
                               description = strings.PATREON_SERVER_ID_DESCRIPTION)
                           ):
        server_id = utils.idStrArgToInt(server_id, "server_id")
        await self.commonPatreon(interaction, interaction.user.id, server_id)

    @commands.command(aliases = strings.PATREON_ALIASES, brief = "- " + strings.PATREON_BRIEF, description = strings.PATREON_DESCRIPTION)
    @predicates.isAuthorAPatronInGBotPatreonServer()
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def patreon(self, ctx: Context, server_id: int):
        await self.commonPatreon(ctx, ctx.author.id, server_id)

    async def commonPatreon(self, context, authorId, server_id):
        # add server_id to the patreon member table with specified server (override if already set)
        patreon_queries.addPatronEntry(authorId, server_id)
        await context.send('GBot is now accessible in the specified server. Thank you for subscribing and enjoy!')

def setup(client: commands.Bot):
    client.add_cog(Patreon(client))