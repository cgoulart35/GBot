#region IMPORTS
from GBotDiscord.src import presentation
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

# How each feature works, in a few sentences: shown on /help <feature> and read by the agent when
# someone asks. Every number comes from the settings or from the class that uses it, so changing a
# limit or a reward changes the guide too. Each has to fit in one embed field, 1024 characters.

def hours(seconds):
    return f'{seconds / 3600:g}'

def agent():
    return (
        "Admins set it up with a Claude API key from `/agent key`, then shape it with `/agent settings` and `/agent instructions`. "
        "It replies when mentioned or replied to, or to every message in `always` mode, and only to admins unless access is `everyone`. "
        "It can react, remember what you ask it to, and look at images and link previews when images are on. "
        "Mode, access, images and mentions can differ by channel, and a channel's instructions and memories add to the server's. "
        "`/agent memory` lists what it remembers, and `/agent show` shows what applies where."
    )

def config():
    return (
        "Admins open `/config` to turn features on or off (green is on), pick the Storms and admin channels and the admin and Who Dis roles, "
        "and change the prefix for prefix commands. The server owner, and anyone with the admin role, counts as a GBot admin. "
        "Anyone can report a message or a member to the admins: right-click it, then **Apps → Report**. "
        "The report lands in the admin channel with the messages captured, where an admin marks it ✅ Handled or 🚫 Not an issue, and 🚩 Reports in `/config` shows everything reported about a member."
    )

def gcoin():
    return (
        "GCoin is GBot's currency, and your balance follows you to every server with GBot. "
        "Earn it in Storms and Who Dis, or from other members with `/gcoin send`. "
        "Spend it crafting and buying GTrade items, or betting in Storms. "
        "`/gcoin wallet` and `/gcoin history` show your balance and every transaction, and `/gcoin wallets` ranks the server."
    )

def gtrade():
    from GBotDiscord.src.gtrade.gtrade_cog import GTrade
    return (
        "Craft an item with `/gtrade craft`, attaching its image: you pay its value in GCoin, and that becomes its price. "
        f"You can hold up to {GTrade.NUM_MAX_ITEMS} items, with names up to {GTrade.MAX_ITEM_NAME_LENGTH} characters. "
        f"`/gtrade sell` with no user lists an item on the server's market for {GBotPropertiesManager.GTRADE_MARKET_SALE_TIMEOUT_HOURS} hours, and naming a user asks them to buy it. "
        "`/gtrade buy` works the other way round. "
        f"Requests last {GBotPropertiesManager.GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES} minutes and come with ✅ Accept, ❌ Decline and 🚫 Cancel buttons, and listings with 🛒 Buy. "
        "`/gtrade destroy` gives you the item's value back."
    )

def hype():
    return (
        "Admins manage matches with `/hype`: 💬 **Add reply** and 😀 **Add reaction** open a form for a pattern and what to answer with, and ✏️ **Edit** and 🗑️ **Delete** change one. "
        "When a message matches, GBot replies with one of its responses or reacts with one of its emoji, picked at random. "
        "Patterns are regular expressions, so `(?i)let'?s go` matches both \"lets go\" and \"LET'S GO\"."
    )

def music():
    return (
        "Join a voice channel and use `/music play` with a search, a YouTube link or a playlist. "
        f"Songs can be up to {GBotPropertiesManager.MUSIC_MAX_DURATION_MINUTES} minutes long, a playlist adds up to its first {GBotPropertiesManager.MUSIC_MAX_PLAYLIST_SONGS} songs, and the queue holds {GBotPropertiesManager.MUSIC_MAX_QUEUE_SONGS}. "
        "`/music queue` shows what's playing and what's next, and 🛗 elevator mode loops the whole queue. "
        "`/music spotify` plays along with what a member is listening to on Spotify, from YouTube. "
        f"GBot leaves after {GBotPropertiesManager.MUSIC_TIMEOUT_SECONDS // 60} minutes with nothing playing or nobody listening, except in elevator mode."
    )

def storms():
    from GBotDiscord.src.storms.storms_cog import Storms
    return (
        f"Every {hours(GBotPropertiesManager.STORMS_MIN_TIME_BETWEEN_SECONDS)} to {hours(GBotPropertiesManager.STORMS_MAX_TIME_BETWEEN_SECONDS)} hours, a Storm rolls into the Storms channel. "
        f"The first to use `/storms umbrella` starts it and earns **{presentation.formatGCoin(Storms.UMBRELLA_REWARD_GCOIN)} GCoin**. "
        "Then everyone races to guess a secret number from 1 to 200 with `/storms guess`, and each wrong guess gets a higher or lower hint. "
        f"The winner earns **{presentation.formatGCoin(Storms.GUESS_REWARD_GCOIN)} GCoin**, more for guessing fast: ⚡ 10x on your first guess, 5x on your second, 2.5x on your third and 1.25x on your fourth. "
        "`/storms bet` is a guess with GCoin on it: win and you earn your bet, with the same boost, or miss and lose it. "
        f"Storm messages clear themselves after {GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS} seconds."
    )

def whodis():
    from GBotDiscord.src.whodis.whodis_cog import WhoDis
    return (
        "`/whodis start` opts you in with the server's Who Dis role and pairs you with a random member who has it too. You chat in DMs through GBot, so neither of you knows who the other is. "
        f"Each of you gets one guess with `/whodis guess`: guess right and you win **{presentation.formatGCoin(WhoDis.BASE_REWARD_MULTIPLIER)} GCoin** for every member online, up to {presentation.formatGCoin(WhoDis.MAX_REWARD_GCOIN)}, but a wrong guess ends the game. "
        f"Games end after {GBotPropertiesManager.WHODIS_TIMEOUT_MINUTES} minutes, and you can start a new one {GBotPropertiesManager.WHODIS_COOLDOWN_MINUTES} minutes after starting the last. "
        "`/whodis leave` takes you out of future games, and `/whodis report` sends someone's recent messages to the admins."
    )

GUIDES = {'Agent': agent, 'Config': config, 'GCoin': gcoin, 'GTrade': gtrade, 'Hype': hype, 'Music': music, 'Storms': storms, 'Who Dis': whodis}

def guideFor(featureName):
    return GUIDES[featureName]()
