import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bountyguard.domain import GuardError
from bountyguard.identity import b58encode
from bountyguard.near import TestnetSigner,make_key
from bountyguard.store import Store


class RPC:
    def __init__(self):self.sends=0;self.wrong=False;self.result=None
    def account(self,account):return {'code_hash':'pinned'}
    def access_key(self,account,key):return {'nonce':1,'block_hash':b58encode(bytes([8])*32)}
    def call(self,method,args):
        if method=='send_tx':
            self.sends+=1;raw=base64.b64decode(args['signed_tx_base64']);txhash=b58encode(hashlib.sha256(raw[:-65]).digest())
            self.result={'final_execution_status':'FINAL','transaction':{'hash':txhash,'receiver_id':'contract.testnet','signer_id':'owner.testnet'},'status':{'SuccessValue':''}}
        result=json.loads(json.dumps(self.result))
        if self.wrong:result['transaction']['hash']='wrong-original-hash'
        return result


class SignerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'journal.sqlite3');self.rpc=RPC()
        self.vault={'account_id':'owner.testnet',**make_key()}
        self.env=patch.dict(os.environ,{'BOUNTYGUARD_ENABLE_TESTNET':'1'});self.env.start()
        self.secret=patch('bountyguard.near.load_vault',return_value=self.vault);self.secret.start()
        self.protect=patch('bountyguard.near.protect',side_effect=lambda raw,decrypt=False:raw);self.protect.start()
        self.signer=TestnetSigner(self.store,self.rpc,'contract.testnet','not-a-real-vault.dpapi','pinned')
    def tearDown(self):self.protect.stop();self.secret.stop();self.env.stop();self.temp.cleanup()
    def send(self,operation='b:fund',bounty='b'):return self.signer.execute(operation,bounty,'owner.testnet','fund_assigned',{'id':bounty},1)
    def test_confirmed_original_transaction_is_reused_after_restart(self):
        first=self.send();second=TestnetSigner(Store(self.store.path),self.rpc,'contract.testnet','unused','pinned').execute('b:fund','b','owner.testnet','fund_assigned',{'id':'b'},1)
        self.assertEqual(first,second);self.assertEqual(self.rpc.sends,1)
    def test_wrong_transaction_hash_cannot_confirm_and_is_not_resent(self):
        self.rpc.wrong=True
        with self.assertRaises(GuardError):self.send()
        with self.assertRaises(GuardError):self.send()
        self.assertEqual(self.rpc.sends,1)
        self.rpc.wrong=False;receipt=self.signer.reconcile('b:fund')
        self.assertIn('transaction_hash',receipt);self.assertEqual(self.rpc.sends,1)
    def test_code_upgrade_blocks_signing(self):
        self.signer.code_hash='different'
        with self.assertRaises(GuardError):self.send()
        self.assertEqual(self.rpc.sends,0)
    def test_mainnet_or_unbounded_operations_are_not_available(self):
        with self.assertRaises(GuardError):TestnetSigner(self.store,self.rpc,'contract.near','unused','pinned')
        with self.assertRaises(GuardError):self.signer.execute('x','b','owner.testnet','arbitrary_method',{},0)
        with self.assertRaises(GuardError):self.signer.execute('x','b','owner.testnet','pay',{},10**24)
        self.assertEqual(self.rpc.sends,0)
    def test_two_funding_intents_are_enforced_before_a_third_signature(self):
        self.send('a:fund','a');self.send('b:fund','b')
        with self.assertRaises(GuardError):self.send('c:fund','c')
        self.assertEqual(self.rpc.sends,2)
    def test_unsigned_preparation_can_be_reconciled_without_broadcast(self):
        self.store.operation('x','b','pay',{'signer':'owner.testnet'})
        result=self.signer.reconcile('x')
        self.assertEqual(result['state'],'NOT_SIGNED');self.assertEqual(self.rpc.sends,0)


if __name__=='__main__':unittest.main()
