#region IMPORTS
import os
import asyncio
import ipaddress
import socket
import httpx
import pandas
import df2img
import emoji
import re
import nextcord
from nextcord.ext.commands.errors import ArgumentParsingError
from decimal import ROUND_HALF_UP, Decimal
from typing import List
from urllib.parse import urlsplit

from GBotDiscord.src.config import config_queries
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.firebase import GBotFirebaseService
#endregion

MAX_URL_REDIRECTS = 5

def idToUserStr(userId):
    return '<@!' + str(userId) + '>'

def idToRoleStr(userId):
    return '<@&' + str(userId) + '>'

def idToChannelStr(userId):
    return '<#' + str(userId) + '>'

def idStrArgToInt(id, name):
    try:
        return int(id)
    except (TypeError, ValueError):
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

def splitMessage(text, limit = 2000):
    # Discord's limit on a message a bot sends
    return [text[i:i + limit] for i in range(0, len(text), limit)]

def isUserAdminOrOwner(user: nextcord.Member, guild: nextcord.Guild):
    adminRoleId = config_queries.getServerValue(guild.id, 'role_admin')
    if (user.id != guild.owner_id) and not isUserAssignedRole(user, adminRoleId):
        return False
    return True

def isUserAssignedRole(user: nextcord.Member, roleId):
    if not roleId:
        return False
    roleId = int(roleId)
    roles: List[nextcord.Role] = user.roles
    assignedRoleIds = [role.id for role in roles]
    return roleId in assignedRoleIds

async def isUserInThisGuildAndNotABot(user: nextcord.Member, guild: nextcord.Guild):
    async for member in guild.fetch_members():
        if member.id == user.id and not member.bot:
            return True
    return False

def isPublicHost(host):
    # runs on a worker thread, as a name lookup blocks. Every address counts: a name can list several.
    for *_, address in socket.getaddrinfo(host, None, type = socket.SOCK_STREAM):
        ip = ipaddress.ip_address(address[0].split('%')[0])
        ip = getattr(ip, 'ipv4_mapped', None) or ip
        if not ip.is_global or ip.is_multicast:
            return False
    return True

async def isPublicUrl(url):
    # A link a user pastes is fetched from wherever the bot runs, so it must not be able to point at
    # that machine or its network. Looking up the name covers any spelling of an address as well.
    try:
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or not parts.hostname:
            return False
        return await asyncio.to_thread(isPublicHost, parts.hostname)
    except (OSError, ValueError):
        # includes a name that doesn't resolve, and text that isn't a usable URL at all
        return False

async def isUrlImageContentTypeAndStatus200(url):
    image_formats = ('image/png', 'image/jpeg', 'image/jpg', 'image/gif')
    async with httpx.AsyncClient() as httpxClient:
        try:
            # redirects are followed by hand, as each one could point somewhere new
            for _ in range(MAX_URL_REDIRECTS + 1):
                if not await isPublicUrl(url):
                    return False
                # streamed: the status and headers answer this, so the body is never downloaded
                async with httpxClient.stream('GET', url, timeout = 60) as response:
                    if response.has_redirect_location:
                        url = str(response.url.join(response.headers['location']))
                        continue
                    # the header may be absent, and may carry parameters ('image/png; charset=utf-8'),
                    # so compare on the media type alone
                    mediaType = response.headers.get('content-type', '').split(';')[0].strip().lower()
                    return response.status_code == 200 and mediaType in image_formats
            return False
        except (httpx.HTTPError, httpx.InvalidURL, ValueError):
            # unreachable, or text that isn't a usable URL at all
            return False

def calculateTimeLeftStr(secondsLeft):
    m, s = divmod(secondsLeft, 60)
    h, m = divmod(m, 60)
    return f'{int(h):d}h {int(m):02d}m {int(s):02d}s'

def roundDecimalPlaces(decimal, places):
    precision = '0' * places
    return Decimal(str(decimal)).quantize(Decimal(f'1.{precision}'), rounding = ROUND_HALF_UP)

def copyDictWithoutKeys(myDict, excludeKeys):
    return { x: myDict[x] for x in myDict if x not in excludeKeys }

def filterGuildsForInstance(client: nextcord.Client, allServerData: dict):
    instanceGuilds = [ str(guild.id) for guild in client.guilds ]
    filteredServerData = allServerData.copy()
    for serverId in allServerData.keys():
        if serverId not in instanceGuilds:
            filteredServerData.pop(serverId)

    return filteredServerData

def getServerPrefixOrDefault(message: nextcord.Message):
    if message.guild == None:
        return '.'
    return config_queries.getServerValue(message.guild.id, 'prefix')

async def getCommandPrefix(client, message: nextcord.Message):
    # runs for every message in every server, so the lookup stays off the event loop
    return await GBotFirebaseService.run(getServerPrefixOrDefault, message)

def getGuildsForPatreonToIgnore():
    patreonGuildId = GBotPropertiesManager.PATREON_GUILD_ID
    # copy, so appending the patreon guild below does not mutate the property itself
    guildsToIgnore = list(GBotPropertiesManager.PATREON_IGNORE_GUILDS)
    if patreonGuildId not in guildsToIgnore:
        guildsToIgnore.append(patreonGuildId)
    return guildsToIgnore

async def getOnlineAndIdleUsers(guild: nextcord.Guild):
    onlineUsers = []
    async for member in guild.fetch_members():  # pragma: no branch
        memberWithStatusInfo = guild.get_member(member.id)
        if not memberWithStatusInfo.bot and (memberWithStatusInfo.status == nextcord.Status.online or memberWithStatusInfo.status == nextcord.Status.idle):
            onlineUsers.append(memberWithStatusInfo)
    return onlineUsers

async def getUserIdFromName(guild: nextcord.Guild, name: str):
    async for member in guild.fetch_members():
        if member.name.lower() == name.lower():
            return member.id
    return None

async def sendMessageToAdmins(client: nextcord.Client, serverId, message, logger):
    channelId = await GBotFirebaseService.run(config_queries.getServerValue, int(serverId), 'channel_admin')
    try:
        # int(channelId) already raises for an unset channel, which lands in the except below
        channel: nextcord.TextChannel = await client.fetch_channel(int(channelId))
        if channel != None:
            await channel.send(message)
            return True
        else:
            return False
    except Exception as e:
        logger.error(f'Admin channel not configured correctly for server {serverId}: {e}')
        return False

async def purgePreviousMessages(deleteMessages, channel: nextcord.TextChannel):
    # delete all PartialInteractionMessage messages
    # delete all messages not in configured channel
    copyDeleteMessages = deleteMessages.copy()
    for deleteMessage in copyDeleteMessages:
        if isinstance(deleteMessage, nextcord.PartialInteractionMessage):
            deleteMessages.remove(deleteMessage)
            await deleteMessage.delete()
        elif deleteMessage.channel.id != channel.id:
            deleteMessages.remove(deleteMessage)
            # not the message's own delete: a deferred slash reply's uses its interaction token, which
            # expires after 15 minutes, and a refusal can wait hours for the next Storm's purge. Its
            # channel is only a PartialMessageable, which can't make a partial message, so the real
            # one comes from the guild. Someone may have deleted the message or the channel already.
            messageChannel = channel.guild.get_channel_or_thread(deleteMessage.channel.id)
            if messageChannel is not None:
                try:
                    await messageChannel.get_partial_message(deleteMessage.id).delete()
                except nextcord.NotFound:
                    pass

    # delete remaining messages in configured channel in bulk
    if len(deleteMessages) <= 100:
        await channel.delete_messages(deleteMessages)
    else:
        # separate list into chunks of 100 messages max (Discord's bulk-delete cap)
        for i in range(0, len(deleteMessages), 100):
            await channel.delete_messages(deleteMessages[i:i + 100])

async def removeRoleFromAllUsers(guild: nextcord.Guild, role: nextcord.Role):
    try:
        async for member in guild.fetch_members():  # pragma: no branch
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