#region IMPORTS
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, available_timezones
#endregion

# Reading "when" a reminder is for, in the person's own time zone, and moving a repeat on. Our own
# small parser rather than a library: it reads exactly the forms the form and the command show
# ("in 2 hours", "tomorrow 9am", "Thursday 8pm", "Dec 25 10:00"), and each of them is tested.

class WhenNotUnderstood(ValueError):
    pass

class WhenInThePast(ValueError):
    pass

# with a day but no time, a reminder is for the morning, and "tonight" for the evening
DEFAULT_TIME = time(9, 0)
TONIGHT_TIME = time(20, 0)

ONCE = 'once'
DAILY = 'daily'
WEEKLY = 'weekly'
REPEATS = (ONCE, DAILY, WEEKLY)

WEEKDAYS = {'monday': 0, 'mon': 0, 'tuesday': 1, 'tue': 1, 'tues': 1, 'wednesday': 2, 'wed': 2, 'thursday': 3, 'thu': 3, 'thur': 3, 'thurs': 3,
            'friday': 4, 'fri': 4, 'saturday': 5, 'sat': 5, 'sunday': 6, 'sun': 6}
WEEKDAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MONTHS = {'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3, 'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'jun': 6,
          'july': 7, 'jul': 7, 'august': 8, 'aug': 8, 'september': 9, 'sep': 9, 'sept': 9, 'october': 10, 'oct': 10,
          'november': 11, 'nov': 11, 'december': 12, 'dec': 12}
UNITS = {'minute': timedelta(minutes = 1), 'hour': timedelta(hours = 1), 'day': timedelta(days = 1), 'week': timedelta(weeks = 1)}
UNIT_WORDS = {'m': 'minute', 'min': 'minute', 'mins': 'minute', 'minute': 'minute', 'minutes': 'minute',
              'h': 'hour', 'hr': 'hour', 'hrs': 'hour', 'hour': 'hour', 'hours': 'hour',
              'd': 'day', 'day': 'day', 'days': 'day', 'w': 'week', 'wk': 'week', 'wks': 'week', 'week': 'week', 'weeks': 'week'}

DAY_WORD = re.compile(r'(today|tonight|tomorrow|tmrw|tmr)(?:\s+(?:at\s+)?(.+))?')
WEEKDAY = re.compile(r'(?:next\s+|this\s+)?([a-z]+)(?:\s+(?:at\s+)?(.+))?')
MONTH_FIRST = re.compile(r'([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?(?:,?\s+(?:at\s+)?(.+))?')
DAY_FIRST = re.compile(r'(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)(?:,?\s+(\d{4}))?(?:,?\s+(?:at\s+)?(.+))?')
ISO_DATE = re.compile(r'(\d{4})-(\d{1,2})-(\d{1,2})(?:[\st]+(?:at\s+)?(.+))?')
SLASH_DATE = re.compile(r'(\d{1,2})/(\d{1,2})(?:/(\d{2}|\d{4}))?(?:\s+(?:at\s+)?(.+))?')
CLOCK = re.compile(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.?|p\.m\.?|a|p)?')
DURATION_PART = re.compile(r'(\d+|an?|one)\s*([a-z]+)')

def parseTime(text):
    # "9am", "9:30 pm", "21:00", "noon", "midnight"
    if text in ('noon', 'midday'):
        return time(12, 0)
    if text == 'midnight':
        return time(0, 0)
    match = CLOCK.fullmatch(text)
    if match is None:
        raise WhenNotUnderstood(text)
    hour, minute, meridiem = int(match.group(1)), int(match.group(2) or 0), match.group(3)
    if minute > 59:
        raise WhenNotUnderstood(text)
    if meridiem:
        if not 1 <= hour <= 12:
            raise WhenNotUnderstood(text)
        hour = hour % 12 + (12 if meridiem.startswith('p') else 0)
    elif hour > 23:
        raise WhenNotUnderstood(text)
    return time(hour, minute)

def parseDuration(text):
    # "2 hours", "an hour", "1h30m", "1 hour and 30 minutes"
    remaining = re.sub(r'\s*(,|and)\s*', ' ', text).strip()
    total = timedelta()
    position = 0
    for match in DURATION_PART.finditer(remaining):
        if remaining[position:match.start()].strip():
            raise WhenNotUnderstood(text)
        unit = UNIT_WORDS.get(match.group(2))
        if unit is None:
            raise WhenNotUnderstood(text)
        count = 1 if match.group(1) in ('a', 'an', 'one') else int(match.group(1))
        total += UNITS[unit] * count
        position = match.end()
    if position == 0 or remaining[position:].strip() or total <= timedelta():
        raise WhenNotUnderstood(text)
    return total

def at(day: date, clock: time, zone):
    return datetime.combine(day, clock, tzinfo = zone)

def withTime(rest, default):
    return parseTime(rest) if rest else default

def onDate(year, month, day, rest, now, yearGiven):
    try:
        moment = at(date(year, month, day), withTime(rest, DEFAULT_TIME), now.tzinfo)
    except ValueError:
        raise WhenNotUnderstood(f'{month}/{day}')
    # "Dec 25" in late December means next year's
    if moment <= now and not yearGiven:
        moment = moment.replace(year = year + 1)
    return moment

def parseWhen(text, now: datetime):
    # When text means, after now, in now's time zone. Raises WhenNotUnderstood for anything it can't
    # read, and WhenInThePast for a time that has gone.
    words = re.sub(r'\s+', ' ', (text or '').lower()).strip().rstrip('.')
    words = re.sub(r'^(at|on)\s+', '', words)
    if not words:
        raise WhenNotUnderstood(text)
    moment = None
    if words.startswith('in '):
        moment = now + parseDuration(words[3:])
    elif match := DAY_WORD.fullmatch(words):
        word, rest = match.groups()
        day = now.date() + timedelta(days = 1 if word.startswith('t') and word not in ('today', 'tonight') else 0)
        clock = withTime(rest, TONIGHT_TIME if word == 'tonight' else DEFAULT_TIME)
        # "tonight at 9" is 9 in the evening
        if word == 'tonight' and clock.hour < 12 and rest and not re.search(r'[ap]', rest):
            clock = clock.replace(hour = clock.hour + 12)
        moment = at(day, clock, now.tzinfo)
    elif (match := WEEKDAY.fullmatch(words)) and match.group(1) in WEEKDAYS:
        ahead = (WEEKDAYS[match.group(1)] - now.weekday()) % 7
        clock = withTime(match.group(2), DEFAULT_TIME)
        moment = at(now.date() + timedelta(days = ahead), clock, now.tzinfo)
        if moment <= now:
            moment = at(now.date() + timedelta(days = ahead + 7), clock, now.tzinfo)
    elif (match := MONTH_FIRST.fullmatch(words)) and match.group(1) in MONTHS:
        month, day, year, rest = match.groups()
        moment = onDate(int(year or now.year), MONTHS[month], int(day), rest, now, year is not None)
    elif (match := DAY_FIRST.fullmatch(words)) and match.group(2) in MONTHS:
        day, month, year, rest = match.groups()
        moment = onDate(int(year or now.year), MONTHS[month], int(day), rest, now, year is not None)
    elif match := ISO_DATE.fullmatch(words):
        year, month, day, rest = match.groups()
        moment = onDate(int(year), int(month), int(day), rest, now, True)
    elif match := SLASH_DATE.fullmatch(words):
        # month first, as Discord's own dates are for most of its people
        month, day, year, rest = match.groups()
        fullYear = None if year is None else int(year) + (2000 if len(year) == 2 else 0)
        moment = onDate(fullYear or now.year, int(month), int(day), rest, now, year is not None)
    else:
        clock = parseTime(words)
        moment = at(now.date(), clock, now.tzinfo)
        if moment <= now:
            moment = at(now.date() + timedelta(days = 1), clock, now.tzinfo)
    if moment <= now:
        raise WhenInThePast(text)
    return moment

def advance(moment: datetime, repeat, zone):
    # the next time a repeat is due: the same clock time a day or a week on, so summer time keeps 9am at 9am
    local = moment.astimezone(zone)
    return at(local.date() + timedelta(days = 7 if repeat == WEEKLY else 1), local.time(), zone)

def nextAfter(moment: datetime, repeat, zone, now: datetime):
    # past now, however many were missed, so a repeat that came due while GBot was down sends once
    while moment <= now:
        moment = advance(moment, repeat, zone)
    return moment

def moveToZone(moment: datetime, oldZone, newZone):
    # the same clock time in the new zone: someone who moves still means their own 9am
    local = moment.astimezone(oldZone)
    return at(local.date(), local.time(), newZone)

def describeRepeat(moment: datetime, repeat, zone):
    local = moment.astimezone(zone)
    clock = formatClock(local)
    if repeat == DAILY:
        return f'Every day at {clock}'
    if repeat == WEEKLY:
        return f'Every {WEEKDAY_NAMES[local.weekday()]} at {clock}'
    return 'Once'

def formatClock(local: datetime):
    return local.strftime('%I:%M %p').lstrip('0')

def formatMoment(moment: datetime, zone):
    # for where Discord's own timestamps don't show, like a dropdown: "Tue, Nov 10 at 9:00 AM"
    local = moment.astimezone(zone)
    return f"{local.strftime('%a, %b')} {local.day} at {formatClock(local)}"

# Time zones offered in the picker, each shown with its time now so people match their own clock.
# Any other IANA name can be typed in.
ZONES = [
    ('Pacific/Honolulu', 'Hawaii', 'Honolulu'),
    ('America/Anchorage', 'Alaska', 'Anchorage'),
    ('America/Los_Angeles', 'Pacific Time', 'Los Angeles, Vancouver, Seattle'),
    ('America/Phoenix', 'Arizona', 'Phoenix'),
    ('America/Denver', 'Mountain Time', 'Denver, Calgary'),
    ('America/Chicago', 'Central Time', 'Chicago, Dallas, Mexico City'),
    ('America/New_York', 'Eastern Time', 'New York, Toronto, Miami'),
    ('America/Halifax', 'Atlantic Time', 'Halifax, Puerto Rico'),
    ('America/Sao_Paulo', 'Brazil', 'São Paulo, Rio de Janeiro'),
    ('UTC', 'UTC', 'Coordinated Universal Time'),
    ('Europe/London', 'UK and Ireland', 'London, Dublin, Lisbon'),
    ('Europe/Paris', 'Central Europe', 'Paris, Berlin, Madrid, Rome'),
    ('Europe/Athens', 'Eastern Europe', 'Athens, Helsinki, Kyiv'),
    ('Africa/Johannesburg', 'South Africa', 'Johannesburg, Cape Town'),
    ('Asia/Dubai', 'Gulf', 'Dubai, Abu Dhabi'),
    ('Asia/Kolkata', 'India', 'Mumbai, Delhi, Bengaluru'),
    ('Asia/Singapore', 'Singapore', 'Singapore, Manila, Kuala Lumpur'),
    ('Asia/Shanghai', 'China', 'Shanghai, Beijing, Hong Kong'),
    ('Asia/Tokyo', 'Japan and Korea', 'Tokyo, Seoul'),
    ('Australia/Sydney', 'Eastern Australia', 'Sydney, Melbourne'),
    ('Pacific/Auckland', 'New Zealand', 'Auckland, Wellington'),
]

def zoneLabel(name):
    return next((label for zone, label, _ in ZONES if zone == name), name)

def zoneNamed(text):
    # an IANA name, matched without caring about case, or None
    wanted = (text or '').strip().replace(' ', '_').lower()
    return next((ZoneInfo(name) for name in available_timezones() if name.lower() == wanted), None)
