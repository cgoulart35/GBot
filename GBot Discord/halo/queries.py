#region IMPORTS
from datetime import datetime

import firebase
#endregion

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