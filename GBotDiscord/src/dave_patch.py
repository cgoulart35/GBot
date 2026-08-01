#region IMPORTS
import logging
from nextcord.gateway import DiscordVoiceWebSocket
#endregion

# C-13: nextcord never dispatches voice opcode 24, DAVE_PREPARE_EPOCH.
#
# nextcord 3.2.0 (and master, checked 2026-07-30) declares the opcode and implements its handler,
# E2EEState.prepare_epoch — but gateway.py's received_message only branches on opcodes 21, 22, 11
# and 13, so prepare_epoch's single caller is initialise(), which runs once per connect from
# SESSION_DESCRIPTION. Discord sends opcode 24 with epoch = 1 whenever a new MLS group has to be
# created mid-session, which is exactly what happens when the last human leaves a voice channel
# (the call drops to passthrough) and then comes back (it re-upgrades to E2EE). Without the
# handler GBot never re-creates its group and never sends a key package (opcode 26), so it stays
# outside the group while every frame it sends is encrypted for an epoch nobody else is on: the
# bot reports that it is playing and the channel hears silence. mls_proposals is also the one MLS
# handler with no recovery path, so the session never self-heals — the failure lasts until the
# voice client is torn down.
#
# 3.2.0 is the newest release, so there is nothing to bump to. Delete this module once nextcord
# dispatches the opcode itself; test_nextcord_still_does_not_dispatch_prepare_epoch is the canary
# that fails when that happens.

logger = logging.getLogger()

def applyDavePrepareEpochPatch():
    if getattr(DiscordVoiceWebSocket.received_message, 'isGBotDavePrepareEpochPatch', False):
        return

    originalReceivedMessage = DiscordVoiceWebSocket.received_message

    async def receivedMessageWithPrepareEpoch(self, msg):
        # delegate first so nextcord's own bookkeeping (seq_ack, the message hook) keeps its
        # ordering; opcode 24 reaches none of its branches, so nothing is handled twice
        await originalReceivedMessage(self, msg)

        if msg['op'] != DiscordVoiceWebSocket.DAVE_PREPARE_EPOCH:
            return
        e2eeState = self._connection.e2ee_state
        if e2eeState is None:
            return

        data = msg['d']
        epoch = data['epoch']
        protocolVersion = data['protocol_version']
        logger.info(f'GBot preparing DAVE MLS epoch {epoch} for protocol version {protocolVersion}.')
        await e2eeState.prepare_epoch(epoch, protocolVersion)

    receivedMessageWithPrepareEpoch.isGBotDavePrepareEpochPatch = True
    DiscordVoiceWebSocket.received_message = receivedMessageWithPrepareEpoch
