const fs=require("node:fs"),path=require("node:path"),crypto=require("node:crypto");
const fixture=JSON.parse(fs.readFileSync(path.join(__dirname,"../../tests/fixtures/dragon_visual_wire_v1.json"),"utf8"));
const stable=x=>Array.isArray(x)?`[${x.map(stable).join(",")}]`:x&&typeof x==="object"?`{${Object.entries(x).sort(([a],[b])=>a.localeCompare(b)).map(([k,v])=>JSON.stringify(k)+":"+stable(v)).join(",")}}`:JSON.stringify(x);
const canonical=stable(fixture);
const digest=crypto.createHash("sha256").update(canonical,"utf8").digest("hex");
if(digest!=="cc8ca97b5e608ae872209ce7fa4f47a49905489f9b42a1d56db90acb9a7d3261")throw new Error(`canonical wire drift: ${digest}`);
if(!canonical.includes("user-α"))throw new Error("UTF-8 canonicalization lost Unicode");
console.log("dragon canonical wire parity ok",digest);
