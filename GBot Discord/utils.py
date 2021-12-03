#region IMPORTS
import discord

import config.queries
#endregion

def idToUserStr(userId):
    return '<@!' + str(userId) + '>'

def idToRoleStr(userId):
    return '<@&' + str(userId) + '>'

def idToChannelStr(userId):
    return '<#' + str(userId) + '>'

def isUserAdminOrOwner(user: discord.User, guild: discord.Guild):
    assignedRoleIds = [role.id for role in user.roles]
    adminRoleId = config.queries.getServerValue(guild.id, 'role_admin')
    if (user.id != guild.owner_id) and (adminRoleId not in assignedRoleIds):
        return False  
    return True

async def removeRoleFromAllUsers(guild: discord.Guild, role: discord.Role):
    async for member in guild.fetch_members():
        if role in member.roles:
            await member.remove_roles(role)