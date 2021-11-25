#region IMPORTS
from discord.ext import commands
from discord.ext.commands.errors import CheckFailure

import config.queries
#endregion

def isMessageAuthorAdmin():
    async def predicate(ctx):
        if ctx.author.id != ctx.guild.owner_id:
            raise CheckFailure('command failed check isMessageAuthorAdmin')
        return True
    return commands.check(predicate)

def isMessageSentInGuild():
    async def predicate(ctx):
        if ctx.guild is None:
            raise CheckFailure('command failed check isMessageSentInGuild')
        return True
    return commands.check(predicate)

def isFeatureEnabledForServer(feature):
    async def predicate(ctx):
        featureSwitch = config.queries.getServerValue(ctx.guild.id, feature)
        if featureSwitch == False:
            raise CheckFailure('command failed check isFeatureEnabledForServer')
        return True
    return commands.check(predicate)

# TODO: take into account admin role in isGuildAdmin() 