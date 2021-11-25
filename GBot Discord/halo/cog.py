#region IMPORTS
import logging
import asyncio
import requests
import discord
from discord.ext import commands, tasks
from datetime import datetime

import halo.queries
import config.queries
from properties import botConfig
#endregion

class Halo(commands.Cog):

    def __init__(self, client):
        self.client = client
        self.logger = logging.getLogger()
        self.DAILY_HOUR = 11
        self.DAILY_MINUTE = 0
        self.host = 'https://cryptum.halodotapi.com'
        self.pathMOTD = '/games/hi/motd'
    
    # Events
    @commands.Cog.listener()
    async def on_ready(self):
        self.wait_to_start_daily_batch_jobs.start()

    # Tasks
    @tasks.loop(minutes=1)
    async def wait_to_start_daily_batch_jobs(self):
        dateTimeObj = datetime.now()
        if dateTimeObj.hour == self.DAILY_HOUR and dateTimeObj.minute == self.DAILY_MINUTE:
            self.wait_to_start_daily_batch_jobs.cancel()
            self.logger.info('Initial kickoff time reached. Starting daily batch jobs...')
            self.batch_update_halo_MOTD.start()

    @tasks.loop(hours=24)
    async def batch_update_halo_MOTD(self):
        asyncio.create_task(self.haloMotdGetRequest())

    async def haloMotdGetRequest(self):
        self.logger.info('Retrieving Halo Infinite MOTD...')
        dateTimeObj = datetime.now()
        date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")
        url = self.host + self.pathMOTD
        cryptumToken = botConfig['properties']['cryptumToken']
        headers = {
            'Content-Type': 'application/json',
            'Cryptum-API-Version': '2.3-alpha',
            'Authorization': f'Cryptum-Token {cryptumToken}'
        }
        response = requests.request("GET", url, headers = headers, verify = False)
        jsonMOTD = response.json()
        self.logger.info('Saving Halo Infinite MOTD...')
        halo.queries.postHaloInfiniteMOTD(date, jsonMOTD)
        asyncio.create_task(self.haloMotdSendDiscord(jsonMOTD))

    async def haloMotdSendDiscord(self, jsonMOTD):
        self.logger.info('Sending Halo Infinite MOTD to guilds...')
        servers = config.queries.getAllServers()
        for serverId, serverValues in servers.items():
            if serverValues['toggle_halo']:
                channel = await self.client.fetch_channel(serverValues['channel_halo'])
                for msg in jsonMOTD['data']:
                    msgTitle = msg['title']
                    msgText = msg['message']
                    msgImageUrl = msg['image_url']
                    embed = discord.Embed(color = discord.Color.purple(), title = msgTitle, description = msgText)
                    embed.set_image(url = msgImageUrl)
                    await channel.send(embed = embed)

def setup(client):
    client.add_cog(Halo(client))