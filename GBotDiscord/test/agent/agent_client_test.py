#region IMPORTS
import json
import unittest
from unittest.mock import AsyncMock, patch

import anthropic
import httpx2

from GBotDiscord.src.agent import agent_client
#endregion

KEY = 'sk-ant-the-real-secret'

def message(content, stopReason = 'end_turn', inputTokens = 10, outputTokens = 5, cacheRead = None):
    usage = {'input_tokens': inputTokens, 'output_tokens': outputTokens}
    if cacheRead is not None:
        usage['cache_read_input_tokens'] = cacheRead
    return {'id': 'msg_1', 'type': 'message', 'role': 'assistant', 'model': 'claude-x', 'content': content, 'stop_reason': stopReason, 'stop_sequence': None, 'usage': usage}

def text(value):
    return {'type': 'text', 'text': value}

def tool(name, toolInput = None, toolId = 'tool_1'):
    return {'type': 'tool_use', 'id': toolId, 'name': name, 'input': toolInput or {}}

def error(status, kind):
    return httpx2.Response(status, json = {'type': 'error', 'error': {'type': kind, 'message': 'nope'}})

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/agent/agent_client_test.py
class TestAgentClient(unittest.IsolatedAsyncioTestCase):

    # The real SDK over a fake network, so requests and responses are what it really builds and parses.
    def useResponses(self, *responses):
        self.requests = []
        remaining = list(responses)
        def handler(request):
            self.requests.append(request)
            response = remaining.pop(0)
            return response if isinstance(response, httpx2.Response) else httpx2.Response(200, json = response)
        def newClient(apiKey):
            return anthropic.AsyncAnthropic(api_key = apiKey, max_retries = 0, http_client = anthropic.DefaultAsyncHttpxClient(transport = httpx2.MockTransport(handler)))
        patcher = patch.object(agent_client, 'newClient', newClient)
        patcher.start()
        self.addCleanup(patcher.stop)

    def bodies(self):
        return [json.loads(request.content) for request in self.requests]

    async def run_(self, runTool = None, maxTurns = 3, useEffort = True, allowSilence = True):
        return await agent_client.runConversation(apiKey = KEY, model = 'claude-x', useEffort = useEffort, cachedSystem = 'rules', system = 'memories', prompt = 'hello', maxTokens = 100, maxTurns = maxTurns, runTool = runTool or AsyncMock(return_value = ('ok', False)), allowSilence = allowSilence)

    def test_newClient_keeps_the_key_out_of_retries_and_sets_a_timeout(self):
        client = anthropic.AsyncAnthropic(api_key = KEY)
        self.assertEqual(client.api_key, KEY)
        real = agent_client.anthropic.AsyncAnthropic
        with patch.object(agent_client.anthropic, 'AsyncAnthropic', side_effect = real) as constructor:
            agent_client.newClient(KEY)
        self.assertEqual(constructor.call_args.kwargs, {'api_key': KEY, 'timeout': agent_client.REQUEST_TIMEOUT_SECONDS, 'max_retries': 1})

    async def test_a_plain_reply(self):
        self.useResponses(message([text(' hi there ')], inputTokens = 10, outputTokens = 5, cacheRead = 7))
        result = await self.run_()
        self.assertEqual((result.text, result.tokens, result.silent, result.refused), ('hi there', 22, False, False))
        body = self.bodies()[0]
        self.assertEqual(body['model'], 'claude-x')
        self.assertEqual(body['max_tokens'], 100)
        self.assertEqual(body['output_config'], {'effort': 'low'})
        self.assertEqual(body['messages'], [{'role': 'user', 'content': 'hello'}])
        self.assertEqual(body['system'][0], {'type': 'text', 'text': 'rules', 'cache_control': {'type': 'ephemeral'}})
        self.assertEqual(body['system'][1], {'type': 'text', 'text': 'memories'})
        self.assertEqual({tool['name'] for tool in body['tools']}, {'react', 'save_memory', 'update_memory', 'forget_memory', 'get_leaderboard', 'get_wallet', 'get_market', 'get_music_queue', 'stay_silent'})
        self.assertNotIn('tool_choice', body)

    async def test_effort_is_left_out_for_a_model_without_it(self):
        self.useResponses(message([text('hi')]))
        await self.run_(useEffort = False)
        self.assertNotIn('output_config', self.bodies()[0])

    async def test_system_without_memories(self):
        self.useResponses(message([text('hi')]))
        await agent_client.runConversation(apiKey = KEY, model = 'm', useEffort = True, cachedSystem = 'rules', system = '', prompt = 'p', maxTokens = 1, maxTurns = 1, runTool = AsyncMock())
        self.assertEqual(len(self.bodies()[0]['system']), 1)

    async def test_the_only_tools_are_the_ones_we_wrote(self):
        self.assertEqual([tool['name'] for tool in agent_client.TOOLS], ['react', 'save_memory', 'update_memory', 'forget_memory', 'get_leaderboard', 'get_wallet', 'get_market', 'get_music_queue', 'play_music', 'control_music', 'stay_silent'])
        for definition in agent_client.TOOLS:
            self.assertTrue(definition['strict'])
            self.assertFalse(definition['input_schema']['additionalProperties'])

    async def test_a_tool_runs_and_its_result_goes_back(self):
        self.useResponses(message([tool('react', {'emoji': '👍'})], 'tool_use'), message([text('done')]))
        runTool = AsyncMock(return_value = ('Reacted.', False))
        result = await self.run_(runTool)
        runTool.assert_awaited_once_with('react', {'emoji': '👍'})
        self.assertEqual(result.text, 'done')
        self.assertEqual(result.tokens, 30)
        second = self.bodies()[1]['messages']
        self.assertEqual(second[1]['role'], 'assistant')
        self.assertEqual(second[2]['content'], [{'type': 'tool_result', 'tool_use_id': 'tool_1', 'content': 'Reacted.', 'is_error': False}])

    async def test_a_refused_tool_is_reported_as_an_error(self):
        self.useResponses(message([tool('save_memory', {'text': 'x'})], 'tool_use'), message([text('sorry')]))
        await self.run_(AsyncMock(return_value = ('Only admins.', True)))
        self.assertTrue(self.bodies()[1]['messages'][2]['content'][0]['is_error'])

    async def test_stay_silent_ends_it_with_no_text_but_counts_tokens(self):
        self.useResponses(message([text('thinking aloud'), tool('stay_silent')], 'tool_use'))
        result = await self.run_()
        self.assertTrue(result.silent)
        self.assertEqual(result.text, '')
        self.assertEqual(result.tokens, 15)
        self.assertEqual(len(self.requests), 1)

    async def test_silence_is_not_offered_unless_allowed(self):
        self.useResponses(message([text('hi')]))
        await self.run_(allowSilence = False)
        self.assertEqual({tool['name'] for tool in self.bodies()[0]['tools']}, {'react', 'save_memory', 'update_memory', 'forget_memory', 'get_leaderboard', 'get_wallet', 'get_market', 'get_music_queue'})

    async def test_words_written_beside_a_tool_call_survive_an_empty_last_turn(self):
        self.useResponses(message([text('Use /music skip'), tool('react', {'emoji': '👍'})], 'tool_use'), message([]))
        result = await self.run_()
        self.assertEqual(result.text, 'Use /music skip')

    async def test_later_words_replace_earlier_ones(self):
        self.useResponses(message([text('Let me check'), tool('get_market', {})], 'tool_use'), message([text('Nothing for sale')]))
        result = await self.run_()
        self.assertEqual(result.text, 'Nothing for sale')

    async def test_music_tools_are_only_offered_when_turned_on(self):
        self.useResponses(message([text('hi')]), message([text('hi')]))
        await self.run_()
        await agent_client.runConversation(apiKey = KEY, model = 'm', useEffort = True, cachedSystem = 'rules', system = '', prompt = 'p', maxTokens = 1, maxTurns = 1, runTool = AsyncMock(), allowMusic = True)
        first, second = self.bodies()
        self.assertNotIn('play_music', {tool['name'] for tool in first['tools']})
        self.assertNotIn('control_music', {tool['name'] for tool in first['tools']})
        self.assertLessEqual({'play_music', 'control_music'}, {tool['name'] for tool in second['tools']})

    async def test_asking_for_silence_when_not_offered_does_not_silence_it(self):
        self.useResponses(message([tool('stay_silent')], 'tool_use'), message([text('hello')]))
        result = await self.run_(allowSilence = False)
        self.assertFalse(result.silent)
        self.assertEqual(result.text, 'hello')

    async def test_the_last_turn_cannot_call_tools(self):
        self.useResponses(message([tool('react', {'emoji': '👍'})], 'tool_use'), message([text('done')]))
        result = await self.run_(maxTurns = 2)
        self.assertEqual(result.text, 'done')
        bodies = self.bodies()
        self.assertNotIn('tool_choice', bodies[0])
        self.assertEqual(bodies[1]['tool_choice'], {'type': 'none'})

    async def test_the_loop_stops_at_the_turn_limit(self):
        self.useResponses(message([tool('react', {'emoji': '👍'})], 'tool_use'), message([tool('react', {'emoji': '👍'})], 'tool_use'))
        result = await self.run_(maxTurns = 2)
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(result.text, '')

    async def test_tool_use_stop_with_no_tool_block_finishes(self):
        self.useResponses(message([text('odd')], 'tool_use'))
        self.assertEqual((await self.run_()).text, 'odd')

    async def test_a_refusal_has_no_text(self):
        self.useResponses(message([], 'refusal'))
        result = await self.run_()
        self.assertTrue(result.refused)
        self.assertEqual(result.tokens, 15)

    async def test_failures_are_sorted_without_any_detail(self):
        for status, kind, expected in ((401, 'authentication_error', agent_client.AgentKeyProblem), (403, 'permission_error', agent_client.AgentKeyProblem), (400, 'invalid_request_error', agent_client.AgentKeyProblem), (404, 'not_found_error', agent_client.AgentKeyProblem), (429, 'rate_limit_error', agent_client.AgentUnavailable), (529, 'overloaded_error', agent_client.AgentUnavailable)):
            with self.subTest(status = status):
                self.useResponses(error(status, kind))
                with self.assertRaises(expected) as caught:
                    await self.run_()
                self.assertNotIn(KEY, str(caught.exception))
                self.assertNotIn('nope', str(caught.exception))

    async def test_isValidKey(self):
        self.useResponses(httpx2.Response(200, json = {'data': [], 'has_more': False, 'first_id': None, 'last_id': None}))
        self.assertTrue(await agent_client.isValidKey(KEY))
        self.assertIn(KEY, str(self.requests[0].headers.get('x-api-key')) + str(self.requests[0].headers.get('authorization')))
        for status, kind in ((401, 'authentication_error'), (403, 'permission_error')):
            self.useResponses(error(status, kind))
            self.assertFalse(await agent_client.isValidKey(KEY))
        self.useResponses(error(529, 'overloaded_error'))
        with self.assertRaises(agent_client.AgentUnavailable):
            await agent_client.isValidKey(KEY)

    async def test_listModels_keeps_only_claude(self):
        def model(name):
            return {'id': name, 'type': 'model', 'display_name': name, 'created_at': '2026-01-01T00:00:00Z'}
        self.useResponses(httpx2.Response(200, json = {'data': [model('claude-a'), model('other'), model('claude-b')], 'has_more': False, 'first_id': 'claude-a', 'last_id': 'claude-b'}))
        self.assertEqual(await agent_client.listModels(KEY), ['claude-a', 'claude-b'])
        self.useResponses(error(401, 'authentication_error'))
        with self.assertRaises(agent_client.AgentKeyProblem):
            await agent_client.listModels(KEY)

    async def test_supportsEffort_reads_the_real_capabilities(self):
        base = {'id': 'claude-a', 'type': 'model', 'display_name': 'a', 'created_at': '2026-01-01T00:00:00Z'}
        self.useResponses(httpx2.Response(200, json = base))
        self.assertFalse(await agent_client.supportsEffort(KEY, 'claude-a'))
        supported = {'supported': True}
        unsupported = {'supported': False}
        effort = {'supported': True, 'low': supported, 'medium': supported, 'high': supported, 'max': supported, 'xhigh': supported}
        capabilities = {'batch': supported, 'citations': supported, 'code_execution': supported, 'context_management': {'supported': True}, 'image_input': supported, 'pdf_input': supported, 'structured_outputs': supported, 'thinking': {'supported': True, 'types': {'adaptive': supported, 'enabled': unsupported}}, 'effort': effort}
        self.useResponses(httpx2.Response(200, json = {**base, 'capabilities': capabilities}))
        self.assertTrue(await agent_client.supportsEffort(KEY, 'claude-a'))
        self.useResponses(error(404, 'not_found_error'))
        with self.assertRaises(agent_client.AgentKeyProblem):
            await agent_client.supportsEffort(KEY, 'claude-a')
