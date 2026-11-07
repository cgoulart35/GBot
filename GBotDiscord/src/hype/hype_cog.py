#region IMPORTS
import logging
import random
import re
import typing
import regex as regexLibrary
import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context

from GBotDiscord.src import presentation
from GBotDiscord.src import strings
from GBotDiscord.src import utils
from GBotDiscord.src import pagination
from GBotDiscord.src import predicates
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.hype import hype_queries
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.firebase import GBotFirebaseService
#endregion

MATCHES_PER_PAGE = 10

class Hype(commands.Cog):

    EmojiInputType = typing.Union[nextcord.Emoji, nextcord.PartialEmoji, str]

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()
        self.MATCH_TIMEOUT_SECONDS = 0.25
        self.MAX_SHOWN_REGEX = 150
        self.MAX_SHOWN_RESPONSES = 200

    def describeRegex(self, regex):
        # patterns are full of characters Discord treats as formatting, so they always sit in a code
        # span. A backtick would end that span early, so a lookalike stands in for it on screen.
        shown = regex[:self.MAX_SHOWN_REGEX] + ('…' if len(regex) > self.MAX_SHOWN_REGEX else '')
        return f"`{shown.replace('`', 'ˋ')}`"

    def describeResponse(self, response):
        # one "F*CKING" in a reply would otherwise turn everything up to the next * into italics,
        # including the next match's pattern. Custom emoji and links have to stay as they are.
        pieces = re.split(r'(<a?:\w+:\d+>)', response)
        return ''.join(piece if index % 2 else nextcord.utils.escape_markdown(piece, ignore_links = True) for index, piece in enumerate(pieces))

    def describeResponses(self, responses):
        # cut between responses where possible: cutting escaped text could split an escape or emoji
        parts = []
        room = self.MAX_SHOWN_RESPONSES
        for response in responses:
            piece = self.describeResponse(response)
            if len(piece) > room:
                parts.append(self.describeResponse(response[:room // 2]) + '…')
                break
            parts.append(piece)
            room -= len(piece) + 2
        return ', '.join(parts) or 'nothing'

    # Events
    @commands.Cog.listener()
    async def on_message(self, msg: nextcord.Message):
        # make sure message in a guild not from a bot
        if (msg.guild != None and not msg.author.bot and not msg.content.startswith(await GBotFirebaseService.run(utils.getServerPrefixOrDefault, msg))):
            serverId = msg.guild.id

            # these run on every message in every server, and only read, so they wait off the event loop
            # get all regex for this server and check if there is a match
            matches = await GBotFirebaseService.run(hype_queries.getAllServerMatches, serverId)
            # the commands are gated, but this listener isn't one of them. Read only once there are matches.
            if matches != None and await GBotFirebaseService.run(config_queries.getServerValue, serverId, 'toggle_hype') != False:
                for match in matches.values():
                    regex = match['regex']
                    # the database doesn't store an empty list, so the key is simply missing
                    responses = match.get('responses')
                    isReaction = match['isReaction']

                    # a match with no responses has nothing to reply with
                    if not responses:
                        continue

                    # a match saved before patterns were validated can still be invalid; skip it
                    # rather than failing on every message sent in this server
                    try:
                        isMatch = regexLibrary.match(regex, msg.content, timeout = self.MATCH_TIMEOUT_SECONDS)
                    except regexLibrary.error:
                        self.logger.error(f'GBot Hype skipped an invalid match regex in server {serverId}: {regex}')
                        continue
                    except TimeoutError:
                        # a badly written pattern can otherwise run for hours, and hold up every server
                        self.logger.error(f'GBot Hype stopped a match regex that took too long in server {serverId}: {regex}')
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
            regexLibrary.compile(regex)
            return True
        except regexLibrary.error as e:
            await presentation.sendError(context, f"The message match could not be created as '{regex}' is not a valid regular expression: {e}")
            return False

    async def commonHype(self, context, regex, responses):
        if not responses:
            await presentation.sendError(context, 'The message match could not be created as it has no responses to reply with.')
            return
        if not await self.validateMatchRegex(context, regex):
            return
        await GBotFirebaseService.run(hype_queries.createMatch, context.guild.id, regex, list(responses), False)
        await presentation.sendReply(context, content = f"↩️ A new message match has been created with regex {self.describeRegex(regex)}. All matching messages will reply with one of the following: {self.describeResponses(responses)}", ephemeral = True)

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
                await presentation.sendError(context, f"The emoji could not be added as the bot does not have access to this emoji: '<:{emoji.name}:{emoji.id}>'")
            elif isinstance(emoji, nextcord.Emoji):
                emojiList.append(f'<:{emoji.name}:{emoji.id}>')
                atLeastOneEmoji = True
            else:
                emojiList.append(emoji)
                atLeastOneEmoji = True

        if atLeastOneEmoji:
            if not await self.validateMatchRegex(context, regex):
                return
            await GBotFirebaseService.run(hype_queries.createMatch, context.guild.id, regex, list(emojiList), True)
            await presentation.sendReply(context, content = f"↩️ A new message match has been created with regex {self.describeRegex(regex)}. All matching messages will react with one of the following: {self.describeResponses(emojiList)}", ephemeral = True)

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
            
    def describeMatchChoice(self, matchValues):
        # the dropdown's row: the pattern, and what it does
        action = 'Reacts with' if matchValues['isReaction'] else 'Replies with'
        responses = ', '.join(matchValues.get('responses', [])) or 'nothing'
        return {'label': matchValues['regex'], 'description': f'{action} {responses}', 'emoji': '😀' if matchValues['isReaction'] else '💬'}

    def listMatches(self, matches):
        matchIds = list(matches or {})
        lines = []
        for number, matchId in enumerate(matchIds, start = 1):
            matchValues = matches[matchId]
            action = '😀 **Reacts:**' if matchValues['isReaction'] else '💬 **Replies:**'
            # cut short: one very long match failing to display would make every match in the
            # server impossible to remove. A full page of these still fits in an embed.
            lines.append(f"**{number}.** {self.describeRegex(matchValues['regex'])}\n{action} {self.describeResponses(matchValues.get('responses', []))}")
        return matchIds, lines, [self.describeMatchChoice(matches[matchId]) for matchId in matchIds]

    async def commonUnmatch(self, context, author):
        # private: it's a settings screen, and there's no question left to ask in the channel
        await presentation.deferIfSlash(context, ephemeral = True)
        serverId = context.guild.id
        matches = await GBotFirebaseService.run(hype_queries.getAllServerMatches, serverId)
        if not matches:
            await presentation.sendError(context, f'Sorry {author.mention}, the server has no matches configured.')
            return
        matchIds, lines, choices = self.listMatches(matches)

        async def delete(picker, interaction, index):
            await GBotFirebaseService.run(hype_queries.removeMatch, serverId, matchIds[index])
            fresh = await GBotFirebaseService.run(hype_queries.getAllServerMatches, serverId)
            ids, freshLines, freshChoices = self.listMatches(fresh)
            matchIds[:] = ids
            picker.replace(freshLines, freshChoices)
            await picker.refresh(interaction, f'🗑️ Match {index + 1} deleted.')

        thumbnailUrl = context.guild.icon.url if context.guild.icon != None else None
        source = pagination.DescriptionPageSource(lines, '↩️ GBot Hype Matches', presentation.BRAND_COLOR, thumbnailUrl, MATCHES_PER_PAGE, empty = 'No matches left. Add one with `/hype respond` or `/hype react`.')
        actions = [pagination.Action('Delete', '🗑️', nextcord.ButtonStyle.danger, delete, needsSelection = True, confirm = 'Delete for good')]
        picker = pagination.ListPicker(source, choices, actions, 'Choose a match to delete…')
        await pagination.startPages(context, picker, ephemeral = True)

def setup(client: commands.Bot):
    client.add_cog(Hype(client))