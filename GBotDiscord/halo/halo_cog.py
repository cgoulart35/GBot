#region IMPORTS
import pathlib
import os
import logging
import json
import random
import httpx
import nextcord
from nextcord.ext import commands, tasks
from nextcord.ext.commands.context import Context
from datetime import datetime
from decimal import Decimal
from urllib import parse
from collections import OrderedDict

from GBotDiscord import utils
from GBotDiscord import predicates
from GBotDiscord.config import config_queries
from GBotDiscord.gcoin import gcoin_queries
from GBotDiscord.halo import halo_queries
from GBotDiscord.halo.halo_models import HaloInfiniteCompetitionVariables, HaloInfiniteWeeklyCompetitionModel, HaloInfiniteParticipantModel
#endregion

class Halo(commands.Cog):

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()
        self.parentDir = str(pathlib.Path(__file__).parent.parent.absolute()).replace("\\",'/')
        self.AUTOCODE_TOKEN = os.getenv("AUTOCODE_TOKEN")
        self.HALO_MOTD_HOUR = os.getenv("HALO_INFINITE_MOTD_HOUR")
        self.HALO_MOTD_MINUTE = os.getenv("HALO_INFINITE_MOTD_MINUTE")
        self.HALO_COMPETITION_DAY = os.getenv("HALO_INFINITE_COMPETITION_DAY")
        self.HALO_COMPETITION_HOUR = os.getenv("HALO_INFINITE_COMPETITION_HOUR")
        self.HALO_COMPETITION_MINUTE = os.getenv("HALO_INFINITE_COMPETITION_MINUTE")
        self.HALO_IMG_PATH = f'{self.parentDir}/images/haloInfiniteImage.jpg'
        self.HALO_SEASON_IMG_PATH = f'{self.parentDir}/images/haloInfiniteSeasonTwo.jpg'
        self.GCOIN_DAILY_WIN_REWARD = Decimal('0.14')
        self.GCOIN_WEEKLY_PARTICIPATION_REWARD = Decimal('0.50')
        self.GCOIN_WEEKLY_WIN_REWARD = Decimal('1.00')
        self.HALO_API_VERSION = '0.3.9'
        self.HALO_API_HOST = f'https://halo.api.stdlib.com/infinite@{self.HALO_API_VERSION}'
        self.HALO_API_STATS = f'/stats/service-record/multiplayer'
        self.HALO_API_MOTD = f'/articles/list/'
    
    # Events
    @commands.Cog.listener()
    async def on_guild_remove(self, guild: nextcord.Guild):
        self.logger.info(f'Deleting Halo Infinite data for guild {guild.id} ({guild.name}).')
        halo_queries.deleteServerHaloValues(guild.id)

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            self.wait_to_start_batch_halo_MOTD.start()
        except RuntimeError:
            self.logger.info('wait_to_start_batch_halo_MOTD task is already launched and is not completed.')
        try:
            self.wait_to_start_batch_halo_player_stats.start()
        except RuntimeError:
            self.logger.info('wait_to_start_batch_halo_player_stats task is already launched and is not completed.')

    # Tasks
    @tasks.loop(minutes=1)
    async def wait_to_start_batch_halo_MOTD(self):
        dateTimeObj = datetime.now()
        if str(dateTimeObj.hour) == self.HALO_MOTD_HOUR and str(dateTimeObj.minute) == self.HALO_MOTD_MINUTE:
            self.wait_to_start_batch_halo_MOTD.cancel()
            self.logger.info('Initial kickoff time reached. Starting Halo Infinite MOTD batch job...')
            try:
                self.batch_halo_MOTD.start()
            except RuntimeError:
                self.logger.info('batch_halo_MOTD task is already launched and is not completed.')

    @tasks.loop(minutes=1)
    async def wait_to_start_batch_halo_player_stats(self):
        dateTimeObj = datetime.now()
        if str(dateTimeObj.hour) == self.HALO_COMPETITION_HOUR and str(dateTimeObj.minute) == self.HALO_COMPETITION_MINUTE:
            self.wait_to_start_batch_halo_player_stats.cancel()
            self.logger.info('Initial kickoff time reached. Starting Halo Infinite Player Stats batch job...')
            try:
                self.batch_halo_player_stats.start()
            except RuntimeError:
                self.logger.info('batch_halo_player_stats task is already launched and is not completed.')

    @tasks.loop(hours=24)
    async def batch_halo_MOTD(self):
        await self.haloMotdGetRequest()

    @tasks.loop(hours=24)
    async def batch_halo_player_stats(self):
        await self.haloPlayerStatsGetRequests()

    async def haloMotdGetRequest(self):
        async with httpx.AsyncClient() as httpxClient:
            self.logger.info('Retrieving latest Halo Infinite MOTD...')
            url = self.HALO_API_HOST + self.HALO_API_MOTD
            autocodeToken = self.AUTOCODE_TOKEN
            headers = { 'Authorization': f'Bearer {autocodeToken}' }
            response = await httpxClient.get(url, headers = headers, timeout = 60)
            if response.status_code != 200:
                self.logger.error(f'Error retrieving message data: {response.text}')
            else:
                newJsonMOTD = response.json()
                await self.haloMotdSendDiscord(newJsonMOTD)

    async def haloMotdSendDiscord(self, newJsonMOTD):
        self.logger.info('Calculating all server Halo Infinite MOTD updates...')
        newStrMOTD = json.dumps(newJsonMOTD, sort_keys = True)
        dateTimeObj = datetime.now()
        date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")
        servers = config_queries.getAllServers()
        for serverId, serverValues in servers.items():
            if serverValues['toggle_halo'] and 'channel_halo_motd' in serverValues:
                oldJsonMOTD = halo_queries.getLastHaloInfiniteMOTD(serverId)
                oldStrMOTD = json.dumps(oldJsonMOTD, sort_keys = True)
                if newStrMOTD != oldStrMOTD:
                    halo_queries.postHaloInfiniteMOTD(serverId, date, newJsonMOTD)
                    # filter out updates that have been posted before to reduce server posting
                    updatesToPost = []
                    for message in newJsonMOTD['data']:
                        if oldJsonMOTD == '' or message not in oldJsonMOTD['data']:
                            updatesToPost.append(message)
                    channel: nextcord.TextChannel = await self.client.fetch_channel(int(serverValues['channel_halo_motd']))
                    for msg in updatesToPost:
                        msgTitle = msg['title']
                        msgText = msg['message']
                        msgImgUrl = msg['image_url']
                        if await utils.isUrlImageContentTypeAndStatus200(msgImgUrl):
                            messageImg = None
                            messageUrl = msgImgUrl
                        else:
                            messageImg = nextcord.File(self.HALO_SEASON_IMG_PATH)
                            messageUrl = None
                        await utils.sendDiscordEmbed(channel, msgTitle, msgText, nextcord.Color.purple(), messageImg, messageUrl)

    async def haloPlayerStatsGetRequests(self):
        self.logger.info('Retrieving Halo Infinite Player Stats...')
        dateTimeObj = datetime.now()
        date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")
        allServerConfigs = config_queries.getAllServers()
        allHaloInfiniteServers = halo_queries.getAllHaloInfiniteServers()
        obtainedPlayerData = {}
        for serverId, serverValues in allServerConfigs.items():
            # GCoin integration
            isGCoinEnabled = config_queries.getServerValue(serverId, 'toggle_gcoin')
            gcoinRewardsStr = " (Halo GCoin Rewards Enabled)" if isGCoinEnabled else ''

            freshPlayerDataCompetition = HaloInfiniteWeeklyCompetitionModel('', {}, date)
            if serverValues['toggle_halo'] and 'channel_halo_competition' in serverValues:
                nextCompetitionId = halo_queries.getNextCompetitionId(serverId)
                channel: nextcord.TextChannel = await self.client.fetch_channel(int(serverValues['channel_halo_competition']))
                try:
                    players = allHaloInfiniteServers[serverId]['participating_players']
                    # always filter only those participating
                    players = dict(filter(lambda playerItem: halo_queries.isUserParticipatingInHalo(serverId, playerItem[0]), players.items()))
                    # if it is not competition announcement day, filter participating players to those only who had data grabbed at start of week to limit API cost
                    if str(dateTimeObj.weekday()) != self.HALO_COMPETITION_DAY:
                        players = dict(filter(lambda playerItem: halo_queries.isUserInThisWeeksInitialDataFetch(serverId, nextCompetitionId - 1, playerItem[0]), players.items()))
                    
                except Exception:
                    players = {}
                for playerId, playerValues in players.items():
                    gamertag = playerValues['gamertag']
                    wins = playerValues['wins']
                    if gamertag not in obtainedPlayerData:
                        playerDataJson = await self.haloPlayerStatsGetRequest(gamertag)
                        if not playerDataJson:
                            continue
                        obtainedPlayerData[gamertag] = playerDataJson
                    else:
                        playerDataJson = obtainedPlayerData[gamertag]
                    playerDataJson['wins'] = wins
                    freshPlayerDataCompetition.participants[playerId] = HaloInfiniteParticipantModel.createObjectFromDatabaseOrAPI(playerDataJson)

                # if it is new competition time, post the data to database and announce winners
                if str(dateTimeObj.weekday()) == self.HALO_COMPETITION_DAY:
                    competitionVariable = random.choice(list(HaloInfiniteCompetitionVariables)).value
                    freshPlayerDataCompetition.competition_variable = competitionVariable
                    halo_queries.postHaloInfiniteServerPlayerData(serverId, nextCompetitionId, freshPlayerDataCompetition)
                    if nextCompetitionId == 0:
                        headerStr = "**Week  0:  The  week  you  probably  didn't  even  know  about...**"
                        descriptionStr = 'Hello there! Week 1 of Halo Infinite challenges starts a week from right now!\nSign up before the next week starts to be included in random weekly challenges!\n\nUse the commands below to participate in the weekly Halo Infinite challenges.\n\n__Participate:__\n.halo YOUR_GAMERTAG\n__Leave:__\n.halo rm'
                        haloImg = nextcord.File(self.HALO_IMG_PATH)
                        await utils.sendDiscordEmbed(channel, headerStr, descriptionStr, nextcord.Color.dark_blue(), haloImg)
                        continue
                    elif nextCompetitionId == 1:
                        headerStr = '**Week  1:  The  competition  starts  now!**'
                        descriptionStr = f'__Random Competition Variable:__\n{competitionVariable}\n\nForget to participate for Week 1? No worries!\nSign up before the next week starts to be included in random weekly challenges!\n\nUse the commands below to participate in the weekly Halo Infinite challenges.\n\n__Participate:__\n.halo YOUR_GAMERTAG\n__Leave:__\n.halo rm'
                        haloImg = nextcord.File(self.HALO_IMG_PATH)
                        await utils.sendDiscordEmbed(channel, headerStr, descriptionStr, nextcord.Color.dark_blue(), haloImg)
                        continue
                    else:
                        winnersAndTable = await self.generatePlayerProgressTableAndWinners(serverId, nextCompetitionId - 1, freshPlayerDataCompetition, serverValues, True, isGCoinEnabled, date)

                        headerStr1 = f'**Week  {nextCompetitionId - 1}  Results!{gcoinRewardsStr}**'
                        await utils.sendDiscordEmbed(channel, headerStr1, winnersAndTable[0], nextcord.Color.green())

                        headerStr2 = f'**Week  {nextCompetitionId}**'
                        nextWeekStr = f"__Random Competition Variable:__\n{competitionVariable}\n\nHaven't participated yet? No worries!\nSign up before the next week starts to be included in random weekly challenges!\n\nUse the commands below to participate in the weekly Halo Infinite challenges.\n\n__Participate:__\n.halo YOUR_GAMERTAG\n__Leave:__\n.halo rm"
                        haloImg = nextcord.File(self.HALO_IMG_PATH)

                        if winnersAndTable[1]:
                            tempDataTable = nextcord.File('tempDataTable.png')
                            await channel.send(file = tempDataTable)
                            utils.deleteTempTableImage()
                        
                        await utils.sendDiscordEmbed(channel, headerStr2, nextWeekStr, nextcord.Color.dark_blue(), haloImg)
                        continue

                # if it is not new competition time, don't post the data to database and announce progress
                else:
                    if nextCompetitionId - 1 > 0:
                        winnersAndTable = await self.generatePlayerProgressTableAndWinners(serverId, nextCompetitionId - 1, freshPlayerDataCompetition, serverValues, False, isGCoinEnabled, date)

                        headerStr = f'**Week  {nextCompetitionId - 1}  Progress!{gcoinRewardsStr}**'
                        await utils.sendDiscordEmbed(channel, headerStr, winnersAndTable[0], nextcord.Color.green())

                        if winnersAndTable[1]:
                            tempDataTable = nextcord.File('tempDataTable.png')
                            await channel.send(file = tempDataTable)
                            utils.deleteTempTableImage()
                        continue
        
    async def haloPlayerStatsGetRequest(self, gamertag):
        async with httpx.AsyncClient() as httpxClient:
            playerGamertagUrl = parse.quote(gamertag)
            url = self.HALO_API_HOST + self.HALO_API_STATS + f'/?gamertag={playerGamertagUrl}'
            autocodeToken = self.AUTOCODE_TOKEN
            headers = { 'Authorization': f'Bearer {autocodeToken}' }
            response = await httpxClient.get(url, headers = headers, timeout = 60)
            if response.status_code != 200:
                self.logger.error(f'Error retrieving player data for {gamertag}: {response.text}')
                return None
            return response.json()

    async def generatePlayerProgressTableAndWinners(self, serverId, competitionId, newCompetitionDataJson: HaloInfiniteWeeklyCompetitionModel, serverValues, assignRoles, isGCoinEnabled, date):
        playerProgressData = {}
        numDecimalPlaces = 0
        startingCompetitionDataJson = halo_queries.getThisWeeksInitialDataFetch(serverId, competitionId)
        startingCompetitionDataJson: HaloInfiniteWeeklyCompetitionModel = HaloInfiniteWeeklyCompetitionModel.createObjectFromDatabaseOrAPI(startingCompetitionDataJson)
        if startingCompetitionDataJson != None and startingCompetitionDataJson.competition_variable != None and startingCompetitionDataJson.participants != None:
            competitionVariable = startingCompetitionDataJson.competition_variable
            players: dict[HaloInfiniteParticipantModel] = newCompetitionDataJson.participants
            # always filter participating players to those only who had data grabbed at start of week for functionality purposes
            players = dict(filter(lambda playerItem: halo_queries.isUserInThisWeeksInitialDataFetch(serverId, competitionId, playerItem[0]), players.items()))
            for participantId, participantValues in players.items():
                participantValues: HaloInfiniteParticipantModel
                startingParticipantValues: HaloInfiniteParticipantModel = startingCompetitionDataJson.participants[participantId]
                if competitionVariable == HaloInfiniteCompetitionVariables.KILLS.value:
                    startingVariable = startingParticipantValues.data.core.summary.kills
                    newVariable = participantValues.data.core.summary.kills

                elif competitionVariable == HaloInfiniteCompetitionVariables.MELEE_KILLS.value:
                    startingVariable = startingParticipantValues.data.core.breakdowns.kills.melee
                    newVariable = participantValues.data.core.breakdowns.kills.melee

                elif competitionVariable == HaloInfiniteCompetitionVariables.GRENADE_KILLS.value:
                    startingVariable = startingParticipantValues.data.core.breakdowns.kills.grenades
                    newVariable = participantValues.data.core.breakdowns.kills.grenades

                elif competitionVariable == HaloInfiniteCompetitionVariables.HEADSHOT_KILLS.value:
                    startingVariable = startingParticipantValues.data.core.breakdowns.kills.headshots
                    newVariable = participantValues.data.core.breakdowns.kills.headshots

                elif competitionVariable == HaloInfiniteCompetitionVariables.POWER_WEAPON_KILLS.value:
                    startingVariable = startingParticipantValues.data.core.breakdowns.kills.power_weapons
                    newVariable = participantValues.data.core.breakdowns.kills.power_weapons

                elif competitionVariable == HaloInfiniteCompetitionVariables.ASSISTS.value:
                    startingVariable = startingParticipantValues.data.core.summary.assists
                    newVariable = participantValues.data.core.summary.assists
                    
                elif competitionVariable == HaloInfiniteCompetitionVariables.EMP_ASSISTS.value:
                    startingVariable = startingParticipantValues.data.core.breakdowns.assists.emp
                    newVariable = participantValues.data.core.breakdowns.assists.emp

                elif competitionVariable == HaloInfiniteCompetitionVariables.DRIVER_ASSISTS.value:
                    startingVariable = startingParticipantValues.data.core.breakdowns.assists.driver
                    newVariable = participantValues.data.core.breakdowns.assists.driver

                elif competitionVariable == HaloInfiniteCompetitionVariables.CALLOUT_ASSISTS.value:
                    startingVariable = startingParticipantValues.data.core.breakdowns.assists.callouts
                    newVariable = participantValues.data.core.breakdowns.assists.callouts

                elif competitionVariable == HaloInfiniteCompetitionVariables.VEHICLES_DESTROYED.value:
                    startingVariable = startingParticipantValues.data.core.summary.vehicles.destroys
                    newVariable = participantValues.data.core.summary.vehicles.destroys

                elif competitionVariable == HaloInfiniteCompetitionVariables.VEHICLES_HIJACKED.value:
                    startingVariable = startingParticipantValues.data.core.summary.vehicles.hijacks
                    newVariable = participantValues.data.core.summary.vehicles.hijacks

                elif competitionVariable == HaloInfiniteCompetitionVariables.MATCHES_WON.value:
                    startingVariable = startingParticipantValues.data.core.breakdowns.matches.wins
                    newVariable = participantValues.data.core.breakdowns.matches.wins

                elif competitionVariable == HaloInfiniteCompetitionVariables.MATCHES_PLAYED.value:
                    startingVariable = startingParticipantValues.data.matches_played
                    newVariable = participantValues.data.matches_played

                elif competitionVariable == HaloInfiniteCompetitionVariables.TIME_PLAYED.value:
                    startingVariable = startingParticipantValues.data.time_played.seconds
                    newVariable = participantValues.data.time_played.seconds

                elif competitionVariable == HaloInfiniteCompetitionVariables.TOTAL_SCORE.value:
                    startingVariable = startingParticipantValues.data.core.total_score
                    newVariable = participantValues.data.core.total_score

                elif competitionVariable == HaloInfiniteCompetitionVariables.MEDALS.value:
                    startingVariable = startingParticipantValues.data.core.summary.medals
                    newVariable = participantValues.data.core.summary.medals

                elif competitionVariable == HaloInfiniteCompetitionVariables.SHOTS_LANDED.value:
                    startingVariable = startingParticipantValues.data.core.shots.landed
                    newVariable = participantValues.data.core.shots.landed

                elif competitionVariable == HaloInfiniteCompetitionVariables.SHOTS_FIRED.value:
                    startingVariable = startingParticipantValues.data.core.shots.fired
                    newVariable = participantValues.data.core.shots.fired

                elif competitionVariable == HaloInfiniteCompetitionVariables.SHOT_ACCURACY.value:
                    startingVariable = startingParticipantValues.data.core.shots.accuracy
                    newVariable = participantValues.data.core.shots.accuracy

                elif competitionVariable == HaloInfiniteCompetitionVariables.WIN_RATE.value:
                    startingVariable = startingParticipantValues.data.win_rate
                    newVariable = participantValues.data.win_rate
                    numDecimalPlaces = 4

                elif competitionVariable == HaloInfiniteCompetitionVariables.KDA_RATIO.value:
                    startingVariable = startingParticipantValues.data.core.kda
                    newVariable = participantValues.data.core.kda
                    numDecimalPlaces = 4

                elif competitionVariable == HaloInfiniteCompetitionVariables.KD_RATIO.value:
                    startingVariable = startingParticipantValues.data.core.kdr
                    newVariable = participantValues.data.core.kdr
                    numDecimalPlaces = 4

                diff = newVariable - startingVariable
                if type(diff) is Decimal:
                    diff = diff.normalize()
                diff = str(diff)
                if diff not in playerProgressData:
                    playerProgressData[diff] = []
                playerProgressData[diff].append({'id': participantId, 'wins': participantValues.wins}) 

        guild = await self.client.fetch_guild(serverId)
        if assignRoles and 'role_halo_recent' in serverValues:
            recentWinRole = guild.get_role(int(serverValues['role_halo_recent']))
            removeWinRoleSuccess = await utils.removeRoleFromAllUsers(guild, recentWinRole)
        else:
            recentWinRole = None

        sortedPlayerProgressData = OrderedDict(sorted(playerProgressData.items(), key = lambda scoreGroup: Decimal(scoreGroup[0]), reverse = True))
        bodyList = []
        playerWinCounts = {}
        winnersStr = ''
        placeNumber = 1
        addWinRoleSuccess = False
        for score, scoreGroupValues in sortedPlayerProgressData.items():
            incrementPlaceNumber = False
            for participantObj in scoreGroupValues:
                participantId = participantObj['id']
                participantWins = participantObj['wins']
                user = await guild.fetch_member(participantId)
                sender = { 'id': None, 'name': 'Halo' }
                receiver = { 'id': participantId, 'name': user.name }
                if placeNumber == 1 and Decimal(score) != Decimal('0'):
                    winnersStr += utils.idToUserStr(participantId) + ','
                    if recentWinRole != None:
                        participantWins += 1
                        iterAddWinRoleSuccess = await utils.addRoleToUser(user, recentWinRole)
                        if iterAddWinRoleSuccess:
                            addWinRoleSuccess = True
                        halo_queries.setParticipantWinCount(serverId, participantId, participantWins)
                    if participantWins not in playerWinCounts:
                        playerWinCounts[participantWins] = []
                    playerWinCounts[participantWins].append(participantId)
                    # GCoin integration; daily and weekly winner rewards
                    if isGCoinEnabled:
                        gcoin_queries.performTransaction(self.GCOIN_DAILY_WIN_REWARD, date, sender, receiver, '', 'Daily Win', False, False)
                        if assignRoles:
                            gcoin_queries.performTransaction(self.GCOIN_WEEKLY_WIN_REWARD, date, sender, receiver, '', 'Weekly Win', False, False)
                else:
                    if participantWins not in playerWinCounts:
                        playerWinCounts[participantWins] = []
                    playerWinCounts[participantWins].append(participantId)
                if Decimal(score) != Decimal('0') or participantWins > 0:
                    incrementPlaceNumber = True
                    userStr = user.nick if user.nick else user.name
                    roundedScore = score
                    if numDecimalPlaces > 0:
                        roundedScore = str(utils.roundDecimalPlaces(score, numDecimalPlaces))
                    bodyList.append({'Place': str(placeNumber), 'Player': userStr, competitionVariable: roundedScore, 'Weekly Wins': str(participantWins)})
                # GCoin integration; weekly participation reward
                if isGCoinEnabled and Decimal(score) != Decimal('0') and assignRoles:
                    gcoin_queries.performTransaction(self.GCOIN_WEEKLY_PARTICIPATION_REWARD, date, sender, receiver, '', 'Participation', False, False)
            if incrementPlaceNumber:
                placeNumber += 1

        if assignRoles and 'role_halo_most' in serverValues:
            mostWinsRole = guild.get_role(int(serverValues['role_halo_most']))
            removeMostRoleSuccess = await utils.removeRoleFromAllUsers(guild, mostWinsRole)
        else:
            mostWinsRole = None

        mostWinsStr = ''
        addMostRoleSuccess = False
        if mostWinsRole != None:
            sortedPlayerWinCounts = OrderedDict(sorted(playerWinCounts.items(), key = lambda winGroup: winGroup[0], reverse = True))
            for group in sortedPlayerWinCounts.values():
                for participantId in group:
                    mostWinsStr += utils.idToUserStr(participantId) + ','
                    user = await guild.fetch_member(participantId)
                    iterAddMostRoleSuccess = await utils.addRoleToUser(user, mostWinsRole)
                    if iterAddMostRoleSuccess:
                        addMostRoleSuccess = True
                break

        if winnersStr != '':
            recentRoleStr = ''
            if recentWinRole != None and removeWinRoleSuccess and addWinRoleSuccess:
                recentRoleStr = f' and were assigned {recentWinRole.mention}'
            mostRoleStr = ''
            if mostWinsRole != None and removeMostRoleSuccess and addMostRoleSuccess:
                mostRoleStr = f' {mostWinsStr} you have the most wins and were assigned {mostWinsRole.mention}!'
            if assignRoles:
                winnersStr = f"{winnersStr} you won this week's challenge{recentRoleStr}!\n{mostRoleStr}"
            else:
                winnersStr = f"{winnersStr} you are in the lead!"
        else:
            winnersStr = 'No active players.'

        if not bodyList:
            isTable = False
        else:
            colList = ['Place', 'Player', competitionVariable, 'Weekly Wins']
            colWidth = [0.75, 2.7, 2.7, 1.1]
            utils.createTempTableImage(bodyList, colList, 'GBot: Halo Infinite Weekly Challenges', colWidth)
            isTable = True
        return (winnersStr, isTable)

    # Commands
    @commands.command(aliases=['h'], brief = "- Participate in or leave the weekly GBot Halo competition. (admin optional)", description = "Participate in or leave the weekly GBot Halo competition. (admin optional)\naction options are: <gamertag>, rm")
    @predicates.isFeatureEnabledForServer('toggle_halo')
    @predicates.isMessageSentInGuild()
    async def halo(self, ctx: Context, action = None, user: nextcord.User = None):
        guild = ctx.guild
        serverId = guild.id
        author = ctx.author
        authorMention = author.mention
        if user != None:
            if not utils.isUserAdminOrOwner(author, guild):
                await ctx.send(f'Sorry {authorMention}, you need to be an admin to add or remove other participants.')
                return
            if not await utils.isUserInGuild(user, ctx.guild):
                await ctx.send(f"Sorry {authorMention}, please specify a user in this guild.")
                return
            userId = user.id
            userMention = user.mention
        else:
            userId = author.id
            userMention = authorMention
        if action == None or action.startswith('<@'):
            await ctx.send(f'Sorry {authorMention}, you need to specify a gamertag or type \'rm\'.')
            return
        isParticipating = halo_queries.isUserParticipatingInHalo(serverId, userId)
        if action == 'rm':
            if isParticipating:
                halo_queries.removeHaloParticipant(serverId, userId)
                await ctx.send(f'{userMention} has been removed as a Halo Infinite participant.')
            else:
                await ctx.send(f'{userMention} is not participating in Halo Infinite.')
        else:
            response = await self.haloPlayerStatsGetRequest(action)
            if not response:
                await ctx.send(f'Sorry {userMention}, {action} is not a valid gamertag.')
                return
            halo_queries.addHaloParticipant(serverId, userId, action)
            await ctx.send(f'{userMention} has been added as a Halo Infinite participant as {action}.')

def setup(client: commands.Bot):
    client.add_cog(Halo(client))