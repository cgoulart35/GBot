#region IMPORTS
import logging
from decimal import Decimal, InvalidOperation

import nextcord
from nextcord.ext.commands.context import Context
from nextcord.ext.commands.errors import CommandInvokeError, CommandOnCooldown, MissingRequiredArgument, UserInputError

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

async def deferIfSlash(context, ephemeral = False):
    # Buys up to 15 minutes instead of 3 seconds. A timeout after money has moved would look like a
    # failure and invite a second attempt. Discord fixes a reply's visibility here, so anything that
    # should stay private has to be checked before calling this.
    if isinstance(context, nextcord.Interaction):
        await context.response.defer(ephemeral = ephemeral)

async def sendError(context, description, *, feature = None, ephemeral = True):
    # A message a cog keeps to delete later has to pass ephemeral = False, since nobody can delete a
    # private reply. Storms purges its messages, so its refusals stay public.
    return await sendReply(context, embed = errorEmbed(description = description, feature = feature), ephemeral = ephemeral)

async def sendEmbed(context, *, title, description = None, feature = None, thumbnailUrl = None):
    embed = brandEmbed(title = title, description = description, feature = feature)
    if thumbnailUrl is not None:
        embed.set_thumbnail(url = thumbnailUrl)
    return await sendReply(context, embed = embed)

def formatGCoin(amount):
    # display only: 1,250.00. Stored values and their rounding belong to utils.roundDecimalPlaces.
    # Transaction history passes amounts already signed, and a credit's + has to survive.
    text = str(amount)
    return f"{'+' if text.startswith('+') else ''}{Decimal(text):,.2f}"

def parseGCoin(text):
    # GBot displays amounts with commas, so people type and paste them back that way. NaN and
    # Infinity are valid Decimals but not amounts, and comparing NaN raises later on, so they stop here.
    amount = Decimal(str(text).replace(',', '').strip())
    if not amount.is_finite():
        raise InvalidOperation
    return amount

async def sendWelcome(guild):
    # Once, on join. Most features start off, so a new server otherwise gets no guidance. It finds
    # somewhere it may post or stays quiet: being unable to say hello is no failure worth reporting.
    embed = brandEmbed(title = 'Thanks for adding GBot!', description = 'Most features start off.\n\n**Admins:** turn them on with `/config toggle`.\n**Everyone:** see what is available with `/help`.')
    try:
        for channel in [guild.system_channel] + list(guild.text_channels):
            if channel is not None:
                permissions = channel.permissions_for(guild.me)
                if permissions.send_messages and permissions.embed_links:
                    await channel.send(embed = embed)
                    return
    except Exception as e:
        logging.getLogger().error(f'GBot could not post its welcome message in guild {guild.id}: {e}')

def usageText(context, command):
    return f'{context.clean_prefix}{command.qualified_name} {command.signature}'.rstrip()

def describeCommandError(error, mention, context = None, command = None):
    # The text for a failed command, or None for one that is deliberately silent: a disabled prefix
    # command, or a mistyped command that matches nothing. isinstance order matters only for the
    # argument errors, as MissingRequiredArgument is a kind of UserInputError.
    if isinstance(context, Context) and isinstance(error, MissingRequiredArgument):
        return f"Sorry {mention}, that command is missing `{error.param.name}`. Usage: `{usageText(context, command)}`"
    if isinstance(error, InvalidOperation):
        return f'Sorry {mention}, please enter a valid amount.'
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
    # a command that crashed arrives wrapped, unlike one a check refused, which can be deliberately
    # silent. A crash always gets a reply: slash would otherwise say "did not respond", prefix nothing.
    crashed = isinstance(error, (nextcord.ApplicationInvokeError, CommandInvokeError))
    if crashed:
        error = error.original
    description = describeCommandError(error, author.mention, context, command)
    if description is None:
        if not crashed:
            return
        description = f'Sorry {author.mention}, something went wrong running that command. It has been logged.'
    embed = errorEmbed(description = description)
    # a cooldown can be for a command that has to stay secret, which a public prefix reply would give
    # away. A slash reply is private anyway, and also reaches someone whose DMs are closed.
    if isinstance(error, CustomCommandOnCooldown) and error.is_private_message and not isinstance(context, nextcord.Interaction):
        await author.send(embed = embed)
    else:
        await sendReply(context, embed = embed, ephemeral = True)
