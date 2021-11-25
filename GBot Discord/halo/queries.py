#region IMPORTS
import firebase
#endregion

def postHaloInfiniteMOTD(date, jsonMOTD):
    rowMOTD = {
        'date': date,
        'motd': jsonMOTD
    }
    firebase.db.child("halo_infinite_MOTD").push(rowMOTD)