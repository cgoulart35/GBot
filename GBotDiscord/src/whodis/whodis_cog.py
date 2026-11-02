#region IMPORTS
import logging
import asyncio
import random
import nextcord
from nextcord.ext import commands, tasks
from nextcord.ext.commands.context import Context
from decimal import Decimal
from datetime import datetime, timedelta

from GBotDiscord.src import presentation
from GBotDiscord.src import strings
from GBotDiscord.src import utils
from GBotDiscord.src import predicates
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.gcoin import gcoin_queries
from GBotDiscord.src.leaderboards import leaderboards_queries
from GBotDiscord.src.exceptions import WhoDisNotConfigured, CustomCommandOnCooldown
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.firebase import GBotFirebaseService
#endregion

class WhoDis(commands.Cog):

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()

        self.MAX_CHANNEL_MSG_HISTORY_LOOKUP = 250
        self.NUM_MESSAGES_TO_REPORT = 5
        self.BASE_REWARD_MULTIPLIER = Decimal('50.00')
        self.MAX_REWARD_GCOIN = Decimal('1000000.00')
        self.NUM_PARTICIPANTS_FOR_MAX_REWARD = 20000

        self.whoDisGames = {}
        self.whoDisCooldown = {}
        self.whoDisStartLock = asyncio.Lock()
        self.whoDisGuessLock = asyncio.Lock()

    # Events
    @commands.Cog.listener()
    async def on_ready(self):
        try:
            self.who_dis_timeout.start()
        except RuntimeError:
            self.logger.info('who_dis_timeout task is already launched and is not completed.')

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: nextcord.Guild):
        # the players' guesses and reports need this server, so their game can't carry on
        for gameKey in [key for key, game in self.whoDisGames.items() if game['guild'].id == guild.id]:
            game = self.whoDisGames.pop(gameKey)
            self.logger.info(f'Who Dis game with the following game-key ended because GBot left server {guild.id}: {gameKey}')
            await self.notifyPlayers((game['initiator'], game['randomUser']), '🚪 Game over', 'GBot left the server this game was started from.', gameKey)

    @commands.Cog.listener()
    async def on_message(self, msg: nextcord.Message):
        # make sure message in a private message not from a bot
        if (msg.guild == None and not msg.author.bot):
            authorId = msg.author.id
            # check to see if message author is in a who dis game
            existingGameKey = self.getWhoDisGameKey(authorId)
            if existingGameKey is not None:
                # skip over commands & don't send/save for reports. Only real ones: "...ok" is chat
                if (await self.client.get_context(msg)).valid:
                    return

                # determine if author is initiator or random user & forward message to paired user
                initiator: nextcord.User = self.whoDisGames[existingGameKey]['initiator']
                if initiator.id == authorId:
                    sendToUser: nextcord.User = self.whoDisGames[existingGameKey]['randomUser']
                    if len(self.whoDisGames[existingGameKey]['initiatorMessages']) >= self.NUM_MESSAGES_TO_REPORT:
                        self.whoDisGames[existingGameKey]['initiatorMessages'].pop(0)
                    self.whoDisGames[existingGameKey]['initiatorMessages'].append(msg)
                else:
                    sendToUser: nextcord.User = initiator
                    if len(self.whoDisGames[existingGameKey]['randomUserMessages']) >= self.NUM_MESSAGES_TO_REPORT:
                        self.whoDisGames[existingGameKey]['randomUserMessages'].pop(0)
                    self.whoDisGames[existingGameKey]['randomUserMessages'].append(msg)
                # send text if any. Nitro allows longer messages than a bot can send in one.
                if msg.content:
                    for part in utils.splitMessage(msg.content):
                        await sendToUser.send(part)
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

            # get timed out games
            timedOutGameKeys = []
            for gameKey, gameInfo in self.whoDisGames.items():
                startTime = datetime.strptime(gameInfo['startTime'], "%m/%d/%y %I:%M:%S %p")
                if currentTime >= startTime + timedelta(minutes = GBotPropertiesManager.WHODIS_TIMEOUT_MINUTES):
                    timedOutGameKeys.append(gameKey)
            # time out the games after identifying them so we don't modify the size of the whoDisGames dict
            for gameKey in timedOutGameKeys:
                await self.timeoutWhoDis(gameKey)

            # get timed out cooldowns
            timedOutUserCooldowns = []
            for userId, timeStartedStr in self.whoDisCooldown.items():
                timeStarted = datetime.strptime(timeStartedStr, "%m/%d/%y %I:%M:%S %p")
                if currentTime >= timeStarted + timedelta(minutes = GBotPropertiesManager.WHODIS_COOLDOWN_MINUTES):
                    timedOutUserCooldowns.append(userId)

            # time out cooldown locks after set time period
            for userId in timedOutUserCooldowns:
                self.whoDisCooldown.pop(userId)
                self.logger.info(f'Who Dis cooldown timed out for user: {userId}')
        except Exception as e:
            self.logger.error(f'Error in WhoDis.who_dis_timeout(): {e}')

    # Commands
    # The two group roots. Discord never invokes a slash command that has subcommands, so the slash
    # root's body is unreachable in production — nextcord just needs a callback to hang the group on.
    @nextcord.slash_command(name = strings.WHODIS_GROUP_NAME, description = strings.WHODIS_GROUP_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    async def whodisSlashGroup(self, interaction: nextcord.Interaction):
        pass

    @commands.group(name = strings.WHODIS_GROUP_NAME, aliases = strings.WHODIS_GROUP_ALIASES, brief = "- " + strings.WHODIS_GROUP_BRIEF, description = strings.WHODIS_GROUP_DESCRIPTION, invoke_without_command = True)
    # invoke_without_command means these run ONLY for a bare ".whodis" — when a subcommand
    # matches, nextcord dispatches straight to it and the root's checks never fire. So this
    # is the group's own gate, not a second one on every leaf: it mirrors exactly the checks
    # every leaf here shares, or a bare root would be an ungated way into a gated cog.
    @predicates.isFeatureEnabledForServer('toggle_who_dis', True)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', True)
    @predicates.isGuildOrUserSubscribed()
    async def whodisGroup(self, ctx: Context):
        # a bare ".whodis" names no subcommand; list what lives under the group instead of doing nothing
        await ctx.send_help(ctx.command)

    @whodisSlashGroup.subcommand(name = strings.WHODIS_START_NAME, description = strings.WHODIS_START_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isFeatureEnabledForServer('toggle_who_dis', True, True)
    async def startSlash(self, interaction: nextcord.Interaction):
        await self.commonWhoDis(interaction, interaction.user)

    @whodisGroup.command(name = strings.WHODIS_START_NAME, aliases = strings.WHODIS_START_ALIASES, brief = "- " + strings.WHODIS_START_BRIEF, description = strings.WHODIS_START_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_who_dis', True)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', True)
    @predicates.isGuildOrUserSubscribed()
    async def start(self, ctx: Context):
        await self.commonWhoDis(ctx, ctx.author)

    async def commonWhoDis(self, context, author: nextcord.Member):
        guild = context.guild
        authorId = author.id
        authorMention = author.mention
        deleteMsgs = []

        # check to see if sent in a private message
        isPrivateMessage = guild is None

        # bind the above before the try, so an unexpected failure inside it (a deferral that
        # fails, say) surfaces as itself instead of as UnboundLocalError from the finally
        try:
            # private, because who started a game is the secret the whole mini-game rests on
            if isinstance(context, nextcord.Interaction):
                await context.response.defer(ephemeral = True)

            # obtain lock for starting who dis games; only one who dis can be started at a time
            # (ensures user pairings are unique) — concurrent starts wait here rather than racing
            async with self.whoDisStartLock:
                # check to see if user is already in a who dis game
                existingGameKey = self.getWhoDisGameKey(authorId)

                # end the existing game whether in a guild or private message
                if existingGameKey is not None:
                    await self.cancelWhoDis(context, isPrivateMessage, author, deleteMsgs, existingGameKey)

                # start a new game only if sent in a guild
                else:
                    # sent in a private message; send error message need to start in guild
                    if isPrivateMessage:
                        await presentation.sendError(context, f'Sorry {authorMention}, Who Dis games must be started in a server.')
                    # sent in a guild; start a new game
                    else:
                        serverId = str(guild.id)

                        # check to see if who dis games are configured
                        isConfigured = await GBotFirebaseService.run(self.isServerWhoDisConfigured, guild)
                        if not isConfigured[0]:
                            raise WhoDisNotConfigured
                        whoDisRole: nextcord.Role = isConfigured[1]

                        # check to see if author is online
                        if (author.status != nextcord.Status.online and author.status != nextcord.Status.idle):
                            await self.refuseStart(context, author, deleteMsgs, f"Sorry {authorMention}, you need to be online to start 'Who Dis?' games.")
                            return

                        # check to see if author is assigned who dis role
                        if not utils.isUserAssignedRole(author, whoDisRole.id):
                            # if user is not assigned the who dis consent role, assign it
                            isRoleAdded = await utils.addRoleToUser(author, whoDisRole)
                            if isRoleAdded:
                                # send message saying you have opted in
                                await author.send("❓ You have consented to participating in 'Who Dis?' games. Please follow your server's rules. You can opt-out with the `/whodis leave` command anytime.")
                            else:
                                await self.refuseStart(context, author, deleteMsgs, f"Sorry {authorMention}, there was a problem opting you into 'Who Dis?' games.")
                                await utils.sendMessageToAdmins(self.client, serverId, f"{authorMention}'s whoDis command failed as there was a problem assigning them the {whoDisRole.mention} role.", self.logger)
                                self.logger.error(f'Who Dis game failed in server {serverId} due to error assigning user {authorId} role {whoDisRole.id}.')
                                return

                        # check to see if author is currently in cooldown
                        authorIdStr = str(authorId)
                        if (authorIdStr in self.whoDisCooldown):
                            timeStartedStr = self.whoDisCooldown[authorIdStr]
                            timeStarted = datetime.strptime(timeStartedStr, "%m/%d/%y %I:%M:%S %p")
                            timeCooldownEnd = timeStarted + timedelta(minutes = GBotPropertiesManager.WHODIS_COOLDOWN_MINUTES)
                            timeLeftDelta = timeCooldownEnd - datetime.now()
                            if isinstance(context, Context):
                                deleteMsgs.append(await context.send('Who Dis not started.'))
                            raise CustomCommandOnCooldown(timeLeftDelta.total_seconds(), True, "to start another 'Who Dis?' game.")

                        randomUserData = await self.getRandomWhoDisUser(authorId, guild, whoDisRole)
                        if randomUserData[0] is None:
                            await self.refuseStart(context, author, deleteMsgs, f'Sorry {authorMention}, there are currently no users available for Who Dis.')
                        else:
                            if await self.startWhoDis(author, randomUserData[0], randomUserData[1], guild):
                                await self.reportStatus(context, deleteMsgs, 'Who Dis starting...')
                            else:
                                await self.refuseStart(context, author, deleteMsgs, f"Sorry {authorMention}, the game couldn't start because private messages are closed for one of the players. Please try again.")

        except WhoDisNotConfigured:
            await self.refuseStart(context, author, deleteMsgs, f'Sorry {authorMention}, Who Dis is not configured in this server.')
            await utils.sendMessageToAdmins(self.client, serverId, f"{authorMention}'s whoDis command failed as there is currently no role configured for Who Dis.", self.logger)
            self.logger.error(f'Who Dis game not allowed in server {serverId} due to not being configured.')
        finally:
            # delete original msg (if context)
            if isinstance(context, Context):
                deleteMsgs.append(context.message)
            if not isPrivateMessage:
                await self.deletePublicWhoDisMessages(guild.id, deleteMsgs, context.channel)

    @whodisSlashGroup.subcommand(name = strings.WHODIS_LEAVE_NAME, description = strings.WHODIS_LEAVE_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_who_dis', True, True)
    async def leaveSlash(self, interaction: nextcord.Interaction):
        await self.commonLeaveDis(interaction, interaction.user)

    @whodisGroup.command(name = strings.WHODIS_LEAVE_NAME, aliases = strings.WHODIS_LEAVE_ALIASES, brief = "- " + strings.WHODIS_LEAVE_BRIEF, description = strings.WHODIS_LEAVE_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_who_dis', True)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', True)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def leave(self, ctx: Context):
        await self.commonLeaveDis(ctx, ctx.author)

    async def commonLeaveDis(self, context, author: nextcord.Member):
        # unassign role and send message
        try:
            guild = context.guild
            serverId = guild.id
            authorId = author.id
            authorMention = author.mention

            # check to see if who dis games are configured 
            isConfigured = await GBotFirebaseService.run(self.isServerWhoDisConfigured, guild)
            if not isConfigured[0]:
                raise WhoDisNotConfigured
            whoDisRole: nextcord.Role = isConfigured[1]
            
            # remove author's who dis role if assigned
            if utils.isUserAssignedRole(author, whoDisRole.id):   
                await author.remove_roles(whoDisRole)
                await presentation.sendReply(context, content = f"👋 {authorMention}, you have successfully opted-out of this server's 'Who Dis?' games.", ephemeral = True)
            else:
                await presentation.sendError(context, f"{authorMention}, you are already not participating in this server's 'Who Dis?' games.")
        except WhoDisNotConfigured:
            await presentation.sendError(context, f'Sorry {authorMention}, Who Dis is not configured in this server.')
            await utils.sendMessageToAdmins(self.client, serverId, f"{authorMention}'s whoDis command failed as there is currently no role configured for Who Dis.", self.logger)
            self.logger.error(f'Who Dis game not allowed in server {serverId} due to not being configured.')

    @whodisSlashGroup.subcommand(name = strings.WHODIS_GUESS_NAME, description = strings.WHODIS_GUESS_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInPrivateMessage(True)
    @predicates.isFeatureEnabledForServer('toggle_who_dis', True, True)
    async def guessSlash(self,
                       interaction: nextcord.Interaction,
                       user = nextcord.SlashOption(
                            name = 'user',
                            required = True,
                            description = strings.WHODIS_GUESS_USER_DESCRIPTION
                       )):
        await self.commonDis(interaction, interaction.user, user)

    @whodisGroup.command(name = strings.WHODIS_GUESS_NAME, aliases = strings.WHODIS_GUESS_ALIASES, brief = "- " + strings.WHODIS_GUESS_BRIEF, description = strings.WHODIS_GUESS_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_who_dis', True)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', True)
    @predicates.isMessageSentInPrivateMessage()
    @predicates.isGuildOrUserSubscribed()
    async def guess(self, ctx: Context, user):
        await self.commonDis(ctx, ctx.author, user)

    async def commonDis(self, context, author, user: str):
        if isinstance(context, nextcord.Interaction):
            await context.response.defer()

        authorId = author.id
        authorMention = author.mention

        # obtain lock for guessing who dis games; only one user can guess at a time (ensures only 1 winner)
        async with self.whoDisGuessLock:
            # check to see if user is already in a who dis game
            existingGameKey = self.getWhoDisGameKey(authorId)
            if existingGameKey is None:
                # if no ongoing who dis, send error message
                await presentation.sendError(context, f'Sorry {authorMention}, there is currently no active Who Dis game.')
                return

            # determine author's guess
            guild = self.whoDisGames[existingGameKey]['guild']
            userId = await utils.getUserIdFromName(guild, user.removeprefix('@'))
            if userId is None:
                # if no user found in guild send error message
                await presentation.sendError(context, f'Sorry {authorMention}, please provide the name of a user in the server in which the Who Dis game was started. Nicknames are not supported.')
                return
            guessKey = [authorId, userId]

            # tell user if correct or not and end who dis
            await self.guessWhoDis(context, author, guessKey, existingGameKey)
    
    @whodisSlashGroup.subcommand(name = strings.WHODIS_REPORT_NAME, description = strings.WHODIS_REPORT_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isFeatureEnabledForServer('toggle_who_dis', True, True)
    async def reportSlash(self,
                          interaction: nextcord.Interaction,
                          user: nextcord.User = nextcord.SlashOption(
                                name = 'user',
                                required = False,
                                description = strings.WHODIS_REPORT_USER_DESCRIPTION
                          )):
        await self.commonReport(interaction, interaction.user, user)

    @whodisGroup.command(name = strings.WHODIS_REPORT_NAME, aliases = strings.WHODIS_REPORT_ALIASES, brief = "- " + strings.WHODIS_REPORT_BRIEF, description = strings.WHODIS_REPORT_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_who_dis', True)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', True)
    @predicates.isGuildOrUserSubscribed()
    async def report(self, ctx: Context, user: nextcord.User = None):
        await self.commonReport(ctx, ctx.author, user)

    async def commonReport(self, context, author, user: nextcord.User):
        if isinstance(context, nextcord.Interaction):
            # private, or the channel learns that someone reported someone
            await context.response.defer(ephemeral = True)

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
                await presentation.sendError(context, f'Sorry {authorMention}, please report a user when using this command in a server.')
                return
            else:
                userId = await utils.getUserIdFromName(guild, user.name)
                if userId is None:
                    # if no user found in guild send error message
                    await presentation.sendError(context, f'Sorry {authorMention}, please provide the name of a user in this server. Nicknames are not supported.')
                    return
                
                # try to collect the reported user's last x messages in the reported channel
                isReportSuccessful = await utils.sendMessageToAdmins(self.client, serverId, f"{authorMention} reported {user.mention} in channel {context.channel.mention}. If captured, the reported user's last {self.NUM_MESSAGES_TO_REPORT} messages will show below.", self.logger)
                reportedUser = user
                collectedMessages = []
                async for message in context.channel.history(limit = self.MAX_CHANNEL_MSG_HISTORY_LOOKUP):  # pragma: no branch
                    if len(collectedMessages) >= self.NUM_MESSAGES_TO_REPORT:
                        break
                    if message.author.id == user.id:
                        if (message.content and (message.content.startswith('.') or message.content.startswith('/') or message.content.startswith(await GBotFirebaseService.run(utils.getServerPrefixOrDefault, message)))):
                            continue
                        collectedMessages.append(message)
                collectedMessages.reverse()
        # if sent in a private message (who dis), ignore user argument
        else:
            # if no ongoing who dis, send error message saying no ongoing dis and/or need to be in guild
            if existingGameKey is None:
                await presentation.sendError(context, f'Sorry {authorMention}, there is currently no active Who Dis game. You can report users in server text channels as well.')
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
                isReportSuccessful = await utils.sendMessageToAdmins(self.client, serverId, f"{authorMention} reported {reportedUser.mention} in a private Who Dis game. If captured, the reported user's last {self.NUM_MESSAGES_TO_REPORT} messages will show below.", self.logger)
        # report collected messages if intial report successful (from channels or who dis games)
        if (isReportSuccessful):
            counter = 1
            isEverythingSent = True
            for message in collectedMessages:
                # send text if any
                if message.content:
                    textToSend = f'{counter}.) Captured message from {reportedUser.mention}: {message.content}'
                # if not, prep to to send attachments and stickers
                else:
                    textToSend = f'{counter}.) Captured message from {reportedUser.mention}:'
                # the added text can take a message that fit over Discord's limit
                pieces = utils.splitMessage(textToSend)
                # send attachments if any
                if message.attachments:
                    pieces.extend(attachment.url for attachment in message.attachments)
                # send stickers if any
                if message.stickers:
                    pieces.extend(sticker.url for sticker in message.stickers)
                for piece in pieces:
                    isEverythingSent = await utils.sendMessageToAdmins(self.client, serverId, piece, self.logger) and isEverythingSent
                counter += 1
            if isEverythingSent:
                await presentation.sendReply(context, content = '✅ The report has been successfully submitted.', ephemeral = True)
            else:
                await presentation.sendError(context, 'The report was only partly submitted. Please let an admin know.')
        else:
            await presentation.sendError(context, f'The report was not submitted because the server has no admin channel configured.')

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
        # user requirements: online, not a bot, in the same guild, assigned the who dis role, not initiator, not in game already
        otherOnlineUsersWithRole = []
        numOnlineParticipants = 0
        onlineUsers = await utils.getOnlineAndIdleUsers(guild)
        for onlineUser in onlineUsers:
            userId = onlineUser.id
            if utils.isUserAssignedRole(onlineUser, role.id):
                numOnlineParticipants += 1
                if authorId != userId and self.getWhoDisGameKey(userId) == None:
                    otherOnlineUsersWithRole.append(onlineUser)
        
        # if list not empty, choose a random user
        if len(otherOnlineUsersWithRole) > 0:
            return (random.choice(otherOnlineUsersWithRole), numOnlineParticipants)
        # return None if no users available
        else:
            return (None, None)

    def getWhoDisGameKey(self, userId):
        # match a whole id, not a substring of the key: Discord ids vary in length, so a
        # shorter (older) id contained in a longer one would otherwise collide
        for gameKey in self.whoDisGames.keys():
            if str(userId) in gameKey.split(':'):
                return gameKey
        return None

    async def startWhoDis(self, initiator: nextcord.User, randomUser: nextcord.User, numOnlineParticipants, guild: nextcord.Guild):
        # returns whether the game started. Told first and recorded after: someone with private messages
        # closed could never play, and the game would otherwise hold both players and spend the cooldown.
        dateTimeNow = datetime.now()
        startTime = dateTimeNow.strftime("%m/%d/%y %I:%M:%S %p")
        initiatorId = str(initiator.id)
        randomUserId = str(randomUser.id)
        gameKey = initiatorId + ':' + randomUserId
        card = self.gameCard('🕵️ New message... who dis?', f"Someone mysterious from `{guild.name}` just slid into your DMs. Chat here, then guess who with `/whodis guess` within {GBotPropertiesManager.WHODIS_TIMEOUT_MINUTES} minutes.")
        try:
            await initiator.send(embed = card)
        except nextcord.HTTPException as e:
            self.logger.info(f'Who Dis game not started in server {guild.id} as initiating user {initiatorId} could not be messaged: {e}')
            return False
        try:
            await randomUser.send(embed = card)
        except nextcord.HTTPException as e:
            self.logger.info(f'Who Dis game not started in server {guild.id} as random user {randomUserId} could not be messaged: {e}')
            await self.notifyPlayers((initiator,), '🚪 Game cancelled', 'The other player can not be messaged right now.', gameKey)
            return False
        self.whoDisGames[gameKey] = {
            'startTime': startTime,
            'initiator': initiator,
            'randomUser': randomUser,
            'numOnlineParticipants': numOnlineParticipants,
            'guild': guild,
            'initiatorMessages': [],
            'randomUserMessages': [],
        }
        self.whoDisCooldown[initiatorId] = startTime
        self.logger.info(f'New Who Dis game started: initiating user {initiatorId} was paired with random user {randomUserId} in server {guild.id}.')
        return True

    async def cancelWhoDis(self, context, isPrivateMessage, author, deleteMsgs, gameKey):
        initiator: nextcord.User = self.whoDisGames[gameKey]['initiator']
        randomUser: nextcord.User = self.whoDisGames[gameKey]['randomUser']
        
        self.whoDisGames.pop(gameKey)
        self.logger.info(f'Who Dis game with the following game-key cancelled: {gameKey}')

        # if not sent in a private message, delete replies and original msg (if context) and just reponse (if interaction)
        if isPrivateMessage:
            await context.send(embed = self.gameCard('🚪 Game cancelled', 'You cancelled the game.'))
        else:
            await author.send(embed = self.gameCard('🚪 Game cancelled', 'You cancelled the game.'))
            await self.reportStatus(context, deleteMsgs, 'Who Dis cancelled.')
        
        if author.id == initiator.id:
            await randomUser.send(embed = self.gameCard('🚪 Game cancelled', 'The other player left. No hard feelings.'))
        else:
            await initiator.send(embed = self.gameCard('🚪 Game cancelled', 'The other player left. No hard feelings.'))

    async def guessWhoDis(self, context, author, guessKey, gameKey):
        # guess key is list of 2 user IDs
        # game keys look like '012345678910111213:131211109876543210'
        initiator: nextcord.User = self.whoDisGames[gameKey]['initiator']
        randomUser: nextcord.User = self.whoDisGames[gameKey]['randomUser']
        numOnlineParticipants = self.whoDisGames[gameKey]['numOnlineParticipants']

        # as of right now, the game ends if a user guesses incorrectly too
        self.whoDisGames.pop(gameKey)
        self.logger.info(f'Who Dis game with the following game-key ended: {gameKey}')  

        # determine other user
        if author.id == initiator.id:
            otherUser = randomUser
            otherUserMention = randomUser.mention
        else:
            otherUser = initiator
            otherUserMention = initiator.mention
        # if guess is correct: it has to name the other player. Both ids are in the game key, so
        # checking the key alone would pay out for guessing your own name.
        if guessKey[1] == otherUser.id:
            reward = await GBotFirebaseService.run(self.rewardGuesser, author, numOnlineParticipants)
            await context.send(embed = self.gameCard('🎉 You got them!', f"It was {otherUserMention} all along! You won {presentation.formatGCoin(reward)} GCoin!"))
            await otherUser.send(embed = self.gameCard("👀 You've been found!", 'They figured out it was you. Nicely played, the game is over.'))
        # if guess is not correct
        else:
            await context.send(embed = self.gameCard('❌ Wrong guess', "It wasn't them, and the mystery lives on. The game is over."))
            await otherUser.send(embed = self.gameCard('😏 They guessed wrong', 'Your secret is safe. The game is over.'))     

    async def refuseStart(self, context, author, deleteMsgs, description):
        # A slash reply can be private, so that is all it takes. A prefix reply cannot, so the channel
        # gets a neutral line that is deleted shortly and the reason goes to a DM.
        if isinstance(context, nextcord.Interaction):
            await presentation.sendError(context, description)
        else:
            deleteMsgs.append(await context.send('Who Dis not started.'))
            await presentation.sendError(author, description)

    async def reportStatus(self, context, deleteMsgs, text):
        # only a prefix reply is public, and so needs deleting. A private reply cannot be deleted.
        if isinstance(context, nextcord.Interaction):
            await presentation.sendReply(context, content = text, ephemeral = True)
        else:
            deleteMsgs.append(await context.send(text))

    def gameCard(self, title, description):
        return presentation.brandEmbed(title = title, description = description, feature = 'Who Dis')

    async def timeoutWhoDis(self, gameKey):
        initiator: nextcord.User = self.whoDisGames[gameKey]['initiator']
        randomUser: nextcord.User = self.whoDisGames[gameKey]['randomUser']
        self.whoDisGames.pop(gameKey)
        self.logger.info(f'Who Dis game with the following game-key timed out: {gameKey}')
        await self.notifyPlayers((initiator, randomUser), "⏰ Time's up", 'Nobody guessed in time, so the mystery lives on. The game is over.', gameKey)

    async def notifyPlayers(self, users, title, description, gameKey):
        # separately: one player's closed DMs must not cost the other player the notice
        for user in users:
            try:
                await user.send(embed = self.gameCard(title, description))
            except Exception as e:
                self.logger.error(f'Who Dis could not send {title!r} to user {user.id} for game {gameKey}: {e}')

    def rewardGuesser(self, author: nextcord.User, numOnlineParticipants):
        # update player's statistics
        leaderboards_queries.incrementUserNumValue(author.id, author.name, 'numWhoDisWins')
        # give initiator points
        dateTimeObj = datetime.now()
        date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")
        sender = { 'id': None, 'name': 'Who Dis' }
        receiver = { 'id': author.id, 'name': author.name }

        if numOnlineParticipants < self.NUM_PARTICIPANTS_FOR_MAX_REWARD:
            finalReward = utils.roundDecimalPlaces(Decimal(numOnlineParticipants) * self.BASE_REWARD_MULTIPLIER, 2)
        else:
            finalReward = self.MAX_REWARD_GCOIN

        gcoin_queries.performTransaction(finalReward, date, sender, receiver, '', 'Guessed User', False, False)
        return finalReward

    async def deletePublicWhoDisMessages(self, serverId, deleteMessages, channel: nextcord.TextChannel):
        self.logger.info(f'Deleting Who Dis messages in server {serverId}.')
        if deleteMessages != None and len(deleteMessages) > 0:
            try:
                await utils.purgePreviousMessages(deleteMessages, channel)
            except Exception as e:
                await utils.sendMessageToAdmins(self.client, serverId, f"There were public Who Dis messages that did not get deleted. Please make sure the bot has the 'Manage Messages' permission in common channels used for Who Dis commands.", self.logger)
                self.logger.error(f'Public Who Dis messages in server {serverId} failed to delete with the following error: {e}')

def setup(client: commands.Bot):
    client.add_cog(WhoDis(client))