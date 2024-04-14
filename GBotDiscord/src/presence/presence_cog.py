#region IMPORTS
import logging
import nextcord
from nextcord.ext import commands, tasks
from datetime import datetime

from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

class Presence(commands.Cog):

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()
        self.presence_index = 0
        self.default_presence_activities = []
        self.custom_presence_expire_time = datetime.now()

    #Events
    @commands.Cog.listener()
    async def on_ready(self):
        self.default_presence_activities.append(nextcord.Game(f'GBot {GBotPropertiesManager.GBOT_VERSION}'))
        self.default_presence_activities.append(nextcord.Activity(type = nextcord.ActivityType.listening, name = "slash commands"))
        self.default_presence_activities.append(nextcord.Activity(type = nextcord.ActivityType.watching, name = "user messages"))
        try:
            self.loop_presence.start()
        except RuntimeError:
            self.logger.info('loop_presence task is already launched and is not completed.')

    # Tasks
    @tasks.loop(seconds=20)
    async def loop_presence(self):
        try:
            currentTime = datetime.now()
            if self.custom_presence_expire_time and currentTime >= self.custom_presence_expire_time:
                await self.client.change_presence(status = nextcord.Status.online, activity = self.default_presence_activities[self.presence_index])
                self.presence_index += 1
                if self.presence_index > len(self.default_presence_activities) - 1: self.presence_index = 0
        except Exception as e:
            self.logger.error(f'Error in Presence.loop_presence(): {e}')

    async def changePresence(self, presence, expireTime):
        try:
            self.custom_presence_expire_time = expireTime
            await self.client.change_presence(status = nextcord.Status.online, activity = presence)
            return True
        except Exception as e:
            self.logger.error(f'Error in Presence.changePresence(): {e}')
            return False

def setup(client: commands.Bot):
    client.add_cog(Presence(client))