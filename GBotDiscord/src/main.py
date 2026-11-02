#region IMPORTS
import pathlib
import os
import logging
import sys
import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context

from GBotDiscord.src import presentation
from GBotDiscord.src import utils
from GBotDiscord.src.dave_patch import applyDavePrepareEpochPatch
from GBotDiscord.src.logging_setup import buildHandlers, captureStream, duplicateStream, installCrashLogging
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.firebase import GBotFirebaseService
from GBotDiscord.src.quart_api.api import GBotAPIService
#endregion

# create log folder if it doesn't exist
if not os.path.exists('Logs'):
    os.mkdir('Logs')

# create log handlers, and turn anything else written to stdout or stderr into log lines as well:
# ffmpeg, hypercorn's request lines, and whatever a library prints. See logging_setup.py.
parentDir = str(pathlib.Path(__file__).parent.parent.parent.absolute()).replace("\\",'/')
handlers = buildHandlers(parentDir + '/Logs/GBotDiscord.log', duplicateStream(sys.stdout.fileno()))

# initialize logger
logging.basicConfig(handlers = handlers, 
                    level = logging.INFO)
logger = logging.getLogger()
# a logging failure reports itself on stderr, which is now captured and logged, and would loop forever
logging.raiseExceptions = False
installCrashLogging(logger)
sys.stdout.reconfigure(line_buffering = True)
captureStream(sys.stdout.fileno(), 'stdout', logging.INFO)
captureStream(sys.stderr.fileno(), 'stderr', logging.WARNING)
# one line per song step adds nothing: its failures are warnings and errors, which still show. Voice
# and gateway logs stay at the root level, because they are how C-13 was found.
logging.getLogger('nextcord.player').setLevel(logging.WARNING)

# start property manager and get properties
GBotPropertiesManager.startPropertyManager()
logger.setLevel(GBotPropertiesManager.LOG_LEVEL)

# start firebase scheduler
GBotFirebaseService.startFirebaseScheduler()

# patch nextcord's voice gateway to dispatch DAVE_PREPARE_EPOCH (see dave_patch.py)
applyDavePrepareEpochPatch()

# initialize discord client and events
def getCommandPrefix(client, message: nextcord.Message):
    return utils.getServerPrefixOrDefault(message)

intents = nextcord.Intents.all()
discordClient = commands.Bot(command_prefix = getCommandPrefix,
                             intents = intents)
discordClient.load_extension('help.help_cog')
discordClient.load_extension('config.config_cog')
# DISCONTINUED discordClient.load_extension('halo.halo_cog')
discordClient.load_extension('music.music_cog')
discordClient.load_extension('gcoin.gcoin_cog')
discordClient.load_extension('gtrade.gtrade_cog')
discordClient.load_extension('patreon.patreon_cog')
discordClient.load_extension('presence.presence_cog')
discordClient.load_extension('hype.hype_cog')
discordClient.load_extension('storms.storms_cog')
discordClient.load_extension('whodis.whodis_cog')

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
    logger.info(f'{author.name} {guildStr}executed the command: {command.name} (Message: {content})')

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
        logger.error(f'{author.name} {guildStr}failed to execute a command ({command.name}): {error}', exc_info = getattr(error, 'original', None))
    await presentation.sendCommandError(context, author, command, error)

# register GBot API
GBotAPIService.registerAPI(discordClient)

discordClient.run(GBotPropertiesManager.DISCORD_TOKEN)