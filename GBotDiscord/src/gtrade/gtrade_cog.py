#region IMPORTSs
import logging
import asyncio
import nextcord
from nextcord.ext import commands, tasks
from nextcord.ext.commands.context import Context
from datetime import datetime
from decimal import Decimal, InvalidOperation

from GBotDiscord.src import strings
from GBotDiscord.src import utils
from GBotDiscord.src import pagination
from GBotDiscord.src import predicates
from GBotDiscord.src.gtrade import gtrade_queries
from GBotDiscord.src.gcoin import gcoin_queries
from GBotDiscord.src.exceptions import EnforceRealUsersError, EnforceSenderReceiverNotEqual, EnforcePositiveTransactions, EnforceSenderFundsError, ItemNameConflict, ItemTypeInvalid, ItemMaxCount, UserCancelledCommand
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

class GTrade(commands.Cog):

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()
        self.NUM_MAX_ITEMS = 100

    # Events
    @commands.Cog.listener()
    async def on_guild_remove(self, guild: nextcord.Guild):
        self.logger.info(f'Deleting GTrade pending transactions in guild {guild.id} ({guild.name}).')
        gtrade_queries.removeAllServerPendingTradeTransaction(guild.id)

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            self.remove_expired_transactions.start()
        except RuntimeError:
            self.logger.info('remove_expired_transactions task is already launched and is not completed.')

    # Tasks
    @tasks.loop(minutes=1)
    async def remove_expired_transactions(self):
        try:
            currentTime = datetime.now()
            allServersTransactionsMap = gtrade_queries.getAllTradeTransactions()
            if allServersTransactionsMap != None:
                for serverId, serverTransactionMap in allServersTransactionsMap.items():
                    for trxId, trx in serverTransactionMap.items():
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
                            gtrade_queries.removePendingTradeTransaction(serverId, trxId)
                            channel: nextcord.TextChannel = await self.client.fetch_channel(int(trx['sourceChannelId']))
                            await channel.send(f'Sorry {utils.idToUserStr(userId)}, your {trxStr}')
        except Exception as e:
            self.logger.error(f'Error in GTrade.remove_expired_transactions(): {e}')

    # Commands
    @nextcord.slash_command(name = strings.CRAFT_NAME, description = strings.CRAFT_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', True, True)
    async def craftSlash(self,
                         interaction: nextcord.Interaction,
                         name = nextcord.SlashOption(
                            name = 'name',
                            required = True,
                            description = strings.CRAFT_NAME_DESCRIPTION
                         ),
                         value = nextcord.SlashOption(
                            name = 'value',
                            required = True,
                            description = strings.CRAFT_VALUE_DESCRIPTION
                         ),
                         type = nextcord.SlashOption(
                            name = 'type',
                            choices = ['image'],
                            required = True,
                            description = strings.CRAFT_TYPE_DESCRIPTION
                         )):
        await self.commonCraft(interaction, interaction.user, name, value, type)

    @commands.command(aliases = strings.CRAFT_ALIASES, brief = "- " + strings.CRAFT_BRIEF, description = strings.CRAFT_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', True)
    @predicates.isGuildOrUserSubscribed()
    async def craft(self, ctx: Context, name, value, type):
        await self.commonCraft(ctx, ctx.author, name, value, type)

    async def commonCraft(self, context, author, name, value, type):
        try:
            dateTimeObj = datetime.now()
            date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")
            userId = author.id
            userMention = author.mention
            authorName = author.name
            originalServer = 'Direct Message' if context.guild == None else context.guild.name
            value = utils.roundDecimalPlaces(value, 2)
            if value <= Decimal('0'):
                raise EnforcePositiveTransactions
            # validate no existing items with this name in inventory and not too many
            allUserItems = gtrade_queries.getAllUserItems(userId)
            if allUserItems != None:
                if len(allUserItems) >= self.NUM_MAX_ITEMS:
                    raise ItemMaxCount
                for item in allUserItems.values():
                    thisItemName = item['name']
                    if thisItemName == name:
                        raise ItemNameConflict
            # if item type is picture ask for image file or URL and create correct dataJson
            if type == 'image':
                # ask for image file or url until users responds with answer or 'cancel'
                imageObtained = False
                errorMsg = ''
                while(not imageObtained):
                    userResponse: nextcord.Message = await utils.askUserQuestion(self.client, context, author, f"{errorMsg} What image would you like to use? Please send an image file, an image URL, or 'cancel'. (.jpg, .jpeg, .png, .gif)", GBotPropertiesManager.USER_RESPONSE_TIMEOUT_SECONDS)
                    content = userResponse.content
                    attachments = userResponse.attachments
                    # if user's reponse is string
                    if content != '':
                        # if response content starts with command prefix or is cancel then cancel current command
                        if content.lower() == 'cancel' or content.startswith(utils.getServerPrefixOrDefault(userResponse)):
                            raise UserCancelledCommand
                        else:
                            # if URL is valid URL
                            if await utils.isUrlImageContentTypeAndStatus200(content):
                                imageUrl = content
                                imageObtained = True
                            # if URL not valid
                            else:
                                errorMsg = 'Invalid image URL.'
                    # if user's response is file
                    elif attachments != None:
                        imageUrl = attachments[0].url
                        imageObtained = True
                dataJson = { 'imageUrl': imageUrl }
            else:
                raise ItemTypeInvalid
            # try to perform GCoin transaction with validation
            sender = { 'id': userId, 'name': authorName }
            receiver = { 'id': None, 'name': 'GTrade' }
            gcoin_queries.performTransaction(value, date, sender, receiver, 'crafted', '', False, True)
            # create item for user
            gtrade_queries.createItem(userId, name, value, authorName, originalServer, date, name, value, date, type, dataJson)
            await context.send(f"{userMention}, you crafted '{name}' ({type}) for {value} GCoin.")
        except asyncio.TimeoutError:
            await context.send(f'Sorry {userMention}, you did not respond in time.')
        except EnforcePositiveTransactions:
            await context.send(f'Sorry {userMention}, you can not craft items with non-positive values.')
        except EnforceSenderFundsError:
            await context.send(f'Sorry {userMention}, you have insufficient funds.')
        except ItemNameConflict:
            await context.send(f'Sorry {userMention}, you already have an item with this name.')
        except ItemTypeInvalid:
            await context.send(f'Sorry {userMention}, please provide a valid item type.')
        except ItemMaxCount:
            await context.send(f"Sorry {userMention}, you can't have more than {self.NUM_MAX_ITEMS} items.")
        except UserCancelledCommand:
            await context.send(f'{userMention}, item craft has been cancelled.')
        except InvalidOperation:
            await context.send(f'Sorry {userMention}, please enter a valid amount. Remember to use quotes for names that are more than one word.')

    @nextcord.slash_command(name = strings.RENAME_NAME, description = strings.RENAME_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', True, True)
    async def renameSlash(self,
                         interaction: nextcord.Interaction,
                         item = nextcord.SlashOption(
                            name = 'item',
                            required = True,
                            description = strings.RENAME_ITEM_DESCRIPTION
                         ),
                         name = nextcord.SlashOption(
                            name = 'name',
                            required = True,
                            description = strings.RENAME_NAME_DESCRIPTION
                         )):
        await self.commonRename(interaction, interaction.user, item, name)

    @commands.command(aliases = strings.RENAME_ALIASES, brief = "- " + strings.RENAME_BRIEF, description = strings.RENAME_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', True)
    @predicates.isGuildOrUserSubscribed()
    async def rename(self, ctx: Context, item, name):
        await self.commonRename(ctx, ctx.author, item, name)

    async def commonRename(self, context, author, item, name):
        try:
            userId = author.id
            userMention = author.mention
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
                await context.send(f"Sorry {userMention}, you do not have an item named '{item}'.")
                return
            gtrade_queries.renameItem(userId, itemIdToRename, name)
            # update all pending transaction for this item to use the new item name (where author is seller and item name is previous name)
            gtrade_queries.renameItemRelatedPendingTradeTransactions(userId, item, name)
            await context.send(f"{userMention}, you renamed your item '{item}' to '{name}'.")
        except ItemNameConflict:
            await context.send(f'Sorry {userMention}, you already have an item with this name.')

    @nextcord.slash_command(name = strings.DESTROY_NAME, description = strings.DESTROY_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', True, True)
    async def destroySlash(self,
                         interaction: nextcord.Interaction,
                         item = nextcord.SlashOption(
                            name = 'item',
                            required = True,
                            description = strings.DESTROY_ITEM_DESCRIPTION
                         )):
        await self.commonDestroy(interaction, interaction.user, item)

    @commands.command(aliases = strings.DESTROY_ALIASES, brief = "- " + strings.DESTROY_BRIEF, description = strings.DESTROY_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', True)
    @predicates.isGuildOrUserSubscribed()
    async def destroy(self, ctx: Context, item):
        await self.commonDestroy(ctx, ctx.author, item)

    async def commonDestroy(self, context, author, item):
        dateTimeObj = datetime.now()
        date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")
        authorId = author.id
        authorMention = author.mention
        itemTuple = gtrade_queries.getUserItem(authorId, item)
        if itemTuple != None:
            # add remove item from inventory
            gtrade_queries.removeItem(authorId, itemTuple[0])
            # remove any related pending transactions
            gtrade_queries.removeRelatedPendingTradeTransactions(authorId, item)
            # give the user money back
            price = itemTuple[1]['value']
            sender = { 'id': None, 'name': 'GTrade' }
            receiver = { 'id': authorId, 'name': authorMention }
            gcoin_queries.performTransaction(utils.roundDecimalPlaces(price, 2), date, sender, receiver, '', 'destroyed', False, False)
            await context.send(f"{authorMention}, you destroyed your item '{item}' for {price} GCoin.")
        else:
            await context.send(f"Sorry {authorMention}, you do not have an item named '{item}'.")

    @nextcord.slash_command(name = strings.ITEMS_NAME, description = strings.ITEMS_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', True, True)
    async def itemsSlash(self,
                         interaction: nextcord.Interaction,
                         user: nextcord.User = nextcord.SlashOption(
                            name = 'user',
                            required = False,
                            description = strings.ITEMS_USER_DESCRIPTION
                        )):
        await self.commonItems(interaction, interaction.user, user)

    @commands.command(aliases = strings.ITEMS_ALIASES, brief = "- " + strings.ITEMS_BRIEF, description = strings.ITEMS_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', True)
    @predicates.isGuildOrUserSubscribed()
    async def items(self, ctx: Context, user: nextcord.User = None):
        await self.commonItems(ctx, ctx.author, user)

    async def commonItems(self, context, author, user):
        authorMention = author.mention
        if context.guild is None and user != None:
            await context.send(f"Sorry {authorMention}, please use this command on other users in a server.")
        else:
            if isinstance(context, nextcord.Interaction):
                await context.response.defer()
            # if user specified use user
            if user != None:
                if not await utils.isUserInThisGuildAndNotABot(user, context.guild):
                    await context.send(f"Sorry {authorMention}, please specify a user in this guild.")
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
            items = gtrade_queries.getAllUserItems(itemsOwnerId)
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
                    fields.append((f'{i + 1}.) {name}', f'`{value} GCoin`\n`{type}`'))

                pages = pagination.CustomButtonMenuPages(source = pagination.FieldPageSource(fields, thumbnailUrl, f"{itemsOwnerName}'s Items", nextcord.Color.orange(), False, 10))
                await pagination.startPages(context, pages)

            # if no items in inventory
            else:
                await context.send(f"Sorry {authorMention}, {itemsOwnerStr} not have any items.")

    @nextcord.slash_command(name = strings.ITEM_NAME, description = strings.ITEM_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', True, True)
    async def itemSlash(self,
                         interaction: nextcord.Interaction,
                         item = nextcord.SlashOption(
                            name = 'item',
                            required = True,
                            description = strings.ITEM_ITEM_DESCRIPTION
                         )):
        await self.commonItem(interaction, interaction.user, item)

    @commands.command(aliases = strings.ITEM_ALIASES, brief = "- " + strings.ITEM_BRIEF, description = strings.ITEM_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', True)
    @predicates.isGuildOrUserSubscribed()
    async def item(self, ctx: Context, item):
        await self.commonItem(ctx, ctx.author, item)

    async def commonItem(self, context, author, item):
        authorId = author.id
        authorMention = author.mention
        # get authors item with specified name
        itemTuple = gtrade_queries.getUserItem(authorId, item)
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
                embed = nextcord.Embed(color = 0xFFFFFF, title = name, description = f'Owned by {authorMention}')
                
                embed.add_field(name = 'Value', value = gcoinAmount, inline = True)
                embed.add_field(name = 'Date Obtained', value = dateObtained, inline = True)
                embed.add_field(name = 'Date Created', value = dateCreated, inline = True)

                embed.add_field(name = 'Original Value', value = originalValue, inline = True)
                embed.add_field(name = 'Original Name', value = originalName, inline = True)
                embed.add_field(name = 'Original Creator', value = originalCreator, inline = True)
                
                embed.add_field(name = 'Original Server', value = originalServer, inline = True)

                embed.set_image(url = imageUrl)
                if author.avatar != None:
                    embed.set_thumbnail(url = author.avatar.url)
                await context.send(embed = embed)
        # if item does not exist
        else:
            await context.send(f"Sorry {authorMention}, you do not have an item named '{item}'.")

    @nextcord.slash_command(name = strings.MARKET_NAME, description = strings.MARKET_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', False, True)
    async def marketSlash(self, interaction: nextcord.Interaction):
        await self.commonMarket(interaction, interaction.user)

    @commands.command(aliases = strings.MARKET_ALIASES, brief = "- " + strings.MARKET_BRIEF, description = strings.MARKET_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def market(self, ctx: Context):
        await self.commonMarket(ctx, ctx.author)

    async def commonMarket(self, context, author):
        if isinstance(context, nextcord.Interaction):
            await context.response.defer()
        serverId = context.guild.id
        authorId = author.id
        authorMention = author.name
        allServerPending = gtrade_queries.getAllServerPendingTradeTransactions(serverId)
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
                itemName = trx['item']['name']
                itemValue = trx['item']['value']
                # add all items for sale on market (where no one is buyer, seller is not none, and type is 'market')
                if thisBuyerId == None and thisSellerId != None and thisTrxType == 'market':
                    marketSellList.append(f'`{marketSellCount + 1}.) {thisSellerUser.name} is selling {itemName} for {itemValue} GCoin.`')
                    marketSellCount += 1
                # all incoming buys (where author is seller, buyer is not none, and type is 'buy')
                elif thisBuyerId != None and thisSellerId == str(authorId) and thisTrxType == 'buy':
                    incomingBuyList.append(f'`{incomingBuyCount + 1}.) {thisBuyerUser.name} has requested to buy {itemName} from you for {itemValue} GCoin.`')
                    incomingBuyCount += 1
                # all incoming sells (where author is buyer, seller is not none, and type is 'sell')
                elif thisBuyerId == str(authorId) and thisSellerId != None and thisTrxType == 'sell':
                    incomingSellList.append(f'`{incomingSellCount + 1}.) {thisSellerUser.name} has requested to sell you {itemName} for {itemValue} GCoin.`')
                    incomingSellCount += 1
                # all outgoing buys (where author is buyer, seller is not none, and type is 'buy')
                elif thisBuyerId == str(authorId) and thisSellerId != None and thisTrxType == 'buy':
                    outgoingBuyList.append(f'`{outgoingBuyCount + 1}.) {authorMention}, you have requested to buy {itemName} from {thisSellerUser.name} for {itemValue} GCoin.`')
                    outgoingBuyCount += 1
                # all outgoing sells (where author is seller, buyer is not none, type is 'sell')
                elif thisBuyerId != None and thisSellerId == str(authorId) and thisTrxType == 'sell':
                    outgoingSellList.append(f'`{outgoingSellCount + 1}.) {authorMention}, you have requested to sell {itemName} to {thisBuyerUser.name} for {itemValue} GCoin.`')
                    outgoingSellCount += 1

            # add lists to data list if they aren't empty
            data = []
            if len(marketSellList) > 0:
                data.append('**Items For Sale**')
                data.extend(marketSellList)
            if len(incomingBuyList) > 0:
                data.append('**Incoming Buy Requests**')
                data.extend(incomingBuyList)
            if len(incomingSellList) > 0:
                data.append('**Incoming Sell Requests**')
                data.extend(incomingSellList)
            if len(outgoingBuyList) > 0:
                data.append('**Outgoing Buy Requests**')
                data.extend(outgoingBuyList)
            if len(outgoingSellList) > 0:
                data.append('**Outgoing Sell Requests**')
                data.extend(outgoingSellList)

            pages = pagination.CustomButtonMenuPages(source = pagination.DescriptionPageSource(data, "Market Items", nextcord.Color.orange(), author.avatar.url if author.avatar != None else None, 10))
            await pagination.startPages(context, pages)
        else:
            await context.send(f"Sorry {author.mention}, there are no available items for sale or transaction requests.")

    @nextcord.slash_command(name = strings.BUY_NAME, description = strings.BUY_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', False, True)
    async def buySlash(self,
                         interaction: nextcord.Interaction,
                         item = nextcord.SlashOption(
                            name = 'item',
                            required = True,
                            description = strings.BUY_ITEM_DESCRIPTION
                         ),
                         user: nextcord.User = nextcord.SlashOption(
                            name = 'user',
                            required = True,
                            description = strings.BUY_USER_DESCRIPTION
                        )):
        await self.commonBuy(interaction, interaction.user, item, user)

    @commands.command(aliases = strings.BUY_ALIASES, brief = "- " + strings.BUY_BRIEF, description = strings.BUY_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def buy(self, ctx: Context, item, user: nextcord.User):
        await self.commonBuy(ctx, ctx.author, item, user)

    async def commonBuy(self, context, author, item, user):
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
                await context.send(f"Sorry {authorMention}, please specify a user in this guild.")
                return
            if authorId == userId:
                raise EnforceSenderReceiverNotEqual
            itemTuple = gtrade_queries.getUserItem(userId, item)
            if itemTuple != None:
                price = utils.roundDecimalPlaces(itemTuple[1]['value'], 2)
                pendingSellTrx = gtrade_queries.getPendingTradeTransaction(serverId, 'sell', item, userId, authorId)
                pendingMarketTrx = gtrade_queries.getPendingTradeTransaction(serverId, 'market', item, userId)
                # complete a user's pending sell request if exists, or buy an item for sale in the server's market if exists
                pendingTrx = None
                if pendingSellTrx != None:
                    pendingTrx = pendingSellTrx
                elif pendingMarketTrx != None:
                    pendingTrx = pendingMarketTrx
                if pendingTrx != None:
                    self.completeTradeTransaction(serverId, date, pendingTrx[0], itemTuple, userObj, authorObj)
                    await context.send(f"{authorMention}, you bought '{item}' from {userMention} for {price} GCoin.")
                # create a request to buy from a user if no pending sells exist (market or request)
                else:
                    pendingBuyTrx = gtrade_queries.getPendingTradeTransaction(serverId, 'buy', item, userId, authorId)
                    # if buy request already created, remove it
                    if pendingBuyTrx != None:
                        gtrade_queries.removePendingTradeTransaction(serverId, pendingBuyTrx[0])
                        await context.send(f"{authorMention}, you are no longer requesting to buy '{item}' from {userMention}.")
                    else:
                        existingItems = gtrade_queries.getAllUserItems(authorId)
                        if existingItems != None:
                            if len(existingItems) >= self.NUM_MAX_ITEMS:
                                raise ItemMaxCount
                            for existingItem in existingItems.values():
                                name = existingItem['name']
                                if name == item:
                                    raise ItemNameConflict
                        if price > gcoin_queries.getUserBalance(authorId):
                            raise EnforceSenderFundsError
                        gtrade_queries.createPendingTradeTransaction(serverId, date, str(channelId), itemTuple[1], 'buy', str(userId), str(authorId))
                        await context.send(f"{userMention}, {authorMention} wants to buy '{item}' from you for {price} GCoin.")
            else:
                await context.send(f"Sorry {authorMention}, {userMention} does not have an item named '{item}'.")
        except EnforceRealUsersError:
            await context.send(f'Sorry {authorMention}, please specify a valid user.')
        except EnforceSenderReceiverNotEqual:
            await context.send(f'Sorry {authorMention}, you can not buy from or sell to yourself.')
        except EnforcePositiveTransactions:
            await context.send(f'Sorry {authorMention}, you can not buy or sell items for non-positive amounts.')
        except EnforceSenderFundsError:
            await context.send(f'Sorry {authorMention}, you have insufficient funds.')
        except ItemNameConflict:
            await context.send(f'Sorry {authorMention}, you already have an item with this name.')
        except ItemMaxCount:
            await context.send(f"Sorry {authorMention}, you can't have more than {self.NUM_MAX_ITEMS} items.")

    @nextcord.slash_command(name = strings.SELL_NAME, description = strings.SELL_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', False, True)
    async def sellSlash(self,
                         interaction: nextcord.Interaction,
                         item = nextcord.SlashOption(
                            name = 'item',
                            required = True,
                            description = strings.SELL_ITEM_DESCRIPTION
                         ),
                         user: nextcord.User = nextcord.SlashOption(
                            name = 'user',
                            required = False,
                            description = strings.SELL_USER_DESCRIPTION
                        )):
        await self.commonSell(interaction, interaction.user, item, user)

    @commands.command(aliases = strings.SELL_ALIASES, brief = "- " + strings.SELL_BRIEF, description = strings.SELL_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_gtrade', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def sell(self, ctx: Context, item, user: nextcord.User = None):
        await self.commonSell(ctx, ctx.author, item, user)

    async def commonSell(self, context, author, item, user):
        dateTimeObj = datetime.now()
        date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")
        serverId = context.guild.id
        channelId = context.channel.id
        authorId = author.id
        authorMention = author.mention
        authorObj = { 'id': authorId, 'name': author.name }
        itemTuple = gtrade_queries.getUserItem(authorId, item)
        if itemTuple != None:
            try:
                price = utils.roundDecimalPlaces(itemTuple[1]['value'], 2)
                if user is None:
                    pendingMarketTrx = gtrade_queries.getPendingTradeTransaction(serverId, 'market', item, authorId)
                    # if no pending market sale for the item already, create one
                    if pendingMarketTrx == None:
                        gtrade_queries.createPendingTradeTransaction(serverId, date, str(channelId), itemTuple[1], 'market', str(authorId))
                        await context.send(f"{authorMention}, your item '{item}' is for sale for {price} GCoin.")
                    # if pending market sale for item already, remove it
                    else:
                        gtrade_queries.removePendingTradeTransaction(serverId, pendingMarketTrx[0])
                        await context.send(f"{authorMention}, your item '{item}' is no longer for sale.")
                else:
                    userId = user.id
                    userMention = user.mention
                    userObj = { 'id': userId, 'name': user.name }
                    if not await utils.isUserInThisGuildAndNotABot(user, context.guild):
                        await context.send(f"Sorry {authorMention}, please specify a user in this guild.")
                        return
                    if authorId == userId:
                            raise EnforceSenderReceiverNotEqual
                    pendingBuyTrx = gtrade_queries.getPendingTradeTransaction(serverId, 'buy', item, authorId, userId)
                    pendingSellTrx = gtrade_queries.getPendingTradeTransaction(serverId, 'sell', item, authorId, userId)
                    # if sell request already created, remove it
                    if pendingSellTrx != None:
                        gtrade_queries.removePendingTradeTransaction(serverId, pendingSellTrx[0])
                        await context.send(f"{authorMention}, you are no longer requesting to sell '{item}' to {userMention}.")
                    # if no pending buy request, create sell request
                    elif pendingBuyTrx == None:
                        gtrade_queries.createPendingTradeTransaction(serverId, date, str(channelId), itemTuple[1], 'sell', str(authorId), str(userId))
                        await context.send(f"{userMention}, {authorMention} wants to sell you '{item}' for {price} GCoin.")
                    # if pending buy request exists, complete it by selling
                    else:
                        self.completeTradeTransaction(serverId, date, pendingBuyTrx[0], itemTuple, authorObj, userObj)
                        await context.send(f"{authorMention}, you sold '{item}' to {userMention} for {price} GCoin.")
            except EnforceRealUsersError:
                await context.send(f'Sorry {authorMention}, please specify a valid user.')
            except EnforceSenderReceiverNotEqual:
                await context.send(f'Sorry {authorMention}, you can not buy from or sell to yourself.')
            except EnforcePositiveTransactions:
                await context.send(f'Sorry {authorMention}, you can not buy or sell items for negative amounts.')
            except EnforceSenderFundsError:
                await context.send(f'Sorry {authorMention}, {userMention} has insufficient funds.')
            except ItemNameConflict:
                await context.send(f'Sorry {authorMention}, {userMention} already has an item with this name.')
            except ItemMaxCount:
                await context.send(f"Sorry {authorMention}, {userMention} already has {self.NUM_MAX_ITEMS} items.")
        else:
            await context.send(f"Sorry {authorMention}, you do not have an item named '{item}'.")

    def completeTradeTransaction(self, serverId, date, pendingTrxId, itemTuple, seller, buyer):
        # if buyer already has item with this name or already max items
        existingItems = gtrade_queries.getAllUserItems(buyer['id'])
        if existingItems != None:
            if len(existingItems) >= self.NUM_MAX_ITEMS:
                raise ItemMaxCount
            for existingItem in existingItems.values():
                existingItemName = existingItem['name']
                if existingItemName == itemTuple[1]['name']:
                    raise ItemNameConflict

        # perform GCoin trx between users
        gcoin_queries.performTransaction(utils.roundDecimalPlaces(itemTuple[1]['value'], 2), date, buyer, seller, 'bought', 'sold', True, True)

        # remove all pending transactions affected
        gtrade_queries.removePendingTradeTransactionAndOthersAffected(serverId, pendingTrxId)

        # perform the item handshake
        originalName = itemTuple[1]['originalName']
        originalValue = itemTuple[1]['originalValue']
        originalCreator = itemTuple[1]['originalCreator']
        originalServer = itemTuple[1]['originalServer']
        dateCreated = itemTuple[1]['dateCreated']
        name = itemTuple[1]['name']
        value = itemTuple[1]['value']
        dataType = itemTuple[1]['dataType']
        dataJson = itemTuple[1]['dataJson']
        gtrade_queries.createItem(buyer['id'], originalName, originalValue, originalCreator, originalServer, dateCreated, name, value, date, dataType, dataJson)
        gtrade_queries.removeItem(seller['id'], itemTuple[0])

def setup(client: commands.Bot):
    client.add_cog(GTrade(client))