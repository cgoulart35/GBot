from nextcord.ext import commands

# command decorator checks
class MessageAuthorNotAdmin(commands.CheckFailure):
    pass

class MessageNotSentFromGuild(commands.CheckFailure):
    pass

class MessageNotSentFromPrivateMessage(commands.CheckFailure):
    pass

class FeatureNotEnabledForGuild(commands.CheckFailure):
    def __init__(self, message, featureName):
        super().__init__(message)
        self.featureName = featureName

    def userMessage(self, mention):
        # features start off in a new server, so a refusal has to say how to turn one on, or the
        # server just looks broken
        return f'Sorry {mention}, {self.featureName} is turned off in this server. An admin can turn it on with `/config toggle`.'

class LegacyPrefixCommandsNotEnabledForGuild(commands.CheckFailure):
    pass

class NotSentFromPatreonGuild(commands.CheckFailure):
    pass

class NotAPatron(commands.CheckFailure):
    pass

class NotSubscribed(commands.CheckFailure):
    pass

# command errors
class CustomCommandOnCooldown(commands.CommandError):
   def __init__(self, retry_after, is_private_message, reason):
       self.retry_after = retry_after
       self.is_private_message = is_private_message
       self.reason = reason

# GCoin transaction errors
class EnforceRealUsersError(Exception):
    pass

class EnforceSenderReceiverNotEqual(Exception):
    pass

class EnforcePositiveTransactions(Exception):
    pass

class EnforceSenderFundsError(Exception):
    pass

# GTrade item errors
class ItemNameTooLong(Exception):
    pass

class ItemNoLongerAvailable(Exception):
    pass

class ItemNameConflict(Exception):
    pass

class ItemTypeInvalid(Exception):
    pass

class ItemMaxCount(Exception):
    pass

# Storm errors
class StormNotConfigured(Exception):
    pass

# Who Dis errors
class WhoDisNotConfigured(Exception):
    pass

# other errors
class PropertyNotSpecified(Exception):
    pass

class PropertyValueInvalid(Exception):
    pass

class UserCancelledCommand(Exception):
    pass