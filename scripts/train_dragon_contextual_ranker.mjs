// Original contextual hard-negative curriculum. No external text or source bodies.
import {readFileSync} from 'node:fs';
function contextualTrain(v2){
 const N=18,H=48,M=3;
 const features=[...v2.features,"relative_semantic","relative_exact","relative_gap","relative_retry","semantic_percentile","gap_percentile","remaining_fraction","role_disagreement"];
 const rng=seed=>{let s=seed>>>0;return()=>{s=(Math.imul(s,1664525)+1013904223)>>>0;return s/4294967296}};
 const clamp=x=>Math.max(0,Math.min(1,x)),avg=a=>a.reduce((s,x)=>s+x,0)/a.length;
 const sig=x=>1/(1+Math.exp(-Math.max(-40,Math.min(40,x))));
 function context(x,pool){
   const mean=k=>avg(pool.map(a=>a[k])),percent=k=>pool.filter(a=>a[k]<=x[k]).length/pool.length;
   return [...x,clamp(.5+(x[0]-mean(0))*.5),clamp(.5+(x[1]-mean(1))*.5),clamp(.5+(x[9]-mean(9))*.5),clamp(.5+(x[6]-mean(6))*.5),percent(0),percent(9),pool.length/8,Math.abs(x[0]-x[7])];
 }
 function groups(seed,count,shift){
   const rand=rng(seed),result=[];
   for(let n=0;n<count;n++){
     const phase=n%4,amount=8-(n%5),pool=[],latent=[];
     const difficulty=.25+.65*rand(),gapNeed=.2+.8*rand();
     for(let i=0;i<amount;i++){
       const rel=rand(),decoy=rand()<(shift?.30:.18),exact=clamp(rel+(rand()-.5)*difficulty+(decoy?.38:0)),concept=clamp(rel+(rand()-.5)*difficulty-(decoy?.37:0));
       const gram=clamp(exact+(rand()-.5)*.7),semantic=clamp(.4*exact+.35*concept+.15*gram+.1*rand());
       const novelty=rand(),depth=Math.floor(rand()*4)/3,retry=Math.floor(rand()*4)/3,first=shift?rand():clamp(rel+(rand()-.5)*1.3),variety=rand(),gap=clamp(exact*gapNeed+(rand()-.5)*.8);
       pool.push([semantic,exact,concept,gram,novelty,depth,retry,first,variety,gap]);latent.push({rel,decoy});
     }
     const g=pool.map((a,i)=>{
       const x=context(a,pool),rel=latent[i].rel;
       const [s,e,c,f,nv,d,rt,j,v,g]=a;
       const u=1.0*e+1.42*c+.35*f+.50*s+.65*g+.55*v*(.25+.75*rel)+.68*nv*c-.75*rt-.28*d
         +.65*x[11]+.54*x[12]+.65*x[14]+.40*x[15]-.75*x[13]-.55*x[17]*(1-c)
         +(phase===0?.6*g:phase===1?.6*nv*c:phase===2?-.5*rt:.45*c)
         +.22*rel-(latent[i].decoy?.14:0)+(rand()-.5)*(shift?.30:.18);
       return {x,u};
     });result.push(g);
   }return result;
 }
 const train=groups(0x44335631,4096,false),dev=groups(0x44335632,768,false),hold=groups(0x44335633,1536,true);
 const models=[];
 function forward(m,x,h){let z=0;for(let j=0;j<H;j++){let s=m.b[j];for(let k=0;k<N;k++)s+=m.w[j][k]*x[k];h[j]=Math.tanh(s);z+=m.v[j]*h[j]}return z}
 for(let m=0;m<M;m++){
   const rand=rng(0x77390000+m),model={w:Array.from({length:H},()=>Array.from({length:N},()=>(rand()-.5)*.35)),b:Array(H).fill(0),v:Array.from({length:H},()=>(rand()-.5)*.25)},a=new Array(H),b=new Array(H);
   for(let ep=0;ep<16;ep++){
     const lr=.022/(1+ep/12);
     for(let n=0;n<train.length;n++){
       const g=train[(n*2053+ep*137+m*71)%train.length],i=Math.floor(rand()*g.length),j=(i+1+Math.floor(rand()*(g.length-1)))%g.length;
       const x=g[i],y=g[j],delta=x.u-y.u;if(Math.abs(delta)<.08)continue;
       const za=forward(model,x.x,a),zb=forward(model,y.x,b),err=sig(za-zb)-sig(delta*3.5);
       for(let t=0;t<H;t++){const v=model.v[t],ga=err*v*(1-a[t]*a[t]),gb=-err*v*(1-b[t]*b[t]);for(let k=0;k<N;k++)model.w[t][k]-=lr*(ga*x.x[k]+gb*y.x[k]+.00035*model.w[t][k]);model.b[t]-=lr*(ga+gb);model.v[t]-=lr*(err*(a[t]-b[t])+.00035*v)}
     }
   }models.push(model)
 }
 const aggregate=zs=>avg(zs)-.15*Math.sqrt(avg(zs.map(z=>(z-avg(zs))**2)));
 const predict=x=>aggregate(models.map(m=>forward(m,x,new Array(H))));
 const baseline=x=>aggregate(v2.members.map(m=>m.output.reduce((sum,v,j)=>sum+v*Math.tanh(m.hidden_bias[j]+m.input[j].reduce((s,w,k)=>s+w*x[k],0)),0)));
 function evaluate(gs,fn){
   let ndcg=0,regret=0,pairs=0,correct=0;
   for(const g of gs){
     const ranked=g.map((a,i)=>({...a,i,p:fn(a.x)})).sort((a,b)=>b.p-a.p||a.i-b.i),ideal=g.map(a=>a.u).sort((a,b)=>b-a),min=ideal[ideal.length-1];
     const gain=xs=>xs.slice(0,3).reduce((s,u,i)=>s+(Math.exp(Math.min(5,u-min))-1)/Math.log2(i+2),0);
     ndcg+=gain(ranked.map(a=>a.u))/Math.max(1e-9,gain(ideal));regret+=ideal[0]-ranked[0].u;
     for(let i=0;i<ranked.length;i++)for(let j=i+1;j<ranked.length;j++){const d=ranked[i].u-ranked[j].u;if(Math.abs(d)>.08){pairs++;correct+=+(d>0)}}
   }return {ndcg3:ndcg/gs.length,pair_accuracy:correct/pairs,top_regret:regret/gs.length};
 }
 const report={development:evaluate(dev,predict),v2_development:evaluate(dev,baseline),shifted_holdout:evaluate(hold,predict),v2_holdout:evaluate(hold,baseline),lexical_holdout:evaluate(hold,x=>x[0])};
 if(report.development.ndcg3<=report.v2_development.ndcg3||report.shifted_holdout.ndcg3<=report.v2_holdout.ndcg3||report.shifted_holdout.pair_accuracy<=report.v2_holdout.pair_accuracy)throw Error("contextual model promotion held: "+JSON.stringify(report));
 const round=x=>Number(x.toFixed(10)),pack=a=>a.map(x=>Array.isArray(x)?pack(x):round(x));
 return {schema:"skeleton.dragon.navigation-ranker.v3",architecture:{inputs:N,hidden:H,members:M,activation:"tanh",output:"contextual_pairwise_logit"},features,members:models.map(m=>({input:pack(m.w),hidden_bias:pack(m.b),output:pack(m.v)})),training:{curriculum:"original-contextual-hard-negative-v3",train_groups:train.length,development_groups:dev.length,shifted_holdout_groups:hold.length,train_candidates:train.reduce((s,g)=>s+g.length,0),holdout_candidates:hold.reduce((s,g)=>s+g.length,0),epochs:16,report,source_bodies_used:false,production_quality_verified:false}};
}
const v2=JSON.parse(readFileSync(new URL('../skeleton/ai/webcrawler/models/dragon_navigation_ranker.v2.json',import.meta.url),'utf8'));
console.log(JSON.stringify(contextualTrain(v2),null,2));
