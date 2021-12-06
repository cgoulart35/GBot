#region IMPORTS
from nextcord.ext import commands

import utils
import config.queries
from exceptions import MessageAuthorNotAdmin, MessageNotSentFromGuild, FeatureNotEnabledForGuild
#endregion

def isMessageAuthorAdmin():
    async def predicate(ctx):
        isAdmin = utils.isUserAdminOrOwner(ctx.author, ctx.guild)
        if not isAdmin:
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