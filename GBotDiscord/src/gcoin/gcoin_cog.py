#region IMPORTS
import logging
import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context
from decimal import Decimal
from datetime import datetime

from GBotDiscord.src import strings
from GBotDiscord.src import utils
from GBotDiscord.src import pagination
from GBotDiscord.src import predicates
from GBotDiscord.src.gcoin import gcoin_queries
from GBotDiscord.src.exceptions import EnforceRealUsersError, EnforceSenderReceiverNotEqual, EnforcePositiveTransactions, EnforceSenderFundsError
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

class GCoin(commands.Cog):

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()
        self.NUM_TRX_HISTORY_TO_DISPLAY = 100

    # Commands
    @nextcord.slash_command(name = strings.SEND_NAME, description = strings.SEND_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_gcoin', False, True)
    async def sendSlash(self,
                        interaction: nextcord.Interaction,
                        user: nextcord.User = nextcord.SlashOption(
                            name = 'user',
                            required = True,
                            description = strings.SEND_USER_DESCRIPTION
                        ),
                        amount = nextcord.SlashOption(
                            name = "amount",
                            description = strings.SEND_AMOUNT_DESCRIPTION)
                        ):
        await self.commonSend(interaction, interaction.user, user, Decimal(str(amount)))

    @commands.command(aliases = strings.SEND_ALIASES, brief = "- " + strings.SEND_BRIEF, description = strings.SEND_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_gcoin', False)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def send(self, ctx: Context, user: nextcord.User, amount: Decimal):
        await self.commonSend(ctx, ctx.author, user, amount)

    async def commonSend(self, context, author, user: nextcord.User, amount: Decimal):
        try:
            dateTimeObj = datetime.now()
            date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")
            authorMention = author.mention
            sender = { 'id': author.id, 'name': author.name }
            receiver = { 'id': user.id, 'name': user.name }
            if not await utils.isUserInThisGuildAndNotABot(user, context.guild):
                await context.send(f'Sorry {authorMention}, please specify a user in this guild.')
                return
            gcoinRounded = utils.roundDecimalPlaces(amount, 2)
            gcoin_queries.performTransaction(gcoinRounded, date, sender, receiver, 'sent', 'received', True, True)
            await context.send(f'{authorMention}, you sent {user.mention} {gcoinRounded} GCoin.')
        except EnforceRealUsersError:
            await context.send(f'Sorry {authorMention}, please specify a valid user.')
        except EnforceSenderReceiverNotEqual:
            await context.send(f'Sorry {authorMention}, you can not send GCoin to yourself.')
        except EnforcePositiveTransactions:
            await context.send(f'Sorry {authorMention}, you can not send a non-positive amount.')
        except EnforceSenderFundsError:
            await context.send(f'Sorry {authorMention}, you have insufficient funds.')
        except:
            await context.send(f'Sorry {authorMention}, please enter a valid amount.')

    @nextcord.slash_command(name = strings.WALLETS_NAME, description = strings.WALLETS_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_gcoin', False, True)
    async def walletsSlash(self, interaction: nextcord.Interaction):
        await self.commonWallets(interaction, interaction.user)

    @commands.command(aliases = strings.WALLETS_ALIASES, brief = "- " + strings.WALLETS_BRIEF, description = strings.WALLETS_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_gcoin', False)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def wallets(self, ctx: Context):
        await self.commonWallets(ctx, ctx.author)

    async def commonWallets(self, context, author):
        if isinstance(context, nextcord.Interaction):
            await context.response.defer()
        guild = context.guild
        serverBalances = []
        async for member in guild.fetch_members():
            balance = gcoin_queries.getUserBalance(member.id)
            if balance > 0:
                memberBalance = { 'name': member.name, 'balance': balance}
                serverBalances.append(memberBalance)
        
        if serverBalances:
            fields = []
            sortedServerBalances = sorted(serverBalances, key=lambda memberBalance: memberBalance['balance'], reverse=True)
            for i in range(0, len(sortedServerBalances)):
                memberBalance = sortedServerBalances[i]
                name = memberBalance['name']
                balance = memberBalance['balance']
                fields.append((f'{i + 1}.) {name}', f'`{balance} GCoin`'))

            pages = pagination.CustomButtonMenuPages(source = pagination.FieldPageSource(fields, guild.icon.url if guild.icon != None else None, "User Wallets", nextcord.Color.yellow(), False, 10))
            await pagination.startPages(context, pages)
        else:
            await context.send(f'Sorry {author.mention}, no users have any positive balances.')

    @nextcord.slash_command(name = strings.WALLET_NAME, description = strings.WALLET_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isFeatureEnabledForServer('toggle_gcoin', False, True)
    async def walletSlash(self,
                          interaction: nextcord.Interaction,
                          user: nextcord.User = nextcord.SlashOption(
                            name = 'user',
                            required = False,
                            description = strings.WALLET_USER_DESCRIPTION
                        )):
        await self.commonWallet(interaction, interaction.user, user)

    @commands.command(aliases = strings.WALLET_ALIASES, brief = "- " + strings.WALLET_BRIEF, description = strings.WALLET_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_gcoin', True)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', True)
    @predicates.isGuildOrUserSubscribed()
    async def wallet(self, ctx: Context, user: nextcord.User = None):
        await self.commonWallet(ctx, ctx.author, user)

    async def commonWallet(self, context, author, user):
        authorMention = author.mention
        if context.guild is None and user != None:
            await context.send(f"Sorry {authorMention}, please use this command on other users in a server.")
        else:
            if context.guild is not None and user != None:
                if not await utils.isUserInThisGuildAndNotABot(user, context.guild):
                    await context.send(f"Sorry {authorMention}, please specify a user in this guild.")
                    return
            if user != None:
                userId = user.id
                userMention = user.name
                if user.avatar != None:
                    thumbnailUrl = user.avatar.url
                else:
                    thumbnailUrl = None
            else:
                userId = author.id
                userMention = author.name
                if author.avatar != None:
                    thumbnailUrl = author.avatar.url
                else:
                    thumbnailUrl = None                    
                    
            balance = gcoin_queries.getUserBalance(userId)
            embed = nextcord.Embed(color = nextcord.Color.yellow(), title = f"{userMention}'s Wallet")
            embed.add_field(name = 'Wallet', value = f"`{balance}`", inline = False)
            if thumbnailUrl != None:
                embed.set_thumbnail(url = thumbnailUrl)
            await context.send(embed = embed)

    @nextcord.slash_command(name = strings.HISTORY_NAME, description = strings.HISTORY_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isFeatureEnabledForServer('toggle_gcoin', False, True)
    async def historySlash(self,
                          interaction: nextcord.Interaction,
                          user: nextcord.User = nextcord.SlashOption(
                            name = 'user',
                            required = False,
                            description = strings.HISTORY_USER_DESCRIPTION
                        )):
        await self.commonHistory(interaction, interaction.user, user)

    @commands.command(aliases = strings.HISTORY_ALIASES, brief = "- " + strings.HISTORY_BRIEF, description = strings.HISTORY_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_gcoin', True)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', True)
    @predicates.isGuildOrUserSubscribed()
    async def history(self, ctx: Context, user: nextcord.User = None):
        await self.commonHistory(ctx, ctx.author, user)

    async def commonHistory(self, context, author, user):
        authorMention = author.mention
        if context.guild is None and user != None:
            await context.send(f"Sorry {authorMention}, please use this command on other users in a server as an admin.")
        else:
            if isinstance(context, nextcord.Interaction):
                await context.response.defer()
            if context.guild is not None and user != None:
                if not await utils.isUserInThisGuildAndNotABot(user, context.guild):
                    await context.send(f"Sorry {authorMention}, please specify a user in this guild.")
                    return
            if user != None:
                if not utils.isUserAdminOrOwner(author, context.guild):
                    await context.send(f"Sorry {authorMention}, you need to be an admin to view other user's history.")
                    return
                userId = user.id
                userMention = user.name
                if user.avatar != None:
                    thumbnailUrl = user.avatar.url
                else:
                    thumbnailUrl = None                
                noHistoryErrorMsg = f'{user.mention} has no transaction history.'
            else:
                userId = author.id
                userMention = author.name
                if author.avatar != None:
                    thumbnailUrl = author.avatar.url
                else:
                    thumbnailUrl = None                 
                noHistoryErrorMsg = 'you have no transaction history.'
            history = gcoin_queries.getUserTransactionHistory(userId)
            if history != None:
                sortedHistory = sorted(history.values(), key=lambda transaction: datetime.strptime(transaction["date"], "%m/%d/%y %I:%M:%S %p"), reverse=True)
                fields = []
                for i in range(self.NUM_TRX_HISTORY_TO_DISPLAY):
                    if i == len(sortedHistory):
                        break
                    transaction = sortedHistory[i]
                    other = transaction['other']
                    memo = transaction['memo']
                    date = datetime.strptime(transaction["date"], "%m/%d/%y %I:%M:%S %p").strftime("%m/%d/%y %I:%M %p")
                    gcoinAmount = transaction['gcoin']
                    fields.append((f'{i + 1}.) {other} ({memo})', f'`{date}`\n`{gcoinAmount} GCoin`'))

                pages = pagination.CustomButtonMenuPages(source = pagination.FieldPageSource(fields, thumbnailUrl, f"{userMention}'s Transactions", nextcord.Color.yellow(), False, 10))
                await pagination.startPages(context, pages)

            else:
                await context.send(f'Sorry {authorMention}, {noHistoryErrorMsg}')

def setup(client: commands.Bot):
    client.add_cog(GCoin(client))