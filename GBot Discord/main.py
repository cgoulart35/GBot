#region IMPORTS
import pathlib
import os
import logging
import discord
from discord.ext import commands

import config.queries
from properties import botConfig
from exceptions import MessageAuthorNotAdmin, MessageNotSentFromGuild, FeatureNotEnabledForGuild
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
    if message.guild == None:
        return '.'
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
    if isinstance(error, MessageAuthorNotAdmin):
        await ctx.send(f'Sorry {ctx.author.mention}, you need to be an admin to execute this command.')
    if isinstance(error, MessageNotSentFromGuild):
        await ctx.send(f'Sorry {ctx.author.mention}, this command needs to be executed in a server.')
    if isinstance(error, FeatureNotEnabledForGuild):
        await ctx.send(f'Sorry {ctx.author.mention}, this feature is currently disabled.')

discordClient.run(botConfig['properties']['discordToken'])