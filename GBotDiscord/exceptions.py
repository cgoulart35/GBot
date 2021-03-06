from nextcord.ext import commands

# command decorator checks
class MessageAuthorNotAdmin(commands.CheckFailure):
    pass

class MessageNotSentFromGuild(commands.CheckFailure):
    pass

class FeatureNotEnabledForGuild(commands.CheckFailure):
    pass

class NotSentFromPatreonGuild(commands.CheckFailure):
    pass

class NotAPatron(commands.CheckFailure):
    pass

class NotSubscribed(commands.CheckFailure):
    pass

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
class ItemNameConflict(Exception):
    pass

class ItemTypeInvalid(Exception):
    pass

class ItemMaxCount(Exception):
    pass

# other errors
class UserCancelledCommand(Exception):
    pass