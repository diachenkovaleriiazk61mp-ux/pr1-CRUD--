import io
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import experiment

class StartupTests(unittest.TestCase):
    def test_health_is_polled_before_compose_finishes(self):
        entered = threading.Event()
        observed = threading.Event()
        def compose(*args):
            entered.set()
            if not observed.wait(2):
                raise AssertionError('health was not polled during compose up')
        class Response(io.BytesIO):
            status = 200
        def health(*args, **kwargs):
            self.assertTrue(entered.wait(2))
            observed.set()
            return Response(b'{}')
        with patch.object(experiment,'compose',side_effect=compose), patch.object(experiment.urllib.request,'urlopen',side_effect=health):
            self.assertGreaterEqual(experiment.measure_startup(),0)

    def test_compose_failure_is_not_reported_as_success(self):
        with patch.object(experiment,'compose',side_effect=RuntimeError('compose failed')), patch.object(experiment.urllib.request,'urlopen',side_effect=OSError('offline')):
            with self.assertRaisesRegex(RuntimeError,'compose failed'):
                experiment.measure_startup()

if __name__ == '__main__':
    unittest.main()
