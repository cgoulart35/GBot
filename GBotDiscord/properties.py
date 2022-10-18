#region IMPORTS
import os
#endregion

class GBotPropertiesManager:
    # GBOT PROPERTIES
    GBOT_VERSION = None
    TZ = None
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
        GBotPropertiesManager.GBOT_VERSION =                                os.getenv("GBOT_VERSION")
        GBotPropertiesManager.TZ =                                          os.getenv("TZ")
        GBotPropertiesManager.API_PORT =                                    int(os.getenv("API_PORT"))

        GBotPropertiesManager.GIT_UPDATER_HOST =                            os.getenv("GIT_UPDATER_HOST")
        GBotPropertiesManager.PATREON_URL =                                 os.getenv("PATREON_URL")

        GBotPropertiesManager.DISCORD_TOKEN =                               os.getenv("DISCORD_TOKEN")
        GBotPropertiesManager.FIREBASE_CONFIG_JSON =                        os.getenv("FIREBASE_CONFIG_JSON")
        GBotPropertiesManager.FIREBASE_AUTH_EMAIL =                         os.getenv("FIREBASE_AUTH_EMAIL")
        GBotPropertiesManager.FIREBASE_AUTH_PASSWORD =                      os.getenv("FIREBASE_AUTH_PASSWORD")

        GBotPropertiesManager.PATREON_GUILD_ID =                            int(os.getenv("PATREON_GUILD_ID"))
        GBotPropertiesManager.PATRON_ROLE_ID =                              int(os.getenv("PATRON_ROLE_ID"))
        GBotPropertiesManager.PATREON_IGNORE_GUILDS =                       os.getenv("PATREON_IGNORE_GUILDS")

        GBotPropertiesManager.USER_RESPONSE_TIMEOUT_SECONDS =               int(os.getenv("USER_RESPONSE_TIMEOUT_SECONDS"))
        GBotPropertiesManager.MUSIC_TIMEOUT_SECONDS =                       int(os.getenv("MUSIC_TIMEOUT_SECONDS"))
        GBotPropertiesManager.MUSIC_CACHE_DELETION_TIMEOUT_MINUTES =        int(os.getenv("MUSIC_CACHE_DELETION_TIMEOUT_MINUTES"))
        GBotPropertiesManager.GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES =  int(os.getenv("GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES"))
        GBotPropertiesManager.GTRADE_MARKET_SALE_TIMEOUT_HOURS =            int(os.getenv("GTRADE_MARKET_SALE_TIMEOUT_HOURS"))
        GBotPropertiesManager.STORMS_MIN_TIME_BETWEEN_SECONDS =             int(os.getenv("STORMS_MIN_TIME_BETWEEN_SECONDS"))
        GBotPropertiesManager.STORMS_MAX_TIME_BETWEEN_SECONDS =             int(os.getenv("STORMS_MAX_TIME_BETWEEN_SECONDS"))
        GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS =        int(os.getenv("STORMS_DELETE_MESSAGES_AFTER_SECONDS"))