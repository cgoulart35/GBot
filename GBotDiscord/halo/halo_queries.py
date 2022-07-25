# #region IMPORTS
# import copy
# from datetime import datetime

# from GBotDiscord.firebase import GBotFirebaseService
# from GBotDiscord.halo.halo_models import HaloInfiniteWeeklyCompetitionModel
# #endregion

# def deleteServerHaloValues(serverId):
#     GBotFirebaseService.db.child("halo_infinite_servers").child(serverId).remove(GBotFirebaseService.getAuthToken())

# def getAllHaloInfiniteServers():
#     result = GBotFirebaseService.db.child("halo_infinite_servers").get(GBotFirebaseService.getAuthToken())
#     return result.val()

# def getHaloInfiniteServer(serverId):
#     result = GBotFirebaseService.db.child("halo_infinite_servers").child(serverId).get(GBotFirebaseService.getAuthToken())
#     return result.val()

# def postHaloInfiniteMOTD(serverId, date, jsonMOTD):
#     rowMOTD = {
#         'date': date,
#         'motd': jsonMOTD
#     }
#     GBotFirebaseService.db.child("halo_infinite_servers").child(serverId).child('message_of_the_day').push(rowMOTD)

# def getLastHaloInfiniteMOTD(serverId):
#     result = GBotFirebaseService.db.child("halo_infinite_MOTD").get(GBotFirebaseService.getAuthToken())
#     result = GBotFirebaseService.db.child("halo_infinite_servers").child(serverId).child('message_of_the_day').get(GBotFirebaseService.getAuthToken())
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
#     GBotFirebaseService.db.child("halo_infinite_servers").child(serverId).child('participating_players').child(userId).set(participantData)

# def removeHaloParticipant(serverId, userId):
#     GBotFirebaseService.db.child("halo_infinite_servers").child(serverId).child('participating_players').child(userId).child('isActive').set(False)

# def setParticipantWinCount(serverId, userId, winCount):
#     GBotFirebaseService.db.child("halo_infinite_servers").child(serverId).child('participating_players').child(userId).child('wins').set(winCount)

# def isUserParticipatingInHalo(serverId, userId):
#     result = GBotFirebaseService.db.child("halo_infinite_servers").child(serverId).child('participating_players').child(userId).child('isActive').get(GBotFirebaseService.getAuthToken())
#     if result.val() != None:
#         return result.val()
#     else:
#         return False

# def isUserInThisWeeksInitialDataFetch(serverId, competitionId, userId):
#     result = GBotFirebaseService.db.child("halo_infinite_servers").child(serverId).child('weekly_competitions').child(competitionId).child('participants').child(userId).get(GBotFirebaseService.getAuthToken())
#     if result.val() != None:
#         return True
#     else:
#         return False

# def getNextCompetitionId(serverId):
#     result = GBotFirebaseService.db.child("halo_infinite_servers").child(serverId).child('weekly_competitions').get(GBotFirebaseService.getAuthToken())
#     competitionList = result.val()
#     if competitionList == None:
#         return 0
#     return len(competitionList)

# def postHaloInfiniteServerPlayerData(serverId, competitionId, freshPlayerDataCompetition: HaloInfiniteWeeklyCompetitionModel):
#     dataToPost = copy.deepcopy(freshPlayerDataCompetition)
#     GBotFirebaseService.db.child("halo_infinite_servers").child(serverId).child('weekly_competitions').child(competitionId).set(dataToPost.convertDecimalsToStrings().firebaseFormat())

# def getThisWeeksInitialDataFetch(serverId, competitionId):
#     result = GBotFirebaseService.db.child("halo_infinite_servers").child(serverId).child('weekly_competitions').child(competitionId).get(GBotFirebaseService.getAuthToken())
#     return result.val()