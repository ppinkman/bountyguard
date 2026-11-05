from pathlib import Path
import tempfile
import time
import unittest

from fastapi.testclient import TestClient

from bountyguard.api import create_app
from bountyguard.auth import Sessions
from bountyguard.store import Store
from test_bounties import FakeGitHub, FakeRPC


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'api.sqlite3')
        self.client=TestClient(create_app(self.store,FakeRPC(),sessions=Sessions(FakeGitHub)))
    def tearDown(self):self.client.close();self.temp.cleanup()
    def login(self):
        result=self.client.post('/api/session',json={'token':'owner-token'})
        self.assertEqual(result.status_code,200)
        return result.json()
    def create_body(self):return {'issue_url':'https://github.com/maintainer/demo/issues/12','deadline':int(time.time())+3600,'required_checks':['test']}
    def test_english_page_and_language_switch_asset(self):
        page=self.client.get('/');self.assertEqual(page.status_code,200)
        self.assertIn('<html lang="en">',page.text)
        self.assertIn('Content-Security-Policy',page.headers)
        self.assertEqual(self.client.get('/assets/app.js').status_code,200)
    def test_unauthenticated_mutation_is_refused(self):self.assertEqual(self.client.post('/api/bounties',json=self.create_body()).status_code,401)
    def test_cookie_write_needs_csrf_and_origin(self):
        session=self.login()
        self.assertEqual(self.client.post('/api/bounties',json=self.create_body()).status_code,403)
        result=self.client.post('/api/bounties',json=self.create_body(),headers={'X-CSRF-Token':session['csrf'],'Origin':'https://evil.test'})
        self.assertEqual(result.status_code,403)
        good=self.client.post('/api/bounties',json=self.create_body(),headers={'X-CSRF-Token':session['csrf']})
        self.assertEqual(good.status_code,200);self.assertEqual(good.json()['state'],'DRAFT')
    def test_local_login_is_not_enabled_by_default(self):self.assertEqual(self.client.post('/api/session/local',json={}).status_code,403)
    def test_session_has_http_only_cookie_and_logout_revokes_it(self):
        response=self.client.post('/api/session',json={'token':'owner-token'});session=response.json()
        self.assertIn('HttpOnly',response.headers['set-cookie']);self.assertIn('SameSite=strict',response.headers['set-cookie'])
        self.assertEqual(self.client.post('/api/logout',json={},headers={'X-CSRF-Token':session['csrf']}).status_code,200)
        self.assertEqual(self.client.get('/api/session').status_code,401)
    def test_private_key_fields_are_not_accepted_by_wallet_endpoint(self):
        session=self.login()
        bounty=self.client.post('/api/bounties',json=self.create_body(),headers={'X-CSRF-Token':session['csrf']}).json()
        result=self.client.post('/api/bounties/'+bounty['id']+'/wallet/verify',json={'challenge_id':'x','public_key':'x','signature':'x','private_key':'never-accept'},headers={'X-CSRF-Token':session['csrf']})
        self.assertEqual(result.status_code,422)


if __name__=='__main__':unittest.main()
