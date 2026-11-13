#region IMPORTS
from GBotDiscord.src import pagination
#endregion

# Many trades made in one go, and what is said of them. Kept out of gtrade_cog: the bot loads each cog
# module as its own copy (load_extension), so a class from it made by another importer, as the agent
# is, would fail the cog's isinstance check and every trade would post on its own. From here there is
# one Gathered for both.

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
