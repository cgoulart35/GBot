#region IMPORTS
from datetime import datetime

import firebase
#endregion

def getAllHaloInfiniteServers():
    result = firebase.db.child("halo_infinite_servers").get(firebase.getAuthToken())
    return result.val()

def postHaloInfiniteMOTD(date, jsonMOTD):
    rowMOTD = {
        'date': date,
        'motd': jsonMOTD
    }
    firebase.db.child("halo_infinite_MOTD").push(rowMOTD)

def getLatestHaloInfiniteMOTD():
    result = firebase.db.child("halo_infinite_MOTD").get(firebase.getAuthToken())
    if result.val() != None:
        messages = result.val()
        sortedMessages = sorted(messages.values(), key=lambda message: datetime.strptime(message["date"], "%m/%d/%y %I:%M:%S %p"), reverse=True)
        return sortedMessages[0]['motd']
    else:
        return ''

def addHaloParticipant(serverId, userId, gamertag):
    firebase.db.child("halo_infinite_servers").child(serverId).child('participating_players').child(userId).child('gamertag').set(gamertag)

def removeHaloParticipant(serverId, userId):
    firebase.db.child("halo_infinite_servers").child(serverId).child('participating_players').child(userId).remove(firebase.getAuthToken())

def isUserParticipatingInHalo(serverId, userId):
    result = firebase.db.child("halo_infinite_servers").child(serverId).child('participating_players').child(userId).child('gamertag').get(firebase.getAuthToken())
    if result.val() != None:
        return True
    else:
        return False

def isUserInThisWeeksInitialDataFetch(serverId, competitionId, userId):
    result = firebase.db.child("halo_infinite_servers").child(serverId).child('weekly_competitions').child(competitionId).child('participants').child(userId).get(firebase.getAuthToken())
    if result.val() != None:
        return True
    else:
        return False

def getThisWeeksInitialDataFetch(serverId, competitionId):
    result = firebase.db.child("halo_infinite_servers").child(serverId).child('weekly_competitions').child(competitionId).get(firebase.getAuthToken())
    return result.val()

def getNextCompetitionId(serverId):
    result = firebase.db.child("halo_infinite_servers").child(serverId).child('weekly_competitions').get(firebase.getAuthToken())
    competitionList = result.val()
    if competitionList == None:
        return 0
    return len(competitionList)

def postHaloInfiniteServerPlayerData(serverId, competitionId, freshPlayerDataCompetition):
    firebase.db.child("halo_infinite_servers").child(serverId).child('weekly_competitions').child(competitionId).set(freshPlayerDataCompetition)