#region IMPORTS
import logging
from quart import abort

from GBotDiscord.src.leaderboards import leaderboards_queries
#endregion

class Leaderboard():
    logger = logging.getLogger()

    def get():
        try:
            return leaderboards_queries.getLeaderboard()
        except:
            abort(400, "Error: Unhandled exception.")