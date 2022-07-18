#region IMPORTS
import os
import logging
import asyncio
import random
import re
import typing
import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context

from GBotDiscord import utils
from GBotDiscord import pagination
from GBotDiscord import predicates
from GBotDiscord.hype import hype_queries
from GBotDiscord.exceptions import UserCancelledCommand
#endregion

class Hype(commands.Cog):

    EmojiInputType = typing.Union[nextcord.Emoji, nextcord.PartialEmoji, str]

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()
        self.USER_RESPONSE_TIMEOUT_SECONDS = int(os.getenv("USER_RESPONSE_TIMEOUT_SECONDS"))

    # Events
    @commands.Cog.listener()
    async def on_message(self, msg: nextcord.Message):
        # make sure message in a guild not from a bot
        if (msg.guild != None and not msg.author.bot):
            serverId = msg.guild.id

            # get all regex for this server and check if there is a match
            matches = hype_queries.getAllServerMatches(serverId)
            if matches != None:
                for match in matches.values():
                    regex = match['regex']
                    responses = match['responses']
                    isReaction = match['isReaction']
                    
                    # select a random response in the list of options
                    response = random.choice(responses)

                    if re.match(regex, msg.content):
                        if isReaction:
                            await msg.add_reaction(response)
                        else:
                            await msg.reply(response)
                        self.logger.info(f'GBot Hype responded to a match in server {serverId} sent from {msg.author.name} ({msg.author.id}).')

    # Commands
    @commands.command(aliases=['hy'], brief = "- Set a regular expression to match against new messages in this server, and a list of possible responses to reply to it with. (admin only)", description = "Set a regular expression to match against new messages in this server, and a list of possible responses to reply to it with. Surround regex and response each with double quotes if multiple words. (admin only)")
    @predicates.isMessageAuthorAdmin()
    @predicates.isFeatureEnabledForServer('toggle_hype')
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def hype(self, ctx: Context, regex, *responses):
        hype_queries.createMatch(ctx.guild.id, regex, list(responses), False)
        await ctx.send(f"A new message match has been created with regex '{regex}'. All matching messages will reply with one of the following: {list(responses)}")

    @commands.command(aliases=['re'], brief = "- Set a regular expression to match against new messages in this server, and a list of possible emojis to react to it with. (admin only)", description = "Set a regular expression to match against new messages in this server, and a list of possible emojis to react to it with. Surround regex with double quotes if multiple words. (admin only)")
    @predicates.isMessageAuthorAdmin()
    @predicates.isFeatureEnabledForServer('toggle_hype')
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def react(self, ctx: Context, regex, *emojis: EmojiInputType):
        emojiList = []
        for emoji in emojis:
            if isinstance(emoji, nextcord.Emoji):
                emojiList.append(f'<:{emoji.name}:{emoji.id}>')
            else:
                emojiList.append(emoji)

        hype_queries.createMatch(ctx.guild.id, regex, list(emojiList), True)
        await ctx.send(f"A new message match has been created with regex '{regex}'. All matching messages will react with one of the following: {list(emojiList)}")

    @commands.command(aliases=['um'], brief = "- Remove an existing regular expression match repsonse in this server. (admin only)", description = "Remove an existing regular expression match repsonse in this server. (admin only)")
    @predicates.isMessageAuthorAdmin()
    @predicates.isFeatureEnabledForServer('toggle_hype')
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def unmatch(self, ctx: Context):
            serverId = ctx.guild.id
            userMention = ctx.author.mention
            matches = hype_queries.getAllServerMatches(serverId)
            if matches != None:
                try:
                    matchIds = []
                    fields = []
                    counter = 1
                    for matchId, matchValues in matches.items():
                        matchIds.append(matchId)
                        regex = matchValues['regex']
                        responses = matchValues['responses']
                        isReaction = matchValues['isReaction']
                        if isReaction:
                            fields.append((f'Match {counter}', f'`Regex: {regex}`\n`Reactions: {responses}`'))
                        else:
                            fields.append((f'Match {counter}', f'`Regex: {regex}`\n`Replies: {responses}`'))
                        counter += 1

                    if ctx.guild.icon != None:
                        thumbnailUrl = ctx.guild.icon.url
                    else:
                        thumbnailUrl = None 

                    # print out configured matches with corresponding selection number
                    pages = pagination.CustomButtonMenuPages(source = pagination.FieldPageSource(fields, thumbnailUrl, "GBot Hype Matches", nextcord.Color.blue(), False, 10))
                    await pages.start(ctx)

                    # ask for number selection until users respond with answer or 'cancel'
                    numberObtained = False
                    errorMsg = ''
                    while(not numberObtained):
                        userResponse: nextcord.Message = await utils.askUserQuestion(self.client, ctx, f'{errorMsg} What match would you like to remove for this server? Please respond with the corresponding number.', self.USER_RESPONSE_TIMEOUT_SECONDS)
                        content = userResponse.content
                        # if user's reponse is string
                        if content != '':
                            # if response content starts with command prefix or is cancel then cancel current command
                            if content.lower() == 'cancel' or content.startswith(utils.getServerPrefixOrDefault(userResponse)):
                                raise UserCancelledCommand
                            else:
                                # if string provided is a valid number
                                if content.isnumeric():
                                    selection = int(content)
                                    if selection > 0 and selection <= len(matchIds):
                                        numberObtained = True
                                errorMsg = 'Invalid selection.'

                    # remove the match using the user's submitted selection
                    hype_queries.removeMatch(serverId, matchIds[selection - 1])
                    await ctx.send(f'Match {selection} deleted.')
                except asyncio.TimeoutError:
                    await ctx.send(f'Sorry {userMention}, you did not respond in time.')
                except UserCancelledCommand:
                    await ctx.send(f'{userMention}, match deletion has been cancelled.')
            else:
                await ctx.send(f'Sorry {userMention}, the server has no matches configured.')

def setup(client: commands.Bot):
    client.add_cog(Hype(client))