#region IMPORTS
import nextcord
from nextcord.ext import commands

from GBotDiscord.src.agent import agent_queries
from GBotDiscord.src.help import guides
from GBotDiscord.src import pagination
from GBotDiscord.src import predicates
from GBotDiscord.src import presentation
from GBotDiscord.src import strings
from GBotDiscord.src import utils
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.exceptions import NotSubscribed
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.firebase import GBotFirebaseService
#endregion

class Feature:
    def __init__(self, name, emoji, command, toggle, cog, open, adminOnly = False, inPrivateMessages = False):
        self.name = name
        self.emoji = emoji
        self.command = command
        self.toggle = toggle
        # the cog and how Help's button opens its card: open(cog, interaction, user)
        self.cog = cog
        self.open = open
        self.adminOnly = adminOnly
        self.inPrivateMessages = inPrivateMessages

    @property
    def heading(self):
        return f'{self.emoji} {self.name}'

# the order help lists them in, A to Z. Config has no toggle because it is how the toggles get changed.
FEATURES = [
    Feature('Agent', strings.FEATURE_EMOJIS['toggle_agent'], strings.AGENT_NAME, 'toggle_agent', 'Agent', lambda cog, interaction, user: cog.openCard(interaction, user), adminOnly = True),
    Feature('Config', '⚙️', strings.CONFIG_NAME, None, 'Config', lambda cog, interaction, user: cog.openCard(interaction, user), adminOnly = True),
    Feature('GCoin', strings.FEATURE_EMOJIS['toggle_gcoin'], strings.GCOIN_NAME, 'toggle_gcoin', 'GCoin', lambda cog, interaction, user: cog.commonWallet(interaction, user, None), inPrivateMessages = True),
    Feature('GTrade', strings.FEATURE_EMOJIS['toggle_gtrade'], strings.GTRADE_NAME, 'toggle_gtrade', 'GTrade', lambda cog, interaction, user: cog.openItems(interaction, user), inPrivateMessages = True),
    Feature('Hype', strings.FEATURE_EMOJIS['toggle_hype'], strings.HYPE_NAME, 'toggle_hype', 'Hype', lambda cog, interaction, user: cog.openCard(interaction, user), adminOnly = True),
    Feature('Music', strings.FEATURE_EMOJIS['toggle_music'], strings.MUSIC_NAME, 'toggle_music', 'Music', lambda cog, interaction, user: cog.commonMusic(interaction, user, [])),
    Feature('Storms', strings.FEATURE_EMOJIS['toggle_storms'], strings.STORMS_NAME, 'toggle_storms', 'Storms', lambda cog, interaction, user: cog.commonStatus(interaction)),
    Feature('Who Dis', strings.FEATURE_EMOJIS['toggle_who_dis'], strings.WHODIS_NAME, 'toggle_who_dis', 'WhoDis', lambda cog, interaction, user: cog.openCard(interaction, user), inPrivateMessages = True),
]
BUTTONS_PER_ROW = 5

def featureNamed(name):
    return next((feature for feature in FEATURES if feature.name == name or feature.command == name), None)

def isFeatureOn(feature, guild):
    # a feature can only be off in a server; in a private message there is no toggle to consult
    return guild is None or feature.toggle is None or config_queries.getServerValue(guild.id, feature.toggle) != False

def areLegacyPrefixCommandsOn(guild):
    return guild is None or config_queries.getServerValue(guild.id, 'toggle_legacy_prefix_commands') != False

def commandPrefix(guild):
    return '.' if guild is None else config_queries.getServerValue(guild.id, 'prefix')

def membersCanUseAgentMemory(feature, guild):
    return isFeatureOn(feature, guild) and agent_queries.getServerConfig(guild.id).get('memoryAccess') == 'everyone'

async def subscriptionRefusal(guild, author):
    # why GBot can't be used here, or None when it can
    try:
        await predicates.ensureSubscribed(guild, author)
    except NotSubscribed as refusal:
        return refusal
    return None

def describeUsage(command, prefix, showPrefix):
    # /music [search] comes first because slash is what always works; a server can turn prefix off
    usage = command.brief[2:] if command.brief and command.brief.startswith('- ') else (command.brief or '')
    if not showPrefix:
        return usage
    names = '|'.join([command.name] + list(command.aliases))
    arguments = f' {command.signature}' if command.signature else ''
    return f'{usage}\n`{prefix}[{names}]{arguments}`'

async def availableFeatures(guild, author):
    # (what this person can open here, what is turned off here). Admin features would only refuse
    # anyone else, so they aren't offered, except the agent's memories where members may use them.
    isAdmin = guild is not None and await GBotFirebaseService.run(utils.isUserAdminOrOwner, author, guild)
    available, turnedOff = [], []
    for feature in FEATURES:
        if guild is None and not feature.inPrivateMessages:
            continue
        if feature.adminOnly and not isAdmin:
            if feature.name == 'Agent' and await GBotFirebaseService.run(membersCanUseAgentMemory, feature, guild):
                available.append(feature)
            continue
        if not await GBotFirebaseService.run(isFeatureOn, feature, guild):
            turnedOff.append(feature.name)
            continue
        available.append(feature)
    return available, turnedOff

async def overviewEmbed(client, guild, author, available, turnedOff):
    embed = presentation.brandEmbed(title = strings.HELP_TITLE, description = strings.HELP_OVERVIEW)
    for feature in available:
        command = client.get_command(feature.command)
        brief = command.brief[2:] if command is not None and command.brief else ''
        embed.add_field(name = feature.heading, value = f'`/{feature.command}` {brief}', inline = False)
    if guild is not None and guild.id == GBotPropertiesManager.PATREON_GUILD_ID:
        embed.add_field(name = '⭐ Patreon', value = f'`/{strings.PATREON_NAME}` {strings.PATREON_BRIEF}', inline = False)
    if turnedOff:
        embed.add_field(name = 'Turned off here', value = f"{', '.join(turnedOff)}\nAn admin can turn these on in `/config`.", inline = False)
    if not await GBotFirebaseService.run(areLegacyPrefixCommandsOn, guild):
        embed.add_field(name = 'Prefix commands', value = 'Turned off here, so use the slash commands. An admin can change this in `/config`.', inline = False)
    return embed

def featureEmbed(client, feature, guild):
    command = client.get_command(feature.command)
    if isFeatureOn(feature, guild):
        embed = presentation.brandEmbed(title = feature.heading, description = command.description, feature = feature.name)
    else:
        embed = presentation.warningEmbed(title = feature.heading, description = f'{feature.name} is turned off in this server. An admin can turn it on in `/config`.\n\n{command.description}', feature = feature.name)
    # how it works first, then the command that does it
    embed.add_field(name = '📖 How it works', value = guides.guideFor(feature.name), inline = False)
    slash = next((root for root in client.get_all_application_commands() if root.name == feature.command and root.type == nextcord.ApplicationCommandType.chat_input), None)
    options = ' '.join(f'<{option}>' if details.required else f'[{option}]' for option, details in (slash.options.items() if slash else ()))
    embed.add_field(name = f'/{feature.command} {options}'.rstrip(), value = describeUsage(command, commandPrefix(guild), areLegacyPrefixCommandsOn(guild)), inline = False)
    return embed

class HelpCard(pagination.OwnedView):
    # /help: the front door. A button opens each feature's card, and the dropdown shows how one works.
    def __init__(self, client, guild, available, turnedOff):
        super().__init__()
        self.client = client
        self.guild = guild
        self.available = available
        self.turnedOff = turnedOff
        self.page = None

    async def render(self, author):
        self.clear_items()
        if self.page is None:
            embed = await overviewEmbed(self.client, self.guild, author, self.available, self.turnedOff)
            for index, feature in enumerate(self.available):
                self.button(feature.emoji, self.opener(feature), label = feature.name, row = index // BUTTONS_PER_ROW)
            # the ranking is GCoin's, but worth a button of its own on the front door
            if featureNamed('GCoin') in self.available:
                self.button('🏆', self.openRanking, label = 'Ranking', row = len(self.available) // BUTTONS_PER_ROW)
            self.closeButton(row = 3)
        else:
            embed = await GBotFirebaseService.run(featureEmbed, self.client, self.page, self.guild)
            self.button('◀️', self.back, label = 'Back', row = 0)
            if self.page in self.available:
                self.button(self.page.emoji, self.opener(self.page), label = f'Open {self.page.name}', style = nextcord.ButtonStyle.primary, row = 0)
            self.closeButton(row = 0)
        shown = self.available + [feature for feature in FEATURES if feature.name in self.turnedOff]
        if shown:
            select = nextcord.ui.Select(custom_id = pagination.newId('pick'), placeholder = '📖 How does a feature work?', row = 2, options = [
                nextcord.SelectOption(label = feature.name, emoji = feature.emoji, value = feature.name, default = feature is self.page) for feature in shown])
            select.callback = self.pick
            self.add_item(select)
        return embed

    async def show(self, interaction):
        await interaction.response.edit_message(embed = await self.render(interaction.user), view = self)

    async def pick(self, interaction):
        self.page = featureNamed(interaction.data['values'][0])
        await self.show(interaction)

    async def back(self, interaction):
        self.page = None
        await self.show(interaction)

    async def openRanking(self, interaction):
        await interaction.response.defer(ephemeral = True)
        await predicates.recheck(interaction, feature = 'toggle_gcoin', privateMessagesAllowed = True)
        await self.client.get_cog('GCoin').openRanking(interaction)

    def opener(self, feature):
        async def open(interaction):
            # its card opens as if its command had been typed, checked as that command is
            await interaction.response.defer(ephemeral = True)
            await predicates.recheck(interaction, feature = feature.toggle, admin = feature.adminOnly and feature.name != 'Agent', privateMessagesAllowed = feature.inPrivateMessages)
            await feature.open(self.client.get_cog(feature.cog), interaction, interaction.user)
        return open

async def openHelp(client, context, author, featureName = None):
    refusal = await subscriptionRefusal(context.guild, author)
    if refusal is not None:
        # the same refusal every other command gives
        await presentation.sendCommandError(context, author, None, refusal)
        return
    available, turnedOff = await availableFeatures(context.guild, author)
    card = HelpCard(client, context.guild, available, turnedOff)
    card.page = featureNamed(featureName) if featureName else None
    # what is listed depends on who asked, and it would only add noise for everybody else
    await card.send(context, True, embed = await card.render(author), view = card)

class GBotHelpCommand(commands.HelpCommand):
    """Keeps nextcord's handling of .help <anything> and ctx.send_help, and owns only what is shown."""

    async def send_bot_help(self, mapping):
        await openHelp(self.context.bot, self.context, self.context.author)

    async def send_cog_help(self, cog):
        feature = next((feature for feature in FEATURES if feature.cog == cog.qualified_name), None)
        await openHelp(self.context.bot, self.context, self.context.author, feature.name if feature else None)

    async def send_command_help(self, command):
        feature = featureNamed(command.name)
        await openHelp(self.context.bot, self.context, self.context.author, feature.name if feature else None)

    async def send_error_message(self, error):
        await presentation.sendReply(self.context, embed = presentation.errorEmbed(description = f'{error} Try `/help` to see what is available.'))

class Help(commands.Cog):

    def __init__(self, client: nextcord.Client):
        self.client = client

    @nextcord.slash_command(name = strings.HELP_NAME, description = strings.HELP_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    async def helpSlash(self,
                        interaction: nextcord.Interaction,
                        feature = nextcord.SlashOption(
                            name = 'feature',
                            required = False,
                            choices = [feature.name for feature in FEATURES],
                            description = strings.HELP_FEATURE_DESCRIPTION
                        )):
        await openHelp(self.client, interaction, interaction.user, feature)

def setup(client: commands.Bot):
    client.help_command = GBotHelpCommand()
    client.add_cog(Help(client))
