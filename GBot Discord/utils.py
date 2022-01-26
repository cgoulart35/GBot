#region IMPORTS
import os
import re
import httpx
import itertools
import pandas
import df2img
import nextcord
from typing import List

import config.queries
#endregion

def idToUserStr(userId):
    return '<@!' + str(userId) + '>'

def idToRoleStr(userId):
    return '<@&' + str(userId) + '>'

def idToChannelStr(userId):
    return '<#' + str(userId) + '>'

def isUserAdminOrOwner(user: nextcord.Member, guild: nextcord.Guild):
    roles: List[nextcord.Role] = user.roles
    assignedRoleIds = [role.id for role in roles]
    adminRoleId = config.queries.getServerValue(guild.id, 'role_admin')
    if (user.id != guild.owner_id) and (adminRoleId not in assignedRoleIds):
        return False
    return True

async def isUrlStatus200(url):
    async with httpx.AsyncClient() as httpxClient:
        response = await httpxClient.get(url, timeout = 60)
        if response.status_code != 200:
            return False
        else:
            return True

async def sendDiscordEmbed(channel: nextcord.TextChannel, title, description, color, file: nextcord.File = None, fileURL = None):
    embed = nextcord.Embed(title = title, description = description, color = color)
    if file != None and fileURL == None:
        embed.set_image(url = f'attachment://{file.filename}')
    elif file == None and fileURL != None:
        embed.set_image(url = fileURL)
    else:
        file = None
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

def createTempTableImage(bodyList, colList, title, colWidth):
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
            font_color = 'darkred',
            font_family = 'Times New Roman',
            font_size = 22,
            text = title,
        ),
        tbl_header = dict(
            align = 'right',
            fill_color = 'blue',
            font_color = 'white',
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
    df2img.save_dataframe(fig = fig, filename='tempDataTable.png')

def deleteTempTableImage():
    if os.path.exists('tempDataTable.png'):
        os.remove('tempDataTable.png')
        return True
    return False

# Method taken from yt-dlp for filename sanitizing
def sanitize_filename(s, restricted=False, is_id=False):
    """Sanitizes a string so it could be used as part of a filename.
    If restricted is set, use a stricter subset of allowed characters.
    Set is_id if this is not an arbitrary string, but an ID that should be kept
    if possible.
    """

    ACCENT_CHARS = dict(zip('ÂÃÄÀÁÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖŐØŒÙÚÛÜŰÝÞßàáâãäåæçèéêëìíîïðñòóôõöőøœùúûüűýþÿ',
                        itertools.chain('AAAAAA', ['AE'], 'CEEEEIIIIDNOOOOOOO', ['OE'], 'UUUUUY', ['TH', 'ss'],
                                        'aaaaaa', ['ae'], 'ceeeeiiiionooooooo', ['oe'], 'uuuuuy', ['th'], 'y')))

    def replace_insane(char):
        if restricted and char in ACCENT_CHARS:
            return ACCENT_CHARS[char]
        elif not restricted and char == '\n':
            return ' '
        elif char == '?' or ord(char) < 32 or ord(char) == 127:
            return ''
        elif char == '"':
            return '' if restricted else '\''
        elif char == ':':
            return '_-' if restricted else ' -'
        elif char in '\\/|*<>':
            return '_'
        if restricted and (char in '!&\'()[]{}$;`^,#' or char.isspace()):
            return '_'
        if restricted and ord(char) > 127:
            return '_'
        return char

    if s == '':
        return ''
    # Handle timestamps
    s = re.sub(r'[0-9]+(?::[0-9]+)+', lambda m: m.group(0).replace(':', '_'), s)
    result = ''.join(map(replace_insane, s))
    if not is_id:
        while '__' in result:
            result = result.replace('__', '_')
        result = result.strip('_')
        # Common case of "Foreign band name - English song title"
        if restricted and result.startswith('-_'):
            result = result[2:]
        if result.startswith('-'):
            result = '_' + result[len('-'):]
        result = result.lstrip('.')
        if not result:
            result = '_'
    return result