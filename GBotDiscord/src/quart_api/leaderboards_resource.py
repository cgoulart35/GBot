#region IMPORTS
import logging

from GBotDiscord.src.leaderboards import leaderboards_queries
from GBotDiscord.src.quart_api.errors import abortUnhandled
#endregion

class Leaderboard():
    logger = logging.getLogger()

    def get():
        try:
            return leaderboards_queries.getLeaderboard()
        except Exception as e:
            abortUnhandled(e)