#region IMPORTS
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from GBotDiscord.src.reminders import when
#endregion

NEW_YORK = ZoneInfo('America/New_York')
# Monday 9 November 2026, 8:14 PM in New York
NOW = datetime(2026, 11, 9, 20, 14, tzinfo = NEW_YORK)

def local(year, month, day, hour = 9, minute = 0, zone = NEW_YORK):
    return datetime(year, month, day, hour, minute, tzinfo = zone)

class TestWhen(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\n\nStarting when unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted when unit tests.\n')

    def read(self, text, now = NOW):
        return when.parseWhen(text, now)

    def test_in_a_while(self):
        self.assertEqual(self.read('in 2 hours'), NOW + timedelta(hours = 2))
        self.assertEqual(self.read('in an hour'), NOW + timedelta(hours = 1))
        self.assertEqual(self.read('in 1h30m'), NOW + timedelta(minutes = 90))
        self.assertEqual(self.read('in 1 hour and 30 minutes'), NOW + timedelta(minutes = 90))
        self.assertEqual(self.read('In 10 mins.'), NOW + timedelta(minutes = 10))
        self.assertEqual(self.read('in 3 days'), NOW + timedelta(days = 3))
        self.assertEqual(self.read('in a week'), NOW + timedelta(weeks = 1))
        for text in ('in', 'in soon', 'in 2', 'in 2 parsecs', 'in 0 minutes', 'in 2 hours later', 'in later 2 hours'):
            with self.subTest(text = text), self.assertRaises(when.WhenNotUnderstood):
                self.read(text)

    def test_months_and_years_are_the_calendars(self):
        self.assertEqual(self.read('in a year'), local(2027, 11, 9, 20, 14))
        self.assertEqual(self.read('in 2 months'), local(2027, 1, 9, 20, 14))
        self.assertEqual(self.read('in 1 year and 2 days'), local(2027, 11, 11, 20, 14))
        self.assertEqual(self.read('in 1mo'), local(2026, 12, 9, 20, 14))
        # a shorter month ends on its last day, leap years included
        self.assertEqual(self.read('in a month', local(2027, 1, 31)), local(2027, 2, 28))
        self.assertEqual(self.read('in a month', local(2028, 1, 31)), local(2028, 2, 29))
        self.assertEqual(self.read('in 12 months', local(2026, 12, 31)), local(2027, 12, 31))
        with self.assertRaises(when.WhenTooFar):
            self.read('in 1000 years')
        with self.assertRaises(when.WhenNotUnderstood):
            self.read('in 0 months')

    def test_next_week_month_and_year(self):
        self.assertEqual(self.read('next week'), local(2026, 11, 16, 20, 14))
        self.assertEqual(self.read('next month'), local(2026, 12, 9, 20, 14))
        self.assertEqual(self.read('next year at 9am'), local(2027, 11, 9, 9))
        self.assertEqual(self.read('next month 6pm'), local(2026, 12, 9, 18))
        for text in ('next decade', 'next year at lunch'):
            with self.subTest(text = text), self.assertRaises(when.WhenNotUnderstood):
                self.read(text)

    def test_today_tonight_and_tomorrow(self):
        self.assertEqual(self.read('tomorrow 9am'), local(2026, 11, 10, 9))
        self.assertEqual(self.read('tomorrow at 9:30 pm'), local(2026, 11, 10, 21, 30))
        self.assertEqual(self.read('tmrw'), local(2026, 11, 10, 9))
        self.assertEqual(self.read('today 11pm'), local(2026, 11, 9, 23))
        # a day said outright doesn't roll on: 8 PM tonight has gone at 8:14
        with self.assertRaises(when.WhenInThePast):
            self.read('tonight')

    def test_tonight_is_the_evening(self):
        early = local(2026, 11, 9, 15)
        self.assertEqual(self.read('tonight', early), local(2026, 11, 9, 20))
        self.assertEqual(self.read('tonight at 9', early), local(2026, 11, 9, 21))
        with self.assertRaises(when.WhenInThePast):
            self.read('today 9am')

    def test_a_weekday(self):
        self.assertEqual(self.read('Thursday 8pm'), local(2026, 11, 12, 20))
        self.assertEqual(self.read('thu'), local(2026, 11, 12, 9))
        self.assertEqual(self.read('next friday at noon'), local(2026, 11, 13, 12))
        # today's, if it hasn't happened yet, else next week's
        self.assertEqual(self.read('monday 11pm'), local(2026, 11, 9, 23))
        self.assertEqual(self.read('monday 9am'), local(2026, 11, 16, 9))

    def test_a_date(self):
        self.assertEqual(self.read('Dec 25 10:00'), local(2026, 12, 25, 10))
        self.assertEqual(self.read('december 25th'), local(2026, 12, 25, 9))
        self.assertEqual(self.read('25 Dec 7pm'), local(2026, 12, 25, 19))
        self.assertEqual(self.read('Jan 2, 2027 at 8am'), local(2027, 1, 2, 8))
        self.assertEqual(self.read('2026-12-25 18:30'), local(2026, 12, 25, 18, 30))
        self.assertEqual(self.read('12/25'), local(2026, 12, 25, 9))
        self.assertEqual(self.read('12/25/27 noon'), local(2027, 12, 25, 12))
        # a date this year that has gone means next year's
        self.assertEqual(self.read('Nov 1'), local(2027, 11, 1, 9))
        with self.assertRaises(when.WhenInThePast):
            self.read('2025-01-01')
        for text in ('Feb 30', '13/40', 'Smarch 3'):
            with self.subTest(text = text), self.assertRaises(when.WhenNotUnderstood):
                self.read(text)

    def test_a_time_alone_is_its_next_one(self):
        self.assertEqual(self.read('9pm'), local(2026, 11, 9, 21))
        self.assertEqual(self.read('at 8am'), local(2026, 11, 10, 8))
        self.assertEqual(self.read('21:00'), local(2026, 11, 9, 21))
        self.assertEqual(self.read('midnight'), local(2026, 11, 10, 0))
        self.assertEqual(self.read('noon'), local(2026, 11, 10, 12))
        self.assertEqual(self.read('9 p.m.'), local(2026, 11, 9, 21))

    def test_in_counts_to_the_second(self):
        self.assertEqual(self.read('in 30 seconds'), NOW + timedelta(seconds = 30))
        self.assertEqual(self.read('in 1m30s'), NOW + timedelta(seconds = 90))
        self.assertEqual(self.read('in 200000 secs'), NOW + timedelta(seconds = 200000))
        # a timer counts from now, and a time that's named falls on its minute
        self.assertEqual(when.readWhen('in 90 seconds', NOW)[1], True)
        self.assertEqual(when.readWhen('next month', NOW)[1], True)
        for text in ('next month 6pm', 'tomorrow 9am', '9pm', 'Dec 25'):
            with self.subTest(text = text):
                self.assertEqual(when.readWhen(text, NOW)[1], False)

    def test_a_time_in_the_minute_it_is_goes_off_now(self):
        # named times fall on their minute, so the one under way hasn't gone
        now = NOW.replace(second = 40)
        for text in ('8:14pm', 'today 8:14pm', 'monday 8:14pm', 'Nov 9 8:14pm'):
            with self.subTest(text = text):
                self.assertEqual(self.read(text, now), NOW)
        # the minute before has, so it's the next one
        self.assertEqual(self.read('8:13pm', now), local(2026, 11, 10, 20, 13))
        with self.assertRaises(when.WhenInThePast):
            self.read('today 8:13pm', now)

    def test_a_huge_count_is_too_far_rather_than_a_crash(self):
        with self.assertRaises(when.WhenTooFar):
            self.read('in 99999999999 days')
        # each term under the cap, and their sum past what a date can hold
        with self.assertRaises(when.WhenTooFar):
            self.read('in 500w 500w 500w 500w 500w')
        # each count is held to the limit before it's multiplied, so the biggest can't overflow
        for text in ('in 99999999999 weeks', 'in 99999999999 years', 'in 999999999999999 seconds'):
            with self.subTest(text = text), self.assertRaises(when.WhenTooFar):
                self.read(text)

    def test_what_it_cannot_read(self):
        for text in ('', None, 'soonish', '25:00', '13pm', '9:75', 'tomorrow at lunch', 'whenever'):
            with self.subTest(text = text), self.assertRaises(when.WhenNotUnderstood):
                self.read(text)

    def test_a_repeat_keeps_its_clock_time_across_summer_time(self):
        # New York leaves summer time on 1 November 2026
        before = local(2026, 10, 31, 9)
        self.assertEqual(when.advance(before, when.DAILY, NEW_YORK), local(2026, 11, 1, 9))
        self.assertEqual(when.advance(before, when.WEEKLY, NEW_YORK), local(2026, 11, 7, 9))
        # one missed several times over sends once, at the next one still to come
        self.assertEqual(when.nextAfter(local(2026, 11, 1, 9), when.DAILY, NEW_YORK, NOW), local(2026, 11, 10, 9))

    def test_repeats_made_exact_from_their_first_time(self):
        thursday = local(2026, 11, 12, 20)
        self.assertEqual([when.makeRepeat(kind, thursday, NEW_YORK) for kind in (when.ONCE, when.DAILY, when.WEEKDAYS_ONLY, when.WEEKLY, when.MONTHLY, when.YEARLY)],
                         ['once', 'daily', 'weekdays', 'weekly', 'monthly:12', 'yearly:11-12'])
        self.assertEqual(when.makeRepeat(when.DAYS, thursday, NEW_YORK, [4, 0, 2, 0]), 'days:0,2,4')
        for kind, days in ((when.DAYS, []), (when.DAYS, [7]), (when.DAYS, ['mon']), ('hourly', None)):
            with self.subTest(kind = kind, days = days), self.assertRaises(when.RepeatNotUnderstood):
                when.makeRepeat(kind, thursday, NEW_YORK, days)

    def test_each_repeat_moves_on_at_the_same_clock_time(self):
        friday = local(2026, 11, 13, 9)
        self.assertEqual(when.advance(friday, 'weekdays', NEW_YORK), local(2026, 11, 16, 9))
        self.assertEqual(when.advance(local(2026, 11, 16, 9), 'weekdays', NEW_YORK), local(2026, 11, 17, 9))
        self.assertEqual(when.advance(friday, 'days:0,2,4', NEW_YORK), local(2026, 11, 16, 9))
        self.assertEqual(when.advance(local(2026, 11, 16, 9), 'days:0,2,4', NEW_YORK), local(2026, 11, 18, 9))
        # a month's own date, back after a shorter month, and December into January
        self.assertEqual(when.advance(local(2027, 1, 31), 'monthly:31', NEW_YORK), local(2027, 2, 28))
        self.assertEqual(when.advance(local(2027, 2, 28), 'monthly:31', NEW_YORK), local(2027, 3, 31))
        self.assertEqual(when.advance(local(2026, 12, 10), 'monthly:10', NEW_YORK), local(2027, 1, 10))
        # Feb 29 on the years that have it, and the 28th between
        self.assertEqual(when.advance(local(2028, 2, 29), 'yearly:2-29', NEW_YORK), local(2029, 2, 28))
        self.assertEqual(when.advance(local(2031, 2, 28), 'yearly:2-29', NEW_YORK), local(2032, 2, 29))

    def test_a_repeat_begun_by_a_timer_falls_on_its_minute_after(self):
        begun = datetime(2026, 11, 10, 21, 30, 53, 120000, tzinfo = NEW_YORK)
        self.assertEqual(when.advance(begun, 'days:0', NEW_YORK), local(2026, 11, 16, 21, 30))
        self.assertEqual(when.advance(begun, 'daily', NEW_YORK), local(2026, 11, 11, 21, 30))

    def test_a_repeat_by_weekday_starts_on_one_of_its_days(self):
        saturday = local(2026, 11, 14, 9)
        self.assertEqual(when.onOrAfter(saturday, 'weekdays', NEW_YORK), local(2026, 11, 16, 9))
        self.assertEqual(when.onOrAfter(saturday, 'days:5', NEW_YORK), saturday)
        self.assertEqual(when.onOrAfter(saturday, 'monthly:14', NEW_YORK), saturday)

    def test_reading_and_describing_repeats(self):
        self.assertEqual(when.readRepeat('Weekdays'), (when.WEEKDAYS_ONLY, None))
        self.assertEqual(when.readRepeat('annually'), (when.YEARLY, None))
        self.assertEqual(when.readRepeat('mon,wed,fri'), (when.DAYS, [0, 2, 4]))
        self.assertEqual(when.readRepeat('Tue and Thu'), (when.DAYS, [1, 3]))
        for text in ('hourly', '', 'mon,soon'):
            with self.subTest(text = text):
                self.assertIsNone(when.readRepeat(text))
        moment = local(2026, 11, 12, 20)
        self.assertEqual([when.describeRepeat(moment, repeat, NEW_YORK) for repeat in ('weekdays', 'monthly:1', 'monthly:22', 'monthly:3', 'monthly:11', 'yearly:2-29', 'days:4', 'days:0,2,4')], [
            'Every weekday at 8:00 PM', 'Every month on the 1st at 8:00 PM', 'Every month on the 22nd at 8:00 PM', 'Every month on the 3rd at 8:00 PM',
            'Every month on the 11th at 8:00 PM', 'Every year on Feb 29 at 8:00 PM', 'Every Fri at 8:00 PM', 'Every Mon, Wed and Fri at 8:00 PM'])

    def test_moving_zones_keeps_the_clock_time(self):
        denver = ZoneInfo('America/Denver')
        moved = when.moveToZone(local(2026, 11, 10, 9), NEW_YORK, denver)
        self.assertEqual(moved, datetime(2026, 11, 10, 9, tzinfo = denver))
        self.assertEqual(moved - local(2026, 11, 10, 9), timedelta(hours = 2))

    def test_describing(self):
        moment = local(2026, 11, 12, 20)
        self.assertEqual(when.describeRepeat(moment, when.ONCE, NEW_YORK), 'Once')
        self.assertEqual(when.describeRepeat(moment, when.DAILY, NEW_YORK), 'Every day at 8:00 PM')
        self.assertEqual(when.describeRepeat(moment, when.WEEKLY, NEW_YORK), 'Every Thursday at 8:00 PM')
        self.assertEqual(when.formatMoment(moment, NEW_YORK, NOW), 'Thu, Nov 12 at 8:00 PM')
        self.assertEqual(when.formatMoment(moment, ZoneInfo('UTC'), NOW), 'Fri, Nov 13 at 1:00 AM')
        # another year says which, or next year's Nov 10 reads as this week's
        self.assertEqual(when.formatMoment(local(2027, 11, 10, 18, 41), NEW_YORK, NOW), 'Wed, Nov 10, 2027 at 6:41 PM')
        # this year is the reader's: New Year's Eve in New York is already next year in UTC
        self.assertEqual(when.formatMoment(local(2026, 12, 31, 21), NEW_YORK, NOW), 'Thu, Dec 31 at 9:00 PM')

    def test_zones(self):
        self.assertEqual(when.zoneLabel('America/New_York'), 'Eastern Time')
        self.assertEqual(when.zoneLabel('Asia/Kathmandu'), 'Asia/Kathmandu')
        self.assertEqual(when.zoneNamed('europe/berlin').key, 'Europe/Berlin')
        self.assertEqual(when.zoneNamed(' America/Los Angeles ').key, 'America/Los_Angeles')
        self.assertIsNone(when.zoneNamed('Mars/Olympus'))
        self.assertIsNone(when.zoneNamed(None))
        # every offered zone is real, and the picker can show them all
        self.assertLessEqual(len(when.ZONES), 25)
        for name, _, _ in when.ZONES:
            ZoneInfo(name)
