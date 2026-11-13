#region IMPORTS
import logging
import random
import re
import regex as regexLibrary
import emoji
import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context

from GBotDiscord.src import access
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
MAX_PATTERN_CHARACTERS = 300
MAX_RESPONSES_CHARACTERS = 2000
CUSTOM_EMOJI = re.compile(r'<a?:\w+:(\d+)>')

class Hype(commands.Cog):

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()
        self.MATCH_TIMEOUT_SECONDS = 0.25
        self.MAX_SHOWN_REGEX = 150
        self.MAX_SHOWN_RESPONSES = 200
        # (server, pattern, emoji) of each reaction that failed and was said so, so it's said once
        # rather than under every message it matches, until the bot restarts. By emoji, so a match
        # edited to another broken one is said again.
        self.toldBroken = set()

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
            if matches != None and await GBotFirebaseService.run(config_queries.getServerValue, serverId, 'toggle_hype') != False \
                    and await GBotFirebaseService.run(access.isActive, serverId):
                for match in matches.values():
                    regex = match['regex']
                    # the database doesn't store an empty list, so the key is simply missing
                    responses = match.get('responses')
                    isReaction = match['isReaction']

                    # a match with no responses has nothing to reply with
                    if not responses:
                        continue

                    if self.isMatch(serverId, regex, msg.content):
                        # select a random response in the list of options
                        response = random.choice(responses)

                        if isReaction:
                            try:
                                await msg.add_reaction(response)
                            except Exception:
                                if (serverId, regex, response) not in self.toldBroken:
                                    self.toldBroken.add((serverId, regex, response))
                                    await msg.reply("GBot ran into an issue trying to react to this message. Please remove the broken match.")
                        else:
                            await msg.reply(response)
                        self.logger.info(f'GBot Hype responded to a match in server {serverId} sent from {msg.author.name} ({msg.author.id}).')

    def isMatch(self, serverId, regex, content):
        # a match saved before patterns were validated can still be invalid; it's skipped rather than
        # failing on every message sent in this server
        try:
            return regexLibrary.match(regex, content, timeout = self.MATCH_TIMEOUT_SECONDS) is not None
        except regexLibrary.error:
            self.logger.error(f'GBot Hype skipped an invalid match regex in server {serverId}: {regex}')
        except TimeoutError:
            # a badly written pattern can otherwise run for hours, and hold up every server
            self.logger.error(f'GBot Hype stopped a match regex that took too long in server {serverId}: {regex}')
        return False

    def describeTest(self, serverId, matches, content):
        # 🧪 Test: what a message would set off, without trying it in a live channel
        fired = []
        for number, matchValues in enumerate((matches or {}).values(), start = 1):
            if matchValues.get('responses') and self.isMatch(serverId, matchValues['regex'], content):
                verb = '😀 reacts with one of' if matchValues['isReaction'] else '💬 replies with one of'
                fired.append(f"**{number}.** {self.describeRegex(matchValues['regex'])} {verb}: {self.describeResponses(matchValues['responses'])}")
        if not fired:
            return '🧪 That message wouldn\'t match anything.'
        return '\n'.join(['🧪 That message would match:'] + fired)[:1024]

    # Commands
    # One command, like /patreon: everything about matches happens on its card
    @nextcord.slash_command(name = strings.HYPE_NAME, description = strings.HYPE_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_hype', False, True)
    @predicates.isMessageAuthorAdmin(True)
    async def hypeSlash(self, interaction: nextcord.Interaction):
        await self.commonHype(interaction, interaction.user)

    @commands.command(name = strings.HYPE_NAME, aliases = strings.HYPE_ALIASES, brief = "- " + strings.HYPE_BRIEF, description = strings.HYPE_DESCRIPTION)
    @predicates.isMessageAuthorAdmin()
    @predicates.isFeatureEnabledForServer('toggle_hype', False)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def hype(self, ctx: Context):
        await self.commonHype(ctx, ctx.author)

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

    def readResponses(self, text, isReaction, guild):
        # replies are one per line. Emoji can be on lines or separated by spaces, as none contain one.
        pieces = text.split() if isReaction else [line.strip() for line in text.split('\n')]
        pieces = [piece for piece in pieces if piece]
        if not pieces:
            return None, f"Please give at least one {'emoji' if isReaction else 'reply'}."
        if isReaction:
            for piece in pieces:
                custom = CUSTOM_EMOJI.fullmatch(piece)
                usable = self.client.get_emoji(int(custom.group(1))) is not None if custom else emoji.is_emoji(piece)
                if not usable:
                    return None, f"GBot can't react with {piece}. Use normal emoji, or custom emoji from a server GBot is in."
        return pieces, None

    def patternProblem(self, regex):
        # compiled before saving: an invalid pattern stored here would otherwise fail on every message
        try:
            regexLibrary.compile(regex)
            return None
        except regexLibrary.error as e:
            return f"{self.describeRegex(regex)} isn't a valid regular expression: {e}"

    async def commonHype(self, context, author):
        # private: it's a settings screen, and nothing is asked in the channel
        await pagination.openPrivately(context, '↩️', 'Hype matches', self.openCard, feature = 'toggle_hype', admin = True)

    async def openCard(self, context, author):
        await presentation.deferIfSlash(context, ephemeral = True)
        serverId = context.guild.id
        matches = await GBotFirebaseService.run(hype_queries.getAllServerMatches, serverId)
        matchIds, lines, choices = self.listMatches(matches)
        current = {'matches': matches or {}}

        async def reload(picker, interaction, notice):
            fresh = await GBotFirebaseService.run(hype_queries.getAllServerMatches, serverId)
            current['matches'] = fresh or {}
            ids, freshLines, freshChoices = self.listMatches(fresh)
            matchIds[:] = ids
            picker.replace(freshLines, freshChoices)
            await picker.redraw(interaction, notice)

        async def stillAdmin(interaction):
            # decided when they click, as their role, Hype or the subscription may have changed since
            try:
                await predicates.recheck(interaction, feature = 'toggle_hype', admin = True)
                return True
            except commands.CheckFailure as e:
                await picker.redraw(interaction, f'❌ {presentation.describeCommandError(e, author.mention)}')
                return False

        def formFor(title, isReaction, regex, responses, save):
            async def submitted(modalInteraction, pattern, text):
                # acknowledged first, as Discord allows 3 seconds and this waits on the database
                await modalInteraction.response.defer()
                pattern = pattern.strip()
                problem = self.patternProblem(pattern)
                cleaned = None
                if problem is None:
                    cleaned, problem = self.readResponses(text, isReaction, context.guild)
                if problem:
                    await picker.redraw(modalInteraction, f'❌ {problem}')
                    return
                if not await stillAdmin(modalInteraction):
                    return
                await save(modalInteraction, pattern, cleaned)
            return HypeModal(title, isReaction, regex, '\n'.join(responses), submitted)

        def adder(isReaction):
            async def add(picker, interaction, index):
                async def save(modalInteraction, pattern, cleaned):
                    await GBotFirebaseService.run(hype_queries.createMatch, serverId, pattern, cleaned, isReaction)
                    await reload(picker, modalInteraction, f"✅ Added. Messages matching {self.describeRegex(pattern)} now get {'a reaction' if isReaction else 'a reply'}.")
                await interaction.response.send_modal(formFor('Add a reaction' if isReaction else 'Add a reply', isReaction, None, [], save))
            return add

        async def edit(picker, interaction, index):
            matchId = matchIds[index]
            match = current['matches'].get(matchId) or {}
            async def save(modalInteraction, pattern, cleaned):
                # False for one deleted since this list was drawn, from another card or by the agent
                updated = await GBotFirebaseService.run(hype_queries.updateMatch, serverId, matchId, pattern, cleaned)
                await reload(picker, modalInteraction, f'✏️ Match {index + 1} updated.' if updated else '❌ That match was deleted, so nothing was changed.')
            await interaction.response.send_modal(formFor(f'Edit match {index + 1}', match.get('isReaction') is True, match.get('regex'), match.get('responses') or [], save))

        async def delete(picker, interaction, index):
            await interaction.response.defer()
            if not await stillAdmin(interaction):
                return
            await GBotFirebaseService.run(hype_queries.removeMatch, serverId, matchIds[index])
            await reload(picker, interaction, f'🗑️ Match {index + 1} deleted.')

        async def test(picker, interaction, index):
            async def submitted(modalInteraction, values):
                await modalInteraction.response.defer()
                if not await stillAdmin(modalInteraction):
                    return
                fresh = await GBotFirebaseService.run(hype_queries.getAllServerMatches, serverId)
                await picker.redraw(modalInteraction, self.describeTest(serverId, fresh, values[0]))
            await interaction.response.send_modal(pagination.Form('Test a message', [pagination.Field('A message someone might send', placeholder = "LET'S GO team", long = True, maxLength = 2000)], submitted))

        thumbnailUrl = context.guild.icon.url if context.guild.icon != None else None
        source = pagination.DescriptionPageSource(lines, '↩️ GBot Hype Matches', presentation.BRAND_COLOR, thumbnailUrl, MATCHES_PER_PAGE, empty = 'No matches yet. Add one with 💬 **Add reply** or 😀 **Add reaction**.')
        actions = [
            pagination.Action('Add reply', '💬', nextcord.ButtonStyle.success, adder(False)),
            pagination.Action('Add reaction', '😀', nextcord.ButtonStyle.success, adder(True)),
            pagination.Action('Edit', '✏️', nextcord.ButtonStyle.primary, edit, needsSelection = True),
            pagination.Action('Delete', '🗑️', nextcord.ButtonStyle.danger, delete, needsSelection = True, confirm = 'Delete for good'),
            pagination.Action('Test', '🧪', nextcord.ButtonStyle.secondary, test, row = 3)
        ]
        picker = pagination.ListPicker(source, choices, actions, 'Choose a match to edit or delete…')
        await pagination.startPages(context, picker, ephemeral = True)

class HypeModal(nextcord.ui.Modal):
    # the pattern and what it does, typed into a form rather than into the channel
    def __init__(self, title, isReaction, regex, responses, onSubmit):
        super().__init__(title = title, timeout = GBotPropertiesManager.USER_RESPONSE_TIMEOUT_SECONDS)
        self.onSubmit = onSubmit
        self.pattern = nextcord.ui.TextInput(label = 'Pattern (a regular expression)', max_length = MAX_PATTERN_CHARACTERS, default_value = regex, placeholder = "For example: (?i)let'?s go")
        self.responses = nextcord.ui.TextInput(label = 'Emoji to react with' if isReaction else 'Replies, one per line', style = nextcord.TextInputStyle.paragraph, max_length = MAX_RESPONSES_CHARACTERS, default_value = responses or None, placeholder = '🎉 🔥 👍' if isReaction else "Let's goooo!\nHype!")
        self.add_item(self.pattern)
        self.add_item(self.responses)

    async def callback(self, interaction: nextcord.Interaction):
        await self.onSubmit(interaction, self.pattern.value, self.responses.value)

def setup(client: commands.Bot):
    client.add_cog(Hype(client))