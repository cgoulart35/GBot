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

import utils
import predicates
import halo.queries
import config.queries
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
        self.SEASON_ONE_IMG_PATH = f'{self.parentDir}/images/haloInfiniteSeasonOne.jpg'
        self.HALO_COMPETITION_VARIABLES = [
            'Kills',
            'Melee Kills',
            'Grenade Kills',
            'Headshot Kills',
            'Power Weapon Kills',
            'Assists',
            'Emp Assists',
            'Driver Assists',
            'Callout Assists',
            'Vehicles Destroyed',
            'Vehicles Hijacked',
            'Matches Won',
            'Matches Played',
            'Time Played',
            'Total Score',
            'Medals',
            'Shots Landed',
            'Shots Fired',
            'Shot Accuracy (%)',
            'Win Rate (%)',
            'KDA Ratio',
            'KD Ratio'
        ]
        self.HALO_API_VERSION = '0.3.9'
        self.HALO_API_HOST = f'https://halo.api.stdlib.com/infinite@{self.HALO_API_VERSION}'
        self.HALO_API_STATS = f'/stats/service-record/multiplayer'
        self.HALO_API_MOTD = f'/articles/list/'
    
    # Events
    @commands.Cog.listener()
    async def on_guild_remove(self, guild: nextcord.Guild):
        self.logger.info(f'Deleting Halo Infinite data for guild {guild.id} ({guild.name}).')
        halo.queries.deleteServerHaloValues(guild.id)

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
        servers = config.queries.getAllServers()
        for serverId, serverValues in servers.items():
            if serverValues['toggle_halo'] and 'channel_halo_motd' in serverValues:
                oldJsonMOTD = halo.queries.getLastHaloInfiniteMOTD(serverId)
                oldStrMOTD = json.dumps(oldJsonMOTD, sort_keys = True)
                if newStrMOTD != oldStrMOTD:
                    halo.queries.postHaloInfiniteMOTD(serverId, date, newJsonMOTD)
                    # filter out updates that have been posted before to reduce server posting
                    updatesToPost = []
                    for message in newJsonMOTD['data']:
                        if oldJsonMOTD == '' or message not in oldJsonMOTD['data']:
                            updatesToPost.append(message)
                    channel: nextcord.TextChannel = await self.client.fetch_channel(serverValues['channel_halo_motd'])
                    for msg in updatesToPost:
                        msgTitle = msg['title']
                        msgText = msg['message']
                        msgImgUrl = msg['image_url']
                        if await utils.isUrlImageContentTypeAndStatus200(msgImgUrl):
                            messageImg = None
                            messageUrl = msgImgUrl
                        else:
                            messageImg = nextcord.File(self.SEASON_ONE_IMG_PATH)
                            messageUrl = None
                        await utils.sendDiscordEmbed(channel, msgTitle, msgText, nextcord.Color.purple(), messageImg, messageUrl)

    async def haloPlayerStatsGetRequests(self):
        self.logger.info('Retrieving Halo Infinite Player Stats...')
        dateTimeObj = datetime.now()
        date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")
        allServerConfigs = config.queries.getAllServers()
        allHaloInfiniteServers = halo.queries.getAllHaloInfiniteServers()
        obtainedPlayerData = {}
        for serverId, serverValues in allServerConfigs.items():
            freshPlayerDataCompetition = { 'start_day': date, 'participants': {} }
            if serverValues['toggle_halo'] and 'channel_halo_competition' in serverValues:
                nextCompetitionId = halo.queries.getNextCompetitionId(serverId)
                channel: nextcord.TextChannel = await self.client.fetch_channel(serverValues['channel_halo_competition'])
                try:
                    players = allHaloInfiniteServers[serverId]['participating_players']
                    # always filter only those participating
                    players = dict(filter(lambda playerItem: halo.queries.isUserParticipatingInHalo(serverId, playerItem[0]), players.items()))
                    # if it is not competition announcement day, filter participating players to those only who had data grabbed at start of week to limit API cost
                    if str(dateTimeObj.weekday()) != self.HALO_COMPETITION_DAY:
                        players = dict(filter(lambda playerItem: halo.queries.isUserInThisWeeksInitialDataFetch(serverId, nextCompetitionId - 1, playerItem[0]), players.items()))
                    
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
                    freshPlayerDataCompetition['participants'][playerId] = playerDataJson

                # if it is new competition time, post the data to database and announce winners
                if str(dateTimeObj.weekday()) == self.HALO_COMPETITION_DAY:
                    competitionVariable = random.choice(self.HALO_COMPETITION_VARIABLES)
                    freshPlayerDataCompetition['competition_variable'] = competitionVariable
                    halo.queries.postHaloInfiniteServerPlayerData(serverId, nextCompetitionId, freshPlayerDataCompetition)
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
                        winnersAndTable = await self.generatePlayerProgressTableAndWinners(serverId, nextCompetitionId - 1, freshPlayerDataCompetition, serverValues, True)

                        headerStr1 = f'**Week  {nextCompetitionId - 1}  Results!**'
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
                        winnersAndTable = await self.generatePlayerProgressTableAndWinners(serverId, nextCompetitionId - 1, freshPlayerDataCompetition, serverValues, False)
                        
                        headerStr = f'**Week  {nextCompetitionId - 1}  Progress!**'
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

    async def generatePlayerProgressTableAndWinners(self, serverId, competitionId, newCompetitionDataJson, serverValues, assignRoles):
        playerProgressData = {}
        startingCompetitionDataJson = halo.queries.getThisWeeksInitialDataFetch(serverId, competitionId)
        if startingCompetitionDataJson != None and 'competition_variable' in startingCompetitionDataJson and 'participants' in startingCompetitionDataJson:
            competitionVariable = startingCompetitionDataJson['competition_variable']
            players = newCompetitionDataJson['participants']
            # always filter participating players to those only who had data grabbed at start of week for functionality purposes
            players = dict(filter(lambda playerItem: halo.queries.isUserInThisWeeksInitialDataFetch(serverId, competitionId, playerItem[0]), players.items()))
            for participantId, participantValues in players.items():
                if competitionVariable == 'Kills':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['core']['summary']['kills']
                    newVariable = participantValues['data']['core']['summary']['kills']

                elif competitionVariable == 'Melee Kills':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['core']['breakdowns']['kills']['melee']
                    newVariable = participantValues['data']['core']['breakdowns']['kills']['melee']

                elif competitionVariable == 'Grenade Kills':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['core']['breakdowns']['kills']['grenades']
                    newVariable = participantValues['data']['core']['breakdowns']['kills']['grenades']

                elif competitionVariable == 'Headshot Kills':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['core']['breakdowns']['kills']['headshots']
                    newVariable = participantValues['data']['core']['breakdowns']['kills']['headshots']

                elif competitionVariable == 'Power Weapon Kills':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['core']['breakdowns']['kills']['power_weapons']
                    newVariable = participantValues['data']['core']['breakdowns']['kills']['power_weapons']

                elif competitionVariable == 'Assists':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['core']['summary']['assists']
                    newVariable = participantValues['data']['core']['summary']['assists']
                    
                elif competitionVariable == 'Emp Assists':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['core']['breakdowns']['assists']['emp']
                    newVariable = participantValues['data']['core']['breakdowns']['assists']['emp']

                elif competitionVariable == 'Driver Assists':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['core']['breakdowns']['assists']['driver']
                    newVariable = participantValues['data']['core']['breakdowns']['assists']['driver']

                elif competitionVariable == 'Callout Assists':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['core']['breakdowns']['assists']['callouts']
                    newVariable = participantValues['data']['core']['breakdowns']['assists']['callouts']

                elif competitionVariable == 'Vehicles Destroyed':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['core']['summary']['vehicles']['destroys']
                    newVariable = participantValues['data']['core']['summary']['vehicles']['destroys']

                elif competitionVariable == 'Vehicles Hijacked':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['core']['summary']['vehicles']['hijacks']
                    newVariable = participantValues['data']['core']['summary']['vehicles']['hijacks']

                elif competitionVariable == 'Matches Won':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['core']['breakdowns']['matches']['wins']
                    newVariable = participantValues['data']['core']['breakdowns']['matches']['wins']

                elif competitionVariable == 'Matches Played':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['matches_played']
                    newVariable = participantValues['data']['matches_played']

                elif competitionVariable == 'Time Played':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['time_played']['seconds']
                    newVariable = participantValues['data']['time_played']['seconds']

                elif competitionVariable == 'Total Score':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['core']['total_score']
                    newVariable = participantValues['data']['core']['total_score']

                elif competitionVariable == 'Medals':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['core']['summary']['medals']
                    newVariable = participantValues['data']['core']['summary']['medals']

                elif competitionVariable == 'Shots Landed':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['core']['shots']['landed']
                    newVariable = participantValues['data']['core']['shots']['landed']

                elif competitionVariable == 'Shots Fired':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['core']['shots']['fired']
                    newVariable = participantValues['data']['core']['shots']['fired']

                elif competitionVariable == 'Shot Accuracy (%)':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['core']['shots']['accuracy']
                    newVariable = participantValues['data']['core']['shots']['accuracy']

                elif competitionVariable == 'Win Rate (%)':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['win_rate']
                    newVariable = participantValues['data']['win_rate']

                elif competitionVariable == 'KDA Ratio':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['core']['kda']
                    newVariable = participantValues['data']['core']['kda']

                elif competitionVariable == 'KD Ratio':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['core']['kdr']
                    newVariable = participantValues['data']['core']['kdr']

                diff = str(Decimal(str(newVariable)) - Decimal(str(startingVariable)))
                if diff not in playerProgressData:
                    playerProgressData[diff] = []
                playerProgressData[diff].append({'id': participantId, 'wins': participantValues['wins']}) 

        guild = await self.client.fetch_guild(serverId)
        if assignRoles and 'role_halo_recent' in serverValues:
            recentWinRole = guild.get_role(serverValues['role_halo_recent'])
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
                if placeNumber == 1 and Decimal(score) != Decimal('0'):
                    winnersStr += utils.idToUserStr(participantId) + ','
                    if recentWinRole != None:
                        participantWins += 1
                        iterAddWinRoleSuccess = await utils.addRoleToUser(user, recentWinRole)
                        if iterAddWinRoleSuccess:
                            addWinRoleSuccess = True
                        halo.queries.setParticipantWinCount(serverId, participantId, participantWins)
                    if participantWins not in playerWinCounts:
                        playerWinCounts[participantWins] = []
                    playerWinCounts[participantWins].append(participantId)   
                else:
                    if participantWins not in playerWinCounts:
                        playerWinCounts[participantWins] = []
                    playerWinCounts[participantWins].append(participantId)
                if Decimal(score) != Decimal('0') or participantWins > 0:
                    incrementPlaceNumber = True
                    userStr = user.nick if user.nick else user.name
                    roundedScore = str(utils.roundDecimalPlaces(score, 4))
                    bodyList.append({'Place': str(placeNumber), 'Player': userStr, competitionVariable: roundedScore, 'Weekly Wins': str(participantWins)})
            if incrementPlaceNumber:
                placeNumber += 1

        if assignRoles and 'role_halo_most' in serverValues:
            mostWinsRole = guild.get_role(serverValues['role_halo_most'])
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
        isParticipating = halo.queries.isUserParticipatingInHalo(serverId, userId)
        if action == None or action == 'rm':
            if isParticipating:
                halo.queries.removeHaloParticipant(serverId, userId)
                await ctx.send(f'{userMention} has been removed as a Halo Infinite participant.')
            else:
                await ctx.send(f'{userMention} is not participating in Halo Infinite.')
        else:
            response = await self.haloPlayerStatsGetRequest(action)
            if not response:
                await ctx.send(f'Sorry {userMention}, {action} is not a valid gamertag.')
                return
            halo.queries.addHaloParticipant(serverId, userId, action)
            await ctx.send(f'{userMention} has been added as a Halo Infinite participant as {action}.')

def setup(client: commands.Bot):
    client.add_cog(Halo(client))