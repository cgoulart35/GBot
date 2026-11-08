#region IMPORTS
import logging
import asyncio
import random
import nextcord
from nextcord.ext import commands, tasks
from nextcord.ext.commands.context import Context
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta

from GBotDiscord.src import presentation
from GBotDiscord.src import strings
from GBotDiscord.src import utils
from GBotDiscord.src import predicates
from GBotDiscord.src import pagination
from GBotDiscord.src.help import guides
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.gcoin import gcoin_queries
from GBotDiscord.src.leaderboards import leaderboards_queries
from GBotDiscord.src.exceptions import EnforcePositiveTransactions, EnforceSenderFundsError, StormNotConfigured
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.firebase import GBotFirebaseService
#endregion

STORMS_BUTTON_PREFIX = 'storms:'
STORMS_UMBRELLA = 'umbrella'
STORMS_GUESS = 'guess'
STORMS_BET = 'bet'
STORMS_HOW = 'how'
STORMS_HINT = 'hint'
MAX_NUMBER = 200
STORM_MINUTES = 10
MAX_PLAYERS_SHOWN = 15
# a win's boost, by how many tries it took. After four there is none.
MULTIPLIERS = {1: Decimal('10'), 2: Decimal('5'), 3: Decimal('2.5'), 4: Decimal('1.25')}

class Storms(commands.Cog):

    # what the API leaves out of a Storm's state: messages, which aren't data
    STATE_NOT_SHOWN = ('deleteMessages', 'card', 'hints')

    # on the class, so /help's guide reads the same numbers the game pays out
    UMBRELLA_REWARD_GCOIN = Decimal('0.25')
    GUESS_REWARD_GCOIN = Decimal('1.00')

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()

        self.stormStates = {}
        self.stormLocks = {}

    # Events
    @commands.Cog.listener()
    async def on_guild_join(self, guild: nextcord.Guild):
        serverId = str(guild.id)
        self.logger.info(f'Adding server storm state for guild {serverId} ({guild.name}).')
        self.stormLocks[serverId] = asyncio.Lock()
        self.generateNewStorm(serverId)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: nextcord.Guild):
        serverId = str(guild.id)
        self.logger.info(f'Removing server storm state for guild {serverId} ({guild.name}).')
        # pop with a default; a guild filtered out by filterGuildsForInstance was never initialized
        self.stormLocks.pop(serverId, None)
        self.stormStates.pop(serverId, None)

    @commands.Cog.listener()
    async def on_ready(self):
        # every time, not only the first: this also fires on a reconnect, and a server that added the
        # bot while it was offline only ever gets a place in client.guilds, never a join event
        for guild in self.client.guilds:
            serverId = str(guild.id)
            if serverId not in self.stormStates:
                self.stormLocks[serverId] = asyncio.Lock()
                self.generateNewStorm(serverId)
        try:
            self.storm_invoker.start()
        except RuntimeError:
            self.logger.info('storm_invoker task is already launched and is not completed.')

    # Tasks
    @tasks.loop(seconds=1)
    async def storm_invoker(self):
        currentTime = datetime.now()
        # check all server storms; iterate a snapshot of the keys, as the awaits below can
        # remove entries from stormStates
        for serverId in list(self.stormStates.keys()):
            # one guild's failure stays its own: this used to abort the pass, skipping every later guild
            try:
                stormState = self.stormStates.get(serverId)
                if stormState is None:
                    continue
                stormStateNum = stormState['stormState']
                triggerTime = datetime.strptime(stormState['triggerTime'], "%m/%d/%y %I:%M:%S %p")

                # if storm is not running
                if stormStateNum == 0:
                    generatedAtTime = datetime.strptime(stormState['generatedAtTime'], "%m/%d/%y %I:%M:%S %p")
                    deleteReady = stormState['deleteReady']

                    # if it is time for the storm, check to see if storms configured
                    if currentTime >= triggerTime:

                        # if storms are configured, start the storm in the channel
                        isConfigured = await self.isServerStormsConfigured(serverId)
                        if isConfigured[0]:
                            stormStateNum = stormState['stormState']
                            try:
                                await self.startStorm(serverId, isConfigured[1])
                            except Exception as e:
                                # no send permission in the channel, say. Left pending, this
                                # would retry against Discord every second until it worked.
                                self.logger.error(f'Storm failed to start in server {serverId}; scheduling another: {e}')
                                self.generateNewStorm(serverId)
                            
                        # if storms are not configured, delay it by generating a new storm
                        else:
                            self.logger.info(f'Storm skipped in server {serverId} due to not being configured.')
                            self.generateNewStorm(serverId)

                    # if storms haven't been running for x seconds, delete messages in the list if there are any
                    elif deleteReady and (currentTime - generatedAtTime >= timedelta(seconds = GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS)):
                        await self.purgePreviousStormMessages(serverId, stormState['deleteMessages'])

                # if storm is running
                else:
                    # if its been 5 minutes & no 5 minute warning has been given, check to see if storms configured
                    if not stormState['fiveMinuteWarning'] and currentTime >= triggerTime + timedelta(minutes = 5):
                        stormState['fiveMinuteWarning'] = True

                        # if storms are configured, send 5 minute warning
                        isConfigured = await self.isServerStormsConfigured(serverId)
                        if isConfigured[0]:
                            self.saveMessageForPurge(serverId, await presentation.sendEmbed(isConfigured[1], title = "🌦️ 5 minutes remaining", feature = 'Storms'))
                            
                    # if its been 9 minutes & no 1 minute warning has been given, check to see if storms configured
                    if not stormState['oneMinuteWarning'] and currentTime >= triggerTime + timedelta(minutes = 9):
                        stormState['oneMinuteWarning'] = True

                        # if storms are configured, send 1 minute warning
                        isConfigured = await self.isServerStormsConfigured(serverId)
                        if isConfigured[0]:                  
                            self.saveMessageForPurge(serverId, await presentation.sendEmbed(isConfigured[1], title = "🌦️ 1 minute remaining", feature = 'Storms'))
                            
                    # if storm has been running for 10 minutes, try to end it
                    if currentTime >= triggerTime + timedelta(minutes = STORM_MINUTES):
                        await self.stormTimeout(serverId)
            except Exception as e:
                self.logger.error(f'Error in Storms.storm_invoker() for guild {serverId}: {e}')

    # Commands
    @nextcord.slash_command(name = strings.STORMS_NAME, description = strings.STORMS_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_storms', False, True)
    async def stormsSlash(self,
                          interaction: nextcord.Interaction,
                          number: int = nextcord.SlashOption(
                            name = 'number',
                            required = False,
                            min_value = 1,
                            max_value = MAX_NUMBER,
                            description = strings.STORMS_NUMBER_DESCRIPTION),
                          bet = nextcord.SlashOption(
                            name = 'bet',
                            required = False,
                            description = strings.STORMS_BET_DESCRIPTION)
                          ):
        await self.commonStorms(interaction, interaction.user, number, presentation.parseGCoin(bet) if bet is not None else None)

    @commands.command(name = strings.STORMS_NAME, aliases = strings.STORMS_ALIASES, brief = "- " + strings.STORMS_BRIEF, description = strings.STORMS_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_storms', False)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def storms(self, ctx: Context, number: int = None, bet: presentation.parseGCoin = None):
        await self.commonStorms(ctx, ctx.author, number, bet)

    async def commonStorms(self, context, author, number, bet):
        # A number guesses, and a number with a bet bets. Nothing puts up the umbrella while a Storm is
        # incoming, the fastest way for someone typing, or says what's going on.
        if number is None and bet is not None:
            await self.tell(context, f'Sorry {author.mention}, please give a number to bet on.', isError = True)
        elif number is not None:
            await self.commonGuess(context, author, number, utils.roundDecimalPlaces(bet, 2) if bet is not None else None)
        elif self.stormStates[str(context.guild.id)]['stormState'] == 1:
            await self.commonUmbrella(context, author)
        else:
            await self.commonStatus(context)

    async def commonStatus(self, context):
        stormState = self.stormStates[str(context.guild.id)]
        if stormState['stormState'] == 2:
            text = f'🌧️ A Storm is on. Guess with `/storms <number>`, or press 🎯 **Guess** on its card.'
        else:
            text = f'🌞 No Storm right now. They roll in every {guides.hours(GBotPropertiesManager.STORMS_MIN_TIME_BETWEEN_SECONDS)} to {guides.hours(GBotPropertiesManager.STORMS_MAX_TIME_BETWEEN_SECONDS)} hours.'
        await self.tell(context, text)

    async def answerPrivately(self, context):
        # Discord allows 3 seconds, and this waits on the storm lock and on GCoin. Private, so a hint
        # stays with whoever asked. A form's submit gets a message of its own rather than editing the card.
        if isinstance(context, nextcord.Interaction) and context.response.is_done() is not True:
            await context.response.defer(ephemeral = True, with_message = context.type == nextcord.InteractionType.modal_submit)

    async def tell(self, context, text, isError = False, view = None):
        # private for a press or a slash command. A prefix command's answer is public, so it's
        # cleared with the Storm's messages.
        if isError:
            message = await presentation.sendError(context, text, feature = 'Storms', ephemeral = True)
        else:
            kwargs = {'view': view} if view is not None else {}
            message = await context.send(text, ephemeral = True, **kwargs) if isinstance(context, nextcord.Interaction) else await context.send(text, **kwargs)
        if not isinstance(context, nextcord.Interaction):
            self.saveMessageForPurge(str(context.guild.id), message)

    async def tidyPrefix(self, context):
        # a typed guess shows its number, which would hand the next guesser a free hint
        if isinstance(context, Context):
            try:
                await context.message.delete()
            except nextcord.HTTPException:
                self.saveMessageForPurge(str(context.guild.id), context.message)

    async def commonUmbrella(self, context, author):
        serverId = str(context.guild.id)
        await self.answerPrivately(context)
        try:
            # a concurrent umbrella waits here rather than racing, so exactly one caller can observe
            # stormState 1 and win the reward
            async with self.stormLocks[serverId]:
                isConfigured = await self.isServerStormsConfigured(serverId)
                if not isConfigured[0]:
                    raise StormNotConfigured
                stormState = self.stormStates[serverId]
                if stormState['stormState'] == 1:
                    await GBotFirebaseService.run(self.rewardUmbrella, author.id, author.name)
                    stormState['stormState'] = 2
                    stormState['startedBy'] = author.id
                    await self.showCard(serverId)
                    elsewhere = '' if context.channel.id == isConfigured[1].id else f' Guess in {isConfigured[1].mention}.'
                    await self.tell(context, f'☂️ {author.mention}, you started the Storm and earned **{presentation.formatGCoin(self.UMBRELLA_REWARD_GCOIN)} GCoin**!{elsewhere}')
                elif stormState['stormState'] == 0:
                    await self.tell(context, f'Sorry {author.mention}, there is currently no active Storm.', isError = True)
                else:
                    await self.tell(context, f'Sorry {author.mention}, the Storm has already been started!', isError = True)
        except StormNotConfigured:
            await self.notConfigured(context, author, 'umbrella')
        finally:
            await self.tidyPrefix(context)

    async def commonGuess(self, context, author, number: int, gcoin: Decimal = None):
        serverId = str(context.guild.id)
        await self.answerPrivately(context)
        try:
            # guesses are serialized so only one can win
            async with self.stormLocks[serverId]:
                isConfigured = await self.isServerStormsConfigured(serverId)
                if not isConfigured[0]:
                    raise StormNotConfigured
                if self.stormStates[serverId]['stormState'] != 2:
                    await self.tell(context, f'Sorry {author.mention}, there is currently no active Storm.', isError = True)
                    return
                if not 1 <= number <= MAX_NUMBER:
                    await self.tell(context, f'Sorry {author.mention}, please guess a number from 1 to {MAX_NUMBER}.', isError = True)
                    return
                won, text = await self.guessNumber(serverId, author, number, gcoin)
            if won or isinstance(context, nextcord.Interaction):
                await self.tell(context, text)
            else:
                # the channel only learns it was wrong, and the hint waits behind a button for its guesser
                self.stormStates[serverId]['hints'][author.id] = text
                hint = pagination.persistentView([pagination.persistentButton('See your hint', '🔒', nextcord.ButtonStyle.secondary, f'{STORMS_BUTTON_PREFIX}{STORMS_HINT}:{author.id}')])
                try:
                    await self.tell(context, f'❌ **{author.display_name}** guessed wrong.', view = hint)
                finally:
                    pagination.stopped(hint)
        except StormNotConfigured:
            await self.notConfigured(context, author, 'bet' if gcoin is not None else 'guess')
        except EnforceSenderFundsError:
            await self.tell(context, f'Sorry {author.mention}, you have insufficient funds.', isError = True)
        except EnforcePositiveTransactions:
            await self.tell(context, f'Sorry {author.mention}, you can not bet a non-positive amount.', isError = True)
        finally:
            await self.tidyPrefix(context)

    async def notConfigured(self, context, author, what):
        await self.tell(context, f'Sorry {author.mention}, Storms are not configured in this server.', isError = True)
        await utils.sendMessageToAdmins(self.client, str(context.guild.id), f"{author.mention}'s {what} failed as there is currently no channel configured for the current Storm.", self.logger)
        self.logger.error(f'Storm {what} skipped in server {context.guild.id} due to not being configured.')

    async def guessNumber(self, serverId, author, number: int, gcoin: Decimal = None):
        # (whether it won, and what to tell the guesser)
        date = datetime.now().strftime("%m/%d/%y %I:%M:%S %p")
        authorId = str(author.id)
        authorName = author.name
        # refused here, ahead of the guess count and the win statistics a losing bet can't undo
        if gcoin is not None and gcoin <= 0:
            raise EnforcePositiveTransactions
        if gcoin is not None and gcoin > await GBotFirebaseService.run(gcoin_queries.getUserBalance, authorId):
            raise EnforceSenderFundsError
        self.recordGuessAttempt(serverId, authorId)
        stormState = self.stormStates[serverId]
        winningNumber = stormState['winningNumber']
        if winningNumber == number:
            multiplierInfo = await GBotFirebaseService.run(self.rewardWin, serverId, authorId, authorName, gcoin, date)
            await self.completeStorm(serverId, author, number, multiplierInfo)
            return True, f'🎉 {author.mention}, you guessed it and won **{presentation.formatGCoin(multiplierInfo[0])} GCoin**!'
        if gcoin is not None:
            receiver = {'id': None, 'name': 'Storms'}
            sender = {'id': authorId, 'name': authorName}
            await GBotFirebaseService.run(gcoin_queries.performTransaction, gcoin, date, sender, receiver, 'Lost Bet', '', False, True)
            start = f'💸 So close! You lost **{presentation.formatGCoin(gcoin)} GCoin**.'
        else:
            start = '🎯 Not quite!'
        tries = self.getPlayerGuessCount(serverId, authorId)
        direction = 'too low ⬆️, so go higher' if number < winningNumber else 'too high ⬇️, so go lower'
        nextMultiplier = MULTIPLIERS.get(tries + 1)
        boost = f'a win on your next try pays x{nextMultiplier}' if nextMultiplier else 'wins pay x1 from here'
        await self.showCard(serverId)
        return False, f'{start} **{number}** is {direction}. That was try {tries}, so {boost}.'

    def describePlayers(self, serverId, winnerId = None):
        attempts = self.stormStates[serverId]['attemptsMap']
        guild = self.client.get_guild(int(serverId))
        lines = []
        for userId, tries in sorted(attempts.items(), key = lambda entry: entry[1], reverse = True)[:MAX_PLAYERS_SHOWN]:
            member = guild.get_member(int(userId)) if guild is not None else None
            name = nextcord.utils.escape_markdown(member.display_name) if member is not None else 'Someone'
            lines.append(f"{name} · {tries} {'try' if tries == 1 else 'tries'}{' 🏆' if userId == winnerId else ''}")
        if len(attempts) > MAX_PLAYERS_SHOWN:
            lines.append(f'…and {len(attempts) - MAX_PLAYERS_SHOWN} more')
        return '\n'.join(lines) or 'Nobody has guessed yet.'

    def endsAt(self, serverId):
        triggerTime = datetime.strptime(self.stormStates[serverId]['triggerTime'], "%m/%d/%y %I:%M:%S %p")
        return int((triggerTime + timedelta(minutes = STORM_MINUTES)).timestamp())

    def cardFor(self, serverId):
        # the Storm's one message: incoming, then in progress, edited as people play
        stormState = self.stormStates[serverId]
        ends = f'Ends <t:{self.endsAt(serverId)}:R>.'
        if stormState['stormState'] == 1:
            embed = presentation.brandEmbed(title = '⛈️ Storm incoming!', description = f'First to press ☂️ **Umbrella** starts it and earns **{presentation.formatGCoin(self.UMBRELLA_REWARD_GCOIN)} GCoin**.\n{ends}', feature = 'Storms')
            buttons = [(strings.STORMS_UMBRELLA_LABEL, '☂️', nextcord.ButtonStyle.success, STORMS_UMBRELLA)]
        else:
            boosts = ' · '.join(f'x{multiplier}' for multiplier in MULTIPLIERS.values())
            embed = presentation.brandEmbed(title = '🌧️ Storm in progress', description = f'Guess a number from 1 to {MAX_NUMBER}. Your hint is yours alone.\n⚡ {boosts} on your first four tries\n{ends}', feature = 'Storms')
            embed.add_field(name = 'Players', value = self.describePlayers(serverId), inline = False)
            if stormState['startedBy'] is not None:
                embed.add_field(name = 'Started by', value = f"<@{stormState['startedBy']}> ☂️", inline = False)
            buttons = [('Guess', '🎯', nextcord.ButtonStyle.primary, STORMS_GUESS), ('Bet', '🎲', nextcord.ButtonStyle.secondary, STORMS_BET)]
        buttons.append(('How it works', '📖', nextcord.ButtonStyle.secondary, STORMS_HOW))
        return embed, pagination.persistentView([pagination.persistentButton(label, emoji, style, f'{STORMS_BUTTON_PREFIX}{action}') for label, emoji, style, action in buttons])

    async def showCard(self, serverId):
        card = self.stormStates[serverId]['card']
        if card is None:
            return
        embed, view = self.cardFor(serverId)
        try:
            await card.edit(embed = embed, view = view)
        except nextcord.HTTPException as e:
            self.logger.error(f'GBot Storms could not update its card in server {serverId}: {e}')
        finally:
            pagination.stopped(view)

    async def endCard(self, card, embed):
        if card is None:
            return
        try:
            await card.edit(embed = embed, view = None)
        except nextcord.HTTPException as e:
            self.logger.error(f'GBot Storms could not close its card: {e}')

    @commands.Cog.listener()
    async def on_interaction(self, interaction: nextcord.Interaction):
        parts = pagination.persistentParts(interaction, STORMS_BUTTON_PREFIX)
        if parts is None:
            return
        try:
            await self.answerCardButton(interaction, parts)
        except Exception as e:
            await presentation.sendInteractionError(interaction, e)

    async def answerCardButton(self, interaction, parts):
        action = parts[0]
        if action == STORMS_GUESS:
            await interaction.response.send_modal(self.guessForm(interaction, False))
        elif action == STORMS_BET:
            await interaction.response.send_modal(self.guessForm(interaction, True))
        elif action == STORMS_HOW:
            await interaction.response.send_message(embed = presentation.brandEmbed(title = '📖 How Storms work', description = guides.guideFor('Storms'), feature = 'Storms'), ephemeral = True)
        elif action == STORMS_HINT:
            hint = self.stormStates.get(str(interaction.guild.id), {}).get('hints', {}).get(interaction.user.id)
            if str(interaction.user.id) != parts[1]:
                await presentation.sendError(interaction, 'That hint is for whoever guessed.', feature = 'Storms')
            else:
                await interaction.response.send_message(hint or 'That hint is gone, as the Storm has moved on.', ephemeral = True)
        elif action == STORMS_UMBRELLA:
            await interaction.response.defer(ephemeral = True)
            await predicates.recheck(interaction, feature = 'toggle_storms')
            await self.commonUmbrella(interaction, interaction.user)

    def guessForm(self, interaction, isBet):
        fields = [pagination.Field(f'Your guess (1 to {MAX_NUMBER})', placeholder = '42', maxLength = 3)]
        if isBet:
            fields.append(pagination.Field('GCoin to bet', placeholder = '5.00', maxLength = 20))
        async def submit(submitted, values):
            await self.answerPrivately(submitted)
            await predicates.recheck(submitted, feature = 'toggle_storms')
            try:
                number = int(values[0])
                gcoin = utils.roundDecimalPlaces(presentation.parseGCoin(values[1]), 2) if isBet else None
            except (ValueError, InvalidOperation):
                await self.tell(submitted, f'Sorry {submitted.user.mention}, please enter a whole number{" and a valid amount" if isBet else ""}.', isError = True)
                return
            await self.commonGuess(submitted, submitted.user, number, gcoin)
        return pagination.Form('Bet on a guess' if isBet else 'Guess the number', fields, submit)

    def rewardUmbrella(self, authorId, authorName):
        # update player's statistics
        leaderboards_queries.incrementUserNumValue(authorId, authorName, 'numStormStarts')

        # give player points for starting storm
        dateTimeObj = datetime.now()
        date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")
        sender = { 'id': None, 'name': 'Storms' }
        receiver = { 'id': authorId, 'name': authorName }
        gcoin_queries.performTransaction(self.UMBRELLA_REWARD_GCOIN, date, sender, receiver, '', 'Started Storm', False, False)

    def rewardWin(self, serverId, authorId, authorName, gcoin, date):
        # update player's statistics
        leaderboards_queries.incrementUserNumValue(authorId, authorName, 'numStormWins')
        # if bet made use specified points, otherwise use self.GUESS_REWARD_GCOIN (apply multipier)
        sender = { 'id': None, 'name': 'Storms' }
        receiver = { 'id': authorId, 'name': authorName }
        multiplierInfo = self.applyMultiplier(serverId, authorId, authorName, (self.GUESS_REWARD_GCOIN if gcoin == None else gcoin))
        gcoin_queries.performTransaction(multiplierInfo[0], date, sender, receiver, '', (f'Won Guess {multiplierInfo[1]}' if gcoin == None else f'Won Bet {multiplierInfo[1]}'), False, False)
        return multiplierInfo

    def generateNewStorm(self, serverId, startNow = None):
        if serverId in self.stormStates and self.stormStates[serverId] != None:
            deleteMessages = self.stormStates[serverId]['deleteMessages']
        else:
            deleteMessages = []

        dateTimeNow = datetime.now()
        if startNow != None and startNow:
            dateTimeObj = dateTimeNow
        else:
            randomSeconds = random.randint(GBotPropertiesManager.STORMS_MIN_TIME_BETWEEN_SECONDS, GBotPropertiesManager.STORMS_MAX_TIME_BETWEEN_SECONDS)
            dateTimeObj = dateTimeNow + timedelta(seconds = randomSeconds)
        triggerTime = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")
        generatedAtTime = dateTimeNow.strftime("%m/%d/%y %I:%M:%S %p")
        serverStormState = {
            'stormState': 0,
            'triggerTime': triggerTime,
            'generatedAtTime': generatedAtTime,
            'winningNumber': random.randint(1, 200),
            'attemptsMap': {},
            'fiveMinuteWarning': False,
            'oneMinuteWarning': False,
            'deleteReady': True,
            'deleteMessages': deleteMessages,
            # the Storm's card, who started it, and the hints waiting behind a prefix guess's button
            'card': None,
            'startedBy': None,
            'hints': {}
        }
        self.stormStates[serverId] = serverStormState
        self.logger.info(f'Storm scheduled in server {serverId} to start at {triggerTime}.')

    async def startStorm(self, serverId, channel: nextcord.TextChannel):
        # the incoming card, which becomes the Storm in progress when someone puts up their umbrella
        self.stormStates[serverId]['stormState'] = 1
        embed, view = self.cardFor(serverId)
        try:
            card = await channel.send(embed = embed, view = view)
        finally:
            pagination.stopped(view)
        self.stormStates[serverId]['card'] = card
        self.saveMessageForPurge(serverId, card)
        self.logger.info(f'Storm started in server {serverId}.')

    async def stormTimeout(self, serverId):
        # obtain storm lock and call generateNewStorm; waiting here means a command already
        # in flight finishes against the old storm rather than a half-replaced one
        async with self.stormLocks[serverId]:
            self.logger.info(f'Storm timed out in server {serverId}.')
            stormState = self.stormStates[serverId]
            if stormState['stormState'] == 1:
                description = 'Nobody put up an umbrella this time.'
            else:
                description = f"Nobody guessed it. The number was **{stormState['winningNumber']}**."
            embed = presentation.brandEmbed(title = '🌞 Storm over', description = description, feature = 'Storms')
            if stormState['attemptsMap']:
                embed.add_field(name = 'Players', value = self.describePlayers(serverId), inline = False)
            card = stormState['card']
            self.generateNewStorm(serverId)
            await self.endCard(card, embed)

    async def completeStorm(self, serverId, winner, number, multiplierInfo):
        # the card becomes the result, and the number can be told now it's over
        self.logger.info(f'Storm completed in server {serverId}.')
        stormState = self.stormStates[serverId]
        tries = stormState['attemptsMap'].get(str(winner.id), 1)
        embed = presentation.brandEmbed(title = self.describeWinTitle(multiplierInfo), description = f'{winner.mention} guessed **{number}** on their {presentation.ordinal(tries)} try and won **{presentation.formatGCoin(multiplierInfo[0])} GCoin**!', feature = 'Storms')
        embed.add_field(name = 'Players', value = self.describePlayers(serverId, str(winner.id)), inline = False)
        card = stormState['card']
        self.generateNewStorm(serverId)
        await self.endCard(card, embed)

    def describeWinTitle(self, multiplierInfo):
        # no multiplier applies after 4 guesses, and "x1" would only look like a bonus that did nothing
        return '🎉 Storm won!' if multiplierInfo[1] == 'x1' else f'🎉 Storm won! ⚡ {multiplierInfo[1]}'

    def saveMessageForPurge(self, serverId, message):
        self.stormStates[serverId]['deleteMessages'].append(message)

    async def purgePreviousStormMessages(self, serverId, deleteMessages):
        self.logger.info(f'Purging Storm messages in server {serverId}.')
        self.stormStates[serverId]['deleteReady'] = False
        if deleteMessages != None and len(deleteMessages) > 0:
            try:
                isConfigured = await self.isServerStormsConfigured(serverId)
                if not isConfigured[0]:
                    raise StormNotConfigured()
                await utils.purgePreviousMessages(deleteMessages, isConfigured[1])
            except Exception as e:
                await utils.sendMessageToAdmins(self.client, serverId, f"There were messages that did not get deleted in the last Storm's configured channel. Please make sure the bot has the 'Manage Messages' permission in all channels used for Storm commands.", self.logger)
                self.logger.error(f'Storm messages in server {serverId} failed to purge with the following error: {e}')
            finally:
                self.stormStates[serverId]['deleteMessages'] = []

    def getPlayerGuessCount(self, serverId, userId):
        if userId in self.stormStates[serverId]['attemptsMap']:
            guessCount = self.stormStates[serverId]['attemptsMap'][userId]
        else:
            guessCount = 0
        return guessCount

    def recordGuessAttempt(self, serverId, userId):
        guessCount = self.getPlayerGuessCount(serverId, userId)
        self.stormStates[serverId]['attemptsMap'][userId] = guessCount + 1

    def applyMultiplier(self, serverId, userId, userName, reward):
        guessCount = self.getPlayerGuessCount(serverId, userId)
        multiplier = MULTIPLIERS.get(guessCount, Decimal('1'))
        statistic = f'numStormTier{guessCount}Multi' if guessCount in MULTIPLIERS else None
        # update player's statistics
        if statistic is not None:
            leaderboards_queries.incrementUserNumValue(userId, userName, statistic)
        finalReward = utils.roundDecimalPlaces(reward * multiplier, 2)
        return (finalReward, f'x{multiplier}')

    def readStormsConfig(self, serverId):
        return (config_queries.getServerValue(serverId, 'toggle_storms'), config_queries.getServerValue(serverId, 'channel_storms'))

    async def isServerStormsConfigured(self, serverId):
        isStormsEnabled, channelId = await GBotFirebaseService.run(self.readStormsConfig, serverId)
        try:
            channel: nextcord.TextChannel = await self.client.fetch_channel(int(channelId))
        except Exception:
            # not set, or a channel that is gone or out of reach right now. Not bare, so a shutdown
            # still gets through.
            return (False, None)
        return (isStormsEnabled and channelId != None and channel != None, channel)

def setup(client: commands.Bot):
    client.add_cog(Storms(client))