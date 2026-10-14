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


class OpenLoopValidityTests(unittest.TestCase):
    def test_dispatch_rate_and_lag_independent_of_completion_rate(self):
        from loadgen import validity
        good = dict(target_rps=500, sent_rps=500, achieved_rps=120,
                    p95_scheduler_lag_ms=5)
        self.assertEqual(validity(good), [])
        self.assertTrue(validity(dict(good, sent_rps=135)))
        self.assertTrue(validity(dict(good, p95_scheduler_lag_ms=1000)))

    def test_slow_responses_queue_with_insufficient_threads(self):
        from loadgen import worker, summarize, validity
        def delayed(url, planned, origin):
            sent=time.perf_counter()
            time.sleep(.03)
            done=time.perf_counter()
            return dict(planned=planned-origin, sent=sent-origin, done=done-origin,
                        status=200, instance='test', latency_ms=(done-sent)*1000,
                        scheduled_latency_ms=(done-planned)*1000, lag_ms=(sent-planned)*1000)
        with patch('loadgen.request_one', side_effect=delayed):
            queued=worker(('http://unused',500,.2,time.perf_counter()+.05,0,1,1))
            independent=worker(('http://unused',500,.2,time.perf_counter()+.05,0,1,64))
        self.assertTrue(validity(summarize(queued,.2,500)))
        self.assertEqual(validity(summarize(independent,.2,500)), [])
