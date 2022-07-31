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

from GBotDiscord import utils
from GBotDiscord.firebase import GBotFirebaseService
from GBotDiscord.quart_api.api import GBotAPIService
from GBotDiscord.exceptions import MessageAuthorNotAdmin, MessageNotSentFromGuild, FeatureNotEnabledForGuild, NotSentFromPatreonGuild, NotAPatron, NotSubscribed
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
parentDir = str(pathlib.Path(__file__).parent.parent.absolute()).replace("\\",'/')
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

# get configuration variables
version = os.getenv("GBOT_VERSION")
discordToken = os.getenv("DISCORD_TOKEN")

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

@discordClient.event
async def on_ready():
    logger.info(f'GBot logged in as {discordClient.user}.')
    await discordClient.change_presence(status=nextcord.Status.online, activity=nextcord.Game(f'GBot {version}'))

@discordClient.event
async def on_command_completion(ctx: Context):
    guildStr = ''
    if ctx.guild is not None:
        guildStr = f'(guild {ctx.guild.id}) '
    logger.info(f'{ctx.author.name} {guildStr}excuted the command: {ctx.command.name} (Message: {ctx.message.content})')

@discordClient.event
async def on_command_error(ctx: Context, error):
    if ctx.command is not None:
        guildStr = ''
        if ctx.guild is not None:
            guildStr = f'(guild {ctx.guild.id}) '
        logger.error(f'{ctx.author.name} {guildStr}failed to execute a command ({ctx.command.name}): {error}')
    if isinstance(error, CommandOnCooldown):
        m, s = divmod(error.retry_after, 60)
        h, m = divmod(m, 60)
        timeLeft = f'{int(h):d}h {int(m):02d}m {int(s):02d}s'
        await ctx.send(f'Sorry {ctx.author.mention}, please wait {timeLeft} to execute this command again.')
    if isinstance(error, MessageAuthorNotAdmin):
        await ctx.send(f'Sorry {ctx.author.mention}, you need to be an admin to execute this command.')
    if isinstance(error, MessageNotSentFromGuild):
        await ctx.send(f'Sorry {ctx.author.mention}, this command needs to be executed in a server.')
    if isinstance(error, FeatureNotEnabledForGuild):
        await ctx.send(f'Sorry {ctx.author.mention}, this feature is currently disabled.')
    if isinstance(error, NotSentFromPatreonGuild):
        await ctx.send(f'Sorry {ctx.author.mention}, this command only works in the GBot Patreon server.')
    if isinstance(error, NotAPatron):
        await ctx.send(f'Sorry {ctx.author.mention}, you need to be a GBot Patron to execute this command.')
    if isinstance(error, NotSubscribed):
        await ctx.send(f'Sorry {ctx.author.mention}, you do not have access to GBot. Please subscribe here: {os.getenv("PATREON_URL")}')

# register GBot API
GBotAPIService.registerAPI(discordClient)

discordClient.run(discordToken)