import json
from enum import Enum
from decimal import Decimal

class HaloInfiniteCompetitionVariables(Enum):
    KILLS =                 'Kills'
    MELEE_KILLS =           'Melee Kills'
    GRENADE_KILLS =         'Grenade Kills'
    HEADSHOT_KILLS =        'Headshot Kills'
    POWER_WEAPON_KILLS =    'Power Weapon Kills'
    ASSISTS =               'Assists'
    EMP_ASSISTS =           'Emp Assists'
    DRIVER_ASSISTS =        'Driver Assists'
    CALLOUT_ASSISTS =       'Callout Assists'
    VEHICLES_DESTROYED =    'Vehicles Destroyed'
    VEHICLES_HIJACKED =     'Vehicles Hijacked'
    MATCHES_WON =           'Matches Won'
    MATCHES_PLAYED =        'Matches Played'
    TIME_PLAYED =           'Time Played'
    TOTAL_SCORE =           'Total Score'
    MEDALS =                'Medals'
    SHOTS_LANDED =          'Shots Landed'
    SHOTS_FIRED =           'Shots Fired'
    SHOT_ACCURACY =         'Shot Accuracy (%)'
    WIN_RATE =              'Win Rate (%)'
    KDA_RATIO =             'KDA Ratio'
    KD_RATIO =              'KD Ratio'

class HaloInfiniteAdditionalModel():

    def __init__(self, gamertag: str, filter: str):
        self.gamertag = gamertag
        self.filter = filter

    def createObjectFromDatabaseOrAPI(dictionary):
        gamertag = dictionary['gamertag']
        filter = dictionary['filter']
        return HaloInfiniteAdditionalModel(gamertag, filter)

class HaloInfiniteTimePlayedModel():

    def __init__(self, seconds: int, human: str):
        self.seconds = seconds
        self.human = human

    def createObjectFromDatabaseOrAPI(dictionary):
        seconds = dictionary['seconds']
        human = dictionary['human']
        return HaloInfiniteTimePlayedModel(seconds, human)

class HaloInfiniteImageUrlsModel():

    def __init__(self, small: str, medium: str, large: str):
        self.small = small
        self.medium = medium
        self.large = large

    def createObjectFromDatabaseOrAPI(dictionary):
        small = dictionary['small']
        medium = dictionary['medium']
        large = dictionary['large']
        return HaloInfiniteImageUrlsModel(small, medium, large)

class HaloInfiniteMedalModel():

    def __init__(self, id: int, name: str, count: int, image_urls: HaloInfiniteImageUrlsModel):
        self.id = id
        self.name = name
        self.count = count
        self.image_urls = image_urls

    def createObjectFromDatabaseOrAPI(dictionary):
        id = dictionary['id']
        name = dictionary['name']
        count = dictionary['count']
        image_urls = HaloInfiniteImageUrlsModel.createObjectFromDatabaseOrAPI(dictionary['image_urls'])
        return HaloInfiniteMedalModel(id, name, count, image_urls)

class HaloInfiniteMedalsModel():

    def __init__(self, medals: list[HaloInfiniteMedalModel]):
        self.medals = medals

    def createObjectFromDatabaseOrAPI(medals_data):
        # if type is dict from database (already a list if from API)
        if type(medals_data) is dict:
            medals_data = medals_data['medals']

        medals: list[HaloInfiniteMedalModel] = []
        for medal in medals_data:
            medals.append(HaloInfiniteMedalModel.createObjectFromDatabaseOrAPI(medal))
        return HaloInfiniteMedalsModel(medals)


class HaloInfiniteMatchesModel():

    def __init__(self, wins: int, losses: int, left: int, draws: int):
        self.wins = wins
        self.losses = losses
        self.left = left
        self.draws = draws

    def createObjectFromDatabaseOrAPI(dictionary):
        wins = dictionary['wins']
        losses = dictionary['losses']
        left = dictionary['left']
        draws = dictionary['draws']
        return HaloInfiniteMatchesModel(wins, losses, left, draws)

class HaloInfiniteAssistsModel():

    def __init__(self, emp: int, driver: int, callouts: int):
        self.emp = emp
        self.driver = driver
        self.callouts = callouts

    def createObjectFromDatabaseOrAPI(dictionary):
        emp = dictionary['emp']
        driver = dictionary['driver']
        callouts = dictionary['callouts']
        return HaloInfiniteAssistsModel(emp, driver, callouts)

class HaloInfiniteKillsModel():

    def __init__(self, melee: int, grenades: int, headshots: int, power_weapons: int):
        self.melee = melee
        self.grenades = grenades
        self.headshots = headshots
        self.power_weapons = power_weapons

    def createObjectFromDatabaseOrAPI(dictionary):
        melee = dictionary['melee']
        grenades = dictionary['grenades']
        headshots = dictionary['headshots']
        power_weapons = dictionary['power_weapons']
        return HaloInfiniteKillsModel(melee, grenades, headshots, power_weapons)

class HaloInfiniteBreakdownsModel():

    def __init__(self, kills: HaloInfiniteKillsModel, assists: HaloInfiniteAssistsModel, matches: HaloInfiniteMatchesModel, medals: HaloInfiniteMedalsModel):
        self.kills = kills
        self.assists = assists
        self.matches = matches
        self.medals = medals

    def createObjectFromDatabaseOrAPI(dictionary):
        kills = HaloInfiniteKillsModel.createObjectFromDatabaseOrAPI(dictionary['kills'])
        assists = HaloInfiniteAssistsModel.createObjectFromDatabaseOrAPI(dictionary['assists'])
        matches = HaloInfiniteMatchesModel.createObjectFromDatabaseOrAPI(dictionary['matches'])
        medals = HaloInfiniteMedalsModel.createObjectFromDatabaseOrAPI(dictionary['medals'])
        return HaloInfiniteBreakdownsModel(kills, assists, matches, medals)

class HaloInfiniteShotsModel():

    def __init__(self, fired: int, landed: int, missed: int, accuracy):
        self.fired = fired
        self.landed = landed
        self.missed = missed
        self.accuracy = accuracy

    def createObjectFromDatabaseOrAPI(dictionary):
        fired = dictionary['fired']
        landed = dictionary['landed']
        missed = dictionary['missed']
        accuracy = Decimal(str(dictionary['accuracy']))
        return HaloInfiniteShotsModel(fired, landed, missed, accuracy)

    def convertDecimalsToStrings(self):
        self.accuracy = str(self.accuracy)
        return self

class HaloInfiniteDamageModel():

    def __init__(self, taken: int, dealt: int, average: int):
        self.taken = taken
        self.dealt = dealt
        self.average = average

    def createObjectFromDatabaseOrAPI(dictionary):
        taken = dictionary['taken']
        dealt = dictionary['dealt']
        average = dictionary['average']
        return HaloInfiniteDamageModel(taken, dealt, average)

class HaloInfiniteVehiclesModel():

    def __init__(self, destroys: int, hijacks: int):
        self.destroys = destroys
        self.hijacks = hijacks

    def createObjectFromDatabaseOrAPI(dictionary):
        destroys = dictionary['destroys']
        hijacks = dictionary['hijacks']
        return HaloInfiniteVehiclesModel(destroys, hijacks)

class HaloInfiniteSummaryModel():

    def __init__(self, kills: int, deaths: int, assists: int, betrayals: int, suicides: int, vehicles: HaloInfiniteVehiclesModel, medals: int):
        self.kills = kills
        self.deaths = deaths
        self.assists = assists
        self.betrayals = betrayals
        self.suicides = suicides
        self.vehicles = vehicles
        self.medals = medals

    def createObjectFromDatabaseOrAPI(dictionary):
        kills = dictionary['kills']
        deaths = dictionary['deaths']
        assists = dictionary['assists']
        betrayals = dictionary['betrayals']
        suicides = dictionary['suicides']
        vehicles = HaloInfiniteVehiclesModel.createObjectFromDatabaseOrAPI(dictionary['vehicles'])
        medals = dictionary['medals']
        return HaloInfiniteSummaryModel(kills, deaths, assists, betrayals, suicides, vehicles, medals)

class HaloInfiniteCoreModel():

    def __init__(self, summary: HaloInfiniteSummaryModel, damage: HaloInfiniteDamageModel, shots: HaloInfiniteShotsModel, breakdowns: HaloInfiniteBreakdownsModel, kda, kdr, total_score: int):
        self.summary = summary
        self.damage = damage
        self.shots = shots
        self.breakdowns = breakdowns
        self.kda = kda
        self.kdr = kdr
        self.total_score = total_score

    def createObjectFromDatabaseOrAPI(dictionary):
        summary = HaloInfiniteSummaryModel.createObjectFromDatabaseOrAPI(dictionary['summary'])
        damage = HaloInfiniteDamageModel.createObjectFromDatabaseOrAPI(dictionary['damage'])
        shots = HaloInfiniteShotsModel.createObjectFromDatabaseOrAPI(dictionary['shots'])
        breakdowns = HaloInfiniteBreakdownsModel.createObjectFromDatabaseOrAPI(dictionary['breakdowns'])
        kda = Decimal(str(dictionary['kda']))
        kdr = Decimal(str(dictionary['kdr']))
        total_score = dictionary['total_score']
        return HaloInfiniteCoreModel(summary, damage, shots, breakdowns, kda, kdr, total_score)

    def convertDecimalsToStrings(self):
        self.shots.convertDecimalsToStrings()
        self.kda = str(self.kda)
        self.kdr = str(self.kdr)
        return self

class HaloInfiniteDataModel():

    def __init__(self, core: HaloInfiniteCoreModel, matches_played: int, time_played: HaloInfiniteTimePlayedModel, win_rate):
        self.core = core
        self.matches_played = matches_played
        self.time_played = time_played
        self.win_rate = win_rate

    def createObjectFromDatabaseOrAPI(dictionary):
        core = HaloInfiniteCoreModel.createObjectFromDatabaseOrAPI(dictionary['core'])
        matches_played = dictionary['matches_played']
        time_played = HaloInfiniteTimePlayedModel.createObjectFromDatabaseOrAPI(dictionary['time_played'])
        win_rate = Decimal(str(dictionary['win_rate']))
        return HaloInfiniteDataModel(core, matches_played, time_played, win_rate)

    def convertDecimalsToStrings(self):
        self.core.convertDecimalsToStrings()
        self.win_rate = str(self.win_rate)
        return self

class HaloInfiniteParticipantModel():

    def __init__(self, data: HaloInfiniteDataModel, additional: HaloInfiniteAdditionalModel, wins: int):
        self.data = data
        self.additional = additional
        self.wins = wins

    def createObjectFromDatabaseOrAPI(dictionary):
        data = HaloInfiniteDataModel.createObjectFromDatabaseOrAPI(dictionary['data'])
        additional = HaloInfiniteAdditionalModel.createObjectFromDatabaseOrAPI(dictionary['additional'])
        wins = dictionary['wins']
        return HaloInfiniteParticipantModel(data, additional, wins)

    def convertDecimalsToStrings(self):
        self.data.convertDecimalsToStrings()
        return self

class HaloInfiniteWeeklyCompetitionModel():

    def __init__(self, competition_variable: str, participants: dict[HaloInfiniteParticipantModel], start_day: str):
        self.competition_variable = competition_variable
        self.participants = participants
        self.start_day = start_day

    # convert all decimal values as floats (from API) or as strings (from database) to Decimals
    def createObjectFromDatabaseOrAPI(dictionary: dict):
        competition_variable = dictionary['competition_variable']
        start_day = dictionary['start_day']
        participants: dict[HaloInfiniteParticipantModel] = {}
        for participantId, participantValues in dictionary['participants'].items():
            participants[participantId] = HaloInfiniteParticipantModel.createObjectFromDatabaseOrAPI(participantValues)
        return HaloInfiniteWeeklyCompetitionModel(competition_variable, participants, start_day)

    # convert all Decimals to strings to save to database
    def convertDecimalsToStrings(self):
        for participant in self.participants.values():
            participant: HaloInfiniteParticipantModel
            participant.convertDecimalsToStrings()
        return self

    # creates a serializable object for firebase
    def firebaseFormat(self):
        serializedString = json.dumps(self, default = lambda o: o.__dict__, sort_keys = True, indent = 2)
        dictionaryObject = json.loads(serializedString)
        return dictionaryObject
