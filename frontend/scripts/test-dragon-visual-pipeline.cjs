const fs=require('node:fs'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../src/components/dragonVisualObservationPipeline.ts'),'utf8');
function ok(v,m){if(!v)throw new Error(m)}
ok(src.includes('crypto.subtle.digest("SHA-256"'),'frame pixels must be content-digested locally');
ok(src.includes('frameDigest')&&src.includes('frameId'),'decoder must emit custody identities');
ok(src.includes('luminanceMean')&&src.includes('edgeDensity'),'appearance measurements missing');
ok(src.includes('motionEnergy')&&src.includes('sceneChange'),'motion measurements missing');
ok(src.includes('new Uint8Array(64*36*3)'),'digest input must exclude alpha and stay bounded');
ok(src.includes('URL.revokeObjectURL(url)'),'recording object URL must be released');
ok(!src.includes('fetch(')&&!src.includes('axios'),'local decoder must not upload pixels');
ok(src.includes('signal?: AbortSignal'),'decoder must expose cooperative cancellation');
ok(src.includes('signal?.addEventListener("abort"'),'decoder waits must be abortable');
ok(src.includes('ensureActive()'),'decoder must check cancellation during frame processing');
console.log('dragon visual pipeline contract ok');
