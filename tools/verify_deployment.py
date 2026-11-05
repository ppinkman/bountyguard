"""Read-only testnet code-hash verification. No vault, signer or completion call."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bountyguard.near import NearRPC


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deployment',type=Path,default=ROOT/'deployments/testnet.json')
    parser.add_argument('--bounty')
    args=parser.parse_args();config=json.loads(args.deployment.read_text(encoding='utf-8'))
    rpc=NearRPC();account=rpc.account(config['contract'])
    if account['code_hash']!=config['code_hash']:raise SystemExit('Code hash does not match the pinned deployment.')
    result={'network':'testnet','contract':config['contract'],'code_hash':account['code_hash'],'block_height':account['block_height'],'block_hash':account['block_hash'],'verified':True}
    if args.bounty:result['bounty']=rpc.view(config['contract'],'get_bounty',{'id':args.bounty})
    print(json.dumps(result))


if __name__=='__main__':main()
