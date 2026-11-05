"""Read actual public GitHub evidence; never creates a bounty or signs a transaction."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bountyguard.domain import GuardError, digest, github_url
from bountyguard.github import GitHub
from bountyguard.review import Reviewer
from bountyguard.store import Store


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',default='pallets/flask')
    parser.add_argument('--pr')
    parser.add_argument('--use-model',action='store_true')
    parser.add_argument('--index',type=Path,default=ROOT/'artifacts/live-inspection.json')
    args=parser.parse_args()
    token=os.getenv('GITHUB_TOKEN')
    if not token:
        token=subprocess.check_output(['gh','auth','token'],stderr=subprocess.DEVNULL,text=True).strip()
    github=GitHub(token)
    actor=github.me()
    if args.pr:
        repo,number=github_url(args.pr,'pull');candidates=[{'number':number}]
    else:
        repo=args.repo
        if not __import__('re').fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):raise SystemExit('Invalid repository.')
        candidates=github.request(f'/repos/{repo}/pulls?state=closed&per_page=8&sort=updated&direction=desc')
    selected=None;skipped=[]
    for candidate in candidates:
        try:
            pr,files=github.pr_snapshot(repo,candidate['number'])
            if not any(f['filename'].endswith('.py') for f in files):continue
            linked=github.closes_issue(repo,pr['number'],0)
            selected=(pr,files,linked);break
        except GuardError as exc:skipped.append({'number':candidate['number'],'reason':str(exc)})
    if selected is None:raise SystemExit('No bounded Python PR found. Specify --pr. No model request was made.')
    pr,files,linked=selected
    issue=None
    for reference in linked:
        if reference['repository']['databaseId']==pr['base']['repo']['id']:
            issue=github.issue(repo,reference['number']);break
    context={'issue':{'title':issue['title'],'body':issue.get('body') or ''} if issue else {'title':pr['title'],'body':pr.get('body') or '', 'source':'PR description; no linked Issue was available'},'repo':repo,'pr_number':pr['number'],'head_sha':pr['head']['sha'],'base_sha':pr['base']['sha'],'diff_hash':digest(files),'files':files}
    evidence={'scope':'Read-only inspection of an existing public third-party PR; not a funded bounty, endorsement, independent customer or security certification.','authenticated_reader_id':actor['id'],'pr_url':pr['html_url'],'repo_id':pr['base']['repo']['id'],'author_id':pr['user']['id'],'merged':pr['merged'],'linked_issue_url':issue['html_url'] if issue else None,'context':context,'skipped_candidates':skipped}
    args.index.parent.mkdir(parents=True,exist_ok=True)
    if args.index.exists():
        existing=json.loads(args.index.read_text(encoding='utf-8'))
        if existing.get('context',{}).get('head_sha')!=context['head_sha']:
            raise SystemExit('The evidence index already names another revision; choose a new index explicitly.')
    args.index.write_text(json.dumps(evidence,indent=2,ensure_ascii=False),encoding='utf-8')
    if args.use_model:
        # Reuse the application's single persistent credit-intent counter.
        reviewer=Reviewer(Store(ROOT/'data/bountyguard.sqlite3'))
        evidence['ai']=reviewer.review(digest({'mode':'public-pr-inspection/v1','context':context}),context)
        args.index.write_text(json.dumps(evidence,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'pr_url':evidence['pr_url'],'head_sha':context['head_sha'],'changed_files':len(files),'linked_issue_url':evidence['linked_issue_url'],'model_verdict':evidence.get('ai',{}).get('verdict'),'usage':evidence.get('ai',{}).get('usage'),'index':str(args.index)},ensure_ascii=True))


if __name__=='__main__':main()
