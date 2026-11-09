#region IMPORTS
import nextcord

from GBotDiscord.src import strings
#endregion

# What GBot asks Discord for, and whether a server's setup lets each feature work. The invite link
# asks for exactly PERMISSIONS, and /config's card lists what setupProblems finds, with the fix.

# Every intent GBot uses, so it isn't sent events it ignores. The three privileged ones are all
# used: message content (prefix commands, Hype, the agent, Who Dis relaying DMs), members (Who Dis
# pairing, the ranking, name lookups) and presences (Who Dis pairs only people who are online, and
# Follow Spotify reads what someone is playing). Emojis keep guild.emojis filled for reactions.
def gatewayIntents():
    return nextcord.Intents(guilds = True, members = True, presences = True, message_content = True,
                            guild_messages = True, dm_messages = True, voice_states = True,
                            emojis = True, guild_reactions = True, dm_reactions = True)

# Everything any feature needs. Not Administrator, and nothing that manages the server itself.
PERMISSIONS = nextcord.Permissions(
    view_channel = True, send_messages = True, send_messages_in_threads = True, embed_links = True,
    attach_files = True, read_message_history = True, add_reactions = True, use_external_emojis = True,
    connect = True, speak = True,
    # Storms and Who Dis tidy up the messages a game leaves, members' ones included
    manage_messages = True,
    # the Who Dis role, which also has to sit below GBot's own role
    manage_roles = True,
    # role pings from the agent, only when its mentions setting allows them
    mention_everyone = True)

def inviteUrl(clientId):
    return nextcord.utils.oauth_url(clientId, permissions = PERMISSIONS, scopes = ('bot', 'applications.commands'))

# The names a person sees in Server Settings
PERMISSION_NAMES = {
    'view_channel': 'View Channels',
    'send_messages': 'Send Messages',
    'send_messages_in_threads': 'Send Messages in Threads',
    'embed_links': 'Embed Links',
    'attach_files': 'Attach Files',
    'read_message_history': 'Read Message History',
    'add_reactions': 'Add Reactions',
    'use_external_emojis': 'Use External Emojis',
    'connect': 'Connect',
    'speak': 'Speak',
    'manage_messages': 'Manage Messages',
    'manage_roles': 'Manage Roles'
}

# what every feature relies on, everywhere GBot posts
BASICS = ('view_channel', 'send_messages', 'send_messages_in_threads', 'embed_links', 'attach_files', 'read_message_history')
# extras by feature, checked server-wide: these features post wherever they're used
FEATURE_PERMISSIONS = {
    'toggle_music': ('connect', 'speak'),
    'toggle_hype': ('add_reactions', 'use_external_emojis'),
    'toggle_agent': ('add_reactions',),
    'toggle_who_dis': ('manage_messages', 'manage_roles')
}
STORMS_CHANNEL = BASICS + ('manage_messages',)
ADMIN_CHANNEL = ('view_channel', 'send_messages', 'embed_links')

def missing(permissions, needed):
    return [PERMISSION_NAMES[name] for name in needed if not getattr(permissions, name)]

def listed(names):
    return ', '.join(f'**{name}**' for name in names)

def roleProblem(guild: nextcord.Guild, role: nextcord.Role):
    # Discord only lets a bot give out roles below its own highest one, and none that an integration
    # manages. None when GBot can give this role out.
    me = guild.me
    if role.is_default() or role.managed:
        return f"{role.mention} can't be given out by anyone, so pick another role."
    if not me.guild_permissions.manage_roles:
        return f'GBot needs the **Manage Roles** permission to give out {role.mention}.'
    if role.position >= me.top_role.position:
        return f"GBot can't give out {role.mention}, as it's above GBot's own role. Move **{me.top_role.name}** above it in Server Settings → Roles."
    return None

def channelProblem(guild: nextcord.Guild, channelId, label, needed):
    channel = guild.get_channel(int(channelId))
    if channel is None:
        return f'The {label} channel was deleted. Pick a new one below.'
    gaps = missing(channel.permissions_for(guild.me), needed)
    if gaps:
        return f'GBot is missing {listed(gaps)} in {channel.mention}.'
    return None

def setupProblems(guild: nextcord.Guild, serverConfig):
    # One line per problem stopping a turned-on feature from working, each saying how to fix it
    problems = []
    serverWide = guild.me.guild_permissions
    gaps = missing(serverWide, BASICS)
    if gaps:
        problems.append(f'GBot is missing {listed(gaps)} server-wide.')
    for toggle, needed in FEATURE_PERMISSIONS.items():
        gaps = missing(serverWide, needed)
        if serverConfig.get(toggle) == True and gaps:
            problems.append(f'{strings.FEATURE_EMOJIS[toggle]} {strings.FEATURE_NAMES[toggle]} needs {listed(gaps)}.')
    if serverConfig.get('toggle_storms') == True:
        if serverConfig.get('channel_storms') is None:
            problems.append('Storms needs a channel. Pick one below.')
        else:
            problems.append(channelProblem(guild, serverConfig['channel_storms'], 'Storms', STORMS_CHANNEL))
    if serverConfig.get('channel_admin') is not None:
        problems.append(channelProblem(guild, serverConfig['channel_admin'], 'admin', ADMIN_CHANNEL))
    if serverConfig.get('toggle_who_dis') == True:
        role = guild.get_role(int(serverConfig['role_who_dis'])) if serverConfig.get('role_who_dis') is not None else None
        if role is None:
            problems.append('Who Dis needs a role. Pick one in 👥 Roles.')
        elif serverWide.manage_roles:
            # a missing Manage Roles is already listed above
            problems.append(roleProblem(guild, role))
    return [problem for problem in problems if problem is not None]

