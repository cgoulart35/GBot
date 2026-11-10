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
# safe: doing what the sender could do themselves, which moves no money and changes nothing of anyone else's
TOOL_PLAY_MUSIC = 'play_music'
TOOL_CONTROL_MUSIC = 'control_music'
TOOL_SET_REMINDER = 'set_reminder'
TOOL_DELETE_REMINDER = 'delete_reminder'
TOOL_GUESS_STORM = 'guess_storm'
MUSIC_ACTIONS = ['skip', 'pause', 'resume', 'stop', 'shuffle']
# all: what moves GCoin or items or changes the server's settings. Each only posts a confirm card, and
# nothing happens until the sender presses it.
TOOL_SEND_GCOIN = 'send_gcoin'
TOOL_BUY_ITEM = 'buy_item'
TOOL_SELL_ITEM = 'sell_item'
TOOL_SET_FEATURE = 'set_feature'
TOOL_BET_STORM = 'bet_storm'
# the features the agent can switch: not itself, as nothing acting on the agent's own settings goes through it
SWITCHABLE_FEATURES = ['GCoin', 'GTrade', 'Hype', 'Music', 'Reminders', 'Storms', 'Who Dis', 'Legacy Prefix Command']

# What the agent may do in a channel, set by admins. Each level adds to the one before it, and only a
# level's tools are sent to Claude, so it can't be talked into one it wasn't given.
ABILITIES_OFF = 'off'
ABILITIES_READ = 'read'
ABILITIES_SAFE = 'safe'
ABILITIES_ALL = 'all'
ABILITIES = [ABILITIES_OFF, ABILITIES_READ, ABILITIES_SAFE, ABILITIES_ALL]
READ_TOOLS = {TOOL_GET_WALLET, TOOL_GET_RANKING, TOOL_SEARCH_MARKET, TOOL_GET_ITEMS, TOOL_SHOW_ITEM, TOOL_GET_MUSIC_QUEUE, TOOL_GET_FEATURES, TOOL_GET_REMINDERS}
SAFE_TOOLS = {TOOL_PLAY_MUSIC, TOOL_CONTROL_MUSIC, TOOL_SET_REMINDER, TOOL_DELETE_REMINDER, TOOL_GUESS_STORM}
ALL_TOOLS = {TOOL_SEND_GCOIN, TOOL_BUY_ITEM, TOOL_SELL_ITEM, TOOL_SET_FEATURE, TOOL_BET_STORM}
ACTING_TOOLS = SAFE_TOOLS | ALL_TOOLS

# The API allows at most 20 strict tools in a request, and every level has to fit. The read lookups
# aren't strict, as their code checks what it's given anyway; whatever changes something stays strict.
MAX_STRICT_TOOLS = 20

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
        'description': 'Set the time zone of the sender of the last message, only when they say where they are or ask you to set it, never anyone else\'s. Pass an IANA name like America/Denver. Their reminders move with it. The result says whether it worked.',
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'zone': {'type': 'string'}}, 'required': ['zone'], 'additionalProperties': False}
    },
    {
        'name': TOOL_GET_WALLET,
        'description': "Look up one member's GCoin balance. Pass their id from <people> or their name, or an empty string for the sender.",
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
        'description': "Look up the sender's own reminders in this server, with their ids.",
        'input_schema': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}
    },
    {
        'name': TOOL_PLAY_MUSIC,
        'description': "Play or queue a song for the sender of the last message, by a search or a link, only when they clearly ask you to. The result says whether it worked.",
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
        'description': "Set a reminder for the sender of the last message, only when they clearly ask for one. Pass when as they said it, like \"in 2 hours\", \"tomorrow 9am\" or \"Thursday 8pm\", what to remind them of, repeat as once, daily or weekly, and where as here or dm. The result says whether it worked.",
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'when': {'type': 'string'}, 'what': {'type': 'string'}, 'repeat': {'type': 'string', 'enum': ['once', 'daily', 'weekly']}, 'where': {'type': 'string', 'enum': ['here', 'dm']}}, 'required': ['when', 'what', 'repeat', 'where'], 'additionalProperties': False}
    },
    {
        'name': TOOL_DELETE_REMINDER,
        'description': "Delete one of the sender's own reminders here, by its id from get_reminders, only when they clearly ask you to.",
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'id': {'type': 'string'}}, 'required': ['id'], 'additionalProperties': False}
    },
    {
        'name': TOOL_SEND_GCOIN,
        'description': "Ask the sender of the last message to confirm sending GCoin to a member, only when they clearly ask to send it. Pass the member's id from <people> or their name, the amount, and a short note or an empty string. This only posts a confirm card: nothing is sent until they press it.",
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'user': {'type': 'string'}, 'amount': {'type': 'string'}, 'note': {'type': 'string'}}, 'required': ['user', 'amount', 'note'], 'additionalProperties': False}
    },
    {
        'name': TOOL_BUY_ITEM,
        'description': "Ask the sender of the last message to confirm buying a GTrade item from the member who owns it, only when they clearly ask to buy it. Pass the item's exact name and the owner's id or name. This only posts a confirm card.",
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'item': {'type': 'string'}, 'owner': {'type': 'string'}}, 'required': ['item', 'owner'], 'additionalProperties': False}
    },
    {
        'name': TOOL_SELL_ITEM,
        'description': "Ask the sender of the last message to confirm selling one of their GTrade items, only when they clearly ask: on the market, with an empty string for buyer, or offered to one member by their id or name. Pass the item's exact name. On the market, asking again takes it off. This only posts a confirm card.",
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'item': {'type': 'string'}, 'buyer': {'type': 'string'}}, 'required': ['item', 'buyer'], 'additionalProperties': False}
    },
    {
        'name': TOOL_SET_FEATURE,
        'description': "Ask an admin to confirm turning one of GBot's features on or off in this server, only when they clearly ask. This only posts a confirm card.",
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'feature': {'type': 'string', 'enum': SWITCHABLE_FEATURES}, 'setting': {'type': 'string', 'enum': ['on', 'off']}}, 'required': ['feature', 'setting'], 'additionalProperties': False}
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
        'name': TOOL_STAY_SILENT,
        'description': 'Send no reply to the last message. Use it only when your instructions or preferences specifically say not to answer this kind of message.',
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}
    }
]

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
                result.tokens += usage.input_tokens + usage.output_tokens + (usage.cache_creation_input_tokens or 0) + (usage.cache_read_input_tokens or 0)
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
                messages.append({'role': 'assistant', 'content': response.content})
                messages.append({'role': 'user', 'content': toolResults})
    except anthropic.AnthropicError as error:
        raise translate(error) from None
    return result
