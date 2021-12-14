#region IMPORTS
import os
import requests
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

def isUrlStatus200(url):
    response = requests.request('GET', url, verify = False)
    if response.status_code != 200:
        return False
    else:
        return True

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

async def removeRoleFromAllUsers(guild: nextcord.Guild, role: nextcord.Role):
    async for member in guild.fetch_members():
        if role in member.roles:
            await member.remove_roles(role)