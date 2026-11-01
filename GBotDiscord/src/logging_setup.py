#region IMPORTS
import json
import logging
import os
import sys
import threading
#endregion

class JsonLineFormatter(logging.Formatter):
    """Every record becomes one line of valid JSON, so any line can be pasted into a JSON formatter.

    json.dumps does the escaping. Hand-written escaping missed newlines and control characters, and
    it had to rewrite the record to do it, so a second handler escaped the same text all over again.
    A record is shared between handlers, so this must never change one.
    """

    def format(self, record):
        entry = {
            'level': record.levelname,
            'time': self.formatTime(record),
            'message': self.parseMessage(record.getMessage()),
            'name': record.name
        }
        if record.exc_info:
            entry['exception'] = self.formatException(record.exc_info)
        if record.stack_info:
            entry['stack'] = self.formatStack(record.stack_info)
        return json.dumps(entry, ensure_ascii = False)

    def parseMessage(self, message):
        # a message that is itself a JSON object or list nests as real JSON, so the API's lines only
        # need formatting once. Anything else stays text, including "[youtube] ...", which merely
        # looks like the start of a list.
        if message.lstrip().startswith(('{', '[')):
            try:
                return json.loads(message)
            except ValueError:
                pass
        return message

def buildHandlers(logFilePath, stream):
    formatter = JsonLineFormatter()
    handlers = [logging.FileHandler(filename = logFilePath, encoding = 'utf-8'), logging.StreamHandler(stream)]
    for handler in handlers:
        handler.setFormatter(formatter)
    return handlers

def duplicateStream(fd):
    # the real stream, kept for the log handlers: once captureStream redirects fd, a handler writing
    # to it would feed its own output straight back into the capture, forever
    return os.fdopen(os.dup(fd), 'w', encoding = 'utf-8', errors = 'replace', buffering = 1)

def captureStream(fd, loggerName, level):
    """Turns everything written to a file descriptor into log records, one per line.

    Redirecting the descriptor rather than sys.stdout is what reaches subprocesses, which inherit it
    and never see Python's objects: ffmpeg's stderr, and hypercorn's request lines, all come through
    here. If the reader ever stops, the descriptor goes back to where it pointed, because otherwise
    the pipe fills up and the next write to it blocks the whole bot.
    """
    original = os.dup(fd)
    readEnd, writeEnd = os.pipe()
    os.dup2(writeEnd, fd)
    os.close(writeEnd)
    logger = logging.getLogger(loggerName)

    def relay():
        try:
            with os.fdopen(readEnd, errors = 'replace') as lines:
                for line in lines:
                    text = line.rstrip()
                    if text:
                        logger.log(level, text)
        finally:
            os.dup2(original, fd)
            os.close(original)

    thread = threading.Thread(target = relay, daemon = True, name = f'log-capture-{loggerName}')
    thread.start()
    return thread

def installCrashLogging(logger):
    # Logged directly rather than left to reach stderr: the capture reader is a daemon thread, and it
    # can die with the process before relaying the very traceback that explains why.
    def logUncaught(excType, excValue, excTraceback):
        logger.critical('Uncaught exception', exc_info = (excType, excValue, excTraceback))

    def logUncaughtInThread(args):
        threadName = args.thread.name if args.thread is not None else 'unknown'
        logger.critical(f'Uncaught exception in thread {threadName}', exc_info = (args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = logUncaught
    threading.excepthook = logUncaughtInThread
