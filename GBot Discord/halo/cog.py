#region IMPORTS
import logging
import pathlib
import json
import random
import asyncio
import requests
import nextcord
from nextcord.ext import commands, tasks
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
        self.HALO_IMG_FILE = nextcord.File(f'{self.parentDir}/images/haloInfiniteImage.jpg')
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
            if serverValues['toggle_halo'] and 'channel_halo_motd' in serverValues:
                channel = await self.client.fetch_channel(serverValues['channel_halo_motd'])
                for msg in jsonMOTD['data']:
                    msgTitle = msg['title']
                    msgText = msg['message']
                    msgImageUrl = msg['image_url']
                    embed = nextcord.Embed(color = nextcord.Color.purple(), title = msgTitle, description = msgText)
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
            if serverValues['toggle_halo'] and 'channel_halo_competition' in serverValues:
                nextCompetitionId = halo.queries.getNextCompetitionId(serverId)
                channel = await self.client.fetch_channel(serverValues['channel_halo_competition'])
                try:
                    players = allHaloInfiniteServers[serverId]['participating_players']
                    # always filter only those participating
                    players = dict(filter(lambda playerItem: halo.queries.isUserParticipatingInHalo(serverId, playerItem[0]), players.items()))
                    # if it is not competition announcement day, filter participating players to those only who had data grabbed at start of week to limit API cost
                    if str(dateTimeObj.weekday()) != self.HALO_COMPETITION_DAY:
                        players = dict(filter(lambda playerItem: halo.queries.isUserInThisWeeksInitialDataFetch(serverId, nextCompetitionId - 1, playerItem[0]), players.items()))
                    
                except Exception:
                    players = {}
                for playerId, playerValues in players.items():
                    gamertag = playerValues['gamertag']
                    wins = playerValues['wins']
                    if gamertag not in obtainedPlayerData:
                        playerDataJson = self.haloPlayerStatsGetRequest(gamertag)
                        if not playerDataJson:
                            continue
                        playerDataJson['wins'] = wins
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
                        embed = nextcord.Embed(color = nextcord.Color.dark_blue(), title = headerStr, description = descriptionStr)
                        embed.set_image(url=f'attachment://{self.HALO_IMG_FILE.filename}')
                        await channel.send(embed = embed, file = self.HALO_IMG_FILE)
                        continue
                    elif nextCompetitionId == 1:
                        headerStr = '**Week  1:  The  competition  starts  now!**'
                        descriptionStr = f'__Random Competition Variable:__\n{competitionVariable}\n\nForget to participate for Week 1? No worries!\nSign up before the next week starts to be included in random weekly challenges!\n\nUse the commands below to participate in the weekly Halo Infinite challenges.\n\n__Participate:__\n.halo YOUR_GAMERTAG\n__Leave:__\n.halo rm'
                        embed = nextcord.Embed(color = nextcord.Color.dark_blue(), title = headerStr, description = descriptionStr)
                        embed.set_image(url=f'attachment://{self.HALO_IMG_FILE.filename}')
                        await channel.send(embed = embed, file = self.HALO_IMG_FILE)
                        continue
                    else:
                        winnersAndTable = await self.generatePlayerProgressTableAndWinners(serverId, nextCompetitionId - 1, freshPlayerDataCompetition, serverValues, True)

                        headerStr = f'**Week  {nextCompetitionId - 1}  Results!**'
                        embed1 = nextcord.Embed(color = nextcord.Color.green(), title = headerStr, description = winnersAndTable[0])

                        headerStr = f'**Week  {nextCompetitionId}**'
                        nextWeekStr = f"__Random Competition Variable:__\n{competitionVariable}\n\nHaven't participated yet? No worries!\nSign up before the next week starts to be included in random weekly challenges!\n\nUse the commands below to participate in the weekly Halo Infinite challenges.\n\n__Participate:__\n.halo YOUR_GAMERTAG\n__Leave:__\n.halo rm"
                        embed2 = nextcord.Embed(color = nextcord.Color.dark_blue(), title = headerStr, description = nextWeekStr)
                        embed2.set_image(url=f'attachment://{self.HALO_IMG_FILE.filename}')

                        await channel.send(embed = embed1)
                        if winnersAndTable[1] != None:
                            await channel.send(f"\n```{winnersAndTable[1]}```\n")
                        await channel.send(embed = embed2, file = self.HALO_IMG_FILE)
                        continue
                # if it is not new competition time, don't post the data to database and announce progress
                else:
                    if nextCompetitionId - 1 > 0:
                        winnersAndTable = await self.generatePlayerProgressTableAndWinners(serverId, nextCompetitionId - 1, freshPlayerDataCompetition, serverValues, False)
                        
                        headerStr = f'**Week  {nextCompetitionId - 1}  Progress!**'
                        embed1 = nextcord.Embed(color = nextcord.Color.green(), title = headerStr, description = winnersAndTable[0])
                    
                        await channel.send(embed = embed1)
                        if winnersAndTable[1] != None:
                            await channel.send(f"\n```{winnersAndTable[1]}```\n")
                        continue

    def haloPlayerStatsGetRequest(self, gamertag):
        playerGamertagUrl = parse.quote(gamertag)
        url = self.HOST + self.PATH_SERVICE_RECORD.replace('*', playerGamertagUrl)
        cryptumToken = botConfig['properties']['cryptumToken']
        headers = {
            'Content-Type': 'application/json',
            'Cryptum-API-Version': '2.3-alpha',
            'Authorization': f'Cryptum-Token {cryptumToken}'
        }
        response = requests.request("GET", url, headers = headers, verify = False)
        if response.status_code != 200:
            self.logger.error(f'Error retrieving player data for {gamertag}: {response.text}')
            return None
        return response.json()

    async def generatePlayerProgressTableAndWinners(self, serverId, competitionId, newCompetitionDataJson, serverValues, assignRoles):
        playerProgressData = {}
        startingCompetitionDataJson = halo.queries.getThisWeeksInitialDataFetch(serverId, competitionId)
        if startingCompetitionDataJson != None and 'competition_variable' in startingCompetitionDataJson and 'participants' in startingCompetitionDataJson:
            competitionVariable = startingCompetitionDataJson['competition_variable']
            players = newCompetitionDataJson['participants']
            # always filter participating players to those only who had data grabbed at start of week for functionality purposes
            players = dict(filter(lambda playerItem: halo.queries.isUserInThisWeeksInitialDataFetch(serverId, competitionId, playerItem[0]), players.items()))
            for participantId, participantValues in players.items():
                if competitionVariable == 'Kills':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['summary']['kills']
                    newVariable = participantValues['data']['summary']['kills']

                elif competitionVariable == 'Melee Kills':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['breakdowns']['kills']['melee']
                    newVariable = participantValues['data']['breakdowns']['kills']['melee']

                elif competitionVariable == 'Grenade Kills':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['breakdowns']['kills']['grenades']
                    newVariable = participantValues['data']['breakdowns']['kills']['grenades']

                elif competitionVariable == 'Headshot Kills':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['breakdowns']['kills']['headshots']
                    newVariable = participantValues['data']['breakdowns']['kills']['headshots']

                elif competitionVariable == 'Power Weapon Kills':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['breakdowns']['kills']['power_weapons']
                    newVariable = participantValues['data']['breakdowns']['kills']['power_weapons']

                elif competitionVariable == 'Assists':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['summary']['assists']
                    newVariable = participantValues['data']['summary']['assists']
                    
                elif competitionVariable == 'Emp Assists':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['breakdowns']['assists']['emp']
                    newVariable = participantValues['data']['breakdowns']['assists']['emp']

                elif competitionVariable == 'Driver Assists':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['breakdowns']['assists']['driver']
                    newVariable = participantValues['data']['breakdowns']['assists']['driver']

                elif competitionVariable == 'Callout Assists':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['breakdowns']['assists']['callouts']
                    newVariable = participantValues['data']['breakdowns']['assists']['callouts']

                elif competitionVariable == 'Vehicles Destroyed':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['summary']['vehicles']['destroys']
                    newVariable = participantValues['data']['summary']['vehicles']['destroys']

                elif competitionVariable == 'Vehicles Hijacked':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['summary']['vehicles']['hijacks']
                    newVariable = participantValues['data']['summary']['vehicles']['hijacks']

                elif competitionVariable == 'Matches Won':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['breakdowns']['matches']['wins']
                    newVariable = participantValues['data']['breakdowns']['matches']['wins']

                elif competitionVariable == 'Matches Played':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['matches_played']
                    newVariable = participantValues['data']['matches_played']

                elif competitionVariable == 'Time Played':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['time_played']['seconds']
                    newVariable = participantValues['data']['time_played']['seconds']

                elif competitionVariable == 'Total Score':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['total_score']
                    newVariable = participantValues['data']['total_score']

                elif competitionVariable == 'Medals':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['summary']['medals']
                    newVariable = participantValues['data']['summary']['medals']

                elif competitionVariable == 'Shots Landed':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['shots']['landed']
                    newVariable = participantValues['data']['shots']['landed']

                elif competitionVariable == 'Shots Fired':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['shots']['fired']
                    newVariable = participantValues['data']['shots']['fired']

                elif competitionVariable == 'Shot Accuracy (%)':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['shots']['accuracy']
                    newVariable = participantValues['data']['shots']['accuracy']

                elif competitionVariable == 'Win Rate (%)':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['win_rate']
                    newVariable = participantValues['data']['win_rate']

                elif competitionVariable == 'Kill-Death-Assist Ratio':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['kda']
                    newVariable = participantValues['data']['kda']

                elif competitionVariable == 'Kill-Death Ratio':
                    startingVariable = startingCompetitionDataJson['participants'][participantId]['data']['kdr']
                    newVariable = participantValues['data']['kdr']

                diff = str(newVariable - startingVariable)
                if diff not in playerProgressData:
                    playerProgressData[diff] = []
                playerProgressData[diff].append({'id': participantId, 'wins': participantValues['wins']}) 

        guild = await self.client.fetch_guild(serverId)
        if assignRoles and 'role_halo_recent' in serverValues:
            recentWinRole = guild.get_role(serverValues['role_halo_recent'])
            await utils.removeRoleFromAllUsers(guild, recentWinRole)
        else:
            recentWinRole = None

        sortedPlayerProgressData = OrderedDict(sorted(playerProgressData.items(), key = lambda scoreGroup: scoreGroup[0], reverse = True))
        bodyList = []
        playerWinCounts = {}
        winnersStr = ''
        placeNumber = 1
        for score, scoreGroupValues in sortedPlayerProgressData.items():
            for participantObj in scoreGroupValues:
                participantId = participantObj['id']
                participantWins = participantObj['wins']
                user = await guild.fetch_member(participantId)
                if placeNumber == 1 and float(score) != 0:
                    winnersStr += utils.idToUserStr(participantId) + ','
                    participantWins += 1
                    if participantWins not in playerWinCounts:
                        playerWinCounts[participantWins] = []
                    playerWinCounts[participantWins].append(participantId)
                    halo.queries.setParticipantWinCount(serverId, participantId, participantWins)
                    if recentWinRole != None:
                        await user.add_roles(recentWinRole)
                else:
                    if participantWins not in playerWinCounts:
                        playerWinCounts[participantWins] = []
                    playerWinCounts[participantWins].append(participantId)
                if float(score) != 0 or participantWins > 0:
                    userStr = user.nick if user.nick else user.name
                    gamertag = startingCompetitionDataJson['participants'][participantId]['additional']['gamertag']
                    bodyList.append([str(placeNumber), userStr, gamertag, score, str(participantWins)])
            placeNumber += 1

        if assignRoles and 'role_halo_most' in serverValues:
            mostWinsRole = guild.get_role(serverValues['role_halo_most'])
            await utils.removeRoleFromAllUsers(guild, mostWinsRole)
        else:
            mostWinsRole = None

        mostWinsStr = ''
        if mostWinsRole != None:
            sortedPlayerWinCounts = OrderedDict(sorted(playerWinCounts.items(), key = lambda winGroup: winGroup[0], reverse = True))
            for group in sortedPlayerWinCounts.values():
                for participantId in group:
                    mostWinsStr += utils.idToUserStr(participantId) + ','
                    user = await guild.fetch_member(participantId)
                    await user.add_roles(mostWinsRole)
                break

        if winnersStr != '':
            recentRoleStr = ''
            if recentWinRole != None:
                recentRoleStr = f' and were assigned {recentWinRole.mention}'
            mostRoleStr = ''
            if mostWinsRole != None:
                mostRoleStr = f' {mostWinsStr} you have the most wins and were assigned {mostWinsRole.mention}!'
            winnersStr = f"{winnersStr} you won this week's challenge{recentRoleStr}!\n{mostRoleStr}"
        else:
            winnersStr = 'No active players'

        if not bodyList:
            table = None
        else:
            table = table2ascii(
                header = ["Place", "Player", "Gamertag", competitionVariable, "Weekly Wins"],
                body = bodyList,
                style = PresetStyle.thin_compact
            )
        return (winnersStr, table)

    # Commands
    @commands.command(brief = "- Participate in or leave the weekly GBot Halo competition.", description = "Participate in or leave the weekly GBot Halo competition.\naction options are: <gamertag>, rm")
    @commands.cooldown(1, 1200)
    @predicates.isFeatureEnabledForServer('toggle_halo')
    @predicates.isMessageSentInGuild()
    async def halo(self, ctx, action = None, user: nextcord.User = None):
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
            response = self.haloPlayerStatsGetRequest(action)
            if not response:
                await ctx.send(f'Sorry {userMention}, {action} is not a valid gamertag.')
                return
            halo.queries.addHaloParticipant(serverId, userId, action)
            await ctx.send(f'{userMention} has been added as a Halo Infinite participant as {action}.')

def setup(client):
    client.add_cog(Halo(client))