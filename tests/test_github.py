import copy
import unittest

from bountyguard.domain import GuardError
from bountyguard.github import GitHub, REVISION_JOB_DECLARATION


class Connector(GitHub):
    def __init__(self):
        super().__init__("unit-token")
        self.run={"id":100,"workflow_id":9,"head_sha":"a"*40,"event":"pull_request","path":".github/workflows/ci.yml","status":"completed","conclusion":"success","check_suite_id":8,"run_attempt":1,"pull_requests":[{"number":15,"head":{"sha":"a"*40},"base":{"sha":"b"*40}}]}
        self.job={"id":40,"name":"test","check_run_url":"https://api.github.com/repos/a/b/check-runs/20","status":"completed","conclusion":"success"}
        self.check={"app":{"id":15368,"slug":"github-actions"},"check_suite":{"id":8},"head_sha":"generated-merge-sha","status":"completed","conclusion":"success"}
        self.extra_jobs = []
        self.extra_checks = {}
        self.workflow_files = {}
        self.job_path = None

    def pages(self, path, key=None, max_items=100):
        if path.endswith("/jobs"):
            self.job_path = path
            return copy.deepcopy([self.job, *self.extra_jobs])
        return [copy.deepcopy(self.run)]

    def request(self, path, body=None):
        return copy.deepcopy(self.extra_checks.get(path.rsplit("/", 1)[-1], self.check))

    def file(self, repo, path, ref):
        return self.workflow_files[(repo, ref)]


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

    def test_merged_projection_can_use_the_exact_premerge_run(self):
        accepted=self.evidence();self.client.run['pull_requests']=[];self.pr['merged']=True
        self.assertTrue(self.client.ci_evidence('a/b',self.pr,self.policy,accepted=accepted)['passed'])

    def test_empty_projection_before_merge_still_fails(self):
        accepted=self.evidence();self.client.run['pull_requests']=[]
        result=self.client.ci_evidence('a/b',self.pr,self.policy,accepted=accepted)
        self.assertFalse(result['passed'])
        self.assertTrue(result['association_missing'])

    def test_cached_green_cannot_hide_a_new_failure(self):
        accepted=self.evidence();self.client.run['pull_requests']=[];self.pr['merged']=True;self.client.check['conclusion']='failure'
        self.assertFalse(self.client.ci_evidence('a/b',self.pr,self.policy,accepted=accepted)['passed'])

    def test_different_attempt_requires_another_review(self):
        accepted=self.evidence();self.client.run['pull_requests']=[];self.pr['merged']=True;self.client.run['run_attempt']=2
        self.assertFalse(self.client.ci_evidence('a/b',self.pr,self.policy,accepted=accepted)['passed'])

    def test_a_different_run_cannot_borrow_an_old_association(self):
        accepted=self.evidence();self.client.run['pull_requests']=[];self.pr['merged']=True;self.client.run['id']=101
        self.assertFalse(self.client.ci_evidence('a/b',self.pr,self.policy,accepted=accepted)['passed'])

    def add_fork_binding(self):
        self.pr["head"]["repo"] = {"id": 50, "full_name": "worker/b"}
        self.pr["base"]["repo"] = {"id": 60, "full_name": "a/b"}
        self.client.run.update(pull_requests=[], repository={"id": 60}, head_repository={"id": 50})
        self.policy["workflow_blob_sha"] = "pinned-blob"
        self.client.workflow_files = {
            ("a/b", "b" * 40): {"sha": "pinned-blob", "content": REVISION_JOB_DECLARATION},
            ("worker/b", "a" * 40): {"sha": "pinned-blob", "content": REVISION_JOB_DECLARATION},
        }
        job = {**self.client.job, "id": 41, "name": "BountyGuard PR 15 base " + "b" * 40,
               "run_id": 100, "head_sha": "a" * 40,
               "check_run_url": "https://api.github.com/repos/a/b/check-runs/21"}
        self.client.extra_jobs = [job]
        self.client.extra_checks = {"21": {**self.client.check, "head_sha": "a" * 40}}
        return job

    def test_fork_job_binds_missing_pr_projection(self):
        self.add_fork_binding()
        evidence = self.evidence()
        self.assertTrue(evidence["passed"])
        self.assertEqual(evidence["revision_job"]["job_id"], 41)
        self.assertEqual(self.client.job_path, "/repos/a/b/actions/runs/100/attempts/1/jobs")

    def test_fork_job_cannot_use_old_base_or_another_pr(self):
        job = self.add_fork_binding()
        for name in ("BountyGuard PR 15 base " + "c" * 40, "BountyGuard PR 12 base " + "b" * 40):
            with self.subTest(name=name):
                job["name"] = name
                self.assertFalse(self.evidence()["passed"])

    def test_fork_job_must_match_pinned_workflow_on_both_sides(self):
        self.add_fork_binding()
        for key in (("worker/b", "a" * 40), ("a/b", "b" * 40)):
            with self.subTest(key=key):
                document = self.client.workflow_files[key]
                self.client.workflow_files[key] = {**document, "sha": "different"}
                self.assertFalse(self.evidence()["passed"])
                self.client.workflow_files[key] = document
        self.client.workflow_files[("a/b", "b" * 40)]["content"] = "unrelated workflow"
        self.assertFalse(self.evidence()["passed"])

    def test_fork_job_rejects_wrong_run_repository_or_check_suite(self):
        job = self.add_fork_binding()
        job["run_id"] = 101
        self.assertFalse(self.evidence()["passed"])
        job["run_id"] = 100
        self.client.run["head_repository"] = {"id": 900}
        self.assertFalse(self.evidence()["passed"])
        self.client.run["head_repository"] = {"id": 50}
        self.client.extra_checks["21"]["check_suite"] = {"id": 900}
        self.assertFalse(self.evidence()["passed"])

    def test_fork_job_must_be_unique(self):
        job = self.add_fork_binding()
        self.client.extra_jobs.append(dict(job, id=45))
        self.assertFalse(self.evidence()["passed"])

    def test_merge_rechecks_original_fork_job_and_run_attempt(self):
        job = self.add_fork_binding()
        accepted = self.evidence()
        self.pr["merged"] = True
        self.assertTrue(self.client.ci_evidence("a/b", self.pr, self.policy, accepted)["passed"])
        job["id"] = 45
        self.assertFalse(self.client.ci_evidence("a/b", self.pr, self.policy, accepted)["passed"])
        job["id"] = 41
        self.client.run["run_attempt"] = 2
        self.assertFalse(self.client.ci_evidence("a/b", self.pr, self.policy, accepted)["passed"])


if __name__ == "__main__":unittest.main()
