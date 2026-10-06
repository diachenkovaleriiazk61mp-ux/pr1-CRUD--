import sys, unittest
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import validate, create_app

class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.good=dict(patient_code='P007', vaccine='MMR', batch='B1', dose_number=1,
                       administration_date=date.today().isoformat(), facility='Clinic')
    def test_boundaries(self):
        for dose in (1,4):
            self.assertEqual(validate(dict(self.good,dose_number=dose)),{})
        for dose in (0,5,True,1.5,'1',None):
            self.assertIn('dose_number',validate(dict(self.good,dose_number=dose)))
    def test_dates(self):
        self.assertIn('administration_date',validate(dict(self.good,administration_date=(date.today()+timedelta(days=1)).isoformat())))
        for value in ('2026-02-30','20261006',None):
            self.assertIn('administration_date',validate(dict(self.good,administration_date=value)))
    def test_full_replacement_and_server_id(self):
        for field in self.good:
            data=self.good.copy(); del data[field]
            self.assertIn(field,validate(data))
        self.assertIn('id',validate(dict(self.good,id=7)))
    def test_invalid_json_shapes(self):
        for value in (None, [], 42, 'text'):
            self.assertIn('body',validate(value))
    def test_strings(self):
        for field in ('patient_code','vaccine','batch','facility'):
            for value in ('','   ',None,200,'a'*201):
                self.assertIn(field,validate(dict(self.good,**{field:value})))
    def test_http_validation_and_unavailable_health(self):
        class OfflinePool:
            def connection(self):
                raise RuntimeError('offline')
        client=create_app(OfflinePool()).test_client()
        self.assertEqual(client.get('/healthz').status_code,503)
        self.assertEqual(client.post('/vaccinations',json={}).status_code,400)
        self.assertEqual(client.post('/vaccinations',data='{',content_type='application/json').status_code,400)
        self.assertEqual(client.get('/vaccinations?limit=101').status_code,400)
        self.assertEqual(client.get('/vaccinations?offset=-1').status_code,400)
if __name__=='__main__': unittest.main()
