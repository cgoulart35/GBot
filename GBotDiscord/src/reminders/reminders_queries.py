#region IMPORTS
from GBotDiscord.src.firebase import GBotFirebaseService
#endregion

# tables:
    # reminders: deleted with the server's other data when GBot leaves it
        # serverId
            # reminderId
                # userId: who set it, and who it pings unless target says otherwise
                # channelId: where it was set, and where it goes unless where is dm
                # text
                # nextAt: when it's next due, ISO 8601 in UTC
                # repeat: once, daily, weekdays, weekly, monthly:<day>, yearly:<month>-<day> or days:<0-6,...>
                # where: here or dm
                # target: absent for the person who set it, else 'everyone' or a role ID
                # delivered: a one-off already sent, ISO 8601 in UTC, kept a day so it can be snoozed
                # snoozed: true on a one-off that was snoozed, which is itself moved later
                # snoozeOf: on a repeat's snooze, a one-off copy, the id of the repeat it came from
                # timer: true while nextAt is a moment counted to ("in 2 hours") rather than a clock time,
                #        so a change of time zone leaves it where it is
    # users
        # userId
            # timezone: an IANA name, the same in every server

def getAllReminders():
    return GBotFirebaseService.get(["reminders"]).val()

def getServerReminders(serverId):
    return GBotFirebaseService.get(["reminders", str(serverId)]).val()

def getReminder(serverId, reminderId):
    return GBotFirebaseService.get(["reminders", str(serverId), reminderId]).val()

def addReminder(serverId, reminder):
    return GBotFirebaseService.push(["reminders", str(serverId)], reminder)

def updateReminder(serverId, reminderId, changes):
    # Whether it was there to change. An update to one deleted a moment before would bring back half
    # a reminder, with no owner or text, which nothing that lists reminders could then read.
    if getReminder(serverId, reminderId) is None:
        return False
    GBotFirebaseService.update(["reminders", str(serverId), reminderId], changes)
    return True

def removeReminder(serverId, reminderId):
    GBotFirebaseService.remove(["reminders", str(serverId), reminderId])

def getTimezone(userId):
    return GBotFirebaseService.get(["users", str(userId), "timezone"]).val()

def setTimezone(userId, zoneName):
    GBotFirebaseService.set(["users", str(userId), "timezone"], zoneName)
