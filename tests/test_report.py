import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import report

class ReportTests(unittest.TestCase):
    def test_unknown_image_and_changed_raw_rows_update_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);out=root/'results';out.mkdir()
            (root/'author.json').write_text(json.dumps(dict(student='Test',group='Group')))
            for filename in ['DESIGN.md','Dockerfile','.dockerignore','docker-compose.yml','nginx.conf','schema.sql']:
                (root/filename).write_text('fixture')
            (out/'series.json').write_text(json.dumps(dict(status='complete',image_id='arbitrary-new-image')))
            def row(i):
                return dict(planned=i*.001,sent=i*.001,done=i*.001+.01,
                            status=200,instance='test',latency_ms=10,
                            scheduled_latency_ms=10,lag_ms=0)
            for n in (1,2):
                for rate in (10,100,500):
                    for repeat in (1,2,3):
                        # Summary intentionally stale: the raw rows must be used.
                        data=dict(summary=dict(duration=30,target_rps=rate,achieved_rps=999),rows=[row(0)])
                        (out/f'open-{n}-{rate}-{repeat}.json').write_text(json.dumps(data))
            with patch.object(report,'ROOT',root),patch.object(report,'OUT',out):
                report.main()
                first=(root/'REPORT.md').read_text()
                for repeat in (1,2,3):
                    path=out/f'open-2-500-{repeat}.json'
                    data=json.loads(path.read_text());data['rows']=[row(i) for i in range(3)]
                    path.write_text(json.dumps(data))
                report.main()
                second=(root/'REPORT.md').read_text()
            self.assertNotEqual(first,second)
            self.assertIn('S=0.100/0.033=3.00000',second)
            self.assertNotIn('431.567',second)
            self.assertNotIn('999.000',second)
            self.assertNotIn('\n\n| 2 |',second)
            self.assertIn('Порівняння не виконано',second)

if __name__=='__main__':
    unittest.main()
