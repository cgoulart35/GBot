#region IMPORTS
from discord.ext import commands

import config.queries
from exceptions import MessageAuthorNotAdmin, MessageNotSentFromGuild, FeatureNotEnabledForGuild
#endregion

def isMessageAuthorAdmin():
    async def predicate(ctx):
        assignedRoleIds = [role.id for role in ctx.author.roles]
        adminRoleId = config.queries.getServerValue(ctx.guild.id, 'role_admin')
        if (ctx.author.id != ctx.guild.owner_id) and (adminRoleId not in assignedRoleIds):
            raise MessageAuthorNotAdmin('command failed check isMessageAuthorAdmin')
        return True
    return commands.check(predicate)

def isMessageSentInGuild():
    async def predicate(ctx):
        if ctx.guild is None:
            raise MessageNotSentFromGuild('command failed check isMessageSentInGuild')
        return True
    return commands.check(predicate)

def isFeatureEnabledForServer(feature):
    async def predicate(ctx):
        featureSwitch = config.queries.getServerValue(ctx.guild.id, feature)
        if featureSwitch == False:
            raise FeatureNotEnabledForGuild('command failed check isFeatureEnabledForServer')
        return True
    return commands.check(predicate)