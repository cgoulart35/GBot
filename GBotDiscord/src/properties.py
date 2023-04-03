#region IMPORTS
import os
import logging

from GBotDiscord.src.exceptions import PropertyNotSpecified
#endregion

class GBotPropertiesManager:
    logger = logging.getLogger()

    # GBOT PROPERTIES
    GBOT_VERSION = None
    TZ = None
    LOG_LEVEL = None
    API_PORT = None

    # COMMUNICATION PROPERTIES
    GIT_UPDATER_HOST = None
    PATREON_URL = None
    
    # CREDENTIAL PROPERTIES
    DISCORD_TOKEN = None
    FIREBASE_CONFIG_JSON = None
    FIREBASE_AUTH_EMAIL = None
    FIREBASE_AUTH_PASSWORD = None
    
    # DISCORD ID PROPERTIES
    PATREON_GUILD_ID = None
    PATRON_ROLE_ID = None
    PATREON_IGNORE_GUILDS = None

    # TIME PROPERTIES
    USER_RESPONSE_TIMEOUT_SECONDS = None
    MUSIC_TIMEOUT_SECONDS = None
    MUSIC_CACHE_DELETION_TIMEOUT_MINUTES = None
    GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES = None
    GTRADE_MARKET_SALE_TIMEOUT_HOURS = None
    STORMS_MIN_TIME_BETWEEN_SECONDS = None
    STORMS_MAX_TIME_BETWEEN_SECONDS = None
    STORMS_DELETE_MESSAGES_AFTER_SECONDS = None

    def startPropertyManager():
        # initialize properties
        GBotPropertiesManager.GBOT_VERSION =                                GBotPropertiesManager.getEnvProperty("GBOT_VERSION")                # required
        GBotPropertiesManager.TZ =                                          GBotPropertiesManager.getEnvProperty("TZ", "America/New_York")      # not required, usable
        GBotPropertiesManager.LOG_LEVEL =                                   GBotPropertiesManager.getEnvProperty("LOG_LEVEL", "INFO")           # not required, usable
        GBotPropertiesManager.API_PORT =                                    GBotPropertiesManager.getEnvProperty("API_PORT", "5004")            # not required, usable

        GBotPropertiesManager.GIT_UPDATER_HOST =                            GBotPropertiesManager.getEnvProperty("GIT_UPDATER_HOST", "")        # not required, unusable
        GBotPropertiesManager.PATREON_URL =                                 GBotPropertiesManager.getEnvProperty("PATREON_URL")                 # required

        GBotPropertiesManager.DISCORD_TOKEN =                               GBotPropertiesManager.getEnvProperty("DISCORD_TOKEN")               # required
        GBotPropertiesManager.FIREBASE_CONFIG_JSON =                        GBotPropertiesManager.getEnvProperty("FIREBASE_CONFIG_JSON")        # required
        GBotPropertiesManager.FIREBASE_AUTH_EMAIL =                         GBotPropertiesManager.getEnvProperty("FIREBASE_AUTH_EMAIL")         # required
        GBotPropertiesManager.FIREBASE_AUTH_PASSWORD =                      GBotPropertiesManager.getEnvProperty("FIREBASE_AUTH_PASSWORD")      # required

        GBotPropertiesManager.PATREON_GUILD_ID =                            GBotPropertiesManager.getEnvProperty("PATREON_GUILD_ID")            # required
        GBotPropertiesManager.PATRON_ROLE_ID =                              GBotPropertiesManager.getEnvProperty("PATRON_ROLE_ID")              # required
        GBotPropertiesManager.PATREON_IGNORE_GUILDS =                       GBotPropertiesManager.getEnvProperty("PATREON_IGNORE_GUILDS", "")   # not required, usable

        GBotPropertiesManager.USER_RESPONSE_TIMEOUT_SECONDS =               GBotPropertiesManager.getEnvProperty("USER_RESPONSE_TIMEOUT_SECONDS", "300")            # not required, usable
        GBotPropertiesManager.MUSIC_TIMEOUT_SECONDS =                       GBotPropertiesManager.getEnvProperty("MUSIC_TIMEOUT_SECONDS", "300")                    # not required, usable
        GBotPropertiesManager.MUSIC_CACHE_DELETION_TIMEOUT_MINUTES =        GBotPropertiesManager.getEnvProperty("MUSIC_CACHE_DELETION_TIMEOUT_MINUTES", "180")     # not required, usable
        GBotPropertiesManager.GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES =  GBotPropertiesManager.getEnvProperty("GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES", "5") # not required, usable
        GBotPropertiesManager.GTRADE_MARKET_SALE_TIMEOUT_HOURS =            GBotPropertiesManager.getEnvProperty("GTRADE_MARKET_SALE_TIMEOUT_HOURS", "3")           # not required, usable
        GBotPropertiesManager.STORMS_MIN_TIME_BETWEEN_SECONDS =             GBotPropertiesManager.getEnvProperty("STORMS_MIN_TIME_BETWEEN_SECONDS", "3600")         # not required, usable
        GBotPropertiesManager.STORMS_MAX_TIME_BETWEEN_SECONDS =             GBotPropertiesManager.getEnvProperty("STORMS_MAX_TIME_BETWEEN_SECONDS", "14400")        # not required, usable
        GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS =        GBotPropertiesManager.getEnvProperty("STORMS_DELETE_MESSAGES_AFTER_SECONDS", "900")     # not required, usable

    def getEnvProperty(property, default = None):
        value = os.getenv(property)
        if value:
            return GBotPropertiesManager.determineValue(property, value)
        elif default != None:
            return default
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
            "MUSIC_CACHE_DELETION_TIMEOUT_MINUTES",
            "GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES",
            "GTRADE_MARKET_SALE_TIMEOUT_HOURS",
            "STORMS_MIN_TIME_BETWEEN_SECONDS",
            "STORMS_MAX_TIME_BETWEEN_SECONDS",
            "STORMS_DELETE_MESSAGES_AFTER_SECONDS"
        ]

        if property in INT_PROPERTIES:
            return int(value)
        elif property == "LOG_LEVEL":
            return GBotPropertiesManager.getLogLevel(value)
        else:
            return value                

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
        
    def setProperty(property, value):
        if property == "GBOT_VERSION":
            GBotPropertiesManager.GBOT_VERSION = value
        elif property == "TZ":
            GBotPropertiesManager.TZ = value
        elif property == "LOG_LEVEL":
            GBotPropertiesManager.LOG_LEVEL = value
        elif property == "API_PORT":
            GBotPropertiesManager.API_PORT = value
        elif property == "GIT_UPDATER_HOST":
            GBotPropertiesManager.GIT_UPDATER_HOST = value
        elif property == "PATREON_URL":
            GBotPropertiesManager.PATREON_URL = value
        elif property == "DISCORD_TOKEN":
            GBotPropertiesManager.DISCORD_TOKEN = value
        elif property == "FIREBASE_CONFIG_JSON":
            GBotPropertiesManager.FIREBASE_CONFIG_JSON = value
        elif property == "FIREBASE_AUTH_EMAIL":
            GBotPropertiesManager.FIREBASE_AUTH_EMAIL = value
        elif property == "FIREBASE_AUTH_PASSWORD":
            GBotPropertiesManager.FIREBASE_AUTH_PASSWORD = value
        elif property == "PATREON_GUILD_ID":
            GBotPropertiesManager.PATREON_GUILD_ID = value
        elif property == "PATRON_ROLE_ID":
            GBotPropertiesManager.PATRON_ROLE_ID = value
        elif property == "PATREON_IGNORE_GUILDS":
            GBotPropertiesManager.PATREON_IGNORE_GUILDS = value
        elif property == "USER_RESPONSE_TIMEOUT_SECONDS":
            GBotPropertiesManager.USER_RESPONSE_TIMEOUT_SECONDS = value
        elif property == "MUSIC_TIMEOUT_SECONDS":
            GBotPropertiesManager.MUSIC_TIMEOUT_SECONDS = value
        elif property == "MUSIC_CACHE_DELETION_TIMEOUT_MINUTES":
            GBotPropertiesManager.MUSIC_CACHE_DELETION_TIMEOUT_MINUTES = value
        elif property == "GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES":
            GBotPropertiesManager.GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES = value
        elif property == "GTRADE_MARKET_SALE_TIMEOUT_HOURS":
            GBotPropertiesManager.GTRADE_MARKET_SALE_TIMEOUT_HOURS = value
        elif property == "STORMS_MIN_TIME_BETWEEN_SECONDS":
            GBotPropertiesManager.STORMS_MIN_TIME_BETWEEN_SECONDS = value
        elif property == "STORMS_MAX_TIME_BETWEEN_SECONDS":
            GBotPropertiesManager.STORMS_MAX_TIME_BETWEEN_SECONDS = value
        elif property == "STORMS_DELETE_MESSAGES_AFTER_SECONDS":
            GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS = value
        else:
            return False
        return True