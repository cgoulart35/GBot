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

class WhenTooFar(ValueError):
    pass


class ReminderProblem(Exception):
    # a reminder that can't be set, with what to tell the person (raised by reminders_cog)
    pass

# past the furthest a reminder can be (10 years), and far short of the last date a datetime can hold:
# each count is held to it before it's multiplied, so a huge one can't overflow, and so is their sum
MAX_TOTAL = timedelta(days = 3800)

# with a day but no time, a reminder is for the morning, and "tonight" for the evening
DEFAULT_TIME = time(9, 0)
TONIGHT_TIME = time(20, 0)

# How a reminder repeats. Stored as written here, with what a repeat needs to stay put after it: a
# month's or a year's own date ("monthly:31", "yearly:2-29"), so a short month doesn't move it for
# good, and the chosen weekdays ("days:0,2,4", Monday being 0).
ONCE = 'once'
DAILY = 'daily'
WEEKDAYS_ONLY = 'weekdays'
WEEKLY = 'weekly'
MONTHLY = 'monthly'
YEARLY = 'yearly'
DAYS = 'days'
# what can be picked, each made exact from the reminder's first time by makeRepeat
REPEATS = (ONCE, DAILY, WEEKDAYS_ONLY, WEEKLY, MONTHLY, YEARLY, DAYS)
WORK_DAYS = (0, 1, 2, 3, 4)

WEEKDAYS = {'monday': 0, 'mon': 0, 'tuesday': 1, 'tue': 1, 'tues': 1, 'wednesday': 2, 'wed': 2, 'thursday': 3, 'thu': 3, 'thur': 3, 'thurs': 3,
            'friday': 4, 'fri': 4, 'saturday': 5, 'sat': 5, 'sunday': 6, 'sun': 6}
REPEAT_WORDS = {'once': ONCE, 'none': ONCE, 'no': ONCE, 'daily': DAILY, 'day': DAILY, 'everyday': DAILY,
                'weekdays': WEEKDAYS_ONLY, 'weekday': WEEKDAYS_ONLY, 'weekly': WEEKLY, 'week': WEEKLY,
                'monthly': MONTHLY, 'month': MONTHLY, 'yearly': YEARLY, 'year': YEARLY, 'annually': YEARLY}
WEEKDAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MONTHS = {'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3, 'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'jun': 6,
          'july': 7, 'jul': 7, 'august': 8, 'aug': 8, 'september': 9, 'sep': 9, 'sept': 9, 'october': 10, 'oct': 10,
          'november': 11, 'nov': 11, 'december': 12, 'dec': 12}
UNITS = {'second': timedelta(seconds = 1), 'minute': timedelta(minutes = 1), 'hour': timedelta(hours = 1), 'day': timedelta(days = 1), 'week': timedelta(weeks = 1)}
# months and years are the calendar's: "in a month" on Jan 31 is Feb 28, at the same time of day
MONTH_UNITS = {'month': 1, 'year': 12}
UNIT_WORDS = {'s': 'second', 'sec': 'second', 'secs': 'second', 'second': 'second', 'seconds': 'second',
              'm': 'minute', 'min': 'minute', 'mins': 'minute', 'minute': 'minute', 'minutes': 'minute',
              'h': 'hour', 'hr': 'hour', 'hrs': 'hour', 'hour': 'hour', 'hours': 'hour',
              'd': 'day', 'day': 'day', 'days': 'day', 'w': 'week', 'wk': 'week', 'wks': 'week', 'week': 'week', 'weeks': 'week',
              'mo': 'month', 'mos': 'month', 'month': 'month', 'months': 'month', 'y': 'year', 'yr': 'year', 'yrs': 'year', 'year': 'year', 'years': 'year'}

NEXT_PERIOD = re.compile(r'next (week|month|year)(?:\s+(?:at\s+)?(.+))?')
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

def addMonths(moment: datetime, months):
    # the same day and clock time that many months on, or the month's last day if it's shorter
    month = moment.month - 1 + months
    year, month = moment.year + month // 12, month % 12 + 1
    day = monthDay(year, month, moment.day)
    return moment.replace(year = year, month = month, day = day.day)

def parseDuration(text):
    # "2 hours", "an hour", "1h30m", "1 hour and 30 minutes", "a year": the months, and the rest
    remaining = re.sub(r'\s*(,|and)\s*', ' ', text).strip()
    total = timedelta()
    months = 0
    position = 0
    for match in DURATION_PART.finditer(remaining):
        if remaining[position:match.start()].strip():
            raise WhenNotUnderstood(text)
        unit = UNIT_WORDS.get(match.group(2))
        if unit is None:
            raise WhenNotUnderstood(text)
        count = 1 if match.group(1) in ('a', 'an', 'one') else int(match.group(1))
        size = timedelta(days = 31 * MONTH_UNITS[unit]) if unit in MONTH_UNITS else UNITS[unit]
        if count > MAX_TOTAL // size:
            raise WhenTooFar(text)
        if unit in MONTH_UNITS:
            months += MONTH_UNITS[unit] * count
        else:
            total += UNITS[unit] * count
        if total + timedelta(days = 31 * months) > MAX_TOTAL:
            raise WhenTooFar(text)
        position = match.end()
    if position == 0 or remaining[position:].strip() or (total <= timedelta() and months == 0):
        raise WhenNotUnderstood(text)
    return months, total

def gone(moment: datetime, now: datetime):
    # A named time falls on its minute, so the minute it's in hasn't gone yet: "at 10:32pm" said
    # at 10:32:40 means now, not tomorrow. A timer is always ahead, so this never holds for one.
    return moment < now.replace(second = 0, microsecond = 0)

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
    if gone(moment, now) and not yearGiven:
        moment = moment.replace(year = year + 1)
    return moment

def parseWhen(text, now: datetime):
    return readWhen(text, now)[0]

def readWhen(text, now: datetime):
    # When text means, after now, in now's time zone, and whether it's a timer: "in 90 seconds" and
    # "next month" count from now to the second, and every time that's named falls on its minute.
    # Raises WhenNotUnderstood for anything it can't read, and WhenInThePast for a time that has gone.
    words = re.sub(r'\s+', ' ', (text or '').lower()).strip().rstrip('.')
    words = re.sub(r'^(at|on)\s+', '', words)
    if not words:
        raise WhenNotUnderstood(text)
    moment = None
    timer = False
    if words.startswith('in '):
        months, rest = parseDuration(words[3:])
        moment = addMonths(now, months) + rest
        timer = True
    elif match := NEXT_PERIOD.fullmatch(words):
        # "next month" is a month from now, and "next year at 9am" that day at 9am
        period, rest = match.groups()
        later = now + UNITS['week'] if period == 'week' else addMonths(now, MONTH_UNITS[period])
        moment = at(later.date(), parseTime(rest), now.tzinfo) if rest else later
        timer = not rest
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
        if gone(moment, now):
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
        if gone(moment, now):
            moment = at(now.date() + timedelta(days = 1), clock, now.tzinfo)
    if gone(moment, now):
        raise WhenInThePast(text)
    return moment, timer

class RepeatNotUnderstood(ValueError):
    pass

def kindOf(repeat):
    return (repeat or ONCE).split(':')[0]

def daysOf(repeat):
    # the weekdays a repeat goes off on, or None for one that isn't by weekday
    kind = kindOf(repeat)
    if kind == WEEKDAYS_ONLY:
        return WORK_DAYS
    if kind == DAYS:
        return tuple(int(day) for day in repeat.split(':')[1].split(','))
    return None

def makeRepeat(kind, moment: datetime, zone, days = None):
    # A repeat made exact from the reminder's first time: a month's date, a year's day, or the
    # weekdays picked. Raises RepeatNotUnderstood for anything else.
    local = moment.astimezone(zone)
    if kind in (ONCE, DAILY, WEEKDAYS_ONLY, WEEKLY):
        return kind
    if kind == MONTHLY:
        return f'{MONTHLY}:{local.day}'
    if kind == YEARLY:
        return f'{YEARLY}:{local.month}-{local.day}'
    if kind == DAYS:
        picked = sorted(set(days or ()))
        if not picked or not all(isinstance(day, int) and 0 <= day <= 6 for day in picked):
            raise RepeatNotUnderstood(days)
        return f'{DAYS}:{",".join(str(day) for day in picked)}'
    raise RepeatNotUnderstood(kind)

def readRepeat(text):
    # a repeat as typed: "weekly", "weekdays", "monthly", or days like "mon,wed,fri". Returns (kind,
    # days), or None.
    words = [word for word in re.split(r'[\s,/&+]+|\band\b', (text or '').lower().strip()) if word]
    if len(words) == 1 and words[0] in REPEAT_WORDS:
        return REPEAT_WORDS[words[0]], None
    if words and all(word in WEEKDAYS for word in words):
        return DAYS, sorted({WEEKDAYS[word] for word in words})
    return None

def onOrAfter(moment: datetime, repeat, zone):
    # the first time a repeat by weekday goes off: its own time, or the next chosen day at that time.
    # Only for a time that was named: a timer goes off when it said, and the repeat follows.
    days = daysOf(repeat)
    local = moment.astimezone(zone)
    if days is None or local.weekday() in days:
        return moment
    return advance(moment, repeat, zone)

def monthDay(year, month, day):
    # that day of the month, or its last day if it's shorter
    last = (date(year + month // 12, month % 12 + 1, 1) - timedelta(days = 1)).day
    return date(year, month, min(day, last))

def advance(moment: datetime, repeat, zone):
    # the next time a repeat is due, at the same clock time, so summer time keeps 9am at 9am
    local = moment.astimezone(zone)
    kind = kindOf(repeat)
    if kind == MONTHLY:
        month = local.month % 12 + 1
        day = monthDay(local.year + (1 if month == 1 else 0), month, int(repeat.split(':')[1]))
    elif kind == YEARLY:
        month, wanted = (int(part) for part in repeat.split(':')[1].split('-'))
        day = monthDay(local.year + 1, month, wanted)
    elif (days := daysOf(repeat)) is not None:
        day = local.date() + timedelta(days = 1)
        while day.weekday() not in days:
            day += timedelta(days = 1)
    else:
        day = local.date() + timedelta(days = 7 if kind == WEEKLY else 1)
    # on its minute: a repeat begun by a timer ("in 1 hour") doesn't keep that second every time
    return at(day, local.time().replace(second = 0, microsecond = 0), zone)

def nextAfter(moment: datetime, repeat, zone, now: datetime):
    # past now, however many were missed, so a repeat that came due while GBot was down sends once
    while moment <= now:
        moment = advance(moment, repeat, zone)
    return moment

def moveToZone(moment: datetime, oldZone, newZone):
    # the same clock time in the new zone: someone who moves still means their own 9am
    local = moment.astimezone(oldZone)
    return at(local.date(), local.time(), newZone)

def repeatPhrase(moment: datetime, repeat, zone):
    # describeRepeat inside a sentence: "every Thursday at 8:00 PM", not "every thursday at 8:00 pm"
    described = describeRepeat(moment, repeat, zone)
    return described[0].lower() + described[1:]

def ordinal(number):
    return f"{number}{'th' if 10 <= number % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th')}"

def describeRepeat(moment: datetime, repeat, zone):
    local = moment.astimezone(zone)
    clock = formatClock(local)
    kind = kindOf(repeat)
    if kind == DAILY:
        return f'Every day at {clock}'
    if kind == WEEKDAYS_ONLY:
        return f'Every weekday at {clock}'
    if kind == WEEKLY:
        return f'Every {WEEKDAY_NAMES[local.weekday()]} at {clock}'
    if kind == MONTHLY:
        return f"Every month on the {ordinal(int(repeat.split(':')[1]))} at {clock}"
    if kind == YEARLY:
        month, day = (int(part) for part in repeat.split(':')[1].split('-'))
        return f"Every year on {date(2000, month, 1).strftime('%b')} {day} at {clock}"
    if kind == DAYS:
        names = [WEEKDAY_NAMES[day][:3] for day in daysOf(repeat)]
        listed = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
        return f'Every {listed} at {clock}'
    return 'Once'

def formatClock(local: datetime):
    return local.strftime('%I:%M %p').lstrip('0')

def formatMoment(moment: datetime, zone, now: datetime):
    # for where Discord's own timestamps don't show, like a dropdown: "Tue, Nov 10 at 9:00 AM", with
    # the year when it isn't this one, or "Wed, Nov 10" next year reads as this week's
    local = moment.astimezone(zone)
    year = '' if local.year == now.astimezone(zone).year else f', {local.year}'
    return f"{local.strftime('%a, %b')} {local.day}{year} at {formatClock(local)}"

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
