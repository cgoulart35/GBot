#region IMPORTSs
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

class GTrade(commands.Cog):

    NUM_MAX_ITEMS = 100
    # Discord's own limit on an autocomplete choice, and short enough that one listing can't push
    # a /gtrade market page past what an embed can hold, which would break it for the whole server
    MAX_ITEM_NAME_LENGTH = 100

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()
        self.MAX_AUTOCOMPLETE_CHOICES = 25
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

    async def sendWithTradeButtons(self, context, text, trxId, kind):
        view = self.tradeButtons(trxId, kind)
        await context.send(text, view = view)
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
            await predicates.ensureSubscribed(guild, interaction.user)
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
            # the same code as /gtrade buy and sell, which re-check everything and move the GCoin
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
    # The two group roots. Discord never invokes a slash command that has subcommands, so the slash
    # root's body is unreachable in production — nextcord just needs a callback to hang the group on.
    @nextcord.slash_command(name = strings.GTRADE_GROUP_NAME, description = strings.GTRADE_GROUP_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    async def gtradeSlashGroup(self, interaction: nextcord.Interaction):
        pass

    @commands.group(name = strings.GTRADE_GROUP_NAME, aliases = strings.GTRADE_GROUP_ALIASES, brief = "- " + strings.GTRADE_GROUP_BRIEF, description = strings.GTRADE_GROUP_DESCRIPTION, invoke_without_command = True)
    # invoke_without_command means these run ONLY for a bare ".gtrade" — when a subcommand
    # matches, nextcord dispatches straight to it and the root's checks never fire. So this
    # is the group's own gate, not a second one on every leaf: it mirrors exactly the checks
    # every leaf here shares, or a bare root would be an ungated way into a gated cog.
    @predicates.isFeatureEnabledForServer('toggle_gtrade', True)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', True)
    @predicates.isGuildOrUserSubscribed()
    async def gtradeGroup(self, ctx: Context):
        # a bare ".gtrade" names no subcommand; list what lives under the group instead of doing nothing
        await ctx.send_help(ctx.command)

    @gtradeSlashGroup.subcommand(name = strings.GTRADE_CRAFT_NAME, description = strings.GTRADE_CRAFT_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', True, True)
    async def craftSlash(self,
                         interaction: nextcord.Interaction,
                         name = nextcord.SlashOption(
                            name = 'name',
                            required = True,
                            description = strings.GTRADE_CRAFT_NAME_DESCRIPTION
                         ),
                         value = nextcord.SlashOption(
                            name = 'value',
                            required = True,
                            description = strings.GTRADE_CRAFT_VALUE_DESCRIPTION
                         ),
                         image: nextcord.Attachment = nextcord.SlashOption(
                            name = 'image',
                            required = False,
                            description = strings.GTRADE_CRAFT_IMAGE_DESCRIPTION
                         ),
                         image_url = nextcord.SlashOption(
                            name = 'image_url',
                            required = False,
                            description = strings.GTRADE_CRAFT_IMAGE_URL_DESCRIPTION
                         )):
        await self.commonCraft(interaction, interaction.user, name, value, image, image_url)

    @gtradeGroup.command(name = strings.GTRADE_CRAFT_NAME, aliases = strings.GTRADE_CRAFT_ALIASES, brief = "- " + strings.GTRADE_CRAFT_BRIEF, description = strings.GTRADE_CRAFT_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', True)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', True)
    @predicates.isGuildOrUserSubscribed()
    async def craft(self, ctx: Context, name, value, image_url = None):
        # a prefix command takes its image as a file attached to the same message
        await self.commonCraft(ctx, ctx.author, name, value, ctx.message.attachments[0] if ctx.message.attachments else None, image_url)

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
            await presentation.sendError(context, f'Sorry {userMention}, please give one image: attach it, or give a link to it.')
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
            await presentation.sendError(context, f'Sorry {userMention}, please enter a valid amount. Remember to use quotes for names that are more than one word.')

    async def keepImage(self, context, text, image, userId, itemId):
        try:
            message = await context.send(text, file = await image.to_file())
            if not getattr(message, 'attachments', None):
                message = await message.fetch()
            await GBotFirebaseService.run(gtrade_queries.setItemImageUrl, userId, itemId, message.attachments[0].url)
        except (nextcord.HTTPException, IndexError) as e:
            self.logger.error(f'GTrade could not keep a copy of an item image for user {userId}: {type(e).__name__}')

    @gtradeSlashGroup.subcommand(name = strings.GTRADE_RENAME_NAME, description = strings.GTRADE_RENAME_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', True, True)
    async def renameSlash(self,
                         interaction: nextcord.Interaction,
                         item = nextcord.SlashOption(
                            name = 'item',
                            required = True,
                            description = strings.GTRADE_RENAME_ITEM_DESCRIPTION
                         ),
                         name = nextcord.SlashOption(
                            name = 'name',
                            required = True,
                            description = strings.GTRADE_RENAME_NAME_DESCRIPTION
                         )):
        await self.commonRename(interaction, interaction.user, item, name)

    @gtradeGroup.command(name = strings.GTRADE_RENAME_NAME, aliases = strings.GTRADE_RENAME_ALIASES, brief = "- " + strings.GTRADE_RENAME_BRIEF, description = strings.GTRADE_RENAME_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', True)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', True)
    @predicates.isGuildOrUserSubscribed()
    async def rename(self, ctx: Context, item, name):
        await self.commonRename(ctx, ctx.author, item, name)

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

    @gtradeSlashGroup.subcommand(name = strings.GTRADE_DESTROY_NAME, description = strings.GTRADE_DESTROY_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', True, True)
    async def destroySlash(self,
                         interaction: nextcord.Interaction,
                         item = nextcord.SlashOption(
                            name = 'item',
                            required = True,
                            description = strings.GTRADE_DESTROY_ITEM_DESCRIPTION
                         )):
        await self.commonDestroy(interaction, interaction.user, item)

    @gtradeGroup.command(name = strings.GTRADE_DESTROY_NAME, aliases = strings.GTRADE_DESTROY_ALIASES, brief = "- " + strings.GTRADE_DESTROY_BRIEF, description = strings.GTRADE_DESTROY_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', True)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', True)
    @predicates.isGuildOrUserSubscribed()
    async def destroy(self, ctx: Context, item):
        await self.commonDestroy(ctx, ctx.author, item)

    async def commonDestroy(self, context, author, item):
        # asked before the trade lock is taken, so a pending answer can't hold up everyone's trades
        await presentation.deferIfSlash(context, ephemeral = True)
        itemTuple = await GBotFirebaseService.run(gtrade_queries.getUserItem, author.id, item)
        if itemTuple == None:
            await presentation.sendError(context, f"Sorry {author.mention}, you do not have an item named '{item}'.")
            return
        refund = presentation.formatGCoin(utils.roundDecimalPlaces(itemTuple[1]['value'], 2))
        confirmed, view = await pagination.confirm(context, f"💥 Destroy '{item}'?", f"You get **{refund} GCoin** back, and the item is gone for good. Any sale or trade request for it ends too.", 'Destroy', '💥', feature = 'GTrade')
        if not confirmed:
            return
        async with self.tradeLock:
            await view.finish(await self.destroyUnderLock(author, item))

    async def destroyUnderLock(self, author, item):
        dateTimeObj = datetime.now()
        date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")
        # looked up again, as it could have been sold or destroyed while the question was up
        itemTuple = await GBotFirebaseService.run(gtrade_queries.getUserItem, author.id, item)
        if itemTuple == None:
            return f"🚫 '{item}' is no longer yours to destroy."
        price = await GBotFirebaseService.run(self.destroyItem, author.id, author.name, item, itemTuple, date)
        return f"💥 {author.mention}, you destroyed your item '{item}' for {presentation.formatGCoin(price)} GCoin."

    @gtradeSlashGroup.subcommand(name = strings.GTRADE_ITEMS_NAME, description = strings.GTRADE_ITEMS_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', False, True)
    async def itemsSlash(self,
                         interaction: nextcord.Interaction,
                         user: nextcord.User = nextcord.SlashOption(
                            name = 'user',
                            required = False,
                            description = strings.GTRADE_ITEMS_USER_DESCRIPTION
                        )):
        await self.commonItems(interaction, interaction.user, user)

    @gtradeGroup.command(name = strings.GTRADE_ITEMS_NAME, aliases = strings.GTRADE_ITEMS_ALIASES, brief = "- " + strings.GTRADE_ITEMS_BRIEF, description = strings.GTRADE_ITEMS_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', True)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', True)
    @predicates.isGuildOrUserSubscribed()
    async def items(self, ctx: Context, user: nextcord.User = None):
        await self.commonItems(ctx, ctx.author, user)

    async def commonItems(self, context, author, user):
        authorMention = author.mention
        if context.guild is None and user != None:
            await presentation.sendError(context, f"Sorry {authorMention}, please use this command on other users in a server.")
        else:
            if isinstance(context, nextcord.Interaction):
                await context.response.defer(ephemeral = True)
            # if user specified use user
            if user != None:
                if not await utils.isUserInThisGuildAndNotABot(user, context.guild):
                    await presentation.sendError(context, f"Sorry {authorMention}, please specify a user in this guild.")
                    return
                itemsOwnerId = user.id
                itemsOwnerMention = user.mention
                itemsOwnerName = user.name
                itemsOwnerStr = f'{itemsOwnerMention} does'
                if user.avatar != None:
                    thumbnailUrl = user.avatar.url
                else:
                    thumbnailUrl = None                   
            # if user not specified use author
            else:
                itemsOwnerId = author.id
                itemsOwnerMention = authorMention
                itemsOwnerName = author.name
                itemsOwnerStr = 'you do'
                if author.avatar != None:
                    thumbnailUrl = author.avatar.url
                else:
                    thumbnailUrl = None                  
            # get all user's items         
            items = await GBotFirebaseService.run(gtrade_queries.getAllUserItems, itemsOwnerId)
            # if there are items sort and show them
            if items != None:
                fields = []
                sortedItems = sorted(items.values(), key=lambda item: utils.roundDecimalPlaces(item['value'], 2), reverse=True)
                for i in range(self.NUM_MAX_ITEMS):
                    if i == len(sortedItems):
                        break
                    item = sortedItems[i]
                    name = item['name']
                    type = item['dataType']
                    value = item['value']
                    fields.append((f'{i + 1}. 🖼️ {name}' if type == 'image' else f'{i + 1}. {name}', f'`{presentation.formatGCoin(value)} GCoin`'))

                pages = pagination.CustomButtonMenuPages(source = pagination.FieldPageSource(fields, thumbnailUrl, f"🎒 {itemsOwnerName}'s Items", presentation.BRAND_COLOR, False, 10))
                await pagination.startPages(context, pages, ephemeral = True)

            # if no items in inventory
            else:
                await presentation.sendError(context, f"Sorry {authorMention}, {itemsOwnerStr} not have any items.")

    @gtradeSlashGroup.subcommand(name = strings.GTRADE_ITEM_NAME, description = strings.GTRADE_ITEM_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', True, True)
    async def itemSlash(self,
                         interaction: nextcord.Interaction,
                         item = nextcord.SlashOption(
                            name = 'item',
                            required = True,
                            description = strings.GTRADE_ITEM_ITEM_DESCRIPTION
                         )):
        await self.commonItem(interaction, interaction.user, item)

    @gtradeGroup.command(name = strings.GTRADE_ITEM_NAME, aliases = strings.GTRADE_ITEM_ALIASES, brief = "- " + strings.GTRADE_ITEM_BRIEF, description = strings.GTRADE_ITEM_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', True)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', True)
    @predicates.isGuildOrUserSubscribed()
    async def item(self, ctx: Context, item):
        await self.commonItem(ctx, ctx.author, item)

    async def commonItem(self, context, author, item):
        authorId = author.id
        authorMention = author.mention
        # get authors item with specified name
        itemTuple = await GBotFirebaseService.run(gtrade_queries.getUserItem, authorId, item)
        # if item exists showcase it
        if itemTuple != None:
            originalName = itemTuple[1]['originalName']
            originalValue = itemTuple[1]['originalValue']
            originalCreator = itemTuple[1]['originalCreator']
            originalServer = itemTuple[1]['originalServer']
            dateCreated = datetime.strptime(itemTuple[1]['dateCreated'], "%m/%d/%y %I:%M:%S %p").strftime("%m/%d/%y")
            name = itemTuple[1]['name']
            gcoinAmount = itemTuple[1]['value']
            dateObtained = datetime.strptime(itemTuple[1]['dateObtained'], "%m/%d/%y %I:%M:%S %p").strftime("%m/%d/%y")
            dataType = itemTuple[1]['dataType']
            dataJson = itemTuple[1]['dataJson']
            # if item is an image
            if dataType == 'image':
                imageUrl = dataJson['imageUrl']
                embed = presentation.brandEmbed(title = f'🖼️ {name}', description = f'Owned by {authorMention}', feature = 'GTrade')
                
                embed.add_field(name = 'Value', value = f'{presentation.formatGCoin(gcoinAmount)} GCoin', inline = True)
                embed.add_field(name = 'Date Obtained', value = dateObtained, inline = True)
                embed.add_field(name = 'Date Created', value = dateCreated, inline = True)

                embed.add_field(name = 'Original Value', value = f'{presentation.formatGCoin(originalValue)} GCoin', inline = True)
                embed.add_field(name = 'Original Name', value = originalName, inline = True)
                embed.add_field(name = 'Original Creator', value = originalCreator, inline = True)
                
                embed.add_field(name = 'Original Server', value = originalServer, inline = True)

                embed.set_image(url = imageUrl)
                if author.avatar != None:
                    embed.set_thumbnail(url = author.avatar.url)
                await context.send(embed = embed)
        # if item does not exist
        else:
            await presentation.sendError(context, f"Sorry {authorMention}, you do not have an item named '{item}'.")

    @gtradeSlashGroup.subcommand(name = strings.GTRADE_MARKET_NAME, description = strings.GTRADE_MARKET_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', False, True)
    async def marketSlash(self, interaction: nextcord.Interaction):
        await self.commonMarket(interaction, interaction.user)

    @gtradeGroup.command(name = strings.GTRADE_MARKET_NAME, aliases = strings.GTRADE_MARKET_ALIASES, brief = "- " + strings.GTRADE_MARKET_BRIEF, description = strings.GTRADE_MARKET_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', False)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def market(self, ctx: Context):
        await self.commonMarket(ctx, ctx.author)

    async def commonMarket(self, context, author):
        if isinstance(context, nextcord.Interaction):
            await context.response.defer()
        serverId = context.guild.id
        authorId = author.id
        allServerPending = await GBotFirebaseService.run(gtrade_queries.getAllServerPendingTradeTransactions, serverId)
        if allServerPending != None:
            marketSellList = []
            marketSellCount = 0
            incomingBuyList = []
            incomingBuyCount = 0
            incomingSellList = []
            incomingSellCount = 0
            outgoingBuyList = []
            outgoingBuyCount = 0
            outgoingSellList = []
            outgoingSellCount = 0
            for trx in allServerPending.values():
                thisTrxType = trx['trxType']
                thisSellerId = trx['sellerId']
                thisSellerUser: nextcord.Member = context.guild.get_member(int(thisSellerId))
                thisBuyerId = None if 'buyerId' not in trx else trx['buyerId']
                thisBuyerUser: nextcord.Member = None if thisBuyerId == None else context.guild.get_member(int(thisBuyerId))
                # get_member returns None once a party leaves the guild (or isn't cached) — fall
                # back to a placeholder so one stale listing can't break /market for everyone
                thisSellerName = thisSellerUser.name if thisSellerUser != None else 'Unknown user'
                thisBuyerName = thisBuyerUser.name if thisBuyerUser != None else 'Unknown user'
                itemName = trx['item']['name']
                itemValue = trx['item']['value']
                price = f'{presentation.formatGCoin(itemValue)} GCoin'
                # add all items for sale on market (where no one is buyer, seller is not none, and type is 'market')
                if thisBuyerId == None and thisSellerId != None and thisTrxType == 'market':
                    marketSellList.append(f'{marketSellCount + 1}. **{itemName}** for {price}, from {thisSellerName}')
                    marketSellCount += 1
                # all incoming buys (where author is seller, buyer is not none, and type is 'buy')
                elif thisBuyerId != None and thisSellerId == str(authorId) and thisTrxType == 'buy':
                    incomingBuyList.append(f'{incomingBuyCount + 1}. {thisBuyerName} wants to buy **{itemName}** for {price}')
                    incomingBuyCount += 1
                # all incoming sells (where author is buyer, seller is not none, and type is 'sell')
                elif thisBuyerId == str(authorId) and thisSellerId != None and thisTrxType == 'sell':
                    incomingSellList.append(f'{incomingSellCount + 1}. {thisSellerName} wants to sell you **{itemName}** for {price}')
                    incomingSellCount += 1
                # all outgoing buys (where author is buyer, seller is not none, and type is 'buy')
                elif thisBuyerId == str(authorId) and thisSellerId != None and thisTrxType == 'buy':
                    outgoingBuyList.append(f'{outgoingBuyCount + 1}. You asked {thisSellerName} for **{itemName}** at {price}')
                    outgoingBuyCount += 1
                # all outgoing sells (where author is seller, buyer is not none, type is 'sell')
                elif thisBuyerId != None and thisSellerId == str(authorId) and thisTrxType == 'sell':
                    outgoingSellList.append(f'{outgoingSellCount + 1}. You offered {thisBuyerName} **{itemName}** at {price}')
                    outgoingSellCount += 1

            # add lists to data list if they aren't empty
            data = []
            if len(marketSellList) > 0:
                data.append('**🛒 Items For Sale**')
                data.extend(marketSellList)
            if len(incomingBuyList) > 0:
                data.append('**📥 Incoming Buy Requests**')
                data.extend(incomingBuyList)
            if len(incomingSellList) > 0:
                data.append('**📥 Incoming Sell Requests**')
                data.extend(incomingSellList)
            if len(outgoingBuyList) > 0:
                data.append('**📤 Outgoing Buy Requests**')
                data.extend(outgoingBuyList)
            if len(outgoingSellList) > 0:
                data.append('**📤 Outgoing Sell Requests**')
                data.extend(outgoingSellList)

            # only other people's private requests are pending, so an empty card would be all there is
            if not data:
                await presentation.sendError(context, f"Sorry {author.mention}, there are no available items for sale or transaction requests.")
                return

            pages = pagination.CustomButtonMenuPages(source = pagination.DescriptionPageSource(data, "🏪 Market", presentation.BRAND_COLOR, author.avatar.url if author.avatar != None else None, 10))
            await pagination.startPages(context, pages)
        else:
            await presentation.sendError(context, f"Sorry {author.mention}, there are no available items for sale or transaction requests.")

    @gtradeSlashGroup.subcommand(name = strings.GTRADE_BUY_NAME, description = strings.GTRADE_BUY_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', False, True)
    async def buySlash(self,
                         interaction: nextcord.Interaction,
                         user: nextcord.User = nextcord.SlashOption(
                            name = 'user',
                            required = True,
                            description = strings.GTRADE_BUY_USER_DESCRIPTION
                        ),
                         item = nextcord.SlashOption(
                            name = 'item',
                            required = True,
                            description = strings.GTRADE_BUY_ITEM_DESCRIPTION
                         )):
        await self.commonBuy(interaction, interaction.user, item, user)

    @gtradeGroup.command(name = strings.GTRADE_BUY_NAME, aliases = strings.GTRADE_BUY_ALIASES, brief = "- " + strings.GTRADE_BUY_BRIEF, description = strings.GTRADE_BUY_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', False)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def buy(self, ctx: Context, user: nextcord.User, item):
        await self.commonBuy(ctx, ctx.author, item, user)

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
                    await context.send(f"🎉 {authorMention}, you bought '{item}' from {userMention} for {presentation.formatGCoin(price)} GCoin.")
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

    @gtradeSlashGroup.subcommand(name = strings.GTRADE_SELL_NAME, description = strings.GTRADE_SELL_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', False, True)
    async def sellSlash(self,
                         interaction: nextcord.Interaction,
                         item = nextcord.SlashOption(
                            name = 'item',
                            required = True,
                            description = strings.GTRADE_SELL_ITEM_DESCRIPTION
                         ),
                         user: nextcord.User = nextcord.SlashOption(
                            name = 'user',
                            required = False,
                            description = strings.GTRADE_SELL_USER_DESCRIPTION
                        )):
        await self.commonSell(interaction, interaction.user, item, user)

    @gtradeGroup.command(name = strings.GTRADE_SELL_NAME, aliases = strings.GTRADE_SELL_ALIASES, brief = "- " + strings.GTRADE_SELL_BRIEF, description = strings.GTRADE_SELL_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', False)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def sell(self, ctx: Context, item, user: nextcord.User = None):
        await self.commonSell(ctx, ctx.author, item, user)

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
                        await context.send(f"🎉 {authorMention}, you sold '{item}' to {userMention} for {presentation.formatGCoin(price)} GCoin.")
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

    # Autocompletes
    @itemSlash.on_autocomplete("item")
    @renameSlash.on_autocomplete("item")
    @destroySlash.on_autocomplete("item")
    @sellSlash.on_autocomplete("item")
    async def loadAuthorItems(self, interaction: nextcord.Interaction, item: str):
        await self.loadItemsForUserId(interaction, item, interaction.user.id)

    @buySlash.on_autocomplete("item")
    async def loadUserItems(self, interaction: nextcord.Interaction, item: str):
        userId = None
        if interaction.data != None and 'options' in interaction.data and len(interaction.data['options']) > 0:
            # data.options[0] is the "buy" subcommand itself. The options the user has filled in sit
            # one level down, in the order they filled them in, so "user" has to be found by name.
            for option in interaction.data['options'][0].get('options', []):
                if option['name'] == 'user':
                    userId = option['value']
        if userId:
            await self.loadItemsForUserId(interaction, item, userId)
        else:
            await interaction.response.send_autocomplete([])

    async def loadItemsForUserId(self, interaction: nextcord.Interaction, item: str, userId):
        items = []

        # get all user's items
        userItems = await GBotFirebaseService.run(gtrade_queries.getAllUserItems, userId)
        if userItems != None:
            for itemId, itemData in userItems.items():
                # a name saved before the length limit can't be offered: Discord rejects the whole list
                if len(itemData['name']) <= self.MAX_ITEM_NAME_LENGTH:
                    items.append(itemData['name'])

        # if no items, don't show anything        
        # if no item specified show all items, otherwise show items that start with the specified item
        if item:
            items = [x for x in items if x.lower().startswith(item.lower())]
        # someone can own more items than Discord accepts as choices; typing narrows the rest down
        await interaction.response.send_autocomplete(items[:self.MAX_AUTOCOMPLETE_CHOICES])

def setup(client: commands.Bot):
    client.add_cog(GTrade(client))