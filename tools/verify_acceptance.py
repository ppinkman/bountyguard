"""Verify public acceptance evidence without a private key or model request."""
import argparse
import base64
import json
import os
from pathlib import Path
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bountyguard.domain import digest,diff_digest,github_url,issue_context,testnet_account
from bountyguard.github import GitHub
from bountyguard.identity import b58decode,nep413_digest
from bountyguard.near import NearRPC


def require(value,message):
    if not value:raise SystemExit('Verification failed: '+message)


def verify_agent_demo(receipt, rpc, github):
    deployment = json.loads((ROOT / 'deployments/testnet.json').read_text(encoding='utf-8'))
    contract = receipt['contract']
    require(contract == deployment['contract'] and rpc.account(contract)['code_hash'] == deployment['code_hash'],
            'unexpected testnet contract or code hash')
    identifier = receipt['bounty_id']
    chain = rpc.view(contract, 'get_bounty', {'id': identifier})
    expected = {
        'status': 'Paid', 'claimant': receipt['claimant'], 'maintainer': receipt['maintainer'],
        'github_user_id': str(receipt['actor_id']), 'repo_id': str(receipt['repo_id']),
        'amount': receipt['amount_yocto'], 'terms_hash': receipt['assigned_terms_hash'],
        'delivery_hash': receipt['delivery_hash'], 'report_hash': receipt['report_hash'],
    }
    require(chain and all(chain.get(key) == value for key, value in expected.items()), 'on-chain bounty differs')
    tx = rpc.call('tx', {'tx_hash': receipt['transaction_hash'], 'sender_account_id': testnet_account(receipt['maintainer']),
                        'wait_until': 'FINAL'})
    transaction = tx['transaction']
    require(tx['final_execution_status'] == 'FINAL' and 'SuccessValue' in tx['status']
            and transaction['hash'] == receipt['transaction_hash']
            and transaction['signer_id'] == receipt['maintainer'] and transaction['receiver_id'] == contract
            and len(transaction['actions']) == 1, 'payment transaction did not finalize as recorded')
    call = transaction['actions'][0]['FunctionCall']
    require(call['method_name'] == 'pay' and json.loads(base64.b64decode(call['args'], validate=True)) == {
        'id': identifier, 'expected_delivery_hash': receipt['delivery_hash'], 'expected_report_hash': receipt['report_hash'],
    }, 'payment transaction was for different evidence')
    repo, pr_number = github_url(receipt['pr_url'], 'pull')
    issue_repo, issue_number = github_url(receipt['issue_url'], 'issues')
    require(repo.lower() == issue_repo.lower() and str(issue_number) == chain['issue_number']
            and receipt['actor_id'] != receipt['maintainer_id'], 'issue or distinct account evidence differs')
    issue = github.issue(repo, issue_number)
    require(digest(issue_context(issue, receipt['repo_id'])) == receipt['issue_hash'], 'Issue terms changed')
    pr, files = github.pr_snapshot(repo, pr_number)
    head = receipt['head_sha']
    require(pr['merged'] and pr['user']['id'] == receipt['actor_id']
            and pr['base']['repo']['id'] == receipt['repo_id'] and pr['head']['sha'] == head
            and pr['merge_commit_sha'] == receipt['merge_sha'], 'PR author, revision or merge differs')
    require(digest({'pr_number': pr_number, 'head_sha': head, 'diff_hash': diff_digest(files)})
            == receipt['delivery_hash'], 'PR diff differs from paid delivery')
    run = github.request(f"/repos/{repo}/actions/runs/{int(receipt['ci_run_id'])}/attempts/{int(receipt['run_attempt'])}")
    require(run['head_sha'] == head and run['workflow_id'] == receipt['workflow_id']
            and run['event'] == 'pull_request' and run['status'] == 'completed'
            and run['conclusion'] == 'success', 'recorded CI attempt differs')
    print(json.dumps({'verified': True, 'bounty_id': identifier, 'pr_url': receipt['pr_url'],
                      'head_sha': head, 'transaction_hash': receipt['transaction_hash'],
                      'scope': 'Public revision, CI attempt, final payment and chain state. Local runner events are operator records.'}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt',type=Path,default=ROOT/'deployments/live-acceptance.json')
    args=parser.parse_args();receipt=json.loads(args.receipt.read_text(encoding='utf-8'))
    if receipt.get('schema') == 'bountyguard/agent-demo/v1':
        return verify_agent_demo(receipt, NearRPC(), GitHub(os.getenv('GITHUB_TOKEN')))
    deployment=receipt['deployment'];rpc=NearRPC();account=rpc.account(deployment['contract'])
    require(account['code_hash']==deployment['code_hash'],'contract code hash changed')
    chains={};verified_revisions=[];checked_keys={}
    targets=[('primary_bounty','Paid'),('refunded_bounty','Refunded')]
    if 'agent_bounty' in receipt:targets.append(('agent_bounty','Paid'))
    github=GitHub(os.getenv('GITHUB_TOKEN'))
    for key,state in targets:
        bounty=receipt[key];chain=rpc.view(deployment['contract'],'get_bounty',{'id':bounty['id']})
        require(chain is not None and chain['status']==state,'unexpected chain bounty state')
        expected={'maintainer':bounty['maintainer_account'],'claimant':bounty['claim']['near_account_id'],'terms_hash':bounty['assigned_terms_hash'],'amount':bounty['amount_yocto'],'repo_id':str(bounty['repo_id']),'github_user_id':str(bounty['claim']['actor_id']),'issue_number':bounty['issue_number'],'deadline_ns':str(bounty['deadline']*10**9)}
        require(all(chain[k]==v for k,v in expected.items()),'chain identity, reward or terms mismatch')
        proofs=receipt['identity_proofs'][bounty['id']]
        require(set(proofs)=={'maintainer','claimant'},'both role proofs are required')
        require(bounty['claim']['binding_hash']==digest(proofs['claimant']),'claim wallet binding hash mismatch')
        require(bounty['assigned_terms_hash']==digest({'terms_hash':bounty['terms_hash'],'claim':bounty['claim'],'maintainer_account':bounty['maintainer_account']}),'assigned terms hash mismatch')
        for role,proof in proofs.items():
            context=json.loads(proof['message'])
            expected_id=bounty['creator_id'] if role=='maintainer' else bounty['claim']['actor_id']
            expected_account=bounty['maintainer_account'] if role=='maintainer' else bounty['claim']['near_account_id']
            require(context['bounty_id']==bounty['id'] and context['github_user_id']==expected_id and context['near_account_id']==expected_account and context['purpose']==role and context['repo']==bounty['repo'] and context['repo_id']==bounty['repo_id'] and context['issue_number']==bounty['issue_number'] and context['terms_hash']==bounty['terms_hash'] and context['network']=='testnet' and context['application']=='BountyGuard','wallet proof context mismatch')
            Ed25519PublicKey.from_public_bytes(b58decode(proof['public_key'].split(':')[1])).verify(base64.b64decode(proof['signature'],validate=True),nep413_digest(proof['message'],base64.b64decode(proof['nonce']),proof['recipient'],proof.get('callback_url')))
            key_pair=(expected_account,proof['public_key'])
            if key_pair not in checked_keys:
                checked_keys[key_pair]=rpc.access_key(*key_pair)
            require(checked_keys[key_pair]['permission']=='FullAccess','proof key is not currently on the account')
        chains[key]={'id':bounty['id'],'status':chain['status'],'transfer_nonce':chain['transfer_nonce'],'amount':chain['amount']}
        if state=='Paid':
            report=bounty['review']
            require(report['report_hash']==digest({k:v for k,v in report.items() if k!='report_hash'}),'off-chain review hash mismatch')
            require(report['delivery_hash']==digest({k:report[k] for k in ('pr_number','head_sha','diff_hash')}),'delivery hash mismatch')
            require(chain['delivery_hash']==report['delivery_hash'] and chain['report_hash']==report['report_hash'],'chain evidence differs from receipt')
            repo,number=github_url(bounty['pr_url'],'pull')
            pr=github.request(f'/repos/{repo}/pulls/{number}')
            files=github.pages(f'/repos/{repo}/pulls/{number}/files',max_items=40)
            require(pr['merged'] and pr['head']['sha']==report['head_sha'] and pr['user']['id']==bounty['claim']['actor_id'],'GitHub revision/author/merge mismatch')
            require(len(files)==pr['changed_files'] and diff_digest(files)==report['diff_hash'],'GitHub diff mismatch or incomplete file list')
            issue=github.issue(repo,bounty['issue_number'])
            require(digest(issue_context(issue,bounty['repo_id']))==bounty['issue_hash'],'Issue terms changed')
            verified_revisions.append({'github_pr':bounty['pr_url'],'head_sha':report['head_sha']})
    print(json.dumps({'verified':True,'contract':deployment['contract'],'code_hash':account['code_hash'],'chain_states':chains,**verified_revisions[0],'github_revisions':verified_revisions,'wallet_signatures_verified':2*len(targets),'scope':'Pinned code, on-chain terms/states, recorded wallet signatures/current key membership and GitHub revision. Not proof of code correctness, AI correctness, historical key membership, nonce consumption, authorship by a particular model or independent commercial participation.'}))


if __name__=='__main__':main()
