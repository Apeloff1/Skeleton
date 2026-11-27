"""Execute the shipped browser helpers; no model/native qualification is inferred."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess

from skeleton.app.offline_web import JAVASCRIPT
from skeleton.forge.game_design_spec import compile_brief


ROOT = Path(__file__).resolve().parents[1]


def functions(*names: str) -> str:
    result = []
    for name in names:
        start = re.search(r"(?m)^  (?:async )?function " + re.escape(name) + r"\(", JAVASCRIPT)
        assert start is not None, name
        end = re.search(r"(?m)^  (?:async )?function ", JAVASCRIPT[start.end():])
        result.append(JAVASCRIPT[start.start():start.end() + end.start()] if end else JAVASCRIPT[start.start():])
    return "\n".join(result)


def node(script: str, *names: str):
    prelude = "const assert = require('node:assert/strict'); const vm = require('node:vm');\n"
    prelude += "const shipped = " + json.dumps(functions(*names)) + ";\n"
    result = subprocess.run(["node", "-e", prelude + script], cwd=ROOT,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_guided_brief_reaches_real_compiler_with_exact_explicit_choices():
    output = node(r"""
      const context = {TextEncoder}; vm.createContext(context);
      vm.runInContext(shipped + '; globalThis.build = nativeGameBrief;', context);
      const choices = {brief:'Keep my original  wording.\nAnd the second line.', difficulty:'easy',
        theme:'frost', encounter:'ranged', speed:'300', objective:'Recover the beacon'};
      const briefs = ['shooter','platformer','roguelike'].map(genre => context.build({...choices,genre}));
      for (const brief of briefs) assert.ok(brief.endsWith(choices.brief));
      for (const bad of [{genre:'shell'}, {theme:'custom://resource'}, {speed:'3e2'},
        {speed:'361'}, {difficulty:'extreme'}, {objective:'New; command'},
        {objective:'two\nlines'}, {objective:' '}, {brief:'界'.repeat(1400)}]) {
        assert.throws(() => context.build({genre:'shooter',...choices,...bad}));
      }
      console.log(JSON.stringify(briefs));
    """, "nativeGameBrief")
    specs = [compile_brief(brief) for brief in json.loads(output)]
    assert [spec["genre"] for spec in specs] == ["top_down_shooter", "platformer", "rpg_roguelike"]
    for spec in specs:
        assert spec["engine"] == "godot4" and spec["scope"] == "small"
        assert spec["gameplay"] == {"difficulty": "easy", "theme": "frost",
            "encounter_style": "ranged", "player_speed": 300, "objective_label": "Recover the beacon"}


def test_archive_stream_is_confined_to_original_receipt_size_and_is_cancellable():
    node(r"""
      const context = {Uint8Array}; vm.createContext(context);
      vm.runInContext(shipped + '; globalThis.read = readBoundedForgeArchive;', context);
      function response(chunks, header, options = {}) {
        const observations = {cancelled:0,released:0}; let index = 0;
        const reader = {read:async() => index < chunks.length ? {done:false,value:chunks[index++]} : {done:true},
          cancel:async() => {observations.cancelled++}, releaseLock:() => {observations.released++}};
        return {ok:true,redirected:false,headers:{get:name => name === 'Content-Type' ? 'application/zip' : header},
          body:{getReader:() => reader},observations,...options};
      }
      (async() => {
        const control = new AbortController();
        const good = response([new Uint8Array([1,2]),new Uint8Array([3])],'3');
        assert.deepEqual(Array.from(await context.read(good,3,control.signal)),[1,2,3]);
        assert.equal(good.observations.released,1);
        for (const bad of [response([new Uint8Array(4)],null), response([new Uint8Array(2)],'3'),
          response([new Uint8Array(3)],'4'), response([],null),
          response([new Uint8Array(3)],'3',{redirected:true}),
          response([new Uint8Array(3)],'3',{headers:{get:()=>'text/html'}})]) {
          await assert.rejects(context.read(bad,3,control.signal));
        }
        const cancelled = new AbortController(); cancelled.abort();
        const pending = response([new Uint8Array(3)],'3');
        await assert.rejects(context.read(pending,3,cancelled.signal),/cancelled/);
        assert.equal(pending.observations.cancelled,1); assert.equal(pending.observations.released,1);
      })().catch(error=>{console.error(error);process.exitCode=1});
    """, "readBoundedForgeArchive")


def test_exact_review_and_original_request_survive_readiness_edits_and_lost_acknowledgement():
    node(r"""
      const {randomUUID,createHash} = require('node:crypto');
      const state = {connected:true,epoch:1,forgeJob:null,forgeRequest:null,forgeUncertain:false,
        forgeReviewedBrief:null,forgeAvailability:{ready:true},forgePolling:false};
      const notices = [], posts = []; let draft = 'original brief'; let fail = true;
      const context = {state,crypto:{randomUUID},performance:{now:()=>1000},
        nativeGameBrief:fields=>fields, forgeFields:()=>draft,
        refreshForge:async()=>{}, exactLocalSha256:async text=>createHash('sha256').update(text).digest('hex'),
        stopForgePolling:()=>{},scheduleForgePoll:()=>{},renderForgeJob:()=>{},updateControls:()=>{},
        status:value=>notices.push(value),
        api:async(method,path,body)=> {
          if (method === 'POST') {posts.push(JSON.parse(JSON.stringify(body))); if(fail)throw new Error('lost ACK');}
          return {request_id:state.forgeRequest.request_id,brief_sha256:state.forgeRequest.brief_sha256,
            state:'queued',terminal:false};
        }};
      vm.createContext(context); vm.runInContext(shipped + `; globalThis.subject={
        submit:submitForge,retry:retryForgeSubmission,poll:pollForge,active:forgeActive};`,context);
      (async()=>{
        await assert.rejects(context.subject.submit(),/Review the exact/); assert.equal(posts.length,0);
        state.forgeReviewedBrief=draft;
        context.refreshForge=async()=>{draft='changed while checking';state.forgeReviewedBrief=null};
        await assert.rejects(context.subject.submit(),/changed while checking/); assert.equal(posts.length,0);
        draft='original brief';state.forgeReviewedBrief=draft;context.refreshForge=async()=>{};
        await context.subject.submit();
        assert.equal(posts.length,1); assert.equal(state.forgeUncertain,true);
        assert.equal(state.forgeJob.state,'unknown'); assert.equal(context.subject.active(),true);
        assert.equal(Object.isFrozen(state.forgeRequest),true);
        context.api=async()=>{const e=new Error('not visible yet');e.status=404;throw e};
        await context.subject.poll();
        assert.equal(state.forgeJob.state,'unknown'); assert.equal(state.forgeJob.terminal,false);
        assert.equal(state.forgeUncertain,true); assert.equal(posts.length,1);
        draft='edited next idea';state.forgeReviewedBrief=draft;fail=false;
        context.api=async(method,path,body)=>{
          if(method==='POST')posts.push(JSON.parse(JSON.stringify(body)));
          return {request_id:state.forgeRequest.request_id,brief_sha256:state.forgeRequest.brief_sha256,
            state:'queued',terminal:false};
        };
        await context.subject.retry();
        assert.deepEqual(posts[1],posts[0]); assert.equal(posts[1].brief,'original brief');
        assert.equal(draft,'edited next idea');assert.equal(state.forgeUncertain,false);
        assert.equal(state.forgeReviewedBrief,'edited next idea');
      })().catch(error=>{console.error(error);process.exitCode=1});
    """, "forgeActive", "checkedForgeJob", "pollForge", "submitForge", "sendForgeRequest", "retryForgeSubmission")
