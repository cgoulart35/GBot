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
from GBotDiscord.src.exceptions import EnforceSenderFundsError
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

class Storms(commands.Cog):

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()

        self.UMBRELLA_REWARD_GCOIN = Decimal('0.25')
        self.GUESS_REWARD_GCOIN = Decimal('1.00')

        self.stormStates = {}
        self.stormLocks = {}
        servers = config_queries.getAllServers()
        for serverId in servers.keys():
            self.stormLocks[serverId] = threading.Lock()
            self.generateNewStorm(serverId)

    # Events
    @commands.Cog.listener()
    async def on_guild_join(self, guild: nextcord.Guild):
        serverId = str(guild.id)
        self.logger.info(f'Adding server storm state for guild {serverId} ({guild.name}).')
        self.stormLocks[serverId] = threading.Lock()
        self.generateNewStorm(serverId)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: nextcord.Guild):
        serverId = str(guild.id)
        self.logger.info(f'Removing server storm state for guild {serverId} ({guild.name}).')
        self.stormLocks.pop(serverId)
        self.stormStates.pop(serverId)

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            self.storm_invoker.start()
        except RuntimeError:
            self.logger.info('storm_invoker task is already launched and is not completed.')

    # Tasks
    @tasks.loop(seconds=1)
    async def storm_invoker(self):
        currentTime = datetime.now()
        # check all server storms
        for serverId, stormState in self.stormStates.items():
            stormStateNum = stormState['stormState']
            triggerTime = datetime.strptime(stormState['triggerTime'], "%m/%d/%y %I:%M:%S %p")

            # if storm is not running
            if stormStateNum == 0:

                # if it is time for the storm, check to see if storms configured
                if currentTime >= triggerTime:

                    # if storms are configured, start the storm in the channel
                    isConfigured = await self.isServerStormsConfigured(serverId)
                    if isConfigured[0]:
                        stormStateNum = stormState['stormState']
                        await self.startStorm(serverId, isConfigured[1])
                        
                    # if storms are not configured, delay it by generating a new storm
                    else:
                        self.logger.info(f'Storm skipped in server {serverId} due to not being configured.')
                        self.generateNewStorm(serverId)                        

            # if storm is running
            else:
                # if its been 5 minutes & no 5 minute warning has been given, check to see if storms configured
                if not stormState['fiveMinuteWarning'] and currentTime >= triggerTime + timedelta(minutes = 5):
                    stormState['fiveMinuteWarning'] = True

                    # if storms are configured, send 5 minute warning
                    isConfigured = await self.isServerStormsConfigured(serverId)
                    if isConfigured[0]:
                        await utils.sendDiscordEmbed(isConfigured[1], "🌦️ 🌦️ 🌦️ **5 MINUTES REMAINING!** 🌦️ 🌦️ 🌦️", None, nextcord.Color.orange(), None, None, None, GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS)
                        
                # if its been 9 minutes & no 1 minute warning has been given, check to see if storms configured
                if not stormState['oneMinuteWarning'] and currentTime >= triggerTime + timedelta(minutes = 9):
                    stormState['oneMinuteWarning'] = True

                    # if storms are configured, send 1 minute warning
                    isConfigured = await self.isServerStormsConfigured(serverId)
                    if isConfigured[0]:                  
                        await utils.sendDiscordEmbed(isConfigured[1], "🌦️ 🌦️ 🌦️ **1 MINUTE REMAINING!** 🌦️ 🌦️ 🌦️", None, nextcord.Color.orange(), None, None, None, GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS)
                        
                # if storm has been running for 10 minutes, try to end it
                if currentTime >= triggerTime + timedelta(minutes = 10):
                    await self.stormTimeout(serverId) 

    # Commands
    @nextcord.slash_command(name = strings.UMBRELLA_NAME, description = strings.UMBRELLA_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_storms', False, True)
    async def umbrellaSlash(self, interaction: nextcord.Interaction):
        await self.commonUmbrella(interaction, interaction.user)

    @commands.command(aliases = strings.UMBRELLA_ALIASES, brief = "- " + strings.UMBRELLA_BRIEF, description = strings.UMBRELLA_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_storms', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def umbrella(self, ctx: Context):
        await self.commonUmbrella(ctx, ctx.author)

    async def commonUmbrella(self, context, author):
        try:
            # obtain lock for server's storm
            serverId = str(context.guild.id)
            authorMention = author.mention
            lock: threading.Lock = self.stormLocks[serverId]
            lock.acquire()
            if self.stormStates[serverId]['stormState'] == 1:
                # give player points for starting storm
                authorId = author.id
                dateTimeObj = datetime.now()
                date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")
                sender = { 'id': None, 'name': 'Storms' }
                receiver = { 'id': authorId, 'name': author.name }
                gcoin_queries.performTransaction(self.UMBRELLA_REWARD_GCOIN, date, sender, receiver, '', 'Started Storm', False, False)

                # send new message that storm started
                message = f"""{utils.idToUserStr(authorId)}, you put up your umbrella first and earned {self.UMBRELLA_REWARD_GCOIN} GCoin!

    **First to guess the winning number correctly between 1 and 200 earns GCoin!**

    - Use '**.guess [number]**' to make a guess with a winning reward of {self.GUESS_REWARD_GCOIN} GCoin!
    - Use '**.bet [gcoin] [number]**' to make a guess. If you win, you earn the amount of GCoin bet within your wallet. If you lose, you lose GCoin.
    - Use '**.wallet**' to show how much GCoin you have in your wallet!

    - GCoin earned is multiplied if you guess within 4 guesses!"""
                await utils.sendDiscordEmbed(context, "⛈️ ⛈️ ⛈️ **STORM STARTED** ⛈️ ⛈️ ⛈️", message, nextcord.Color.orange(), None, None, None, GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS)

                # update state to 2
                self.stormStates[serverId]['stormState'] = 2
            elif self.stormStates[serverId]['stormState'] == 0:
                # no active storm
                await context.send(f'Sorry {authorMention}, there is currently no active Storm.', delete_after = GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS)
            elif self.stormStates[serverId]['stormState'] == 2:
                # storm already started
                await context.send(f'Sorry {authorMention}, the Storm has already been started!', delete_after = GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS)
        finally:
            lock.release()
            if isinstance(context, Context):
                await context.message.delete(delay = GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS)

    @nextcord.slash_command(name = strings.GUESS_NAME, description = strings.GUESS_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_storms', False, True)
    async def guessSlash(self,
                         interaction: nextcord.Interaction,
                         number: int = nextcord.SlashOption(
                            name = "number",
                            description = strings.GUESS_NUMBER_DESCRIPTION)
                         ):
        await self.commonGuess(interaction, interaction.user, number)

    @commands.command(aliases = strings.GUESS_ALIASES, brief = "- " + strings.GUESS_BRIEF, description = strings.GUESS_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_storms', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def guess(self, ctx: Context, number: int):
        await self.commonGuess(ctx, ctx.author, number)

    async def commonGuess(self, context, author, number: int):
        try:
            # obtain lock for server's storm
            serverId = str(context.guild.id)
            authorMention = author.mention
            lock: threading.Lock = self.stormLocks[serverId]
            lock.acquire()
            if self.stormStates[serverId]['stormState'] == 2:
                await self.guessNumber(context, author, number)
            else:
                # no active storm
                await context.send(f'Sorry {authorMention}, there is currently no active Storm.', delete_after = GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS)
        finally:
            lock.release()
            if isinstance(context, Context):
                await context.message.delete(delay = GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS)

    @nextcord.slash_command(name = strings.BET_NAME, description = strings.BET_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_storms', False, True)
    async def betSlash(self,
                       interaction: nextcord.Interaction,
                       gcoin = nextcord.SlashOption(
                            name = "gcoin",
                            description = strings.BET_GCOIN_DESCRIPTION),
                       number: int = nextcord.SlashOption(
                            name = "number",
                            description = strings.BET_NUMBER_DESCRIPTION)
                       ):
        await self.commonBet(interaction, interaction.user, Decimal(str(gcoin)), number)

    @commands.command(aliases = strings.BET_ALIASES, brief = "- " + strings.BET_BRIEF, description = strings.BET_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_storms', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def bet(self, ctx: Context, gcoin: Decimal, number: int):
        await self.commonBet(ctx, ctx.author, gcoin, number)

    async def commonBet(self, context, author, gcoin: Decimal, number: int):
        try:
            # obtain lock for server's storm
            serverId = str(context.guild.id)
            authorMention = author.mention
            lock: threading.Lock = self.stormLocks[serverId]
            lock.acquire()
            if self.stormStates[serverId]['stormState'] == 2:
                await self.guessNumber(context, author, number, utils.roundDecimalPlaces(gcoin, 2))
            else:
                # no active storm
                await context.send(f'Sorry {authorMention}, there is currently no active Storm.', delete_after = GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS)
        except EnforceSenderFundsError:
            await context.send(f'Sorry {author.mention}, you have insufficient funds.')
        finally:
            lock.release()
            if isinstance(context, Context):
                await context.message.delete(delay = GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS)

    async def guessNumber(self, context, author, number: int, gcoin: Decimal = None):
        dateTimeObj = datetime.now()
        date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")
        serverId = str(context.guild.id)
        authorId = str(author.id)
        authorName = author.name
        authorMention = author.mention

        # validate that user has the money that they are betting
        if gcoin != None and gcoin > gcoin_queries.getUserBalance(authorId):
            raise EnforceSenderFundsError
        # update player's guess count
        self.recordGuessAttempt(serverId, authorId)
        # if correct guess
        winningNumber = self.stormStates[serverId]['winningNumber']
        if winningNumber == number:
            # if bet made use specified points, otherwise use self.GUESS_REWARD_GCOIN (apply multipier)
            sender = { 'id': None, 'name': 'Storms' }
            receiver = { 'id': authorId, 'name': authorName }
            multiplierInfo = self.applyMultiplier(serverId, authorId, (self.GUESS_REWARD_GCOIN if gcoin == None else gcoin))
            gcoin_queries.performTransaction(multiplierInfo[0], date, sender, receiver, '', (f'Won Guess {multiplierInfo[1]}' if gcoin == None else f'Won Bet {multiplierInfo[1]}'), False, False)
            # send new message that storm ended
            await self.completeStorm(context, serverId, authorMention, multiplierInfo)
            return
        # if incorrect guess
        elif gcoin != None:
            # take away points player bet
            receiver = { 'id': None, 'name': 'Storms' }
            sender = { 'id': authorId, 'name': authorName }
            gcoin_queries.performTransaction(gcoin, date, sender, receiver, 'Lost Bet', '', False, True)
            message = f'Sorry {authorMention}, you guessed incorrectly and lost {gcoin} GCoin.'
        else:
            message = f'Sorry {authorMention}, you guessed incorrectly.'
        await context.send(message + ' The winning number is' + (' greater than ' if number < winningNumber else ' less than ') + str(number) + '.', delete_after = GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS)

    def generateNewStorm(self, serverId, startNow = None):
        if startNow != None and startNow:
            dateTimeObj = datetime.now()
        else:
            randomSeconds = random.randint(GBotPropertiesManager.STORMS_MIN_TIME_BETWEEN_SECONDS, GBotPropertiesManager.STORMS_MAX_TIME_BETWEEN_SECONDS)
            dateTimeObj = datetime.now() + timedelta(seconds = randomSeconds)
        date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")
        serverStormState = {
            'stormState': 0,
            'triggerTime': date,
            'winningNumber': random.randint(1, 200),
            'attemptsMap': {},
            'fiveMinuteWarning': False,
            'oneMinuteWarning': False
        }
        self.stormStates[serverId] = serverStormState
        self.logger.info(f'Storm scheduled in server {serverId} to start at {date}.')

    async def startStorm(self, serverId, channel: nextcord.TextChannel):
        guild = await self.client.fetch_guild(serverId)
        if guild.icon != None:
            thumbnailUrl = guild.icon.url
        else:
            thumbnailUrl = None 

        # send start message to channel with instructions
        await utils.sendDiscordEmbed(channel, "🌧️ ⛈️ ☂️ **STORM INCOMING** ☂️ ⛈️ 🌧️", f"First to use '**.umbrella**' starts the Storm and earns {self.UMBRELLA_REWARD_GCOIN} GCoin! 10 minute countdown starting now!", nextcord.Color.orange(), None, None, thumbnailUrl, GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS)
        # change state of storm to 1
        self.stormStates[serverId]['stormState'] = 1
        self.logger.info(f'Storm started in server {serverId}.')

    async def stormTimeout(self, serverId):
        try:
            # obtain storm lock command and call generateNewStorm
            lock: threading.Lock = self.stormLocks[serverId]
            lock.acquire()
            self.logger.info(f'Storm timed out in server {serverId}.')
            self.generateNewStorm(serverId)
            # if server is still configured for storms, send storm over message
            isConfigured = await self.isServerStormsConfigured(serverId)
            if isConfigured[0]:
                await utils.sendDiscordEmbed(isConfigured[1], "🌞 🌞 🌞 **STORM OVER** 🌞 🌞 🌞", None, nextcord.Color.orange(), None, None, None, GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS)
        finally:
            lock.release()

    async def completeStorm(self, context, serverId, authorMention, multiplierInfo):
        self.logger.info(f'Storm completed in server {serverId}.')
        # update state to 0 by generating a new storm
        self.generateNewStorm(serverId)
        # send storm complete message to storm channel
        isConfigured = await self.isServerStormsConfigured(serverId)
        if isConfigured[0]:
            await context.send(f'Congratulations {authorMention}, you guessed correctly and earned {multiplierInfo[0]} points! ({multiplierInfo[1]} applied)', delete_after = GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS)
            await utils.sendDiscordEmbed(isConfigured[1], "🌞 🌞 🌞 **STORM OVER** 🌞 🌞 🌞", None, nextcord.Color.orange(), None, None, None, GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS)

    def getPlayerGuessCount(self, serverId, userId):
        if userId in self.stormStates[serverId]['attemptsMap']:
            guessCount = self.stormStates[serverId]['attemptsMap'][userId]
        else:
            guessCount = 0
        return guessCount

    def recordGuessAttempt(self, serverId, userId):
        guessCount = self.getPlayerGuessCount(serverId, userId)
        self.stormStates[serverId]['attemptsMap'][userId] = guessCount + 1

    def applyMultiplier(self, serverId, userId, reward):
        guessCount = self.getPlayerGuessCount(serverId, userId)
        multiplier = Decimal('1')
        if guessCount == 1:
            multiplier = Decimal('10')
        elif guessCount == 2:
            multiplier = Decimal('5')
        elif guessCount == 3:
            multiplier = Decimal('2.5')
        elif guessCount == 4:
            multiplier = Decimal('1.25')
        finalReward = utils.roundDecimalPlaces(reward * multiplier, 2)
        return (finalReward, f'x{multiplier}')

    async def isServerStormsConfigured(self, serverId):
        isStormsEnabled = config_queries.getServerValue(serverId, 'toggle_storms')
        channelId = config_queries.getServerValue(serverId, 'channel_storms')
        channel: nextcord.TextChannel = await self.client.fetch_channel(int(channelId))
        return (isStormsEnabled and channelId != None and channel != None, channel)

def setup(client: commands.Bot):
    client.add_cog(Storms(client))