"""Trigger the existing maintainer settlement for one reviewed testnet revision."""
import argparse
import json
import os

from bountyguard.domain import GuardError
from bountyguard.github import GitHub
from tools.agent_demo import payment
from tools.agent_wallet import DemoError, LocalAPI, checked_id
from tools.agent_workspace import SHA


def settle(api, github, bounty_id, expected_head, token, confirm=input):
    identifier = checked_id(bounty_id)
    if not SHA.fullmatch(expected_head):
        raise DemoError("Use the exact 40-character reviewed head SHA.")
    path = "bounties/" + identifier
    actor = api.login(token)
    bounty = api.call(path)
    review = bounty.get("review") or {}
    if (bounty["network"] != "testnet" or actor["id"] != bounty["creator_id"]
            or review.get("head_sha") != expected_head or review.get("verdict") != "PASS"):
        raise DemoError("Maintainer identity, testnet or approved revision does not match.")
    if bounty["state"] == "PAID":
        return payment(bounty, expected_head)
    if bounty["state"] != "READY_TO_MERGE":
        raise DemoError("Bounty is not ready. Use the existing recovery flow if settlement is uncertain.")
    pr = github.request(f"/repos/{bounty['repo']}/pulls/{int(bounty['pr_number'])}")
    print(json.dumps({"reviewed_head": expected_head, "current_head": pr["head"]["sha"],
                      "merged": pr["merged"], "bounty_id": identifier, "amount_tnear": bounty["amount"]}))
    if not pr["merged"] or pr["head"]["sha"] != expected_head:
        raise DemoError("The reviewed head must be the merged revision.")
    if confirm("Type yes to request testnet settlement: ") != "yes":
        raise DemoError("Settlement was not requested.")
    # Check again after the human pause. The existing sync handler independently
    # validates the review, live PR, merge ancestry and CI before the signer runs.
    latest = api.call(path)
    if (latest.get("review") or {}).get("report_hash") != review["report_hash"]:
        raise DemoError("The review changed during confirmation. Inspect the new revision.")
    return payment(api.call(path + "/sync", {}), expected_head)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bounty", required=True)
    parser.add_argument("--expect-head", required=True)
    args = parser.parse_args()
    token = os.environ.get("BOUNTYGUARD_MAINTAINER_GITHUB_TOKEN")
    if not token or token == os.environ.get("BOUNTYGUARD_AGENT_GITHUB_TOKEN"):
        parser.exit(1, "Use a separate maintainer shell and its explicit GitHub credential.\n")
    api = LocalAPI()
    try:
        print(json.dumps(settle(api, GitHub(token), args.bounty, args.expect_head, token)))
    except (DemoError, GuardError, EOFError, KeyError, TypeError) as exc:
        parser.exit(1, (str(exc) if isinstance(exc, DemoError) else "Settlement stopped; inspect the current bounty state.") + "\n")
    finally:
        api.close()


if __name__ == "__main__":
    main()
