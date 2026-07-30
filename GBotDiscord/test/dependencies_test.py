#region IMPORTS
import importlib
import importlib.metadata
import unittest

from nextcord import voice_client
#endregion

# Runtime dependency lock tests (HalloweenEvent pattern): every dep pinned in
# requirements.txt must import, and security floors must never regress.

RUNTIME_DEPENDENCY_MODULES = [
    'audioop',
    'dave',
    'debugpy',
    'df2img',
    'emoji',
    'firebase_admin',
    'httpx',
    'nextcord',
    'nextcord.ext.menus',
    'numpy',
    'pandas',
    'nacl.secret',
    'quart',
    'quart_cors',
    'yt_dlp',
    'urllib3',
    'werkzeug',
]


class TestDependencies(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        print('\nExecuting dependencies unit tests...\n')

    @classmethod
    def tearDownClass(cls):
        print('\n\nCompleted dependencies unit tests.\n')

    def test_runtimeDependencies_all_importable(self):
        for moduleName in RUNTIME_DEPENDENCY_MODULES:
            with self.subTest(module = moduleName):
                importlib.import_module(moduleName)

    def test_ytDlp_at_or_above_security_floor(self):
        # CVE-2026-26331 was fixed in yt-dlp 2026.02.21; the pin must never regress below it.
        version = tuple(int(part) for part in importlib.metadata.version('yt-dlp').split('.'))
        self.assertGreaterEqual(version, (2026, 2, 21))

    def test_urllib3_at_or_above_security_floor(self):
        # urllib3 1.26.x carried five PYSEC advisories held in place by Pyrebase4's pin;
        # the firebase-admin migration cleared them and urllib3 must never regress below 2.
        version = tuple(int(part) for part in importlib.metadata.version('urllib3').split('.'))
        self.assertGreaterEqual(version, (2, 0, 0))

    def test_quart_at_or_above_security_floor(self):
        # PYSEC-2026-1860 was fixed in quart 0.20.0; the pin must never regress below it.
        version = tuple(int(part) for part in importlib.metadata.version('quart').split('.'))
        self.assertGreaterEqual(version, (0, 20, 0))

    def test_pynacl_at_or_above_security_floor(self):
        # PYSEC-2026-3002 was fixed in PyNaCl 1.6.2. nextcord 3.2.0's voice extra declares
        # PyNaCl<1.6, so the tempting "just honour the library's range" move reintroduces the
        # advisory; the pin is above the ceiling on purpose and must never regress below it.
        version = tuple(int(part) for part in importlib.metadata.version('PyNaCl').split('.'))
        self.assertGreaterEqual(version, (1, 6, 2))

    def test_voiceStack_advertises_dave_protocol(self):
        # Discord has enforced DAVE (voice E2EE) for all non-stage voice since 2026-03-02 and
        # refuses connections with close code 4017 unless the client advertises a protocol
        # version. nextcord builds that number as min(its own ceiling, dave's ceiling) and
        # returns 0 outright when the binding is absent, so all three facts below have to hold
        # or /play, /spotify and /elevator are dead in production.
        self.assertTrue(voice_client.has_nacl, 'PyNaCl is missing: voice transport encryption is unavailable.')
        self.assertTrue(voice_client.has_dave, 'dave-py is missing: nextcord would advertise max_dave_protocol_version 0.')
        self.assertGreaterEqual(importlib.import_module('dave').get_max_supported_protocol_version(), 1)
        self.assertGreaterEqual(voice_client.E2EEState.MAX_SUPPORTED_PROTOCOL_VERSION, 1)

    def test_h11_at_or_above_security_floor(self):
        # PYSEC-2026-348 was fixed in h11 0.16.0 (transitive via httpx/httpcore);
        # the resolved version must never regress below it.
        version = tuple(int(part) for part in importlib.metadata.version('h11').split('.'))
        self.assertGreaterEqual(version, (0, 16, 0))
