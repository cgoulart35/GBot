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

                    # a match with no responses has nothing to reply with
                    if not responses:
                        continue

                    # a match saved before patterns were validated can still be invalid; skip it
                    # rather than failing on every message sent in this server
                    try:
                        isMatch = re.match(regex, msg.content)
                    except re.error:
                        self.logger.error(f'GBot Hype skipped an invalid match regex in server {serverId}: {regex}')
                        continue

                    if isMatch:
                        # select a random response in the list of options
                        response = random.choice(responses)

                        if isReaction:
                            try:
                                await msg.add_reaction(response)
                            except Exception:
                                await msg.reply("GBot ran into an issue trying to react to this message. Please remove the broken match.")
                        else:
                            await msg.reply(response)
                        self.logger.info(f'GBot Hype responded to a match in server {serverId} sent from {msg.author.name} ({msg.author.id}).')

    # Commands
    # The two group roots. Discord never invokes a slash command that has subcommands, so the slash
    # root's body is unreachable in production — nextcord just needs a callback to hang the group on.
    @nextcord.slash_command(name = strings.HYPE_GROUP_NAME, description = strings.HYPE_GROUP_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    async def hypeSlashGroup(self, interaction: nextcord.Interaction):
        pass

    @commands.group(name = strings.HYPE_GROUP_NAME, aliases = strings.HYPE_GROUP_ALIASES, brief = "- " + strings.HYPE_GROUP_BRIEF, description = strings.HYPE_GROUP_DESCRIPTION, invoke_without_command = True)
    # invoke_without_command means these run ONLY for a bare ".hype" — when a subcommand
    # matches, nextcord dispatches straight to it and the root's checks never fire. So this
    # is the group's own gate, not a second one on every leaf: it mirrors exactly the checks
    # every leaf here shares, or a bare root would be an ungated way into a gated cog.
    @predicates.isMessageAuthorAdmin()
    @predicates.isFeatureEnabledForServer('toggle_hype', False)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def hypeGroup(self, ctx: Context):
        # a bare ".hype" names no subcommand; list what lives under the group instead of doing nothing
        await ctx.send_help(ctx.command)

    @hypeSlashGroup.subcommand(name = strings.HYPE_RESPOND_NAME, description = strings.HYPE_RESPOND_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_hype', False, True)
    @predicates.isMessageAuthorAdmin(True)
    async def respondSlash(self,
                        interaction: nextcord.Interaction,
                        regex = nextcord.SlashOption(
                            name = 'regex',
                            description = strings.HYPE_RESPOND_REGEX_DESCRIPTION
                        ),
                        responses = nextcord.SlashOption(
                            name = 'responses',
                            description = strings.HYPE_RESPOND_RESPONSES_DESCRIPTION
                        )):
        await self.commonHype(interaction, regex, utils.strParamToArgs(responses))

    @hypeGroup.command(name = strings.HYPE_RESPOND_NAME, aliases = strings.HYPE_RESPOND_ALIASES, brief = "- " + strings.HYPE_RESPOND_BRIEF, description = strings.HYPE_RESPOND_DESCRIPTION)
    @predicates.isMessageAuthorAdmin()
    @predicates.isFeatureEnabledForServer('toggle_hype', False)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def respond(self, ctx: Context, regex, *responses):
        await self.commonHype(ctx, regex, responses)

    async def validateMatchRegex(self, context, regex):
        # compile before saving; an invalid pattern stored here would otherwise raise on every
        # message sent in the server
        try:
            re.compile(regex)
            return True
        except re.error as e:
            await context.send(f"The message match could not be created as '{regex}' is not a valid regular expression: {e}")
            return False

    async def commonHype(self, context, regex, responses):
        if not await self.validateMatchRegex(context, regex):
            return
        hype_queries.createMatch(context.guild.id, regex, list(responses), False)
        await context.send(f"A new message match has been created with regex '{regex}'. All matching messages will reply with one of the following: {list(responses)}")

    @hypeSlashGroup.subcommand(name = strings.HYPE_REACT_NAME, description = strings.HYPE_REACT_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_hype', False, True)
    @predicates.isMessageAuthorAdmin(True)
    async def reactSlash(self,
                        interaction: nextcord.Interaction,
                        regex = nextcord.SlashOption(
                            name = 'regex',
                            description = strings.HYPE_REACT_REGEX_DESCRIPTION
                        ),
                        emojis = nextcord.SlashOption(
                            name = 'emojis',
                            description = strings.HYPE_REACT_EMOJIS_DESCRIPTION
                        )):
        await self.commonReact(interaction, regex, utils.emojisParamToArgs(emojis))

    @hypeGroup.command(name = strings.HYPE_REACT_NAME, aliases = strings.HYPE_REACT_ALIASES, brief = "- " + strings.HYPE_REACT_BRIEF, description = strings.HYPE_REACT_DESCRIPTION)
    @predicates.isMessageAuthorAdmin()
    @predicates.isFeatureEnabledForServer('toggle_hype', False)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
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
            if not await self.validateMatchRegex(context, regex):
                return
            hype_queries.createMatch(context.guild.id, regex, list(emojiList), True)
            await context.send(f"A new message match has been created with regex '{regex}'. All matching messages will react with one of the following: {list(emojiList)}")

    @hypeSlashGroup.subcommand(name = strings.HYPE_REMOVE_NAME, description = strings.HYPE_REMOVE_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_hype', False, True)
    @predicates.isMessageAuthorAdmin(True)
    async def removeSlash(self, interaction: nextcord.Interaction):
        await self.commonUnmatch(interaction, interaction.user)

    @hypeGroup.command(name = strings.HYPE_REMOVE_NAME, aliases = strings.HYPE_REMOVE_ALIASES, brief = "- " + strings.HYPE_REMOVE_BRIEF, description = strings.HYPE_REMOVE_DESCRIPTION)
    @predicates.isMessageAuthorAdmin()
    @predicates.isFeatureEnabledForServer('toggle_hype', False)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def remove(self, ctx: Context):
        await self.commonUnmatch(ctx, ctx.author)
            
    async def commonUnmatch(self, context, author):
            if isinstance(context, nextcord.Interaction):
                await context.response.defer()
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
                        userResponse: nextcord.Message = await utils.askUserQuestion(self.client, context, author, f"{errorMsg} What match would you like to remove for this server? Please respond with the corresponding number, or 'cancel'.", GBotPropertiesManager.USER_RESPONSE_TIMEOUT_SECONDS)
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