#region IMPORTS
import os
import httpx
import pandas
import df2img
import emoji
import re
import nextcord
from nextcord.ext.commands.errors import ArgumentParsingError
from nextcord.ext.commands.context import Context
from decimal import ROUND_HALF_UP, Decimal
from typing import List

from GBotDiscord.src.config import config_queries
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

def idToUserStr(userId):
    return '<@!' + str(userId) + '>'

def idToRoleStr(userId):
    return '<@&' + str(userId) + '>'

def idToChannelStr(userId):
    return '<#' + str(userId) + '>'

def idStrArgToInt(id, name):
    try:
        return int(id)
    except:
        raise ArgumentParsingError(name)
    
def strParamToArgs(original: str):
    condensedString = re.sub(r"[\"]\s*[\"]", "\"", original)
    listOfDirtyStringsEmpty = condensedString.split("\"")
    listOfDirtyStringsNoEmpty = [x for x in listOfDirtyStringsEmpty if x]
    return listOfDirtyStringsNoEmpty

def emojisParamToArgs(emojisStr: str):
    emojiList = []
    buildingEmoji = False
    currentEmoji = ''
    for char in emojisStr:
        if char.isspace():
            continue
        if char != '<' and buildingEmoji == False and emoji.is_emoji(char):
            emojiList.append(char)
            continue
        if char == '<' and buildingEmoji == False:
            buildingEmoji = True
            currentEmoji = char
            continue
        if char == '>' and buildingEmoji == True:
            currentEmoji += char
            emojiList.append(currentEmoji)
            buildingEmoji = False
            currentEmoji = ''
            continue
        if char != '<' and buildingEmoji == True:
            currentEmoji += char
            continue
    if not emojiList:
        raise ArgumentParsingError('emojis')
    return emojiList

def isUserAdminOrOwner(user: nextcord.Member, guild: nextcord.Guild):
    adminRoleId = config_queries.getServerValue(guild.id, 'role_admin')
    if (user.id != guild.owner_id) and not isUserAssignedRole(user, int(adminRoleId)):
        return False
    return True

def isUserAssignedRole(user: nextcord.Member, roleId: int):
    roles: List[nextcord.Role] = user.roles
    assignedRoleIds = [role.id for role in roles]
    return roleId in assignedRoleIds

async def isUserInThisGuildAndNotABot(user: nextcord.Member, guild: nextcord.Guild):
    async for member in guild.fetch_members():
        if member.id == user.id and not member.bot:
            return True
    return False

async def isUrlImageContentTypeAndStatus200(url):
    async with httpx.AsyncClient() as httpxClient:
        try:
            image_formats = ('image/png', 'image/jpeg', 'image/jpg', 'image/gif')
            response = await httpxClient.get(url, timeout = 60, follow_redirects = True)
            if response.status_code != 200 or response.headers['content-type'] not in image_formats:
                return False
            else:
                return True
        except:
            return False

def roundDecimalPlaces(decimal, places):
    precision = '0' * places
    return Decimal(str(decimal)).quantize(Decimal(f'1.{precision}'), rounding = ROUND_HALF_UP)

def getServerPrefixOrDefault(message: nextcord.Message):
    if message.guild == None:
        return '.'
    return config_queries.getServerValue(message.guild.id, 'prefix')

def getGuildsForPatreonToIgnore():
    patreonGuildId = GBotPropertiesManager.PATREON_GUILD_ID
    guildsToIgnore = GBotPropertiesManager.PATREON_IGNORE_GUILDS
    if patreonGuildId not in guildsToIgnore:
        guildsToIgnore.append(patreonGuildId)
    return guildsToIgnore

async def askUserQuestion(client: nextcord.Client, context, author: nextcord.Member, question, configuredTimeout):
    def check(message: nextcord.Message):
            return message.author == author and message.channel == context.channel
    await context.send(question)
    return await client.wait_for('message', check = check, timeout = configuredTimeout)

async def sendDiscordEmbed(channel: nextcord.TextChannel, title, description, color, file: nextcord.File = None, fileURL = None, thumbnailUrl = None, deleteAfter = None):
    if description != None:
        embed = nextcord.Embed(title = title, description = description, color = color)
    else:
        embed = nextcord.Embed(title = title, color = color)
    if file != None and fileURL == None:
        embed.set_image(url = f'attachment://{file.filename}')
    elif file == None and fileURL != None:
        embed.set_image(url = fileURL)
    else:
        file = None
    if thumbnailUrl != None:
        embed.set_thumbnail(url = thumbnailUrl)
    if deleteAfter != None:
        await channel.send(embed = embed, file = file, delete_after = deleteAfter)
    else:
        await channel.send(embed = embed, file = file)

async def removeRoleFromAllUsers(guild: nextcord.Guild, role: nextcord.Role):
    try:
        async for member in guild.fetch_members():
            if role in member.roles:
                await member.remove_roles(role)
        return True
    except Exception:
        return False

async def addRoleToUser(user: nextcord.Member, role: nextcord.Role):
    try:
        await user.add_roles(role)
        return True
    except Exception:
        return False

def createTempTableImage(filename, bodyList, colList, colWidth, title, headerFontColor, headerFillColor):
    data = {}
    for column in colList:
        data[column] = []
        for body in bodyList:
            data[column].append(body[column])
    dataframe = pandas.DataFrame(data)
    dataframe.set_index(colList[0], inplace = True)
    fig = df2img.plot_dataframe(
        dataframe,
        title = dict(
            font_color = 'black',
            font_family = 'Times New Roman',
            font_size = 22,
            text = title,
        ),
        tbl_header = dict(
            align = 'right',
            fill_color = headerFillColor,
            font_color = headerFontColor,
            font_size = 20,
            line_color = 'darkslategray',
            line_width = 2
        ),
        tbl_cells=dict(
            align = 'right',
            font_size = 20,
            line_color = 'darkslategray',
            line_width = 2,
            height = 40
        ),
        row_fill_color = ('#ffffff', '#d7d8d6'),
        col_width = colWidth,
        fig_size = (750, 115 + (40 * len(bodyList)))
    )
    df2img.save_dataframe(fig = fig, filename = filename)

def deleteTempTableImage(filename):
    if os.path.exists(filename):
        os.remove(filename)
        return True
    return False