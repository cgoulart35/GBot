#region IMPORTS
import copy
from datetime import datetime

import firebase
from halo.halo_models import HaloInfiniteWeeklyCompetitionModel
#endregion

def deleteServerHaloValues(serverId):
    firebase.db.child("halo_infinite_servers").child(serverId).remove(firebase.getAuthToken())

def getAllHaloInfiniteServers():
    result = firebase.db.child("halo_infinite_servers").get(firebase.getAuthToken())
    return result.val()

def postHaloInfiniteMOTD(serverId, date, jsonMOTD):
    rowMOTD = {
        'date': date,
        'motd': jsonMOTD
    }
    firebase.db.child("halo_infinite_servers").child(serverId).child('message_of_the_day').push(rowMOTD)

def getLastHaloInfiniteMOTD(serverId):
    result = firebase.db.child("halo_infinite_MOTD").get(firebase.getAuthToken())
    result = firebase.db.child("halo_infinite_servers").child(serverId).child('message_of_the_day').get(firebase.getAuthToken())
    if result.val() != None:
        messages = result.val()
        sortedMessages = sorted(messages.values(), key=lambda message: datetime.strptime(message["date"], "%m/%d/%y %I:%M:%S %p"), reverse=True)
        return sortedMessages[0]['motd']
    else:
        return ''

def addHaloParticipant(serverId, userId, gamertag):
    participantData = {
        'gamertag': gamertag,
        'wins': 0,
        'isActive': True
    }
    firebase.db.child("halo_infinite_servers").child(serverId).child('participating_players').child(userId).set(participantData)

def removeHaloParticipant(serverId, userId):
    firebase.db.child("halo_infinite_servers").child(serverId).child('participating_players').child(userId).child('isActive').set(False)

def setParticipantWinCount(serverId, userId, winCount):
    firebase.db.child("halo_infinite_servers").child(serverId).child('participating_players').child(userId).child('wins').set(winCount)

def isUserParticipatingInHalo(serverId, userId):
    result = firebase.db.child("halo_infinite_servers").child(serverId).child('participating_players').child(userId).child('isActive').get(firebase.getAuthToken())
    if result.val() != None:
        return result.val()
    else:
        return False

def isUserInThisWeeksInitialDataFetch(serverId, competitionId, userId):
    result = firebase.db.child("halo_infinite_servers").child(serverId).child('weekly_competitions').child(competitionId).child('participants').child(userId).get(firebase.getAuthToken())
    if result.val() != None:
        return True
    else:
        return False

def getNextCompetitionId(serverId):
    result = firebase.db.child("halo_infinite_servers").child(serverId).child('weekly_competitions').get(firebase.getAuthToken())
    competitionList = result.val()
    if competitionList == None:
        return 0
    return len(competitionList)

def postHaloInfiniteServerPlayerData(serverId, competitionId, freshPlayerDataCompetition: HaloInfiniteWeeklyCompetitionModel):
    dataToPost = copy.deepcopy(freshPlayerDataCompetition)
    firebase.db.child("halo_infinite_servers").child(serverId).child('weekly_competitions').child(competitionId).set(dataToPost.convertDecimalsToStrings().firebaseFormat())

def getThisWeeksInitialDataFetch(serverId, competitionId):
    result = firebase.db.child("halo_infinite_servers").child(serverId).child('weekly_competitions').child(competitionId).get(firebase.getAuthToken())
    return result.val()