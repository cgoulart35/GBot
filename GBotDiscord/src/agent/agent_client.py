#region IMPORTS
from dataclasses import dataclass

import anthropic
#endregion

# The only file that knows the agent runs on Claude, so another provider could sit beside it later.
# It holds no permissions: every tool call goes through the runTool the cog passes in, which is where
# Discord roles get checked. Nothing here decides what anyone is allowed to do.

DEFAULT_MODEL = 'claude-haiku-5-5'
REQUEST_TIMEOUT_SECONDS = 60.0

TOOL_REACT = 'react'
TOOL_SAVE_MEMORY = 'save_memory'
TOOL_UPDATE_MEMORY = 'update_memory'
TOOL_FORGET_MEMORY = 'forget_memory'
TOOL_GET_LEADERBOARD = 'get_leaderboard'
TOOL_GET_WALLET = 'get_wallet'
TOOL_GET_MARKET = 'get_market'
TOOL_GET_MUSIC_QUEUE = 'get_music_queue'
TOOL_PLAY_MUSIC = 'play_music'
TOOL_CONTROL_MUSIC = 'control_music'
MUSIC_ACTIONS = ['skip', 'pause', 'resume', 'stop', 'shuffle']
TOOL_STAY_SILENT = 'stay_silent'

TOOLS = [
    {
        'name': TOOL_REACT,
        'description': 'Add an emoji reaction to the last message. Pass one normal emoji, or one of this server\'s custom emoji as <:name:id>.',
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'emoji': {'type': 'string'}}, 'required': ['emoji'], 'additionalProperties': False}
    },
    {
        'name': TOOL_SAVE_MEMORY,
        'description': 'Remember something for later, only when the sender of the last message clearly asks you to remember it or keep doing it from now on. The result says whether it was allowed.',
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'text': {'type': 'string'}}, 'required': ['text'], 'additionalProperties': False}
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
        'name': TOOL_GET_LEADERBOARD,
        'description': 'Look up the top GCoin balances and game wins among this server\'s members.',
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}
    },
    {
        'name': TOOL_GET_WALLET,
        'description': 'Look up one member\'s GCoin balance. Pass their id from <people> or their name, or an empty string for the sender.',
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'user': {'type': 'string'}}, 'required': ['user'], 'additionalProperties': False}
    },
    {
        'name': TOOL_GET_MARKET,
        'description': 'Look up the items for sale on this server\'s GTrade market.',
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}
    },
    {
        'name': TOOL_GET_MUSIC_QUEUE,
        'description': 'Look up what is playing and what is queued in this server.',
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}
    },
    {
        'name': TOOL_PLAY_MUSIC,
        'description': 'Play or queue a song for the sender of the last message, by a search or a link, only when they clearly ask you to. The result says whether it worked.',
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'query': {'type': 'string'}}, 'required': ['query'], 'additionalProperties': False}
    },
    {
        'name': TOOL_CONTROL_MUSIC,
        'description': 'Control the music, only when the sender of the last message clearly asks you to. The result says whether it worked.',
        'strict': True,
        'input_schema': {'type': 'object', 'properties': {'action': {'type': 'string', 'enum': MUSIC_ACTIONS}}, 'required': ['action'], 'additionalProperties': False}
    },
    {
        'name': TOOL_STAY_SILENT,
        'description': 'Send no reply to the last message. Use it when your instructions or preferences mean you should not answer.',
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

async def runConversation(*, apiKey, model, useEffort, system, cachedSystem, prompt, maxTokens, maxTurns, runTool, allowSilence = False, allowMusic = False):
    # runTool(name, input) -> (result text, whether it failed). The loop is written out rather than
    # using the SDK's runner so that its turn limit is ours, and the last turn can't call more tools.
    result = AgentResult()
    messages = [{'role': 'user', 'content': prompt}]
    systemBlocks = [{'type': 'text', 'text': cachedSystem, 'cache_control': {'type': 'ephemeral'}}]
    if system:
        systemBlocks.append({'type': 'text', 'text': system})
    # with nothing telling it to hold back, it has no business going quiet, so it isn't offered the choice
    hidden = set() if allowSilence else {TOOL_STAY_SILENT}
    # an admin has to turn these on, and until then it shouldn't know it could ask
    if not allowMusic:
        hidden |= {TOOL_PLAY_MUSIC, TOOL_CONTROL_MUSIC}
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
                result.text = ''.join(block.text for block in response.content if block.type == 'text').strip()
                toolUses = [block for block in response.content if block.type == 'tool_use']
                if response.stop_reason != 'tool_use' or not toolUses:
                    return result
                toolResults = []
                for toolUse in toolUses:
                    if toolUse.name == TOOL_STAY_SILENT and allowSilence:
                        result.silent = True
                    resultText, failed = await runTool(toolUse.name, toolUse.input)
                    toolResults.append({'type': 'tool_result', 'tool_use_id': toolUse.id, 'content': resultText, 'is_error': failed})
                if result.silent:
                    result.text = ''
                    return result
                messages.append({'role': 'assistant', 'content': response.content})
                messages.append({'role': 'user', 'content': toolResults})
    except anthropic.AnthropicError as error:
        raise translate(error) from None
    return result
