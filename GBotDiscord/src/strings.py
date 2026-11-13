# Command metadata, one block per cog.
#
# Each feature is one command (8.2): with no fields it opens the feature's card, where its buttons
# do what the old subcommands did, and optional fields give a fast path (/music <search>,
# /storms 42). So GBot claims ten global names, and the right-click menus a few more.
#
# Naming is uniform: <COG>_NAME, _BRIEF, _DESCRIPTION and _ALIASES for the command,
# <COG>_<OPTION>_DESCRIPTION for a slash option, and <COG>_<MENU>_NAME for a right-click menu.

# what /help, /config and the welcome message all show next to a feature. A to Z, with the prefix
# setting last since it isn't a feature of its own. Every list of features follows this order.
FEATURE_EMOJIS = {
    'toggle_agent': '🤖',
    'toggle_gcoin': '💰',
    'toggle_gtrade': '🏪',
    'toggle_hype': '↩️',
    'toggle_music': '🎵',
    'toggle_reminders': '🔔',
    'toggle_storms': '🌧️',
    'toggle_who_dis': '❓',
    'toggle_legacy_prefix_commands': '⌨️'
}

# the name a person reads for each server toggle
FEATURE_NAMES = {
    # DISCONTINUED 'toggle_halo': 'Halo',
    'toggle_agent': 'Agent',
    'toggle_gcoin': 'GCoin',
    'toggle_gtrade': 'GTrade',
    'toggle_hype': 'Hype',
    'toggle_music': 'Music',
    'toggle_reminders': 'Reminders',
    'toggle_storms': 'Storms',
    'toggle_who_dis': 'Who Dis',
    'toggle_legacy_prefix_commands': 'Legacy Prefix Command'
}

#region REMINDERS
REMINDERS_NAME = "remind"
REMINDERS_BRIEF = "Set a reminder, or see yours."
REMINDERS_DESCRIPTION = "Set a reminder for yourself, here or by DM, once or repeating (every day, weekday, week, month or year, or on chosen days), in your own time zone. With no fields it shows your reminders, where you can add, delete and change your time zone. Admins can also remind a role or everyone, and see everyone's reminders in this server. For a prefix command, quote anything with spaces: .remind \"tomorrow 9am\" \"call the dentist\""
REMINDERS_ALIASES = ['rm']
REMINDERS_WHEN_DESCRIPTION = 'When: "in 2 hours", "tomorrow 9am", "Thursday 8pm", "Dec 25 10:00".'
REMINDERS_WHAT_DESCRIPTION = "What to remind you of."
REMINDERS_REPEAT_DESCRIPTION = "Once (the default), or every day, weekday, week, month or year. Pick days on the card."
REMINDERS_WHERE_DESCRIPTION = "Here (the default), pinging you, or by DM."
REMINDERS_ROLE_DESCRIPTION = "A role to ping instead of you, or @everyone. (admin only)"
#endregion

#region HELP
HELP_NAME = "help"
HELP_TITLE = "GBot Help"
HELP_BRIEF = "See what GBot can do in this server."
HELP_OVERVIEW = "Here's what GBot can do here. Press a button to open one, or pick a feature below to see how it works."
HELP_FEATURE_DESCRIPTION = "A feature to see how it works."
#endregion

#region CONFIG
CONFIG_NAME = "config"
CONFIG_BRIEF = "GBot's settings for this server. (admin only)"
CONFIG_DESCRIPTION = "Open this server's GBot settings: turn features on and off, pick the Storms and admin channels and the admin and Who Dis roles, change the prefix for prefix commands, and look up the reports on a member. (admin only)"
CONFIG_ALIASES = ['c']

REPORT_MESSAGE_NAME = "Report to admins"
REPORT_MEMBER_NAME = "Report"
#endregion

#region GCOIN
GCOIN_NAME = "gcoin"
GCOIN_BRIEF = "Your GCoin wallet, or someone else's."
GCOIN_DESCRIPTION = "Show your GCoin wallet, or another member's: their balance and rank here, then send GCoin, see your transaction history, or see the ranking for this server and everywhere. Admins can also see other members' history."
GCOIN_ALIASES = ['gc']
GCOIN_USER_DESCRIPTION = "Someone else whose wallet you want to see."
GCOIN_VIEW_WALLET_NAME = "View wallet"
#endregion

#region GTRADE
GTRADE_NAME = "gtrade"
GTRADE_BRIEF = "Your items: craft, show off, sell and buy them."
GTRADE_DESCRIPTION = "Open your items: craft one from an image link, show one off, rename it, destroy it for its value back, or sell it on this server's market or to one person. The market lists what's for sale here, and Trades every trade of yours still open, to answer or take back."
GTRADE_ALIASES = ['gt']
GTRADE_VIEW_ITEMS_NAME = "View items"
GTRADE_CRAFT_ITEM_NAME = "Craft item"
#endregion

#region HYPE
HYPE_NAME = "hype"
HYPE_BRIEF = "Manage automated replies and reactions to messages. (admin only)"
HYPE_DESCRIPTION = "List, add, edit, delete and test this server's Hype matches: when a message matches a regular expression, GBot replies with one of its responses or reacts with one of its emoji, picked at random. (admin only)"
HYPE_ALIASES = ['hy']
#endregion

#region AGENT
AGENT_NOTICE = "ℹ️ GBot's AI agent is on here. Messages in this channel can be sent to Anthropic so it can respond."
AGENT_NAME = "agent"
AGENT_BRIEF = "An AI agent you set up in plain words."
AGENT_DESCRIPTION = "Set up an AI agent that replies and reacts in this server: its key, its instructions in plain words, when it replies and who it responds to, for the whole server or one channel, and what it remembers. Admins get all of it. Members get the memories they saved, if memory_access is everyone."
AGENT_ALIASES = ['ag']
#endregion

#region MUSIC
MUSIC_NAME = "music"
MUSIC_BRIEF = "Play music from YouTube in your voice channel."
MUSIC_DESCRIPTION = "Play a search, a YouTube link or a playlist in your voice channel, or open the now-playing card without one: pause, skip, stop, shuffle, loop the queue with elevator mode, add songs, move or remove queued ones, restart the song and follow someone's Spotify. Anyone in GBot's voice channel can press it."
MUSIC_ALIASES = ['m']
MUSIC_SEARCH_DESCRIPTION = "A song to play: a search, a YouTube link or a playlist. Leave it out to see the card."
#endregion

#region STORMS
STORMS_NAME = "storms"
STORMS_BRIEF = "Guess the Storm's number to win GCoin."
STORMS_DESCRIPTION = "Storms roll into this server's Storms channel now and then: put up your umbrella to start one, then guess its number from 1 to 200, or bet GCoin on a guess, with a bigger win the fewer tries it takes. Your higher or lower hint is yours alone. With no number, it puts up your umbrella or says whether a Storm is on."
STORMS_ALIASES = ['s']
STORMS_NUMBER_DESCRIPTION = "Your guess, from 1 to 200."
STORMS_BET_DESCRIPTION = "GCoin to bet on your guess: win it, multiplied, or lose it."
STORMS_UMBRELLA_LABEL = "Umbrella"
#endregion

#region WHO DIS
WHODIS_NAME = "whodis"
WHODIS_BRIEF = "Chat anonymously with a random member, then guess who."
WHODIS_DESCRIPTION = "Get paired with a random member for an anonymous chat in DMs, then guess who they are for a chance to win GCoin. Without a name it opens the card to start a game, or leave Who Dis. With one, in your DMs with GBot, it's your one guess."
WHODIS_ALIASES = ['wd']
WHODIS_USER_DESCRIPTION = "Your guess: the name of who you think you're chatting with."
#endregion

#region PATREON
PATREON_NAME = "patreon"
PATREON_BRIEF = "In the GBot Patreon server, specify your server's ID to enable GBot functionality. (patrons only)"
PATREON_DESCRIPTION = "In the GBot Patreon server, specify a server's ID to enable GBot functionality in that server. (patrons only)"
PATREON_ALIASES = ['pt']
PATREON_SERVER_ID_DESCRIPTION = "The ID of the server you are registering GBot with."
#endregion

#region HALO
# DISCONTINUED — kept in place alongside the archived halo_cog, which still references these names.
HALO_NAME = "name"
HALO_BRIEF = "Participate in or leave the weekly GBot Halo competition. (admin optional)"
HALO_DESCRIPTION = "Participate in or leave the weekly GBot Halo competition. (admin optional)\naction options are: <gamertag>, rm"
HALO_ALIASES = ['h']
#endregion
