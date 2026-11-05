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
from bountyguard.domain import digest,diff_digest,github_url,issue_context
from bountyguard.github import GitHub
from bountyguard.identity import b58decode,nep413_digest
from bountyguard.near import NearRPC


def require(value,message):
    if not value:raise SystemExit('Verification failed: '+message)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt',type=Path,default=ROOT/'deployments/live-acceptance.json')
    args=parser.parse_args();receipt=json.loads(args.receipt.read_text(encoding='utf-8'))
    deployment=receipt['deployment'];rpc=NearRPC();account=rpc.account(deployment['contract'])
    require(account['code_hash']==deployment['code_hash'],'contract code hash changed')
    chains={};verified_revisions=[]
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
            require(rpc.access_key(expected_account,proof['public_key'])['permission']=='FullAccess','proof key is not currently on the account')
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
