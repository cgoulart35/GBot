#region IMPORTS
import unittest

#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/music/music_test.py
#   - or use the "Python: Current File" run configuration to run music_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestMusic(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting music unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted music unit tests.\n')

    def test_on_guild_join(self):
        pass

    def test_on_guild_remove(self):
        pass

    def test_on_ready(self):
        pass

    def test_music_timeout(self):
        pass

    def test_cached_youtube_files(self):
        pass

    def test_play(self):
        pass

    def test_queue(self):
        pass

    def test_elevator(self):
        pass

    def test_skip(self):
        pass

    def test_stop(self):
        pass

    def test_pause(self):
        pass

    def test_resume(self):
        pass

    def test_searchYouTubeAndCacheDownload(self):
        pass

    def test_channelSync(self):
        pass

    def test_playMusic(self):
        pass

    def test_disconnectAndClearQueue(self):
        pass

if __name__ == '__main__':
    unittest.main()