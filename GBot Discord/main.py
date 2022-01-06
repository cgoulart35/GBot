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

import config.queries
import firebase
from exceptions import MessageAuthorNotAdmin, MessageNotSentFromGuild, FeatureNotEnabledForGuild
#endregion

# get parent directory
parentDir = str(pathlib.Path(__file__).parent.parent.absolute())
parentDir = parentDir.replace("\\",'/')

# create and configure root logger
if not os.path.exists('Logs'):
    os.mkdir('Logs')
LOG_FORMAT = "%(levelname)s %(asctime)s - %(message)s"
file_handler = logging.FileHandler(filename = parentDir + '/Logs/GBot Discord.log')
stdout_handler = logging.StreamHandler(sys.stdout)
handlers = [file_handler, stdout_handler]
logging.basicConfig(handlers = handlers,
                    format = LOG_FORMAT,
                    level = logging.INFO)
logger = logging.getLogger()

# get configuration variables
version = os.getenv("GBOT_VERSION")
discordToken = os.getenv("DISCORD_TOKEN")

# start firebase scheduler
firebase.startFirebaseScheduler(parentDir)

# initialize discord client and events
def getServerPrefix(client, message: nextcord.Message):
    if message.guild == None:
        return '.'
    return config.queries.getServerValue(message.guild.id, 'prefix')

intents = nextcord.Intents.all()
discordClient = commands.Bot(command_prefix = getServerPrefix,
                             intents = intents,
                             help_command = DefaultHelpCommand(
                                 width = 100,
                                 indent = 10,
                                 no_category = 'Other')
                            )
discordClient.load_extension('config.cog')
discordClient.load_extension('halo.cog')

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

discordClient.run(discordToken)