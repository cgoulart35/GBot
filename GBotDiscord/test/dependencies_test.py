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
    'httpx',
    'nextcord',
    'nextcord.ext.menus',
    'numpy',
    'pandas',
    'pkg_resources',
    'pyrebase',
    'quart',
    'quart_cors',
    'yt_dlp',
    'urllib3',
    'requests_toolbelt',
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
