from pathlib import Path
import base64
import json
import re
import tempfile
import time
import unittest

from fastapi.testclient import TestClient

from bountyguard.api import create_app
from bountyguard.auth import Sessions
from bountyguard.store import Store
from test_bounties import FakeGitHub, FakeRPC
from bountyguard.identity import b58encode, nep413_digest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


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

    def test_public_demo_links_to_recorded_paid_and_blocked_evidence(self):
        root = Path(__file__).resolve().parents[1]
        evidence = json.loads((root / "deployments/live-acceptance.json").read_text(encoding="utf-8"))
        self.assertIn('href="/assets/demo.html"', self.client.get("/").text)
        demo = self.client.get("/assets/demo.html")
        self.assertEqual(demo.status_code, 200)
        self.assertEqual(self.client.get("/assets/demo.css").status_code, 200)
        paid = evidence["primary_bounty"]
        rejected = evidence["adversarial"]
        rejected_review = rejected["observation"]["review"]
        self.assertTrue(rejected_review["ci"]["passed"])
        self.assertEqual(rejected_review["verdict"], "NEEDS_REVIEW")
        for value in (paid["payment_receipt"]["explorer_url"], paid["review"]["head_sha"], rejected["url"],
                      str(rejected_review["ci"]["run_id"]), rejected_review["head_sha"]):
            self.assertIn(value, demo.text)
        self.assertNotIn("<script", demo.text)
        self.assertEqual(self.client.get("/api/bounties").json(), [])
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

    def test_wallet_bundle_is_local_and_csp_nonce_is_fresh_and_matches(self):
        first=self.client.get('/');second=self.client.get('/')
        nonce=re.search(r'name="bg-csp-nonce" content="([^"]+)"',first.text).group(1)
        self.assertIn("'nonce-"+nonce+"'",first.headers['content-security-policy'])
        self.assertIn('nonce="'+nonce+'"',first.text)
        self.assertNotIn('__CSP_NONCE__',first.text)
        self.assertNotIn(nonce,second.text)
        self.assertNotIn("'unsafe-inline'",first.headers['content-security-policy'])
        self.assertNotIn("'unsafe-eval'",first.headers['content-security-policy'])
        self.assertEqual(self.client.get('/assets/wallet-bundle.js').status_code,200)

    def test_wallet_binding_status_requires_login_and_only_returns_own_roles(self):
        session=self.login()
        bounty=self.client.post('/api/bounties',json=self.create_body(),headers={'X-CSRF-Token':session['csrf']}).json()
        service=self.client.app.state.service
        key=Ed25519PrivateKey.generate()
        public='ed25519:'+b58encode(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw))
        service.rpc.keys[('owner.testnet',public)]='FullAccess'
        challenge=service.identity.challenge(bounty,session['actor'],'owner.testnet','maintainer')
        signature=base64.b64encode(key.sign(nep413_digest(challenge['message'],base64.b64decode(challenge['nonce']),challenge['recipient']))).decode()
        service.identity.verify(challenge['id'],session['actor'],public,signature)
        path='/api/bounties/'+bounty['id']+'/wallet/status'
        own=self.client.get(path).json()
        self.assertEqual(own['maintainer']['account'],'owner.testnet')
        self.assertIsNone(own['claimant'])
        self.assertNotIn('signature',own['maintainer'])
        self.client.post('/api/session',json={'token':'worker-token'})
        self.assertEqual(self.client.get(path).json(),{'maintainer':None,'claimant':None})
        self.client.cookies.clear()
        self.assertEqual(self.client.get(path).status_code,401)


if __name__=='__main__':unittest.main()
