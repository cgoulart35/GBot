#region IMPORTS
import logging
import threading
import random
import nextcord
from nextcord.ext import commands, tasks
from nextcord.ext.commands.context import Context
from decimal import Decimal
from datetime import datetime, timedelta

from GBotDiscord.src import strings
from GBotDiscord.src import utils
from GBotDiscord.src import predicates
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.gcoin import gcoin_queries
from GBotDiscord.src.exceptions import WhoDisNotConfigured
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

class WhoDis(commands.Cog):

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()

        self.MAX_CHANNEL_MSG_HISTORY_LOOKUP = 250
        self.NUM_MESSAGES_TO_REPORT = 5
        self.GUESS_REWARD_GCOIN = Decimal('10.00')

        self.whoDisGames = {}
        self.whoDisLock = threading.Lock()

    # Events
    @commands.Cog.listener()
    async def on_ready(self):
        try:
            self.who_dis_timeout.start()
        except RuntimeError:
            self.logger.info('who_dis_timeout task is already launched and is not completed.')

    @commands.Cog.listener()
    async def on_message(self, msg: nextcord.Message):
        # make sure message in a private message not from a bot
        if (msg.guild == None and not msg.author.bot):
            authorId = msg.author.id
            # check to see if message author is in a who dis game
            existingGameKey = self.getWhoDisGameKey(authorId)
            if existingGameKey is not None:
                # skip over prefixed commands & don't send/save for reports
                if msg.content and (msg.content.startswith('.') or msg.content.startswith('/')):
                    return

                # determine if author is initiator or random user & forward message to paired user
                initiator: nextcord.User = self.whoDisGames[existingGameKey]['initiator']
                if initiator.id == authorId:
                    sendToUser: nextcord.User = self.whoDisGames[existingGameKey]['randomUser']
                    if len(self.whoDisGames[existingGameKey]['initiatorMessages']) >= self.NUM_MESSAGES_TO_REPORT:
                        self.whoDisGames[existingGameKey]['initiatorMessages'].pop()
                    self.whoDisGames[existingGameKey]['initiatorMessages'].append(msg)
                else:
                    sendToUser: nextcord.User = initiator
                    if len(self.whoDisGames[existingGameKey]['randomUserMessages']) >= self.NUM_MESSAGES_TO_REPORT:
                        self.whoDisGames[existingGameKey]['randomUserMessages'].pop()
                    self.whoDisGames[existingGameKey]['randomUserMessages'].append(msg)
                # send text if any
                if msg.content:
                    await sendToUser.send(msg.content)
                # send attachments if any
                if msg.attachments:
                    for attachment in msg.attachments:
                        await sendToUser.send(attachment.url)
                # send stickers if any
                if msg.stickers:
                    for sticker in msg.stickers:
                        await sendToUser.send(sticker.url)

    # Tasks
    @tasks.loop(seconds=1)
    async def who_dis_timeout(self):
        try:
            currentTime = datetime.now()
            timedOutGameKeys = []
            for gameKey, gameInfo in self.whoDisGames.items():
                startTime = datetime.strptime(gameInfo['startTime'], "%m/%d/%y %I:%M:%S %p")
                if currentTime >= startTime + timedelta(minutes = GBotPropertiesManager.WHODIS_TIMEOUT_MINUTES):
                    timedOutGameKeys.append(gameKey)
            # time out the games after identifying them so we don't modify the size of the whoDisGames dict
            for gameKey in timedOutGameKeys:
                await self.timeoutWhoDis(gameKey)
        except Exception as e:
            self.logger.error(f'Error in WhoDis.who_dis_timeout(): {e}')

    # Commands
    @nextcord.slash_command(name = strings.WHODIS_NAME, description = strings.WHODIS_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isFeatureEnabledForServer('toggle_who_dis', True, True)
    async def whoDisSlash(self, interaction: nextcord.Interaction):
        await self.commonWhoDis(interaction, interaction.user)

    @commands.command(aliases = strings.WHODIS_ALIASES, brief = "- " + strings.WHODIS_BRIEF, description = strings.WHODIS_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_who_dis', True)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', True)
    @predicates.isGuildOrUserSubscribed()
    async def whodis(self, ctx: Context):
        await self.commonWhoDis(ctx, ctx.author)

    async def commonWhoDis(self, context, author):
        try:
            if isinstance(context, nextcord.Interaction):
                await context.response.defer()

            # obtain lock for starting who dis games; only one who dis can be started at a time (ensures user pairings are unique)
            guild = context.guild
            authorId = author.id
            authorMention = author.mention
            self.whoDisLock.acquire(blocking = False)

            # check to see if sent in a private message
            isPrivateMessage = guild is None

            # check to see if user is already in a who dis game
            existingGameKey = self.getWhoDisGameKey(authorId)

            # end the existing game whether in a guild or private message
            if existingGameKey is not None:
                await self.cancelWhoDis(existingGameKey, authorId)
                await context.send('Who Dis cancelled.')
            # start a new game only if sent in a guild
            else:
                # sent in a private message; send error message need to start in guild
                if isPrivateMessage:
                    await context.send(f'Sorry {authorMention}, Who Dis games must be started in a server.')
                # sent in a guild; start a new game
                else:
                    serverId = str(guild.id)

                    # check to see if who dis games are configured 
                    isConfigured = self.isServerWhoDisConfigured(guild)
                    if not isConfigured[0]:
                        raise WhoDisNotConfigured
                    whoDisRole: nextcord.Role = isConfigured[1]
                    
                    # check to see if author is assigned who dis role
                    optInMessage = ''
                    if not utils.isUserAssignedRole(author, whoDisRole.id):                    
                        # if user is not assigned the who dis consent role, assign it
                        isRoleAdded = await utils.addRoleToUser(author, whoDisRole)
                        if isRoleAdded:
                            # send message saying you have opted in
                            optInMessage = "You have consented to participating in 'Who Dis?' games. Please follow your server's rules. You can opt-out with the `/leaveDis` command anytime.\n"
                        else:
                            await context.send(f"Sorry {authorMention}, there was a problem opting you into 'Who Dis?' games.")
                            await utils.sendMessageToAdmins(self.client, serverId, f"{authorMention}'s whoDis command failed as there was a problem assigning them the {whoDisRole.mention} role.")
                            self.logger.error(f'Who Dis game failed in server {serverId} due to error assigning user {authorId} role {whoDisRole.id}.')
                            return
                    randomUser = await self.getRandomWhoDisUser(authorId, guild, whoDisRole)
                    if randomUser is None:
                        await context.send(f'Sorry {authorMention}, there are currently no users available for Who Dis.')
                    else:
                        await context.send(optInMessage + 'Who Dis starting...')
                        await self.startWhoDis(author, randomUser, guild)

        except WhoDisNotConfigured:
            await context.send(f'Sorry {authorMention}, Who Dis is not configured in this server.')
            await utils.sendMessageToAdmins(self.client, serverId, f"{authorMention}'s whoDis command failed as there is currently no role configured for Who Dis.")
            self.logger.error(f'Who Dis game not allowed in server {serverId} due to not being configured.')
        finally:
            self.whoDisLock.release()

    @nextcord.slash_command(name = strings.LEAVEDIS_NAME, description = strings.LEAVEDIS_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_who_dis', True, True)
    async def leaveDisSlash(self, interaction: nextcord.Interaction):
        await self.commonLeaveDis(interaction, interaction.user)

    @commands.command(aliases = strings.LEAVEDIS_ALIASES, brief = "- " + strings.LEAVEDIS_BRIEF, description = strings.LEAVEDIS_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_who_dis', True)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', True)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def leavedis(self, ctx: Context):
        await self.commonLeaveDis(ctx, ctx.author)

    async def commonLeaveDis(self, context, author: nextcord.Member):
        # unassign role and send message
        try:
            guild = context.guild
            serverId = guild.id
            authorId = author.id
            authorMention = author.mention

            # check to see if who dis games are configured 
            isConfigured = self.isServerWhoDisConfigured(guild)
            if not isConfigured[0]:
                raise WhoDisNotConfigured
            whoDisRole: nextcord.Role = isConfigured[1]
            
            # remove author's who dis role if assigned
            if utils.isUserAssignedRole(author, whoDisRole.id):   
                await author.remove_roles(whoDisRole)
                await context.send(f"{authorMention}, you have successfully opted-out of this server's 'Who Dis?' games.")
            else:
                await context.send(f"{authorMention}, you are already not participating in this server's 'Who Dis?' games.")
        except WhoDisNotConfigured:
            await context.send(f'Sorry {authorMention}, Who Dis is not configured in this server.')
            await utils.sendMessageToAdmins(self.client, serverId, f"{authorMention}'s whoDis command failed as there is currently no role configured for Who Dis.")
            self.logger.error(f'Who Dis game not allowed in server {serverId} due to not being configured.')

    @nextcord.slash_command(name = strings.DIS_NAME, description = strings.DIS_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInPrivateMessage(True)
    @predicates.isFeatureEnabledForServer('toggle_who_dis', True, True)
    async def disSlash(self,
                       interaction: nextcord.Interaction,
                       user = nextcord.SlashOption(
                            name = 'user',
                            required = True,
                            description = strings.DIS_USER_DESCRIPTION
                       )):
        await self.commonDis(interaction, interaction.user, user)

    @commands.command(aliases = strings.DIS_ALIASES, brief = "- " + strings.DIS_BRIEF, description = strings.DIS_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_who_dis', True)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', True)
    @predicates.isMessageSentInPrivateMessage()
    @predicates.isGuildOrUserSubscribed()
    async def dis(self, ctx: Context, user):
        await self.commonDis(ctx, ctx.author, user)

    async def commonDis(self, context, author, user: str):
        authorId = author.id
        authorMention = author.mention

        # check to see if user is already in a who dis game
        existingGameKey = self.getWhoDisGameKey(authorId)
        if existingGameKey is None:
            # if no ongoing who dis, send error message
            await context.send(f'Sorry {authorMention}, there is currently no active Who Dis game.')
            return

        # make sure the person guessing is the initiator
        if not existingGameKey.startswith(str(authorId) + ':'):
            await context.send(f'Sorry {authorMention}, only the initiator can use this command.')
            return

        # determine author's guess
        guild = self.whoDisGames[existingGameKey]['guild']
        userId = await utils.getUserIdFromName(guild, user.removeprefix('@'))
        if userId is None:
            # if no user found in guild send error message
            await context.send(f'Sorry {authorMention}, please provide the name of a user in the server in which the Who Dis game was started. Nicknames are not supported.')
            return
        guessKey = str(authorId) + ':' + str(userId)
        
        # tell user if correct or not and end who dis
        await self.guessWhoDis(context, guessKey, existingGameKey)            
    
    @nextcord.slash_command(name = strings.REPORT_NAME, description = strings.REPORT_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isFeatureEnabledForServer('toggle_who_dis', True, True)
    async def reportSlash(self,
                          interaction: nextcord.Interaction,
                          user: nextcord.User = nextcord.SlashOption(
                                name = 'user',
                                required = False,
                                description = strings.REPORT_USER_DESCRIPTION
                          )):
        await self.commonReport(interaction, interaction.user, user)

    @commands.command(aliases = strings.REPORT_ALIASES, brief = "- " + strings.REPORT_BRIEF, description = strings.REPORT_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_who_dis', True)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', True)
    @predicates.isGuildOrUserSubscribed()
    async def report(self, ctx: Context, user: nextcord.User = None):
        await self.commonReport(ctx, ctx.author, user)

    async def commonReport(self, context, author, user: nextcord.User):
        if isinstance(context, nextcord.Interaction):
            await context.response.defer()

        guild = context.guild
        authorId = author.id
        authorMention = author.mention
        
        # check to see if user is already in a who dis game
        existingGameKey = self.getWhoDisGameKey(authorId)

        # if in a guild
        if guild is not None:
            serverId = guild.id
            # if no user provided, send error message saying need to provide user
            if user is None:
                await context.send(f'Sorry {authorMention}, please report a user when using this command in a server.')
                return
            else:
                userId = await utils.getUserIdFromName(guild, user.name)
                if userId is None:
                    # if no user found in guild send error message
                    await context.send(f'Sorry {authorMention}, please provide the name of a user in this server. Nicknames are not supported.')
                    return
                
                # try to collect the reported user's last x messages in the reported channel
                isReportSuccessful = await utils.sendMessageToAdmins(self.client, serverId, f"{authorMention} reported {user.mention} in channel {context.channel.mention}. If captured, the reported user's last {self.NUM_MESSAGES_TO_REPORT} messages will show below.")
                reportedUser = user
                collectedMessages = []
                async for message in context.channel.history(limit = self.MAX_CHANNEL_MSG_HISTORY_LOOKUP):
                    if len(collectedMessages) >= self.NUM_MESSAGES_TO_REPORT:
                        break
                    if message.author.id == user.id:
                        if (message.content and (message.content.startswith('.') or message.content.startswith('/') or message.content.startswith(utils.getServerPrefixOrDefault(message)))):
                            continue
                        collectedMessages.append(message)
                collectedMessages.reverse()
        # if sent in a private message (who dis), ignore user argument
        else:
            # if no ongoing who dis, send error message saying no ongoing dis and/or need to be in guild
            if existingGameKey is None:
                await context.send(f'Sorry {authorMention}, there is currently no active Who Dis game. You can report users in server text channels as well.')
                return
            # if ongoing who dis, send message to guild admin channel with last x messsages from reported user
            else:
                # determine if author is initiator or random user
                serverId = self.whoDisGames[existingGameKey]['guild'].id
                initiator: nextcord.User = self.whoDisGames[existingGameKey]['initiator']
                if initiator.id == authorId:
                    reportedUser = self.whoDisGames[existingGameKey]['randomUser']
                    collectedMessages = self.whoDisGames[existingGameKey]['randomUserMessages']
                else:
                    reportedUser = initiator
                    collectedMessages = self.whoDisGames[existingGameKey]['initiatorMessages']
                isReportSuccessful = await utils.sendMessageToAdmins(self.client, serverId, f"{authorMention} reported {reportedUser.mention} in a private Who Dis game. If captured, the reported user's last {self.NUM_MESSAGES_TO_REPORT} messages will show below.")
        # report collected messages if intial report successful (from channels or who dis games)
        if (isReportSuccessful):
            counter = 1
            for message in collectedMessages:
                # send text if any
                if message.content:
                    textToSend = f'{counter}.) Captured message from {reportedUser.mention}: {message.content}'
                # if not, prep to to send attachments and stickers
                else:
                    textToSend = f'{counter}.) Captured message from {reportedUser.mention}:'
                await utils.sendMessageToAdmins(self.client, serverId, textToSend)

                # send attachments if any
                if message.attachments:
                    for attachment in message.attachments:
                        await utils.sendMessageToAdmins(self.client, serverId, attachment.url)
                # send stickers if any
                if message.stickers:
                    for sticker in message.stickers:
                        await utils.sendMessageToAdmins(self.client, serverId, sticker.url)
                counter += 1
            await context.send(f'The report has been successfully submitted.')
        else:
            await context.send(f'The report was not submitted because the server has no admin channel configured.')

    def isServerWhoDisConfigured(self, guild: nextcord.Guild):
        serverId = guild.id
        isWhoDisEnabled = config_queries.getServerValue(serverId, 'toggle_who_dis')
        roleId = config_queries.getServerValue(serverId, 'role_who_dis')
        if roleId == None:
            return (False, None)
        whoDisRole: nextcord.Role = None
        for role in guild.roles:
            if str(role.id) == roleId:
                whoDisRole = role
                break
        return (isWhoDisEnabled and whoDisRole != None, whoDisRole)

    async def getRandomWhoDisUser(self, authorId, guild: nextcord.Guild, role: nextcord.Role):
        # user requirements: online, not a bot, in the same guild, not initiator, not in game already, & assigned the who dis role
        onlineUsersWithRole = []
        onlineUsers = await utils.getOnlineAndIdleUsers(guild)
        for onlineUser in onlineUsers:
            userId = onlineUser.id
            if authorId != userId and self.getWhoDisGameKey(userId) == None and utils.isUserAssignedRole(onlineUser, role.id):
                onlineUsersWithRole.append(onlineUser)
        
        # if list not empty, choose a random user
        if len(onlineUsersWithRole) > 0:
            return random.choice(onlineUsersWithRole)
        # return None if no users available
        else:
            return None

    def getWhoDisGameKey(self, userId):
        for gameKey in self.whoDisGames.keys():
            if str(userId) in gameKey:
                return gameKey
        return None

    async def startWhoDis(self, initiator: nextcord.User, randomUser: nextcord.User, guild: nextcord.Guild):
        dateTimeNow = datetime.now()
        startTime = dateTimeNow.strftime("%m/%d/%y %I:%M:%S %p")
        newWhoDis = {
            'startTime': startTime,
            'initiator': initiator,
            'randomUser': randomUser,
            'guild': guild,
            'initiatorMessages': [],
            'randomUserMessages': [],
        }
        initiatorId = str(initiator.id)
        randomUserId = str(randomUser.id)
        gameKey = initiatorId + ':' + randomUserId
        self.whoDisGames[gameKey] = newWhoDis
        self.logger.info(f'New Who Dis game started: initiating user {initiatorId} was paired with random user {randomUserId} in server {guild.id}.')
        await initiator.send(f"# NEW MESSAGE, WHO DIS? - GAME STARTED #\n**(please guess the random user using the `/dis` command within {GBotPropertiesManager.WHODIS_TIMEOUT_MINUTES} minutes)**")
        await randomUser.send(f"# NEW MESSAGE, WHO DIS? - GAME STARTED #\n**(someone is trying to guess who you are)**")

    async def cancelWhoDis(self, gameKey, authorId):
        initiator: nextcord.User = self.whoDisGames[gameKey]['initiator']
        randomUser: nextcord.User = self.whoDisGames[gameKey]['randomUser']
        if authorId == initiator.id:
            await initiator.send(f"# DIS... A GHOST? - GAME CANCELLED #\n**(you cancelled the game)**")
            await randomUser.send(f"# DIS... A GHOST? - GAME CANCELLED #\n**(the game was cancelled)**")
        else:
            await initiator.send(f"# DIS... A GHOST? - GAME CANCELLED #\n**(the game was cancelled)**")
            await randomUser.send(f"# DIS... A GHOST? - GAME CANCELLED #\n**(you cancelled the game)**")
        self.whoDisGames.pop(gameKey)
        self.logger.info(f'Who Dis game with the following game-key cancelled: {gameKey}')

    async def guessWhoDis(self, context, guessKey, gameKey):
        # game keys look like '012345678910111213:131211109876543210'
        initiator: nextcord.User = self.whoDisGames[gameKey]['initiator']
        randomUser: nextcord.User = self.whoDisGames[gameKey]['randomUser']
        initiatorMention = initiator.mention
        randomUserMention = randomUser.mention
        # if guess is correct
        if guessKey == gameKey:
            self.rewardGuesser(initiator)
            await context.send(f"# DIS {randomUserMention} - GAME OVER #\n**(you guessed correctly and won {self.GUESS_REWARD_GCOIN} GCoin!)**")
            await randomUser.send(f"# DIS {initiatorMention} - GAME OVER #\n**(they figured out it was you!)**")
        # if guess is not correct
        else:
            await context.send(f"# DIS {randomUserMention} - GAME OVER #\n**(you guessed incorrectly!)**")
            await randomUser.send(f"# DIS {initiatorMention} - GAME OVER #\n**(they couldn't figure out it was you!)**")
        self.whoDisGames.pop(gameKey)
        self.logger.info(f'Who Dis game with the following game-key ended: {gameKey}')       

    async def timeoutWhoDis(self, gameKey):
        initiator: nextcord.User = self.whoDisGames[gameKey]['initiator']
        randomUser: nextcord.User = self.whoDisGames[gameKey]['randomUser']
        await initiator.send(f"# DIS... A GHOST? - GAME TIMED OUT #\n**(you ran out of time!)**")
        await randomUser.send(f"# DIS... A GHOST? - GAME TIMED OUT #\n**(they couldn't figure out it was you!)**")
        self.whoDisGames.pop(gameKey)
        self.logger.info(f'Who Dis game with the following game-key timed out: {gameKey}')

    def rewardGuesser(self, initiator: nextcord.User):
        # give initiator points
        dateTimeObj = datetime.now()
        date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")
        sender = { 'id': None, 'name': 'Who Dis' }
        receiver = { 'id': initiator.id, 'name': initiator.name }
        gcoin_queries.performTransaction(self.GUESS_REWARD_GCOIN, date, sender, receiver, '', 'Guessed User', False, False)

def setup(client: commands.Bot):
    client.add_cog(WhoDis(client))