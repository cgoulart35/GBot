#region IMPORTS
import importlib
import importlib.metadata
import unittest
#endregion

# Runtime dependency lock tests (HalloweenEvent pattern): every dep pinned in
# requirements.txt must import, and security floors must never regress.

RUNTIME_DEPENDENCY_MODULES = [
    'audioop',
    'debugpy',
    'df2img',
    'emoji',
    'firebase_admin',
    'httpx',
    'nextcord',
    'nextcord.ext.menus',
    'numpy',
    'pandas',
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

    def test_h11_at_or_above_security_floor(self):
        # PYSEC-2026-348 was fixed in h11 0.16.0 (transitive via httpx/httpcore);
        # the resolved version must never regress below it.
        version = tuple(int(part) for part in importlib.metadata.version('h11').split('.'))
        self.assertGreaterEqual(version, (0, 16, 0))
