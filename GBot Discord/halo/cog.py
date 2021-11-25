#region IMPORTS
import logging
import aiohttp
import requests
import asyncio
import discord
from discord.ext import commands, tasks
from datetime import datetime

import predicates
import utils
import halo.queries
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

    @tasks.loop(minutes=2)
    async def batch_update_halo_MOTD(self):
        asyncio.create_task(self.haloMotdGetRequest())
        # TODO send batch messages out to all servers with embeds of all pages

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
        self.logger.info('Saving Halo Infinite MOTD...')
        halo.queries.postHaloInfiniteMOTD(date, response.json())

def setup(client):
    client.add_cog(Halo(client))