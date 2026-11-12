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
        "Admins set it up in `/agent`: 🔑 **Key** takes a Claude API key in a private form, ⚙️ **Settings** and 📝 **Instructions** shape it, and ♻️ **Reset** undoes them. "
        "It replies when mentioned or replied to, or to every message in `always` mode, and only to admins unless access is `everyone`. "
        "It can react, remember what you ask it to, and see images and link previews when images are on. "
        "With **abilities** at `read` it looks things up, at `safe` also plays music, sets reminders and guesses in Storms, and at `all` sends GCoin, trades, bets and changes settings, after a confirm only you can press, only as you could yourself. "
        "What only you should see comes as a 🔒 **Open** button, and Who Dis in your DMs. "
        "Mode, access, images, mentions and abilities can differ by channel, and a channel's instructions and memories add to the server's. "
        "Pick a channel on the card to see and change what applies there. 🧠 **Memories** lists what it remembers, and members get their own memories from `/agent` when memory access is everyone."
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
        "Earn it in Storms and Who Dis, or from other members, who send it with 💸 **Send** on their `/gcoin` wallet. "
        "Spend it crafting and buying GTrade items, or betting in Storms. "
        "`/gcoin` shows your wallet, or someone else's with `user`, and right-clicking a member, then **Apps → View wallet**, does too. "
        "📜 **History** lists every transaction, and 🏆 **Ranking** ranks this server and everyone everywhere."
    )

def gtrade():
    from GBotDiscord.src.gtrade.gtrade_cog import GTrade
    return (
        "`/gtrade` opens your items. ⚒️ **Craft** makes one from an image link, and to use an image you uploaded, right-click its message, then **Apps → Craft item**. You pay its value in GCoin, and that becomes its price. "
        f"You can hold up to {GTrade.NUM_MAX_ITEMS} items, with names up to {GTrade.MAX_ITEM_NAME_LENGTH} characters. "
        f"Pick an item to 🔎 **Show** it off, ✏️ **Rename** it, 💥 **Destroy** it for its value back, or 🏷️ **Sell** it: on the market for {GBotPropertiesManager.GTRADE_MARKET_SALE_TIMEOUT_HOURS} hours, or to one person. "
        "🏪 **Market** lists what's for sale here, 🤝 **Trades** every request and listing of yours still open, to answer or take back, and right-clicking a member, then **Apps → View items**, lets you ask to buy one of theirs. "
        f"Requests last {GBotPropertiesManager.GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES} minutes and come with ✅ Accept, ❌ Decline and 🚫 Cancel buttons, and listings with 🛒 Buy."
    )

def hype():
    return (
        "Admins manage matches with `/hype`: 💬 **Add reply** and 😀 **Add reaction** open a form for a pattern and what to answer with, ✏️ **Edit** and 🗑️ **Delete** change one, and 🧪 **Test** shows what a message would set off. "
        "When a message matches, GBot replies with one of its responses or reacts with one of its emoji, picked at random. "
        "Patterns are regular expressions, so `(?i)let'?s go` matches both \"lets go\" and \"LET'S GO\"."
    )

def music():
    return (
        "Join a voice channel and use `/music` with a search, a YouTube link or a playlist. "
        f"Songs can be up to {GBotPropertiesManager.MUSIC_MAX_DURATION_MINUTES} minutes long, a playlist adds up to its first {GBotPropertiesManager.MUSIC_MAX_PLAYLIST_SONGS} songs, and the queue holds {GBotPropertiesManager.MUSIC_MAX_QUEUE_SONGS}. "
        "The now-playing card updates itself as songs change, and anyone in GBot's voice channel can press it: ⏸️ pause, ⏮️ restart the song, ⏭️ skip, ⏹️ stop, 💿 add a song, 📜 the queue to move or remove songs, 🔀 shuffle, 🔁 elevator mode to loop the whole queue, and 🎧 follow a member's Spotify, played from YouTube. Elevator and Spotify turn green while they're on, and with nothing playing, `/music` offers 🎧 too. "
        f"`/music` on its own brings the card back down. GBot leaves after {GBotPropertiesManager.MUSIC_TIMEOUT_SECONDS // 60} minutes with nothing playing or nobody listening, except in elevator mode."
    )

def reminders():
    from GBotDiscord.src.reminders import reminders_cog
    from GBotDiscord.src.reminders.reminders_cog import Reminders
    return (
        "`/remind` on its own lists your reminders here: ➕ **New** asks when and what, then lets you pick how it repeats (every day, weekday, week, month or year, or on days you choose) and whether it comes here or by DM. "
        "Or set one straight away: `/remind when:tomorrow 9am what:call the dentist`. It reads times like \"in 2 hours\", \"tomorrow 9am\", \"Thursday 8pm\" and \"Dec 25 10:00\". "
        "🌍 **Time zone** is set once and follows you to every server, and changing it moves your reminders with you. "
        f"A reminder can be up to {reminders_cog.MAX_YEARS_AHEAD} years ahead, and you can have {Reminders.MAX_PER_PERSON} in each server. When one goes off, 💤 snoozes it, and a repeat can be skipped or stopped. "
        "Admins can also remind a role or everyone, and see everyone's reminders with 👥 **Server's**."
    )

def storms():
    from GBotDiscord.src.storms.storms_cog import Storms
    return (
        f"Every {hours(GBotPropertiesManager.STORMS_MIN_TIME_BETWEEN_SECONDS)} to {hours(GBotPropertiesManager.STORMS_MAX_TIME_BETWEEN_SECONDS)} hours, a Storm rolls into the Storms channel. "
        f"The first to press ☂️ **Umbrella** starts it and earns **{presentation.formatGCoin(Storms.UMBRELLA_REWARD_GCOIN)} GCoin**. "
        "Then everyone races to guess a secret number from 1 to 200 with 🎯 **Guess** or `/storms 42`, and each wrong guess gets a higher or lower hint that only the guesser sees. "
        f"The winner earns **{presentation.formatGCoin(Storms.GUESS_REWARD_GCOIN)} GCoin**, more for guessing fast: ⚡ 10x on your first guess, 5x on your second, 2.5x on your third and 1.25x on your fourth. "
        "🎲 **Bet**, or `/storms 42 5`, is a guess with GCoin on it: win and you earn your bet, with the same boost, or miss and lose it. "
        f"Storm messages clear themselves after {GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS} seconds."
    )

def whodis():
    from GBotDiscord.src.whodis.whodis_cog import WhoDis
    return (
        "🕵️ **Start a game** in `/whodis` opts you in with the server's Who Dis role and pairs you with a random member who has it too. You chat in DMs through GBot, so neither of you knows who the other is. "
        f"Each of you gets one guess with `/whodis user:<their name>`: guess right and you win **{presentation.formatGCoin(WhoDis.BASE_REWARD_MULTIPLIER)} GCoin** for every member online, up to {presentation.formatGCoin(WhoDis.MAX_REWARD_GCOIN)}, but a wrong guess ends the game. "
        f"Games end after {GBotPropertiesManager.WHODIS_TIMEOUT_MINUTES} minutes, and you can start a new one {GBotPropertiesManager.WHODIS_COOLDOWN_MINUTES} minutes after starting the last. "
        "The game's card in your DMs has 🛑 **End game** and 🚩 **Report**, which sends the other player's latest messages to the server's admins. When a game ends, 🕵️ **Play again** starts the next. 🚪 **Leave Who Dis** in `/whodis` ends your game and takes you out of future ones."
    )

GUIDES = {'Agent': agent, 'Config': config, 'GCoin': gcoin, 'GTrade': gtrade, 'Hype': hype, 'Music': music, 'Reminders': reminders, 'Storms': storms, 'Who Dis': whodis}

def guideFor(featureName):
    return GUIDES[featureName]()
