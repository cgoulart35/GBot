#region IMPORTS
from GBotDiscord.src.presentation import ERROR_COLOR
#endregion

def assertErrorCard(sendMock, description):
    """Asserts that a send mock received a red error card with this exact text."""
    sent = []
    for call in sendMock.call_args_list:
        embed = call.kwargs.get('embed')
        if embed is not None:
            sent.append(embed.description)
            if embed.description == description and embed.color == ERROR_COLOR:
                return
    raise AssertionError(f'No error card with {description!r}. Cards sent: {sent}. All calls: {sendMock.call_args_list}')

def assertCard(sendMock, title, description):
    """Asserts that a send mock received a card with this title and text."""
    for call in sendMock.call_args_list:
        embed = call.kwargs.get('embed')
        if embed is not None and embed.title == title and embed.description == description:
            return
    raise AssertionError(f'No card {title!r} / {description!r}. All calls: {sendMock.call_args_list}')
