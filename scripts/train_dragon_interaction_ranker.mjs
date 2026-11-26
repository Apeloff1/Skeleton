// Original contextual interaction curriculum, disjoint folds; no external content.
import {readFileSync} from 'node:fs';
function trainV4(v3){
 const N=50,H=112,M=5;
 const names=[...v3.features,"agreement","concept_gap","exact_gap","semantic_gap","concept_novelty","semantic_novelty","variety_gap","retry_safety","depth_safety","trust_discount","hard_negative","concept_dominance","lexical_dominance","semantic_rank_match","gap_rank_match","concept_retry","semantic_retry","novelty_retry","gap_retry","depth_retry","exact_concept","semantic_concept","semantic_variety","concept_variety","objective_balance","gap_remaining","semantic_remaining","uncertainty_context","rank_gap","rank_concept","rare_match","source_cost"];
 const rng=seed=>{let s=seed>>>0;return()=>{s=(Math.imul(s,1664525)+1013904223)>>>0;return s/4294967296}};
 const clamp=x=>Math.max(0,Math.min(1,x)),avg=a=>a.reduce((s,x)=>s+x,0)/a.length;
 const sig=x=>1/(1+Math.exp(-Math.max(-40,Math.min(40,x))));
 function expand(x){const [s,e,c,f,n,d,t,j,v,g,rs,re,rg,rt,sp,gp,remain,dis]=x;return [...x,
  1-dis,c*g,e*g,s*g,c*n,s*n,v*g,1-t,1-d,j*(1-dis),e*(1-c),c*(1-e),e*(1-c),
  s*j,g*j,c*(1-t),s*(1-t),n*(1-t),g*(1-t),(1-d)*(1-t),e*c,s*c,s*v,c*v,
  Math.min(e,c,g),g*remain,s*remain,dis*(1-sp),j*g,j*c,c*(1-sp),.5*(d+t)]}
 function context(x,pool){const mean=k=>avg(pool.map(a=>a[k])),pct=k=>pool.filter(a=>a[k]<=x[k]).length/pool.length;
  return expand([...x,...[0,1,9,6].map(k=>clamp(.5+.5*(x[k]-mean(k)))),pct(0),pct(9),pool.length/8,Math.abs(x[0]-x[7])])}
 function groups(seed,count,shift){const R=rng(seed),out=[];for(let i=0;i<count;i++){
   const amount=4+i%5,phase=i%5,noise=.22+R()*.52,pool=[];for(let j=0;j<amount;j++){
    const trueRel=R(),decoy=R()<(shift?.36:.24),e=clamp(trueRel+(R()-.5)*noise+(decoy?.42:0)),c=clamp(trueRel+(R()-.5)*noise-(decoy?.45:0)),f=clamp(e+(R()-.5)*.82);
    const s=clamp(.4*e+.35*c+.15*f+.1*R()),n=R(),d=Math.floor(R()*4)/3,t=Math.floor(R()*4)/3,jr=shift?R():clamp(trueRel+(R()-.5)*1.7),v=R(),g=clamp(e*(.25+.75*R())+(R()-.5)*.8);
    pool.push([s,e,c,f,n,d,t,jr,v,g])
   }
   out.push(pool.map(a=>{const x=context(a,pool),[s,e,c,f,n,d,t,j,v,g]=a;
    // Original conceptual curriculum: reward complementary evidence and reliable
    // novelty, penalize expensive misleading matches and unsupported deference.
    const u=.55*s+.72*e+1.21*c+.25*f+.43*g+.35*v-.48*t-.24*d
     +.78*x[19]+.40*x[20]+.57*x[22]+.86*x[24]+.86*x[27]-.78*x[28]
     +.55*x[33]+.47*x[36]+.38*x[41]+.65*x[42]+.42*x[44]-.52*x[45]+.44*x[48]-.56*x[49]
     +[.40*x[24],.42*x[22],.64*x[27],.47*x[41],.48*x[48]][phase]+(R()-.5)*(shift?.30:.22);
    return {x,u};
   }));
 }return out}
 const train=groups(0x44345631,40960,false),dev=groups(0x44345632,1024,false),hold=groups(0x44345633,2048,true);
 const models=[];
 function forward(m,x,h){let z=0;for(let u=0;u<H;u++){let s=m.b[u],offset=u*N;for(let k=0;k<N;k++)s+=m.w[offset+k]*x[k];const a=Math.tanh(s);h[u]=a;z+=m.v[u]*a}return z}
 for(let q=0;q<M;q++){
  const R=rng(0x78340000+q),m={w:Float64Array.from({length:H*N},()=> (R()-.5)*.22),b:new Float64Array(H),v:Float64Array.from({length:H},()=> (R()-.5)*.18)},a=new Float64Array(H),b=new Float64Array(H);
  // Every group belongs to one disjoint ensemble training fold; each
  // independent member learns only its fold (8,192 groups).
  for(let ep=0;ep<4;ep++){
   const lr=.028/(1+ep*.35);
   for(let k=0;k<8192;k++){const g=train[((k*4051+ep*173)%8192)*M+q],i=Math.floor(R()*g.length),j=(i+1+Math.floor(R()*(g.length-1)))%g.length;
    const x=g[i],y=g[j],delta=x.u-y.u;if(Math.abs(delta)<.06)continue;
    const za=forward(m,x.x,a),zb=forward(m,y.x,b),error=sig(za-zb)-sig(delta*3.4);
    for(let u=0;u<H;u++){const v=m.v[u],ga=error*v*(1-a[u]*a[u]),gb=-error*v*(1-b[u]*b[u]),off=u*N;for(let t=0;t<N;t++)m.w[off+t]-=lr*(ga*x.x[t]+gb*y.x[t]+.00025*m.w[off+t]);m.b[u]-=lr*(ga+gb);m.v[u]-=lr*(error*(a[u]-b[u])+.00025*v)}
   }
  }models.push(m);
 }
 const ag=z=>avg(z)-.15*Math.sqrt(avg(z.map(t=>(t-avg(z))**2)));
 const h=new Float64Array(H),predict=x=>ag(models.map(m=>forward(m,x,h)));
 const prior=x=>ag(v3.members.map(m=>m.output.reduce((s,v,j)=>s+v*Math.tanh(m.hidden_bias[j]+m.input[j].reduce((a,w,k)=>a+w*x[k],0)),0)));
 function metric(groups,fn){let ndcg=0,pairs=0,good=0,regret=0;for(const g of groups){
  const list=g.map((a,i)=>({...a,i,p:fn(a.x)})).sort((a,b)=>b.p-a.p||a.i-b.i),ideal=g.map(a=>a.u).sort((a,b)=>b-a),min=ideal[ideal.length-1];
  const dcg=x=>x.slice(0,3).reduce((s,u,i)=>s+(Math.exp(Math.min(5,u-min))-1)/Math.log2(i+2),0);
  ndcg+=dcg(list.map(a=>a.u))/Math.max(1e-9,dcg(ideal));regret+=ideal[0]-list[0].u;
  for(let i=0;i<list.length;i++)for(let j=i+1;j<list.length;j++){const delta=list[i].u-list[j].u;if(Math.abs(delta)>.06){pairs++;good+=+(delta>0)}}
 }return{ndcg3:ndcg/groups.length,pair_accuracy:good/pairs,top_regret:regret/groups.length}}
 const report={development:metric(dev,predict),v3_development:metric(dev,prior),shifted_holdout:metric(hold,predict),v3_holdout:metric(hold,prior),lexical_holdout:metric(hold,x=>x[0])};
 if(report.development.ndcg3<=report.v3_development.ndcg3||report.shifted_holdout.ndcg3<=report.v3_holdout.ndcg3||report.shifted_holdout.pair_accuracy<=report.v3_holdout.pair_accuracy||report.shifted_holdout.top_regret>=report.v3_holdout.top_regret)throw Error(JSON.stringify(report));
 const round=x=>Number(x.toFixed(9));
 return{schema:"skeleton.dragon.navigation-ranker.v4",architecture:{inputs:N,hidden:H,members:M,activation:"tanh",output:"contextual_pairwise_logit"},features:names,
  members:models.map(m=>({input:Array.from({length:H},(_,i)=>Array.from(m.w.slice(i*N,(i+1)*N),round)),hidden_bias:Array.from(m.b,round),output:Array.from(m.v,round)})),
  training:{curriculum:"original-interaction-folded-navigation-v4",train_groups:train.length,development_groups:dev.length,shifted_holdout_groups:hold.length,train_candidates:train.reduce((s,g)=>s+g.length,0),holdout_candidates:hold.reduce((s,g)=>s+g.length,0),epochs:4,folds:5,report,source_bodies_used:false,production_quality_verified:false}};
}
const v3=JSON.parse(readFileSync(new URL('../skeleton/ai/webcrawler/models/dragon_navigation_ranker.v3.json',import.meta.url),'utf8'));
console.log(JSON.stringify(trainV4(v3)));
