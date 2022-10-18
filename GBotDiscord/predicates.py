#region IMPORTS
from nextcord.ext import commands
from nextcord.ext.commands.context import Context

from GBotDiscord import utils
from GBotDiscord.config import config_queries
from GBotDiscord.patreon import patreon_queries
from GBotDiscord.exceptions import MessageAuthorNotAdmin, MessageNotSentFromGuild, FeatureNotEnabledForGuild, NotSentFromPatreonGuild, NotAPatron, NotSubscribed
from GBotDiscord.properties import GBotPropertiesManager
#endregion

def isMessageAuthorAdmin():
    async def predicate(ctx: Context):
        isAdmin = utils.isUserAdminOrOwner(ctx.author, ctx.guild)
        if not isAdmin:
            raise MessageAuthorNotAdmin('command failed check isMessageAuthorAdmin')
        return True
    return commands.check(predicate)

def isMessageSentInGuild():
    async def predicate(ctx: Context):
        if ctx.guild is None:
            raise MessageNotSentFromGuild('command failed check isMessageSentInGuild')
        return True
    return commands.check(predicate)

def isFeatureEnabledForServer(feature):
    async def predicate(ctx: Context):
        featureSwitch = config_queries.getServerValue(ctx.guild.id, feature)
        if featureSwitch == False:
            raise FeatureNotEnabledForGuild('command failed check isFeatureEnabledForServer')
        return True
    return commands.check(predicate)

def isAuthorAPatronInGBotPatreonServer():
    async def predicate(ctx: Context):
        serverId = GBotPropertiesManager.PATREON_GUILD_ID
        roleId = GBotPropertiesManager.PATRON_ROLE_ID
        if ctx.guild.id != serverId:
            raise NotSentFromPatreonGuild('command failed check isAuthorAPatronInGBotPatreonServer')
        if not utils.isUserAssignedRole(ctx.author, roleId):
            raise NotAPatron('command failed check isAuthorAPatronInGBotPatreonServer')
        return True
    return commands.check(predicate)

def isGuildOrUserSubscribed():
    async def predicate(ctx: Context):
        guildId = None if ctx.guild is None else ctx.guild.id
        mutualGuilds = ctx.author.mutual_guilds
        
        # if the guild should be ignored, skip patreon validation
        guildsToIgnore = utils.getGuildsForPatreonToIgnore()
        if guildsToIgnore != None:   
            if guildId != None and guildId in guildsToIgnore:
                return True
            if guildId == None and mutualGuilds != None:
                for mutualGuild in mutualGuilds:
                    if mutualGuild.id in guildsToIgnore:
                        return True

        allPatronMembers = patreon_queries.getAllPatrons()
        if allPatronMembers != None:
            for values in allPatronMembers.values():
                serverId = int(values['serverId'])
                # if the command was made from a subscribed guild
                if guildId != None and serverId == guildId:
                    return True
                # if the command was made in a private message by someone in a subscribed guild
                if guildId == None and mutualGuilds != None and serverId in mutualGuilds:
                    return True
        raise NotSubscribed('command failed check isGuildOrUserSubscribed') 
    return commands.check(predicate)