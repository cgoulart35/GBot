#region IMPORTS
import nextcord
from nextcord.ext import commands, application_checks
from nextcord.ext.commands.context import Context

from GBotDiscord.src import utils
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.patreon import patreon_queries
from GBotDiscord.src.exceptions import MessageAuthorNotAdmin, MessageNotSentFromGuild, FeatureNotEnabledForGuild, NotSentFromPatreonGuild, NotAPatron, NotSubscribed
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

def isMessageAuthorAdmin(isSlashCommand = False):
    async def commonPredicate(guild, author):
        isAdmin = utils.isUserAdminOrOwner(author, guild)
        if not isAdmin:
            raise MessageAuthorNotAdmin('command failed check isMessageAuthorAdmin')
        return True
    
    if isSlashCommand:
        async def predicate(interaction: nextcord.Interaction):
            return await commonPredicate(interaction.guild, interaction.user)
        return application_checks.check(predicate)
    else:
        async def predicate(ctx: Context):
            return await commonPredicate(ctx.guild, ctx.author)
        return commands.check(predicate)

def isMessageSentInGuild(isSlashCommand = False):
    async def commonPredicate(guild):
        if guild is None:
            raise MessageNotSentFromGuild('command failed check isMessageSentInGuild')
        return True

    if isSlashCommand:
        async def predicate(interaction: nextcord.Interaction):
            return await commonPredicate(interaction.guild)
        return application_checks.check(predicate)
    else:
        async def predicate(ctx: Context):
            return await commonPredicate(ctx.guild)
        return commands.check(predicate)

def isFeatureEnabledForServer(feature, privateMessagesAllowed, isSlashCommand = False):
    async def commonPredicate(guild):
        # if private messages allowed, only validate feature switch if in guild
        if privateMessagesAllowed and guild is None:
            return True
        
        # if message sent in guild, tell user if feature disabled
        featureSwitch = config_queries.getServerValue(guild.id, feature)
        if featureSwitch == False:
            raise FeatureNotEnabledForGuild('command failed check isFeatureEnabledForServer')
        return True
    
    if isSlashCommand:
        async def predicate(interaction: nextcord.Interaction):
            return await commonPredicate(interaction.guild)
        return application_checks.check(predicate)
    else:
        async def predicate(ctx: Context):
            return await commonPredicate(ctx.guild)
        return commands.check(predicate)

def isAuthorAPatronInGBotPatreonServer(isSlashCommand = False):
    async def commonPredicate(guild, author):
        serverId = GBotPropertiesManager.PATREON_GUILD_ID
        roleId = GBotPropertiesManager.PATRON_ROLE_ID
        if guild.id != serverId:
            raise NotSentFromPatreonGuild('command failed check isAuthorAPatronInGBotPatreonServer')
        if not utils.isUserAssignedRole(author, roleId):
            raise NotAPatron('command failed check isAuthorAPatronInGBotPatreonServer')
        return True
    
    if isSlashCommand:
        async def predicate(interaction: nextcord.Interaction):
            return await commonPredicate(interaction.guild, interaction.user)
        return application_checks.check(predicate)
    else:
        async def predicate(ctx: Context):
            return await commonPredicate(ctx.guild, ctx.author)
        return commands.check(predicate)

def isGuildOrUserSubscribed(isSlashCommand = False):
    async def commonPredicate(guild, author):
        guildId = None if guild is None else guild.id
        mutualGuilds = author.mutual_guilds
        
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

    if isSlashCommand:
        async def predicate(interaction: nextcord.Interaction):
            return await commonPredicate(interaction.guild, interaction.user)
        return application_checks.check(predicate)
    else:
        async def predicate(ctx: Context):
            return await commonPredicate(ctx.guild, ctx.author)
        return commands.check(predicate)