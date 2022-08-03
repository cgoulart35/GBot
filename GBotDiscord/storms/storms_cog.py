#region IMPORTS
import os
import logging
import threading
import random
import nextcord
from nextcord.ext import commands, tasks
from nextcord.ext.commands.context import Context
from decimal import Decimal
from datetime import datetime, timedelta

from GBotDiscord import utils
from GBotDiscord import predicates
from GBotDiscord.config import config_queries
from GBotDiscord.gcoin import gcoin_queries
from GBotDiscord.exceptions import EnforceSenderFundsError
#endregion

class Storms(commands.Cog):

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()

        self.STORMS_MIN_TIME_BETWEEN_SECONDS = int(os.getenv("STORMS_MIN_TIME_BETWEEN_SECONDS"))
        self.STORMS_MAX_TIME_BETWEEN_SECONDS = int(os.getenv("STORMS_MAX_TIME_BETWEEN_SECONDS"))
        self.STORMS_DELETE_MESSAGES_AFTER_SECONDS = int(os.getenv("STORMS_DELETE_MESSAGES_AFTER_SECONDS"))
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
        # check all server storms to see if it is time to start
        for serverId, stormState in self.stormStates.items():
            isStormsEnabled = config_queries.getServerValue(serverId, 'toggle_storms')
            channelId = config_queries.getServerValue(serverId, 'channel_storms')
            triggerTime = datetime.strptime(stormState['triggerTime'], "%m/%d/%y %I:%M:%S %p")

            # if storms are configured
            if isStormsEnabled and channelId != None:
                stormStateNum = stormState['stormState']
                channel: nextcord.TextChannel = await self.client.fetch_channel(int(channelId))

                # if storm is not running
                if stormStateNum == 0:
                    # if it is time for the storm, start the storm in the channel
                    if currentTime >= triggerTime:
                        await self.startStorm(serverId, channel)
                # if storm is running
                else:
                    # if its been 5 minutes & no 5 minute warning has been given, send 5 minute warning
                    if not stormState['fiveMinuteWarning'] and currentTime >= triggerTime + timedelta(minutes = 5):
                        await utils.sendDiscordEmbed(channel, "🌦️ 🌦️ 🌦️ **5 MINUTES REMAINING!** 🌦️ 🌦️ 🌦️", None, nextcord.Color.orange(), None, None, None, self.STORMS_DELETE_MESSAGES_AFTER_SECONDS)
                        stormState['fiveMinuteWarning'] = True
                    # if its been 9 minutes & no 1 minute warning has been given, send 1 minute warning
                    if not stormState['oneMinuteWarning'] and currentTime >= triggerTime + timedelta(minutes = 9):
                        await utils.sendDiscordEmbed(channel, "🌦️ 🌦️ 🌦️ **1 MINUTE REMAINING!** 🌦️ 🌦️ 🌦️", None, nextcord.Color.orange(), None, None, None, self.STORMS_DELETE_MESSAGES_AFTER_SECONDS)
                        stormState['oneMinuteWarning'] = True
                    # if storm has been running for 10 minutes, end it
                    if currentTime >= triggerTime + timedelta(minutes = 10):
                        await self.stormTimeout(serverId, channel)
            # if storms are not configured, keep delaying
            else:
                # if it is time for the unconfigured storm, delay it by generating a new storm
                if currentTime >= triggerTime:
                    self.logger.info(f'Storm skipped in server {serverId} due to not being configured.')
                    self.generateNewStorm(serverId)

    # Commands
    @commands.command(aliases=['u'], brief = "- Start the incoming Storm and earn 0.25 GCoin.", description = "Start the incoming Storm and earn 0.25 GCoin.")
    @predicates.isFeatureEnabledForServer('toggle_storms')
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def umbrella(self, ctx: Context):
        try:
            # obtain lock for server's storm
            serverId = str(ctx.guild.id)
            lock: threading.Lock = self.stormLocks[serverId]
            lock.acquire()
            if self.stormStates[serverId]['stormState'] == 1:
                # give player points for starting storm
                authorId = ctx.author.id
                dateTimeObj = datetime.now()
                date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")
                sender = { 'id': None, 'name': 'Storms' }
                receiver = { 'id': authorId, 'name': ctx.author.name }
                gcoin_queries.performTransaction(self.UMBRELLA_REWARD_GCOIN, date, sender, receiver, '', 'Started Storm', False, False)

                # send new message that storm started
                message = f"""{utils.idToUserStr(authorId)}, you put up your umbrella first and earned {self.UMBRELLA_REWARD_GCOIN} GCoin!

    **First to guess the winning number correctly between 1 and 200 earns GCoin!**

    - Use '**.guess [number]**' to make a guess with a winning reward of {self.GUESS_REWARD_GCOIN} GCoin!
    - Use '**.bet [gcoin] [number]**' to make a guess. If you win, you earn the amount of GCoin bet within your wallet. If you lose, you lose GCoin.
    - Use '**.wallet**' to show how much GCoin you have in your wallet!

    - GCoin earned is multiplied if you guess within 4 guesses!"""
                await utils.sendDiscordEmbed(ctx.channel, "⛈️ ⛈️ ⛈️ **STORM STARTED** ⛈️ ⛈️ ⛈️", message, nextcord.Color.orange(), None, None, None, self.STORMS_DELETE_MESSAGES_AFTER_SECONDS)

                # update state to 2
                self.stormStates[serverId]['stormState'] = 2
        finally:
            lock.release()
            await ctx.message.delete(delay = self.STORMS_DELETE_MESSAGES_AFTER_SECONDS)

    @commands.command(aliases=['g'], brief = "- Make a guess with a winning reward of 1.00 GCoin.", description = "Make a guess with a winning reward of 1.00 GCoin. Multiplier applied for guesses made in 4 attempts or less.")
    @predicates.isFeatureEnabledForServer('toggle_storms')
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def guess(self, ctx: Context, number: int):
        try:
            # obtain lock for server's storm
            serverId = str(ctx.guild.id)
            lock: threading.Lock = self.stormLocks[serverId]
            lock.acquire()
            if self.stormStates[serverId]['stormState'] == 2:
                await self.guessNumber(ctx, number)
        finally:
            lock.release()
            await ctx.message.delete(delay = self.STORMS_DELETE_MESSAGES_AFTER_SECONDS)

    @commands.command(aliases=['b'], brief = "- Make a guess. If you win, you earn the amount of points bet within your wallet. If you lose, you lose those points.", description = "Make a guess. If you win, you earn the amount of points bet within your wallet. If you lose, you lose those points. Multiplier applied for guesses made in 4 attempts or less.")
    @predicates.isFeatureEnabledForServer('toggle_storms')
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def bet(self, ctx: Context, gcoin: Decimal, number: int):
        try:
            # obtain lock for server's storm
            serverId = str(ctx.guild.id)
            lock: threading.Lock = self.stormLocks[serverId]
            lock.acquire()
            if self.stormStates[serverId]['stormState'] == 2:
                await self.guessNumber(ctx, number, utils.roundDecimalPlaces(gcoin, 2))
        except EnforceSenderFundsError:
            await ctx.send(f'Sorry {ctx.author.mention}, you have insufficient funds.')
        finally:
            lock.release()
            await ctx.message.delete(delay = self.STORMS_DELETE_MESSAGES_AFTER_SECONDS)

    async def guessNumber(self, ctx: Context, number: int, gcoin: Decimal = None):
        dateTimeObj = datetime.now()
        date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")
        serverId = str(ctx.guild.id)
        authorId = str(ctx.author.id)
        authorName = ctx.author.name
        authorMention = ctx.author.mention

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
            await self.completeStorm(serverId, authorMention, multiplierInfo)
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
        await ctx.send(message + ' The winning number is' + (' greater than ' if number < winningNumber else ' less than ') + str(number) + '.', delete_after = self.STORMS_DELETE_MESSAGES_AFTER_SECONDS)

    def generateNewStorm(self, serverId):
        randomSeconds = random.randint(self.STORMS_MIN_TIME_BETWEEN_SECONDS, self.STORMS_MAX_TIME_BETWEEN_SECONDS)
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
        await utils.sendDiscordEmbed(channel, "🌧️ ⛈️ ☂️ **STORM INCOMING** ☂️ ⛈️ 🌧️", f"First to use '**.umbrella**' starts the Storm and earns {self.UMBRELLA_REWARD_GCOIN} GCoin! 10 minute countdown starting now!", nextcord.Color.orange(), None, None, thumbnailUrl, self.STORMS_DELETE_MESSAGES_AFTER_SECONDS)
        # change state of storm to 1
        self.stormStates[serverId]['stormState'] = 1
        self.logger.info(f'Storm started in server {serverId}.')

    async def stormTimeout(self, serverId, channel: nextcord.TextChannel):
        try:
            # obtain storm lock command and call generateNewStorm
            lock: threading.Lock = self.stormLocks[serverId]
            lock.acquire()
            self.logger.info(f'Storm timed out in server {serverId}.')
            self.generateNewStorm(serverId)
            await utils.sendDiscordEmbed(channel, "🌞 🌞 🌞 **STORM OVER** 🌞 🌞 🌞", None, nextcord.Color.orange(), None, None, None, self.STORMS_DELETE_MESSAGES_AFTER_SECONDS)
        finally:
            lock.release()

    async def completeStorm(self, serverId, authorMention, multiplierInfo):
        self.logger.info(f'Storm completed in server {serverId}.')
        # update state to 0 by generating a new storm
        self.generateNewStorm(serverId)
        # send storm complete message to storm channel
        channelId = config_queries.getServerValue(serverId, 'channel_storms')
        channel: nextcord.TextChannel = await self.client.fetch_channel(int(channelId))
        await channel.send(f'Congratulations {authorMention}, you guessed correctly and earned {multiplierInfo[0]} points! ({multiplierInfo[1]} applied)', delete_after = self.STORMS_DELETE_MESSAGES_AFTER_SECONDS)
        await utils.sendDiscordEmbed(channel, "🌞 🌞 🌞 **STORM OVER** 🌞 🌞 🌞", None, nextcord.Color.orange(), None, None, None, self.STORMS_DELETE_MESSAGES_AFTER_SECONDS)

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

def setup(client: commands.Bot):
    client.add_cog(Storms(client))