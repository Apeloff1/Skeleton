// Original synthetic task curriculum; no web captures, third-party text or model downloads.
function trainDragonNavigationRanker(){
 const schema="skeleton.dragon.navigation-ranker.v1",N=10,H=16;
 function rng(seed){let s=seed>>>0;return()=>{s=(Math.imul(s,1664525)+1013904223)>>>0;return s/4294967296}}
 function examples(seed,count){const r=rng(seed),out=[];for(let i=0;i<count;i++){
   const a=r(),b=r(),c=r(),d=r(),e=r(),depth=Math.floor(r()*4)/3,retry=Math.floor(r()*4)/3,rank=r(),variety=r(),gap=r();
   const x=[a,b,c,d,e,depth,retry,rank,variety,gap];
   // Original synthetic curriculum: prefer objective relevance, novel
   // paths and low retry cost; exploit novelty only when related.
   const utility=1.65*a+1.15*b+.9*c+.42*d+.86*e*(.25+.75*c)-.52*depth-1.1*retry+.18*rank+.52*variety+.48*gap*(.3+.7*b)-1.92;
   const noise=(r()-.5)*.65;out.push([x,utility+noise>0?1:0]);
 }return out}
 const train=examples(0x44524147,8192),holdout=examples(0x4f4e484f,2048);
 const r=rng(0x52414e4b),w=Array.from({length:H},()=>Array.from({length:N},()=>(r()-.5)*.5)),b=Array(H).fill(0),v=Array.from({length:H},()=>(r()-.5)*.5);let bias=0;
 const sig=z=>1/(1+Math.exp(-Math.max(-40,Math.min(40,z))));
 function forward(x){const h=w.map((row,j)=>Math.tanh(row.reduce((s,a,k)=>s+a*x[k],b[j])));return [h,sig(h.reduce((s,a,j)=>s+a*v[j],bias))]}
 for(let epoch=0;epoch<32;epoch++){const rate=.055/(1+epoch/20);for(let n=0;n<train.length;n++){const [x,y]=train[(n*4051+epoch*173)%train.length],[h,p]=forward(x),err=p-y;
  for(let j=0;j<H;j++){const grad=err*v[j]*(1-h[j]*h[j]);for(let k=0;k<N;k++)w[j][k]-=rate*(grad*x[k]+.0001*w[j][k]);b[j]-=rate*grad;v[j]-=rate*(err*h[j]+.0001*v[j])}bias-=rate*err;
 }}
 function metric(rows,fn){let acc=0,loss=0;for(const [x,y]of rows){const p=Math.max(1e-9,Math.min(1-1e-9,fn(x)));acc+=Number((p>=.5)===!!y);loss-=y*Math.log(p)+(1-y)*Math.log1p(-p)}return{accuracy:acc/rows.length,log_loss:loss/rows.length}}
 const round=x=>Number(x.toFixed(10)),pack=a=>a.map(x=>Array.isArray(x)?pack(x):round(x));
 const trained=metric(holdout,x=>forward(x)[1]);const baseline=metric(holdout,x=>sig(3*(x[0]-.5)));
 if(!(trained.log_loss<baseline.log_loss&&trained.accuracy>.8))throw Error("synthetic qualification held");
 return {schema,architecture:{inputs:N,hidden:H,activation:"tanh",output:"sigmoid"},features:["semantic","exact","concept","trigram","novelty","depth","retry","jeeves_rank","variety","objective_gap"],weights:{input:pack(w),hidden_bias:pack(b),output:pack(v),output_bias:round(bias)},training:{curriculum:"original-synthetic-navigation-v1",train_count:train.length,holdout_count:holdout.length,epochs:32,train_seed:0x44524147,holdout_seed:0x4f4e484f,weight_seed:0x52414e4b,holdout_accuracy:round(trained.accuracy),holdout_log_loss:round(trained.log_loss),baseline_log_loss:round(baseline.log_loss),source_bodies_used:false,production_quality_verified:false}};
}
const model=trainDragonNavigationRanker();
console.log(JSON.stringify(model,null,2));
