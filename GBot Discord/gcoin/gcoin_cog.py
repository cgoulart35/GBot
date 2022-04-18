#region IMPORTS
import logging
import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context
from datetime import datetime

import utils
import predicates
import gcoin.gcoin_queries
from exceptions import EnforceRealUsersError, EnforceSenderReceiverNotEqual, EnforcePositiveTransactions, EnforceSenderFundsError
#endregion

class GCoin(commands.Cog):

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()
        self.NUM_TRX_HISTORY_TO_DISPLAY = 20

    # Commands
    @commands.command(aliases=['sd'], brief = "- Send GCoin to another user in this server.", description = "Send GCoin to another user in this server.")
    @predicates.isFeatureEnabledForServer('toggle_gcoin')
    @predicates.isMessageSentInGuild()
    async def send(self, ctx: Context, user: nextcord.User, amount):
        try:
            dateTimeObj = datetime.now()
            date = dateTimeObj.strftime("%m/%d/%y %I:%M:%S %p")
            author = ctx.author
            authorMention = author.mention
            sender = { 'id': author.id, 'name': author.name }
            receiver = { 'id': user.id, 'name': user.name }
            if not await utils.isUserInGuild(user, ctx.guild):
                await ctx.send(f'Sorry {authorMention}, please specify a user in this guild.')
                return
            gcoinRounded = utils.roundDecimalPlaces(amount, 2)
            gcoin.gcoin_queries.performTransaction(gcoinRounded, date, sender, receiver, 'sent', 'received', True, True)
            await ctx.send(f'{author.name}, you sent {user.mention} {gcoinRounded} GCoin.')
        except EnforceRealUsersError:
            await ctx.send(f'Sorry {authorMention}, please specify a valid user.')
        except EnforceSenderReceiverNotEqual:
            await ctx.send(f'Sorry {authorMention}, you can not send GCoin to yourself.')
        except EnforcePositiveTransactions:
            await ctx.send(f'Sorry {authorMention}, you can not send a non-positive amount.')
        except EnforceSenderFundsError:
            await ctx.send(f'Sorry {authorMention}, you have insufficient funds.')
        except:
            await ctx.send(f'Sorry {authorMention}, please enter a valid amount.')

    @commands.command(aliases=['ws'], brief = "- Show wallets of all users in this server.", description = "Show wallets of all users in this server.")
    @predicates.isFeatureEnabledForServer('toggle_gcoin')
    @predicates.isMessageSentInGuild()
    async def wallets(self, ctx: Context):
        guild = ctx.guild
        serverBalances = []
        async for member in guild.fetch_members():
            balance = gcoin.gcoin_queries.getUserBalance(member.id)
            if balance > 0:
                memberBalance = { 'name': member.name, 'balance': balance}
                serverBalances.append(memberBalance)
        
        if serverBalances:
            sortedServerBalances = sorted(serverBalances, key=lambda memberBalance: memberBalance['balance'], reverse=True)
            memberStr = ''
            balanceStr = ''
            for i in range(0, len(sortedServerBalances)):
                memberBalance = sortedServerBalances[i]
                name = memberBalance['name']
                balance = memberBalance['balance']
                memberStr += f'`{i + 1}.) {name}`\n'
                balanceStr += f'`{balance}`\n'
            embed = nextcord.Embed(color = nextcord.Color.yellow(), title = f"User Wallets")
            embed.add_field(name = 'User', value = memberStr, inline = True)
            embed.add_field(name = 'Wallet', value = balanceStr, inline = True)
            embed.set_thumbnail(url = guild.icon.url)
            await ctx.send(embed = embed)
        else:
            await ctx.send(f'Sorry {ctx.author.mention}, no users have any positive balances.')

    @commands.command(aliases=['w'], brief = "- Show your wallet, or another user's wallet in this server.", description = "Show your wallet, or another user's wallet in this server.")
    async def wallet(self, ctx: Context, user: nextcord.User = None):
        utils.ifInGuildAndFeatureOffThrowError(ctx, 'toggle_gcoin')
        author = ctx.author
        authorMention = author.mention
        if ctx.guild is None and user != None:
            await ctx.send(f"Sorry {authorMention}, please use this command on other users in a server.")
        else:
            if ctx.guild is not None and user != None:
                if not await utils.isUserInGuild(user, ctx.guild):
                    await ctx.send(f"Sorry {authorMention}, please specify a user in this guild.")
                    return
            if user != None:
                userId = user.id
                userMention = user.name
                thumbnailUrl = user.avatar.url
            else:
                userId = author.id
                userMention = author.name
                thumbnailUrl = author.avatar.url
            balance = gcoin.gcoin_queries.getUserBalance(userId)
            embed = nextcord.Embed(color = nextcord.Color.yellow(), title = f"{userMention}'s Wallet")
            embed.add_field(name = 'Wallet', value = f"`{balance}`", inline = False)
            embed.set_thumbnail(url = thumbnailUrl)
            await ctx.send(embed = embed)

    @commands.command(aliases=['hs'], brief = "- Show your transaction history, or another user's transaction history in this server. (admin optional)", description = f"Show your transaction history, or another user's transaction history in this server. Admin role needed to show other user's history. (admin optional)")
    async def history(self, ctx: Context, user: nextcord.User = None):
        utils.ifInGuildAndFeatureOffThrowError(ctx, 'toggle_gcoin')
        author = ctx.author
        authorMention = author.mention
        if ctx.guild is None and user != None:
            await ctx.send(f"Sorry {authorMention}, please use this command on other users in a server as an admin.")
        else:
            if ctx.guild is not None and user != None:
                if not await utils.isUserInGuild(user, ctx.guild):
                    await ctx.send(f"Sorry {authorMention}, please specify a user in this guild.")
                    return
            if user != None:
                if not utils.isUserAdminOrOwner(author, ctx.guild):
                    await ctx.send(f"Sorry {authorMention}, you need to be an admin to view other user's history.")
                    return
                userId = user.id
                userMention = user.name
                thumbnailUrl = user.avatar.url
                noHistoryErrorMsg = f'{user.mention} has no transaction history.'
            else:
                userId = author.id
                userMention = author.name
                thumbnailUrl = author.avatar.url
                noHistoryErrorMsg = 'you have no transaction history.'
            history = gcoin.gcoin_queries.getUserTransactionHistory(userId)
            if history != None:
                embed = nextcord.Embed(color = nextcord.Color.yellow(), title = f"{userMention}'s Transactions")
                sortedHistory = sorted(history.values(), key=lambda transaction: datetime.strptime(transaction["date"], "%m/%d/%y %I:%M:%S %p"), reverse=True)
                withStr = ''
                dateStr = ''
                gcoinStr = ''
                for i in range(self.NUM_TRX_HISTORY_TO_DISPLAY):
                    if i == len(sortedHistory):
                        break
                    transaction = sortedHistory[i]
                    other = transaction['other']
                    memo = transaction['memo']
                    date = datetime.strptime(transaction["date"], "%m/%d/%y %I:%M:%S %p").strftime("%m/%d/%y %I:%M %p")
                    gcoinAmount = transaction['gcoin']
                    withStr += f'`{i + 1}.) {other} ({memo})`\n'
                    dateStr += f'`{date}`\n'
                    gcoinStr += f'`{gcoinAmount}`\n'
                embed.add_field(name = 'With', value = withStr, inline = True)
                embed.add_field(name = 'Date', value = dateStr, inline = True)
                embed.add_field(name = 'GCoin', value = gcoinStr, inline = True)
                embed.set_thumbnail(url = thumbnailUrl)
                await ctx.send(embed = embed)
            else:
                await ctx.send(f'Sorry {authorMention}, {noHistoryErrorMsg}')

def setup(client: commands.Bot):
    client.add_cog(GCoin(client))