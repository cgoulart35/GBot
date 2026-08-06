# Command metadata, grouped by cog to mirror the command tree itself.
#
# Every command lives under its cog's group: /music play, .music play (.m p). Grouping keeps GBot
# from claiming 36 generic global names ("play", "stop", "send", "market") that collide with every
# other bot in a guild's command picker, and it lets two cogs share a leaf name — /storms guess and
# /whodis guess coexist, which is why whodis no longer has to call its guess command "dis".
# Discord allows two levels at most, and a command with subcommands is not itself invocable, so
# leaves stay flat under each group rather than nesting further.
#
# Naming is uniform: <COG>_GROUP_<ATTR> for a group, <COG>_<COMMAND>_<ATTR> for a leaf, and
# <COG>_<COMMAND>_<ARGUMENT>_DESCRIPTION for a slash option. Leaf names only have to be unique
# within their group, so short natural words are usable again — as are aliases, which is why .m s
# is music skip, .c s is config show and .wd s is whodis start.

#region CONFIG
CONFIG_GROUP_NAME = "config"
CONFIG_GROUP_BRIEF = "Configure GBot for this server. (admin only)"
CONFIG_GROUP_DESCRIPTION = "Configure GBot for this server: view the current configuration, set the command prefix, assign feature roles and channels, and turn features on and off. (admin only)"
CONFIG_GROUP_ALIASES = ['c']

CONFIG_SHOW_NAME = "show"
CONFIG_SHOW_BRIEF = "Shows the server's current GBot configuration. (admin only)"
CONFIG_SHOW_DESCRIPTION = "Shows the server's current GBot configuration. (admin only)"
CONFIG_SHOW_ALIASES = ['s']

CONFIG_PREFIX_NAME = "prefix"
CONFIG_PREFIX_BRIEF = "Set the prefix for all GBot commands used in this server. (admin only)"
CONFIG_PREFIX_DESCRIPTION = "Set the prefix for all GBot commands used in this server. (admin only)"
CONFIG_PREFIX_ALIASES = ['pr']
CONFIG_PREFIX_PREFIX_DESCRIPTION = "The character(s) used for this server's command prefix."

CONFIG_ROLE_NAME = "role"
CONFIG_ROLE_BRIEF = "Set the role for a specific GBot feature in this server. (admin only)"
CONFIG_ROLE_DESCRIPTION = "Set the role for a specific GBot feature in this server. (admin only)\nrole_type options are: admin, whodis"
CONFIG_ROLE_ALIASES = ['rl']
CONFIG_ROLE_ROLE_DESCRIPTION = "A role in the server."
CONFIG_ROLE_TYPE_DESCRIPTION = "The type of role to configure."

CONFIG_CHANNEL_NAME = "channel"
CONFIG_CHANNEL_BRIEF = "Set the channel for a specific GBot feature in this server. (admin only)"
CONFIG_CHANNEL_DESCRIPTION = "Set the channel for a specific GBot feature in this server. (admin only)\nchannel_type options are: admin, storms"
CONFIG_CHANNEL_ALIASES = ['ch']
CONFIG_CHANNEL_CHANNEL_DESCRIPTION = "A channel in the server."
CONFIG_CHANNEL_TYPE_DESCRIPTION = "The type of channel to configure."

CONFIG_TOGGLE_NAME = "toggle"
CONFIG_TOGGLE_BRIEF = "Turn on/off all functionality for a GBot feature in this server. (admin only)"
CONFIG_TOGGLE_DESCRIPTION = "Turn on/off all functionality for a GBot feature in this server. (admin only)\nfeature_type options are: gcoin, gtrade, hype, music, storms, whodis, legacy prefix commands"
CONFIG_TOGGLE_ALIASES = ['t']
CONFIG_TOGGLE_FEATURE_TYPE_DESCRIPTION = "The feature to toggle on/off."
#endregion

#region GCOIN
GCOIN_GROUP_NAME = "gcoin"
GCOIN_GROUP_BRIEF = "Earn, send and track GCoin, GBot's currency."
GCOIN_GROUP_DESCRIPTION = "Earn, send and track GCoin, GBot's currency. View wallets and transaction history for yourself or others in this server."
GCOIN_GROUP_ALIASES = ['gc']

GCOIN_SEND_NAME = "send"
GCOIN_SEND_BRIEF = "Send GCoin to another user in this server."
GCOIN_SEND_DESCRIPTION = "Send GCoin to another user in this server."
GCOIN_SEND_ALIASES = ['sd']
GCOIN_SEND_USER_DESCRIPTION = "The user to send GCoin to."
GCOIN_SEND_AMOUNT_DESCRIPTION = "The amount of GCoin to send."

GCOIN_WALLET_NAME = "wallet"
GCOIN_WALLET_BRIEF = "Show your wallet, or another user's wallet in this server."
GCOIN_WALLET_DESCRIPTION = "Show your wallet, or another user's wallet in this server."
GCOIN_WALLET_ALIASES = ['w']
GCOIN_WALLET_USER_DESCRIPTION = "The user whose wallet you want to view."

GCOIN_WALLETS_NAME = "wallets"
GCOIN_WALLETS_BRIEF = "Show wallets of all users in this server."
GCOIN_WALLETS_DESCRIPTION = "Show wallets of all users in this server."
GCOIN_WALLETS_ALIASES = ['ws']

GCOIN_HISTORY_NAME = "history"
GCOIN_HISTORY_BRIEF = "Show your transaction history, or a user's transaction history in this server. (admin optional)"
GCOIN_HISTORY_DESCRIPTION = "Show your transaction history, or another user's transaction history in this server. Admin role needed to show other user's history. (admin optional)"
GCOIN_HISTORY_ALIASES = ['hs']
GCOIN_HISTORY_USER_DESCRIPTION = "The user whose transaction history you want to see."
#endregion

#region GTRADE
GTRADE_GROUP_NAME = "gtrade"
GTRADE_GROUP_BRIEF = "Craft, show off and trade items with other users."
GTRADE_GROUP_DESCRIPTION = "Craft items with GCoin, show them off, and trade them with other users through direct requests or the server's market."
GTRADE_GROUP_ALIASES = ['gt']

GTRADE_CRAFT_NAME = "craft"
GTRADE_CRAFT_BRIEF = "Craft items to show off and trade."
GTRADE_CRAFT_DESCRIPTION = "Craft items to show off and trade. Surround name with double quotes if multiple words.\ntype options are: image"
GTRADE_CRAFT_ALIASES = ['cr']
GTRADE_CRAFT_NAME_DESCRIPTION = "The name of the item you want to craft."
GTRADE_CRAFT_TYPE_DESCRIPTION = "The type of item you want to craft."
GTRADE_CRAFT_VALUE_DESCRIPTION = "The amount of GCoin you want to spend on crafting."

GTRADE_RENAME_NAME = "rename"
GTRADE_RENAME_BRIEF = "Rename an item in your inventory."
GTRADE_RENAME_DESCRIPTION = "Rename an item in your inventory."
GTRADE_RENAME_ALIASES = ['rn']
GTRADE_RENAME_ITEM_DESCRIPTION = "The name of the item you want to rename."
GTRADE_RENAME_NAME_DESCRIPTION = "The new name of the item."

GTRADE_DESTROY_NAME = "destroy"
GTRADE_DESTROY_BRIEF = "Destroy an item in your inventory."
GTRADE_DESTROY_DESCRIPTION = "Destroy an item in your inventory."
GTRADE_DESTROY_ALIASES = ['d']
GTRADE_DESTROY_ITEM_DESCRIPTION = "The name of the item you want to destroy."

GTRADE_ITEM_NAME = "item"
GTRADE_ITEM_BRIEF = "Show off an item in your inventory."
GTRADE_ITEM_DESCRIPTION = "Show off an item in your inventory."
GTRADE_ITEM_ALIASES = ['i']
GTRADE_ITEM_ITEM_DESCRIPTION = "The item you want to show off."

GTRADE_ITEMS_NAME = "items"
GTRADE_ITEMS_BRIEF = "List all items in your inventory, or another user's inventory in this server."
GTRADE_ITEMS_DESCRIPTION = "List all items in your inventory, or another user's inventory in this server."
GTRADE_ITEMS_ALIASES = ['is']
GTRADE_ITEMS_USER_DESCRIPTION = "The user whose inventory you want to see."

GTRADE_MARKET_NAME = "market"
GTRADE_MARKET_BRIEF = "Show all market items for sale and personal trade requests in the discord server."
GTRADE_MARKET_DESCRIPTION = "Show all market items for sale and personal trade requests in the discord server."
GTRADE_MARKET_ALIASES = ['m']

GTRADE_BUY_NAME = "buy"
GTRADE_BUY_BRIEF = "Buy another user's item for sale in the discord server."
GTRADE_BUY_DESCRIPTION = "Buy another user's item for sale in the discord server. Create a request to buy from a user, complete a user's pending sell request, or buy an item for sale in the server's market."
GTRADE_BUY_ALIASES = ['by']
GTRADE_BUY_ITEM_DESCRIPTION = "The item you want to buy."
GTRADE_BUY_USER_DESCRIPTION = "The user you want to buy the item from."

GTRADE_SELL_NAME = "sell"
GTRADE_SELL_BRIEF = "Sell an item to another user in this discord server."
GTRADE_SELL_DESCRIPTION = "Sell an item to another user in this discord server. Create a request to sell to a user, complete a user's pending buy request, or place an item for sale in the server's market."
GTRADE_SELL_ALIASES = ['sl']
GTRADE_SELL_ITEM_DESCRIPTION = "The item you want to sell."
GTRADE_SELL_USER_DESCRIPTION = "The user you want to sell the item to."
#endregion

#region HYPE
HYPE_GROUP_NAME = "hype"
HYPE_GROUP_BRIEF = "Automated replies and reactions to messages. (admin only)"
HYPE_GROUP_DESCRIPTION = "Set up automated replies and emoji reactions that fire when a message in this server matches a regular expression. (admin only)"
HYPE_GROUP_ALIASES = ['hy']

HYPE_RESPOND_NAME = "respond"
HYPE_RESPOND_BRIEF = "Set a regex to match against messages, and a list of possible responses to reply with. (admin only)"
HYPE_RESPOND_DESCRIPTION = "Set a regular expression to match against new messages in this server, and a list of possible responses to reply to it with. Surround regex and response each with double quotes if multiple words. (admin only)"
HYPE_RESPOND_ALIASES = ['rs']
HYPE_RESPOND_REGEX_DESCRIPTION = "A regular expression used for automated replies."
HYPE_RESPOND_RESPONSES_DESCRIPTION = "A double-quote separated list of possible replies for the given regex."

HYPE_REACT_NAME = "react"
HYPE_REACT_BRIEF = "Set a regex to match against messages, and a list of possible emojis to react with. (admin only)"
HYPE_REACT_DESCRIPTION = "Set a regular expression to match against new messages in this server, and a list of possible emojis to react to it with. Surround regex with double quotes if multiple words. (admin only)"
HYPE_REACT_ALIASES = ['re']
HYPE_REACT_REGEX_DESCRIPTION = "A regular expression used for automated reactions."
HYPE_REACT_EMOJIS_DESCRIPTION = "A list of possible reaction emojis for the given regex."

HYPE_REMOVE_NAME = "remove"
HYPE_REMOVE_BRIEF = "Remove an existing regular expression match response in this server. (admin only)"
HYPE_REMOVE_DESCRIPTION = "Remove an existing regular expression match response in this server. (admin only)"
HYPE_REMOVE_ALIASES = ['rm']
#endregion

#region MUSIC
MUSIC_GROUP_NAME = "music"
MUSIC_GROUP_BRIEF = "Play videos/music from YouTube in a voice channel."
MUSIC_GROUP_DESCRIPTION = "Play videos/music streamed from YouTube in a voice channel, manage the queue, and follow another user's Spotify activity."
MUSIC_GROUP_ALIASES = ['m']

MUSIC_PLAY_NAME = "play"
MUSIC_PLAY_BRIEF = "Play videos/music streamed from YouTube."
MUSIC_PLAY_DESCRIPTION = "Play videos/music streamed from YouTube. Accepts a search, a video URL, a livestream, or a playlist."
MUSIC_PLAY_ALIASES = ['p']
MUSIC_PLAY_INPUT_DESCRIPTION = "A song or video name, or a YouTube video, livestream, or playlist URL."

MUSIC_QUEUE_NAME = "queue"
MUSIC_QUEUE_BRIEF = "Displays the current sounds in queue."
MUSIC_QUEUE_DESCRIPTION = "Displays the current sounds in queue."
MUSIC_QUEUE_ALIASES = ['q']

MUSIC_ELEVATOR_NAME = "elevator"
MUSIC_ELEVATOR_BRIEF = "Toggle elevator mode to loop the queue."
MUSIC_ELEVATOR_DESCRIPTION = "Toggle elevator mode to loop the queue. Each sound returns to the end of the queue as it finishes, so a single queued sound repeats and several cycle in order."
MUSIC_ELEVATOR_ALIASES = ['e']

MUSIC_SKIP_NAME = "skip"
MUSIC_SKIP_BRIEF = "Skips the current sound being played."
MUSIC_SKIP_DESCRIPTION = "Skips the current sound being played."
MUSIC_SKIP_ALIASES = ['s']

MUSIC_STOP_NAME = "stop"
MUSIC_STOP_BRIEF = "Stops the bot from playing sounds and clears the queue."
MUSIC_STOP_DESCRIPTION = "Stops the bot from playing sounds and clears the queue."
MUSIC_STOP_ALIASES = ['st']

MUSIC_PAUSE_NAME = "pause"
MUSIC_PAUSE_BRIEF = "Pauses the current sound being played."
MUSIC_PAUSE_DESCRIPTION = "Pauses the current sound being played."
MUSIC_PAUSE_ALIASES = ['ps']

MUSIC_RESUME_NAME = "resume"
MUSIC_RESUME_BRIEF = "Resumes the current sound being played."
MUSIC_RESUME_DESCRIPTION = "Resumes the current sound being played."
MUSIC_RESUME_ALIASES = ['r']

MUSIC_SPOTIFY_NAME = "spotify"
MUSIC_SPOTIFY_BRIEF = "Play current spotify activity streamed from YouTube."
MUSIC_SPOTIFY_DESCRIPTION = "Play current spotify activity streamed from YouTube. Songs are added to the queue as the user's activity changes."
MUSIC_SPOTIFY_ALIASES = ['sp']
MUSIC_SPOTIFY_USER_DESCRIPTION = "The user whose Spotify activity you want to listen to."
#endregion

#region STORMS
STORMS_GROUP_NAME = "storms"
STORMS_GROUP_BRIEF = "Random storm events you can join to earn GCoin."
STORMS_GROUP_DESCRIPTION = "Random storm events announced in this server's storms channel. Start a storm, guess to win, or bet GCoin on your guess."
STORMS_GROUP_ALIASES = ['s']

STORMS_UMBRELLA_NAME = "umbrella"
STORMS_UMBRELLA_BRIEF = "Start the incoming Storm and earn 0.25 GCoin."
STORMS_UMBRELLA_DESCRIPTION = "Start the incoming Storm and earn 0.25 GCoin."
STORMS_UMBRELLA_ALIASES = ['u']

STORMS_GUESS_NAME = "guess"
STORMS_GUESS_BRIEF = "Make a guess with a winning reward of 1.00 GCoin."
STORMS_GUESS_DESCRIPTION = "Make a guess with a winning reward of 1.00 GCoin. Multiplier applied for guesses made in 4 attempts or less."
STORMS_GUESS_ALIASES = ['g']
STORMS_GUESS_NUMBER_DESCRIPTION = "The number you want to guess."

STORMS_BET_NAME = "bet"
STORMS_BET_BRIEF = "Make a guess. If you win, you earn the amount of points bet. If you lose, you lose those points."
STORMS_BET_DESCRIPTION = "Make a guess. If you win, you earn the amount of points bet within your wallet. If you lose, you lose those points. Multiplier applied for guesses made in 4 attempts or less."
STORMS_BET_ALIASES = ['b']
STORMS_BET_GCOIN_DESCRIPTION = "The amount of GCoin you want to bet on your guess."
STORMS_BET_NUMBER_DESCRIPTION = "The number you want to guess."
#endregion

#region WHO DIS
WHODIS_GROUP_NAME = "whodis"
WHODIS_GROUP_BRIEF = "Guess the random user you have been paired with."
WHODIS_GROUP_DESCRIPTION = "A mini-game where you are paired with a random user in the server and try to guess who they are for a chance to win GCoin."
WHODIS_GROUP_ALIASES = ['wd']

WHODIS_START_NAME = "start"
WHODIS_START_BRIEF = "Start or end a mini-game where you try to guess a random user in the server you are paired with."
WHODIS_START_DESCRIPTION = "Start or end a mini-game where you try to guess a random user in the server you are paired with. You have 1 guess, and if you guess correctly you earn GCoin. You can play once every hour."
WHODIS_START_ALIASES = ['s']

WHODIS_GUESS_NAME = "guess"
WHODIS_GUESS_BRIEF = "Guess the name of the user you are paired with for a chance to win GCoin."
WHODIS_GUESS_DESCRIPTION = "Guess the name of the user you are paired with for a chance to win GCoin."
WHODIS_GUESS_ALIASES = ['g']
WHODIS_GUESS_USER_DESCRIPTION = "The user you think you are paired with."

WHODIS_LEAVE_NAME = "leave"
WHODIS_LEAVE_BRIEF = "Remove the server's 'Who Dis?' role opting you out of any future games."
WHODIS_LEAVE_DESCRIPTION = "Remove the server's 'Who Dis?' role opting you out of any future games."
WHODIS_LEAVE_ALIASES = ['l']

WHODIS_REPORT_NAME = "report"
WHODIS_REPORT_BRIEF = "Report a user to server admins for bad behavior."
WHODIS_REPORT_DESCRIPTION = "Report a user to server admins for bad behavior. The reported user's last 5 messages will be captured from the channel sent in, or an ongoing Who Dis game."
WHODIS_REPORT_ALIASES = ['rp']
WHODIS_REPORT_USER_DESCRIPTION = "The user you want to report for bad behavior (leave blank for Who Dis)."
#endregion

#region PATREON
# Deliberately ungrouped: the cog has exactly one command, and grouping it would only yield
# /patreon patreon.
PATREON_NAME = "patreon"
PATREON_BRIEF = "In the GBot Patreon server, specify your server's ID to enable GBot functionality. (patrons only)"
PATREON_DESCRIPTION = "In the GBot Patreon server, specify a server's ID to enable GBot functionality in that server. (patrons only)"
PATREON_ALIASES = ['pt']
PATREON_SERVER_ID_DESCRIPTION = "The ID of the server you are registering GBot with."
#endregion

#region HALO
# DISCONTINUED — kept in place alongside the archived halo_cog, which still references these names.
# Never grouped, because the cog it belongs to is not loaded.
HALO_NAME = "name"
HALO_BRIEF = "Participate in or leave the weekly GBot Halo competition. (admin optional)"
HALO_DESCRIPTION = "Participate in or leave the weekly GBot Halo competition. (admin optional)\naction options are: <gamertag>, rm"
HALO_ALIASES = ['h']
#endregion
