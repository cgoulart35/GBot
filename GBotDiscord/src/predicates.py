#region IMPORTS
import nextcord
from nextcord.ext import commands, application_checks
from nextcord.ext.commands.context import Context

from GBotDiscord.src import access
from GBotDiscord.src import strings
from GBotDiscord.src import utils
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.exceptions import MessageAuthorNotAdmin, MessageNotSentFromGuild, MessageNotSentFromPrivateMessage, FeatureNotEnabledForGuild, LegacyPrefixCommandsNotEnabledForGuild, NotSentFromPatreonGuild, NotAPatron, NotSubscribed, AccessEnded
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.firebase import GBotFirebaseService
#endregion

def isMessageAuthorAdmin(isSlashCommand = False):
    async def commonPredicate(guild, author):
        # prefix checks run top down, so this can run before isMessageSentInGuild gets its turn. Only
        # a CommandError reaches the error handler; anything else ends without a reply.
        if guild is None:
            raise MessageNotSentFromGuild('command failed check isMessageAuthorAdmin')
        # these checks run before every command, and only read, so they wait off the event loop
        isAdmin = await GBotFirebaseService.run(utils.isUserAdminOrOwner, author, guild)
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
    
def isMessageSentInPrivateMessage(isSlashCommand = False):
    async def commonPredicate(guild):
        if not guild is None:
            raise MessageNotSentFromPrivateMessage('command failed check isMessageSentInPrivateMessage')
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
        # see isMessageAuthorAdmin: this can run ahead of isMessageSentInGuild
        if guild is None:
            raise MessageNotSentFromGuild('command failed check isFeatureEnabledForServer')
        
        # if message sent in guild, tell user if feature disabled
        featureSwitch = await GBotFirebaseService.run(config_queries.getServerValue, guild.id, feature)
        if featureSwitch == False:
            if feature == 'toggle_legacy_prefix_commands':
                raise LegacyPrefixCommandsNotEnabledForGuild('command failed check isFeatureEnabledForServer')
            raise FeatureNotEnabledForGuild('command failed check isFeatureEnabledForServer', strings.FEATURE_NAMES.get(feature, 'This feature'))
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
        # see isMessageAuthorAdmin: this can run ahead of isMessageSentInGuild
        if guild is None:
            raise MessageNotSentFromGuild('command failed check isAuthorAPatronInGBotPatreonServer')
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

async def ensureSubscribed(guild, author, allowEnded = False):
    # access.py decides. allowEnded lets a press on a card or game opened before a trial ended, or a
    # subscription lapsed, still work during the grace days, so running games finish; new commands are refused.
    if guild is not None:
        currentState = await GBotFirebaseService.run(access.check, guild.id)
    else:
        # mutual_guilds holds Guild objects, so compare their ids
        currentState = await GBotFirebaseService.run(access.check, None, [mutualGuild.id for mutualGuild in author.mutual_guilds or []])
    if currentState in access.ALLOWED or (allowEnded and currentState in access.GRACE):
        return True
    if currentState in access.GRACE + (access.EXPIRED,):
        raise AccessEnded('command failed check isGuildOrUserSubscribed', guild.id, lapsed = currentState == access.LAPSED)
    raise NotSubscribed('command failed check isGuildOrUserSubscribed')

def isGuildOrUserSubscribed(isSlashCommand = False):
    commonPredicate = ensureSubscribed

    if isSlashCommand:
        async def predicate(interaction: nextcord.Interaction):
            return await commonPredicate(interaction.guild, interaction.user)
        return application_checks.check(predicate)
    else:
        async def predicate(ctx: Context):
            return await commonPredicate(ctx.guild, ctx.author)
        return commands.check(predicate)

async def recheck(interaction: nextcord.Interaction, feature = None, admin = False, privateMessagesAllowed = False, guild = None):
    # A button or form skips its command's checks, and a card can sit open while a feature is turned
    # off or a role taken away, so every press makes them again. Raises what the command's would.
    # guild: the server a card sent to DMs acts for, which a press there doesn't carry.
    guild = guild or interaction.guild
    await ensureSubscribed(guild, interaction.user, allowEnded = True)
    if guild is None:
        if privateMessagesAllowed:
            return True
        raise MessageNotSentFromGuild('press failed check recheck')
    if feature is not None and await GBotFirebaseService.run(config_queries.getServerValue, guild.id, feature) == False:
        raise FeatureNotEnabledForGuild('press failed check recheck', strings.FEATURE_NAMES.get(feature, 'This feature'))
    if admin and not await GBotFirebaseService.run(utils.isUserAdminOrOwner, interaction.user, guild):
        raise MessageAuthorNotAdmin('press failed check recheck')
    return True
