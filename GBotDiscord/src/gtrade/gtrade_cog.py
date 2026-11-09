#region IMPORTS
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
TRADE_MARKET = 'market'
ITEMS_PER_PAGE = 10

class GTrade(commands.Cog):

    NUM_MAX_ITEMS = 100
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
        target = context.channel if isinstance(context, pagination.CardReply) else context
        return await target.send(text, **kwargs)

    async def sendWithTradeButtons(self, context, text, trxId, kind):
        view = self.tradeButtons(trxId, kind)
        try:
            await self.announce(context, text, view = view)
        finally:
            view.stop()

    @commands.Cog.listener()
    async def on_interaction(self, interaction: nextcord.Interaction):
        customId = (interaction.data or {}).get('custom_id', '') if interaction.type == nextcord.InteractionType.component else ''
        if customId.startswith(TRADE_BUTTON_PREFIX):
            action, trxId = customId[len(TRADE_BUTTON_PREFIX):].split(':', 1)
            await self.answerTradeButton(interaction, action, trxId)

    async def answerTradeButton(self, interaction: nextcord.Interaction, action, trxId):
        # acknowledged straight away, as Discord allows 3 seconds and this waits on the database and the
        # trade lock. A click skips the commands' own checks, so they are made here.
        await interaction.response.defer()
        guild = interaction.guild
        try:
            # a trade offered before a trial ended can still be answered during the grace days
            await predicates.ensureSubscribed(guild, interaction.user, allowEnded = True)
        except NotSubscribed:
            await interaction.send('GBot is not active in this server.', ephemeral = True)
            return
        if await GBotFirebaseService.run(config_queries.getServerValue, guild.id, 'toggle_gtrade') == False:
            await interaction.send('GTrade is turned off in this server.', ephemeral = True)
            return
        async with self.tradeLock:
            trx = await GBotFirebaseService.run(gtrade_queries.getPendingTradeTransactionWithId, guild.id, trxId)
            if trx is None:
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
                await interaction.send("These buttons aren't for you.", ephemeral = True)
                return
            item = trx['item']['name']
            if action in (TRADE_DECLINE, TRADE_CANCEL):
                await GBotFirebaseService.run(gtrade_queries.removePendingTradeTransaction, guild.id, trxId)
                word = 'declined' if action == TRADE_DECLINE else 'taken down' if kind == 'market' else 'cancelled'
                await interaction.message.edit(content = f"{interaction.message.content}\n-# {'❌' if action == TRADE_DECLINE else '🚫'} {interaction.user.mention} {word} this.", view = None)
                return
            other = guild.get_member(int(requesterId if action == TRADE_ACCEPT else trx['sellerId']))
            if other is None:
                await self.endTradeButtons(interaction, '⌛ This trade is no longer available, as the other person left.')
                return
            # the same code as the card's buy and sell, which re-check everything and move the GCoin
            if kind == 'buy':
                await self.sellUnderLock(interaction, interaction.user, item, other, accepting = True)
            else:
                await self.buyUnderLock(interaction, interaction.user, item, other)
            if await GBotFirebaseService.run(gtrade_queries.getPendingTradeTransactionWithId, guild.id, trxId) is None:
                try:
                    await interaction.message.edit(view = None)
                except nextcord.HTTPException:
                    pass

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
                            isExpired = False
                            if trxType == 'market':
                                if hoursLater >= GBotPropertiesManager.GTRADE_MARKET_SALE_TIMEOUT_HOURS:
                                    isExpired = True
                                    userId = trx['sellerId']
                                    trxStr = f"market sale for '{itemName}' has expired after {GBotPropertiesManager.GTRADE_MARKET_SALE_TIMEOUT_HOURS} hours."
                            else:
                                if minutesLater >= GBotPropertiesManager.GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES:
                                    isExpired = True
                                    buyerId = trx['buyerId']
                                    sellerId = trx['sellerId']
                                    if trxType == 'buy':
                                        userId = buyerId
                                        trxStr = f"buy request for '{itemName}' from {utils.idToUserStr(sellerId)} has expired after {GBotPropertiesManager.GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES} minutes."
                                    elif trxType == 'sell':
                                        userId = sellerId
                                        trxStr = f"sell request for '{itemName}' to {utils.idToUserStr(buyerId)} has expired after {GBotPropertiesManager.GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES} minutes."
                            if isExpired:
                                async with self.tradeLock:
                                    await GBotFirebaseService.run(gtrade_queries.removePendingTradeTransaction, serverId, trxId)
                                channel: nextcord.TextChannel = await self.client.fetch_channel(int(trx['sourceChannelId']))
                                await presentation.sendError(channel, f'Sorry {utils.idToUserStr(userId)}, your {trxStr}')
                        except Exception as e:
                            self.logger.error(f'Error in GTrade.remove_expired_transactions() for transaction {trxId} in guild {serverId}: {e}')
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
        # A form can't take an upload, so an uploaded image is crafted from its message instead.
        image = next((attachment for attachment in message.attachments if (attachment.content_type or '').startswith('image/')), None)
        if image is None:
            await presentation.sendError(interaction, f'Sorry {interaction.user.mention}, that message has no image to craft from. Right-click a message with an uploaded image, or use ⚒️ **Craft** in `/gtrade` with a link.', feature = 'GTrade')
            return
        async def submit(submitted, values):
            await submitted.response.defer(ephemeral = True)
            await predicates.recheck(submitted, feature = 'toggle_gtrade', privateMessagesAllowed = True)
            reply = pagination.CardReply(submitted)
            await self.commonCraft(reply, submitted.user, values[0], values[1], image, None)
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

        async def acknowledge(interaction):
            # Discord allows 3 seconds, and what follows waits on the database
            await interaction.response.defer()
            await predicates.recheck(interaction, feature = 'toggle_gtrade', privateMessagesAllowed = True)

        async def show(picker, interaction, index):
            # public, so it can be shown off
            await acknowledge(interaction)
            itemTuple = await GBotFirebaseService.run(gtrade_queries.getUserItem, owner.id, itemNames[index])
            if itemTuple is None:
                await reload(picker, interaction, f"❌ '{itemNames[index]}' isn't {'yours' if isOwn else 'theirs'} any more.")
                return
            await interaction.channel.send(embed = self.itemEmbed(owner, itemTuple[1]))
            await picker.redraw(interaction, f"🔎 '{itemNames[index]}' is shown in the channel.")

        async def sell(picker, interaction, index):
            await acknowledge(interaction)
            await self.openSale(interaction, author, itemNames[index])

        async def rename(picker, interaction, index):
            current = itemNames[index]
            async def submit(submitted, values):
                await acknowledge(submitted)
                reply = pagination.CardReply(submitted)
                await self.commonRename(reply, author, current, values[0])
                await reload(picker, submitted, reply.notice)
            await interaction.response.send_modal(pagination.Form(f'Rename {current}', [pagination.Field('New name', default = current, maxLength = self.MAX_ITEM_NAME_LENGTH)], submit))

        async def destroy(picker, interaction, index):
            await acknowledge(interaction)
            async with self.tradeLock:
                text = await self.destroyUnderLock(author, itemNames[index])
            await reload(picker, interaction, text)

        async def craft(picker, interaction, index):
            async def submit(submitted, values):
                await acknowledge(submitted)
                reply = pagination.CardReply(submitted)
                await self.commonCraft(reply, author, values[0], values[1], None, values[2])
                await reload(picker, submitted, reply.notice)
            await interaction.response.send_modal(self.craftForm('Craft an item', submit))

        async def market(picker, interaction, index):
            await acknowledge(interaction)
            await self.openMarket(interaction, author)

        async def askToBuy(picker, interaction, index):
            await acknowledge(interaction)
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
            source.fields = [{'name': 'Waiting on you', 'value': '\n'.join(waiting)[:1024] + '\nAnswer with the buttons on the request.'}] if waiting else None
            return lines, choices

        async def acknowledge(interaction):
            await interaction.response.defer()
            await predicates.recheck(interaction, feature = 'toggle_gtrade')

        async def buy(picker, interaction, index):
            await acknowledge(interaction)
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
            await interaction.channel.send(embed = self.itemEmbed(seller, trx['item']))
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
        price = await GBotFirebaseService.run(self.destroyItem, author.id, author.name, item, itemTuple, date)
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
                    await GBotFirebaseService.run(self.completeTradeTransaction, serverId, date, pendingTrx[0], itemTuple, userObj, authorObj)
                    await self.announce(context, f"🎉 {authorMention} bought '{item}' from {userMention} for {presentation.formatGCoin(price)} GCoin.")
                # create a request to buy from a user if no pending sells exist (market or request)
                else:
                    pendingBuyTrx = await GBotFirebaseService.run(gtrade_queries.getPendingTradeTransaction, serverId, 'buy', item, userId, authorId)
                    # if buy request already created, remove it
                    if pendingBuyTrx != None:
                        await GBotFirebaseService.run(gtrade_queries.removePendingTradeTransaction, serverId, pendingBuyTrx[0])
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
                        await self.sendWithTradeButtons(context, f"🏷️ {authorMention}, your item '{item}' is for sale for {presentation.formatGCoin(price)} GCoin.", trxId, TRADE_MARKET)
                    # if pending market sale for item already, remove it
                    else:
                        await GBotFirebaseService.run(gtrade_queries.removePendingTradeTransaction, serverId, pendingMarketTrx[0])
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
                        await context.send(f"🚫 {authorMention}, you are no longer requesting to sell '{item}' to {userMention}.")
                    # if no pending buy request, create sell request
                    elif pendingBuyTrx == None:
                        trxId = await GBotFirebaseService.run(gtrade_queries.createPendingTradeTransaction, serverId, date, str(channelId), itemTuple[1], 'sell', str(authorId), str(userId))
                        await self.sendWithTradeButtons(context, f"🤝 {userMention}, {authorMention} wants to sell you '{item}' for {presentation.formatGCoin(price)} GCoin.", trxId, TRADE_REQUEST)
                    # if pending buy request exists, complete it by selling
                    else:
                        await GBotFirebaseService.run(self.validateTrade, itemTuple, authorObj, userObj)
                        await presentation.deferIfSlash(context)
                        await GBotFirebaseService.run(self.completeTradeTransaction, serverId, date, pendingBuyTrx[0], itemTuple, authorObj, userObj)
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

    def destroyItem(self, authorId, authorName, item, itemTuple, date):
        # give the user money back, removing the item and any related pending transactions in the same write
        changes = {**gtrade_queries.removeItemChanges(authorId, itemTuple[0]), **gtrade_queries.removeRelatedPendingTradeTransactionsChanges(authorId, item)}
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

    def completeTradeTransaction(self, serverId, date, pendingTrxId, itemTuple, seller, buyer):
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
            **gtrade_queries.removeRelatedPendingTradeTransactionsChanges(seller['id'], name),
            GBotFirebaseService.path('gtrade', 'trade', serverId, pendingTrxId): None,
            **gtrade_queries.createItemChanges(buyer['id'], originalName, originalValue, originalCreator, originalServer, dateCreated, name, value, date, dataType, dataJson),
            **gtrade_queries.removeItemChanges(seller['id'], itemTuple[0])
        }
        gcoin_queries.performTransaction(utils.roundDecimalPlaces(itemTuple[1]['value'], 2), date, buyer, seller, 'bought', 'sold', True, True, changes)

def setup(client: commands.Bot):
    client.add_cog(GTrade(client))