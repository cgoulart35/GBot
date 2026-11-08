#region IMPORTS
from GBotDiscord.src.firebase import GBotFirebaseService
#endregion

# tables:
    # servers
        # serverId
            # version
            # prefix
            # toggle_music
            # toggle_gcoin
            # toggle_gtrade
            # toggle_hype
            # toggle_storms
            # toggle_legacy_prefix_commands
            # toggle_who_dis
            # role_admin (optional)
            # role_who_dis (optional)
            # channel_admin (optional)
            # channel_storms (optional)
    # reports
        # serverId
            # reportId
                # targetId, reporterId: who was reported, and by whom
                # where: where it happened, as people read it ("#general", "a Who Dis game")
                # when: an ISO time, in UTC
                # what: what happened, in the reporter's words, or ''
                # outcome (optional): handled or dismissed
                # outcomeBy (optional): the admin who set it
            # The reported messages stay on the admin channel's card, not here, so GBot keeps
            # as little of what people wrote as it can.

def getAllServers():
    result = GBotFirebaseService.get(["servers"])
    return result.val()

# add new database fields here that have default values
def upgradeServerValues(serverId, currentBotVerion):
    serverConfig = getAllServerValues(serverId)
    setServerValue(serverId, 'version', currentBotVerion)

    # added music in GBot 2.0
    if 'toggle_music' not in serverConfig or serverConfig['toggle_music'] == None:
        setServerValue(serverId, 'toggle_music', False)

    # added gcoin and gtrade in GBot 3.0
    if 'toggle_gcoin' not in serverConfig or serverConfig['toggle_gcoin'] == None:
        setServerValue(serverId, 'toggle_gcoin', False)
    if 'toggle_gtrade' not in serverConfig or serverConfig['toggle_gtrade'] == None:
        setServerValue(serverId, 'toggle_gtrade', False)

    # added hype in GBot 4.0
    if 'toggle_hype' not in serverConfig or serverConfig['toggle_hype'] == None:
        setServerValue(serverId, 'toggle_hype', False)

    # added storms in GBot 5.0
    if 'toggle_storms' not in serverConfig or serverConfig['toggle_storms'] == None:
        setServerValue(serverId, 'toggle_storms', False)

    # added legacy_prefix_commands in GBot 6.0
    if 'toggle_legacy_prefix_commands' not in serverConfig or serverConfig['toggle_legacy_prefix_commands'] == None:
        setServerValue(serverId, 'toggle_legacy_prefix_commands', False)

    # added who dis in GBot 7.0
    if 'toggle_who_dis' not in serverConfig or serverConfig['toggle_who_dis'] == None:
        setServerValue(serverId, 'toggle_who_dis', False)

    # added the agent in GBot 8.1
    if 'toggle_agent' not in serverConfig or serverConfig['toggle_agent'] == None:
        setServerValue(serverId, 'toggle_agent', False)

def initServerValues(serverId, currentBotVerion):
    defaultConfig = {
        'version': currentBotVerion,
        'prefix': '.',
        # DISCONTINUED 'toggle_halo': False,
        'toggle_music': False,
        'toggle_gcoin': False,
        'toggle_gtrade': False,
        'toggle_hype': False,
        'toggle_storms': False,
        'toggle_legacy_prefix_commands': False,
        'toggle_who_dis': False,
        'toggle_agent': False
    }
    GBotFirebaseService.set(["servers", serverId], defaultConfig)

def clearServerValues(serverId):
    GBotFirebaseService.remove(["servers", serverId])
    GBotFirebaseService.remove(["reports", serverId])

def getAllServerValues(serverId):
    result = GBotFirebaseService.get(["servers", serverId])
    return result.val()

def getServerValue(serverId, item):
    result = GBotFirebaseService.get(["servers", serverId, item])
    return result.val()

def setServerValue(serverId, item, value):
    GBotFirebaseService.set(["servers", serverId, item], value)
def addReport(serverId, report):
    return GBotFirebaseService.push(["reports", serverId], report)

def setReportOutcome(serverId, reportId, outcome, outcomeBy):
    # a report deleted with its server's data, or from the database by hand, isn't brought back
    if GBotFirebaseService.get(["reports", serverId, reportId]).val() is None:
        return False
    GBotFirebaseService.update(["reports", serverId, reportId], {'outcome': outcome, 'outcomeBy': outcomeBy})
    return True

def getReportsOn(serverId, targetId):
    # newest first
    reports = GBotFirebaseService.get(["reports", serverId]).val() or {}
    return sorted((report for report in reports.values() if report.get('targetId') == str(targetId)), key = lambda report: report['when'], reverse = True)
