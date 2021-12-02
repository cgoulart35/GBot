#region IMPORTS
import logging
import pathlib
import json
import random
import asyncio
import requests
import discord
from discord.ext import commands, tasks
from datetime import datetime
from urllib import parse
from table2ascii import table2ascii, PresetStyle
from collections import OrderedDict

import utils
import predicates
import halo.queries
import config.queries
from properties import botConfig
#endregion

class Halo(commands.Cog):

    def __init__(self, client):
        self.client = client
        self.logger = logging.getLogger()
        self.parentDir = str(pathlib.Path(__file__).parent.parent.absolute()).replace("\\",'/')
        self.HALO_IMG_FILE = discord.File(f'{self.parentDir}/images/haloInfiniteImage.jpg')
        self.HOST = 'https://cryptum.halodotapi.com/games/hi'
        self.PATH_MOTD = '/motd'
        self.PATH_SERVICE_RECORD = '/stats/players/*/service-record/global'
        self.HALO_MOTD_HOUR = botConfig['properties']['haloInfiniteMotdHour']
        self.HALO_MOTD_MINUTE = botConfig['properties']['haloInfiniteMotdMinute']
        self.HALO_COMPETITION_DAY = botConfig['properties']['haloInfiniteCompetitionDay']
        self.HALO_COMPETITION_HOUR = botConfig['properties']['haloInfiniteCompetitionHour']
        self.HALO_COMPETITION_MINUTE = botConfig['properties']['haloInfiniteCompetitionMinute']
        self.HALO_COMPETITION_VARIABLES = [
            'Kills',
            'Melee Kills',
            'Grenade Kills',
            'Headshot Kills',
            'Power Weapon Kills',
            'Assists',
            'Emp Assists',
            'Driver Assists',
            'Callout Assists',
            'Vehicles Destroyed',
            'Vehicles Hijacked',
            'Matches Won',
            'Matches Played',
            'Time Played',
            'Total Score',
            'Medals',
            'Shots Landed',
            'Shots Fired',
            'Shot Accuracy (%)',
            'Win Rate (%)',
            'Kill-Death-Assist Ratio',
            'Kill-Death Ratio'
        ]
    
    # Events
    @commands.Cog.listener()
    async def on_ready(self):
        self.wait_to_start_batch_halo_MOTD.start()
        self.wait_to_start_batch_halo_player_stats.start()

    # Tasks
    @tasks.loop(minutes=1)
    async def wait_to_start_batch_halo_MOTD(self):
        dateTimeObj = datetime.now()
        if str(dateTimeObj.hour) == self.HALO_MOTD_HOUR and str(dateTimeObj.minute) == self.HALO_MOTD_MINUTE:
            self.wait_to_start_batch_halo_MOTD.cancel()
            self.logger.info('Initial kickoff time reached. Starting Halo Infinite MOTD batch job...')
            self.batch_halo_MOTD.start()

    @tasks.loop(minutes=1)
    async def wait_to_start_batch_halo_player_stats(self):
        dateTimeObj = datetime.now()
        if str(dateTimeObj.hour) == self.HALO_COMPETITION_HOUR and str(dateTimeObj.minute) == self.HALO_COMPETITION_MINUTE:
            self.wait_to_start_batch_halo_player_stats.cancel()
            self.logger.info('Initial kickoff time reached. Starting Halo Infinite Player Stats batch job...')
            self.batch_halo_player_stats.start()

    @tasks.loop(hours=24)
    async def batch_halo_MOTD(self):
        asyncio.create_task(self.haloMotdGetRequest())

    @tasks.loop(hours=24)
    async def batch_halo_player_stats(self):
        asyncio.create_task(self.haloPlayerStatsGetRequests())

    async def haloMotdGetRequest(self):
        self.logger.info('Retrieving Halo Infinite MOTD...')
        dateTimeObj = datetime.now()
        date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")
        url = self.HOST + self.PATH_MOTD
        cryptumToken = botConfig['properties']['cryptumToken']
        headers = {
            'Content-Type': 'application/json',
            'Cryptum-API-Version': '2.3-alpha',
            'Authorization': f'Cryptum-Token {cryptumToken}'
        }
        response = requests.request("GET", url, headers = headers, verify = False)
        newJsonMOTD = response.json()
        oldJsonMOTD = halo.queries.getLatestHaloInfiniteMOTD()
        newStrMOTD = json.dumps(newJsonMOTD, sort_keys = True)
        oldStrMOTD = json.dumps(oldJsonMOTD, sort_keys = True)
        if newStrMOTD != oldStrMOTD:
            self.logger.info('Saving Halo Infinite MOTD...')
            halo.queries.postHaloInfiniteMOTD(date, newJsonMOTD)
            asyncio.create_task(self.haloMotdSendDiscord(newJsonMOTD))
        else:
            self.logger.info('No new updates in the Halo Infinite MOTD.')

    async def haloMotdSendDiscord(self, jsonMOTD):
        self.logger.info('Sending Halo Infinite MOTD to guilds...')
        servers = config.queries.getAllServers()
        for serverId, serverValues in servers.items():
            if serverValues['toggle_halo']:
                channel = await self.client.fetch_channel(serverValues['channel_halo_motd'])
                for msg in jsonMOTD['data']:
                    msgTitle = msg['title']
                    msgText = msg['message']
                    msgImageUrl = msg['image_url']
                    embed = discord.Embed(color = discord.Color.purple(), title = msgTitle, description = msgText)
                    embed.set_image(url = msgImageUrl)
                    await channel.send(embed = embed)

    async def haloPlayerStatsGetRequests(self):
        self.logger.info('Retrieving Halo Infinite Player Stats...')
        allServerConfigs = config.queries.getAllServers()
        allHaloInfiniteServers = halo.queries.getAllHaloInfiniteServers()
        obtainedPlayerData = {}
        for serverId, serverValues in allServerConfigs.items():
            dateTimeObj = datetime.now()
            date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")
            freshPlayerDataCompetition = { 'start_day': date, 'participants': {} }
            if serverValues['toggle_halo']:
                nextCompetitionId = halo.queries.getNextCompetitionId(serverId)
                channel = await self.client.fetch_channel(serverValues['channel_halo_competition'])
                try:
                    players = allHaloInfiniteServers[serverId]['participating_players']
                    # if it is not competition announcement day, filter participating players to those only who had data grabbed at start of week
                    if str(dateTimeObj.weekday()) != self.HALO_COMPETITION_DAY:
                        players = dict(filter(lambda playerItem: halo.queries.isUserInThisWeeksInitialDataFetch(serverId, nextCompetitionId - 1, playerItem[0]), players.items()))
                except Exception:
                    players = {}
                for playerId, playerValues in players.items():
                    gamertag = playerValues['gamertag']
                    if gamertag not in obtainedPlayerData:
                        playerGamertagUrl = parse.quote(gamertag)
                        url = self.HOST + self.PATH_SERVICE_RECORD.replace('*', playerGamertagUrl)
                        cryptumToken = botConfig['properties']['cryptumToken']
                        headers = {
                            'Content-Type': 'application/json',
                            'Cryptum-API-Version': '2.3-alpha',
                            'Authorization': f'Cryptum-Token {cryptumToken}'
                        }
                        response = requests.request("GET", url, headers = headers, verify = False)
                        playerDataJson = response.json()
                        obtainedPlayerData[gamertag] = playerDataJson
                    else:
                        playerDataJson = obtainedPlayerData[gamertag]
                    freshPlayerDataCompetition['participants'][playerId] = playerDataJson

                # if it is new competition time, post the data to database and announce winners
                if str(dateTimeObj.weekday()) == self.HALO_COMPETITION_DAY:
                    competitionVariable = random.choice(self.HALO_COMPETITION_VARIABLES)
                    freshPlayerDataCompetition['competition_variable'] = competitionVariable
                    halo.queries.postHaloInfiniteServerPlayerData(serverId, nextCompetitionId, freshPlayerDataCompetition)
                    if nextCompetitionId == 0:
                        headerStr = "**Week  0:  The  week  you  probably  didn't  even  know  about...**"
                        descriptionStr = 'Hello there! Week 1 of Halo Infinite challenges starts a week from right now!\nSign up before the next week starts to be included in random weekly challenges!\n\nUse the commands below to participate in the weekly Halo Infinite challenges.\n\n__Participate:__\n.halo YOUR_GAMERTAG\n__Leave:__\n.halo rm'
                        embed = discord.Embed(color = discord.Color.dark_blue(), title = headerStr, description = descriptionStr)
                        embed.set_image(url=f'attachment://{self.HALO_IMG_FILE.filename}')
                        await channel.send(embed = embed, file = self.HALO_IMG_FILE)
                        continue
                    elif nextCompetitionId == 1:
                        headerStr = '**Week  1:  The  competition  starts  now!**'
                        descriptionStr = f'__Random Competition Variable:__\n{competitionVariable}\n\nForget to participate for Week 1? No worries!\nSign up before the next week starts to be included in random weekly challenges!\n\nUse the commands below to participate in the weekly Halo Infinite challenges.\n\n__Participate:__\n.halo YOUR_GAMERTAG\n__Leave:__\n.halo rm'
                        embed = discord.Embed(color = discord.Color.dark_blue(), title = headerStr, description = descriptionStr)
                        embed.set_image(url=f'attachment://{self.HALO_IMG_FILE.filename}')
                        await channel.send(embed = embed, file = self.HALO_IMG_FILE)
                        continue
                    else:
                        winnersAndTable = await self.generatePlayerProgressTableAndWinners(serverId, nextCompetitionId - 1, freshPlayerDataCompetition)

                        headerStr = f'**Week  {nextCompetitionId - 1}  Results!**'
                        if winnersAndTable[0] != '':
                            winnersStr = 'Congratulations ' + winnersAndTable[0] + ' you won this weeks challenge!'
                        else:
                            winnersStr = 'No active players'
                        embed1 = discord.Embed(color = discord.Color.green(), title = headerStr, description = winnersStr)

                        headerStr = f'**Week  {nextCompetitionId}**'
                        nextWeekStr = f"__Random Competition Variable:__\n{competitionVariable}\n\nHaven't participated yet? No worries!\nSign up before the next week starts to be included in random weekly challenges!\n\nUse the commands below to participate in the weekly Halo Infinite challenges.\n\n__Participate:__\n.halo YOUR_GAMERTAG\n__Leave:__\n.halo rm"
                        embed2 = discord.Embed(color = discord.Color.dark_blue(), title = headerStr, description = nextWeekStr)
                        embed2.set_image(url=f'attachment://{self.HALO_IMG_FILE.filename}')

                        await channel.send(embed = embed1)
                        if winnersAndTable[1] != None:
                            await channel.send(f"\n```{winnersAndTable[1]}```\n")
                        await channel.send(embed = embed2, file = self.HALO_IMG_FILE)
                        continue
                # if it is not new competition time, don't post the data to database and announce progress
                else:
                    if nextCompetitionId - 1 > 0:
                        winnersAndTable = await self.generatePlayerProgressTableAndWinners(serverId, nextCompetitionId - 1, freshPlayerDataCompetition)
                        
                        headerStr = f'**Week  {nextCompetitionId - 1}  Progress!**'
                        if winnersAndTable[0] != '':
                            winnersStr = winnersAndTable[0] + ' you are in the lead!'
                        else:
                            winnersStr = 'No active players'
                        embed1 = discord.Embed(color = discord.Color.green(), title = headerStr, description = winnersStr)
                    
                        await channel.send(embed = embed1)
                        if winnersAndTable[1] != None:
                            await channel.send(f"\n```{winnersAndTable[1]}```\n")
                        continue

    async def generatePlayerProgressTableAndWinners(self, serverId, competitionId, newCompetitionDataJson):
        playerProgressData = {}
        startingCompetitionDataJson = halo.queries.getThisWeeksInitialDataFetch(serverId, competitionId)
        if startingCompetitionDataJson != None and 'competition_variable' in startingCompetitionDataJson and 'participants' in startingCompetitionDataJson:
            competitionVariable = startingCompetitionDataJson['competition_variable']
            for participantId, participantValues in startingCompetitionDataJson['participants'].items():
                if competitionVariable == 'Kills':
                    newVariable = newCompetitionDataJson['participants'][participantId]['data']['summary']['kills']
                    startingVariable = participantValues['data']['summary']['kills']

                elif competitionVariable == 'Melee Kills':
                    newVariable = newCompetitionDataJson['participants'][participantId]['data']['breakdowns']['kills']['melee']
                    startingVariable = participantValues['data']['breakdowns']['kills']['melee']

                elif competitionVariable == 'Grenade Kills':
                    newVariable = newCompetitionDataJson['participants'][participantId]['data']['breakdowns']['kills']['grenades']
                    startingVariable = participantValues['data']['breakdowns']['kills']['grenades']

                elif competitionVariable == 'Headshot Kills':
                    newVariable = newCompetitionDataJson['participants'][participantId]['data']['breakdowns']['kills']['headshots']
                    startingVariable = participantValues['data']['breakdowns']['kills']['headshots']

                elif competitionVariable == 'Power Weapon Kills':
                    newVariable = newCompetitionDataJson['participants'][participantId]['data']['breakdowns']['kills']['power_weapons']
                    startingVariable = participantValues['data']['breakdowns']['kills']['power_weapons']

                elif competitionVariable == 'Assists':
                    newVariable = newCompetitionDataJson['participants'][participantId]['data']['summary']['assists']
                    startingVariable = participantValues['data']['summary']['assists']
                    
                elif competitionVariable == 'Emp Assists':
                    newVariable = newCompetitionDataJson['participants'][participantId]['data']['breakdowns']['assists']['emp']
                    startingVariable = participantValues['data']['breakdowns']['assists']['emp']

                elif competitionVariable == 'Driver Assists':
                    newVariable = newCompetitionDataJson['participants'][participantId]['data']['breakdowns']['assists']['driver']
                    startingVariable = participantValues['data']['breakdowns']['assists']['driver']

                elif competitionVariable == 'Callout Assists':
                    newVariable = newCompetitionDataJson['participants'][participantId]['data']['breakdowns']['assists']['callouts']
                    startingVariable = participantValues['data']['breakdowns']['assists']['callouts']

                elif competitionVariable == 'Vehicles Destroyed':
                    newVariable = newCompetitionDataJson['participants'][participantId]['data']['summary']['vehicles']['destroys']
                    startingVariable = participantValues['data']['summary']['vehicles']['destroys']

                elif competitionVariable == 'Vehicles Hijacked':
                    newVariable = newCompetitionDataJson['participants'][participantId]['data']['summary']['vehicles']['hijacks']
                    startingVariable = participantValues['data']['summary']['vehicles']['hijacks']

                elif competitionVariable == 'Matches Won':
                    newVariable = newCompetitionDataJson['participants'][participantId]['data']['breakdowns']['matches']['wins']
                    startingVariable = participantValues['data']['breakdowns']['matches']['wins']

                elif competitionVariable == 'Matches Played':
                    newVariable = newCompetitionDataJson['participants'][participantId]['data']['matches_played']
                    startingVariable = participantValues['data']['matches_played']

                elif competitionVariable == 'Time Played':
                    newVariable = newCompetitionDataJson['participants'][participantId]['data']['time_played']['seconds']
                    startingVariable = participantValues['data']['time_played']['seconds']

                elif competitionVariable == 'Total Score':
                    newVariable = newCompetitionDataJson['participants'][participantId]['data']['total_score']
                    startingVariable = participantValues['data']['total_score']

                elif competitionVariable == 'Medals':
                    newVariable = newCompetitionDataJson['participants'][participantId]['data']['summary']['medals']
                    startingVariable = participantValues['data']['summary']['medals']

                elif competitionVariable == 'Shots Landed':
                    newVariable = newCompetitionDataJson['participants'][participantId]['data']['shots']['landed']
                    startingVariable = participantValues['data']['shots']['landed']

                elif competitionVariable == 'Shots Fired':
                    newVariable = newCompetitionDataJson['participants'][participantId]['data']['shots']['fired']
                    startingVariable = participantValues['data']['shots']['fired']

                elif competitionVariable == 'Shot Accuracy (%)':
                    newVariable = newCompetitionDataJson['participants'][participantId]['data']['shots']['accuracy']
                    startingVariable = participantValues['data']['shots']['accuracy']

                elif competitionVariable == 'Win Rate (%)':
                    newVariable = newCompetitionDataJson['participants'][participantId]['data']['win_rate']
                    startingVariable = participantValues['data']['win_rate']

                elif competitionVariable == 'Kill-Death-Assist Ratio':
                    newVariable = newCompetitionDataJson['participants'][participantId]['data']['kda']
                    startingVariable = participantValues['data']['kda']

                elif competitionVariable == 'Kill-Death Ratio':
                    newVariable = newCompetitionDataJson['participants'][participantId]['data']['kdr']
                    startingVariable = participantValues['data']['kdr']

                diff = str(newVariable - startingVariable)
                if diff not in playerProgressData:
                    playerProgressData[diff] = []
                playerProgressData[diff].append(participantId)

        sortedPlayerProgressData = OrderedDict(sorted(playerProgressData.items(), key = lambda scoreGroup: scoreGroup[0], reverse = True))
        bodyList = []
        winnersStr = ''
        placeNumber = 1
        for score, scoreGroupValues in sortedPlayerProgressData.items():
            if score != '0':
                for participantId in scoreGroupValues:
                    if placeNumber == 1:
                        winnersStr += utils.idToUserStr(participantId) + ','
                    guild = await self.client.fetch_guild(serverId)
                    user = await guild.fetch_member(participantId)
                    userStr = user.nick if user.nick else user.name
                    gamertag = startingCompetitionDataJson['participants'][participantId]['additional']['gamertag']
                    bodyList.append([str(placeNumber), userStr, gamertag, score])
                placeNumber += 1

        if not bodyList:
            table = None
        else:
            table = table2ascii(
                header = ["Place", "Player", "Gamertag", competitionVariable],
                body = bodyList,
                style = PresetStyle.thin_compact
            )
        return (winnersStr, table)

    # Commands
    @commands.command(brief = "- Participate in or leave the weekly GBot Halo competition.", description = "Participate in or leave the weekly GBot Halo competition.\naction options are: <gamertag>, rm")
    @predicates.isFeatureEnabledForServer('toggle_halo')
    @predicates.isMessageSentInGuild()
    async def halo(self, ctx, action = None, user: discord.User = None):
        guild = ctx.guild
        serverId = guild.id
        author = ctx.author
        authorMention = author.mention
        if user != None:
            if not utils.isUserAdminOrOwner(author, guild):
                await ctx.send(f'Sorry {authorMention}, you need to be an admin to add or remove other participants.')
                return
            userId = user.id
            userMention = user.mention
        else:
            userId = author.id
            userMention = authorMention
        if action == None or action.startswith('<@'):
            await ctx.send(f'Sorry {authorMention}, you need to specify a gamertag or type \'rm\'.')
            return
        isParticipating = halo.queries.isUserParticipatingInHalo(serverId, userId)
        if action == None or action == 'rm':
            if isParticipating:
                halo.queries.removeHaloParticipant(serverId, userId)
                await ctx.send(f'{userMention} has been removed as a Halo Infinite participant.')
            else:
                await ctx.send(f'{userMention} is not participating in Halo Infinite.')
        else:
            halo.queries.addHaloParticipant(serverId, userId, action)
            await ctx.send(f'{userMention} has been added as a Halo Infinite participant as {action}.')

def setup(client):
    client.add_cog(Halo(client))