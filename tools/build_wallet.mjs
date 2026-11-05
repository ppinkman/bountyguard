import { build } from 'esbuild';
import { readFile } from 'node:fs/promises';

await build({
  entryPoints: ['frontend/wallet-entry.mjs'],
  bundle: true,
  platform: 'browser',
  format: 'iife',
  target: ['es2022'],
  outfile: 'bountyguard/web/wallet-bundle.js',
  legalComments: 'eof',
  plugins: [{
    name: 'near-connect-csp-style-nonce',
    setup(builder) {
      builder.onLoad({ filter: /[\\/]near-connect[\\/]build[\\/]popups[\\/]Popup\.js$/ }, async ({ path }) => {
        const original = await readFile(path, 'utf8');
        const needle = 'const style = document.createElement("style");';
        if (!original.includes(needle)) throw new Error('Review the pinned connector CSS integration before updating.');
        return { contents: original.replace(needle, needle + '\nstyle.setAttribute("nonce", document.querySelector(\'meta[name="bg-csp-nonce"]\')?.content || "");'), loader: 'js' };
      });
      builder.onLoad({ filter: /[\\/]near-connect[\\/]build[\\/]SandboxedWallet[\\/]code\.js$/ }, async ({ path }) => {
        const original = await readFile(path, 'utf8');
        if (!original.includes('<style>')) throw new Error('Review the connector iframe CSP integration before updating.');
        return { contents: original.replace('<style>', '<style${nonceAttr}>'), loader: 'js' };
      });
    },
  }],
});
