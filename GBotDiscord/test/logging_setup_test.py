#region IMPORTS
import json
import logging
import os
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

from GBotDiscord.src.logging_setup import JsonLineFormatter, buildHandlers, captureStream, duplicateStream, installCrashLogging
#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/logging_setup_test.py
#   - or use the "Python: Current File" run configuration to run logging_setup_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestLoggingSetup(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting logging setup unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted logging setup unit tests.\n')

    def setUp(self):
        self.formatter = JsonLineFormatter()

    def _record(self, msg, args = (), exc_info = None, level = logging.INFO, stack = None):
        record = logging.LogRecord('root', level, __file__, 1, msg, args, exc_info)
        record.stack_info = stack
        return record

    def _format(self, *args, **kwargs):
        line = self.formatter.format(self._record(*args, **kwargs))
        self.assertNotIn('\n', line, 'one record must stay one line')
        return json.loads(line)

    #region JsonLineFormatter
    def test_format_has_the_four_expected_fields(self):
        entry = self._format('hello')
        self.assertEqual(list(entry), ['level', 'time', 'message', 'name'])
        self.assertEqual((entry['level'], entry['message'], entry['name']), ('INFO', 'hello', 'root'))

    # Text the old formatter broke. A newline or control character made an invalid line.
    def test_format_any_text_survives_a_round_trip(self):
        for text in ('say "hi"', 'back\\slash', 'line1\nline2', 'tab\there', 'bell\x07', 'emoji 🌧️', ''):
            with self.subTest(text = text):
                self.assertEqual(self._format(text)['message'], text)

    # The old formatter rewrote the shared record, so the second handler escaped it a second time.
    def test_format_gives_two_handlers_the_same_line(self):
        record = self._record('say "%s"', ('hi',))
        first = self.formatter.format(record)
        self.assertEqual(self.formatter.format(record), first)
        self.assertEqual(record.msg, 'say "%s"')
        self.assertEqual(record.args, ('hi',))
        self.assertEqual(json.loads(first)['message'], 'say "hi"')

    # The old formatter called .replace on the message, so this raised and the message was lost.
    def test_format_accepts_a_non_string_message(self):
        self.assertEqual(self._format(ValueError('boom'))['message'], 'boom')

    def test_format_nests_a_json_message(self):
        self.assertEqual(self._format('{"response": {"status": "ok"}}')['message'], {'response': {'status': 'ok'}})
        self.assertEqual(self._format(' [1, 2]')['message'], [1, 2])

    def test_format_keeps_almost_json_as_text(self):
        for text in ('[youtube] Extracting URL', '{not json}', '12', 'true', 'null'):
            with self.subTest(text = text):
                self.assertEqual(self._format(text)['message'], text)

    def test_format_puts_a_traceback_in_its_own_field(self):
        try:
            raise RuntimeError('bad')
        except RuntimeError:
            entry = self._format('failed', exc_info = sys.exc_info())
        self.assertEqual(entry['message'], 'failed')
        self.assertIn('RuntimeError: bad', entry['exception'])

    def test_format_includes_a_stack(self):
        self.assertEqual(self._format('x', stack = 'Stack (most recent call last):')['stack'], 'Stack (most recent call last):')
    #endregion

    #region buildHandlers
    def test_buildHandlers_writes_valid_json_to_both_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'test.log')
            stream = MagicMock()
            handlers = buildHandlers(path, stream)
            record = self._record('say "hi"\nthere')
            for handler in handlers:
                handler.handle(record)
                handler.flush()
            handlers[0].close()
            with open(path, encoding = 'utf-8') as logFile:
                fromFile = logFile.read().rstrip('\n')
            fromStream = stream.write.call_args_list[0].args[0].rstrip('\n')
        self.assertEqual(json.loads(fromFile)['message'], 'say "hi"\nthere')
        self.assertEqual(fromStream, fromFile)
    #endregion

    #region captureStream
    def _target(self):
        # a real descriptor standing in for stdout, whose written bytes can be read back
        readEnd, writeEnd = os.pipe()
        self.addCleanup(os.close, readEnd)
        return readEnd, writeEnd

    def test_duplicateStream_writes_past_a_redirect(self):
        readEnd, target = self._target()
        stream = duplicateStream(target)
        os.close(target)
        stream.write('still here\n')
        stream.close()
        self.assertEqual(os.read(readEnd, 100), b'still here\n')

    def test_captureStream_turns_lines_into_records(self):
        readEnd, target = self._target()
        with self.assertLogs('capture-test', level = logging.WARNING) as logs:
            thread = captureStream(target, 'capture-test', logging.WARNING)
            # a subprocess inherits the descriptor, which is the case this exists for
            os.write(target, b'first line\n\n  second line  \nbad \xff byte\n')
            # replacing the descriptor drops the last writer, which ends the reader
            os.dup2(os.dup(readEnd), target)
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual([record.getMessage() for record in logs.records], ['first line', '  second line', 'bad � byte'])
        os.close(target)

    # If the reader stopped and the pipe stayed in place, the pipe would fill and block the whole bot.
    def test_captureStream_restores_the_descriptor_if_the_reader_dies(self):
        readEnd, target = self._target()
        with patch.object(logging.getLogger('capture-die'), 'log', side_effect = RuntimeError('reader died')), patch.object(threading, 'excepthook'):
            thread = captureStream(target, 'capture-die', logging.INFO)
            os.write(target, b'kills the reader\n')
            thread.join(5)
        self.assertFalse(thread.is_alive())
        os.write(target, b'reaches the original\n')
        self.assertEqual(os.read(readEnd, 100), b'reaches the original\n')
        os.close(target)
    #endregion

    #region installCrashLogging
    def test_installCrashLogging_logs_main_and_thread_crashes(self):
        logger = MagicMock()
        self.addCleanup(setattr, sys, 'excepthook', sys.excepthook)
        self.addCleanup(setattr, threading, 'excepthook', threading.excepthook)
        installCrashLogging(logger)
        error = RuntimeError('bad')
        sys.excepthook(RuntimeError, error, None)
        logger.critical.assert_called_with('Uncaught exception', exc_info = (RuntimeError, error, None))

        named = threading.Thread(name = 'worker')
        threading.excepthook(threading.ExceptHookArgs((RuntimeError, error, None, named)))
        logger.critical.assert_called_with('Uncaught exception in thread worker', exc_info = (RuntimeError, error, None))

        threading.excepthook(threading.ExceptHookArgs((RuntimeError, error, None, None)))
        logger.critical.assert_called_with('Uncaught exception in thread unknown', exc_info = (RuntimeError, error, None))
    #endregion
