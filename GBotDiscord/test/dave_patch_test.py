#region IMPORTS
import unittest
from unittest.mock import AsyncMock, MagicMock

from nextcord.gateway import DiscordVoiceWebSocket

from GBotDiscord.src.dave_patch import applyDavePrepareEpochPatch
#endregion

# nextcord's own implementation, captured before any patch is applied. Module level on purpose:
# held as a class attribute it would bind to the test instance and be called with an extra self.
PRISTINE_RECEIVED_MESSAGE = DiscordVoiceWebSocket.received_message

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/dave_patch_test.py
#   - or use the "Python: Current File" run configuration to run dave_patch_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestDavePatch(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting dave patch unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted dave patch unit tests.\n')

    def tearDown(self):
        # the patch replaces a class attribute; never leak a patched voice gateway into another suite
        DiscordVoiceWebSocket.received_message = PRISTINE_RECEIVED_MESSAGE

    def makeE2eeState(self):
        # mirrors nextcord's E2EEState: prepare_epoch is a coroutine, execute_transition is not
        e2eeState = AsyncMock()
        e2eeState.execute_transition = MagicMock()
        return e2eeState

    def makeWebsocket(self, e2eeState):
        websocket = MagicMock()
        websocket._connection.e2ee_state = e2eeState
        # nextcord awaits this when set; MagicMock's default attribute is not awaitable
        websocket._hook = None
        # nextcord's dispatcher compares the opcode against constants read off self, which on a
        # bare mock are mocks that no opcode can ever equal
        for opcodeName in ('READY', 'HEARTBEAT_ACK', 'RESUMED', 'SESSION_DESCRIPTION', 'HELLO',
                           'DAVE_PREPARE_TRANSITION', 'DAVE_EXECUTE_TRANSITION', 'CLIENTS_CONNECT', 'CLIENT_DISCONNECT'):
            setattr(websocket, opcodeName, getattr(DiscordVoiceWebSocket, opcodeName))
        return websocket

    def prepareEpochMessage(self, epoch = 1, protocolVersion = 1):
        return {'op': DiscordVoiceWebSocket.DAVE_PREPARE_EPOCH, 'd': {'epoch': epoch, 'protocol_version': protocolVersion}}

    # C-13: opcode 24 announces that a new MLS group has to be created, which is what happens when
    # the last human leaves a voice channel and comes back. Without this the bot never rejoins the
    # group and every frame it sends afterwards is undecryptable.
    async def test_prepare_epoch_is_dispatched_to_the_e2ee_state(self):
        e2eeState = self.makeE2eeState()
        websocket = self.makeWebsocket(e2eeState)
        applyDavePrepareEpochPatch()

        await DiscordVoiceWebSocket.received_message(websocket, self.prepareEpochMessage(epoch = 1, protocolVersion = 1))

        e2eeState.prepare_epoch.assert_awaited_once_with(1, 1)

    async def test_prepare_epoch_is_ignored_when_e2ee_state_is_unset(self):
        websocket = self.makeWebsocket(None)
        applyDavePrepareEpochPatch()

        # dave-py absent (has_dave False) means no E2EE state at all; the frame is simply not ours
        await DiscordVoiceWebSocket.received_message(websocket, self.prepareEpochMessage())

    async def test_other_opcodes_still_reach_nextcords_dispatcher(self):
        e2eeState = self.makeE2eeState()
        websocket = self.makeWebsocket(e2eeState)
        applyDavePrepareEpochPatch()

        await DiscordVoiceWebSocket.received_message(
            websocket, {'op': DiscordVoiceWebSocket.DAVE_EXECUTE_TRANSITION, 'd': {'transition_id': 7}})

        e2eeState.execute_transition.assert_called_once_with(7)
        e2eeState.prepare_epoch.assert_not_awaited()

    async def test_applying_the_patch_twice_dispatches_once(self):
        e2eeState = self.makeE2eeState()
        websocket = self.makeWebsocket(e2eeState)
        applyDavePrepareEpochPatch()
        applyDavePrepareEpochPatch()

        await DiscordVoiceWebSocket.received_message(websocket, self.prepareEpochMessage())

        e2eeState.prepare_epoch.assert_awaited_once()

    # canary for nextcord/nextcord#1294: this asserts the *unpatched* library still ignores opcode
    # 24, so it fails the moment a nextcord bump carries the upstream fix — which is when we want
    # to hear about it, since requirements.txt pins the version.
    async def test_nextcord_still_does_not_dispatch_prepare_epoch(self):
        e2eeState = self.makeE2eeState()
        websocket = self.makeWebsocket(e2eeState)

        await PRISTINE_RECEIVED_MESSAGE(websocket, self.prepareEpochMessage())

        self.assertFalse(
            e2eeState.prepare_epoch.await_count,
            'nextcord now dispatches DAVE_PREPARE_EPOCH itself (upstream issue #1294 is fixed), so '
            'GBot no longer needs to. Delete GBotDiscord/src/dave_patch.py, its import and call in '
            'GBotDiscord/src/main.py, this whole test suite plus its wiring in GBotDiscord/test/test.py, '
            "and the nextcord row in CLAUDE.md's \"Upstream issues we carry patches for\" register.")
