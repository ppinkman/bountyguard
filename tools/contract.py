"""Build this project's contract, using an explicitly selected Rust tool bundle.

The optional Windows pthread compatibility setup is adapted from ProofPay's
MIT-licensed development helper. No ProofPay application module is imported.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action',choices=['build','test','fmt','format'])
    parser.add_argument('--tool-root',type=Path)
    args=parser.parse_args()
    env=os.environ.copy()
    for name in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'):
        env.pop(name,None)
    tools=args.tool_root.resolve() if args.tool_root else None
    cargo=shutil.which('cargo')
    if tools:
        cargo=str(tools/'cargo/bin/cargo.exe')
        env['CARGO_HOME']=str(tools/'cargo');env['RUSTUP_HOME']=str(tools/'rustup')
        host=tools/'rustup/toolchains/stable-x86_64-pc-windows-gnu/lib/rustlib/x86_64-pc-windows-gnu/bin'
        native=tools/'w64devkit/bin'
        env['PATH']=os.pathsep.join(map(str,[tools/'cargo/bin',native,host/'self-contained',host]))+os.pathsep+env.get('PATH','')
        env['CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER']=str(host/'self-contained/x86_64-w64-mingw32-gcc.exe')
        if args.action=='test':
            env['AWS_LC_SYS_PREBUILT_NASM']='1'
            output=ROOT/'artifacts/native-link';output.mkdir(parents=True,exist_ok=True)
            source=output/'pthread_compat.c'
            source.write_text('extern unsigned long long mbsrtowcs(void *, const char **, unsigned long long, void *);\nunsigned long long (*__imp_mbsrtowcs)(void *, const char **, unsigned long long, void *) = mbsrtowcs;\n',encoding='ascii')
            subprocess.run([str(native/'gcc.exe'),'-c',str(source),'-o',str(output/'pthread_compat.o')],check=True)
            for name in ('libpthread.a','libwinpthread.a'):
                shutil.copy2(tools/'w64devkit/lib'/name,output/name)
                subprocess.run([str(native/'ar.exe'),'rcs',name,'pthread_compat.o'],cwd=output,check=True)
            env['CARGO_TARGET_X86_64_PC_WINDOWS_GNU_RUSTFLAGS']='-Lnative='+str(output)
    if not cargo:raise SystemExit('Install Rust + wasm32-unknown-unknown, or select --tool-root.')
    command={'build':['build','--target','wasm32-unknown-unknown','--release'],'test':['test','--lib'],'fmt':['fmt','--','--check'],'format':['fmt']}[args.action]
    subprocess.run([cargo,*command],cwd=ROOT/'contracts/bounty',env=env,check=True)


if __name__=='__main__':main()
