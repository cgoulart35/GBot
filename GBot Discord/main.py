#region IMPORTS
import pathlib
import os
import logging
import discord
from discord.ext import commands

import config.queries
from properties import botConfig
#endregion

# get parent directory
parentDir = str(pathlib.Path(__file__).parent.parent.absolute())
parentDir = parentDir.replace("\\",'/')

# create and configure root logger
if not os.path.exists('Logs'):
    os.mkdir('Logs')
LOG_FORMAT = "%(levelname)s %(asctime)s - %(message)s"
logging.basicConfig(filename = parentDir + '/Logs/GBot Discord.log', level = logging.INFO, format = LOG_FORMAT)
logger = logging.getLogger()

# get configuration variables
botVersion = botConfig['properties']['version']
discordToken = botConfig['properties']['discordToken']

# initialize discord client and events
def getServerPrefix(client, message):
    return config.queries.getServerValue(message.guild.id, 'prefix')

discordClient = commands.Bot(command_prefix = getServerPrefix)
discordClient.load_extension('config.cog')

@discordClient.event
async def on_ready():
    logger.info(f'GBot logged in as {discordClient.user}.')
    await discordClient.change_presence(status=discord.Status.online, activity=discord.Game(f'GBot {botVersion}'))

@discordClient.event
async def on_command_completion(ctx):
    logger.info(f'{ctx.author.name} excuted the command: {ctx.command.name}')

@discordClient.event
async def on_command_error(ctx, error):
    logger.error(f'{ctx.author.name} failed to execute a command ({ctx.command.name}): {error}')

discordClient.run(botConfig['properties']['discordToken'])