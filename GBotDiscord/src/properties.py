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
        "GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES",
        "GTRADE_MARKET_SALE_TIMEOUT_HOURS",
        "STORMS_MIN_TIME_BETWEEN_SECONDS",
        "STORMS_MAX_TIME_BETWEEN_SECONDS",
        "STORMS_DELETE_MESSAGES_AFTER_SECONDS",
        "WHODIS_TIMEOUT_MINUTES",
        "WHODIS_COOLDOWN_MINUTES",
        "SLASH_COMMAND_TEST_GUILDS"
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
    GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES = None
    GTRADE_MARKET_SALE_TIMEOUT_HOURS = None
    STORMS_MIN_TIME_BETWEEN_SECONDS = None
    STORMS_MAX_TIME_BETWEEN_SECONDS = None
    STORMS_DELETE_MESSAGES_AFTER_SECONDS = None
    WHODIS_TIMEOUT_MINUTES = None
    WHODIS_COOLDOWN_MINUTES = None

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
        GBotPropertiesManager.GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES =  GBotPropertiesManager.getEnvProperty("GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES", "5") # not required, usable when not given
        GBotPropertiesManager.GTRADE_MARKET_SALE_TIMEOUT_HOURS =            GBotPropertiesManager.getEnvProperty("GTRADE_MARKET_SALE_TIMEOUT_HOURS", "3")           # not required, usable when not given
        GBotPropertiesManager.STORMS_MIN_TIME_BETWEEN_SECONDS =             GBotPropertiesManager.getEnvProperty("STORMS_MIN_TIME_BETWEEN_SECONDS", "3600")         # not required, usable when not given
        GBotPropertiesManager.STORMS_MAX_TIME_BETWEEN_SECONDS =             GBotPropertiesManager.getEnvProperty("STORMS_MAX_TIME_BETWEEN_SECONDS", "14400")        # not required, usable when not given
        GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS =        GBotPropertiesManager.getEnvProperty("STORMS_DELETE_MESSAGES_AFTER_SECONDS", "60")      # not required, usable when not given
        GBotPropertiesManager.WHODIS_TIMEOUT_MINUTES =                      GBotPropertiesManager.getEnvProperty("WHODIS_TIMEOUT_MINUTES", "5")                     # not required, usable when not given
        GBotPropertiesManager.WHODIS_COOLDOWN_MINUTES =                     GBotPropertiesManager.getEnvProperty("WHODIS_COOLDOWN_MINUTES", "10")                   # not required, usable when not given

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
            "GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES",
            "GTRADE_MARKET_SALE_TIMEOUT_HOURS",
            "STORMS_MIN_TIME_BETWEEN_SECONDS",
            "STORMS_MAX_TIME_BETWEEN_SECONDS",
            "STORMS_DELETE_MESSAGES_AFTER_SECONDS",
            "WHODIS_TIMEOUT_MINUTES",
            "WHODIS_COOLDOWN_MINUTES"
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