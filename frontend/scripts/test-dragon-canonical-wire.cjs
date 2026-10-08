const fs=require("node:fs"),path=require("node:path"),crypto=require("node:crypto");
const fixture=JSON.parse(fs.readFileSync(path.join(__dirname,"../../tests/fixtures/dragon_visual_wire_v1.json"),"utf8"));
const stable=x=>Array.isArray(x)?`[${x.map(stable).join(",")}]`:x&&typeof x==="object"?`{${Object.entries(x).sort(([a],[b])=>a.localeCompare(b)).map(([k,v])=>JSON.stringify(k)+":"+stable(v)).join(",")}}`:JSON.stringify(x);
const canonical=stable(fixture);
const digest=crypto.createHash("sha256").update(canonical,"utf8").digest("hex");
if(digest!=="e00ec3da67a7785fa438a35df5158f8d84156e0c51805ed8deeef3c030718139")throw new Error(`canonical wire drift: ${digest}`);
if(!canonical.includes("user-α"))throw new Error("UTF-8 canonicalization lost Unicode");
console.log("dragon canonical wire parity ok",digest);
