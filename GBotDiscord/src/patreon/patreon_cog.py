#region IMPORTS
import logging
import nextcord
from nextcord.ext import commands, tasks
from nextcord.ext.commands.context import Context

from GBotDiscord.src import access
from GBotDiscord.src import presentation
from GBotDiscord.src import strings
from GBotDiscord.src import utils
from GBotDiscord.src import predicates
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.patreon import patreon_queries
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.firebase import GBotFirebaseService
#endregion

class Patreon(commands.Cog):

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()

    def getAllGuilds(self):
        return self.client.guilds

    # Events
    @commands.Cog.listener()
    async def on_ready(self):
        try:
            self.patreon_validation.start()
        except RuntimeError:
            self.logger.info('patreon_validation task is already launched and is not completed.')
        try:
            self.trial_reminders.start()
        except RuntimeError:
            self.logger.info('trial_reminders task is already launched and is not completed.')

    # Tasks
    @tasks.loop(hours=24)
    async def patreon_validation(self):
        try:
            # read live rather than snapshotting in __init__, so setProperty on
            # PATREON_IGNORE_GUILDS takes effect without a restart (predicates.py reads it live too)
            guildsToIgnore = utils.getGuildsForPatreonToIgnore()

            # every 24 hours, check if all patreon members still have the patron role
            allPatronMembers = await GBotFirebaseService.run(patreon_queries.getAllPatrons)
            if allPatronMembers != None:
                patreonGuild = await self.client.fetch_guild(GBotPropertiesManager.PATREON_GUILD_ID)
                for userId, values in allPatronMembers.items():
                    serverId = int(values['serverId'])
                    if serverId in guildsToIgnore:
                        # skip this patron only; `break` here would abandon every remaining entry
                        continue
                    try:
                        user = await patreonGuild.fetch_member(int(userId))
                        isPatron = utils.isUserAssignedRole(user, GBotPropertiesManager.PATRON_ROLE_ID)
                    except nextcord.NotFound:
                        # left the Patreon server, so cannot hold the role. This used to abort the
                        # whole run. Any other failure still does, deliberately: the guild leaving
                        # below must never act on a check that did not complete.
                        isPatron = False
                    await self.checkPatron(userId, values, isPatron)

            # tell each server whose subscription lapsed, once, by whichever bot is in it
            allPatronMembers = await GBotFirebaseService.run(patreon_queries.getAllPatrons) or {}
            subscribedServerIds = access.subscribedServerIds(allPatronMembers)
            lapsedServerIds = access.lapsedServerIds(allPatronMembers)
            guilds = {guild.id: guild for guild in self.getAllGuilds()}
            for userId, values in allPatronMembers.items():
                serverId = int(values['serverId'])
                if 'lapsed' in values and not values.get('lapseNotified') and serverId in guilds and serverId not in subscribedServerIds:
                    await self.sendNotice(guilds[serverId], access.lapseText(serverId, values))
                    await GBotFirebaseService.run(patreon_queries.setPatronLapseNotified, userId)

            # leave any server that isn't subscribed, ignored, on a trial or in its grace days
            trials = await GBotFirebaseService.run(patreon_queries.getAllTrials) or {}
            for guild in guilds.values():
                if access.state(guild.id, guildsToIgnore, subscribedServerIds, trials.get(str(guild.id)), lapsed = lapsedServerIds) in access.LEAVES:
                    try:
                        await guild.leave()
                        self.logger.info(f'GBot Patreon has left unsubscribed server {guild.id}.')
                    except Exception as e:
                        self.logger.error(f'GBot Patreon failed to leave unsubscribed server {guild.id}: {e}')
        except Exception as e:
            self.logger.error(f'Error in Patreon.patreon_validation(): {e}')

    async def checkPatron(self, userId, values, isPatron):
        # Someone who lost the role is marked lapsed rather than dropped, so their server gets the grace
        # days a trial does. Getting it back in that time clears it, and nothing is lost.
        serverId = values['serverId']
        lapsed = values.get('lapsed')
        if isPatron:
            if lapsed is not None:
                await GBotFirebaseService.run(patreon_queries.addPatronEntry, userId, serverId)
                self.logger.info(f'GBot Patreon has renewed the patron entry for userId {userId}: {serverId}')
        elif lapsed is None:
            await GBotFirebaseService.run(patreon_queries.setPatronLapsed, userId, access.utcNow().isoformat())
            self.logger.info(f'GBot Patreon has marked the patron entry for userId {userId} lapsed: {serverId}')
        elif access.utcNow() >= access.lapseEnds(values):
            await GBotFirebaseService.run(patreon_queries.removePatronEntry, userId)
            self.logger.info(f'GBot Patreon has removed the patron entry for userId {userId}: {serverId}')

    # hourly, so "the last day" arrives on it. Each reminder is recorded, so a restart sends none twice.
    @tasks.loop(hours=1)
    async def trial_reminders(self):
        try:
            trials = await GBotFirebaseService.run(patreon_queries.getAllTrials) or {}
            if not trials:
                return
            guildsToIgnore = utils.getGuildsForPatreonToIgnore()
            patrons = await GBotFirebaseService.run(patreon_queries.getAllPatrons)
            subscribedServerIds = access.subscribedServerIds(patrons)
            lapsedServerIds = access.lapsedServerIds(patrons)
            for guild in self.getAllGuilds():
                trial = trials.get(str(guild.id))
                if trial is None:
                    continue
                due = access.reminderDue(trial, access.state(guild.id, guildsToIgnore, subscribedServerIds, trial, lapsed = lapsedServerIds))
                if due is None:
                    continue
                await self.sendNotice(guild, access.reminderText(guild.id, trial, due))
                # recorded even when there was nowhere to post, so it isn't retried every hour
                await GBotFirebaseService.run(patreon_queries.setTrialReminded, guild.id, due)
        except Exception as e:
            self.logger.error(f'Error in Patreon.trial_reminders(): {e}')

    async def sendNotice(self, guild: nextcord.Guild, text):
        # about a trial or a lapsed subscription: the admin channel, or where the welcome message went
        channelId = await GBotFirebaseService.run(config_queries.getServerValue, guild.id, 'channel_admin')
        channel = guild.get_channel(int(channelId)) if channelId is not None else None
        if channel is None:
            channel = presentation.postableChannel(guild)
        if channel is None:
            self.logger.info(f'GBot had nowhere to post a notice in server {guild.id}.')
            return
        try:
            await channel.send(text, view = presentation.subscribeView())
            self.logger.info(f'GBot sent a notice in server {guild.id}.')
        except Exception as e:
            self.logger.error(f'GBot could not send a notice in server {guild.id}: {e}')

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
        await GBotFirebaseService.run(patreon_queries.addPatronEntry, authorId, server_id)
        await context.send('⭐ GBot is now accessible in the specified server. Thank you for subscribing and enjoy!')

def setup(client: commands.Bot):
    client.add_cog(Patreon(client))