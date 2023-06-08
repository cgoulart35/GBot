#region IMPORTS
import logging
import asyncio
import random
import re
import typing
import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context

from GBotDiscord.src import strings
from GBotDiscord.src import utils
from GBotDiscord.src import pagination
from GBotDiscord.src import predicates
from GBotDiscord.src.hype import hype_queries
from GBotDiscord.src.exceptions import UserCancelledCommand
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

class Hype(commands.Cog):

    EmojiInputType = typing.Union[nextcord.Emoji, nextcord.PartialEmoji, str]

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()

    # Events
    @commands.Cog.listener()
    async def on_message(self, msg: nextcord.Message):
        # make sure message in a guild not from a bot
        if (msg.guild != None and not msg.author.bot and not msg.content.startswith(utils.getServerPrefixOrDefault(msg))):
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
                            try:
                                await msg.add_reaction(response)
                            except Exception:
                                await msg.reply("GBot ran into an issue trying to react to this message. Please remove the broken match.")
                        else:
                            await msg.reply(response)
                        self.logger.info(f'GBot Hype responded to a match in server {serverId} sent from {msg.author.name} ({msg.author.id}).')

    # Commands
    @nextcord.slash_command(name = strings.HYPE_NAME, description = strings.HYPE_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_hype', False, True)
    @predicates.isMessageAuthorAdmin(True)
    async def hypeSlash(self,
                        interaction: nextcord.Interaction,
                        regex = nextcord.SlashOption(
                            name = 'regex',
                            description = strings.HYPE_REGEX_DESCRIPTION
                        ),
                        responses = nextcord.SlashOption(
                            name = 'responses',
                            description = strings.HYPE_RESPONSES_DESCRIPTION
                        )):
        await self.commonHype(interaction, regex, utils.strParamToArgs(responses))

    @commands.command(aliases = strings.HYPE_ALIASES, brief = "- " + strings.HYPE_BRIEF, description = strings.HYPE_DESCRIPTION)
    @predicates.isMessageAuthorAdmin()
    @predicates.isFeatureEnabledForServer('toggle_hype', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def hype(self, ctx: Context, regex, *responses):
        await self.commonHype(ctx, regex, responses)

    async def commonHype(self, context, regex, responses):
        hype_queries.createMatch(context.guild.id, regex, list(responses), False)
        await context.send(f"A new message match has been created with regex '{regex}'. All matching messages will reply with one of the following: {list(responses)}")

    @nextcord.slash_command(name = strings.REACT_NAME, description = strings.REACT_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_hype', False, True)
    @predicates.isMessageAuthorAdmin(True)
    async def reactSlash(self,
                        interaction: nextcord.Interaction,
                        regex = nextcord.SlashOption(
                            name = 'regex',
                            description = strings.REACT_REGEX_DESCRIPTION
                        ),
                        emojis = nextcord.SlashOption(
                            name = 'emojis',
                            description = strings.REACT_EMOJIS_DESCRIPTION
                        )):
        await self.commonReact(interaction, regex, utils.emojisParamToArgs(emojis))

    @commands.command(aliases = strings.REACT_ALIASES, brief = "- " + strings.REACT_BRIEF, description = strings.REACT_DESCRIPTION)
    @predicates.isMessageAuthorAdmin()
    @predicates.isFeatureEnabledForServer('toggle_hype', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def react(self, ctx: Context, regex, *emojis: EmojiInputType):
        await self.commonReact(ctx, regex, emojis)

    async def commonReact(self, context, regex, emojis):
        emojiList = []
        atLeastOneEmoji = False
        for emoji in emojis:
            if isinstance(emoji, nextcord.PartialEmoji):
                await context.send(f"The emoji could not be added as the bot does not have access to this emoji: '<:{emoji.name}:{emoji.id}>'")
            elif isinstance(emoji, nextcord.Emoji):
                emojiList.append(f'<:{emoji.name}:{emoji.id}>')
                atLeastOneEmoji = True
            else:
                emojiList.append(emoji)
                atLeastOneEmoji = True

        if atLeastOneEmoji:
            hype_queries.createMatch(context.guild.id, regex, list(emojiList), True)
            await context.send(f"A new message match has been created with regex '{regex}'. All matching messages will react with one of the following: {list(emojiList)}")

    @nextcord.slash_command(name = strings.UNMATCH_NAME, description = strings.UNMATCH_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_hype', False, True)
    @predicates.isMessageAuthorAdmin(True)
    async def unmatchSlash(self, interaction: nextcord.Interaction):
        await self.commonUnmatch(interaction, interaction.user)

    @commands.command(aliases = strings.UNMATCH_ALIASES, brief = "- " + strings.UNMATCH_BRIEF, description = strings.UNMATCH_DESCRIPTION)
    @predicates.isMessageAuthorAdmin()
    @predicates.isFeatureEnabledForServer('toggle_hype', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def unmatch(self, ctx: Context):
        await self.commonUnmatch(ctx, ctx.author)
            
    async def commonUnmatch(self, context, author):
            serverId = context.guild.id
            userMention = author.mention
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

                    if context.guild.icon != None:
                        thumbnailUrl = context.guild.icon.url
                    else:
                        thumbnailUrl = None 

                    # print out configured matches with corresponding selection number
                    pages = pagination.CustomButtonMenuPages(source = pagination.FieldPageSource(fields, thumbnailUrl, "GBot Hype Matches", nextcord.Color.blue(), False, 10))
                    await pagination.startPages(context, pages)

                    # ask for number selection until users respond with answer or 'cancel'
                    numberObtained = False
                    errorMsg = ''
                    while(not numberObtained):
                        userResponse: nextcord.Message = await utils.askUserQuestion(self.client, context, author, f'{errorMsg} What match would you like to remove for this server? Please respond with the corresponding number.', GBotPropertiesManager.USER_RESPONSE_TIMEOUT_SECONDS)
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
                    await context.send(f'Match {selection} deleted.')
                except asyncio.TimeoutError:
                    await context.send(f'Sorry {userMention}, you did not respond in time.')
                except UserCancelledCommand:
                    await context.send(f'{userMention}, match deletion has been cancelled.')
            else:
                await context.send(f'Sorry {userMention}, the server has no matches configured.')

def setup(client: commands.Bot):
    client.add_cog(Hype(client))