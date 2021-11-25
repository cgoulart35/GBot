from discord.ext import commands

class MessageAuthorNotAdmin(commands.CheckFailure):
    pass

class MessageNotSentFromGuild(commands.CheckFailure):
    pass

class FeatureNotEnabledForGuild(commands.CheckFailure):
    pass