import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bountyguard.domain import GuardError
from bountyguard.review import Reviewer
from bountyguard.store import Store


class Response(io.BytesIO):
    headers={}
    def __init__(self,value):super().__init__(json.dumps(value).encode())


class Transport:
    def __init__(self):self.calls=0;self.quote="+return 2";self.fail=False;self.price="0.000001"
    def open(self,request,timeout=20):
        if isinstance(request,str):return Response({"data":[{"id":"Qwen/Qwen3.6-35B-A3B-FP8","pricing":{"prompt":self.price,"completion":"0.000001","request":"0"}}]})
        self.calls+=1
        if self.fail:raise TimeoutError()
        report={"verdict":"PASS","summary":"Bounded review.","findings":[{"evidence_id":"F1L3" if self.quote=="+return 2" else "unknown-id","severity":"LOW","reason":"Changed return."}]}
        return Response({"model":"test-model","usage":{"total_tokens":42},"choices":[{"finish_reason":"stop","message":{"content":json.dumps(report)}}]})


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/"state.sqlite3");self.transport=Transport()
        self.context={"files":[{"filename":"src/a.py","patch":"@@ -1 +1 @@\n-return 1\n+return 2"}]}
        self.env=patch.dict(os.environ,{"BOUNTYGUARD_ENABLE_AI":"1","NEAR_AI_API_KEY":"unit-test-key"});self.env.start()
        self.network=patch("bountyguard.review.opener",return_value=self.transport);self.network.start()
    def tearDown(self):self.network.stop();self.env.stop();self.temp.cleanup()
    def test_repeated_revision_reuses_original_model_result(self):
        reviewer=Reviewer(self.store);one=reviewer.review("a"*64,self.context);two=reviewer.review("a"*64,self.context)
        self.assertEqual(one,two);self.assertEqual(self.transport.calls,1)
    def test_unknown_request_is_not_paid_again(self):
        self.transport.fail=True;reviewer=Reviewer(self.store)
        with self.assertRaises(GuardError):reviewer.review("a"*64,self.context)
        self.transport.fail=False
        with self.assertRaises(GuardError):reviewer.review("a"*64,self.context)
        self.assertEqual(self.transport.calls,1)
    def test_invented_code_citation_is_not_a_valid_review(self):
        self.transport.quote="not in patch"
        with self.assertRaises(GuardError):Reviewer(self.store).review("a"*64,self.context)
    def test_daily_intent_cap_survives_restart(self):
        for i in range(3):Reviewer(self.store).review(str(i)*64,self.context)
        with self.assertRaises(GuardError):Reviewer(Store(self.store.path)).review("f"*64,self.context)
        self.assertEqual(self.transport.calls,3)
    def test_price_cap_precedes_model_request(self):
        self.transport.price="1"
        with self.assertRaises(GuardError):Reviewer(self.store).review("a"*64,self.context)
        self.assertEqual(self.transport.calls,0)


if __name__=="__main__":unittest.main()
