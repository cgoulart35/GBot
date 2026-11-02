#region IMPORTS
import logging
import nextcord
from quart import abort
#endregion

def abortUnhandled(error):
    # A request that doesn't make sense is the caller's to fix. Anything else is ours: a 400 would send
    # someone hunting for a problem in a request that was fine, so it is logged and reported as a 500.
    if isinstance(error, (ValueError, TypeError, AttributeError, KeyError, nextcord.NotFound)):
        abort(400, "Error: Invalid request.")
    logging.getLogger().error(f'GBot API request failed: {error}', exc_info = error)
    abort(500, "Error: Internal error.")
