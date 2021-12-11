#region IMPORTS
import nextcord
import requests
from typing import List

import config.queries
#endregion

def idToUserStr(userId):
    return '<@!' + str(userId) + '>'

def idToRoleStr(userId):
    return '<@&' + str(userId) + '>'

def idToChannelStr(userId):
    return '<#' + str(userId) + '>'

def isUserAdminOrOwner(user: nextcord.Member, guild: nextcord.Guild):
    roles: List[nextcord.Role] = user.roles
    assignedRoleIds = [role.id for role in roles]
    adminRoleId = config.queries.getServerValue(guild.id, 'role_admin')
    if (user.id != guild.owner_id) and (adminRoleId not in assignedRoleIds):
        return False  
    return True

def isUrlStatus200(url):
    response = requests.request("GET", url, verify = False)
    if response.status_code != 200:
        return False
    else:
        return True

async def removeRoleFromAllUsers(guild: nextcord.Guild, role: nextcord.Role):
    async for member in guild.fetch_members():
        if role in member.roles:
            await member.remove_roles(role)