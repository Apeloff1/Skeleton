const fs=require('node:fs');const path=require('node:path');
const model=fs.readFileSync(path.join(__dirname,'../features/Jeeves/companion/dragonCompanionState.ts'),'utf8');
const view=fs.readFileSync(path.join(__dirname,'../features/Jeeves/companion/DragonCompanion.tsx'),'utf8');
const chat=fs.readFileSync(path.join(__dirname,'../features/Jeeves/ChatWorkspace.tsx'),'utf8');
function ok(v,m){if(!v)throw new Error(m)}
ok(model.includes("case'burn_complete':return state('distilling'"),'burn completion must enter distillation');
ok(model.includes('glasses:true,bandage:true'),'distillation must wear glasses and bridge bandage');
ok(!model.match(/case'[^']+'[^\n]+glasses:true/g)?.some?.(x=>!x.includes("burn_complete")),'glasses leaked outside distillation');
ok(view.includes('shellHat'),'dragon must keep broken eggshell cap');
ok(view.includes('blanket'),'snuggle state must have blanket');
ok(view.includes('hornL')&&view.includes('scaleA')&&view.includes('tailSpade'),'upscaled dragon must keep horns, scales and a tail spade');
ok(view.includes("accessibilityRole=\"summary\""),'companion must expose semantic summary');
ok(model.includes("case'distill_complete'"),'distillation completion must be its own event');
ok(!model.includes("case'distill_complete'")||!/case'distill_complete'[^\n]*glasses:true/.test(model),'glasses stay on during distillation, not after it is sealed');
ok(model.includes('companionFromCapture'),'capture events must have a separate companion projection');
ok(chat.includes('DragonCompanionPanel'),'companion must be mounted in Jeeves workspace');
const crawler=fs.readFileSync(path.join(__dirname,'../features/Jeeves/CrawlerWorkspace.tsx'),'utf8');
ok(crawler.includes('companionFromCapture'),'crawler workspace must show the dragon from recorded capture events');
console.log('dragon companion contract ok');
