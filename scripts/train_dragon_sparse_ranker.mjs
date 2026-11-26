// Original sparse conditional ranking curriculum. No external captures.
import {readFileSync} from 'node:fs';
function trainSparse(v4) {
 const BANKS=10,SIZE=32768,TILES=96,BASE=50,N=409600;
 const rng=seed=>{let s=seed>>>0;return()=>{s=(Math.imul(s,1664525)+1013904223)>>>0;return s/4294967296}};
 const clamp=x=>Math.max(0,Math.min(1,x)),mean=a=>a.reduce((s,x)=>s+x,0)/a.length;
 function expand(x){const [s,e,c,f,n,d,t,j,v,g,rs,re,rg,rt,sp,gp,remain,dis]=x;return [...x,1-dis,c*g,e*g,s*g,c*n,s*n,v*g,1-t,1-d,j*(1-dis),e*(1-c),c*(1-e),e*(1-c),s*j,g*j,c*(1-t),s*(1-t),n*(1-t),g*(1-t),(1-d)*(1-t),e*c,s*c,s*v,c*v,Math.min(e,c,g),g*remain,s*remain,dis*(1-sp),j*g,j*c,c*(1-sp),.5*(d+t)]}
 function context(x,pool){const avg=k=>mean(pool.map(a=>a[k])),pct=k=>pool.filter(a=>a[k]<=x[k]).length/pool.length;return expand([...x,...[0,1,9,6].map(k=>clamp(.5+.5*(x[k]-avg(k)))),pct(0),pct(9),pool.length/8,Math.abs(x[0]-x[7])])}
 function tile(x,k){const a=(k*17+3)%BASE,b=(k*29+11)%BASE,c=(k*37+23)%BASE;
   const q=i=>Math.min(7,Math.floor(x[i]*8));let h=Math.imul(k+1,0x9e3779b1)^Math.imul(q(a)+1,0x85ebca6b)^Math.imul(q(b)+1,0xc2b2ae35)^Math.imul(q(c)+1,0x27d4eb2f);h^=h>>>16;h=Math.imul(h,0x7feb352d);h^=h>>>15;return BASE+((h>>>0)%(SIZE-BASE));}
 function indices(x){let out=new Uint32Array(TILES);for(let k=0;k<TILES;k++)out[k]=tile(x,k);return out}
 function group(R,i,shift){
  const count=4+i%5, pool=[],hard=.2+.65*R(),regime=i%7;
  for(let k=0;k<count;k++){
   const rel=R(),decoy=R()<(shift?.34:.23),e=clamp(rel+(R()-.5)*hard+(decoy?.4:0)),c=clamp(rel+(R()-.5)*hard-(decoy?.38:0)),f=clamp(e+(R()-.5)*.82);
   const s=clamp(.4*e+.35*c+.15*f+.1*R()),n=R(),d=Math.floor(R()*4)/3,t=Math.floor(R()*4)/3,j=shift?R():clamp(rel+(R()-.5)*1.6),v=R(),g=clamp(e*(.2+.8*R())+(R()-.5)*.8);
   pool.push([s,e,c,f,n,d,t,j,v,g]);
  }
  return pool.map(a=>{const x=context(a,pool),[s,e,c,f,n,d,t,j,v,g]=a;
   // Analytic synthetic curriculum: cost-sensitive conditional interactions,
   // score discontinuities and diminishing coverage returns.
   let u=.72*s+.48*e+1.1*c+.28*f+.52*g+.38*v-.7*t-.23*d
    +.64*x[19]+.75*x[22]+.45*x[24]+.55*x[27]-.7*x[28]+.46*x[33]+.55*x[41]+.46*x[44]-.5*x[45];
   u+=.73*Math.min(c,g)*Math.sqrt(v)+.66*Math.max(0,c-e)*n-.58*Math.max(0,e-c)*(1-g);
   u+=.44*(g>.5&&c>.4?1:0)-.40*(t>.6&&c<.35?1:0)+.59*Math.sqrt(g*c)*(1-t);
   u+=.25*x[14]+.26*x[15]+.3*(regime===1?g:regime===2?c*(1-t):regime===3?v*c:regime===4?n*c:regime===5?1-t:c);
   return {x,u:u+(R()-.5)*(shift?.20:.15)};
  });
 }
 let models=Array.from({length:BANKS},()=>new Float64Array(SIZE)),bias=new Float64Array(BANKS),visited=Array.from({length:BANKS},()=>new Uint8Array(SIZE));
 const R=rng(0x44523531);let examples=0;
 function raw(w,b,x,is){let z=b;for(let i=0;i<BASE;i++)z+=w[i]*x[i];for(let i=0;i<TILES;i++)z+=w[is[i]]*.25;return z}
 for(let i=0;i<N;i++){
  const bank=Math.floor(i/5)%BANKS, m=models[bank],seen=visited[bank],g=group(R,i,false);
  const lr=.009/(1+Math.floor(i/81920)*.16);
  for(const a of g){const ix=indices(a.x),z=raw(m,bias[bank],a.x,ix),err=Math.max(-2,Math.min(2,z-a.u));bias[bank]-=lr*err;
   for(let k=0;k<BASE;k++){m[k]-=lr*(err*a.x[k]+.00015*m[k]);seen[k]=1;}
   for(let k=0;k<TILES;k++){const index=ix[k];m[index]-=lr*(err*.25+.00008*m[index]);seen[index]=1;}
   examples++;
  }
 }
 // Fixed signed 16-bit quantization, evaluated after quantization.
 const scale=4096,packed=models.map(w=>Int16Array.from(w,x=>Math.max(-32767,Math.min(32767,Math.round(x*scale))))),qbias=Array.from(bias,x=>Math.round(x*scale)/scale);
 const nonzero=packed.map(m=>m.reduce((s,x)=>s+(x!==0),0)), touched=visited.map(m=>m.reduce((s,x)=>s+x,0));
 const aggregate=z=>mean(z)-.15*Math.sqrt(mean(z.map(x=>(x-mean(z))**2)));
 function predict(x){const ix=indices(x);return aggregate(packed.map((w,b)=>raw(w,qbias[b]*scale,x,ix)/scale))}
 function previous(x){return aggregate(v4.members.map(m=>m.output.reduce((s,v,j)=>s+v*Math.tanh(m.hidden_bias[j]+m.input[j].reduce((a,w,k)=>a+w*x[k],0)),0)))}
 function evaluate(seed,num,shift){const R=rng(seed),out={ndcg3:0,pair_accuracy:0,top_regret:0},pairs=[0,0];const vs={...out},lex={...out},vp=[0,0],lp=[0,0];let count=0;
  function add(acc,pair,g,fn){const sorted=g.map((a,i)=>({...a,i,p:fn(a.x)})).sort((a,b)=>b.p-a.p||a.i-b.i),ideal=g.map(a=>a.u).sort((a,b)=>b-a),min=ideal[ideal.length-1];
   const dcg=x=>x.slice(0,3).reduce((s,u,i)=>s+(Math.exp(Math.min(5,u-min))-1)/Math.log2(i+2),0);
   acc.ndcg3+=dcg(sorted.map(a=>a.u))/Math.max(1e-9,dcg(ideal));acc.top_regret+=ideal[0]-sorted[0].u;
   for(let i=0;i<sorted.length;i++)for(let j=i+1;j<sorted.length;j++){const d=sorted[i].u-sorted[j].u;if(Math.abs(d)>.06){pair[1]++;pair[0]+=+(d>0)}}
  }
  for(let i=0;i<num;i++){const g=group(R,i,shift);count+=g.length;add(out,pairs,g,predict);add(vs,vp,g,previous);add(lex,lp,g,x=>x[0]);}
  for(const [a,p] of [[out,pairs],[vs,vp],[lex,lp]]){a.ndcg3/=num;a.top_regret/=num;a.pair_accuracy=p[0]/p[1];}
  return {model:out,prior:vs,lexical:lex,candidates:count};
 }
 const dev=evaluate(0x44523532,1024,false),hold=evaluate(0x44523533,4096,true);
 const report={development:dev.model,v4_development:dev.prior,shifted_holdout:hold.model,v4_holdout:hold.prior,lexical_holdout:hold.lexical};
 if(!(report.shifted_holdout.ndcg3>report.v4_holdout.ndcg3&&report.shifted_holdout.pair_accuracy>report.v4_holdout.pair_accuracy&&report.shifted_holdout.top_regret<report.v4_holdout.top_regret&&report.development.ndcg3>report.v4_development.ndcg3))throw Error(JSON.stringify({report,touched,nonzero}));
 const chars="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
 function encode(w){let out="",a=0,b=0;for(let i=0;i<w.length;i++){const v=w[i]&65535;for(const byte of [v&255,v>>>8]){a=(a<<8)|byte;b+=8;while(b>=6){b-=6;out+=chars[(a>>>b)&63]}}}if(b)out+=chars[(a<<(6-b))&63];while(out.length%4)out+="=";return out;}
 const artifact={schema:"skeleton.dragon.navigation-ranker.v5",architecture:{inputs:50,banks:BANKS,weights_per_bank:SIZE,tiles:TILES,encoding:"int16-le-base64",scale},features:v4.features,
  banks:packed.map((w,i)=>({weights:encode(w).match(/.{1,4096}/g),bias:qbias[i],touched:touched[i],nonzero:nonzero[i]})),
  training:{curriculum:"original-sparse-conditional-navigation-v5",train_groups:N,train_candidates:examples,development_groups:1024,shifted_holdout_groups:4096,holdout_candidates:hold.candidates,epochs:1,folds:BANKS,report,source_bodies_used:false,production_quality_verified:false}};
 return artifact;
}
const v4=JSON.parse(readFileSync(new URL('../skeleton/ai/webcrawler/models/dragon_navigation_ranker.v4.json',import.meta.url),'utf8'));
console.log(JSON.stringify(trainSparse(v4)));
