import copy
import unittest

from bountyguard.domain import GuardError
from bountyguard.github import GitHub


class Connector(GitHub):
    def __init__(self):
        super().__init__("unit-token")
        self.run={"id":100,"workflow_id":9,"head_sha":"a"*40,"event":"pull_request","path":".github/workflows/ci.yml","status":"completed","conclusion":"success","check_suite_id":8,"run_attempt":1,"pull_requests":[{"number":15,"head":{"sha":"a"*40},"base":{"sha":"b"*40}}]}
        self.job={"id":40,"name":"test","check_run_url":"https://api.github.com/repos/a/b/check-runs/20","status":"completed","conclusion":"success"}
        self.check={"app":{"id":15368,"slug":"github-actions"},"check_suite":{"id":8},"head_sha":"generated-merge-sha","status":"completed","conclusion":"success"}
    def pages(self,path,key=None,max_items=100):return [copy.deepcopy(self.job)] if "/jobs?" in path else [copy.deepcopy(self.run)]
    def request(self,path,body=None):return copy.deepcopy(self.check)


class GitHubTests(unittest.TestCase):
    def setUp(self):
        self.client=Connector()
        self.pr={"number":15,"head":{"sha":"a"*40},"base":{"sha":"b"*40}}
        self.policy={"workflow_id":9,"workflow_path":".github/workflows/ci.yml","app_id":15368,"required_checks":["test"]}
    def evidence(self):return self.client.ci_evidence("a/b",self.pr,self.policy)
    def test_generated_merge_sha_can_be_bound_through_run_suite_and_job(self):self.assertTrue(self.evidence()["passed"])
    def test_same_name_wrong_app_is_rejected(self):self.client.check["app"]["id"]=999;self.assertFalse(self.evidence()["passed"])
    def test_same_name_wrong_suite_is_rejected(self):self.client.check["check_suite"]["id"]=999;self.assertFalse(self.evidence()["passed"])
    def test_old_pr_head_cannot_reuse_green_run(self):self.client.run["head_sha"]="c"*40;self.assertFalse(self.evidence()["passed"])
    def test_old_base_cannot_reuse_green_run(self):self.client.run["pull_requests"][0]["base"]["sha"]="c"*40;self.assertFalse(self.evidence()["passed"])
    def test_pending_check_is_not_success(self):self.client.check["status"]="in_progress";self.assertFalse(self.evidence()["passed"])
    def test_skipped_check_is_not_success(self):self.client.check["conclusion"]="skipped";self.assertFalse(self.evidence()["passed"])
    def test_privileged_trigger_is_not_accepted(self):self.client.run["event"]="pull_request_target";self.assertFalse(self.evidence()["passed"])
    def test_changed_workflow_path_is_not_accepted(self):self.client.run["path"]=".github/workflows/other.yml";self.assertFalse(self.evidence()["passed"])
    def test_missing_required_check_is_not_success(self):self.client.job["name"]="lint";self.assertFalse(self.evidence()["passed"])


if __name__ == "__main__":unittest.main()
