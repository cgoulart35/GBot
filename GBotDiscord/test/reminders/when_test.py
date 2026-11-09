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
        self.assertEqual(when.formatMoment(moment, NEW_YORK), 'Thu, Nov 12 at 8:00 PM')
        self.assertEqual(when.formatMoment(moment, ZoneInfo('UTC')), 'Fri, Nov 13 at 1:00 AM')

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
