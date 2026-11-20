"""Source qualification for the actual offline workspace renderer and routes.

The Node harness uses a deliberately tiny inert DOM to assert emitted element
types, exact copy payload and hostile-text treatment. It is not browser E2E.
"""
import shutil
import subprocess
import unittest

from skeleton.app.offline_web import HTML, JAVASCRIPT
from skeleton.app.offline_http import OfflineHTTPApplication, OfflineHTTPError
from skeleton.app.jeeves_approved_memory import ApprovedMemory
from skeleton.ai.model_runtime.offline_chat import OfflineChatStore


_DOM = r"""
const assert=require('node:assert/strict');
class Node {
  constructor(tag,text=''){this.tag=tag;this.value=text;this.children=[];this.events={};}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;this.value='';}
  set textContent(value){this.value=String(value);this.children=[];}
  get textContent(){return this.value+this.children.map(n=>n.textContent).join('');}
  set innerHTML(value){throw new Error('HTML parser invoked');}
  addEventListener(type,handler){this.events[type]=handler;}
}
global.document={
  createElement(tag){
    assert.ok(['strong','code','pre','div','span','button','p','h3','h4','h5','hr',
      'ul','ol','li','blockquote','table','thead','tbody','tr','th','td'].includes(tag),tag);
    return new Node(tag);
  },
  createTextNode(text){return new Node('#text',text);}
};
const all=(node,tag)=>[...(node.tag===tag?[node]:[]),...node.children.flatMap(n=>all(n,tag))];
"""


class RichChatTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node runtime unavailable")
    def test_renderer_inert_and_structured(self):
        start = JAVASCRIPT.index("// BEGIN JEEVES_SAFE_CHAT_RENDERER")
        end = JAVASCRIPT.index("// END JEEVES_SAFE_CHAT_RENDERER")
        renderer = JAVASCRIPT[start:end]
        fixture = r"""
const root=new Node('root');let copied=[];
const fence=String.fromCharCode(96).repeat(3);
const raw=['# A heading','**bold** and '+String.fromCharCode(96)+'inline'+String.fromCharCode(96),
  '- item','- second','3. third','4. fourth','> quote','| A | B |','| --- | --- |',
  '| one | two |',fence+'python','<img src=x onerror=alert(1)>','  print("x")',fence,
  '<script>alert(1)</script>', '[attack](javascript:alert(1))'].join('\n');
renderChatBody(root,raw,code=>copied.push(code));
assert.equal(all(root,'h3')[0].textContent,'A heading');
assert.equal(all(root,'strong')[0].textContent,'bold');
assert.equal(all(root,'ul')[0].children.length,2);
assert.equal(all(root,'ol')[0].start,3);
assert.equal(all(root,'table').length,1);
assert.equal(all(root,'td')[1].textContent,'two');
assert.equal(all(root,'blockquote')[0].textContent,'quote');
assert.ok(root.textContent.includes('<script>alert(1)</script>'));
assert.ok(root.textContent.includes('[attack](javascript:alert(1))'));
assert.equal(all(root,'img').length,0);
all(root,'button')[0].events.click();
assert.equal(copied[0],'<img src=x onerror=alert(1)>\n  print("x")');
renderChatBody(root,fence+'js\nunfinished',()=>{});
assert.ok(root.textContent.includes('unclosed fence'));
assert.ok(root.textContent.includes('unfinished'));
const long='x'.repeat(262145);renderChatBody(root,long,()=>{});
assert.equal(root.textContent,long);
"""
        result = subprocess.run(["node", "-"], input=_DOM + renderer + fixture,
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])

    @unittest.skipUnless(shutil.which("node"), "Node runtime unavailable")
    def test_whole_workspace_javascript_parses(self):
        result = subprocess.run(["node", "--check", "-"], input=JAVASCRIPT,
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])

    def test_memory_controls_present_in_actual_workspace(self):
        for name in ("memory-panel", "memory-search", "memory-compose",
                     "memory-apply", "memory-save", "memory-detach"):
            self.assertEqual(HTML.count('id="' + name + '"'), 1)
            self.assertIn("'" + name + "'", JAVASCRIPT)
        self.assertIn("Retry in new branch", JAVASCRIPT)
        self.assertIn("Edit in new branch", JAVASCRIPT)


class MemoryRouteTests(unittest.TestCase):
    def setUp(self):
        self.store = OfflineChatStore(":memory:")
        # Dispatch is the real application routing method, but these isolated
        # tests intentionally avoid native-model startup or live HTTP.
        self.app = OfflineHTTPApplication.__new__(OfflineHTTPApplication)
        self.app.approved_memory = ApprovedMemory(self.store, "a"*64, "b"*64)

    def tearDown(self):
        self.store.close()

    def dispatch(self, subpath, body):
        return self.app.dispatch("POST", "/v1/memory/" + subpath, body)

    def test_lifecycle_and_composition(self):
        body = {"kind":"goal","label":"Project","text":"Finish the glossary.",
                "tags":[],"expires_at":None,"source":None,"approved":True}
        status, row = self.dispatch("save", body)
        self.assertEqual(status, 201)
        pin = {k:row[k] for k in ("memory_id","revision","sha256")}
        status, search = self.dispatch("search", {"query":"glossary"})
        self.assertEqual(search["records"][0]["memory_id"],row["memory_id"])
        status, composition = self.dispatch("compose", {"draft":"Continue.","pins":[pin]})
        self.assertEqual(status,200)
        self.assertIn("Finish the glossary.", composition["composed_text"])
        self.assertFalse(composition["generation_performed"])
        status, edited = self.dispatch("save", {**body,"pin":pin,"text":"Write the appendix."})
        self.assertEqual(status,200)
        with self.assertRaises(OfflineHTTPError) as caught:
            self.dispatch("compose", {"draft":"Continue.","pins":[pin]})
        self.assertEqual(caught.exception.status,409)
        new_pin = {k:edited[k] for k in pin}
        self.dispatch("delete", {"pin":new_pin,"approved":True})
        self.assertEqual(self.dispatch("list",{})[1]["records"],[])

    def test_closed_shapes_and_required_approval(self):
        for sub, body in (("search",{"query":"test","tenant":"foreign"}),
                          ("list",{"limit":True}), ("compose",{"draft":"x","pins":[]}),
                          ("save",{"approved":False})):
            with self.subTest(sub=sub), self.assertRaises(OfflineHTTPError) as caught:
                self.dispatch(sub,body)
            self.assertEqual(caught.exception.status,400)
        with self.assertRaises(OfflineHTTPError) as caught:
            self.dispatch("unknown",{})
        self.assertEqual(caught.exception.status,404)


if __name__ == "__main__":
    unittest.main()
