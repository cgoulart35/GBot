#region IMPORTS
import nextcord
from nextcord.ext.commands.context import Context
from nextcord.ext.commands.errors import CommandOnCooldown, MissingRequiredArgument, UserInputError

from GBotDiscord.src import utils
from GBotDiscord.src.exceptions import CustomCommandOnCooldown, FeatureNotEnabledForGuild, MessageAuthorNotAdmin, MessageNotSentFromGuild, MessageNotSentFromPrivateMessage, NotAPatron, NotSentFromPatreonGuild, NotSubscribed
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

# Everything a user sees should be built here, so it all looks like one bot. The design decisions
# behind this are recorded in plans/active/presentation-and-ux-consistency.md.

# sampled from the logo. Used for general and success replies; there are no per-feature colours.
BRAND_COLOR = nextcord.Color(0x7CFC50)
ERROR_COLOR = nextcord.Color.red()
WARNING_COLOR = nextcord.Color.gold()

def footerText(feature = None):
    version = f'GBot {GBotPropertiesManager.GBOT_VERSION}'
    return f'{version} • {feature}' if feature else version

def buildEmbed(*, color, title = None, description = None, feature = None):
    embed = nextcord.Embed(color = color)
    if title is not None:
        embed.title = title
    if description is not None:
        embed.description = description
    embed.set_footer(text = footerText(feature))
    return embed

def brandEmbed(*, title = None, description = None, feature = None):
    return buildEmbed(color = BRAND_COLOR, title = title, description = description, feature = feature)

def errorEmbed(*, title = None, description = None, feature = None):
    return buildEmbed(color = ERROR_COLOR, title = title, description = description, feature = feature)

def warningEmbed(*, title = None, description = None, feature = None):
    return buildEmbed(color = WARNING_COLOR, title = title, description = description, feature = feature)

async def sendReply(context, *, content = None, embed = None, ephemeral = False):
    """Replies to a slash Interaction or a prefix Context alike, as the commonX coroutines need.

    Ephemeral only exists for slash commands, so a prefix reply is public regardless. Discord also
    fixes it when an interaction first defers: a reply following a public defer() stays public.
    """
    kwargs = {}
    if content is not None:
        kwargs['content'] = content
    if embed is not None:
        kwargs['embed'] = embed
    if isinstance(context, nextcord.Interaction):
        kwargs['ephemeral'] = ephemeral
    return await context.send(**kwargs)

def usageText(context, command):
    return f'{context.clean_prefix}{command.qualified_name} {command.signature}'.rstrip()

def describeCommandError(error, mention, context = None, command = None):
    # The text for a failed command, or None for one that is deliberately silent: a disabled prefix
    # command, or a mistyped command that matches nothing. isinstance order matters only for the
    # argument errors, as MissingRequiredArgument is a kind of UserInputError.
    if isinstance(context, Context) and isinstance(error, MissingRequiredArgument):
        return f"Sorry {mention}, that command is missing `{error.param.name}`. Usage: `{usageText(context, command)}`"
    if isinstance(error, UserInputError):
        message = f'Sorry {mention}, you provided an invalid argument: {error}'
        if isinstance(context, Context):
            message += f' Usage: `{usageText(context, command)}`'
        return message
    if isinstance(error, CommandOnCooldown):
        return f'Sorry {mention}, please wait {utils.calculateTimeLeftStr(error.retry_after)} to execute this command again.'
    if isinstance(error, CustomCommandOnCooldown):
        return f'Sorry {mention}, please wait {utils.calculateTimeLeftStr(error.retry_after)} {error.reason or "to execute this command again."}'
    if isinstance(error, MessageAuthorNotAdmin):
        return f'Sorry {mention}, you need to be an admin to execute this command.'
    if isinstance(error, MessageNotSentFromGuild):
        return f'Sorry {mention}, this command needs to be executed in a server.'
    if isinstance(error, MessageNotSentFromPrivateMessage):
        return f'Sorry {mention}, this command needs to be executed in a private message.'
    if isinstance(error, FeatureNotEnabledForGuild):
        return error.userMessage(mention)
    if isinstance(error, NotSentFromPatreonGuild):
        return f'Sorry {mention}, this command only works in the GBot Patreon server.'
    if isinstance(error, NotAPatron):
        return f'Sorry {mention}, you need to be a GBot Patron to execute this command.'
    if isinstance(error, NotSubscribed):
        return f'Sorry {mention}, you do not have access to GBot. Please subscribe here: {GBotPropertiesManager.PATREON_URL}'
    return None

async def sendCommandError(context, author, command, error):
    if isinstance(error, nextcord.ApplicationInvokeError):
        error = error.original
    description = describeCommandError(error, author.mention, context, command)
    if description is None:
        return
    embed = errorEmbed(description = description)
    # a cooldown can be for a command run in a private message, which a reply here could not reach
    if isinstance(error, CustomCommandOnCooldown) and error.is_private_message:
        await author.send(embed = embed)
    else:
        await sendReply(context, embed = embed, ephemeral = True)
