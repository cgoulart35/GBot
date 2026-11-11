#region IMPORTS
import logging
import asyncio
import random
from types import SimpleNamespace
import nextcord
from nextcord.ext import commands, tasks
from nextcord.ext.commands.context import Context
from decimal import Decimal
from datetime import datetime, timedelta

from GBotDiscord.src import presentation
from GBotDiscord.src import strings
from GBotDiscord.src import utils
from GBotDiscord.src import predicates
from GBotDiscord.src import pagination
from GBotDiscord.src import server_setup
from GBotDiscord.src.help import guides
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.gcoin import gcoin_queries
from GBotDiscord.src.leaderboards import leaderboards_queries
from GBotDiscord.src.exceptions import WhoDisNotConfigured, CustomCommandOnCooldown
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.firebase import GBotFirebaseService
#endregion

WHODIS_BUTTON_PREFIX = 'whodis:'
WHODIS_END = 'end'
WHODIS_REPORT = 'report'
# the Who Dis card's, which name the server they act for and last until it's closed
WHODIS_START = 'start'
WHODIS_LEAVE = 'leave'
WHODIS_GUIDE = 'guide'
WHODIS_CLOSE = 'close'

class WhoDis(commands.Cog):

    # on the class, so /help's guide reads the same numbers the game pays out
    BASE_REWARD_MULTIPLIER = Decimal('50.00')
    MAX_REWARD_GCOIN = Decimal('1000000.00')
    NUM_PARTICIPANTS_FOR_MAX_REWARD = 20000

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()

        # how many of each player's latest messages a report from the game carries
        self.NUM_MESSAGES_TO_REPORT = 5

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
    @nextcord.slash_command(name = strings.WHODIS_NAME, description = strings.WHODIS_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isFeatureEnabledForServer('toggle_who_dis', True, True)
    async def whodisSlash(self,
                          interaction: nextcord.Interaction,
                          user = nextcord.SlashOption(
                            name = 'user',
                            required = False,
                            description = strings.WHODIS_USER_DESCRIPTION
                          )):
        await self.commonWhoDisCommand(interaction, interaction.user, user)

    @commands.command(name = strings.WHODIS_NAME, aliases = strings.WHODIS_ALIASES, brief = "- " + strings.WHODIS_BRIEF, description = strings.WHODIS_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_who_dis', True)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', True)
    @predicates.isGuildOrUserSubscribed()
    async def whodis(self, ctx: Context, user = None):
        await self.commonWhoDisCommand(ctx, ctx.author, user)

    async def commonWhoDisCommand(self, context, author, user):
        # a name guesses, and nothing opens the card
        if user is not None:
            if isinstance(context, Context) and context.guild is not None:
                # a typed guess in a server would tell the channel who someone is playing with
                await self.deletePublicWhoDisMessages(context.guild.id, [context.message], context.channel)
                await presentation.sendError(author, f'Sorry {author.mention}, please guess in this private message, so nobody else sees it.')
                return
            await self.commonDis(context, author, user)
        elif context.guild is None or isinstance(context, nextcord.Interaction):
            await self.openCard(context, author)
        else:
            await self.openCardFromChannel(context.message, author, context.guild)

    async def openCardFromChannel(self, message, member, guild):
        # Typed in a channel, where a 🔒 Open line saying who asked would tell their partner when the
        # game began. So the message goes and the card comes to their DMs, where the game is played.
        try:
            await message.delete()
        except nextcord.HTTPException:
            pass
        if await self.openCardInDms(guild, member):
            return True
        await message.channel.send(f"Sorry {member.mention}, GBot couldn't message you. Who Dis is played in DMs, so allow messages from this server's members, or use `/whodis`.")
        return False

    async def openCardInDms(self, guild, member):
        # the server's Who Dis card, in their DMs, its buttons acting for that server
        try:
            await self.openCard(SimpleNamespace(author = member, guild = None, send = member.send), member, guild)
        except nextcord.HTTPException:
            return False
        return True

    async def openCard(self, context, author, guild = None):
        # /whodis: start a game, leave, or read how it works. With a guild, it's that server's card sent
        # to their DMs, as there is no server to read from a press there.
        guild = guild or context.guild
        embed, view = self.card(author, guild, guild is not None and context.guild is None)
        # Its buttons last, so the card in their DMs starts the next game too. Only they see it, in a
        # private reply or their DMs, so it needs no owner.
        if isinstance(context, nextcord.Interaction):
            await context.send(embed = embed, view = view, ephemeral = True)
        else:
            await context.send(embed = embed, view = view)
        pagination.stopped(view)

    def card(self, author, guild, inDms):
        gameKey = self.getWhoDisGameKey(author.id)
        buttons = []
        if gameKey is not None:
            status = f"You're in a game, which ends <t:{self.gameEnds(gameKey)}:R>. Guess with `/whodis user:<their name>` in your DMs with GBot, or end it with 🛑 **End game** on its card there."
        elif guild is not None:
            status = f'You can start a new game {GBotPropertiesManager.WHODIS_COOLDOWN_MINUTES} minutes after starting the last.'
        else:
            status = 'Start a game from a server with GBot, with `/whodis` there.'
        if guild is not None:
            # never an End: a game ends from its own card, so a Start left here can't end one
            buttons.append(pagination.persistentButton('Start a game', '🕵️', nextcord.ButtonStyle.success, f'{WHODIS_BUTTON_PREFIX}{WHODIS_START}:{guild.id}'))
            buttons.append(pagination.persistentButton('Leave Who Dis', '🚪', pagination.NAV_STYLE, f'{WHODIS_BUTTON_PREFIX}{WHODIS_LEAVE}:{guild.id}'))
        buttons.append(pagination.persistentButton('How it works', '📖', pagination.NAV_STYLE, f'{WHODIS_BUTTON_PREFIX}{WHODIS_GUIDE}'))
        buttons.append(pagination.persistentButton(None, pagination.CustomButtonMenuPages.STOP, pagination.NAV_STYLE, f'{WHODIS_BUTTON_PREFIX}{WHODIS_CLOSE}'))
        title = f'❓ Who Dis? in {guild.name}' if inDms else '❓ Who Dis?'
        embed = presentation.brandEmbed(title = title, description = f"Get paired with a random member for an anonymous chat in DMs, then guess who they are.\n\n{status}", feature = 'Who Dis')
        return embed, pagination.persistentView(buttons)

    def gameEnds(self, gameKey):
        started = datetime.strptime(self.whoDisGames[gameKey]['startTime'], "%m/%d/%y %I:%M:%S %p")
        return int((started + timedelta(minutes = GBotPropertiesManager.WHODIS_TIMEOUT_MINUTES)).timestamp())

    def memberFor(self, interaction, guild):
        # a press in DMs carries a user, and starting needs the server's member: their status and roles
        if guild is None or interaction.guild is not None:
            return interaction.user
        return guild.get_member(interaction.user.id)

    async def startFromCard(self, interaction, guild):
        await interaction.response.defer(ephemeral = True)
        await predicates.recheck(interaction, feature = 'toggle_who_dis', privateMessagesAllowed = True, guild = guild)
        member = self.memberFor(interaction, guild)
        if member is None:
            await presentation.sendError(interaction, f"Sorry {interaction.user.mention}, you're no longer in {guild.name}.")
            return
        gameKey = self.getWhoDisGameKey(member.id)
        if gameKey is not None:
            await presentation.sendError(interaction, f"Sorry {member.mention}, you're already in a game, which ends <t:{self.gameEnds(gameKey)}:R>. End it from its card in your DMs.")
            return
        await self.commonWhoDis(interaction, member, guild)

    async def closeCard(self, interaction):
        await interaction.response.defer()
        try:
            # a private reply is deleted through the click, as only Discord's own Dismiss reaches it otherwise
            if interaction.message.flags.ephemeral:
                await interaction.delete_original_message()
            else:
                await interaction.message.delete()
        except nextcord.HTTPException:
            pass

    async def leave(self, interaction, guild = None):
        await interaction.response.defer(ephemeral = True)
        await predicates.recheck(interaction, feature = 'toggle_who_dis', guild = guild)
        member = self.memberFor(interaction, guild)
        if member is None:
            await presentation.sendError(interaction, f"Sorry {interaction.user.mention}, you're no longer in {guild.name}.")
            return
        await self.commonLeaveDis(interaction, member, guild)

    async def howItWorks(self, interaction):
        await interaction.response.send_message(embed = presentation.brandEmbed(title = '📖 How Who Dis works', description = guides.guideFor('Who Dis'), feature = 'Who Dis'), ephemeral = True)

    def gameButtons(self, gameKey):
        # on the game's own card in DMs. Their ids say which game, so an old card can't act on a newer
        # one, and they work after a restart, when they find the game is over.
        return pagination.persistentView([
            pagination.persistentButton('End game', '🛑', nextcord.ButtonStyle.secondary, f'{WHODIS_BUTTON_PREFIX}{WHODIS_END}:{gameKey}'),
            pagination.persistentButton('Report', '🚩', nextcord.ButtonStyle.danger, f'{WHODIS_BUTTON_PREFIX}{WHODIS_REPORT}:{gameKey}')])

    def gameOf(self, interaction, gameKey):
        # the game a card belongs to, if it's still on and the presser is in it
        return gameKey if gameKey in self.whoDisGames and str(interaction.user.id) in gameKey.split(':') else None

    @commands.Cog.listener()
    async def on_interaction(self, interaction: nextcord.Interaction):
        parts = pagination.persistentParts(interaction, WHODIS_BUTTON_PREFIX)
        if parts is None:
            return
        gameKey = ':'.join(parts[1:])
        try:
            if parts[0] in (WHODIS_START, WHODIS_LEAVE):
                guild = self.client.get_guild(int(parts[1]))
                if guild is None:
                    await presentation.sendError(interaction, f'Sorry {interaction.user.mention}, GBot is no longer in that server.')
                elif parts[0] == WHODIS_START:
                    await self.startFromCard(interaction, guild)
                else:
                    await self.leave(interaction, guild)
            elif parts[0] == WHODIS_GUIDE:
                await self.howItWorks(interaction)
            elif parts[0] == WHODIS_CLOSE:
                await self.closeCard(interaction)
            elif parts[0] == WHODIS_END:
                await self.endFromCard(interaction, gameKey)
            elif parts[0] == WHODIS_REPORT:
                async def submit(submitted, values):
                    await self.reportGame(submitted, values, gameKey)
                await interaction.response.send_modal(pagination.Form('Report this game', [pagination.Field('What happened? (optional)', placeholder = 'Anything the admins should know', long = True, required = False, maxLength = 1000)], submit))
        except Exception as e:
            await presentation.sendInteractionError(interaction, e)

    async def endFromCard(self, interaction, gameKey):
        await interaction.response.defer(ephemeral = True)
        gameKey = self.gameOf(interaction, gameKey)
        if gameKey is None:
            await presentation.sendReply(interaction, content = '🚪 This game is already over.', ephemeral = True)
        else:
            async with self.whoDisStartLock:
                await self.cancelWhoDis(interaction, True, interaction.user, [], gameKey)
        try:
            await interaction.message.edit(view = None)
        except nextcord.HTTPException:
            pass

    async def reportGame(self, interaction, values, gameKey):
        # the other player's last messages here go to that server's admins, through Config's report
        await interaction.response.defer(ephemeral = True, with_message = True)
        gameKey = self.gameOf(interaction, gameKey)
        if gameKey is None:
            await presentation.sendError(interaction, 'This game is over, so its messages are gone. To report someone in a server, right-click their message, then **Apps → Report to admins**.', feature = 'Who Dis')
            return
        game = self.whoDisGames[gameKey]
        isInitiator = game['initiator'].id == interaction.user.id
        reported = game['randomUser'] if isInitiator else game['initiator']
        messages = game['randomUserMessages'] if isInitiator else game['initiatorMessages']
        config = self.client.get_cog('Config')
        if await config.fileReport(game['guild'], interaction.user, reported, 'a Who Dis game', messages, values[0]):
            await presentation.sendReply(interaction, content = '🚩 Sent to the admins of that server. Thanks for letting them know.', ephemeral = True)
        else:
            await presentation.sendError(interaction, "This report wasn't sent, as that server has no admin channel GBot can post in.", feature = 'Who Dis')

    async def commonWhoDis(self, context, author: nextcord.Member, guild = None):
        # guild: the server a card in DMs acts for
        guild = guild or context.guild
        authorId = author.id
        authorMention = author.mention
        deleteMsgs = []

        # check to see if sent in a private message
        isPrivateMessage = guild is None

        # bind the above before the try, so an unexpected failure inside it (a deferral that
        # fails, say) surfaces as itself instead of as UnboundLocalError from the finally
        try:
            # private, because who started a game is the secret the whole mini-game rests on
            await presentation.deferIfSlash(context, ephemeral = True)

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
                            await self.refuseStart(context, author, deleteMsgs, f"Sorry {authorMention}, you need to be online to start Who Dis games.")
                            return

                        # Every refusal comes before opting them in, so a refused Start changes nothing:
                        # after a Leave, a Start in the cooldown must not quietly rejoin them.
                        # check to see if author is currently in cooldown
                        authorIdStr = str(authorId)
                        if (authorIdStr in self.whoDisCooldown):
                            timeStartedStr = self.whoDisCooldown[authorIdStr]
                            timeStarted = datetime.strptime(timeStartedStr, "%m/%d/%y %I:%M:%S %p")
                            timeCooldownEnd = timeStarted + timedelta(minutes = GBotPropertiesManager.WHODIS_COOLDOWN_MINUTES)
                            timeLeftDelta = timeCooldownEnd - datetime.now()
                            if isinstance(context, Context):
                                deleteMsgs.append(await context.send('Who Dis not started.'))
                            raise CustomCommandOnCooldown(timeLeftDelta.total_seconds(), True, "to start another Who Dis game.")

                        randomUserData = await self.getRandomWhoDisUser(authorId, guild, whoDisRole)
                        if randomUserData[0] is None:
                            await self.refuseStart(context, author, deleteMsgs, f'Sorry {authorMention}, there are currently no users available for Who Dis.')
                            return

                        # check to see if author is assigned who dis role
                        joined = False
                        if not utils.isUserAssignedRole(author, whoDisRole.id):
                            # if user is not assigned the who dis consent role, assign it
                            problem = server_setup.roleProblem(guild, whoDisRole)
                            if problem is not None:
                                await self.refuseStart(context, author, deleteMsgs, f"Sorry {authorMention}, GBot can't give out this server's Who Dis role yet. The admins have been told how to fix it.")
                                await self.reportRoleProblem(serverId, authorMention, problem)
                                return
                            if not await utils.addRoleToUser(author, whoDisRole):
                                await self.refuseStart(context, author, deleteMsgs, f"Sorry {authorMention}, there was a problem opting you into Who Dis in **{guild.name}**.")
                                await utils.sendMessageToAdmins(self.client, serverId, f"{authorMention}'s whoDis command failed as there was a problem assigning them the {whoDisRole.mention} role.", self.logger)
                                self.logger.error(f'Who Dis game failed in server {serverId} due to error assigning user {authorId} role {whoDisRole.id}.')
                                return
                            joined = True

                        if await self.startWhoDis(author, randomUserData[0], randomUserData[1], guild):
                            await self.reportStart(context, author, deleteMsgs, guild, joined)
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

    async def commonLeaveDis(self, context, author: nextcord.Member, guild = None):
        # unassign role and send message
        try:
            guild = guild or context.guild
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
                problem = server_setup.roleProblem(guild, whoDisRole)
                if problem is not None:
                    await presentation.sendError(context, f"Sorry {authorMention}, GBot can't take this server's Who Dis role away yet. The admins have been told how to fix it.")
                    await self.reportRoleProblem(serverId, authorMention, problem)
                    return
                await author.remove_roles(whoDisRole)
                # leaving ends their game here too, as End would: the other player is told they left
                ended = False
                async with self.whoDisStartLock:
                    gameKey = self.getWhoDisGameKey(authorId)
                    if gameKey is not None and self.whoDisGames[gameKey]['guild'].id == guild.id:
                        await self.cancelWhoDis(context, True, author, [], gameKey, leaving = True)
                        ended = True
                await presentation.sendReply(context, content = f"👋 You've left Who Dis in **{guild.name}**{', and your game is over' if ended else ''}.", ephemeral = True)
            else:
                await presentation.sendError(context, f"Sorry {authorMention}, you're not in Who Dis in **{guild.name}**.")
        except WhoDisNotConfigured:
            await presentation.sendError(context, f'Sorry {authorMention}, Who Dis is not configured in this server.')
            await utils.sendMessageToAdmins(self.client, serverId, f"{authorMention}'s whoDis command failed as there is currently no role configured for Who Dis.", self.logger)
            self.logger.error(f'Who Dis game not allowed in server {serverId} due to not being configured.')

    async def reportRoleProblem(self, serverId, authorMention, problem):
        await utils.sendMessageToAdmins(self.client, serverId, f"{authorMention} couldn't join or leave Who Dis games. {problem}", self.logger)
        self.logger.error(f'Who Dis role problem in server {serverId}: {problem}')

    async def commonDis(self, context, author, user: str):
        # private, as the guess names who someone thinks they're playing with
        await presentation.deferIfSlash(context, ephemeral = True)

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
        ends = int((dateTimeNow + timedelta(minutes = GBotPropertiesManager.WHODIS_TIMEOUT_MINUTES)).timestamp())
        card = self.gameCard('🕵️ New message... who dis?', f"Someone mysterious from `{guild.name}` just slid into your DMs. Chat here, then guess who with `/whodis user:<their name>`. You get one guess each.\n\n⏳ Ends <t:{ends}:R>")
        buttons = self.gameButtons(gameKey)
        try:
            await initiator.send(embed = card, view = buttons)
        except nextcord.HTTPException as e:
            self.logger.info(f'Who Dis game not started in server {guild.id} as initiating user {initiatorId} could not be messaged: {e}')
            pagination.stopped(buttons)
            return False
        try:
            await randomUser.send(embed = card, view = buttons)
        except nextcord.HTTPException as e:
            self.logger.info(f'Who Dis game not started in server {guild.id} as random user {randomUserId} could not be messaged: {e}')
            await self.notifyPlayers((initiator,), '🚪 Game cancelled', 'The other player can not be messaged right now.', gameKey, guild)
            pagination.stopped(buttons)
            return False
        pagination.stopped(buttons)
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

    async def cancelWhoDis(self, context, isPrivateMessage, author, deleteMsgs, gameKey, leaving = False):
        # leaving: they left Who Dis, which ends their game too, and its reply says so instead
        initiator: nextcord.User = self.whoDisGames[gameKey]['initiator']
        randomUser: nextcord.User = self.whoDisGames[gameKey]['randomUser']
        guild = self.whoDisGames[gameKey]['guild']
        
        self.whoDisGames.pop(gameKey)
        self.logger.info(f'Who Dis game with the following game-key cancelled: {gameKey}')

        # if not sent in a private message, delete replies and original msg (if context) and just reponse (if interaction)
        if not leaving:
            if isPrivateMessage:
                await self.sendEnding(context, '🚪 Game cancelled', 'You cancelled the game.', guild)
            else:
                await self.sendEnding(author, '🚪 Game cancelled', 'You cancelled the game.', guild)
                # a press's card shows the game is over, so only a typed end says so in the channel
                if isinstance(context, Context):
                    deleteMsgs.append(await context.send('Who Dis cancelled.'))
        
        await self.sendEnding(randomUser if author.id == initiator.id else initiator, '🚪 Game cancelled', 'The other player left. No hard feelings.', guild)

    async def guessWhoDis(self, context, author, guessKey, gameKey):
        # guess key is list of 2 user IDs
        # game keys look like '012345678910111213:131211109876543210'
        initiator: nextcord.User = self.whoDisGames[gameKey]['initiator']
        randomUser: nextcord.User = self.whoDisGames[gameKey]['randomUser']
        numOnlineParticipants = self.whoDisGames[gameKey]['numOnlineParticipants']
        guild = self.whoDisGames[gameKey]['guild']

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
            await self.sendEnding(context, '🎉 You got them!', f"It was {otherUserMention} all along! You won {presentation.formatGCoin(reward)} GCoin!", guild)
            await self.sendEnding(otherUser, "👀 You've been found!", 'They figured out it was you. Nicely played, the game is over.', guild)
        # if guess is not correct
        else:
            await self.sendEnding(context, '❌ Wrong guess', "It wasn't them, and the mystery lives on. The game is over.", guild)
            await self.sendEnding(otherUser, '😏 They guessed wrong', 'Your secret is safe. The game is over.', guild)

    async def reportStart(self, context, author, deleteMsgs, guild, joined):
        # One private reply to the press, whatever it has to say: that they joined, and where the game
        # is. Pressed in DMs, the game card arrives right below and says itself.
        joinedText = f"❓ You've joined Who Dis in **{guild.name}**. Please follow its rules, and leave any time from `/whodis`."
        if isinstance(context, Context):
            # typed, where a reply would be public: the channel gets a line deleted shortly, and joining a DM
            deleteMsgs.append(await context.send('Who Dis starting...'))
            if joined:
                await author.send(joinedText)
        elif context.guild is not None:
            await presentation.sendReply(context, content = f"{joinedText} Your game is in your DMs." if joined else "🕵️ Game started. It's in your DMs with GBot.", ephemeral = True)
        elif joined:
            await presentation.sendReply(context, content = joinedText, ephemeral = True)

    async def refuseStart(self, context, author, deleteMsgs, description):
        # A slash reply can be private, so that is all it takes. A prefix reply cannot, so the channel
        # gets a neutral line that is deleted shortly and the reason goes to a DM.
        if isinstance(context, nextcord.Interaction):
            await presentation.sendError(context, description)
        else:
            deleteMsgs.append(await context.send('Who Dis not started.'))
            await presentation.sendError(author, description)

    def gameCard(self, title, description):
        return presentation.brandEmbed(title = title, description = description, feature = 'Who Dis')

    async def sendEnding(self, target, title, description, guild = None):
        # A card saying a game is over, with 🕵️ Play again for its server: where a game ends is where
        # the next one starts. Its button lasts, as the Who Dis card's Start does, and is that same Start.
        if guild is None:
            await target.send(embed = self.gameCard(title, description))
            return
        view = pagination.persistentView([pagination.persistentButton('Play again', '🕵️', nextcord.ButtonStyle.success, f'{WHODIS_BUTTON_PREFIX}{WHODIS_START}:{guild.id}')])
        try:
            await target.send(embed = self.gameCard(title, description), view = view)
        finally:
            pagination.stopped(view)

    async def timeoutWhoDis(self, gameKey):
        initiator: nextcord.User = self.whoDisGames[gameKey]['initiator']
        randomUser: nextcord.User = self.whoDisGames[gameKey]['randomUser']
        guild = self.whoDisGames[gameKey]['guild']
        self.whoDisGames.pop(gameKey)
        self.logger.info(f'Who Dis game with the following game-key timed out: {gameKey}')
        await self.notifyPlayers((initiator, randomUser), "⏰ Time's up", 'Nobody guessed in time, so the mystery lives on. The game is over.', gameKey, guild)

    async def notifyPlayers(self, users, title, description, gameKey, guild = None):
        # separately: one player's closed DMs must not cost the other player the notice. No guild, no
        # Play again, as when GBot has left the server.
        for user in users:
            try:
                await self.sendEnding(user, title, description, guild)
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