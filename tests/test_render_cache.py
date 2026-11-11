import time
import unittest
from unittest.mock import patch
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtTest import QTest
from amigo.markdown import render
from amigo.render_cache import Presentation

app=QCoreApplication.instance() or QCoreApplication([])

class CacheTests(unittest.TestCase):
    def test_latest_stream_revision_wins_and_unchanged_messages_reuse_blocks(self):
        cache=Presentation();calls=[]
        def slow(text):
            calls.append(text);time.sleep(.03);return render(text)
        try:
            with patch('amigo.render_cache.render',side_effect=slow):
                cache.get(1,'first');cache.start()
                cache.get(1,'partial **');cache.get(1,'final **ação**')
                deadline=time.monotonic()+3
                while (cache.worker or cache.pending) and time.monotonic()<deadline:QTest.qWait(10)
                blocks=cache.get(1,'final **ação**')
                self.assertEqual(blocks[0]['html'],'final <b>ação</b>')
                self.assertIs(cache.get(1,'final **ação**'),blocks)
                self.assertEqual(calls,['first','final **ação**'])
                self.assertFalse(cache.pending);self.assertIsNone(cache.worker)
        finally:cache.close()

    def test_bad_presentation_falls_back_to_literal_text(self):
        cache=Presentation()
        try:
            with patch('amigo.render_cache.render',side_effect=ValueError('fixture')):
                cache.get(1,'<img>');cache.start()
                deadline=time.monotonic()+3
                while cache.worker and time.monotonic()<deadline:QTest.qWait(10)
                block=cache.get(1,'<img>')[0]
                self.assertEqual(block['kind'],'plain');self.assertEqual(block['text'],'<img>')
        finally:cache.close()
