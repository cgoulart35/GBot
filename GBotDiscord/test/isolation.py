#region IMPORTS
from GBotDiscord.src import pagination
#endregion

# Some older suites replace parts of pagination (an __init__, or startPages) and never put them back.
# A suite that builds real lists calls restorePagination() in setUp, so it gets the real thing back
# whatever ran before it. The snapshot is taken at import, which both runners do before any test runs.
_FUNCTIONS = {name: getattr(pagination, name) for name in ('startPages', 'confirm')}
_INITS = {name: getattr(pagination, name).__init__ for name in ('ListPageSource', 'FieldPageSource', 'DescriptionPageSource', 'OwnedView', 'CustomButtonMenuPages', 'ListPicker', 'ConfirmView')}

def restorePagination():
    for name, function in _FUNCTIONS.items():
        setattr(pagination, name, function)
    for name, init in _INITS.items():
        getattr(pagination, name).__init__ = init
