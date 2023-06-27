# #region IMPORTS
# import pathlib
# import os
# import logging
# import json
# import random
# import httpx
# import nextcord
# from nextcord.ext import commands, tasks
# from nextcord.ext.commands.context import Context
# from datetime import datetime
# from decimal import Decimal
# from urllib import parse
# from collections import OrderedDict

# from GBotDiscord.src import strings
# from GBotDiscord.src import utils
# from GBotDiscord.src import predicates
# from GBotDiscord.src.config import config_queries
# from GBotDiscord.src.gcoin import gcoin_queries
# from GBotDiscord.src.halo import halo_queries
# from GBotDiscord.src.halo.halo_models import HaloInfiniteCompetitionVariables, HaloInfiniteWeeklyCompetitionModel, HaloInfiniteParticipantModel
# from GBotDiscord.src.properties import GBotPropertiesManager
# #endregion

# Missed Features: 
# - implement slash commands
# - fix multi-instance issues

# class Halo(commands.Cog):

#     def __init__(self, client: nextcord.Client):
#         self.client = client
#         self.logger = logging.getLogger()
#         self.parentDir = str(pathlib.Path(__file__).parent.parent.absolute()).replace("\\",'/')
#         self.HALO_IMG_PATH = f'{self.parentDir}/images/haloInfiniteImage.jpg'
#         self.HALO_SEASON_IMG_PATH = f'{self.parentDir}/images/haloInfiniteSeasonTwo.jpg'
#         self.GCOIN_DAILY_WIN_REWARD = Decimal('0.14')
#         self.GCOIN_WEEKLY_PARTICIPATION_REWARD = Decimal('0.50')
#         self.GCOIN_WEEKLY_WIN_REWARD = Decimal('1.00')
#         self.HALO_API_VERSION = '0.3.9'
#         self.HALO_API_HOST = f'https://halo.api.stdlib.com/infinite@{self.HALO_API_VERSION}'
#         self.HALO_API_STATS = f'/stats/service-record/multiplayer'
#         self.HALO_API_MOTD = f'/articles/list/'
    
#     # Events
#     @commands.Cog.listener()
#     async def on_guild_remove(self, guild: nextcord.Guild):
#         self.logger.info(f'Deleting Halo Infinite data for guild {guild.id} ({guild.name}).')
#         halo_queries.deleteServerHaloValues(guild.id)

#     @commands.Cog.listener()
#     async def on_ready(self):
#         try:
#             self.wait_to_start_batch_halo_MOTD.start()
#         except RuntimeError:
#             self.logger.info('wait_to_start_batch_halo_MOTD task is already launched and is not completed.')
#         try:
#             self.wait_to_start_batch_halo_player_stats.start()
#         except RuntimeError:
#             self.logger.info('wait_to_start_batch_halo_player_stats task is already launched and is not completed.')

#     # Tasks
#     @tasks.loop(minutes=1)
#     async def wait_to_start_batch_halo_MOTD(self):
#         dateTimeObj = datetime.now()
#         if dateTimeObj.hour == GBotPropertiesManager.HALO_INFINITE_MOTD_HOUR and dateTimeObj.minute == GBotPropertiesManager.HALO_INFINITE_MOTD_MINUTE:
#             self.wait_to_start_batch_halo_MOTD.cancel()
#             self.logger.info('Initial kickoff time reached. Starting Halo Infinite MOTD batch job...')
#             try:
#                 self.batch_halo_MOTD.start()
#             except RuntimeError:
#                 self.logger.info('batch_halo_MOTD task is already launched and is not completed.')

#     @tasks.loop(minutes=1)
#     async def wait_to_start_batch_halo_player_stats(self):
#         dateTimeObj = datetime.now()
#         if dateTimeObj.hour == GBotPropertiesManager.HALO_INFINITE_COMPETITION_HOUR and dateTimeObj.minute == GBotPropertiesManager.HALO_INFINITE_COMPETITION_MINUTE:
#             self.wait_to_start_batch_halo_player_stats.cancel()
#             self.logger.info('Initial kickoff time reached. Starting Halo Infinite Player Stats batch job...')
#             try:
#                 self.batch_halo_player_stats.start()
#             except RuntimeError:
#                 self.logger.info('batch_halo_player_stats task is already launched and is not completed.')

#     @tasks.loop(hours=24)
#     async def batch_halo_MOTD(self):
#         await self.haloMotdGetRequest(selectedServerId = None)

#     @tasks.loop(hours=24)
#     async def batch_halo_player_stats(self):
#         await self.haloPlayerStatsGetRequests(selectedServerId = None, startCompetition = None)

#     async def haloMotdGetRequest(self, selectedServerId):
#         async with httpx.AsyncClient() as httpxClient:
#             self.logger.info('Retrieving latest Halo Infinite MOTD...')
#             url = self.HALO_API_HOST + self.HALO_API_MOTD
#             autocodeToken = GBotPropertiesManager.AUTOCODE_TOKEN
#             headers = { 'Authorization': f'Bearer {autocodeToken}' }
#             response = await httpxClient.get(url, headers = headers, timeout = 60)
#             if response.status_code != 200:
#                 self.logger.error(f'Error retrieving message data: {response.text}')
#             else:
#                 newJsonMOTD = response.json()
#                 await self.haloMotdSendDiscord(newJsonMOTD, selectedServerId)

#     async def haloMotdSendDiscord(self, newJsonMOTD, selectedServerId):
#         newStrMOTD = json.dumps(newJsonMOTD, sort_keys = True)
#         dateTimeObj = datetime.now()
#         date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")

#         # update for all servers or selected server
#         if selectedServerId is None:
#             self.logger.info('Calculating all server Halo Infinite MOTD updates...')
#             servers = config_queries.getAllServers()
#         else:
#             self.logger.info(f'Calculating Halo Infinite MOTD updates for server {selectedServerId}...')
#             selectedServerValues = config_queries.getAllServerValues(selectedServerId)
#             servers = { selectedServerId: selectedServerValues }

#         for serverId, serverValues in servers.items():
#             if serverValues['toggle_halo'] and 'channel_halo_motd' in serverValues:
#                 oldJsonMOTD = halo_queries.getLastHaloInfiniteMOTD(serverId)
#                 oldStrMOTD = json.dumps(oldJsonMOTD, sort_keys = True)
#                 if newStrMOTD != oldStrMOTD:
#                     halo_queries.postHaloInfiniteMOTD(serverId, date, newJsonMOTD)
#                     # filter out updates that have been posted before to reduce server posting
#                     updatesToPost = []
#                     for message in newJsonMOTD['data']:
#                         if oldJsonMOTD == '' or message not in oldJsonMOTD['data']:
#                             updatesToPost.append(message)
#                     channel: nextcord.TextChannel = await self.client.fetch_channel(int(serverValues['channel_halo_motd']))
#                     for msg in updatesToPost:
#                         msgTitle = msg['title']
#                         msgText = msg['message']
#                         msgImgUrl = msg['image_url']
#                         if await utils.isUrlImageContentTypeAndStatus200(msgImgUrl):
#                             messageImg = None
#                             messageUrl = msgImgUrl
#                         else:
#                             messageImg = nextcord.File(self.HALO_SEASON_IMG_PATH)
#                             messageUrl = None
#                         await utils.sendDiscordEmbed(channel, msgTitle, msgText, nextcord.Color.purple(), messageImg, messageUrl)

#     async def haloPlayerStatsGetRequests(self, selectedServerId, startCompetition):
#         dateTimeObj = datetime.now()
#         date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")

#         # if it is time to announce winners
#         isCompetitionAnnouncement = dateTimeObj.weekday() == GBotPropertiesManager.HALO_INFINITE_COMPETITION_DAY

#         # if instructions specified, override isCompetitionAnnouncement to desired value
#         if startCompetition != None:
#             isCompetitionAnnouncement = startCompetition

#         # update for all servers or selected server
#         if selectedServerId is None:
#             self.logger.info('Retrieving Halo Infinite Player Stats for all servers...')
#             allServerConfigs = config_queries.getAllServers()
#             allHaloInfiniteServers = halo_queries.getAllHaloInfiniteServers()
#         else:
#             self.logger.info(f'Retrieving Halo Infinite Player Stats for server {selectedServerId}...')
#             selectedServerConfigs = config_queries.getAllServerValues(selectedServerId)
#             allServerConfigs = { selectedServerId: selectedServerConfigs }
#             selectedHaloInfiniteServer = halo_queries.getHaloInfiniteServer(selectedServerId)
#             allHaloInfiniteServers = { selectedServerId: selectedHaloInfiniteServer }

#         obtainedPlayerData = {}
#         for serverId, serverValues in allServerConfigs.items():
#             # GCoin integration
#             isGCoinEnabled = config_queries.getServerValue(serverId, 'toggle_gcoin')
#             gcoinRewardsStr = " (Halo GCoin Rewards Enabled)" if isGCoinEnabled else ''

#             freshPlayerDataCompetition = HaloInfiniteWeeklyCompetitionModel('', {}, date)
#             if serverValues['toggle_halo'] and 'channel_halo_competition' in serverValues:
#                 nextCompetitionId = halo_queries.getNextCompetitionId(serverId)
#                 channel: nextcord.TextChannel = await self.client.fetch_channel(int(serverValues['channel_halo_competition']))
#                 try:
#                     players = allHaloInfiniteServers[serverId]['participating_players']
#                     # always filter only those participating
#                     players = dict(filter(lambda playerItem: halo_queries.isUserParticipatingInHalo(serverId, playerItem[0]), players.items()))
#                     # if it is not competition announcement day, filter participating players to those only who had data grabbed at start of week to limit API cost
#                     if not isCompetitionAnnouncement:
#                         players = dict(filter(lambda playerItem: halo_queries.isUserInThisWeeksInitialDataFetch(serverId, nextCompetitionId - 1, playerItem[0]), players.items()))
                    
#                 except Exception:
#                     players = {}
#                 for playerId, playerValues in players.items():
#                     gamertag = playerValues['gamertag']
#                     wins = playerValues['wins']
#                     if gamertag not in obtainedPlayerData:
#                         playerDataJson = await self.haloPlayerStatsGetRequest(gamertag)
#                         if not playerDataJson:
#                             if 'channel_admin' in serverValues:
#                                 adminChannel: nextcord.TextChannel = await self.client.fetch_channel(int(serverValues['channel_admin']))
#                                 await adminChannel.send(f"There was an error retrieving Halo Infinite player data for {utils.idToUserStr(playerId)} (Gamertag: {gamertag}).")
#                             continue
#                         obtainedPlayerData[gamertag] = playerDataJson
#                     else:
#                         playerDataJson = obtainedPlayerData[gamertag]
#                     playerDataJson['wins'] = wins
#                     freshPlayerDataCompetition.participants[playerId] = HaloInfiniteParticipantModel.createObjectFromDatabaseOrAPI(playerDataJson)

#                 # if it is new competition time, post the data to database and announce winners
#                 if isCompetitionAnnouncement:
#                     competitionVariable = random.choice(list(HaloInfiniteCompetitionVariables)).value
#                     freshPlayerDataCompetition.competition_variable = competitionVariable
#                     halo_queries.postHaloInfiniteServerPlayerData(serverId, nextCompetitionId, freshPlayerDataCompetition)
#                     if nextCompetitionId == 0:
#                         headerStr = "**Week  0:  The  week  you  probably  didn't  even  know  about...**"
#                         descriptionStr = 'Hello there! Week 1 of Halo Infinite challenges starts a week from right now!\nSign up before the next week starts to be included in random weekly challenges!\n\nUse the commands below to participate in the weekly Halo Infinite challenges.\n\n__Participate:__\n.halo YOUR_GAMERTAG\n__Leave:__\n.halo rm'
#                         haloImg = nextcord.File(self.HALO_IMG_PATH)
#                         await utils.sendDiscordEmbed(channel, headerStr, descriptionStr, nextcord.Color.dark_blue(), haloImg)
#                         continue
#                     elif nextCompetitionId == 1:
#                         headerStr = '**Week  1:  The  competition  starts  now!**'
#                         descriptionStr = f'__Random Competition Variable:__\n{competitionVariable}\n\nForget to participate for Week 1? No worries!\nSign up before the next week starts to be included in random weekly challenges!\n\nUse the commands below to participate in the weekly Halo Infinite challenges.\n\n__Participate:__\n.halo YOUR_GAMERTAG\n__Leave:__\n.halo rm'
#                         haloImg = nextcord.File(self.HALO_IMG_PATH)
#                         await utils.sendDiscordEmbed(channel, headerStr, descriptionStr, nextcord.Color.dark_blue(), haloImg)
#                         continue
#                     else:
#                         winnersAndTable = await self.generatePlayerProgressTableAndWinners(serverId, nextCompetitionId - 1, freshPlayerDataCompetition, serverValues, True, isGCoinEnabled, date)

#                         headerStr1 = f'**Week  {nextCompetitionId - 1}  Results!{gcoinRewardsStr}**'
#                         await utils.sendDiscordEmbed(channel, headerStr1, winnersAndTable[0], nextcord.Color.green())

#                         headerStr2 = f'**Week  {nextCompetitionId}**'
#                         nextWeekStr = f"__Random Competition Variable:__\n{competitionVariable}\n\nHaven't participated yet? No worries!\nSign up before the next week starts to be included in random weekly challenges!\n\nUse the commands below to participate in the weekly Halo Infinite challenges.\n\n__Participate:__\n.halo YOUR_GAMERTAG\n__Leave:__\n.halo rm"
#                         haloImg = nextcord.File(self.HALO_IMG_PATH)

#                         if winnersAndTable[1]:
#                             tempDataTable = nextcord.File('haloUpdate.png')
#                             await channel.send(file = tempDataTable)
#                             utils.deleteTempTableImage('haloUpdate.png')
                        
#                         await utils.sendDiscordEmbed(channel, headerStr2, nextWeekStr, nextcord.Color.dark_blue(), haloImg)
#                         continue

#                 # if it is not new competition time, don't post the data to database and announce progress
#                 else:
#                     if nextCompetitionId - 1 > 0:
#                         winnersAndTable = await self.generatePlayerProgressTableAndWinners(serverId, nextCompetitionId - 1, freshPlayerDataCompetition, serverValues, False, isGCoinEnabled, date)

#                         headerStr = f'**Week  {nextCompetitionId - 1}  Progress!{gcoinRewardsStr}**'
#                         await utils.sendDiscordEmbed(channel, headerStr, winnersAndTable[0], nextcord.Color.green())

#                         if winnersAndTable[1]:
#                             tempDataTable = nextcord.File('haloUpdate.png')
#                             await channel.send(file = tempDataTable)
#                             utils.deleteTempTableImage('haloUpdate.png')
#                         continue
        
#     async def haloPlayerStatsGetRequest(self, gamertag):
#         async with httpx.AsyncClient() as httpxClient:
#             playerGamertagUrl = parse.quote(gamertag)
#             url = self.HALO_API_HOST + self.HALO_API_STATS + f'/?gamertag={playerGamertagUrl}'
#             autocodeToken = GBotPropertiesManager.AUTOCODE_TOKEN
#             headers = { 'Authorization': f'Bearer {autocodeToken}' }
#             response = await httpxClient.get(url, headers = headers, timeout = 60)
#             if response.status_code != 200:
#                 self.logger.error(f'Error retrieving player data for {gamertag}: {response.text}')
#                 return None
#             return response.json()

#     async def generatePlayerProgressTableAndWinners(self, serverId, competitionId, newCompetitionDataJson: HaloInfiniteWeeklyCompetitionModel, serverValues, assignRoles, isGCoinEnabled, date):
#         guild = await self.client.fetch_guild(serverId)
#         initialDataFetch = halo_queries.getThisWeeksInitialDataFetch(serverId, competitionId)
#         startingCompetitionDataJson: HaloInfiniteWeeklyCompetitionModel = HaloInfiniteWeeklyCompetitionModel.createObjectFromDatabaseOrAPI(initialDataFetch)

#         competitionCalculation = await self.calculatePlayerCompetitionData(startingCompetitionDataJson, newCompetitionDataJson, serverId, competitionId)
#         playerProgressData = competitionCalculation[0]
#         competitionVariable = competitionCalculation[1]
#         numDecimalPlaces = competitionCalculation[2]

#         recentWinRoleInfo = await self.getRoleForRecentHaloWinAndRemoveFromAll(guild, serverValues, assignRoles)
#         recentWinRole = recentWinRoleInfo[0]
#         removeWinRoleSuccess = recentWinRoleInfo[1]

#         sortedPlayerProgressData = OrderedDict(sorted(playerProgressData.items(), key = lambda scoreGroup: Decimal(scoreGroup[0]), reverse = True))

#         placementsInfo = await self.determineWinInfoAndPlacements(sortedPlayerProgressData, guild, recentWinRole, serverId, isGCoinEnabled, date, assignRoles, numDecimalPlaces, competitionVariable)
#         bodyList = placementsInfo[0]
#         playerWinCounts = placementsInfo[1]
#         winnersStr = placementsInfo[2]
#         addWinRoleSuccess = placementsInfo[3]

#         mostWinRoleInfo = await self.getRoleForMostHaloWinAndRemoveFromAll(guild, serverValues, assignRoles)
#         mostWinsRole = mostWinRoleInfo[0]
#         removeMostRoleSuccess = mostWinRoleInfo[1]

#         mostWinsInfo = await self.buildMostWinsStringAndAddRoles(mostWinsRole, playerWinCounts, guild)
#         mostWinsStr = mostWinsInfo[0]
#         addMostRoleSuccess = mostWinsInfo[1]

#         winnersStr = self.buildWinnersString(recentWinRole, removeWinRoleSuccess, addWinRoleSuccess, winnersStr, mostWinsRole, removeMostRoleSuccess, addMostRoleSuccess, mostWinsStr, assignRoles)

#         if not bodyList:
#             isTable = False
#         else:
#             colList = ['Place', 'Player', competitionVariable, 'Weekly Wins']
#             colWidth = [0.75, 2.7, 2.7, 1.1]
#             title  = 'GBot: Halo Infinite Weekly Challenges'
#             utils.createTempTableImage('haloUpdate.png', bodyList, colList, colWidth, title, 'black', '#2DF904')
#             isTable = True
#         return (winnersStr, isTable)

#     async def calculatePlayerCompetitionData(self, startingCompetitionDataJson: HaloInfiniteWeeklyCompetitionModel, newCompetitionDataJson: HaloInfiniteWeeklyCompetitionModel, serverId, competitionId):
#             playerProgressData = {}
#             numDecimalPlaces = 0
#             if startingCompetitionDataJson != None and startingCompetitionDataJson.competition_variable != None and startingCompetitionDataJson.participants != None:
#                 competitionVariable = startingCompetitionDataJson.competition_variable
#                 players: dict[HaloInfiniteParticipantModel] = newCompetitionDataJson.participants
#                 # always filter participating players to those only who had data grabbed at start of week for functionality purposes
#                 players = dict(filter(lambda playerItem: halo_queries.isUserInThisWeeksInitialDataFetch(serverId, competitionId, playerItem[0]), players.items()))
#                 for participantId, participantValues in players.items():
#                     participantValues: HaloInfiniteParticipantModel
#                     startingParticipantValues: HaloInfiniteParticipantModel = startingCompetitionDataJson.participants[participantId]
#                     if competitionVariable == HaloInfiniteCompetitionVariables.KILLS.value:
#                         startingVariable = startingParticipantValues.data.core.summary.kills
#                         newVariable = participantValues.data.core.summary.kills

#                     elif competitionVariable == HaloInfiniteCompetitionVariables.MELEE_KILLS.value:
#                         startingVariable = startingParticipantValues.data.core.breakdowns.kills.melee
#                         newVariable = participantValues.data.core.breakdowns.kills.melee

#                     elif competitionVariable == HaloInfiniteCompetitionVariables.GRENADE_KILLS.value:
#                         startingVariable = startingParticipantValues.data.core.breakdowns.kills.grenades
#                         newVariable = participantValues.data.core.breakdowns.kills.grenades

#                     elif competitionVariable == HaloInfiniteCompetitionVariables.HEADSHOT_KILLS.value:
#                         startingVariable = startingParticipantValues.data.core.breakdowns.kills.headshots
#                         newVariable = participantValues.data.core.breakdowns.kills.headshots

#                     elif competitionVariable == HaloInfiniteCompetitionVariables.POWER_WEAPON_KILLS.value:
#                         startingVariable = startingParticipantValues.data.core.breakdowns.kills.power_weapons
#                         newVariable = participantValues.data.core.breakdowns.kills.power_weapons

#                     elif competitionVariable == HaloInfiniteCompetitionVariables.ASSISTS.value:
#                         startingVariable = startingParticipantValues.data.core.summary.assists
#                         newVariable = participantValues.data.core.summary.assists
                        
#                     elif competitionVariable == HaloInfiniteCompetitionVariables.EMP_ASSISTS.value:
#                         startingVariable = startingParticipantValues.data.core.breakdowns.assists.emp
#                         newVariable = participantValues.data.core.breakdowns.assists.emp

#                     elif competitionVariable == HaloInfiniteCompetitionVariables.DRIVER_ASSISTS.value:
#                         startingVariable = startingParticipantValues.data.core.breakdowns.assists.driver
#                         newVariable = participantValues.data.core.breakdowns.assists.driver

#                     elif competitionVariable == HaloInfiniteCompetitionVariables.CALLOUT_ASSISTS.value:
#                         startingVariable = startingParticipantValues.data.core.breakdowns.assists.callouts
#                         newVariable = participantValues.data.core.breakdowns.assists.callouts

#                     elif competitionVariable == HaloInfiniteCompetitionVariables.VEHICLES_DESTROYED.value:
#                         startingVariable = startingParticipantValues.data.core.summary.vehicles.destroys
#                         newVariable = participantValues.data.core.summary.vehicles.destroys

#                     elif competitionVariable == HaloInfiniteCompetitionVariables.VEHICLES_HIJACKED.value:
#                         startingVariable = startingParticipantValues.data.core.summary.vehicles.hijacks
#                         newVariable = participantValues.data.core.summary.vehicles.hijacks

#                     elif competitionVariable == HaloInfiniteCompetitionVariables.MATCHES_WON.value:
#                         startingVariable = startingParticipantValues.data.core.breakdowns.matches.wins
#                         newVariable = participantValues.data.core.breakdowns.matches.wins

#                     elif competitionVariable == HaloInfiniteCompetitionVariables.MATCHES_PLAYED.value:
#                         startingVariable = startingParticipantValues.data.matches_played
#                         newVariable = participantValues.data.matches_played

#                     elif competitionVariable == HaloInfiniteCompetitionVariables.TIME_PLAYED.value:
#                         startingVariable = startingParticipantValues.data.time_played.seconds
#                         newVariable = participantValues.data.time_played.seconds

#                     elif competitionVariable == HaloInfiniteCompetitionVariables.TOTAL_SCORE.value:
#                         startingVariable = startingParticipantValues.data.core.total_score
#                         newVariable = participantValues.data.core.total_score

#                     elif competitionVariable == HaloInfiniteCompetitionVariables.MEDALS.value:
#                         startingVariable = startingParticipantValues.data.core.summary.medals
#                         newVariable = participantValues.data.core.summary.medals

#                     elif competitionVariable == HaloInfiniteCompetitionVariables.SHOTS_LANDED.value:
#                         startingVariable = startingParticipantValues.data.core.shots.landed
#                         newVariable = participantValues.data.core.shots.landed

#                     elif competitionVariable == HaloInfiniteCompetitionVariables.SHOTS_FIRED.value:
#                         startingVariable = startingParticipantValues.data.core.shots.fired
#                         newVariable = participantValues.data.core.shots.fired

#                     elif competitionVariable == HaloInfiniteCompetitionVariables.SHOT_ACCURACY.value:
#                         startingVariable = startingParticipantValues.data.core.shots.accuracy
#                         newVariable = participantValues.data.core.shots.accuracy

#                     elif competitionVariable == HaloInfiniteCompetitionVariables.WIN_RATE.value:
#                         startingVariable = startingParticipantValues.data.win_rate
#                         newVariable = participantValues.data.win_rate
#                         numDecimalPlaces = 4

#                     elif competitionVariable == HaloInfiniteCompetitionVariables.KDA_RATIO.value:
#                         startingVariable = startingParticipantValues.data.core.kda
#                         newVariable = participantValues.data.core.kda
#                         numDecimalPlaces = 4

#                     elif competitionVariable == HaloInfiniteCompetitionVariables.KD_RATIO.value:
#                         startingVariable = startingParticipantValues.data.core.kdr
#                         newVariable = participantValues.data.core.kdr
#                         numDecimalPlaces = 4

#                     diff = newVariable - startingVariable
#                     if type(diff) is Decimal:
#                         diff = diff.normalize()
#                     diff = str(diff)
#                     if diff not in playerProgressData:
#                         playerProgressData[diff] = []
#                     playerProgressData[diff].append({'id': participantId, 'wins': participantValues.wins})      

#             return [playerProgressData, competitionVariable, numDecimalPlaces]

#     async def getRoleForRecentHaloWinAndRemoveFromAll(self, guild: nextcord.Guild, serverValues, assignRoles):
#         if assignRoles and 'role_halo_recent' in serverValues:
#             recentWinRole = guild.get_role(int(serverValues['role_halo_recent']))
#             removeWinRoleSuccess = await utils.removeRoleFromAllUsers(guild, recentWinRole)
#             return [recentWinRole, removeWinRoleSuccess]
#         else:
#             return [None, False]

#     async def determineWinInfoAndPlacements(self, sortedPlayerProgressData, guild: nextcord.Guild, recentWinRole, serverId, isGCoinEnabled, date, assignRoles, numDecimalPlaces, competitionVariable):
#         bodyList = []
#         inactiveWithWins = []
#         playerWinCounts = {}
#         winnersStr = ''
#         addWinRoleSuccess = False
#         placeNumber = 1

#         # looping through different score groups
#         for score, scoreGroupValues in sortedPlayerProgressData.items():
#             incrementPlaceNumber = False

#             # looping through different users in single score group
#             for participantObj in scoreGroupValues:
#                 participantId = participantObj['id']
#                 participantWins = participantObj['wins']
#                 user = await guild.fetch_member(participantId)
#                 userStr = user.nick if user.nick else user.name
#                 sender = { 'id': None, 'name': 'Halo' }
#                 receiver = { 'id': participantId, 'name': user.name }
#                 roundedScore = score
#                 if numDecimalPlaces > 0:
#                     roundedScore = str(utils.roundDecimalPlaces(score, numDecimalPlaces))

#                 # if user has an active score
#                 if Decimal(score) != Decimal('0'):

#                     # if the user is in the top score group
#                     if placeNumber == 1:
#                         winnersStr += utils.idToUserStr(participantId) + ','
#                         if recentWinRole != None:
#                             participantWins += 1
#                             addWinRoleSuccess = await utils.addRoleToUser(user, recentWinRole)
#                             halo_queries.setParticipantWinCount(serverId, participantId, participantWins)
#                         # GCoin integration; daily and weekly winner rewards
#                         if isGCoinEnabled:
#                             gcoin_queries.performTransaction(self.GCOIN_DAILY_WIN_REWARD, date, sender, receiver, '', 'Daily Win', False, False)
#                             if assignRoles:
#                                 gcoin_queries.performTransaction(self.GCOIN_WEEKLY_WIN_REWARD, date, sender, receiver, '', 'Weekly Win', False, False)

#                     # increment place number for next score group and add user placement to body
#                     incrementPlaceNumber = True
#                     bodyList.append({'Place': str(placeNumber), 'Player': userStr, competitionVariable: roundedScore, 'Weekly Wins': str(participantWins)})

#                     # GCoin integration; weekly participation reward
#                     if isGCoinEnabled and assignRoles:
#                         gcoin_queries.performTransaction(self.GCOIN_WEEKLY_PARTICIPATION_REWARD, date, sender, receiver, '', 'Participation', False, False)

#                 else:
#                     # add user's with score of 0 and existing wins to the inactive list (exclude users with score of 0 and no wins)
#                     if participantWins > 0:
#                         inactiveWithWins.append({'Player': userStr, competitionVariable: roundedScore, 'Weekly Wins': participantWins})        

#                 # save user's win count
#                 if participantWins not in playerWinCounts:
#                     playerWinCounts[participantWins] = []
#                 playerWinCounts[participantWins].append(participantId)

#             if incrementPlaceNumber:
#                 placeNumber += 1

#         # sort inactive list by win count
#         sortedInactiveWithWins = sorted(inactiveWithWins, key = lambda inactiveUser: inactiveUser['Weekly Wins'], reverse = True)

#         # add inactive users with wins to body list with same place number
#         for inactiveUser in sortedInactiveWithWins:
#             userStr = inactiveUser['Player']
#             roundedScore = inactiveUser[competitionVariable]
#             participantWins = inactiveUser['Weekly Wins']
#             bodyList.append({'Place': str(placeNumber), 'Player': userStr, competitionVariable: roundedScore, 'Weekly Wins': str(participantWins)})

#         return [bodyList, playerWinCounts, winnersStr, addWinRoleSuccess]

#     async def getRoleForMostHaloWinAndRemoveFromAll(self, guild: nextcord.Guild, serverValues, assignRoles):
#         if assignRoles and 'role_halo_most' in serverValues:
#             mostWinsRole = guild.get_role(int(serverValues['role_halo_most']))
#             removeMostRoleSuccess = await utils.removeRoleFromAllUsers(guild, mostWinsRole)
#             return [mostWinsRole, removeMostRoleSuccess]
#         else:
#             return [None, False]

#     async def buildMostWinsStringAndAddRoles(self, mostWinsRole, playerWinCounts, guild: nextcord.Guild):
#         mostWinsStr = ''
#         addMostRoleSuccess = False
#         if mostWinsRole != None:
#             sortedPlayerWinCounts = OrderedDict(sorted(playerWinCounts.items(), key = lambda winGroup: winGroup[0], reverse = True))
#             for group in sortedPlayerWinCounts.values():
#                 for participantId in group:
#                     mostWinsStr += utils.idToUserStr(participantId) + ','
#                     user = await guild.fetch_member(participantId)
#                     addMostRoleSuccess = await utils.addRoleToUser(user, mostWinsRole)
#                 break
#         return [mostWinsStr, addMostRoleSuccess]

#     def buildWinnersString(self, recentWinRole: nextcord.Role, removeWinRoleSuccess, addWinRoleSuccess, winnersStr, mostWinsRole: nextcord.Role, removeMostRoleSuccess, addMostRoleSuccess, mostWinsStr, assignRoles):
#         if winnersStr != '':
#             recentRoleStr = ''
#             if recentWinRole != None and removeWinRoleSuccess and addWinRoleSuccess:
#                 recentRoleStr = f' and were assigned {recentWinRole.mention}'
#             mostRoleStr = ''
#             if mostWinsRole != None and removeMostRoleSuccess and addMostRoleSuccess:
#                 mostRoleStr = f' {mostWinsStr} you have the most wins and were assigned {mostWinsRole.mention}!'
#             if assignRoles:
#                 winnersStr = f"{winnersStr} you won this week's challenge{recentRoleStr}!\n{mostRoleStr}"
#             else:
#                 winnersStr = f"{winnersStr} you are in the lead!"
#         else:
#             winnersStr = 'No active players.'
#         return winnersStr

#     # Commands
#     @commands.command(aliases = strings.HALO_ALIASES, brief = "- " + strings.HALO_BRIEF, description = strings.HALO_DESCRIPTION)
#     @predicates.isFeatureEnabledForServer('toggle_halo', False)
#     @predicates.isMessageSentInGuild()
#     @predicates.isGuildOrUserSubscribed()
#     async def halo(self, ctx: Context, action = None, user: nextcord.User = None):
#         guild = ctx.guild
#         serverId = guild.id
#         author = ctx.author
#         authorMention = author.mention

#         # determine if author is player, or if player was specified
#         if user != None:
#             if not utils.isUserAdminOrOwner(author, guild):
#                 await ctx.send(f'Sorry {authorMention}, you need to be an admin to add or remove other participants.')
#                 return
#             if not await utils.isUserInThisGuildAndNotABot(user, ctx.guild):
#                 await ctx.send(f"Sorry {authorMention}, please specify a user in this guild.")
#                 return
#             userId = user.id
#             userMention = user.mention
#         else:
#             userId = author.id
#             userMention = authorMention
        
#         # return error message if user did not specify 'rm' or a gamertag
#         if action == None or action.startswith('<@'):
#             await ctx.send(f'Sorry {authorMention}, you need to specify a gamertag or type \'rm\'.')
#             return

#         # remove player if participating already
#         if action == 'rm':
#             isParticipating = halo_queries.isUserParticipatingInHalo(serverId, userId)
#             if isParticipating:
#                 halo_queries.removeHaloParticipant(serverId, userId)
#                 await ctx.send(f'{userMention} has been removed as a Halo Infinite participant.')
#             else:
#                 await ctx.send(f'{userMention} is not participating in Halo Infinite.')
        
#         # add participant upon successful validation
#         else:
#             # check if gamertag is currently in use by player in this server and if player is updating their existing gamertag
#             isGamertagUpdate = False
#             existingWinCount = 0
#             haloInfiniteServer = halo_queries.getHaloInfiniteServer(serverId)
#             participants = haloInfiniteServer['participating_players']
#             for playerId, playerValues in participants.items():
#                 gamertag = playerValues['gamertag']
#                 if playerId == str(userId):
#                     isGamertagUpdate = True
#                     existingWinCount = playerValues['wins']
#                 if action == gamertag:
#                     await ctx.send(f'Sorry {authorMention}, the gamertag {action} is already being used by {utils.idToUserStr(playerId)}.')
#                     return

#             # check if gamertag is valid
#             response = await self.haloPlayerStatsGetRequest(action)
#             if not response:
#                 await ctx.send(f'Sorry {authorMention}, {action} is not a valid gamertag.')
#                 return

#             halo_queries.addHaloParticipant(serverId, userId, action, existingWinCount)
#             if isGamertagUpdate:
#                 await ctx.send(f"{userMention}'s gamertag for Halo Infinite has been updated to {action}.")
#             else:
#                 await ctx.send(f'{userMention} has been added as a Halo Infinite participant as {action}.')

# def setup(client: commands.Bot):
#     client.add_cog(Halo(client))