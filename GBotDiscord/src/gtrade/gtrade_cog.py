#region IMPORTS
import re
import logging
import asyncio
import nextcord
from nextcord.ext import commands, tasks
from nextcord.ext.commands.context import Context
from datetime import datetime
from decimal import Decimal, InvalidOperation

from GBotDiscord.src import presentation
from GBotDiscord.src import strings
from GBotDiscord.src import utils
from GBotDiscord.src import pagination
from GBotDiscord.src import predicates
from GBotDiscord.src.firebase import GBotFirebaseService
from GBotDiscord.src.gtrade import gtrade_queries
from GBotDiscord.src.gcoin import gcoin_queries
from GBotDiscord.src.exceptions import EnforceRealUsersError, EnforceSenderReceiverNotEqual, EnforcePositiveTransactions, EnforceSenderFundsError, ItemNameConflict, ItemNameTooLong, ItemNoLongerAvailable, ItemImageMissing, ItemImageInvalid, ItemMaxCount, NotSubscribed
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.config import config_queries
#endregion

TRADE_BUTTON_PREFIX = 'gtrade:'
TRADE_ACCEPT = 'accept'
TRADE_DECLINE = 'decline'
TRADE_CANCEL = 'cancel'
TRADE_BUY = 'buy'
TRADE_REQUEST = 'request'
# on one message standing for many trades: open the market, or answer every offer one member made another
TRADE_OPEN_MARKET = 'openmarket'
TRADE_ACCEPT_ALL = 'acceptall'
TRADE_DECLINE_ALL = 'declineall'
TRADE_CANCEL_ALL = 'cancelall'
TRADE_CHOOSE = 'choose'
TRADE_TAKE_DOWN_ALL = 'takedownall'
# on an item shown in the channel: taken away by whoever showed it, or whose it is
ITEM_CLOSE = 'closeitem'
MESSAGE_LIMIT = 2000
# what a trade's own message is told once the trade ends some other way than by its buttons
NOTE_GONE = '🚫 No longer available.'
NOTE_SOLD = '🎉 Sold.'
NOTE_EXPIRED = '⌛ Expired.'
# Ends told in a message of their own, which notifies whoever it names as an edit can't: a sale's
# announcement, or the expiry notice. Their trade's message goes rather than staying beside it saying it
# again, as does a message shared by several once all of its trades have ended.
TOLD_ANEW = (NOTE_SOLD, NOTE_EXPIRED)
EMBED_LIMIT = 4096
TRADE_MARKET = 'market'
ITEMS_PER_PAGE = 10

def imageIn(message):
    # (an uploaded image, or None, and a link to one, or None): what a message can be crafted from.
    # A link is checked by commonCraft, as one typed into the form is.
    image = next((attachment for attachment in message.attachments if (attachment.content_type or '').startswith('image/')), None)
    if image is not None:
        return image, None
    for embed in message.embeds:
        for part in (embed.image, embed.thumbnail):
            if getattr(part, 'url', None):
                return None, part.url
    link = re.search(r'https?://\S+', message.content or '')
    return None, link.group(0) if link else None

def summarise(results):
    # (an item's name, what was said of it), for several answered together. The same thing said of
    # many, as "insufficient funds" is, is said once with the items it was said of under it.
    if len(results) == 1:
        return results[0][1]
    said = {}
    for name, text in results:
        said.setdefault(text, []).append(name)
    lines = []
    for text, names in said.items():
        if len(names) > 1:
            lines.append(text + ''.join(f'\n• {name}' for name in names))
        else:
            # one that doesn't say which item it's about is told which
            lines.append(text if names[0] in text else f'{text} ({names[0]})')
    return '\n'.join(lines)

class Gathered(pagination.CardReply):
    # Many trades made in one go, as the agent's "sell all my items" is: what each would have posted is
    # kept instead, so one message says it all (GTrade.announceGathered) rather than one per item,
    # and nothing is posted while the trade lock is held.
    def __init__(self, interaction):
        super().__init__(interaction)
        # (the trade's id, market or request, its own line, the item's name, its price)
        self.trades = []
        # a trade completed there and then
        self.announced = []

class GTrade(commands.Cog):

    NUM_MAX_ITEMS = 100
    # how long trades that ended wait for others ending with them, so one message is changed once
    RETIRE_DELAY_SECONDS = 2
    RETIRE_LONGEST_SECONDS = 30
    # Discord's own limit on an autocomplete choice, and short enough that one listing can't push
    # a market page past what an embed can hold, which would break it for the whole server
    MAX_ITEM_NAME_LENGTH = 100

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()
        # Items and pending trades are read, checked and then written, and other commands can run during
        # each wait on the database. A command holds this from its first read to its last write, so two
        # can't both act on the same item. A craft can't hold it while waiting on a person.
        self.tradeLock = asyncio.Lock()
        # tidying trade messages, kept so they aren't dropped before they finish
        self.retiring = set()
        # {server: (trade, note) waiting to be tidied together}
        self.toRetire = {}

    # Events
    @commands.Cog.listener()
    async def on_guild_remove(self, guild: nextcord.Guild):
        self.logger.info(f'Deleting GTrade pending transactions in guild {guild.id} ({guild.name}).')
        await GBotFirebaseService.run(gtrade_queries.removeAllServerPendingTradeTransaction, guild.id)

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            self.remove_expired_transactions.start()
        except RuntimeError:
            self.logger.info('remove_expired_transactions task is already launched and is not completed.')

    def gather(self, interaction):
        # Made here rather than by whoever calls: the bot loads this module as its own copy, so a
        # Gathered made from another import of it wouldn't be one to this cog, and each trade would post.
        return Gathered(interaction)

    def bulkLine(self, item, price):
        return f'• {item} · {presentation.formatGCoin(price)} GCoin'

    def retireSoon(self, guild, trades, note):
        # Trades that ended some other way than by their own message's buttons, as taken down from
        # 🤝 Trades, by the agent, by expiring or by being bought from the market: their messages say
        # so and lose their buttons. Not waited for, and gathered for a moment first: those that end
        # together are often lines of one message, which has to be read and changed once, not once each.
        entries = [(trx, note) for trx in trades if trx.get('messageId')]
        if not entries or guild is None:
            return
        waiting = self.toRetire.setdefault(guild.id, [])
        waiting.extend(entries)
        if len(waiting) == len(entries):
            task = asyncio.create_task(self.retireWaiting(guild))
            self.retiring.add(task)
            task.add_done_callback(self.retiring.discard)

    def retireRelated(self, found, soldId = None):
        # Every trade for an item that was sold or destroyed, in each server it was open in, as
        # removeRelatedPendingTradeTransactionsChanges found them. Only the one sold is replaced by its
        # sale: the rest, other people's requests and offers among them, say they are gone.
        for serverId, trades in (found[0] if found else {}).items():
            guild = self.client.get_guild(int(serverId))
            for trx in trades:
                self.retireSoon(guild, [trx], NOTE_SOLD if soldId is not None and trx.get('trxId') == soldId else NOTE_GONE)

    async def retireWaiting(self, guild):
        # Until no more have come for a moment and nothing holds the trade lock: many taken down
        # together are one hold of the lock from first to last, however long a slow read stretches
        # the gap between two of them, and tidying in between showed their lines struck in stages.
        # Not for ever, as the lock is every server's.
        waited = 0
        while waited < self.RETIRE_LONGEST_SECONDS:
            count = len(self.toRetire.get(guild.id, []))
            await asyncio.sleep(self.RETIRE_DELAY_SECONDS)
            waited += self.RETIRE_DELAY_SECONDS
            if len(self.toRetire.get(guild.id, [])) == count and not self.tradeLock.locked():
                break
        await self.retire(guild, self.toRetire.pop(guild.id, []))

    async def retire(self, guild, entries):
        # entries: (the trade as it was, what its message is told)
        byMessage = {}
        for trx, note in entries:
            byMessage.setdefault((trx['messageChannelId'], trx['messageId']), []).append((trx, note))
        stillOpen = None
        for (channelId, messageId), ended in byMessage.items():
            try:
                # a thread too, as a trade can be made in one
                channel = guild.get_channel_or_thread(int(channelId))
                message = await channel.fetch_message(int(messageId))
                trx, note = ended[0]
                if not trx.get('messageShared'):
                    if note in TOLD_ANEW:
                        await message.delete()
                    else:
                        await message.edit(content = presentation.fitLines(message.content, MESSAGE_LIMIT, f'\n-# {note}'), view = None)
                    continue
                # one message for several: each that ended is struck through, and the buttons go with the last
                content = message.content
                for trx, _ in ended:
                    line = trx.get('messageLine') or self.bulkLine(trx['item']['name'], trx['item']['value'])
                    content = content.replace(f'{line}\n', f'~~{line}~~\n') if f'{line}\n' in content else content[:-len(line)] + f'~~{line}~~' if content.endswith(line) else content
                if stillOpen is None:
                    stillOpen = {trx.get('messageId') for trx in (await GBotFirebaseService.run(gtrade_queries.getAllServerPendingTradeTransactions, guild.id) or {}).values()}
                if messageId in stillOpen:
                    await message.edit(content = content)
                elif all(note in TOLD_ANEW for _, note in ended):
                    # the last of its trades ended, told in a message of its own
                    await message.delete()
                else:
                    await message.edit(content = content, view = None)
            except Exception as e:
                # a message deleted since, or a channel gone: there is nothing left to tidy
                self.logger.info(f'GBot GTrade left a trade message as it was in guild {guild.id}: {type(e).__name__}')

    def tradeButtons(self, trxId, kind):
        # the trade's id rides in each button, so they keep working after a restart
        # not auto-deferred, and stopped once sent: on_interaction answers every click, so these never
        # sit in nextcord's view store, where they would answer first and stay until a restart
        view = nextcord.ui.View(timeout = None, auto_defer = False)
        if kind == TRADE_MARKET:
            buttons = [('Buy', '🛒', nextcord.ButtonStyle.success, TRADE_BUY), ('Take down', '🚫', nextcord.ButtonStyle.secondary, TRADE_CANCEL)]
        else:
            buttons = [('Accept', '✅', nextcord.ButtonStyle.success, TRADE_ACCEPT), ('Decline', '❌', nextcord.ButtonStyle.danger, TRADE_DECLINE), ('Cancel', '🚫', nextcord.ButtonStyle.secondary, TRADE_CANCEL)]
        for label, emoji, style, action in buttons:
            view.add_item(nextcord.ui.Button(label = label, emoji = emoji, style = style, custom_id = f'{TRADE_BUTTON_PREFIX}{action}:{trxId}'))
        return view

    async def announce(self, context, text, **kwargs):
        # A trade, a listing or a craft is a moment the other person has to see, so from a private
        # card it still goes to the channel. A button or a command answers where it was asked.
        if isinstance(context, Gathered):
            context.announced.append(text)
            return None
        target = context.channel if isinstance(context, pagination.CardReply) else context
        return await target.send(text, **kwargs)

    async def sendWithTradeButtons(self, context, text, trxId, kind, item = None, price = None, guild = None):
        if isinstance(context, Gathered):
            context.trades.append((trxId, kind, text, item, price))
            return
        view = self.tradeButtons(trxId, kind)
        try:
            message = await self.announce(context, text, view = view)
        finally:
            view.stop()
        await GBotFirebaseService.run(gtrade_queries.setTradeMessage, (guild or context.guild).id, trxId, message.channel.id, message.id)

    async def announceGathered(self, gathered, author, user):
        # One message for everything a Gathered kept, posted once the trade lock is free. A lone trade
        # keeps its own message and buttons. Several listings share one with a button to the market,
        # where each is bought, and several offers to one member share one they answer together.
        channel = gathered.channel
        if gathered.announced:
            await channel.send(presentation.fitLines('\n'.join(gathered.announced), MESSAGE_LIMIT))
        if len(gathered.trades) == 1:
            trxId, kind, text, _, _ = gathered.trades[0]
            await self.sendWithTradeButtons(channel, text, trxId, kind, guild = gathered.guild)
        elif gathered.trades:
            listed = '\n'.join(self.bulkLine(item, price) for _, _, _, item, price in gathered.trades)
            count = len(gathered.trades)
            if user is None:
                text = f'🏷️ {author.mention} put {count} items up for sale:\n{listed}'
                buttons = [pagination.persistentButton('Market', '🏪', nextcord.ButtonStyle.success, f'{TRADE_BUTTON_PREFIX}{TRADE_OPEN_MARKET}:all'),
                           pagination.persistentButton('Take all down', '🚫', nextcord.ButtonStyle.secondary, f'{TRADE_BUTTON_PREFIX}{TRADE_TAKE_DOWN_ALL}:{author.id}-')]
            else:
                text = f'🤝 {user.mention}, {author.mention} wants to sell you {count} items:\n{listed}'
                pair = f'{author.id}-{user.id}'
                buttons = [pagination.persistentButton('Accept all', '✅', nextcord.ButtonStyle.success, f'{TRADE_BUTTON_PREFIX}{TRADE_ACCEPT_ALL}:{pair}'),
                           pagination.persistentButton('Decline all', '❌', nextcord.ButtonStyle.danger, f'{TRADE_BUTTON_PREFIX}{TRADE_DECLINE_ALL}:{pair}'),
                           pagination.persistentButton('Cancel all', '🚫', nextcord.ButtonStyle.secondary, f'{TRADE_BUTTON_PREFIX}{TRADE_CANCEL_ALL}:{pair}'),
                           # all is only the shortcut: each offer is its own trade, answered one at a time here
                           pagination.persistentButton('Choose', '🔎', nextcord.ButtonStyle.primary, f'{TRADE_BUTTON_PREFIX}{TRADE_CHOOSE}:{pair}')]
            view = pagination.persistentView(buttons)
            try:
                message = await channel.send(presentation.fitLines(text, MESSAGE_LIMIT), view = view)
            finally:
                view.stop()
            def remember():
                for trxId, _, _, item, price in gathered.trades:
                    gtrade_queries.setTradeMessage(gathered.guild.id, trxId, message.channel.id, message.id, True, self.bulkLine(item, price))
            await GBotFirebaseService.run(remember)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: nextcord.Interaction):
        customId = (interaction.data or {}).get('custom_id', '') if interaction.type == nextcord.InteractionType.component else ''
        if customId.startswith(TRADE_BUTTON_PREFIX):
            action, trxId = customId[len(TRADE_BUTTON_PREFIX):].split(':', 1)
            if action == ITEM_CLOSE:
                await self.answerCloseItem(interaction, trxId)
            elif action == TRADE_OPEN_MARKET:
                await self.answerMarketButton(interaction)
            elif action in (TRADE_ACCEPT_ALL, TRADE_DECLINE_ALL, TRADE_CANCEL_ALL, TRADE_TAKE_DOWN_ALL):
                await self.answerOffersButton(interaction, action, trxId)
            elif action == TRADE_CHOOSE:
                await self.answerChooseButton(interaction, trxId)
            else:
                await self.answerTradeButton(interaction, action, trxId)

    async def showItem(self, channel, shower, owner, item, send = None):
        # 🔎 Show: the item's card in the channel, for everyone, with a ✖️ for whoever showed it or
        # whose it is, as a card in the channel is otherwise there for good. send: how it's posted,
        # for the agent, whose card is a reply to the message that asked.
        view = pagination.persistentView([pagination.persistentButton('Close', '✖️', nextcord.ButtonStyle.secondary, f"{TRADE_BUTTON_PREFIX}{ITEM_CLOSE}:{shower.id}-{getattr(owner, 'id', '')}")])
        try:
            return await (send or channel.send)(embed = self.itemEmbed(owner, item), view = view)
        finally:
            view.stop()

    async def answerCloseItem(self, interaction: nextcord.Interaction, allowed):
        if str(interaction.user.id) not in allowed.split('-'):
            await interaction.send('Only whoever showed this item, or its owner, can close it.', ephemeral = True)
            return
        await interaction.response.defer()
        try:
            await interaction.message.delete()
        except nextcord.HTTPException:
            # gone already
            pass

    async def mayPress(self, interaction):
        # A click skips the commands' own checks, so they are made here. Says why not, privately.
        try:
            # a trade offered before a trial ended can still be answered during the grace days
            await predicates.ensureSubscribed(interaction.guild, interaction.user, allowEnded = True)
        except NotSubscribed:
            await interaction.send('GBot is not active in this server.', ephemeral = True)
            return False
        if await GBotFirebaseService.run(config_queries.getServerValue, interaction.guild.id, 'toggle_gtrade') == False:
            await interaction.send('GTrade is turned off in this server.', ephemeral = True)
            return False
        return True

    async def answerMarketButton(self, interaction: nextcord.Interaction):
        # under a message listing several items for sale: the market, privately, for whoever pressed.
        # Acknowledged first, as the database waits below can outlast Discord's 3 seconds, with GBot
        # shown thinking, privately, until the card replaces it.
        await interaction.response.defer(ephemeral = True, with_message = True)
        if await self.mayPress(interaction):
            await self.openMarket(interaction, interaction.user)

    async def answerChooseButton(self, interaction: nextcord.Interaction, pair):
        # under a message offering one member several items: those offers, privately, to answer one at a time
        await interaction.response.defer(ephemeral = True, with_message = True)
        if not await self.mayPress(interaction):
            return
        sellerId, _, buyerId = pair.partition('-')
        if str(interaction.user.id) not in (sellerId, buyerId):
            await interaction.send("These buttons aren't for you.", ephemeral = True)
            return
        await self.openTrades(interaction, interaction.user, (sellerId, buyerId))

    async def acknowledge(self, interaction, picker = None, privateMessagesAllowed = False):
        # A press on a private GTrade card, checked again as its command would be. Given the list it
        # stays on, it says it's working at once (pagination.WORKING), as what follows can wait on the
        # trade lock behind a bulk sale; a refused one puts the list back as it was.
        if picker is None:
            await interaction.response.defer()
        else:
            await picker.working(interaction)
        try:
            await predicates.recheck(interaction, feature = 'toggle_gtrade', privateMessagesAllowed = privateMessagesAllowed)
        except Exception:
            if picker is not None:
                picker.notice = None
                await picker.show(interaction)
            raise

    def tradeLine(self, guild, me, trx):
        # one open trade, as the member it's shown to reads it: ⬅️ theirs to answer, ➡️ theirs to take back
        nameOf = lambda userId: nextcord.utils.escape_markdown(getattr(guild.get_member(int(userId)), 'display_name', 'Unknown user'))
        name = f"**{nextcord.utils.escape_markdown(trx['item']['name'])}**"
        price = f"`{presentation.formatGCoin(trx['item']['value'])} GCoin`"
        if trx['trxType'] == 'market':
            return f'🏷️ {name} is on the market · {price}'
        if trx['trxType'] == 'buy':
            return f"⬅️ {nameOf(trx['buyerId'])} wants to buy your {name} · {price}" if trx['sellerId'] == me else f"➡️ You asked to buy {name} from {nameOf(trx['sellerId'])} · {price}"
        return f"⬅️ {nameOf(trx['sellerId'])} wants to sell you {name} · {price}" if trx.get('buyerId') == me else f"➡️ You offered {name} to {nameOf(trx['buyerId'])} · {price}"

    def tradesOf(self, pending, me, pair = None):
        # [(trxId, trade)] open here that are this member's, as 🤝 Trades lists them and the agent reads
        # them: what waits on them first, then by name. pair: only the offers one member made another.
        if pair is not None:
            trades = [(trxId, trx) for trxId, trx in pending.items() if trx['trxType'] == 'sell' and (trx['sellerId'], trx.get('buyerId')) == pair]
        else:
            trades = [(trxId, trx) for trxId, trx in pending.items() if me in (trx['sellerId'], trx.get('buyerId'))]
        return sorted(trades, key = lambda entry: (not self.isTheirsToAnswer(me, entry[1]), entry[1]['item']['name'].lower()))

    def isTheirsToAnswer(self, me, trx):
        # a request someone else made them, rather than one of their own or their listing
        return trx['trxType'] != 'market' and (trx['buyerId'] if trx['trxType'] == 'buy' else trx['sellerId']) != me

    async def openTrades(self, context, author, pair = None):
        # 🤝 Trades: every trade still open here that is this member's, to answer or to take back, so
        # none depends on finding the message it was made in. Each is its own trade, so any may be
        # taken and the rest left. pair: only the offers one member made another, as 🔎 Choose opens.
        guild = context.guild
        me = str(author.id)
        found = []

        async def listed():
            pending = await GBotFirebaseService.run(gtrade_queries.getAllServerPendingTradeTransactions, guild.id) or {}
            trades = self.tradesOf(pending, me, pair)
            found[:] = trades
            lines = [f'**{number}.** {self.tradeLine(guild, me, trx)}' for number, (_, trx) in enumerate(trades, start = 1)]
            choices = [{'label': trx['item']['name'], 'description': self.tradeLine(guild, me, trx).split(' ', 1)[1].replace('**', '').replace('`', '').replace('\\', '')[:100], 'emoji': '🖼️'} for _, trx in trades]
            return lines, choices

        async def answer(picker, pressed, index, action):
            await self.acknowledge(pressed, picker)
            trxId, trx = found[index]
            name = trx['item']['name']
            kind = trx['trxType']
            theirs = self.isTheirsToAnswer(me, trx)
            reply = pagination.CardReply(pressed)
            async with self.tradeLock:
                other = guild.get_member(int(trx['buyerId'] if kind == 'buy' else trx['sellerId'])) if theirs else None
                if await GBotFirebaseService.run(gtrade_queries.getPendingTradeTransactionWithId, guild.id, trxId) is None or (action == TRADE_ACCEPT and theirs and other is None):
                    notice = f"⌛ The trade for '{name}' is no longer available."
                elif theirs and action == TRADE_CANCEL:
                    notice = f"❌ '{name}' is theirs to take back. ✅ **Accept** or ❌ **Decline** it."
                elif not theirs and action != TRADE_CANCEL:
                    notice = f"❌ '{name}' is your own, waiting on someone else. 🚫 **Cancel** takes it back."
                elif action == TRADE_ACCEPT:
                    # the same code as the card's buy and sell, which check everything again and move the GCoin
                    if kind == 'buy':
                        await self.sellUnderLock(reply, pressed.user, name, other, accepting = True)
                    else:
                        await self.buyUnderLock(reply, pressed.user, name, other)
                    notice = reply.notice or f"🎉 You {'sold' if kind == 'buy' else 'bought'} '{name}'."
                else:
                    await GBotFirebaseService.run(gtrade_queries.removePendingTradeTransaction, guild.id, trxId)
                    self.retireSoon(guild, [trx], NOTE_GONE)
                    notice = f"❌ You declined '{name}'." if action == TRADE_DECLINE else f"🚫 '{name}' is no longer for sale." if kind == 'market' else f"🚫 You took back your request for '{name}'."
            picker.replace(*await listed())
            await picker.redraw(pressed, notice)

        answering = lambda action: (lambda picker, pressed, index: answer(picker, pressed, index, action))
        if pair is None:
            title, empty = '🤝 Your trades', 'You have no open trades here. ⬅️ ones wait on you, and ➡️ ones are your own.'
        else:
            other = guild.get_member(int(pair[1] if me == pair[0] else pair[0]))
            title, empty = f"🤝 Offers between you and {getattr(other, 'display_name', 'Unknown user')}", 'None of these offers are still open.'
        source = pagination.DescriptionPageSource([], title, presentation.BRAND_COLOR, guild.icon.url if guild.icon is not None else None, ITEMS_PER_PAGE, empty = empty)
        lines, choices = await listed()
        source.entries = lines
        actions = [pagination.Action('Accept', '✅', nextcord.ButtonStyle.success, answering(TRADE_ACCEPT), needsSelection = True),
                   pagination.Action('Decline', '❌', nextcord.ButtonStyle.danger, answering(TRADE_DECLINE), needsSelection = True),
                   pagination.Action('Cancel', '🚫', nextcord.ButtonStyle.secondary, answering(TRADE_CANCEL), needsSelection = True)]
        await pagination.startPages(context, pagination.ListPicker(source, choices, actions, 'Choose a trade…'), ephemeral = True)

    async def showWorking(self, interaction):
        # A trade message's press, answered at once by the message saying it's on it, as what follows
        # waits on the trade lock, behind a bulk sale for as long as that takes. Returns the message's
        # words as they were, for whatever replaces them, or puts back if nothing happens.
        before = interaction.message.content
        await interaction.response.edit_message(content = presentation.fitLines(before, MESSAGE_LIMIT, f'\n-# {pagination.WORKING}'))
        return before

    async def stopWorking(self, interaction, before):
        # nothing happened after all, as a press refused: the message as it was, buttons and all
        try:
            await interaction.message.edit(content = before)
        except nextcord.HTTPException:
            pass

    async def answerOffersButton(self, interaction: nextcord.Interaction, action, pair):
        # Under a message offering one member several items: every offer still open from that seller
        # to that buyer, answered together, with one message saying what happened to each. Under one
        # listing several: every listing of that seller's still up, taken down by them.
        guild = interaction.guild
        sellerId, _, buyerId = pair.partition('-')
        if str(interaction.user.id) != (sellerId if action in (TRADE_CANCEL_ALL, TRADE_TAKE_DOWN_ALL) else buyerId):
            await interaction.response.send_message("These buttons aren't for you.", ephemeral = True)
            return
        before = await self.showWorking(interaction)
        if not await self.mayPress(interaction):
            await self.stopWorking(interaction, before)
            return
        gathered = Gathered(interaction)
        async with self.tradeLock:
            pending = await GBotFirebaseService.run(gtrade_queries.getAllServerPendingTradeTransactions, guild.id) or {}
            if action == TRADE_TAKE_DOWN_ALL:
                offers = [(trxId, trx) for trxId, trx in pending.items() if trx['trxType'] == 'market' and trx['sellerId'] == sellerId]
            else:
                offers = [(trxId, trx) for trxId, trx in pending.items() if trx['trxType'] == 'sell' and trx['sellerId'] == sellerId and trx.get('buyerId') == buyerId]
            seller = guild.get_member(int(sellerId))
            if not offers or (action == TRADE_ACCEPT_ALL and seller is None):
                await self.stopWorking(interaction, before)
                await self.endTradeButtons(interaction, '⌛ These are no longer available.')
                return
            refused = []
            for trxId, trx in offers:
                if action == TRADE_ACCEPT_ALL:
                    # the same code as the card's buy, which checks everything again and moves the GCoin
                    said = len(gathered.notices)
                    await self.buyUnderLock(gathered, interaction.user, trx['item']['name'], seller)
                    refused += [(trx['item']['name'], notice) for notice in gathered.notices[said:]]
                else:
                    await GBotFirebaseService.run(gtrade_queries.removePendingTradeTransaction, guild.id, trxId)
        if action != TRADE_ACCEPT_ALL:
            # this message says so itself below; any of them announced in another is told there
            self.retireSoon(guild, [trx for _, trx in offers if trx.get('messageId') != str(interaction.message.id)], NOTE_GONE)
        try:
            if action == TRADE_ACCEPT_ALL:
                # one refused, as for too little GCoin, stays open with its buttons
                if not gathered.notices:
                    # every one sold, each announced below, so the offer goes rather than staying beside them
                    await interaction.message.delete()
                else:
                    # some refused stay open, with their buttons
                    await self.stopWorking(interaction, before)
                if gathered.announced:
                    await interaction.channel.send(presentation.fitLines('\n'.join(gathered.announced), MESSAGE_LIMIT))
                if gathered.notices:
                    # as a single Accept answers them: privately, to whoever pressed
                    await interaction.send(presentation.fitLines(summarise(refused), MESSAGE_LIMIT), ephemeral = True)
            else:
                word = 'declined' if action == TRADE_DECLINE_ALL else 'took down' if action == TRADE_TAKE_DOWN_ALL else 'cancelled'
                await interaction.message.edit(content = presentation.fitLines(before, MESSAGE_LIMIT, f"\n-# {'❌' if action == TRADE_DECLINE_ALL else '🚫'} {interaction.user.mention} {word} these."), view = None)
        except nextcord.HTTPException:
            pass

    async def answerTradeButton(self, interaction: nextcord.Interaction, action, trxId):
        # acknowledged straight away, as Discord allows 3 seconds and this waits on the database and the
        # trade lock
        before = await self.showWorking(interaction)
        guild = interaction.guild
        if not await self.mayPress(interaction):
            await self.stopWorking(interaction, before)
            return
        async with self.tradeLock:
            trx = await GBotFirebaseService.run(gtrade_queries.getPendingTradeTransactionWithId, guild.id, trxId)
            if trx is None:
                await self.stopWorking(interaction, before)
                await self.endTradeButtons(interaction, '⌛ This trade is no longer available.')
                return
            kind = trx['trxType']
            userId = str(interaction.user.id)
            requesterId = trx['buyerId'] if kind == 'buy' else trx['sellerId']
            answererId = trx['sellerId'] if kind == 'buy' else trx.get('buyerId')
            allowed = {
                TRADE_ACCEPT: kind != 'market' and userId == answererId,
                TRADE_DECLINE: kind != 'market' and userId == answererId,
                TRADE_CANCEL: userId == requesterId,
                TRADE_BUY: kind == 'market' and userId != trx['sellerId']
            }.get(action, False)
            if not allowed:
                await self.stopWorking(interaction, before)
                await interaction.send("These buttons aren't for you.", ephemeral = True)
                return
            item = trx['item']['name']
            if action in (TRADE_DECLINE, TRADE_CANCEL):
                await GBotFirebaseService.run(gtrade_queries.removePendingTradeTransaction, guild.id, trxId)
                word = 'declined' if action == TRADE_DECLINE else 'taken down' if kind == 'market' else 'cancelled'
                await interaction.message.edit(content = f"{before}\n-# {'❌' if action == TRADE_DECLINE else '🚫'} {interaction.user.mention} {word} this.", view = None)
                return
            other = guild.get_member(int(requesterId if action == TRADE_ACCEPT else trx['sellerId']))
            if other is None:
                await self.stopWorking(interaction, before)
                await self.endTradeButtons(interaction, '⌛ This trade is no longer available, as the other person left.')
                return
            # the same code as the card's buy and sell, which re-check everything and move the GCoin
            if kind == 'buy':
                await self.sellUnderLock(interaction, interaction.user, item, other, accepting = True)
            else:
                await self.buyUnderLock(interaction, interaction.user, item, other)
            if await GBotFirebaseService.run(gtrade_queries.getPendingTradeTransactionWithId, guild.id, trxId) is None:
                # sold: the sale is announced in a message of its own, so the trade's goes rather than staying beside it
                try:
                    await interaction.message.delete()
                except nextcord.HTTPException:
                    pass
            else:
                # refused, as for too little GCoin, and said privately: the trade stays open as it was
                await self.stopWorking(interaction, before)

    async def endTradeButtons(self, interaction, text):
        await interaction.send(text, ephemeral = True)
        try:
            await interaction.message.edit(view = None)
        except nextcord.HTTPException:
            pass

    # Tasks
    @tasks.loop(minutes=1)
    async def remove_expired_transactions(self):
        try:
            currentTime = datetime.now()
            # what expired, by the channel it was asked in and whose it was: one message for each, as
            # twenty offers made together expire together
            expired = {}
            allServersTransactionsMap = await GBotFirebaseService.run(gtrade_queries.getAllTradeTransactions)
            if allServersTransactionsMap != None:
                for serverId, serverTransactionMap in allServersTransactionsMap.items():
                    # both bots share one Firebase project, and each may only expire its own
                    # guilds' trades: the other's channels are out of reach, so the entry would be
                    # deleted without its owner ever being told
                    if self.client.get_guild(int(serverId)) is None:
                        continue
                    for trxId, trx in serverTransactionMap.items():
                        # one bad transaction stays its own: this used to abort the pass, so nothing after it expired
                        try:
                            trxType = trx['trxType']
                            item = trx['item']
                            itemName = item['name']
                            timePosted = datetime.strptime(trx['timePosted'], "%m/%d/%y %I:%M:%S %p")
                            secondsLater = (currentTime - timePosted).total_seconds()
                            minutesLater = secondsLater / 60
                            hoursLater = minutesLater / 60
                            userId = ''
                            trxStr = ''
                            # what it was, and with whom, for many expired together: each such group is said once
                            group = ''
                            isExpired = False
                            if trxType == 'market':
                                if hoursLater >= GBotPropertiesManager.GTRADE_MARKET_SALE_TIMEOUT_HOURS:
                                    isExpired = True
                                    userId = trx['sellerId']
                                    trxStr = f"market sale for '{itemName}' has expired after {GBotPropertiesManager.GTRADE_MARKET_SALE_TIMEOUT_HOURS} hours."
                                    group = f'Market sales, after {GBotPropertiesManager.GTRADE_MARKET_SALE_TIMEOUT_HOURS} hours:'
                            else:
                                if minutesLater >= GBotPropertiesManager.GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES:
                                    isExpired = True
                                    buyerId = trx['buyerId']
                                    sellerId = trx['sellerId']
                                    if trxType == 'buy':
                                        userId = buyerId
                                        trxStr = f"buy request for '{itemName}' from {utils.idToUserStr(sellerId)} has expired after {GBotPropertiesManager.GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES} minutes."
                                        group = f'Requests to buy from {utils.idToUserStr(sellerId)}, after {GBotPropertiesManager.GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES} minutes:'
                                    elif trxType == 'sell':
                                        userId = sellerId
                                        trxStr = f"sell request for '{itemName}' to {utils.idToUserStr(buyerId)} has expired after {GBotPropertiesManager.GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES} minutes."
                                        group = f'Offers to {utils.idToUserStr(buyerId)}, after {GBotPropertiesManager.GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES} minutes:'
                            if isExpired:
                                async with self.tradeLock:
                                    await GBotFirebaseService.run(gtrade_queries.removePendingTradeTransaction, serverId, trxId)
                                expired.setdefault((trx['sourceChannelId'], userId), []).append((trxStr, group, itemName))
                                self.retireSoon(self.client.get_guild(int(serverId)), [trx], NOTE_EXPIRED)
                        except Exception as e:
                            self.logger.error(f'Error in GTrade.remove_expired_transactions() for transaction {trxId} in guild {serverId}: {e}')
            for (channelId, userId), lines in expired.items():
                try:
                    channel: nextcord.TextChannel = await self.client.fetch_channel(int(channelId))
                    if len(lines) == 1:
                        await presentation.sendError(channel, f'Sorry {utils.idToUserStr(userId)}, your {lines[0][0]}')
                    else:
                        # each kind said once, with the items under it, rather than a sentence for each
                        groups = {}
                        for _, group, itemName in lines:
                            groups.setdefault(group, []).append(itemName)
                        listed = '\n'.join(group + ''.join(f'\n• {itemName}' for itemName in itemNames) for group, itemNames in groups.items())
                        await presentation.sendError(channel, presentation.fitLines(f'Sorry {utils.idToUserStr(userId)}, {len(lines)} of your trades expired.\n{listed}', EMBED_LIMIT))
                except Exception as e:
                    self.logger.error(f'Error in GTrade.remove_expired_transactions() telling {userId} in channel {channelId}: {e}')
        except Exception as e:
            self.logger.error(f'Error in GTrade.remove_expired_transactions(): {e}')

    # Commands
    @nextcord.slash_command(name = strings.GTRADE_NAME, description = strings.GTRADE_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', True, True)
    async def gtradeSlash(self, interaction: nextcord.Interaction):
        await self.commonGTrade(interaction)

    @commands.command(name = strings.GTRADE_NAME, aliases = strings.GTRADE_ALIASES, brief = "- " + strings.GTRADE_BRIEF, description = strings.GTRADE_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', True)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', True)
    @predicates.isGuildOrUserSubscribed()
    async def gtrade(self, ctx: Context):
        await self.commonGTrade(ctx)

    async def commonGTrade(self, context):
        # private: what you own, what you could sell, and what's waiting on you
        await pagination.openPrivately(context, '🏪', 'Your items', self.openItems, feature = 'toggle_gtrade')

    @nextcord.user_command(name = strings.GTRADE_VIEW_ITEMS_NAME, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', False, True)
    async def viewItems(self, interaction: nextcord.Interaction, member: nextcord.Member):
        if member.bot:
            await presentation.sendError(interaction, f'Sorry {interaction.user.mention}, bots don\'t have items.', feature = 'GTrade')
            return
        await self.openItems(interaction, interaction.user, member)

    @nextcord.message_command(name = strings.GTRADE_CRAFT_ITEM_NAME, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', True, True)
    async def craftItem(self, interaction: nextcord.Interaction, message: nextcord.Message):
        # A form can't take an upload, so an uploaded image is crafted from its message instead, as is a
        # link to one in it
        image, imageUrl = imageIn(message)
        if image is None and imageUrl is None:
            await presentation.sendError(interaction, f'Sorry {interaction.user.mention}, that message has no image to craft from. Right-click a message with an uploaded image or a link to one, or use ⚒️ **Craft** in `/gtrade` with a link.', feature = 'GTrade')
            return
        async def submit(submitted, values):
            await submitted.response.defer(ephemeral = True)
            await predicates.recheck(submitted, feature = 'toggle_gtrade', privateMessagesAllowed = True)
            reply = pagination.CardReply(submitted)
            await self.commonCraft(reply, submitted.user, values[0], values[1], image, imageUrl)
            await submitted.send(reply.notice or '🔨 Crafted.', ephemeral = True)
        await interaction.response.send_modal(self.craftForm('Craft from this image', submit, withLink = False))

    def craftForm(self, title, onSubmit, withLink = True):
        fields = [pagination.Field('Name', placeholder = 'Gravity Hammer', maxLength = self.MAX_ITEM_NAME_LENGTH), pagination.Field('Value in GCoin', placeholder = '25.00', maxLength = 20)]
        if withLink:
            fields.append(pagination.Field('Image link', placeholder = 'https://…/hammer.png', maxLength = 1000))
        return pagination.Form(title, fields, onSubmit)

    async def openItems(self, context, author, owner = None):
        # Your own items to act on, or someone else's to look at and ask to buy. Opened by /gtrade, its
        # one-liner and right-click → View items.
        owner = owner or author
        isOwn = owner.id == author.id
        guild = context.guild
        await presentation.deferIfSlash(context, ephemeral = True)
        itemIds = []
        itemNames = []

        async def listed():
            items = await GBotFirebaseService.run(gtrade_queries.getAllUserItems, owner.id) or {}
            listings = await GBotFirebaseService.run(gtrade_queries.getAllServerPendingTradeTransactions, guild.id) if guild else None
            forSale = {trx['item']['name'] for trx in (listings or {}).values() if trx['trxType'] == 'market' and trx['sellerId'] == str(owner.id)}
            ranked = sorted(items.items(), key = lambda entry: utils.roundDecimalPlaces(entry[1]['value'], 2), reverse = True)
            itemIds[:] = [itemId for itemId, _ in ranked]
            itemNames[:] = [item['name'] for _, item in ranked]
            lines = [f"**{number}.** 🖼️ **{nextcord.utils.escape_markdown(item['name'])}** · `{presentation.formatGCoin(item['value'])} GCoin`{' · 🏷️ for sale' if item['name'] in forSale else ''}" for number, (_, item) in enumerate(ranked, start = 1)]
            choices = [{'label': item['name'], 'description': f"{presentation.formatGCoin(item['value'])} GCoin{' · for sale' if item['name'] in forSale else ''}", 'emoji': '🖼️'} for _, item in ranked]
            return lines, choices

        async def reload(picker, interaction, notice):
            picker.replace(*await listed())
            await picker.redraw(interaction, notice)

        async def acknowledge(interaction, picker = None):
            # Discord allows 3 seconds, and what follows waits on the database, and can wait on the trade
            # lock behind a bulk sale. Given the list, it says it's working rather than only deferring.
            await self.acknowledge(interaction, picker, privateMessagesAllowed = True)

        async def show(picker, interaction, index):
            # public, so it can be shown off
            await acknowledge(interaction, picker)
            itemTuple = await GBotFirebaseService.run(gtrade_queries.getUserItem, owner.id, itemNames[index])
            if itemTuple is None:
                await reload(picker, interaction, f"❌ '{itemNames[index]}' isn't {'yours' if isOwn else 'theirs'} any more.")
                return
            await self.showItem(interaction.channel, interaction.user, owner, itemTuple[1])
            await picker.redraw(interaction, f"🔎 '{itemNames[index]}' is shown in the channel.")

        async def sell(picker, interaction, index):
            await acknowledge(interaction)
            await self.openSale(interaction, author, itemNames[index])

        async def rename(picker, interaction, index):
            current = itemNames[index]
            async def submit(submitted, values):
                await acknowledge(submitted, picker)
                reply = pagination.CardReply(submitted)
                await self.commonRename(reply, author, current, values[0])
                await reload(picker, submitted, reply.notice)
            await interaction.response.send_modal(pagination.Form(f'Rename {current}', [pagination.Field('New name', default = current, maxLength = self.MAX_ITEM_NAME_LENGTH)], submit))

        async def destroy(picker, interaction, index):
            await acknowledge(interaction, picker)
            async with self.tradeLock:
                text = await self.destroyUnderLock(author, itemNames[index])
            await reload(picker, interaction, text)

        async def craft(picker, interaction, index):
            async def submit(submitted, values):
                await acknowledge(submitted, picker)
                reply = pagination.CardReply(submitted)
                await self.commonCraft(reply, author, values[0], values[1], None, values[2])
                await reload(picker, submitted, reply.notice)
            await interaction.response.send_modal(self.craftForm('Craft an item', submit))

        async def market(picker, interaction, index):
            await acknowledge(interaction)
            await self.openMarket(interaction, author)

        async def trades(picker, interaction, index):
            await acknowledge(interaction)
            await self.openTrades(interaction, author)

        async def askToBuy(picker, interaction, index):
            await acknowledge(interaction, picker)
            reply = pagination.CardReply(interaction)
            await self.commonBuy(reply, author, itemNames[index], owner)
            await picker.redraw(interaction, reply.notice or '🤝 Asked in the channel.')

        lines, choices = await listed()
        if isOwn:
            title = f'🏪 Your items · {len(lines)} of {self.NUM_MAX_ITEMS}'
            empty = 'You don\'t have any items yet. Press ⚒️ **Craft** to make one.'
            actions = [pagination.Action('Show', '🔎', nextcord.ButtonStyle.primary, show, needsSelection = True)]
            if guild is not None:
                actions.append(pagination.Action('Sell', '🏷️', nextcord.ButtonStyle.success, sell, needsSelection = True))
            actions += [
                pagination.Action('Rename', '✏️', nextcord.ButtonStyle.primary, rename, needsSelection = True),
                pagination.Action('Destroy', '💥', nextcord.ButtonStyle.danger, destroy, needsSelection = True, confirm = 'Destroy for good'),
                pagination.Action('Craft', '⚒️', nextcord.ButtonStyle.success, craft, row = 3)]
            if guild is not None:
                actions.append(pagination.Action('Market', '🏪', nextcord.ButtonStyle.secondary, market, row = 3))
                actions.append(pagination.Action('Trades', '🤝', nextcord.ButtonStyle.secondary, trades, row = 3))
            fields = [{'name': 'Tip', 'value': 'To craft from an image you uploaded, right-click its message, then **Apps → Craft item**.'}]
        else:
            title = f"🏪 {owner.display_name}'s items · {len(lines)}"
            empty = f'{owner.display_name} doesn\'t have any items yet.'
            actions = [
                pagination.Action('Show', '🔎', nextcord.ButtonStyle.primary, show, needsSelection = True),
                pagination.Action('Ask to buy', '🤝', nextcord.ButtonStyle.success, askToBuy, needsSelection = True)]
            fields = None
        avatar = owner.avatar.url if owner.avatar is not None else None
        source = pagination.DescriptionPageSource(lines, title, presentation.BRAND_COLOR, avatar, ITEMS_PER_PAGE, fields = fields, empty = empty)
        picker = pagination.ListPicker(source, choices, actions, 'Choose an item…')
        await pagination.startPages(context, picker, ephemeral = True)

    async def openSale(self, interaction, author, item):
        # 🏷️ Sell: on the market, or to one person, on its own private message
        view = pagination.OwnedView()
        view.ownerId = author.id
        listings = await GBotFirebaseService.run(gtrade_queries.getPendingTradeTransaction, interaction.guild.id, 'market', item, author.id)
        answered = []
        async def once(pressed):
            # before anything is awaited: a double click is dispatched before the view could stop
            if answered:
                await pressed.response.defer()
                return False
            answered.append(True)
            view.stop()
            return True
        async def done(pressed, reply):
            await pressed.edit_original_message(content = reply.notice or '🏷️ Done, in the channel.', embed = None, view = None)
            view.stop()
        async def toMarket(pressed):
            if not await once(pressed):
                return
            await pressed.response.defer()
            await predicates.recheck(pressed, feature = 'toggle_gtrade')
            reply = pagination.CardReply(pressed)
            await self.commonSell(reply, author, item, None)
            await done(pressed, reply)
        async def toSomeone(pressed, member):
            if not await once(pressed):
                return
            await pressed.response.defer()
            await predicates.recheck(pressed, feature = 'toggle_gtrade')
            reply = pagination.CardReply(pressed)
            await self.commonSell(reply, author, item, member)
            await done(pressed, reply)
        view.button('🏪', toMarket, label = 'Take off the market' if listings else 'The market', style = nextcord.ButtonStyle.secondary if listings else nextcord.ButtonStyle.success)
        view.picker(nextcord.ui.UserSelect, toSomeone, '🤝 Or pick someone to offer it to…', row = 1)
        embed = presentation.brandEmbed(title = f"🏷️ Sell '{item}'", description = f'At its value, on the market for {GBotPropertiesManager.GTRADE_MARKET_SALE_TIMEOUT_HOURS} hours, or to one person, who has {GBotPropertiesManager.GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES} minutes to accept.', feature = 'GTrade')
        await view.send(interaction, True, embed = embed, view = view)

    async def openMarket(self, context, author):
        # what's for sale here, and the requests waiting on you
        guild = context.guild
        listingIds = []

        async def listed():
            pending = await GBotFirebaseService.run(gtrade_queries.getAllServerPendingTradeTransactions, guild.id) or {}
            sales = [(trxId, trx) for trxId, trx in pending.items() if trx['trxType'] == 'market' and trx['sellerId'] != str(author.id)]
            sales.sort(key = lambda entry: entry[1]['item']['name'].lower())
            listingIds[:] = [trx for _, trx in sales]
            nameOf = lambda userId: getattr(guild.get_member(int(userId)), 'display_name', 'Unknown user')
            lines = [f"**{number}.** 🖼️ **{nextcord.utils.escape_markdown(trx['item']['name'])}** · `{presentation.formatGCoin(trx['item']['value'])} GCoin` · by {nextcord.utils.escape_markdown(nameOf(trx['sellerId']))}" for number, (_, trx) in enumerate(sales, start = 1)]
            choices = [{'label': trx['item']['name'], 'description': f"{presentation.formatGCoin(trx['item']['value'])} GCoin · by {nameOf(trx['sellerId'])}", 'emoji': '🖼️'} for _, trx in sales]
            waiting = []
            for trx in pending.values():
                if trx['trxType'] == 'buy' and trx['sellerId'] == str(author.id):
                    waiting.append(f"{nameOf(trx['buyerId'])} wants to buy your **{trx['item']['name']}** for {presentation.formatGCoin(trx['item']['value'])} GCoin")
                elif trx['trxType'] == 'sell' and trx.get('buyerId') == str(author.id):
                    waiting.append(f"{nameOf(trx['sellerId'])} wants to sell you **{trx['item']['name']}** for {presentation.formatGCoin(trx['item']['value'])} GCoin")
            source.fields = [{'name': 'Waiting on you', 'value': '\n'.join(waiting)[:1024] + '\nAnswer them in 🤝 **Trades** in `/gtrade`, or with the buttons on the request.'}] if waiting else None
            return lines, choices

        async def acknowledge(interaction, picker = None):
            await self.acknowledge(interaction, picker)

        async def buy(picker, interaction, index):
            await acknowledge(interaction, picker)
            trx = listingIds[index]
            seller = guild.get_member(int(trx['sellerId']))
            reply = pagination.CardReply(interaction)
            async with self.tradeLock:
                # checked under the same hold of the lock as the buy: a listing that ended would
                # otherwise turn the press into a request to buy
                stillListed = seller is not None and await GBotFirebaseService.run(gtrade_queries.getPendingTradeTransaction, guild.id, 'market', trx['item']['name'], seller.id) is not None
                if stillListed:
                    await self.buyUnderLock(reply, author, trx['item']['name'], seller)
            if not stillListed:
                notice = f"❌ '{trx['item']['name']}' is no longer for sale."
            else:
                notice = reply.notice or f"🎉 You bought '{trx['item']['name']}'."
            picker.replace(*await listed())
            await picker.redraw(interaction, notice)

        async def show(picker, interaction, index):
            await acknowledge(interaction)
            trx = listingIds[index]
            seller = guild.get_member(int(trx['sellerId']))
            await self.showItem(interaction.channel, interaction.user, seller, trx['item'])
            await picker.redraw(interaction, f"🔎 '{trx['item']['name']}' is shown in the channel.")

        source = pagination.DescriptionPageSource([], '🏪 Market', presentation.BRAND_COLOR, guild.icon.url if guild.icon is not None else None, ITEMS_PER_PAGE, empty = 'Nothing is for sale here right now. List one of yours with 🏷️ **Sell** in `/gtrade`.')
        lines, choices = await listed()
        source.entries = lines
        actions = [
            pagination.Action('Buy', '🛒', nextcord.ButtonStyle.success, buy, needsSelection = True),
            pagination.Action('Show', '🔎', nextcord.ButtonStyle.primary, show, needsSelection = True)]
        await pagination.startPages(context, pagination.ListPicker(source, choices, actions, 'Choose something to buy…'), ephemeral = True)

    def itemEmbed(self, owner, item):
        # 🔎 Show: the item with its story. owner is None for someone who has left.
        dateOf = lambda value: datetime.strptime(value, "%m/%d/%y %I:%M:%S %p").strftime("%m/%d/%y")
        embed = presentation.brandEmbed(title = f"🖼️ {item['name']}", description = f"Owned by {owner.mention if owner else 'a former member'}", feature = 'GTrade')
        embed.add_field(name = 'Value', value = f"{presentation.formatGCoin(item['value'])} GCoin", inline = True)
        embed.add_field(name = 'Date Obtained', value = dateOf(item['dateObtained']), inline = True)
        embed.add_field(name = 'Date Created', value = dateOf(item['dateCreated']), inline = True)
        embed.add_field(name = 'Original Value', value = f"{presentation.formatGCoin(item['originalValue'])} GCoin", inline = True)
        embed.add_field(name = 'Original Name', value = item['originalName'], inline = True)
        embed.add_field(name = 'Original Creator', value = item['originalCreator'], inline = True)
        embed.add_field(name = 'Original Server', value = item['originalServer'], inline = True)
        embed.set_image(url = item['dataJson']['imageUrl'])
        if owner is not None and owner.avatar is not None:
            embed.set_thumbnail(url = owner.avatar.url)
        return embed

    async def commonCraft(self, context, author, name, value, image, imageUrl):
        try:
            dateTimeObj = datetime.now()
            date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")
            userId = author.id
            userMention = author.mention
            authorName = author.name
            originalServer = 'Direct Message' if context.guild == None else context.guild.name
            if len(name) > self.MAX_ITEM_NAME_LENGTH:
                raise ItemNameTooLong
            value = utils.roundDecimalPlaces(presentation.parseGCoin(value), 2)
            if value <= Decimal('0'):
                raise EnforcePositiveTransactions
            # validate no existing items with this name in inventory and not too many
            await GBotFirebaseService.run(self.validateNewItem, userId, name)
            # checking a link can take a while, and a slash command has 3 seconds to answer
            await presentation.deferIfSlash(context)
            # the image comes with the command, so there's no follow-up question to wait on
            if (image is None) == (imageUrl is None):
                raise ItemImageMissing
            if image is not None:
                if not (image.content_type or '').startswith('image/'):
                    raise ItemImageInvalid
                imageUrl = image.url
            elif not await utils.isUrlImageContentTypeAndStatus200(imageUrl):
                raise ItemImageInvalid
            dataJson = { 'imageUrl': imageUrl }
            # try to perform GCoin transaction with validation
            sender = { 'id': userId, 'name': authorName }
            receiver = { 'id': None, 'name': 'GTrade' }
            # the item is created in the same write as the payment
            itemChanges = gtrade_queries.createItemChanges(userId, name, value, authorName, originalServer, date, name, value, date, 'image', dataJson)
            # checked again, as the wait for an image can be long enough to craft something else
            async with self.tradeLock:
                await GBotFirebaseService.run(self.validateNewItem, userId, name)
                await GBotFirebaseService.run(gcoin_queries.performTransaction, value, date, sender, receiver, 'crafted', '', False, True, itemChanges)
            done = f"🔨 {userMention}, you crafted '{name}' for {presentation.formatGCoin(value)} GCoin."
            if image is None:
                await context.send(done)
            else:
                # Discord deletes a slash command's upload, and an attached file's link expires, so the
                # image is posted with the result and the item keeps that copy's link instead
                await self.keepImage(context, done, image, userId, next(iter(itemChanges)).rsplit('/', 1)[1])
        except ItemImageMissing:
            await presentation.sendError(context, f'Sorry {userMention}, please give a link to an image, or right-click an uploaded one and use **Apps → Craft item**.')
        except ItemImageInvalid:
            await presentation.sendError(context, f"Sorry {userMention}, that isn't an image GBot can use. Try a PNG, JPG, GIF or WebP, or a direct link to one.")
        except EnforcePositiveTransactions:
            await presentation.sendError(context, f'Sorry {userMention}, you can not craft items with non-positive values.')
        except EnforceSenderFundsError:
            await presentation.sendError(context, f'Sorry {userMention}, you have insufficient funds.')
        except ItemNameConflict:
            await presentation.sendError(context, f'Sorry {userMention}, you already have an item with this name.')
        except ItemNameTooLong:
            await presentation.sendError(context, f"Sorry {userMention}, item names can't be longer than {self.MAX_ITEM_NAME_LENGTH} characters.")
        except ItemMaxCount:
            await presentation.sendError(context, f"Sorry {userMention}, you can't have more than {self.NUM_MAX_ITEMS} items.")
        except InvalidOperation:
            await presentation.sendError(context, f'Sorry {userMention}, please enter a valid amount.')

    async def keepImage(self, context, text, image, userId, itemId):
        try:
            message = await self.announce(context, text, file = await image.to_file())
            if not getattr(message, 'attachments', None):
                message = await message.fetch()
            await GBotFirebaseService.run(gtrade_queries.setItemImageUrl, userId, itemId, message.attachments[0].url)
        except (nextcord.HTTPException, IndexError) as e:
            self.logger.error(f'GTrade could not keep a copy of an item image for user {userId}: {type(e).__name__}')

    async def commonRename(self, context, author, item, name):
        async with self.tradeLock:
            await self.renameUnderLock(context, author, item, name)

    async def renameUnderLock(self, context, author, item, name):
        try:
            userId = author.id
            userMention = author.mention
            if len(name) > self.MAX_ITEM_NAME_LENGTH:
                raise ItemNameTooLong
            if not await GBotFirebaseService.run(self.renameItem, userId, item, name):
                await presentation.sendError(context, f"Sorry {userMention}, you do not have an item named '{item}'.")
                return
            await context.send(f"✏️ {userMention}, you renamed your item '{item}' to '{name}'.")
        except ItemNameConflict:
            await presentation.sendError(context, f'Sorry {userMention}, you already have an item with this name.')
        except ItemNameTooLong:
            await presentation.sendError(context, f"Sorry {userMention}, item names can't be longer than {self.MAX_ITEM_NAME_LENGTH} characters.")

    async def destroyUnderLock(self, author, item):
        dateTimeObj = datetime.now()
        date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")
        # looked up again, as it could have been sold or destroyed while the question was up
        itemTuple = await GBotFirebaseService.run(gtrade_queries.getUserItem, author.id, item)
        if itemTuple == None:
            return f"🚫 '{item}' is no longer yours to destroy."
        found = []
        price = await GBotFirebaseService.run(self.destroyItem, author.id, author.name, item, itemTuple, date, found)
        self.retireRelated(found)
        return f"💥 {author.mention}, you destroyed your item '{item}' for {presentation.formatGCoin(price)} GCoin."

    async def commonBuy(self, context, author, item, user):
        async with self.tradeLock:
            await self.buyUnderLock(context, author, item, user)

    async def buyUnderLock(self, context, author, item, user):
        dateTimeObj = datetime.now()
        date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")
        serverId = context.guild.id
        channelId = context.channel.id
        authorId = author.id
        authorMention = author.mention
        authorObj = { 'id': authorId, 'name': author.name }
        userId = user.id
        userMention = user.mention
        userObj = { 'id': userId, 'name': user.name }
        try:
            if not await utils.isUserInThisGuildAndNotABot(user, context.guild):
                await presentation.sendError(context, f"Sorry {authorMention}, please specify a user in this guild.")
                return
            if authorId == userId:
                raise EnforceSenderReceiverNotEqual
            itemTuple = await GBotFirebaseService.run(gtrade_queries.getUserItem, userId, item)
            if itemTuple != None:
                price = utils.roundDecimalPlaces(itemTuple[1]['value'], 2)
                pendingSellTrx = await GBotFirebaseService.run(gtrade_queries.getPendingTradeTransaction, serverId, 'sell', item, userId, authorId)
                pendingMarketTrx = await GBotFirebaseService.run(gtrade_queries.getPendingTradeTransaction, serverId, 'market', item, userId)
                # complete a user's pending sell request if exists, or buy an item for sale in the server's market if exists
                pendingTrx = None
                if pendingSellTrx != None:
                    pendingTrx = pendingSellTrx
                elif pendingMarketTrx != None:
                    pendingTrx = pendingMarketTrx
                if pendingTrx != None:
                    await GBotFirebaseService.run(self.validateTrade, itemTuple, userObj, authorObj)
                    await presentation.deferIfSlash(context)
                    found = []
                    await GBotFirebaseService.run(self.completeTradeTransaction, serverId, date, pendingTrx[0], itemTuple, userObj, authorObj, found)
                    self.retireRelated(found, pendingTrx[0])
                    await self.announce(context, f"🎉 {authorMention} bought '{item}' from {userMention} for {presentation.formatGCoin(price)} GCoin.")
                # create a request to buy from a user if no pending sells exist (market or request)
                else:
                    pendingBuyTrx = await GBotFirebaseService.run(gtrade_queries.getPendingTradeTransaction, serverId, 'buy', item, userId, authorId)
                    # if buy request already created, remove it
                    if pendingBuyTrx != None:
                        await GBotFirebaseService.run(gtrade_queries.removePendingTradeTransaction, serverId, pendingBuyTrx[0])
                        self.retireSoon(context.guild, [pendingBuyTrx[1]], NOTE_GONE)
                        await context.send(f"🚫 {authorMention}, you are no longer requesting to buy '{item}' from {userMention}.")
                    else:
                        existingItems = await GBotFirebaseService.run(gtrade_queries.getAllUserItems, authorId)
                        if existingItems != None:
                            if len(existingItems) >= self.NUM_MAX_ITEMS:
                                raise ItemMaxCount
                            for existingItem in existingItems.values():
                                name = existingItem['name']
                                if name == item:
                                    raise ItemNameConflict
                        if price > await GBotFirebaseService.run(gcoin_queries.getUserBalance, authorId):
                            raise EnforceSenderFundsError
                        trxId = await GBotFirebaseService.run(gtrade_queries.createPendingTradeTransaction, serverId, date, str(channelId), itemTuple[1], 'buy', str(userId), str(authorId))
                        await self.sendWithTradeButtons(context, f"🤝 {userMention}, {authorMention} wants to buy '{item}' from you for {presentation.formatGCoin(price)} GCoin.", trxId, TRADE_REQUEST)
            else:
                await presentation.sendError(context, f"Sorry {authorMention}, {userMention} does not have an item named '{item}'.")
        except EnforceRealUsersError:
            await presentation.sendError(context, f'Sorry {authorMention}, please specify a valid user.')
        except EnforceSenderReceiverNotEqual:
            await presentation.sendError(context, f'Sorry {authorMention}, you can not buy from or sell to yourself.')
        except EnforcePositiveTransactions:
            await presentation.sendError(context, f'Sorry {authorMention}, you can not buy or sell items for non-positive amounts.')
        except EnforceSenderFundsError:
            await presentation.sendError(context, f'Sorry {authorMention}, you have insufficient funds.')
        except ItemNameConflict:
            await presentation.sendError(context, f'Sorry {authorMention}, you already have an item with this name.')
        except ItemMaxCount:
            await presentation.sendError(context, f"Sorry {authorMention}, you can't have more than {self.NUM_MAX_ITEMS} items.")
        except ItemNoLongerAvailable:
            await presentation.sendError(context, f"Sorry {authorMention}, '{item}' is no longer available.")

    async def commonSell(self, context, author, item, user):
        async with self.tradeLock:
            await self.sellUnderLock(context, author, item, user)

    async def sellUnderLock(self, context, author, item, user, accepting = False):
        dateTimeObj = datetime.now()
        date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")
        serverId = context.guild.id
        channelId = context.channel.id
        authorId = author.id
        authorMention = author.mention
        authorObj = { 'id': authorId, 'name': author.name }
        itemTuple = await GBotFirebaseService.run(gtrade_queries.getUserItem, authorId, item)
        if itemTuple != None:
            try:
                price = utils.roundDecimalPlaces(itemTuple[1]['value'], 2)
                if user is None:
                    pendingMarketTrx = await GBotFirebaseService.run(gtrade_queries.getPendingTradeTransaction, serverId, 'market', item, authorId)
                    # if no pending market sale for the item already, create one
                    if pendingMarketTrx == None:
                        trxId = await GBotFirebaseService.run(gtrade_queries.createPendingTradeTransaction, serverId, date, str(channelId), itemTuple[1], 'market', str(authorId))
                        await self.sendWithTradeButtons(context, f"🏷️ {authorMention}, your item '{item}' is for sale for {presentation.formatGCoin(price)} GCoin.", trxId, TRADE_MARKET, item, price)
                    # if pending market sale for item already, remove it
                    else:
                        await GBotFirebaseService.run(gtrade_queries.removePendingTradeTransaction, serverId, pendingMarketTrx[0])
                        self.retireSoon(context.guild, [pendingMarketTrx[1]], NOTE_GONE)
                        await context.send(f"🚫 {authorMention}, your item '{item}' is no longer for sale.")
                else:
                    userId = user.id
                    userMention = user.mention
                    userObj = { 'id': userId, 'name': user.name }
                    if not await utils.isUserInThisGuildAndNotABot(user, context.guild):
                        await presentation.sendError(context, f"Sorry {authorMention}, please specify a user in this guild.")
                        return
                    if authorId == userId:
                            raise EnforceSenderReceiverNotEqual
                    pendingBuyTrx = await GBotFirebaseService.run(gtrade_queries.getPendingTradeTransaction, serverId, 'buy', item, authorId, userId)
                    pendingSellTrx = await GBotFirebaseService.run(gtrade_queries.getPendingTradeTransaction, serverId, 'sell', item, authorId, userId)
                    # if sell request already created, remove it, unless this is accepting their buy request
                    if pendingSellTrx != None and not accepting:
                        await GBotFirebaseService.run(gtrade_queries.removePendingTradeTransaction, serverId, pendingSellTrx[0])
                        self.retireSoon(context.guild, [pendingSellTrx[1]], NOTE_GONE)
                        await context.send(f"🚫 {authorMention}, you are no longer requesting to sell '{item}' to {userMention}.")
                    # if no pending buy request, create sell request
                    elif pendingBuyTrx == None:
                        trxId = await GBotFirebaseService.run(gtrade_queries.createPendingTradeTransaction, serverId, date, str(channelId), itemTuple[1], 'sell', str(authorId), str(userId))
                        await self.sendWithTradeButtons(context, f"🤝 {userMention}, {authorMention} wants to sell you '{item}' for {presentation.formatGCoin(price)} GCoin.", trxId, TRADE_REQUEST, item, price)
                    # if pending buy request exists, complete it by selling
                    else:
                        await GBotFirebaseService.run(self.validateTrade, itemTuple, authorObj, userObj)
                        await presentation.deferIfSlash(context)
                        found = []
                        await GBotFirebaseService.run(self.completeTradeTransaction, serverId, date, pendingBuyTrx[0], itemTuple, authorObj, userObj, found)
                        self.retireRelated(found, pendingBuyTrx[0])
                        await self.announce(context, f"🎉 {authorMention} sold '{item}' to {userMention} for {presentation.formatGCoin(price)} GCoin.")
            except EnforceRealUsersError:
                await presentation.sendError(context, f'Sorry {authorMention}, please specify a valid user.')
            except EnforceSenderReceiverNotEqual:
                await presentation.sendError(context, f'Sorry {authorMention}, you can not buy from or sell to yourself.')
            except EnforcePositiveTransactions:
                await presentation.sendError(context, f'Sorry {authorMention}, you can not buy or sell items for negative amounts.')
            except EnforceSenderFundsError:
                await presentation.sendError(context, f'Sorry {authorMention}, {userMention} has insufficient funds.')
            except ItemNameConflict:
                await presentation.sendError(context, f'Sorry {authorMention}, {userMention} already has an item with this name.')
            except ItemMaxCount:
                await presentation.sendError(context, f"Sorry {authorMention}, {userMention} already has {self.NUM_MAX_ITEMS} items.")
            except ItemNoLongerAvailable:
                await presentation.sendError(context, f"Sorry {authorMention}, '{item}' is no longer available.")
        else:
            await presentation.sendError(context, f"Sorry {authorMention}, you do not have an item named '{item}'.")

    def validateNewItem(self, userId, name):
        allUserItems = gtrade_queries.getAllUserItems(userId)
        if allUserItems != None:
            if len(allUserItems) >= self.NUM_MAX_ITEMS:
                raise ItemMaxCount
            for item in allUserItems.values():
                if item['name'] == name:
                    raise ItemNameConflict

    def renameItem(self, userId, item, name):
        # get id of item to rename and validate no existing items with new name in inventory
        allUserItems = gtrade_queries.getAllUserItems(userId)
        itemIdToRename = None
        if allUserItems != None:
            for itemId, itemObj in allUserItems.items():
                thisItemName = itemObj['name']
                if thisItemName == item:
                    itemIdToRename = itemId
                if thisItemName == name:
                    raise ItemNameConflict
        if itemIdToRename == None:
            return False
        gtrade_queries.renameItem(userId, itemIdToRename, name)
        # update all pending transaction for this item to use the new item name (where author is seller and item name is previous name)
        gtrade_queries.renameItemRelatedPendingTradeTransactions(userId, item, name)
        return True

    def destroyItem(self, authorId, authorName, item, itemTuple, date, found = None):
        # give the user money back, removing the item and any related pending transactions in the same write.
        # found: given a list, the transactions removed are added to it (removeRelatedPendingTradeTransactionsChanges)
        changes = {**gtrade_queries.removeItemChanges(authorId, itemTuple[0]), **gtrade_queries.removeRelatedPendingTradeTransactionsChanges(authorId, item, found)}
        price = itemTuple[1]['value']
        sender = { 'id': None, 'name': 'GTrade' }
        receiver = { 'id': authorId, 'name': authorName }
        gcoin_queries.performTransaction(utils.roundDecimalPlaces(price, 2), date, sender, receiver, '', 'destroyed', False, False, changes)
        return price

    def validateTrade(self, itemTuple, seller, buyer):
        # everything that can refuse a trade, so a command can check before it defers. A slash reply
        # is only private if nothing has deferred yet, and refusals here are the buyer's own business.
        # if buyer already has item with this name or already max items
        existingItems = gtrade_queries.getAllUserItems(buyer['id'])
        if existingItems != None:
            if len(existingItems) >= self.NUM_MAX_ITEMS:
                raise ItemMaxCount
            for existingItem in existingItems.values():
                existingItemName = existingItem['name']
                if existingItemName == itemTuple[1]['name']:
                    raise ItemNameConflict
        gcoin_queries.validateTransaction(utils.roundDecimalPlaces(itemTuple[1]['value'], 2), buyer, seller, True, True)

    def completeTradeTransaction(self, serverId, date, pendingTrxId, itemTuple, seller, buyer, found = None):
        # a last check, in the same step as the write: itemTuple was read before the command deferred
        currentItem = gtrade_queries.getUserItem(seller['id'], itemTuple[1]['name'])
        if gtrade_queries.getPendingTradeTransactionWithId(serverId, pendingTrxId) is None or currentItem is None or currentItem[0] != itemTuple[0]:
            raise ItemNoLongerAvailable
        self.validateTrade(itemTuple, seller, buyer)

        # the item changes hands and all pending transactions it affects go, in the same write as the money
        originalName = itemTuple[1]['originalName']
        originalValue = itemTuple[1]['originalValue']
        originalCreator = itemTuple[1]['originalCreator']
        originalServer = itemTuple[1]['originalServer']
        dateCreated = itemTuple[1]['dateCreated']
        name = itemTuple[1]['name']
        value = itemTuple[1]['value']
        dataType = itemTuple[1]['dataType']
        dataJson = itemTuple[1]['dataJson']
        changes = {
            **gtrade_queries.removeRelatedPendingTradeTransactionsChanges(seller['id'], name, found),
            GBotFirebaseService.path('gtrade', 'trade', serverId, pendingTrxId): None,
            **gtrade_queries.createItemChanges(buyer['id'], originalName, originalValue, originalCreator, originalServer, dateCreated, name, value, date, dataType, dataJson),
            **gtrade_queries.removeItemChanges(seller['id'], itemTuple[0])
        }
        gcoin_queries.performTransaction(utils.roundDecimalPlaces(itemTuple[1]['value'], 2), date, buyer, seller, 'bought', 'sold', True, True, changes)

def setup(client: commands.Bot):
    client.add_cog(GTrade(client))