#region IMPORTS
from dataclasses import dataclass

import anthropic
#endregion

# The only file that knows the agent runs on Claude, so another provider could sit beside it later.
# It holds no permissions: every tool call goes through the runTool the cog passes in, which is where
# Discord roles get checked. Nothing here decides what anyone is allowed to do.

REQUEST_TIMEOUT_SECONDS = 60.0

TOOL_REACT = 'react'
TOOL_SAVE_MEMORY = 'save_memory'
TOOL_UPDATE_MEMORY = 'update_memory'
TOOL_FORGET_MEMORY = 'forget_memory'
TOOL_STAY_SILENT = 'stay_silent'
TOOL_GET_FEATURE_GUIDE = 'get_feature_guide'
TOOL_SET_TIMEZONE = 'set_timezone'
# read: looking things up, as the commands would show them to the sender
TOOL_GET_WALLET = 'get_wallet'
TOOL_GET_RANKING = 'get_ranking'
TOOL_SEARCH_MARKET = 'search_market'
TOOL_GET_ITEMS = 'get_items'
TOOL_GET_MUSIC_QUEUE = 'get_music_queue'
TOOL_GET_FEATURES = 'get_features'
TOOL_GET_REMINDERS = 'get_reminders'
TOOL_SHOW_ITEM = 'show_item'
TOOL_GET_HISTORY = 'get_history'
TOOL_HYPE_LOOKUP = 'hype_lookup'
TOOL_STORM_STATUS = 'storm_status'
TOOL_OPEN_CARD = 'open_card'
# safe: doing what the sender could do themselves, which moves no money and changes nothing of anyone else's
TOOL_PLAY_MUSIC = 'play_music'
TOOL_CONTROL_MUSIC = 'control_music'
TOOL_SET_REMINDER = 'set_reminder'
TOOL_EDIT_REMINDER = 'edit_reminder'
TOOL_GET_TRADES = 'get_trades'
TOOL_DELETE_REMINDER = 'delete_reminder'
TOOL_GUESS_STORM = 'guess_storm'
TOOL_STORM_UMBRELLA = 'storm_umbrella'
TOOL_WHO_DIS = 'who_dis'
TOOL_EDIT_MUSIC = 'edit_music'
TOOL_RENAME_ITEM = 'rename_item'
MUSIC_ACTIONS = ['skip', 'pause', 'resume', 'stop', 'shuffle']
# all: what moves GCoin or items or changes the server's settings. Each only posts a confirm card, and
# nothing happens until the sender presses it.
TOOL_SEND_GCOIN = 'send_gcoin'
TOOL_BUY_ITEM = 'buy_item'
TOOL_SELL_ITEM = 'sell_item'
TOOL_SET_FEATURE = 'set_feature'
TOOL_BET_STORM = 'bet_storm'
TOOL_HYPE_CHANGE = 'hype_change'
TOOL_CRAFT_ITEM = 'craft_item'
TOOL_DESTROY_ITEM = 'destroy_item'
TOOL_ANSWER_TRADE = 'answer_trade'
TOOL_REMIND_ROLE = 'remind_role'
TOOL_SET_CONFIG = 'set_config'
TOOL_REPORT = 'report'
TOOL_AGENT_SETTING = 'agent_setting'
TOOL_PATREON = 'patreon_register'
# the features set_feature can switch: not the agent itself, which would turn off the conversation
# switching it (its own settings go through agent_setting, behind a confirm)
SWITCHABLE_FEATURES = ['GCoin', 'GTrade', 'Hype', 'Music', 'Reminders', 'Storms', 'Who Dis', 'Legacy Prefix Command']

# What the agent may do in a channel, set by admins. Each level adds to the one before it, and only a
# level's tools are sent to Claude, so it can't be talked into one it wasn't given.
ABILITIES_OFF = 'off'
ABILITIES_READ = 'read'
ABILITIES_SAFE = 'safe'
ABILITIES_ALL = 'all'
ABILITIES = [ABILITIES_OFF, ABILITIES_READ, ABILITIES_SAFE, ABILITIES_ALL]
READ_TOOLS = {TOOL_GET_WALLET, TOOL_GET_RANKING, TOOL_SEARCH_MARKET, TOOL_GET_ITEMS, TOOL_GET_TRADES, TOOL_SHOW_ITEM, TOOL_GET_MUSIC_QUEUE, TOOL_GET_FEATURES, TOOL_GET_REMINDERS,
              TOOL_GET_HISTORY, TOOL_HYPE_LOOKUP, TOOL_STORM_STATUS, TOOL_OPEN_CARD}
SAFE_TOOLS = {TOOL_PLAY_MUSIC, TOOL_CONTROL_MUSIC, TOOL_SET_REMINDER, TOOL_EDIT_REMINDER, TOOL_DELETE_REMINDER, TOOL_GUESS_STORM, TOOL_SET_TIMEZONE,
              TOOL_STORM_UMBRELLA, TOOL_WHO_DIS, TOOL_EDIT_MUSIC, TOOL_RENAME_ITEM}
ALL_TOOLS = {TOOL_SEND_GCOIN, TOOL_BUY_ITEM, TOOL_SELL_ITEM, TOOL_SET_FEATURE, TOOL_BET_STORM,
             TOOL_HYPE_CHANGE, TOOL_CRAFT_ITEM, TOOL_DESTROY_ITEM, TOOL_ANSWER_TRADE, TOOL_REMIND_ROLE, TOOL_SET_CONFIG, TOOL_REPORT, TOOL_AGENT_SETTING, TOOL_PATREON}
ACTING_TOOLS = SAFE_TOOLS | ALL_TOOLS

# The API allows at most 20 strict tools in a request, and every level has to fit. The read lookups
# aren't strict, nor are the later actions; their code checks everything it's given rather than
# relying on the schema.
MAX_STRICT_TOOLS = 20

# a reminder's repeats, as when.py names them, and the weekdays a "days" one goes off on
REPEAT_CHOICES = ['once', 'daily', 'weekdays', 'weekly', 'monthly', 'yearly', 'days']
WEEKDAY_CHOICES = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
DAYS_SCHEMA = {'type': 'array', 'items': {'type': 'string', 'enum': WEEKDAY_CHOICES}}

def toolsAllowed(abilities):
    allowed = set()
    if abilities in (ABILITIES_READ, ABILITIES_SAFE, ABILITIES_ALL):
        allowed |= READ_TOOLS
    if abilities in (ABILITIES_SAFE, ABILITIES_ALL):
        allowed |= SAFE_TOOLS
    if abilities == ABILITIES_ALL:
        allowed |= ALL_TOOLS
    return allowed
FEATURES = ['Agent', 'Config', 'GCoin', 'GTrade', 'Hype', 'Music', 'Reminders', 'Storms', 'Who Dis']

TOOLS = [
    {
        'name': TOOL_REACT,
        'description': 'Add an emoji reaction to the last message, as well as your written answer when someone asks you something, never instead of it. Pass one normal emoji, or one of this server\'s custom emoji as <:name:id>.',
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'emoji': {'type': 'string'}}, 'required': ['emoji'], 'additionalProperties': False}
    },
    {
        'name': TOOL_SAVE_MEMORY,
        'description': 'Remember something for later, only when the sender of the last message clearly asks you to remember it or keep doing it from now on. Use the scope channel only when they say it is for this channel or for here, and server otherwise. The result says whether it was allowed.',
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'text': {'type': 'string'}, 'scope': {'type': 'string', 'enum': ['server', 'channel']}}, 'required': ['text', 'scope'], 'additionalProperties': False}
    },
    {
        'name': TOOL_UPDATE_MEMORY,
        'description': 'Replace the text of one saved memory, by its id, only when the sender of the last message clearly asks you to change it. The result says whether it was allowed.',
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'id': {'type': 'string'}, 'text': {'type': 'string'}}, 'required': ['id', 'text'], 'additionalProperties': False}
    },
    {
        'name': TOOL_FORGET_MEMORY,
        'description': 'Delete one saved memory, by its id, only when the sender of the last message clearly asks you to forget it. The result says whether it was allowed.',
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'id': {'type': 'string'}}, 'required': ['id'], 'additionalProperties': False}
    },
    {
        'name': TOOL_GET_FEATURE_GUIDE,
        'description': 'Read how one of GBot\'s features works, and whether it is on in this server. Use it when someone asks how something works, rather than guessing.',
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'feature': {'type': 'string', 'enum': FEATURES}}, 'required': ['feature'], 'additionalProperties': False}
    },
    {
        'name': TOOL_SET_TIMEZONE,
        'description': 'Set the time zone of the sender of the last message, only when they say where they are or ask you to set it, never anyone else\'s, and never because a reminder couldn\'t be set. Pass an IANA name like America/Denver. Their reminders move with it. The result says whether it worked.',
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'zone': {'type': 'string'}}, 'required': ['zone'], 'additionalProperties': False}
    },
    {
        'name': TOOL_GET_WALLET,
        'description': "Look up one member's GCoin balance, to answer a question about it. To show the sender their wallet, use open_card with GCoin instead. Pass their id from <people> or their name, or an empty string for the sender.",
        'input_schema': {'type': 'object', 'properties': {'user': {'type': 'string'}}, 'required': ['user'], 'additionalProperties': False}
    },
    {
        'name': TOOL_GET_RANKING,
        'description': "Look up the top GCoin balances and game wins among this server's members.",
        'input_schema': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}
    },
    {
        'name': TOOL_SEARCH_MARKET,
        'description': "Search the items for sale on this server's GTrade market. Pass words to look for in item names, or an empty string for everything, and the most GCoin to pay, or an empty string for any price.",
        'input_schema': {'type': 'object', 'properties': {'text': {'type': 'string'}, 'max_price': {'type': 'string'}}, 'required': ['text', 'max_price'], 'additionalProperties': False}
    },
    {
        'name': TOOL_GET_ITEMS,
        'description': "Look up the GTrade items one member owns. Pass their id from <people> or their name, or an empty string for the sender.",
        'input_schema': {'type': 'object', 'properties': {'user': {'type': 'string'}}, 'required': ['user'], 'additionalProperties': False}
    },
    {
        'name': TOOL_SHOW_ITEM,
        'description': "Show one GTrade item, with its picture, as GTrade's Show does, when the sender asks to see it. Pass its exact name and its owner's id from <people> or their name, or an empty string for the sender. The item's card is your whole reply.",
        'input_schema': {'type': 'object', 'properties': {'item': {'type': 'string'}, 'owner': {'type': 'string'}}, 'required': ['item', 'owner'], 'additionalProperties': False}
    },
    {
        'name': TOOL_OPEN_CARD,
        'description': "Show the sender one of GBot's cards when they ask to see it, as typing its command would: Music moves the now-playing card down to the bottom of the channel, GCoin posts their wallet and Storms what the weather is, and any other posts a button that opens that feature's card privately for them, such as their reminders. The card or the button is your whole reply.",
        'input_schema': {'type': 'object', 'properties': {'feature': {'type': 'string', 'enum': FEATURES}}, 'required': ['feature'], 'additionalProperties': False}
    },
    {
        'name': TOOL_GET_MUSIC_QUEUE,
        'description': "Look up what is playing and what is queued in this server.",
        'input_schema': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}
    },
    {
        'name': TOOL_GET_FEATURES,
        'description': "Look up which of GBot's features are turned on in this server.",
        'input_schema': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}
    },
    {
        'name': TOOL_GET_REMINDERS,
        'description': "Look up the times and ids of the sender's own reminders in this server, to answer when one is or to delete one. What they say is private, so to show them their reminders use open_card with Reminders instead.",
        'input_schema': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}
    },
    {
        'name': TOOL_PLAY_MUSIC,
        'description': "Play or queue a song for the sender of the last message, by a search or a link, only when they clearly ask you to. With nothing to search for, as in just play, it resumes what is paused. The result says whether it worked.",
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'query': {'type': 'string'}}, 'required': ['query'], 'additionalProperties': False}
    },
    {
        'name': TOOL_CONTROL_MUSIC,
        'description': "Control the music, only when the sender of the last message clearly asks you to. The result says whether it worked.",
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'action': {'type': 'string', 'enum': MUSIC_ACTIONS}}, 'required': ['action'], 'additionalProperties': False}
    },
    {
        'name': TOOL_SET_REMINDER,
        'description': "Set a reminder for the sender of the last message, only when they clearly ask for one. Pass when as they said it, like \"in 2 hours\", \"tomorrow 9am\" or \"Thursday 8pm\", what to remind them of, how it repeats (days, like [\"mon\", \"wed\", \"fri\"], only with repeat days, else []), and where as here, unless they ask for a DM. \"in\" times count to the second, like \"in 90 seconds\", a time named for the current minute goes off right away, so just set it, a repeat can start with a timer (\"every Monday, 30 seconds from now\" is when \"in 30 seconds\", repeat days, days [\"mon\"]), and reminders go up to 10 years ahead. The result says whether it worked.",
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'when': {'type': 'string'}, 'what': {'type': 'string'}, 'repeat': {'type': 'string', 'enum': REPEAT_CHOICES}, 'days': DAYS_SCHEMA, 'where': {'type': 'string', 'enum': ['here', 'dm']}}, 'required': ['when', 'what', 'repeat', 'days', 'where'], 'additionalProperties': False}
    },
    {
        'name': TOOL_DELETE_REMINDER,
        'description': "Ask the sender to confirm deleting their own reminders here, by their ids from get_reminders, only when they clearly ask you to. Pass every one they asked for, or an empty list for all of theirs, which needs no lookup first: one confirm card covers them all, and it is your whole reply.",
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'ids': {'type': 'array', 'items': {'type': 'string'}}}, 'required': ['ids'], 'additionalProperties': False}
    },
    {
        'name': TOOL_SEND_GCOIN,
        'description': "Ask the sender of the last message to confirm sending GCoin to a member, only when they clearly ask to send it. Pass the member's id from <people> or their name, the amount, and a short note or an empty string. One person per message, never several or everyone: say so. This only posts a confirm card: nothing is sent until they press it.",
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'user': {'type': 'string'}, 'amount': {'type': 'string'}, 'note': {'type': 'string'}}, 'required': ['user', 'amount', 'note'], 'additionalProperties': False}
    },
    {
        'name': TOOL_BUY_ITEM,
        'description': "Ask the sender of the last message to confirm buying a GTrade item from the member who owns it, only when they clearly ask to buy it, or with action cancel to take back a request to buy that they made earlier. Pass the item's exact name and the owner's id or name. This only posts a confirm card.",
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'item': {'type': 'string'}, 'owner': {'type': 'string'}, 'action': {'type': 'string', 'enum': ['buy', 'cancel']}}, 'required': ['item', 'owner', 'action'], 'additionalProperties': False}
    },
    {
        'name': TOOL_SELL_ITEM,
        'description': "Ask the sender of the last message to confirm selling their GTrade items, or to stop selling them, only when they clearly ask: on the market, with an empty string for buyer, or offered to one member by their id or name. Pass every item they named by exact name, or an empty list for all of theirs, which needs no lookup first, and action sell or stop. Items already as asked are left alone. One confirm card lists them all, and nothing happens until they press it.",
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'items': {'type': 'array', 'items': {'type': 'string'}}, 'buyer': {'type': 'string'}, 'action': {'type': 'string', 'enum': ['sell', 'stop']}}, 'required': ['items', 'buyer', 'action'], 'additionalProperties': False}
    },
    {
        'name': TOOL_SET_FEATURE,
        'description': "Ask an admin to confirm turning GBot's features on or off in this server, only when they clearly ask: pass every feature they named, all of them for \"everything\". This only posts one confirm card.",
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'features': {'type': 'array', 'items': {'type': 'string', 'enum': SWITCHABLE_FEATURES}}, 'setting': {'type': 'string', 'enum': ['on', 'off']}}, 'required': ['features', 'setting'], 'additionalProperties': False}
    },
    {
        'name': TOOL_GUESS_STORM,
        'description': "Guess a number in the Storm that is on, for the sender of the last message, only when they clearly ask. Their message is deleted so the number stays private, and GBot posts the result, which is your whole reply.",
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'number': {'type': 'string'}}, 'required': ['number'], 'additionalProperties': False}
    },
    {
        'name': TOOL_BET_STORM,
        'description': "Ask the sender of the last message to confirm a GCoin bet on a guess in the Storm that is on, only when they clearly ask. Their message is deleted so the number stays private. This only posts a confirm card, and their hint comes privately when they press it.",
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'number': {'type': 'string'}, 'bet': {'type': 'string'}}, 'required': ['number', 'bet'], 'additionalProperties': False}
    },
    {
        'name': TOOL_GET_HISTORY,
        'description': "Show recent GCoin transactions privately: the sender's own with an empty string, or for admins someone else's by their id or name. GBot posts a button that opens them privately, which is your whole reply.",
        'input_schema': {'type': 'object', 'properties': {'user': {'type': 'string'}}, 'required': ['user'], 'additionalProperties': False}
    },
    {
        'name': TOOL_HYPE_LOOKUP,
        'description': "For admins: list this server's Hype matches, or test which a message would set off. Pass the message to test, or an empty string to list.",
        'input_schema': {'type': 'object', 'properties': {'action': {'type': 'string', 'enum': ['list', 'test']}, 'text': {'type': 'string'}}, 'required': ['action', 'text'], 'additionalProperties': False}
    },
    {
        'name': TOOL_STORM_STATUS,
        'description': "Look up whether a Storm is on, incoming or not due.",
        'input_schema': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}
    },
    {
        'name': TOOL_STORM_UMBRELLA,
        'description': "Put up the umbrella to start a Storm that is incoming, for the sender, only when they clearly ask. GBot posts the result, which is your whole reply.",
        'input_schema': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}
    },
    {
        'name': TOOL_WHO_DIS,
        'description': "For the sender, only when they clearly ask to start a Who Dis game, end theirs, leave Who Dis, or guess who they are playing with by name. Their message is deleted and their Who Dis card goes to their DMs, where they do it, as who plays is a secret. You write nothing.",
        'input_schema': {'type': 'object', 'properties': {'action': {'type': 'string', 'enum': ['start', 'end', 'leave', 'guess']}, 'name': {'type': 'string'}}, 'required': ['action', 'name'], 'additionalProperties': False}
    },
    {
        'name': TOOL_EDIT_MUSIC,
        'description': "Change the music for the sender, only when they clearly ask: remove songs by their queue positions (several at once in positions, [] otherwise), move one, restart the song, turn elevator mode on or off (on true or false), or follow a member's Spotify (an empty user stops following), which also starts the music if nothing is playing and the sender is in a voice channel. Pass 0 for any position not needed, and on false unless turning elevator mode on.",
        'input_schema': {'type': 'object', 'properties': {'action': {'type': 'string', 'enum': ['remove', 'move', 'restart', 'elevator', 'follow_spotify']}, 'position': {'type': 'integer'}, 'positions': {'type': 'array', 'items': {'type': 'integer'}}, 'to': {'type': 'integer'}, 'user': {'type': 'string'}, 'on': {'type': 'boolean'}}, 'required': ['action', 'position', 'positions', 'to', 'user', 'on'], 'additionalProperties': False}
    },
    {
        'name': TOOL_RENAME_ITEM,
        'description': "Rename one of the sender's GTrade items, only when they clearly ask.",
        'input_schema': {'type': 'object', 'properties': {'item': {'type': 'string'}, 'name': {'type': 'string'}}, 'required': ['item', 'name'], 'additionalProperties': False}
    },
    {
        'name': TOOL_GET_TRADES,
        'description': "Look up the sender's own open GTrade trades in this server: offers and requests waiting on them, ones they made, and what they have on the market. Use it to answer what offers they have, or before accepting, declining or cancelling one.",
        'input_schema': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}
    },
    {
        'name': TOOL_EDIT_REMINDER,
        'description': "Change one of the sender's own reminders, by its id from get_reminders, only when they clearly ask: a new when as they said it, new words for what, or both, with an empty string for whichever stays. How it repeats and where it goes stay as they are. The result says whether it worked.",
        'input_schema': {'type': 'object', 'properties': {'id': {'type': 'string'}, 'when': {'type': 'string'}, 'what': {'type': 'string'}}, 'required': ['id', 'when', 'what'], 'additionalProperties': False}
    },
    {
        'name': TOOL_HYPE_CHANGE,
        'description': "For admins: add, edit or delete a Hype match, only when they clearly ask. For add and edit, pass a regular expression, whether it replies or reacts, and its replies (one per line) or emoji (separated by spaces). For edit, pass the match's number from hype_lookup; for delete, every number they asked for in numbers ([] otherwise), or numbers [] and number 0 for all the matches, which needs no lookup first. This only posts a confirm card showing exactly what will be saved or deleted.",
        'input_schema': {'type': 'object', 'properties': {'action': {'type': 'string', 'enum': ['add', 'edit', 'delete']}, 'number': {'type': 'integer'}, 'numbers': {'type': 'array', 'items': {'type': 'integer'}}, 'pattern': {'type': 'string'}, 'kind': {'type': 'string', 'enum': ['reply', 'reaction']}, 'responses': {'type': 'string'}}, 'required': ['action', 'number', 'numbers', 'pattern', 'kind', 'responses'], 'additionalProperties': False}
    },
    {
        'name': TOOL_CRAFT_ITEM,
        'description': "Craft a GTrade item for the sender from an image attached to their message or a link to one in it, with a name and a value in GCoin, only when they clearly ask. This only posts a confirm card.",
        'input_schema': {'type': 'object', 'properties': {'name': {'type': 'string'}, 'value': {'type': 'string'}}, 'required': ['name', 'value'], 'additionalProperties': False}
    },
    {
        'name': TOOL_DESTROY_ITEM,
        'description': "Destroy the sender's GTrade items for good, only when they clearly ask: pass every one they named, or an empty list for all of theirs, which needs no lookup first. One confirm card lists them all, and nothing happens until they press it.",
        'input_schema': {'type': 'object', 'properties': {'items': {'type': 'array', 'items': {'type': 'string'}}}, 'required': ['items'], 'additionalProperties': False}
    },
    {
        'name': TOOL_ANSWER_TRADE,
        'description': "Accept or decline GTrade offers someone made to the sender, by the item's name and that member's id or name, only when they clearly ask. An empty string for item is every offer that member made them, on one card. This only posts a confirm card.",
        'input_schema': {'type': 'object', 'properties': {'action': {'type': 'string', 'enum': ['accept', 'decline']}, 'item': {'type': 'string'}, 'other': {'type': 'string'}}, 'required': ['action', 'item', 'other'], 'additionalProperties': False}
    },
    {
        'name': TOOL_REMIND_ROLE,
        'description': "For admins: remind a role, or everyone, only when they clearly ask. Pass when as they said it, what, how it repeats (days only with repeat days, else []), and the role's name or id, or everyone. This only posts a confirm card.",
        'input_schema': {'type': 'object', 'properties': {'when': {'type': 'string'}, 'what': {'type': 'string'}, 'repeat': {'type': 'string', 'enum': REPEAT_CHOICES}, 'days': DAYS_SCHEMA, 'role': {'type': 'string'}}, 'required': ['when', 'what', 'repeat', 'days', 'role'], 'additionalProperties': False}
    },
    {
        'name': TOOL_SET_CONFIG,
        'description': "For admins: set one of GBot's settings here, only when they clearly ask: the Storms or admin channel by name, the admin or Who Dis role by name, or the prefix for prefix commands. This only posts a confirm card.",
        'input_schema': {'type': 'object', 'properties': {'setting': {'type': 'string', 'enum': ['storms_channel', 'admin_channel', 'admin_role', 'who_dis_role', 'prefix']}, 'value': {'type': 'string'}}, 'required': ['setting', 'value'], 'additionalProperties': False}
    },
    {
        'name': TOOL_REPORT,
        'description': "Report a member to this server's admins, only when the sender clearly asks, with what happened or an empty string. Their message is deleted and GBot posts a button that opens the confirm privately for them, so nobody sees who reported whom. The button is your whole reply.",
        'input_schema': {'type': 'object', 'properties': {'user': {'type': 'string'}, 'what': {'type': 'string'}}, 'required': ['user', 'what'], 'additionalProperties': False}
    },
    {
        'name': TOOL_AGENT_SETTING,
        'description': "For admins: change one of your own settings, only when they clearly ask: mode, access, images, mentions, abilities, memory_access, model, tokens, cooldown, reply_length, history, member_memories, instructions, or key. Pass a channel's name for a channel's own setting, or an empty string for the whole server. A key is never typed in chat: the card opens a private form. This only posts a confirm card.",
        'input_schema': {'type': 'object', 'properties': {'setting': {'type': 'string'}, 'value': {'type': 'string'}, 'channel': {'type': 'string'}}, 'required': ['setting', 'value', 'channel'], 'additionalProperties': False}
    },
    {
        'name': TOOL_PATREON,
        'description': "For patrons, in the GBot Patreon server only: enable GBot in a server by its ID, only when they clearly ask. This only posts a confirm card.",
        'input_schema': {'type': 'object', 'properties': {'server_id': {'type': 'string'}}, 'required': ['server_id'], 'additionalProperties': False}
    },
    {
        'name': TOOL_STAY_SILENT,
        'description': 'Send no reply to the last message. Use it only when your instructions or preferences specifically say not to answer this kind of message.',
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}
    }
]

# what the last turn is told, as tools are closed to it
LAST_TURN = "No more tools can be used for this message. Reply to them now in plain words: say what was done and what was not, and that they can ask again for the rest. Never write a tool's name."

@dataclass
class AgentResult:
    text: str = ''
    tokens: int = 0
    silent: bool = False
    refused: bool = False

class AgentKeyProblem(Exception):
    """The key, its credit or the model needs an admin's attention. Trying again won't help."""

class AgentUnavailable(Exception):
    """A passing failure: the network, a rate limit or an overloaded service."""

def newClient(apiKey):
    return anthropic.AsyncAnthropic(api_key = apiKey, timeout = REQUEST_TIMEOUT_SECONDS, max_retries = 1)

def translate(error):
    # the type only: the logs and admins need to know which kind of failure this was
    if isinstance(error, (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.BadRequestError, anthropic.NotFoundError)):
        return AgentKeyProblem(type(error).__name__)
    return AgentUnavailable(type(error).__name__)

async def isValidKey(apiKey):
    try:
        async with newClient(apiKey) as client:
            await client.models.list(limit = 1)
        return True
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
        return False
    except anthropic.AnthropicError as error:
        raise translate(error) from None

async def listModels(apiKey):
    try:
        async with newClient(apiKey) as client:
            return [model.id async for model in client.models.list() if model.id.startswith('claude-')]
    except anthropic.AnthropicError as error:
        raise translate(error) from None

async def supportsEffort(apiKey, model):
    # raises AgentKeyProblem when the key can't use this model, which is how a choice gets validated
    try:
        async with newClient(apiKey) as client:
            info = await client.models.retrieve(model)
    except anthropic.AnthropicError as error:
        raise translate(error) from None
    capabilities = info.capabilities
    return capabilities is not None and capabilities.effort is not None and capabilities.effort.supported

async def runConversation(*, apiKey, model, useEffort, system, cachedSystem, prompt, maxTokens, maxTurns, runTool, allowSilence = False, abilities = ABILITIES_OFF):
    # runTool(name, input) -> (result text, whether it failed). The loop is written out rather than
    # using the SDK's runner so that its turn limit is ours, and the last turn can't call more tools.
    result = AgentResult()
    toolRefused = False
    messages = [{'role': 'user', 'content': prompt}]
    systemBlocks = [{'type': 'text', 'text': cachedSystem, 'cache_control': {'type': 'ephemeral'}}]
    if system:
        systemBlocks.append({'type': 'text', 'text': system})
    # with nothing telling it to hold back, it has no business going quiet, so it isn't offered the choice
    hidden = set() if allowSilence else {TOOL_STAY_SILENT}
    # and it isn't told of anything its channel's level doesn't allow
    hidden |= (READ_TOOLS | ACTING_TOOLS) - toolsAllowed(abilities)
    tools = [tool for tool in TOOLS if tool['name'] not in hidden]
    request = {'model': model, 'max_tokens': maxTokens, 'system': systemBlocks, 'tools': tools}
    if useEffort:
        # chat doesn't repay deep reasoning, and thinking counts against the reply's token budget
        request['output_config'] = {'effort': 'low'}
    try:
        async with newClient(apiKey) as client:
            for turn in range(maxTurns):
                toolChoice = {'tool_choice': {'type': 'none'}} if turn == maxTurns - 1 else {}
                response = await client.messages.create(messages = messages, **request, **toolChoice)
                usage = response.usage
                # what counts against the daily limits: tokens read from the cache are billed at a tenth, so they count at a tenth
                result.tokens += usage.input_tokens + usage.output_tokens + (usage.cache_creation_input_tokens or 0) + (usage.cache_read_input_tokens or 0) // 10
                # always look before reading: a refused response has nothing to show
                if response.stop_reason == 'refusal':
                    result.refused = True
                    return result
                # the last words it wrote: having called a tool, it often has nothing left to add
                # unless a tool was refused, as words written before it may say it worked
                written = ''.join(block.text for block in response.content if block.type == 'text').strip()
                result.text = written or ('' if toolRefused else result.text)
                toolUses = [block for block in response.content if block.type == 'tool_use']
                if response.stop_reason != 'tool_use' or not toolUses:
                    return result
                toolResults = []
                toolRefused = False
                for toolUse in toolUses:
                    if toolUse.name == TOOL_STAY_SILENT and allowSilence:
                        result.silent = True
                    resultText, failed = await runTool(toolUse.name, toolUse.input)
                    toolRefused = toolRefused or failed
                    toolResults.append({'type': 'tool_result', 'tool_use_id': toolUse.id, 'content': resultText, 'is_error': failed})
                if result.silent:
                    result.text = ''
                    return result
                if turn == maxTurns - 2:
                    # the next turn can't call a tool, and unless told, it writes one out as words instead
                    toolResults.append({'type': 'text', 'text': LAST_TURN})
                messages.append({'role': 'assistant', 'content': response.content})
                messages.append({'role': 'user', 'content': toolResults})
    except anthropic.AnthropicError as error:
        # what earlier turns used was spent whatever went wrong after, so it's still counted
        problem = translate(error)
        problem.tokens = result.tokens
        raise problem from None
    return result
