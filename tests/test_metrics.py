import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from loadgen import summarize
class MetricsTests(unittest.TestCase):
    def test_overlap_integral_and_completion_window(self):
        rows=[dict(planned=0,sent=0,done=.2,status=200,instance='a',latency_ms=200,scheduled_latency_ms=200,lag_ms=0),dict(planned=.9,sent=.9,done=1.2,status=500,instance='b',latency_ms=300,scheduled_latency_ms=300,lag_ms=0)]
        s=summarize(rows,1,2)
        self.assertAlmostEqual(s['measured_L'],.3)
        self.assertEqual(s['achieved_rps'],1)
        self.assertEqual(s['outstanding_at_end'],1)
        self.assertEqual(s['non_2xx_fraction'],.5)
        self.assertEqual(s['max_inflight'],1)
import time
from unittest.mock import patch
from loadgen import request_one, LOCAL
class TransportTests(unittest.TestCase):
    def test_reuses_connection_and_keeps_query(self):
        LOCAL.connection=None
        with patch('loadgen.http.client.HTTPConnection') as factory:
            response=factory.return_value.getresponse.return_value
            response.status=200; response.getheader.return_value='replica-a'
            for _ in range(2):
                origin=time.perf_counter()
                result=request_one('http://localhost:8099/items?limit=2',origin,origin)
                self.assertEqual(result['status'],200)
            self.assertEqual(factory.call_count,1)
            factory.return_value.request.assert_called_with('GET','/items?limit=2')
        LOCAL.connection=None
    def test_transport_failure_records_reason(self):
        LOCAL.connection=None
        with patch('loadgen.http.client.HTTPConnection') as factory:
            factory.return_value.request.side_effect=OSError('test socket failure')
            origin=time.perf_counter()
            result=request_one('http://localhost:8099/',origin,origin)
            self.assertEqual(result['status'],0)
            self.assertIn('test socket failure',result['error'])
            self.assertIsNone(LOCAL.connection)

if __name__=='__main__': unittest.main()
