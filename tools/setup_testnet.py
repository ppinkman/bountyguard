"""Create independent free testnet development accounts, or deploy this WASM.

All keys stay in CurrentUser DPAPI vaults. Existing ambiguous requests are never
silently replaced with a new identity or new signed deployment transaction.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import secrets
import struct
import sys
import urllib.request

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bountyguard.domain import GuardError, canonical
from bountyguard.github import opener
from bountyguard.identity import b58decode,b58encode,borsh_string
from bountyguard.near import NearRPC,FAUCET_URL,make_key,save_vault,load_vault,protect

DIRECTORY=ROOT/'data/testnet'


def save(path,value):
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,indent=2),encoding='utf-8');temporary.replace(path)


def create_accounts(rpc):
    DIRECTORY.mkdir(parents=True,exist_ok=True)
    index=DIRECTORY/'accounts.json'
    if index.exists():
        accounts=json.loads(index.read_text(encoding='utf-8'))
    else:
        prefix='bg-'+secrets.token_hex(4)
        accounts={role:{'account_id':prefix+'-'+suffix+'.testnet','state':'CREATED_LOCALLY'} for role,suffix in [('maintainer','owner'),('claimant','worker'),('contract','escrow')]}
        for role,record in accounts.items():
            key=make_key();record['public_key']=key['public_key'];save_vault(DIRECTORY/(role+'.dpapi'),{**key,'account_id':record['account_id']})
        save(index,accounts)
    for role,record in accounts.items():
        if record['state']!='CREATED_LOCALLY':
            try:
                key=rpc.access_key(record['account_id'],record['public_key'])
                if key['permission']=='FullAccess':record['state']='VERIFIED_ON_CHAIN';save(index,accounts);continue
            except GuardError:pass
            if record['state']!='VERIFIED_ON_CHAIN':
                raise GuardError('Original faucet result is uncertain for '+role+'. Inspect the existing account; no duplicate account request was made.')
        record['state']='FAUCET_REQUESTED';save(index,accounts)
        request=urllib.request.Request(FAUCET_URL,data=canonical({'newAccountId':record['account_id'],'newAccountPublicKey':record['public_key']}).encode(),headers={'Content-Type':'application/json'})
        with opener().open(request,timeout=30) as response:response.read(100_000)
        key=rpc.access_key(record['account_id'],record['public_key'])
        if key['permission']!='FullAccess':raise GuardError('Faucet account key did not match.')
        record['state']='VERIFIED_ON_CHAIN';save(index,accounts)
    print(json.dumps({'network':'testnet','accounts':accounts}))


def deploy(rpc):
    vault=load_vault(DIRECTORY/'contract.dpapi');account=vault['account_id']
    wasm=ROOT/'contracts/bounty/target/wasm32-unknown-unknown/release/bountyguard_contract.wasm'
    code=wasm.read_bytes();expected=b58encode(hashlib.sha256(code).digest())
    operation_path=DIRECTORY/'deploy-operation.json'
    if operation_path.exists():
        operation=json.loads(operation_path.read_text(encoding='utf-8'))
        if operation['code_hash']!=expected:raise GuardError('A deployment intent already names another build; inspect it before upgrading.')
        result=rpc.call('tx',{'tx_hash':operation['transaction_hash'],'sender_account_id':account,'wait_until':'FINAL'})
    else:
        key=rpc.access_key(account,vault['public_key'])
        deploy_action=b'\x01'+struct.pack('<I',len(code))+code
        arguments=b'{}'
        init_action=b'\x02'+borsh_string('new')+struct.pack('<I',len(arguments))+arguments+struct.pack('<Q',40_000_000_000_000)+(0).to_bytes(16,'little')
        raw=borsh_string(account)+b'\0'+b58decode(vault['public_key'].split(':')[1])+struct.pack('<Q',key['nonce']+1)+borsh_string(account)+b58decode(key['block_hash'])+struct.pack('<I',2)+deploy_action+init_action
        private=Ed25519PrivateKey.from_private_bytes(base64.b64decode(vault['seed']))
        transaction_hash=b58encode(hashlib.sha256(raw).digest());signed=raw+b'\0'+private.sign(hashlib.sha256(raw).digest())
        operation={'transaction_hash':transaction_hash,'code_hash':expected,'contract':account,'signed_dpapi':base64.b64encode(protect(signed)).decode()}
        save(operation_path,operation)
        result=rpc.call('send_tx',{'signed_tx_base64':base64.b64encode(signed).decode(),'wait_until':'FINAL'})
    if result.get('final_execution_status')!='FINAL' or result.get('transaction',{}).get('hash')!=operation['transaction_hash'] or 'SuccessValue' not in result.get('status',{}):raise GuardError('Original deployment is not confirmed. Keep its existing transaction hash.')
    chain=rpc.account(account)
    if chain['code_hash']!=expected:raise GuardError('On-chain code hash does not match the compiled WASM.')
    operation['result']=result;save(operation_path,operation)
    config={'contract':account,'code_hash':expected,'wasm_sha256':hashlib.sha256(code).hexdigest(),'transaction_hash':operation['transaction_hash'],'network':'testnet'}
    save(DIRECTORY/'deployment.json',config)
    print(json.dumps(config))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['create-free-accounts','deploy'])
    args=parser.parse_args();rpc=NearRPC();rpc.assert_testnet()
    if args.action=='create-free-accounts':create_accounts(rpc)
    else:deploy(rpc)


if __name__=='__main__':main()
