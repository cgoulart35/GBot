#region IMPORTS
import logging
import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context
from decimal import Decimal, InvalidOperation
from datetime import datetime

from GBotDiscord.src import presentation
from GBotDiscord.src import strings
from GBotDiscord.src import utils
from GBotDiscord.src import pagination
from GBotDiscord.src import predicates
from GBotDiscord.src.gcoin import gcoin_queries
from GBotDiscord.src.leaderboards import leaderboards_queries
from GBotDiscord.src.exceptions import EnforceRealUsersError, EnforceSenderReceiverNotEqual, EnforcePositiveTransactions, EnforceSenderFundsError
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.firebase import GBotFirebaseService
#endregion

LEADERBOARD_URL = 'https://gbot.stormerg.com/leaderboards.html'
DATE_FORMAT = "%m/%d/%y %I:%M:%S %p"
MAX_NOTE_LENGTH = 100
RANKING_PER_PAGE = 10

def medal(index):
    return ['🥇', '🥈', '🥉'][index] if index < 3 else f'{index + 1}.'

def avatarOf(user):
    return user.avatar.url if user.avatar is not None else None

def sortedHistory(history):
    return sorted((history or {}).values(), key = lambda transaction: datetime.strptime(transaction['date'], DATE_FORMAT), reverse = True)

def describeTransaction(transaction):
    return f"`{presentation.formatGCoin(transaction['gcoin'])}` {transaction['other']} ({transaction['memo']})"

class SendFlow(pagination.OwnedView):
    # 💸 Send, on its own private message so a public wallet keeps showing the wallet: who, then a
    # form for the amount, then a confirm with what you'll have left.
    def __init__(self, cog, guild, author):
        super().__init__()
        self.cog = cog
        self.guild = guild
        self.ownerId = author.id
        self.author = author
        self.receiver = None
        self.amount = None
        self.note = ''

    def pickEmbed(self, notice = None):
        self.clear_items()
        self.picker(nextcord.ui.UserSelect, self.pick, 'Pick a member…', row = 0)
        embed = presentation.brandEmbed(title = '💸 Send GCoin', description = 'Who are you sending GCoin to?', feature = 'GCoin')
        if notice:
            embed.add_field(name = '​', value = notice, inline = False)
        return embed

    async def pick(self, interaction, member):
        # a form has to be the press's first answer, so its checks wait for the submit
        problem = self.cog.receiverProblem(self.author, member, self.guild)
        if problem:
            await interaction.response.edit_message(embed = self.pickEmbed(f'❌ {problem}'), view = self)
            return
        self.receiver = member
        await interaction.response.send_modal(self.cog.amountForm(member, self.submitted))

    async def submitted(self, interaction, values):
        await interaction.response.defer()
        await predicates.recheck(interaction, feature = 'toggle_gcoin')
        embed = await self.prepare(values)
        await interaction.edit_original_message(embed = embed, view = self)

    async def prepare(self, values):
        # checked now, so a refusal says so before anything is confirmed
        problem, amount, left = await self.cog.checkSend(self.author, self.receiver, values[0])
        if problem:
            return self.pickEmbed(f'❌ {problem}')
        self.amount = amount
        self.note = values[1][:MAX_NOTE_LENGTH] if len(values) > 1 else ''
        self.clear_items()
        self.button('💸', self.confirmed, label = 'Send', style = nextcord.ButtonStyle.success)
        self.button('✖️', self.cancelled, label = 'Cancel')
        note = f'\n> {self.note}' if self.note else ''
        return presentation.warningEmbed(title = f'💸 Send {presentation.formatGCoin(amount)} GCoin to {self.receiver.display_name}?', description = f"You'll have **{presentation.formatGCoin(left)} GCoin** left.{note}", feature = 'GCoin')

    async def confirmed(self, interaction):
        await interaction.response.defer()
        await predicates.recheck(interaction, feature = 'toggle_gcoin')
        self.stop()
        problem = await self.cog.transfer(interaction.channel, self.author, self.receiver, self.amount, self.note)
        text = f'❌ {problem}' if problem else f'💸 You sent {self.receiver.mention} **{presentation.formatGCoin(self.amount)} GCoin**.'
        await interaction.edit_original_message(content = text, embed = None, view = None)

    async def cancelled(self, interaction):
        self.stop()
        await interaction.response.edit_message(content = '🚫 Cancelled, so nothing was sent.', embed = None, view = None)

class WalletCard(pagination.OwnedView):
    # /gcoin: a wallet, yours or someone else's, with what you'd do next
    def __init__(self, cog, guild, author, member, isAdmin):
        super().__init__()
        self.cog = cog
        self.guild = guild
        self.author = author
        self.member = member
        self.isAdmin = isAdmin

    @property
    def isOwn(self):
        return self.member.id == self.author.id

    async def render(self):
        balance, history, rank = await GBotFirebaseService.run(self.cog.walletFacts, self.member.id, self.guild)
        title = '💰 Your wallet' if self.isOwn else f"💰 {self.member.display_name}'s wallet"
        embed = presentation.brandEmbed(title = title, description = f'**{presentation.formatGCoin(balance)} GCoin**', feature = 'GCoin')
        if avatarOf(self.member):
            embed.set_thumbnail(url = avatarOf(self.member))
        # what came in and went out last only belongs on your own, as someone else's history is theirs
        if self.isOwn:
            lastIn = next((transaction for transaction in history if not transaction['gcoin'].startswith('-')), None)
            lastOut = next((transaction for transaction in history if transaction['gcoin'].startswith('-')), None)
            embed.add_field(name = 'Last in', value = describeTransaction(lastIn) if lastIn else 'Nothing yet', inline = True)
            embed.add_field(name = 'Last out', value = describeTransaction(lastOut) if lastOut else 'Nothing yet', inline = True)
        if rank is not None:
            embed.add_field(name = 'This server', value = rank, inline = True)
        self.clear_items()
        if self.guild is not None:
            label = 'Send' if self.isOwn else f'Send to {self.member.display_name}'[:80]
            self.button('💸', self.sendGCoin, label = label, style = nextcord.ButtonStyle.success)
        if self.isOwn or self.isAdmin:
            self.button('📜', self.showHistory, label = 'History', style = nextcord.ButtonStyle.primary)
        self.button('🏆', self.showRanking, label = 'Ranking')
        return embed

    async def sendGCoin(self, interaction):
        flow = SendFlow(self.cog, self.guild, interaction.user)
        if self.isOwn:
            await interaction.response.send_message(embed = flow.pickEmbed(), view = flow, ephemeral = True)
            return
        problem = self.cog.receiverProblem(interaction.user, self.member, self.guild)
        if problem:
            await presentation.sendError(interaction, problem, feature = 'GCoin')
            return
        flow.receiver = self.member
        async def submitted(submit, values):
            # the confirm is a new private message, as a form's own reply can't edit a public card
            await submit.response.defer(ephemeral = True, with_message = True)
            await predicates.recheck(submit, feature = 'toggle_gcoin')
            embed = await flow.prepare(values)
            await submit.send(embed = embed, view = flow, ephemeral = True)
        await interaction.response.send_modal(self.cog.amountForm(self.member, submitted))

    async def showHistory(self, interaction):
        await interaction.response.defer(ephemeral = True)
        await predicates.recheck(interaction, feature = 'toggle_gcoin', privateMessagesAllowed = True)
        await self.cog.commonHistory(interaction, interaction.user, None if self.isOwn else self.member)

    async def showRanking(self, interaction):
        await interaction.response.defer(ephemeral = True)
        await predicates.recheck(interaction, feature = 'toggle_gcoin', privateMessagesAllowed = True)
        await self.cog.openRanking(interaction)

class RankingPages(pagination.CustomButtonMenuPages):
    # 🏆 Ranking: this server's wallets, or everyone's everywhere, with a link to the website
    def __init__(self, sources):
        self.sources = sources
        self.tab = next(iter(sources))
        super().__init__(sources[self.tab])

    def needsControls(self):
        return True

    async def render(self):
        embed = await super().render()
        for tab, (emoji, label) in (('server', ('🏠', 'This server')), ('everywhere', ('🌍', 'Everywhere'))):
            if tab in self.sources:
                self.button(emoji, self.tabCallback(tab), label = label, style = nextcord.ButtonStyle.primary if tab == self.tab else nextcord.ButtonStyle.secondary, row = 1)
        self.link('🔗', 'Website', LEADERBOARD_URL, row = 1)
        return embed

    def tabCallback(self, tab):
        async def callback(interaction):
            self.tab = tab
            self.source = self.sources[tab]
            self.current_page = 0
            await self.show(interaction)
        return callback

class GCoin(commands.Cog):

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()
        self.NUM_TRX_HISTORY_TO_DISPLAY = 100

    # Commands
    @nextcord.slash_command(name = strings.GCOIN_NAME, description = strings.GCOIN_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isFeatureEnabledForServer('toggle_gcoin', True, True)
    async def gcoinSlash(self,
                         interaction: nextcord.Interaction,
                         user: nextcord.User = nextcord.SlashOption(
                            name = 'user',
                            required = False,
                            description = strings.GCOIN_USER_DESCRIPTION
                        )):
        await self.commonWallet(interaction, interaction.user, user)

    @commands.command(name = strings.GCOIN_NAME, aliases = strings.GCOIN_ALIASES, brief = "- " + strings.GCOIN_BRIEF, description = strings.GCOIN_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_gcoin', True)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', True)
    @predicates.isGuildOrUserSubscribed()
    async def gcoin(self, ctx: Context, user: nextcord.User = None):
        await self.commonWallet(ctx, ctx.author, user)

    @nextcord.user_command(name = strings.GCOIN_VIEW_WALLET_NAME, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_gcoin', False, True)
    async def viewWallet(self, interaction: nextcord.Interaction, member: nextcord.Member):
        await self.commonWallet(interaction, interaction.user, member)

    async def commonWallet(self, context, author, user):
        # A slash wallet is private. A prefix one is public, so it can be shown off, and its buttons
        # open what is private on its own message.
        if context.guild is None and user is not None:
            await presentation.sendError(context, f"Sorry {author.mention}, please use this command on other users in a server.")
            return
        if user is not None and user.id != author.id and not await utils.isUserInThisGuildAndNotABot(user, context.guild):
            await presentation.sendError(context, f"Sorry {author.mention}, please specify a user in this guild.")
            return
        await presentation.deferIfSlash(context, ephemeral = True)
        isAdmin = context.guild is not None and await GBotFirebaseService.run(utils.isUserAdminOrOwner, author, context.guild)
        member = user or author
        if context.guild is not None:
            member = context.guild.get_member(member.id) or member
        card = WalletCard(self, context.guild, author, member, isAdmin)
        await card.send(context, True, embed = await card.render(), view = card)

    def walletFacts(self, userId, guild):
        # one step on the database worker: the balance, the history newest first and the rank here
        balance = gcoin_queries.getUserBalance(userId)
        history = sortedHistory(gcoin_queries.getUserTransactionHistory(userId))
        rank = None
        if guild is not None:
            balances = gcoin_queries.getAllUserBalances() or {}
            ranked = sorted((Decimal(balances[str(member.id)]['balance']) for member in guild.members if str(member.id) in balances and Decimal(balances[str(member.id)]['balance']) > 0), reverse = True)
            if balance > 0:
                place = sum(1 for other in ranked if other > balance)
                rank = f"{medal(place) + ' ' if place < 3 else ''}{presentation.ordinal(place + 1)} of {len(ranked)}"
            else:
                rank = 'Not ranked yet'
        return balance, history, rank

    def receiverProblem(self, author, member, guild):
        # what can be told before anything is typed
        if member.id == author.id:
            return 'You can not send GCoin to yourself.'
        if member.bot or guild.get_member(member.id) is None:
            return 'Please pick someone in this server.'
        return None

    def amountForm(self, member, onSubmit):
        return pagination.Form(f'Send to {member.display_name}', [
            pagination.Field('Amount of GCoin', placeholder = '5.00', maxLength = 20),
            pagination.Field('Note (optional)', placeholder = 'for the raid snacks', required = False, maxLength = MAX_NOTE_LENGTH)], onSubmit)

    async def checkSend(self, author, receiver, typed):
        # (a refusal, or None), the rounded amount and what the sender would have left
        try:
            amount = utils.roundDecimalPlaces(presentation.parseGCoin(typed), 2)
        except (InvalidOperation, ValueError):
            return 'Please enter a valid amount.', None, None
        sender = {'id': author.id, 'name': author.name}
        try:
            await GBotFirebaseService.run(gcoin_queries.validateTransaction, amount, sender, {'id': receiver.id, 'name': receiver.name}, True, True)
        except Exception as e:
            return self.transactionProblem(e), None, None
        balance = await GBotFirebaseService.run(gcoin_queries.getUserBalance, author.id)
        return None, amount, balance - amount

    def transactionProblem(self, error):
        if isinstance(error, EnforceRealUsersError):
            return 'Please specify a valid user.'
        if isinstance(error, EnforceSenderReceiverNotEqual):
            return 'You can not send GCoin to yourself.'
        if isinstance(error, EnforcePositiveTransactions):
            return 'You can not send a non-positive amount.'
        if isinstance(error, EnforceSenderFundsError):
            return 'You have insufficient funds.'
        raise error

    async def transfer(self, channel, author, receiver, amount, note):
        # moves the money, then says so in public, as the person receiving it has to be able to see it
        date = datetime.now().strftime(DATE_FORMAT)
        sender = {'id': author.id, 'name': author.name}
        try:
            await GBotFirebaseService.run(gcoin_queries.performTransaction, amount, date, sender, {'id': receiver.id, 'name': receiver.name}, 'sent', 'received', True, True)
        except (EnforceRealUsersError, EnforceSenderReceiverNotEqual, EnforcePositiveTransactions, EnforceSenderFundsError) as e:
            return self.transactionProblem(e)
        noteText = f'\n> {note}' if note else ''
        try:
            await channel.send(f'💸 {author.mention} sent {receiver.mention} **{presentation.formatGCoin(amount)} GCoin**.{noteText}')
        except nextcord.HTTPException as e:
            self.logger.error(f'GBot could not announce a GCoin transfer in channel {channel.id}: {e}')
        return None

    def serverRanking(self, guild):
        allUserBalances = gcoin_queries.getAllUserBalances() or {}
        balances = [(member.display_name, Decimal(allUserBalances[str(member.id)]['balance'])) for member in guild.members if str(member.id) in allUserBalances]
        ranked = sorted((entry for entry in balances if entry[1] > 0), key = lambda entry: entry[1], reverse = True)
        return [f'{medal(index)} **{name}** · `{presentation.formatGCoin(balance)} GCoin`' for index, (name, balance) in enumerate(ranked)]

    def everywhereRanking(self):
        # the public leaderboard's numbers, as the website shows them
        board = leaderboards_queries.getLeaderboard() or {}
        ranked = sorted((stats for stats in board.values() if Decimal(stats.get('balance', '0')) > 0), key = lambda stats: Decimal(stats['balance']), reverse = True)
        lines = []
        for index, stats in enumerate(ranked):
            wins = [f'{emoji} {stats[key]}' for key, emoji in (('numStormWins', '🌧️'), ('numWhoDisWins', '❓')) if int(stats.get(key, '0')) > 0]
            lines.append(f"{medal(index)} **{stats.get('username', 'Someone')}** · `{presentation.formatGCoin(stats['balance'])} GCoin`{' · ' + ' · '.join(wins) if wins else ''}")
        return lines

    async def openRanking(self, interaction):
        guild = interaction.guild
        sources = {}
        if guild is not None:
            lines = await GBotFirebaseService.run(self.serverRanking, guild)
            sources['server'] = pagination.DescriptionPageSource(lines, '🏆 Ranking · This server', presentation.BRAND_COLOR, guild.icon.url if guild.icon is not None else None, RANKING_PER_PAGE, empty = 'Nobody here has any GCoin yet.')
        lines = await GBotFirebaseService.run(self.everywhereRanking)
        sources['everywhere'] = pagination.DescriptionPageSource(lines, '🏆 Ranking · Everywhere', presentation.BRAND_COLOR, None, RANKING_PER_PAGE, empty = 'Nobody has any GCoin yet.')
        await pagination.startPages(interaction, RankingPages(sources), ephemeral = True)

    async def commonHistory(self, context, author, user):
        authorMention = author.mention
        await presentation.deferIfSlash(context, ephemeral = True)
        if user is not None and not await GBotFirebaseService.run(utils.isUserAdminOrOwner, author, context.guild):
            await presentation.sendError(context, f"Sorry {authorMention}, you need to be an admin to view other user's history.")
            return
        shown = user or author
        history = await GBotFirebaseService.run(gcoin_queries.getUserTransactionHistory, shown.id)
        if history is None:
            await presentation.sendError(context, f"Sorry {authorMention}, {f'{user.mention} has' if user else 'you have'} no transaction history.")
            return
        fields = []
        for i, transaction in enumerate(sortedHistory(history)[:self.NUM_TRX_HISTORY_TO_DISPLAY]):
            date = datetime.strptime(transaction['date'], DATE_FORMAT).strftime("%m/%d/%y %I:%M %p")
            direction = '📉' if transaction['gcoin'].startswith('-') else '📈'
            fields.append((f"{i + 1}. {transaction['other']} ({transaction['memo']})", f"{direction} `{presentation.formatGCoin(transaction['gcoin'])} GCoin`\n`{date}`"))
        pages = pagination.CustomButtonMenuPages(source = pagination.FieldPageSource(fields, avatarOf(shown), f"📜 {shown.name}'s Transaction History", presentation.BRAND_COLOR, False, 10))
        await pagination.startPages(context, pages, ephemeral = True)

def setup(client: commands.Bot):
    client.add_cog(GCoin(client))
