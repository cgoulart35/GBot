#region IMPORTS
import asyncio
import nextcord
from nextcord.ext import commands

from GBotDiscord.src import predicates
from GBotDiscord.src import presentation
from GBotDiscord.src import strings
from GBotDiscord.src import utils
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.exceptions import NotSubscribed
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

class Feature:
    def __init__(self, name, emoji, group, toggle, adminOnly = False):
        self.name = name
        self.emoji = emoji
        self.group = group
        self.toggle = toggle
        self.adminOnly = adminOnly

    @property
    def heading(self):
        return f'{self.emoji} {self.name}'

# the order help lists them in. Config has no toggle because it is how the toggles get changed.
FEATURES = [
    Feature('Music', '🎵', strings.MUSIC_GROUP_NAME, 'toggle_music'),
    Feature('Storms', '🌧️', strings.STORMS_GROUP_NAME, 'toggle_storms'),
    Feature('GCoin', '💰', strings.GCOIN_GROUP_NAME, 'toggle_gcoin'),
    Feature('GTrade', '🏪', strings.GTRADE_GROUP_NAME, 'toggle_gtrade'),
    Feature('Who Dis', '❓', strings.WHODIS_GROUP_NAME, 'toggle_who_dis'),
    Feature('Hype', '↩️', strings.HYPE_GROUP_NAME, 'toggle_hype', adminOnly = True),
    Feature('Config', '⚙️', strings.CONFIG_GROUP_NAME, None, adminOnly = True),
]

def featureForGroup(group):
    return next((feature for feature in FEATURES if feature.group == group), None)

def isFeatureOn(feature, guild):
    # a feature can only be off in a server; in a private message there is no toggle to consult
    return guild is None or feature.toggle is None or config_queries.getServerValue(guild.id, feature.toggle) != False

def areLegacyPrefixCommandsOn(guild):
    return guild is None or config_queries.getServerValue(guild.id, 'toggle_legacy_prefix_commands') != False

def commandPrefix(guild):
    return '.' if guild is None else config_queries.getServerValue(guild.id, 'prefix')

async def isSubscribed(guild, author):
    try:
        await predicates.ensureSubscribed(guild, author)
    except NotSubscribed:
        return False
    return True

def describeLeaves(group):
    return ' '.join(f'`{command.name}`' for command in group.commands)

def describeCommand(command, prefix, showPrefix):
    # /music play comes first because slash is what always works; a server can turn prefix off
    usage = command.brief[2:] if command.brief and command.brief.startswith('- ') else (command.brief or '')
    if not showPrefix:
        return usage
    names = '|'.join([command.name] + list(command.aliases))
    arguments = f' {command.signature}' if command.signature else ''
    parent = ''
    if command.parent is not None:
        parent = '[' + '|'.join([command.parent.name] + list(command.parent.aliases)) + '] '
    return f'{usage}\n`{prefix}{parent}[{names}]{arguments}`'

async def overviewEmbed(client, guild, author):
    if not await isSubscribed(guild, author):
        return presentation.warningEmbed(title = strings.HELP_TITLE, description = f'GBot is not active here yet. Subscribe to get started: {GBotPropertiesManager.PATREON_URL}')

    isAdmin = guild is None or await asyncio.to_thread(utils.isUserAdminOrOwner, author, guild)
    embed = presentation.brandEmbed(title = strings.HELP_TITLE, description = strings.HELP_OVERVIEW)
    turnedOff = []
    for feature in FEATURES:
        # admin features would only refuse anyone else, so they are not offered to them. In a
        # private message there is no server to be an admin of, so they are simply not relevant.
        if feature.adminOnly and (guild is None or not isAdmin):
            continue
        if not await asyncio.to_thread(isFeatureOn, feature, guild):
            turnedOff.append(feature.name)
            continue
        embed.add_field(name = feature.heading, value = describeLeaves(client.get_command(feature.group)), inline = False)
    if guild is not None and guild.id == GBotPropertiesManager.PATREON_GUILD_ID:
        embed.add_field(name = '⭐ Patreon', value = f'`/{strings.PATREON_NAME}` {strings.PATREON_BRIEF}', inline = False)
    if turnedOff:
        embed.add_field(name = 'Turned off here', value = f"{', '.join(turnedOff)}\nAn admin can turn these on with `/config toggle`.", inline = False)
    if not await asyncio.to_thread(areLegacyPrefixCommandsOn, guild):
        embed.add_field(name = 'Prefix commands', value = 'Turned off here, so use the slash commands. An admin can change this with `/config toggle`.', inline = False)
    return embed

def featureEmbed(client, feature, guild):
    group = client.get_command(feature.group)
    showPrefix = areLegacyPrefixCommandsOn(guild)
    prefix = commandPrefix(guild)
    if isFeatureOn(feature, guild):
        embed = presentation.brandEmbed(title = feature.heading, description = group.description, feature = feature.name)
    else:
        embed = presentation.warningEmbed(title = feature.heading, description = f'{feature.name} is turned off in this server. An admin can turn it on with `/config toggle`.\n\n{group.description}', feature = feature.name)
    for command in group.commands:
        embed.add_field(name = f'/{feature.group} {command.name}', value = describeCommand(command, prefix, showPrefix), inline = False)
    return embed

def commandEmbed(command, guild):
    prefix = commandPrefix(guild)
    showPrefix = areLegacyPrefixCommandsOn(guild)
    feature = featureForGroup(command.parent.name) if command.parent is not None else None
    slashName = f'/{command.parent.name} {command.name}' if command.parent is not None else f'/{command.name}'
    embed = presentation.brandEmbed(title = slashName, description = command.description or command.brief, feature = feature.name if feature else None)
    if showPrefix:
        embed.add_field(name = 'Prefix command', value = describeCommand(command, prefix, True).split('\n')[-1], inline = False)
    return embed

class GBotHelpCommand(commands.HelpCommand):
    """Keeps nextcord's handling of .help <anything> and ctx.send_help, and owns only what is shown."""

    async def _send(self, embed):
        await presentation.sendReply(self.context, embed = embed)

    async def send_bot_help(self, mapping):
        await self._send(await overviewEmbed(self.context.bot, self.context.guild, self.context.author))

    async def send_cog_help(self, cog):
        for command in cog.get_commands():
            feature = featureForGroup(command.name)
            if feature is not None:
                await self._send(await asyncio.to_thread(featureEmbed, self.context.bot, feature, self.context.guild))
                return
        await self.send_bot_help(None)

    async def send_group_help(self, group):
        await self._send(await asyncio.to_thread(featureEmbed, self.context.bot, featureForGroup(group.name), self.context.guild))

    async def send_command_help(self, command):
        await self._send(await asyncio.to_thread(commandEmbed, command, self.context.guild))

    async def send_error_message(self, error):
        await self._send(presentation.errorEmbed(description = f'{error} Try `/help` to see what is available.'))

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
        await self.commonHelpSlash(interaction, feature)

    async def commonHelpSlash(self, interaction, featureName):
        selected = next((feature for feature in FEATURES if feature.name == featureName), None)
        if selected is None:
            embed = await overviewEmbed(self.client, interaction.guild, interaction.user)
        else:
            embed = await asyncio.to_thread(featureEmbed, self.client, selected, interaction.guild)
        # what is listed depends on who asked, and it would only add noise for everybody else
        await presentation.sendReply(interaction, embed = embed, ephemeral = True)

def setup(client: commands.Bot):
    client.help_command = GBotHelpCommand()
    client.add_cog(Help(client))
