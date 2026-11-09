#region IMPORTS
import logging
from datetime import datetime, timedelta, timezone

from GBotDiscord.src import utils
from GBotDiscord.src.patreon import patreon_queries
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

# May this server use GBot, and why: the ignore list, then Patreon, then a free trial. A trial that
# ends, or a subscription that lapses, gets GRACE_DAYS before GBot leaves, during which commands ask
# to subscribe and what GBot does on its own stops. Commands,
# button presses and the daily Patreon check all ask here. The functions that read the database
# are synchronous and run on GBotFirebaseService's worker.

IGNORED = 'ignored'
SUBSCRIBED = 'subscribed'
TRIAL = 'trial'
# the trial is over: commands ask to subscribe, while GBot stays for GRACE_DAYS
ENDED = 'ended'
# its patron lost the role, or left the Patreon server: the same as ENDED, until the daily Patreon
# check removes the patron after the grace days
LAPSED = 'lapsed'
# the grace days are over too, so the daily Patreon check leaves
EXPIRED = 'expired'
NONE = 'none'

ALLOWED = (IGNORED, SUBSCRIBED, TRIAL)
# refused with how to subscribe, and a press on a card or game opened before still works
GRACE = (ENDED, LAPSED)
LEAVES = (EXPIRED, NONE)

# the reminders a trial sends to the server's admins, by how much of it is left
REMINDER_TWO_DAYS = 2
REMINDER_LAST_DAY = 1
REMINDER_ENDED = 0

def utcNow():
    return datetime.now(timezone.utc)

def trialEnds(trial):
    return datetime.fromisoformat(trial['started']) + timedelta(days = GBotPropertiesManager.TRIAL_DAYS)

def graceEnds(trial):
    return trialEnds(trial) + timedelta(days = GBotPropertiesManager.GRACE_DAYS)

def lapseEnds(patron):
    return datetime.fromisoformat(patron['lapsed']) + timedelta(days = GBotPropertiesManager.GRACE_DAYS)

def subscribedServerIds(patrons):
    return {int(values['serverId']) for values in (patrons or {}).values() if 'lapsed' not in values}

def lapsedServerIds(patrons):
    return {int(values['serverId']) for values in (patrons or {}).values() if 'lapsed' in values}

def trialState(trial, at = None):
    if trial is None:
        return NONE
    at = at or utcNow()
    if at < trialEnds(trial):
        return TRIAL
    if at < graceEnds(trial):
        return ENDED
    return EXPIRED

def state(guildId, ignored, subscribed, trial, at = None, lapsed = ()):
    # a running trial outlasts a subscription that lapsed during it
    if guildId in ignored:
        return IGNORED
    if guildId in subscribed:
        return SUBSCRIBED
    onTrial = trialState(trial, at)
    if onTrial != TRIAL and guildId in lapsed:
        return LAPSED
    return onTrial

def check(guildId, mutualGuildIds = ()):
    # A private message counts as allowed when anyone it could come from is: a server the sender
    # shares with GBot that is ignored, subscribed or on a trial.
    ignored = utils.getGuildsForPatreonToIgnore() or []
    ids = [guildId] if guildId is not None else list(mutualGuildIds)
    if any(serverId in ignored for serverId in ids):
        return IGNORED
    patrons = patreon_queries.getAllPatrons()
    subscribed = subscribedServerIds(patrons)
    if any(serverId in subscribed for serverId in ids):
        return SUBSCRIBED
    if guildId is not None:
        return state(guildId, ignored, subscribed, patreon_queries.getTrial(guildId), lapsed = lapsedServerIds(patrons))
    if not ids:
        return NONE
    trials = patreon_queries.getAllTrials() or {}
    return TRIAL if any(state(serverId, ignored, subscribed, trials.get(str(serverId))) == TRIAL for serverId in ids) else NONE

def isActive(guildId):
    # for what GBot does on its own rather than on a command, like a Storm or a Hype reply
    return check(guildId) in ALLOWED

def trialEnding(guildId):
    # when this server's trial ends, or None when it isn't on one
    if check(guildId) != TRIAL:
        return None
    return trialEnds(patreon_queries.getTrial(guildId))

def startTrial(guildId):
    # On joining a server that has never had a trial and isn't subscribed or ignored. The record is
    # kept after GBot leaves, so leaving and re-adding GBot doesn't start another. A TRIAL_DAYS of 0
    # turns trials off. Returns when the server's trial ends, or None when it isn't on one.
    if GBotPropertiesManager.TRIAL_DAYS > 0 and check(guildId) == NONE:
        patreon_queries.setTrial(guildId, utcNow().isoformat())
        logging.getLogger().info(f'GBot started a free trial in server {guildId}.')
    return trialEnding(guildId)

def reminderDue(trial, currentState, at = None):
    # The reminder to send now, or None. Each is sent once, and a later one replaces any that were
    # missed, so a server never gets two at once.
    at = at or utcNow()
    if currentState == ENDED:
        due = REMINDER_ENDED
    elif currentState == TRIAL and trialEnds(trial) - at <= timedelta(days = 1):
        due = REMINDER_LAST_DAY
    elif currentState == TRIAL and trialEnds(trial) - at <= timedelta(days = 2):
        due = REMINDER_TWO_DAYS
    else:
        return None
    sent = trial.get('reminded')
    return None if sent is not None and sent <= due else due

def timestamp(moment, style):
    # Discord shows it in each reader's own time zone
    return f'<t:{int(moment.timestamp())}:{style}>'

def howToSubscribe(guildId):
    return f'To keep GBot, subscribe on Patreon, then run `/patreon` with this server\'s ID, `{guildId}`, in the GBot Patreon server.'

def howToRenew(guildId):
    return f'To keep GBot, renew on Patreon, or have someone else subscribe and run `/patreon` with this server\'s ID, `{guildId}`, in the GBot Patreon server.'

def endedText(guildId, lapsed):
    # what a refused command says once a trial or a subscription is over
    if lapsed:
        return f"This server's GBot subscription has ended. {howToRenew(guildId)}"
    return f"GBot's free trial in this server has ended. {howToSubscribe(guildId)}"

def lapseText(guildId, patron):
    return f"💳 This server's GBot subscription has ended, so its commands now ask to subscribe. Without one GBot leaves after {timestamp(lapseEnds(patron), 'D')}, and its settings here go with it. {howToRenew(guildId)}"

def reminderText(guildId, trial, due):
    if due == REMINDER_ENDED:
        return f"🎁 GBot's free trial in this server has ended, so its commands now ask to subscribe. Without a subscription GBot leaves after {timestamp(graceEnds(trial), 'D')}, and its settings here go with it. {howToSubscribe(guildId)}"
    lastDay = ' That\'s the last day.' if due == REMINDER_LAST_DAY else ''
    return f"🎁 GBot's free trial in this server ends {timestamp(trialEnds(trial), 'R')}.{lastDay} {howToSubscribe(guildId)}"
