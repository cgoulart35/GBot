#region IMPORTS
import logging
import json
import nextcord
from datetime import datetime

from GBotDiscord.src import utils
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.presence.presence_cog import Presence
from GBotDiscord.src.quart_api.errors import abortUnhandled
from GBotDiscord.src.firebase import GBotFirebaseService
#endregion

class Discord():
    logger = logging.getLogger()

    def doc():
        return {
            "options": {
                "action": [
                    {
                        "name": "changePresence",
                        "type": "<playing/listening/watching>",
                        "value": "my string",
                        "expire": "<%m/%d/%y %I:%M:%S %p>"
                    },
                    {
                        "name": "leaveGuild",
                        "serverId": "012345678910111213",
                        "optionalForce": True
                    },
                    {
                        "name": "sendMessage",
                        "message": "Hello world!",
                        "channelId": "012345678910111213",
                        "optionalMessageIdForReply": "012345678910111213"
                    }               
                ]         
            },
            "postBodyTemplate": {
                "action": {
                    "name": "sendMessage",
                    "message": "Hello world!",
                    "channelId": "012345678910111213",
                    "optionalMessageIdForReply": "012345678910111213"
                }
            }
        }

    async def post(client: nextcord.Client, data):
        try:
            value = json.loads(data)

            if "action" in value and "name" in value["action"] and value["action"]["name"] == "leaveGuild" and "serverId" in value["action"]:
                # get server ID
                serverId = value["action"]["serverId"].strip()
                # make bot leave guild with that ID
                if serverId != "" and await GBotFirebaseService.run(config_queries.getAllServerValues, serverId) is not None:
                    # Protected servers never get left automatically, so a request naming one needs
                    # saying so outright. Only a real JSON true counts, not the string "true".
                    if int(serverId) in utils.getGuildsForPatreonToIgnore() and value["action"].get("optionalForce") is not True:
                        return {"action": "leaveGuild", "status": "failure", "message": f'Server {serverId} is protected by PATREON_IGNORE_GUILDS. Set "optionalForce": true in the action to leave it anyway.'}
                    guild = await client.fetch_guild(serverId)
                    await guild.leave()
                    return {"action": "leaveGuild", "status": "success"}

            elif "action" in value and "name" in value["action"] and value["action"]["name"] == "sendMessage" and "message" in value["action"] and "channelId" in value["action"]:
                # send message
                message = value["action"]["message"].strip()
                channelId = value["action"]["channelId"].strip()
                channel = await client.fetch_channel(channelId)

                if "optionalMessageIdForReply" in value["action"]:
                    optionalMessageIdForReply = value["action"]["optionalMessageIdForReply"].strip()
                    messageToReplyTo = await channel.fetch_message(optionalMessageIdForReply)
                    await channel.send(message, reference = messageToReplyTo, allowed_mentions = nextcord.AllowedMentions.all())
                    return {"action": "sendMessage", "status": "success"}
                else:
                    # written by whoever holds API access rather than repeated from a user, so it keeps
                    # the pings presentation.ALLOWED_MENTIONS turns off
                    await channel.send(message, allowed_mentions = nextcord.AllowedMentions.all())
                    return {"action": "sendMessage", "status": "success"}
                
            elif "action" in value and "name" in value["action"] and value["action"]["name"] == "changePresence" and "type" in value["action"] and "value" in value["action"]:
                try:
                    message = "Invalid expire. Please format as: %m/%d/%y %I:%M:%S %p"
                    expire = None
                    if "expire" in value["action"]:
                        stringTime = value["action"]["expire"]
                        expire = datetime.strptime(stringTime, "%m/%d/%y %I:%M:%S %p")

                    message = "Invalid type. Please use one of the following: playing listening watching"
                    type = value["action"]["type"]
                    if type != "playing" and type != "listening" and type != "watching":
                        raise Exception
                    
                    message = "Invalid value."
                    presenceText = value["action"]["value"]
                    if type == "playing":
                        activity = nextcord.Game(presenceText)
                    elif type == "listening":
                        activity = nextcord.Activity(type = nextcord.ActivityType.listening, name = presenceText)
                    elif type == "watching":  # pragma: no branch
                        activity = nextcord.Activity(type = nextcord.ActivityType.watching, name = presenceText)

                    message = "Unable to change presence."
                    presence: Presence = client.get_cog('Presence')
                    result = await presence.changePresence(activity, expire)
                    if result:
                        message = f"Presence set to: '{type} {presenceText}'"
                        if expire:
                            message += f" until {stringTime}"
                        return {"action": "changePresence", "status": "success", "message": message}
                    else:
                        raise Exception
                except Exception:
                    return {"action": "changePresence", "status": "failure", "message": f"Error: {message}"}

            return {"status": "error", "message": "Error: Invalid request."}
        except Exception as e:
            abortUnhandled(e)