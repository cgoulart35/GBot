#region IMPORTS
import json
import unittest
from unittest.mock import ANY, MagicMock, AsyncMock, patch
import nextcord
from nextcord.ext import commands
from datetime import datetime
from werkzeug.exceptions import HTTPException

from GBotDiscord.src.config import config_queries
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.quart_api.discord_resource import Discord
#endregion

_ORIGINAL_CONFIG_QUERIES = {
    name: getattr(config_queries, name)
    for name in dir(config_queries)
    if callable(getattr(config_queries, name)) and not name.startswith('_')
}


# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/quart_api/discord_resource_test.py
#   - or use the "Python: Current File" run configuration to run discord_resource_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestDiscordResource(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting discord_resource unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted discord_resource unit tests.\n')

    def setUp(self):
        for name, fn in _ORIGINAL_CONFIG_QUERIES.items():
            setattr(config_queries, name, fn)
        self.client: nextcord.Client = commands.Bot()

    # region doc

    def test_doc_returns_expected_schema(self):
        result = Discord.doc()
        self.assertIn('options', result)
        self.assertIn('postBodyTemplate', result)
        actionNames = [a['name'] for a in result['options']['action']]
        self.assertEqual(set(actionNames), {'changePresence', 'leaveGuild', 'sendMessage', 'addReaction'})
        self.assertEqual(result['postBodyTemplate']['action']['name'], 'sendMessage')

    # endregion

    # region post — leaveGuild

    async def test_post_leaveGuild_success(self):
        GBotPropertiesManager.PATREON_GUILD_ID = 10
        GBotPropertiesManager.PATREON_IGNORE_GUILDS = [11]
        config_queries.getAllServerValues = MagicMock(return_value={'prefix': '.'})
        guild = MagicMock()
        guild.leave = AsyncMock()
        self.client.fetch_guild = AsyncMock(return_value=guild)
        data = json.dumps({'action': {'name': 'leaveGuild', 'serverId': '987654321'}})

        result = await Discord.post(self.client, data)

        config_queries.getAllServerValues.assert_called_once_with('987654321')
        self.client.fetch_guild.assert_awaited_once_with('987654321')
        guild.leave.assert_awaited_once()
        self.assertEqual(result, {'action': 'leaveGuild', 'status': 'success'})

    # Protected servers never get left automatically, so this path needs an explicit override too.
    async def test_post_leaveGuild_protected_server_needs_force(self):
        config_queries.getAllServerValues = MagicMock(return_value={'prefix': '.'})
        guild = MagicMock()
        guild.leave = AsyncMock()
        self.client.fetch_guild = AsyncMock(return_value=guild)
        with patch('GBotDiscord.src.quart_api.discord_resource.utils.getGuildsForPatreonToIgnore', return_value=[987654321]):
            for action in ({}, {'optionalForce': False}, {'optionalForce': 'true'}, {'optionalForce': 1}):
                with self.subTest(action = action):
                    data = json.dumps({'action': {'name': 'leaveGuild', 'serverId': '987654321', **action}})
                    result = await Discord.post(self.client, data)
                    self.assertEqual(result['status'], 'failure')
                    self.assertIn('"optionalForce": true', result['message'])
            guild.leave.assert_not_awaited()

            data = json.dumps({'action': {'name': 'leaveGuild', 'serverId': '987654321', 'optionalForce': True}})
            result = await Discord.post(self.client, data)
        guild.leave.assert_awaited_once()
        self.assertEqual(result, {'action': 'leaveGuild', 'status': 'success'})

    async def test_post_leaveGuild_empty_serverId_returns_invalid_request(self):
        config_queries.getAllServerValues = MagicMock()
        data = json.dumps({'action': {'name': 'leaveGuild', 'serverId': '   '}})
        result = await Discord.post(self.client, data)
        self.assertEqual(result, {'status': 'error', 'message': 'Error: Invalid request.'})
        config_queries.getAllServerValues.assert_not_called()

    async def test_post_leaveGuild_unknown_server_returns_invalid_request(self):
        config_queries.getAllServerValues = MagicMock(return_value=None)
        self.client.fetch_guild = AsyncMock()
        data = json.dumps({'action': {'name': 'leaveGuild', 'serverId': '987654321'}})
        result = await Discord.post(self.client, data)
        self.assertEqual(result, {'status': 'error', 'message': 'Error: Invalid request.'})
        self.client.fetch_guild.assert_not_awaited()

    # endregion

    # region post — sendMessage

    async def test_post_sendMessage_without_reply(self):
        channel = MagicMock()
        channel.send = AsyncMock()
        self.client.fetch_channel = AsyncMock(return_value=channel)
        data = json.dumps({'action': {
            'name': 'sendMessage',
            'message': 'Hello world!',
            'channelId': '1111',
        }})

        result = await Discord.post(self.client, data)

        self.client.fetch_channel.assert_awaited_once_with('1111')
        channel.send.assert_awaited_once_with('Hello world!', allowed_mentions = ANY)
        self.assertTrue(channel.send.call_args.kwargs['allowed_mentions'].everyone)
        self.assertEqual(result, {'action': 'sendMessage', 'status': 'success'})

    async def test_post_sendMessage_with_reply(self):
        replyTarget = MagicMock()
        channel = MagicMock()
        channel.send = AsyncMock()
        channel.fetch_message = AsyncMock(return_value=replyTarget)
        self.client.fetch_channel = AsyncMock(return_value=channel)
        data = json.dumps({'action': {
            'name': 'sendMessage',
            'message': 'Hello world!',
            'channelId': '1111',
            'optionalMessageIdForReply': '2222',
        }})

        result = await Discord.post(self.client, data)

        channel.fetch_message.assert_awaited_once_with('2222')
        channel.send.assert_awaited_once_with('Hello world!', reference=replyTarget, allowed_mentions = ANY)
        self.assertEqual(result, {'action': 'sendMessage', 'status': 'success'})

    # endregion

    # region post — changePresence

    def _stubPresenceCog(self, *, result=True):
        presence = MagicMock()
        presence.changePresence = AsyncMock(return_value=result)
        self.client.get_cog = MagicMock(return_value=presence)
        return presence

    def reactionSetup(self, emojis = ()):
        message = MagicMock()
        message.add_reaction = AsyncMock()
        channel = MagicMock()
        channel.guild.emojis = list(emojis)
        channel.fetch_message = AsyncMock(return_value = message)
        self.client.fetch_channel = AsyncMock(return_value = channel)
        return channel, message

    def reactionBody(self, emoji):
        return json.dumps({'action': {'name': 'addReaction', 'channelId': '1111', 'messageId': '2222', 'emoji': emoji}})

    async def test_post_addReaction_finds_a_custom_emoji_by_name(self):
        customEmoji = MagicMock()
        customEmoji.name = 'gbot'
        channel, message = self.reactionSetup([customEmoji])

        for given in ('gbot', ':gbot:'):
            message.add_reaction.reset_mock()
            result = await Discord.post(self.client, self.reactionBody(given))
            message.add_reaction.assert_awaited_once_with(customEmoji)
            self.assertEqual(result, {'action': 'addReaction', 'status': 'success'})
        self.client.fetch_channel.assert_awaited_with('1111')
        channel.fetch_message.assert_awaited_with('2222')

    async def test_post_addReaction_passes_other_emoji_as_written(self):
        _, message = self.reactionSetup()
        for given in ('🎃', '<:gbot:123>'):
            message.add_reaction.reset_mock()
            result = await Discord.post(self.client, self.reactionBody(given))
            message.add_reaction.assert_awaited_once_with(given)
            self.assertEqual(result, {'action': 'addReaction', 'status': 'success'})

    async def test_post_addReaction_works_without_a_server(self):
        message = MagicMock()
        message.add_reaction = AsyncMock()
        channel = MagicMock(spec = ['fetch_message'])
        channel.fetch_message = AsyncMock(return_value = message)
        self.client.fetch_channel = AsyncMock(return_value = channel)
        await Discord.post(self.client, self.reactionBody('🎃'))
        message.add_reaction.assert_awaited_once_with('🎃')

    async def test_post_addReaction_reports_what_discord_refuses(self):
        _, message = self.reactionSetup()
        response = MagicMock(status = 400, reason = 'Bad Request')
        message.add_reaction = AsyncMock(side_effect = nextcord.HTTPException(response, {'code': 10014, 'message': 'Unknown Emoji'}))
        result = await Discord.post(self.client, self.reactionBody('nope'))
        self.assertEqual(result, {'action': 'addReaction', 'status': 'failure', 'message': 'Error: Unknown Emoji'})

    async def test_post_addReaction_missing_field_returns_invalid_request(self):
        data = json.dumps({'action': {'name': 'addReaction', 'channelId': '1111', 'emoji': 'gbot'}})
        result = await Discord.post(self.client, data)
        self.assertEqual(result, {'status': 'error', 'message': 'Error: Invalid request.'})

    async def test_post_changePresence_playing_with_expire(self):
        presence = self._stubPresenceCog()
        data = json.dumps({'action': {
            'name': 'changePresence',
            'type': 'playing',
            'value': 'GBot 1.2.3',
            'expire': '01/02/26 03:04:05 PM',
        }})

        result = await Discord.post(self.client, data)

        presence.changePresence.assert_awaited_once()
        activity, expire = presence.changePresence.call_args[0]
        self.assertIsInstance(activity, nextcord.Game)
        self.assertEqual(activity.name, 'GBot 1.2.3')
        self.assertEqual(expire, datetime(2026, 1, 2, 15, 4, 5))
        self.assertEqual(result['action'], 'changePresence')
        # the presence text alone, not the whole request body
        self.assertIn("Presence set to: 'playing GBot 1.2.3'", result['message'])
        self.assertEqual(result['status'], 'success')
        self.assertIn('until 01/02/26 03:04:05 PM', result['message'])

    async def test_post_changePresence_listening_without_expire(self):
        presence = self._stubPresenceCog()
        data = json.dumps({'action': {
            'name': 'changePresence',
            'type': 'listening',
            'value': 'music',
        }})

        result = await Discord.post(self.client, data)

        activity, expire = presence.changePresence.call_args[0]
        self.assertIsInstance(activity, nextcord.Activity)
        self.assertEqual(activity.type, nextcord.ActivityType.listening)
        self.assertEqual(activity.name, 'music')
        self.assertIsNone(expire)
        self.assertEqual(result['status'], 'success')
        self.assertNotIn('until', result['message'])

    async def test_post_changePresence_watching_without_expire(self):
        presence = self._stubPresenceCog()
        data = json.dumps({'action': {
            'name': 'changePresence',
            'type': 'watching',
            'value': 'a movie',
        }})

        result = await Discord.post(self.client, data)

        activity, _ = presence.changePresence.call_args[0]
        self.assertEqual(activity.type, nextcord.ActivityType.watching)
        self.assertEqual(activity.name, 'a movie')
        self.assertEqual(result['status'], 'success')

    async def test_post_changePresence_invalid_expire_returns_failure(self):
        self._stubPresenceCog()
        data = json.dumps({'action': {
            'name': 'changePresence',
            'type': 'playing',
            'value': 'x',
            'expire': 'not-a-datetime',
        }})

        result = await Discord.post(self.client, data)

        self.assertEqual(result['action'], 'changePresence')
        self.assertEqual(result['status'], 'failure')
        self.assertIn('Invalid expire', result['message'])

    async def test_post_changePresence_invalid_type_returns_failure(self):
        self._stubPresenceCog()
        data = json.dumps({'action': {
            'name': 'changePresence',
            'type': 'streaming',
            'value': 'x',
        }})

        result = await Discord.post(self.client, data)

        self.assertEqual(result['status'], 'failure')
        self.assertIn('Invalid type', result['message'])

    async def test_post_changePresence_failure_when_presence_returns_false(self):
        self._stubPresenceCog(result=False)
        data = json.dumps({'action': {
            'name': 'changePresence',
            'type': 'playing',
            'value': 'x',
        }})

        result = await Discord.post(self.client, data)

        self.assertEqual(result['status'], 'failure')
        self.assertIn('Unable to change presence', result['message'])

    # endregion

    # region error & unhandled branches

    async def test_post_unknown_action_returns_invalid_request(self):
        data = json.dumps({'action': {'name': 'somethingElse'}})
        result = await Discord.post(self.client, data)
        self.assertEqual(result, {'status': 'error', 'message': 'Error: Invalid request.'})

    async def test_post_invalid_json_aborts_400(self):
        with self.assertRaises(HTTPException) as cm:
            await Discord.post(self.client, 'not-json')
        self.assertEqual(cm.exception.code, 400)

    # endregion


if __name__ == '__main__':
    unittest.main()
