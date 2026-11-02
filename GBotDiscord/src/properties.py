#region IMPORTS
import os
import logging

from GBotDiscord.src.exceptions import PropertyNotSpecified, PropertyValueInvalid
#endregion

class GBotPropertiesManager:
    logger = logging.getLogger()

    # properties the setProperty API action is allowed to mutate at runtime; every other
    # property (GBOT_VERSION, TZ, API_PORT, DISCORD_TOKEN, FIREBASE_CONFIG_JSON) is
    # intentionally immutable and can only be changed by restarting the bot
    MUTABLE_PROPERTIES = [
        "LOG_LEVEL",
        "PATREON_URL",
        "PATREON_GUILD_ID",
        "PATRON_ROLE_ID",
        "PATREON_IGNORE_GUILDS",
        "USER_RESPONSE_TIMEOUT_SECONDS",
        "MUSIC_TIMEOUT_SECONDS",
        "MUSIC_MAX_DURATION_MINUTES",
        "MUSIC_MAX_PLAYLIST_SONGS",
        "MUSIC_MAX_QUEUE_SONGS",
        "GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES",
        "GTRADE_MARKET_SALE_TIMEOUT_HOURS",
        "STORMS_MIN_TIME_BETWEEN_SECONDS",
        "STORMS_MAX_TIME_BETWEEN_SECONDS",
        "STORMS_DELETE_MESSAGES_AFTER_SECONDS",
        "WHODIS_TIMEOUT_MINUTES",
        "WHODIS_COOLDOWN_MINUTES",
        "SLASH_COMMAND_TEST_GUILDS",
        "AGENT_DAILY_TOKEN_LIMIT",
        "AGENT_USER_COOLDOWN_SECONDS",
        "AGENT_MIN_USER_COOLDOWN_SECONDS",
        "AGENT_REPLY_TOKENS",
        "AGENT_MAX_REPLY_TOKENS",
        "AGENT_HISTORY_MESSAGES",
        "AGENT_MAX_HISTORY_MESSAGES",
        "AGENT_MAX_TOOL_TURNS",
        "AGENT_MAX_INSTRUCTION_CHARACTERS",
        "AGENT_MAX_MEMORIES",
        "AGENT_MAX_MEMORY_CHARACTERS"
    ]

    # GBOT PROPERTIES
    GBOT_VERSION = None
    TZ = None
    LOG_LEVEL = None
    API_PORT = None

    # COMMUNICATION PROPERTIES
    PATREON_URL = None
    
    # CREDENTIAL PROPERTIES
    DISCORD_TOKEN = None
    FIREBASE_CONFIG_JSON = None
    
    # DISCORD ID PROPERTIES
    PATREON_GUILD_ID = None
    PATRON_ROLE_ID = None
    PATREON_IGNORE_GUILDS = None

    # TIME PROPERTIES
    USER_RESPONSE_TIMEOUT_SECONDS = None
    MUSIC_TIMEOUT_SECONDS = None
    MUSIC_MAX_DURATION_MINUTES = None
    MUSIC_MAX_PLAYLIST_SONGS = None
    MUSIC_MAX_QUEUE_SONGS = None
    GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES = None
    GTRADE_MARKET_SALE_TIMEOUT_HOURS = None
    STORMS_MIN_TIME_BETWEEN_SECONDS = None
    STORMS_MAX_TIME_BETWEEN_SECONDS = None
    STORMS_DELETE_MESSAGES_AFTER_SECONDS = None
    WHODIS_TIMEOUT_MINUTES = None
    WHODIS_COOLDOWN_MINUTES = None
    ANTHROPIC_API_KEY = None
    AGENT_KEY_SECRET = None
    AGENT_DAILY_TOKEN_LIMIT = None
    AGENT_USER_COOLDOWN_SECONDS = None
    AGENT_MIN_USER_COOLDOWN_SECONDS = None
    AGENT_REPLY_TOKENS = None
    AGENT_MAX_REPLY_TOKENS = None
    AGENT_HISTORY_MESSAGES = None
    AGENT_MAX_HISTORY_MESSAGES = None
    AGENT_MAX_TOOL_TURNS = None
    AGENT_MAX_INSTRUCTION_CHARACTERS = None
    AGENT_MAX_MEMORIES = None
    AGENT_MAX_MEMORY_CHARACTERS = None

    # DEVELOPMENT ONLY PROPERTIES
    SLASH_COMMAND_TEST_GUILDS = None

    def startPropertyManager():
        # initialize properties
        GBotPropertiesManager.GBOT_VERSION =                                GBotPropertiesManager.getEnvProperty("GBOT_VERSION")                # required
        GBotPropertiesManager.TZ =                                          GBotPropertiesManager.getEnvProperty("TZ", "America/New_York")      # not required, usable when not given
        GBotPropertiesManager.LOG_LEVEL =                                   GBotPropertiesManager.getEnvProperty("LOG_LEVEL", "INFO")           # not required, usable when not given
        GBotPropertiesManager.API_PORT =                                    GBotPropertiesManager.getEnvProperty("API_PORT", "5004")            # not required, usable when not given

        GBotPropertiesManager.PATREON_URL =                                 GBotPropertiesManager.getEnvProperty("PATREON_URL")                 # required

        GBotPropertiesManager.DISCORD_TOKEN =                               GBotPropertiesManager.getEnvProperty("DISCORD_TOKEN")               # required
        GBotPropertiesManager.FIREBASE_CONFIG_JSON =                        GBotPropertiesManager.getEnvProperty("FIREBASE_CONFIG_JSON")        # required

        GBotPropertiesManager.PATREON_GUILD_ID =                            GBotPropertiesManager.getEnvProperty("PATREON_GUILD_ID")            # required
        GBotPropertiesManager.PATRON_ROLE_ID =                              GBotPropertiesManager.getEnvProperty("PATRON_ROLE_ID")              # required
        GBotPropertiesManager.PATREON_IGNORE_GUILDS =                       GBotPropertiesManager.getEnvProperty("PATREON_IGNORE_GUILDS", "")   # not required, usable when not given

        GBotPropertiesManager.USER_RESPONSE_TIMEOUT_SECONDS =               GBotPropertiesManager.getEnvProperty("USER_RESPONSE_TIMEOUT_SECONDS", "300")            # not required, usable when not given
        GBotPropertiesManager.MUSIC_TIMEOUT_SECONDS =                       GBotPropertiesManager.getEnvProperty("MUSIC_TIMEOUT_SECONDS", "300")                    # not required, usable when not given
        GBotPropertiesManager.MUSIC_MAX_DURATION_MINUTES =                  GBotPropertiesManager.getEnvProperty("MUSIC_MAX_DURATION_MINUTES", "180")               # not required, usable when not given
        GBotPropertiesManager.MUSIC_MAX_PLAYLIST_SONGS =                    GBotPropertiesManager.getEnvProperty("MUSIC_MAX_PLAYLIST_SONGS", "50")                  # not required, usable when not given
        GBotPropertiesManager.MUSIC_MAX_QUEUE_SONGS =                       GBotPropertiesManager.getEnvProperty("MUSIC_MAX_QUEUE_SONGS", "200")                    # not required, usable when not given
        GBotPropertiesManager.GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES =  GBotPropertiesManager.getEnvProperty("GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES", "5") # not required, usable when not given
        GBotPropertiesManager.GTRADE_MARKET_SALE_TIMEOUT_HOURS =            GBotPropertiesManager.getEnvProperty("GTRADE_MARKET_SALE_TIMEOUT_HOURS", "3")           # not required, usable when not given
        GBotPropertiesManager.STORMS_MIN_TIME_BETWEEN_SECONDS =             GBotPropertiesManager.getEnvProperty("STORMS_MIN_TIME_BETWEEN_SECONDS", "3600")         # not required, usable when not given
        GBotPropertiesManager.STORMS_MAX_TIME_BETWEEN_SECONDS =             GBotPropertiesManager.getEnvProperty("STORMS_MAX_TIME_BETWEEN_SECONDS", "14400")        # not required, usable when not given
        GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS =        GBotPropertiesManager.getEnvProperty("STORMS_DELETE_MESSAGES_AFTER_SECONDS", "60")      # not required, usable when not given
        GBotPropertiesManager.WHODIS_TIMEOUT_MINUTES =                      GBotPropertiesManager.getEnvProperty("WHODIS_TIMEOUT_MINUTES", "5")                     # not required, usable when not given
        GBotPropertiesManager.WHODIS_COOLDOWN_MINUTES =                     GBotPropertiesManager.getEnvProperty("WHODIS_COOLDOWN_MINUTES", "10")                   # not required, usable when not given
        GBotPropertiesManager.ANTHROPIC_API_KEY = GBotPropertiesManager.getEnvProperty("ANTHROPIC_API_KEY", "")
        GBotPropertiesManager.AGENT_KEY_SECRET = GBotPropertiesManager.getEnvProperty("AGENT_KEY_SECRET", "")
        GBotPropertiesManager.AGENT_DAILY_TOKEN_LIMIT = GBotPropertiesManager.getEnvProperty("AGENT_DAILY_TOKEN_LIMIT", "2000000")
        GBotPropertiesManager.AGENT_USER_COOLDOWN_SECONDS = GBotPropertiesManager.getEnvProperty("AGENT_USER_COOLDOWN_SECONDS", "10")
        GBotPropertiesManager.AGENT_MIN_USER_COOLDOWN_SECONDS = GBotPropertiesManager.getEnvProperty("AGENT_MIN_USER_COOLDOWN_SECONDS", "1")
        GBotPropertiesManager.AGENT_REPLY_TOKENS = GBotPropertiesManager.getEnvProperty("AGENT_REPLY_TOKENS", "1024")
        GBotPropertiesManager.AGENT_MAX_REPLY_TOKENS = GBotPropertiesManager.getEnvProperty("AGENT_MAX_REPLY_TOKENS", "4096")
        GBotPropertiesManager.AGENT_HISTORY_MESSAGES = GBotPropertiesManager.getEnvProperty("AGENT_HISTORY_MESSAGES", "10")
        GBotPropertiesManager.AGENT_MAX_HISTORY_MESSAGES = GBotPropertiesManager.getEnvProperty("AGENT_MAX_HISTORY_MESSAGES", "50")
        GBotPropertiesManager.AGENT_MAX_TOOL_TURNS = GBotPropertiesManager.getEnvProperty("AGENT_MAX_TOOL_TURNS", "3")
        GBotPropertiesManager.AGENT_MAX_INSTRUCTION_CHARACTERS = GBotPropertiesManager.getEnvProperty("AGENT_MAX_INSTRUCTION_CHARACTERS", "2000")
        GBotPropertiesManager.AGENT_MAX_MEMORIES = GBotPropertiesManager.getEnvProperty("AGENT_MAX_MEMORIES", "50")
        GBotPropertiesManager.AGENT_MAX_MEMORY_CHARACTERS = GBotPropertiesManager.getEnvProperty("AGENT_MAX_MEMORY_CHARACTERS", "500")

        GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS =                   GBotPropertiesManager.getEnvProperty("SLASH_COMMAND_TEST_GUILDS", "")                   # not required, usable when not given

    def getEnvProperty(property, default = None):
        value = os.getenv(property)
        if value:
            return GBotPropertiesManager.determineValue(property, value)
        elif default != None:
            # defaults are coerced exactly like env values: an omitted int property must not
            # land as its string default (e.g. STORMS_MIN_TIME_BETWEEN_SECONDS = "3600" would
            # blow up random.randint, and PATREON_IGNORE_GUILDS = "" would blow up the
            # patreon ignore-list append)
            return GBotPropertiesManager.determineValue(property, default)
        else:
            GBotPropertiesManager.logger.error('Required GBot property not specified: ' + property)
            raise PropertyNotSpecified
        
    def determineValue(property, value):
        INT_PROPERTIES = [
            "API_PORT",
            "PATREON_GUILD_ID",
            "PATRON_ROLE_ID",
            "USER_RESPONSE_TIMEOUT_SECONDS",
            "MUSIC_TIMEOUT_SECONDS",
            "MUSIC_MAX_DURATION_MINUTES",
            "MUSIC_MAX_PLAYLIST_SONGS",
            "MUSIC_MAX_QUEUE_SONGS",
            "GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES",
            "GTRADE_MARKET_SALE_TIMEOUT_HOURS",
            "STORMS_MIN_TIME_BETWEEN_SECONDS",
            "STORMS_MAX_TIME_BETWEEN_SECONDS",
            "STORMS_DELETE_MESSAGES_AFTER_SECONDS",
            "WHODIS_TIMEOUT_MINUTES",
            "WHODIS_COOLDOWN_MINUTES",
            "AGENT_DAILY_TOKEN_LIMIT",
            "AGENT_USER_COOLDOWN_SECONDS",
            "AGENT_MIN_USER_COOLDOWN_SECONDS",
            "AGENT_REPLY_TOKENS",
            "AGENT_MAX_REPLY_TOKENS",
            "AGENT_HISTORY_MESSAGES",
            "AGENT_MAX_HISTORY_MESSAGES",
            "AGENT_MAX_TOOL_TURNS",
            "AGENT_MAX_INSTRUCTION_CHARACTERS",
            "AGENT_MAX_MEMORIES",
            "AGENT_MAX_MEMORY_CHARACTERS"
        ]
        SPLITTABLE_INT_PROPERTIES = [
            "PATREON_IGNORE_GUILDS",
            "SLASH_COMMAND_TEST_GUILDS"
        ]

        if property in INT_PROPERTIES:
            return int(value)
        if property in SPLITTABLE_INT_PROPERTIES:
            # env values arrive as a CSV string; API payloads may already be a JSON list
            if isinstance(value, list):
                return [int(x) for x in value]
            if value != '':
                listOfStrings = value.split(',')
                listOfInts = [int(x) for x in listOfStrings]
            else:
                listOfInts = []
            return listOfInts
        elif property == "LOG_LEVEL":
            # a level name resolves to its logging constant; an already-resolved level passes through
            if isinstance(value, int):
                return value
            return GBotPropertiesManager.getLogLevel(value)
        else:
            return value

    def setProperty(property, value):
        # returns False for an unknown or intentionally immutable property; raises
        # PropertyValueInvalid when the property is mutable but the value can't be coerced
        # to its type
        if property not in GBotPropertiesManager.MUTABLE_PROPERTIES:
            return False

        # coerce API-supplied values the same way env values are coerced, so a runtime-set
        # int property can never sit as a string until the next restart
        try:
            value = GBotPropertiesManager.determineValue(property, value)
        except (ValueError, TypeError, AttributeError) as error:
            raise PropertyValueInvalid(f'{property} can not be set to: {value}') from error

        setattr(GBotPropertiesManager, property, value)
        if property == "LOG_LEVEL":
            GBotPropertiesManager.logger.setLevel(value)
        return True

    def getLogLevel(level):
        if level == "CRITICAL":
            return logging.CRITICAL
        elif level == "FATAL":
            return logging.FATAL
        elif level == "ERROR":
            return logging.ERROR
        elif level == "WARNING":
            return logging.WARNING
        elif level == "WARN":
            return logging.WARN
        elif level == "INFO":
            return logging.INFO
        elif level == "DEBUG":
            return logging.DEBUG
        else:
            return logging.NOTSET