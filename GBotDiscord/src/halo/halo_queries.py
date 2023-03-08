# #region IMPORTS
# import copy
# from datetime import datetime

# from GBotDiscord.src.firebase import GBotFirebaseService
# from GBotDiscord.src.halo.halo_models import HaloInfiniteWeeklyCompetitionModel
# #endregion

# def deleteServerHaloValues(serverId):
#     GBotFirebaseService.remove(['halo_infinite_servers', serverId])

# def getAllHaloInfiniteServers():
#     result = GBotFirebaseService.get(['halo_infinite_servers'])
#     return result.val()

# def getHaloInfiniteServer(serverId):
#     result = GBotFirebaseService.get(['halo_infinite_servers', serverId])
#     return result.val()

# def postHaloInfiniteMOTD(serverId, date, jsonMOTD):
#     rowMOTD = {
#         'date': date,
#         'motd': jsonMOTD
#     }
#     GBotFirebaseService.push(['halo_infinite_servers', serverId, 'message_of_the_day'], rowMOTD)

# def getLastHaloInfiniteMOTD(serverId):
#     result = GBotFirebaseService.get(['halo_infinite_servers', serverId, 'message_of_the_day'])
#     if result.val() != None:
#         messages = result.val()
#         sortedMessages = sorted(messages.values(), key=lambda message: datetime.strptime(message["date"], "%m/%d/%y %I:%M:%S %p"), reverse=True)
#         return sortedMessages[0]['motd']
#     else:
#         return ''

# def addHaloParticipant(serverId, userId, gamertag, existingWinCount):
#     participantData = {
#         'gamertag': gamertag,
#         'wins': existingWinCount,
#         'isActive': True
#     }
#     GBotFirebaseService.set(['halo_infinite_servers', serverId, 'participating_players', userId], participantData)

# def removeHaloParticipant(serverId, userId):
#     GBotFirebaseService.set(['halo_infinite_servers', serverId, 'participating_players', userId, 'isActive'], False)

# def setParticipantWinCount(serverId, userId, winCount):
#     GBotFirebaseService.set(['halo_infinite_servers', serverId, 'participating_players', userId, 'wins'], winCount)

# def isUserParticipatingInHalo(serverId, userId):
#     result = GBotFirebaseService.get(['halo_infinite_servers', serverId, 'participating_players', userId, 'isActive'])
#     if result.val() != None:
#         return result.val()
#     else:
#         return False

# def isUserInThisWeeksInitialDataFetch(serverId, competitionId, userId):
#     result = GBotFirebaseService.get(['halo_infinite_servers', serverId, 'weekly_competitions', competitionId, 'participants', userId])
#     if result.val() != None:
#         return True
#     else:
#         return False

# def getNextCompetitionId(serverId):
#     result = GBotFirebaseService.get(['halo_infinite_servers', serverId, 'weekly_competitions'])
#     competitionList = result.val()
#     if competitionList == None:
#         return 0
#     return len(competitionList)

# def postHaloInfiniteServerPlayerData(serverId, competitionId, freshPlayerDataCompetition: HaloInfiniteWeeklyCompetitionModel):
#     dataToPost = copy.deepcopy(freshPlayerDataCompetition)
#     GBotFirebaseService.set(['halo_infinite_servers', serverId, 'weekly_competitions', competitionId], dataToPost.convertDecimalsToStrings().firebaseFormat())

# def getThisWeeksInitialDataFetch(serverId, competitionId):
#     result = GBotFirebaseService.get(['halo_infinite_servers', serverId, 'weekly_competitions', competitionId])
#     return result.val()