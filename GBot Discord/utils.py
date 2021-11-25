#region IMPORTS
import re
#endregion

def idToUserStr(userId):
    return '<@!' + str(userId) + '>'

def idToRoleStr(userId):
    return '<@&' + str(userId) + '>'

def idToChannelStr(userId):
    return '<#' + str(userId) + '>'