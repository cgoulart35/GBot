#region IMPORTS
import logging
import json
import nextcord
from quart import abort

from GBotDiscord.src.config import config_queries
#endregion

class Discord():
    logger = logging.getLogger()

    def get():
        return {
            "options": {
                "action": [
                    {
                        "name": "leaveGuild",
                        "serverId": "012345678910111213"
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
                if serverId != "" and config_queries.getAllServerValues(serverId) is not None:
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
                    await channel.send(message, reference = messageToReplyTo)
                    return {"action": "sendMessage", "status": "success"}
                else:
                    await channel.send(message)
                    return {"action": "sendMessage", "status": "success"}

            return {"status": "error", "message": "Error: Invalid request."}
        except:
            abort(400, "Error: Unhandled exception.")