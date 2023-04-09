#region IMPORTS
import pathlib
import os
import logging
import sys
import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context
from nextcord.ext.commands.errors import CommandOnCooldown
from nextcord.ext.commands.help import DefaultHelpCommand
from hypercorn.logging import AccessLogAtoms

from GBotDiscord.src import utils
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.firebase import GBotFirebaseService
from GBotDiscord.src.quart_api.api import GBotAPIService
from GBotDiscord.src.exceptions import MessageAuthorNotAdmin, MessageNotSentFromGuild, FeatureNotEnabledForGuild, NotSentFromPatreonGuild, NotAPatron, NotSubscribed
#endregion

class CustomFormatter(logging.Formatter):
    def format(self, record):
        if record.args != ():
            if isinstance(record.args, AccessLogAtoms):
                return super().format(record)
            argList = []
            for arg in record.args:
                if arg is None:
                    argList.append('')
                else:
                    argList.append(arg)
            fullMsg = record.msg % (tuple(argList))
        else:
            fullMsg = record.msg
        escapedMsg = fullMsg.replace('\\', '\\\\').replace('"', '\\"')
        record.msg = escapedMsg
        record.args = ()
        return super().format(record)

# create log folder if it doesn't exist
if not os.path.exists('Logs'):
    os.mkdir('Logs')

# create log handlers and assign custom formatter
parentDir = str(pathlib.Path(__file__).parent.parent.parent.absolute()).replace("\\",'/')
fileHandler = logging.FileHandler(filename = parentDir + '/Logs/GBotDiscord.log')
stdoutHandler = logging.StreamHandler(sys.stdout)
customFormatter = CustomFormatter('{"level":"%(levelname)s","time":"%(asctime)s","message":"%(message)s","name":"%(name)s"}')
fileHandler.setFormatter(customFormatter)
stdoutHandler.setFormatter(customFormatter)
handlers = [fileHandler, stdoutHandler]

# initialize logger
logging.basicConfig(handlers = handlers, 
                    level = logging.INFO)
logger = logging.getLogger()

# start property manager and get properties
GBotPropertiesManager.startPropertyManager()
logger.setLevel(GBotPropertiesManager.LOG_LEVEL)

# start firebase scheduler
GBotFirebaseService.startFirebaseScheduler()

# initialize discord client and events
def getCommandPrefix(client, message: nextcord.Message):
    return utils.getServerPrefixOrDefault(message)

intents = nextcord.Intents.all()
discordClient = commands.Bot(command_prefix = getCommandPrefix,
                             intents = intents,
                             help_command = DefaultHelpCommand(
                                 width = 100,
                                 indent = 10,
                                 no_category = 'Other')
                            )
discordClient.load_extension('config.config_cog')
# DISCONTINUED discordClient.load_extension('halo.halo_cog')
discordClient.load_extension('music.music_cog')
discordClient.load_extension('gcoin.gcoin_cog')
discordClient.load_extension('gtrade.gtrade_cog')
discordClient.load_extension('patreon.patreon_cog')
discordClient.load_extension('hype.hype_cog')
discordClient.load_extension('storms.storms_cog')

@discordClient.event
async def on_ready():
    logger.info(f'GBot logged in as {discordClient.user}.')
    await discordClient.change_presence(status=nextcord.Status.online, activity=nextcord.Game(f'GBot {GBotPropertiesManager.GBOT_VERSION}'))

@discordClient.event
async def on_application_command_completion(interaction: nextcord.Interaction):
    await on_completion(interaction.guild, interaction.user, interaction.application_command, interaction.application_command.name)

@discordClient.event
async def on_command_completion(ctx: Context):
    await on_completion(ctx.guild, ctx.author, ctx.command, ctx.message.content)

async def on_completion(guild, author, command, content):
    guildStr = ''
    if guild is not None:
        guildStr = f'(guild {guild.id}) '
    logger.info(f'{author.name} {guildStr}excuted the command: {command.name} (Message: {content})')

@discordClient.event
async def on_application_command_error(interaction: nextcord.Interaction, error):
    await on_error(interaction, interaction.application_command, interaction.guild, interaction.user, error)

@discordClient.event
async def on_command_error(ctx: Context, error):
    await on_error(ctx, ctx.command, ctx.guild, ctx.author, error)

async def on_error(context, command, guild, author, error):
    if command is not None:
        guildStr = ''
        if guild is not None:
            guildStr = f'(guild {guild.id}) '
        logger.error(f'{author.name} {guildStr}failed to execute a command ({command.name}): {error}')
    if isinstance(error, CommandOnCooldown):
        m, s = divmod(error.retry_after, 60)
        h, m = divmod(m, 60)
        timeLeft = f'{int(h):d}h {int(m):02d}m {int(s):02d}s'
        await context.send(f'Sorry {author.mention}, please wait {timeLeft} to execute this command again.')
    if isinstance(error, MessageAuthorNotAdmin):
        await context.send(f'Sorry {author.mention}, you need to be an admin to execute this command.')
    if isinstance(error, MessageNotSentFromGuild):
        await context.send(f'Sorry {author.mention}, this command needs to be executed in a server.')
    if isinstance(error, FeatureNotEnabledForGuild):
        await context.send(f'Sorry {author.mention}, this feature is currently disabled.')
    if isinstance(error, NotSentFromPatreonGuild):
        await context.send(f'Sorry {author.mention}, this command only works in the GBot Patreon server.')
    if isinstance(error, NotAPatron):
        await context.send(f'Sorry {author.mention}, you need to be a GBot Patron to execute this command.')
    if isinstance(error, NotSubscribed):
        await context.send(f'Sorry {author.mention}, you do not have access to GBot. Please subscribe here: {GBotPropertiesManager.PATREON_URL}')

# register GBot API
GBotAPIService.registerAPI(discordClient)

discordClient.run(GBotPropertiesManager.DISCORD_TOKEN)