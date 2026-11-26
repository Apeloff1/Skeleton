// Grouped, original synthetic curriculum; independent pairwise ensemble.
import {readFileSync} from 'node:fs';
function trainV2(v1){
 const N=10,H=32,M=3;
 const rng=seed=>{let s=seed>>>0;return()=>{s=(Math.imul(s,1664525)+1013904223)>>>0;return s/4294967296}};
 const clamp=x=>Math.max(0,Math.min(1,x));
 const sig=x=>1/(1+Math.exp(-Math.max(-40,Math.min(40,x))));
 function groups(seed,count,shift=false){
   const rand=rng(seed),out=[];
   for(let n=0;n<count;n++){
     const scenario=n%4,items=[];
     for(let i=0;i<8;i++){
       const rel=rand(),exact=clamp(rel+(rand()-.5)*.7),concept=clamp(rel+(rand()-.5)*.9),fuzzy=clamp(exact+(rand()-.5)*.8);
       const semantic=.4*exact+.35*concept+.15*fuzzy+.1*rand(),novelty=rand(),depth=Math.floor(rand()*4)/3,retry=Math.floor(rand()*4)/3;
       const first=shift?rand():clamp(rel+(rand()-.5)*1.1),variety=rand(),gap=clamp(exact+(rand()-.5)*.8);
       const x=[semantic,exact,concept,fuzzy,novelty,depth,retry,first,variety,gap];
       const u=(1.15*exact+1.2*concept+.49*fuzzy+.72*semantic+.62*gap+.48*variety*(.3+.7*rel)
         +.78*novelty*concept-.82*retry-.32*depth-.55*(1-rel)*novelty
         +[.7*gap,.6*novelty*rel,-.65*retry,.45*concept][scenario]+(rand()-.5)*(shift?.35:.18));
       items.push({x,u});
     }out.push(items);
   }return out;
 }
 const train=groups(0x44325631,3072),dev=groups(0x44325632,512),hold=groups(0x44325633,1024,true);
 function make(seed){
   const rand=rng(seed),w=Array.from({length:H},()=>Array.from({length:N},()=>(rand()-.5)*.45)),b=Array(H).fill(0),v=Array.from({length:H},()=>(rand()-.5)*.3);
   return {w,b,v};
 }
 function forward(m,x,h){let z=0;for(let j=0;j<H;j++){let s=m.b[j];for(let k=0;k<N;k++)s+=m.w[j][k]*x[k];h[j]=Math.tanh(s);z+=m.v[j]*h[j]}return z}
 const models=[];
 for(let m=0;m<M;m++){
   const model=make(0x52425630+m),rand=rng(0x77330000+m),a=new Array(H),bb=new Array(H);
   for(let epoch=0;epoch<18;epoch++){
     const lr=.032/(1+epoch/12);
     for(let n=0;n<train.length;n++){
       const g=train[(n*2053+epoch*131+m*73)%train.length],i=Math.floor(rand()*8),j=(i+1+Math.floor(rand()*7))%8;
       const x=g[i],y=g[j],delta=x.u-y.u;if(Math.abs(delta)<.09)continue;
       const za=forward(model,x.x,a),zb=forward(model,y.x,bb),target=sig(delta*3.5),err=(sig(za-zb)-target);
       for(let t=0;t<H;t++){
         const v=model.v[t],ga=err*v*(1-a[t]*a[t]),gb=-err*v*(1-bb[t]*bb[t]);
         for(let k=0;k<N;k++)model.w[t][k]-=lr*(ga*x.x[k]+gb*y.x[k]+.0004*model.w[t][k]);
         model.b[t]-=lr*(ga+gb);model.v[t]-=lr*(err*(a[t]-bb[t])+.0004*v);
       }
     }
   }models.push(model);
 }
 const logits=x=>models.map(m=>forward(m,x,new Array(H))),avg=x=>x.reduce((a,b)=>a+b,0)/x.length;
 const predict=x=>{const z=logits(x);return avg(z)-.15*Math.sqrt(avg(z.map(t=>(t-avg(z))**2)))};
 const old=x=>{const w=v1.weights;return w.output_bias+w.output.reduce((a,v,j)=>a+v*Math.tanh(w.hidden_bias[j]+w.input[j].reduce((s,t,k)=>s+t*x[k],0)),0)};
 function evaluate(data,predict){
   let dcg=0,pair=0,total=0,regret=0;
   for(const g of data){
     const ranked=g.map((a,i)=>({...a,i,p:predict(a.x)})).sort((a,b)=>b.p-a.p||a.i-b.i);
     const ideal=g.map(a=>a.u).sort((a,b)=>b-a),min=Math.min(...ideal);
     const gain=xs=>xs.slice(0,3).reduce((s,u,i)=>s+(Math.exp(Math.min(5,u-min))-1)/Math.log2(i+2),0);
     dcg+=gain(ranked.map(a=>a.u))/Math.max(1e-9,gain(ideal));regret+=ideal[0]-ranked[0].u;
     for(let i=0;i<8;i++)for(let j=i+1;j<8;j++){const d=ranked[i].u-ranked[j].u;if(Math.abs(d)>.09){pair+=+(d>0);total++}}
   }return {ndcg3:dcg/data.length,pair_accuracy:pair/total,top_regret:regret/data.length};
 }
 const report={development:evaluate(dev,predict),shifted_holdout:evaluate(hold,predict),v1_holdout:evaluate(hold,old),lexical_holdout:evaluate(hold,x=>x[0])};
 if(report.shifted_holdout.ndcg3<=Math.max(report.v1_holdout.ndcg3,report.lexical_holdout.ndcg3))throw Error(JSON.stringify(report));
 const round=x=>Number(x.toFixed(10)),pack=a=>a.map(x=>Array.isArray(x)?pack(x):round(x));
 return {schema:"skeleton.dragon.navigation-ranker.v2",architecture:{inputs:N,hidden:H,members:M,activation:"tanh",output:"pairwise_logit"},features:v1.features,
 members:models.map(m=>({input:pack(m.w),hidden_bias:pack(m.b),output:pack(m.v)})),training:{curriculum:"original-grouped-navigation-pairwise-v2",train_groups:3072,development_groups:512,shifted_holdout_groups:1024,epochs:18,report,source_bodies_used:false,production_quality_verified:false}};
}
const v1=JSON.parse(readFileSync(new URL('../skeleton/ai/webcrawler/models/dragon_navigation_ranker.v1.json',import.meta.url),'utf8'));
console.log(JSON.stringify(trainV2(v1),null,2));
