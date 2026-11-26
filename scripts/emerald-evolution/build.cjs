'use strict';
// Original procedural candidate models. Poster is the visual target, not a texture or approval receipt.
function buildForm(id,detail=1){
  const forms=[
    {id:"hatchling",levels:[1,10],height:.80,body:[.40,.43,.42],head:[.42,.35,.43],neck:.27,leg:.22,wing:.42,tail:.50,horn:.08,gear:0,scales:4,color:[.23,.58,.45],shell:true},
    {id:"scout",levels:[11,20],height:1.08,body:[.43,.51,.48],head:[.41,.35,.43],neck:.43,leg:.32,wing:.67,tail:.83,horn:.16,gear:1,scales:5,color:[.18,.50,.39]},
    {id:"scholar",levels:[21,30],height:1.35,body:[.50,.58,.57],head:[.43,.37,.46],neck:.63,leg:.42,wing:.91,tail:1.06,horn:.25,gear:2,scales:6,color:[.16,.46,.37]},
    {id:"pathfinder",levels:[31,40],height:1.65,body:[.57,.66,.64],head:[.46,.39,.49],neck:.83,leg:.54,wing:1.25,tail:1.30,horn:.34,gear:3,scales:7,color:[.12,.42,.35]},
    {id:"archivist",levels:[41,50],height:1.94,body:[.65,.76,.72],head:[.51,.42,.53],neck:1.03,leg:.67,wing:1.55,tail:1.58,horn:.44,gear:4,scales:8,color:[.09,.39,.33]}
  ];
  const f=forms.find(x=>x.id===id); if(!f||![1,2,3].includes(detail))throw Error("Invalid evolution form or density");
  const TAU=2*Math.PI, sin=Math.sin,cos=Math.cos, sqrt=Math.sqrt;
  const add=(a,b)=>a.map((x,i)=>x+b[i]),mul=(a,s)=>a.map(x=>x*s),sub=(a,b)=>a.map((x,i)=>x-b[i]),dot=(a,b)=>a.reduce((r,x,i)=>r+x*b[i],0),cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]],unit=a=>mul(a,1/(sqrt(dot(a,a))||1)),mix=(a,b,t)=>add(mul(a,1-t),mul(b,t));
  const q=(axis,a)=>[...mul(unit(axis),sin(a/2)),cos(a/2)];
  const mat=(name,color,metallicFactor,roughnessFactor,extra={})=>({name,pbrMetallicRoughness:{baseColorFactor:[...color,1],metallicFactor,roughnessFactor},...extra});
  const mats=[
    mat("Emerald jade hide",f.color,.12,.46),mat("Ivory throat and belly",[.76,.69,.48],.05,.51),
    mat("Jade raised scale",[.22,.62,.48],.24,.37),mat("Dark emerald scale",[.065,.26,.22],.14,.42),
    mat("Pale horn keratin",[.81,.77,.56],.1,.35),mat("Membrane turquoise",[.09,.52,.39],.1,.47,{doubleSided:true}),
    mat("Dark emerald wing spars",[.05,.25,.21],.13,.42),mat("Eye sclera",[.91,.94,.82],0,.27),
    mat("Cyan iris",[.025,.69,.81],.32,.17),mat("Obsidians",[.006,.018,.025],.15,.12),mat("Catchlight",[1,1,.96],0,.1,{emissiveFactor:[.6,.8,.8]}),
    mat("Gold filigree",[.72,.43,.075],.76,.29),mat("Brown expedition leather",[.19,.085,.035],.04,.70),
    mat("Ivory eggshell",[.88,.79,.59],.05,.43,{doubleSided:true}),mat("Crystal cyan",[.045,.72,.65],.38,.19,{emissiveFactor:[.015,.16,.14]}),
    mat("Emerald mantle",[.025,.24,.20],.13,.63,{doubleSided:true}),mat("Parchment",[.83,.68,.40],.02,.66),mat("Warm smile line",[.055,.11,.075],0,.6)
  ];
  const nodes=[], meshes=[], views=[], accessors=[], animations=[], blocks=[], groups=new Map();let bytes=0,triangles=0,vertices=0;
  function node(name,parent,translation=[0,0,0]){const i=nodes.length;nodes.push({name,translation});if(parent!==null)(nodes[parent].children??=[]).push(i);return i}
  const root=node("dragon_root",null);
  const bodyY=f.leg+f.body[1]*.74, headY=bodyY+f.neck+f.body[1]*.48, headZ=f.body[2]*.54;
  const torso=node("torso",root,[0,bodyY,0]),head=node("head",torso,[0,headY-bodyY,headZ]),leftWing=node("wing_L",torso,[-f.body[0]*.70,f.body[1]*.47,-f.body[2]*.45]),rightWing=node("wing_R",torso,[f.body[0]*.70,f.body[1]*.47,-f.body[2]*.45]),tail=node("tail",torso,[0,-f.body[1]*.38,-f.body[2]*.78]);
  const legs=[node("foreleg_L",torso,[-f.body[0]*.54,-f.body[1]*.28,f.body[2]*.59]),node("foreleg_R",torso,[f.body[0]*.54,-f.body[1]*.28,f.body[2]*.59]),node("hindleg_L",torso,[-f.body[0]*.78,-f.body[1]*.45,-f.body[2]*.22]),node("hindleg_R",torso,[f.body[0]*.78,-f.body[1]*.45,-f.body[2]*.22])];
  const eyes=[node("eye_L",head),node("eye_R",head)],lids=[node("lid_L",head),node("lid_R",head)];
  function group(n,m){const key=n+":"+m;if(!groups.has(key))groups.set(key,{n,m,p:[],normal:[],idx:[]});return groups.get(key)}
  function v(g,p,n){const i=g.p.length/3;g.p.push(...p);g.normal.push(...unit(n));return i}
  function face(g,a,b,c){if(a===b||b===c||a===c)return;const A=g.p.slice(a*3,a*3+3),B=g.p.slice(b*3,b*3+3),C=g.p.slice(c*3,c*3+3),area=cross(sub(B,A),sub(C,A));if(dot(area,area)>1e-20)g.idx.push(a,b,c)}
  function ell(n,m,c,r,rows=9,cols=14,basis=[[1,0,0],[0,1,0],[0,0,1]]){
    const g=group(n,m),start=g.p.length/3;
    function mapped(x){return add(add(mul(basis[0],x[0]),mul(basis[1],x[1])),mul(basis[2],x[2]))}
    const top=v(g,add(c,mapped([0,r[1],0])),mapped([0,1,0]));
    for(let i=1;i<rows;i++){const a=Math.PI*i/rows;for(let j=0;j<cols;j++){const t=TAU*j/cols,dir=[sin(a)*cos(t),cos(a),sin(a)*sin(t)];v(g,add(c,mapped(dir.map((x,k)=>x*r[k]))),mapped(dir.map((x,k)=>x/r[k])))}}
    const bottom=v(g,add(c,mapped([0,-r[1],0])),mapped([0,-1,0]));
    for(let j=0;j<cols;j++){const k=(j+1)%cols;face(g,top,start+1+k,start+1+j);for(let i=0;i<rows-2;i++){const a=start+1+i*cols+j,b=start+1+i*cols+k,c1=a+cols,d=b+cols;face(g,a,b,c1);face(g,b,d,c1)}const a=start+1+(rows-2)*cols+j,b=start+1+(rows-2)*cols+k;face(g,a,b,bottom)}
  }
  function tube(n,m,points,radii,sides=10){const g=group(n,m),start=g.p.length/3;for(let i=0;i<points.length;i++){const t=unit(sub(points[Math.min(i+1,points.length-1)],points[Math.max(i-1,0)])),ref=Math.abs(t[1])>.91?[1,0,0]:[0,1,0],u=unit(cross(t,ref)),w=unit(cross(t,u));for(let j=0;j<sides;j++){const a=TAU*j/sides,dir=add(mul(u,cos(a)),mul(w,sin(a)));v(g,add(points[i],mul(dir,radii[i])),dir)}}for(let i=0;i<points.length-1;i++)for(let j=0;j<sides;j++){const a=start+i*sides+j,b=start+i*sides+(j+1)%sides;face(g,a,b,a+sides);face(g,b,b+sides,a+sides)}for(const i of [0,points.length-1]){const dir=unit(sub(points[i],points[i===0?1:i-1])),k=v(g,points[i],dir);for(let j=0;j<sides;j++){const a=start+i*sides+j,b=start+i*sides+(j+1)%sides;face(g,k,i===0?b:a,i===0?a:b)}}}
  function curved(n,m,a,b,c,base,tip,sides=10,steps=8){const ps=[],rs=[];for(let i=0;i<=steps;i++){const t=i/steps;ps.push(mix(mix(a,b,t),mix(b,c,t),t));rs.push(Math.max(.0007,base*(1-t)**.85+tip*t))}tube(n,m,ps,rs,sides)}
  function plate(n,m,c,normal,width,length,depth){const y=unit(normal),x=unit(cross(Math.abs(y[1])>.90?[0,0,1]:[0,1,0],y)),z=unit(cross(x,y));ell(n,m,c,[width,depth,length],4,7,[x,y,z])}
  function loop(n,m,c,rx,ry,z,r=.012){const ps=[];for(let j=0;j<=24;j++){const a=TAU*j/24;ps.push(add(c,[rx*cos(a),ry*sin(a),z]))}tube(n,m,ps,ps.map(()=>r),6)}
  const B=f.body,H=f.head,D=detail;
  ell(torso,0,[0,0,0],B,18*D,24*D);
  ell(torso,1,[0,-.03,B[2]*.76],[B[0]*.70,B[1]*.88,B[2]*.30],13*D,18*D);
  // Longitudinal chest, asymmetrically overlapping belly scutes.
  const neckEnd=[0,headY-bodyY-.17,headZ-.13];
  tube(torso,0,[[0,B[1]*.24,B[2]*.14],[0,B[1]*.57,B[2]*.43],mul(neckEnd,.78),neckEnd],[B[0]*.63,B[0]*.53,H[0]*.58,H[0]*.55],18*D);
  for(let i=0;i<7+f.gear;i++){const t=(i+.4)/(7+f.gear),y=-B[1]*.65+t*(neckEnd[1]+B[1]*.65),z=t<.52?B[2]*.97:mix([0,0,B[2]*.95],[0,0,headZ+H[2]*.18],(t-.52)/.48)[2];ell(torso,1,[0,y,z],[B[0]*(.55-.21*t),.055+.025*t,.035],5,13)}
  for(let i=0;i<f.scales*D;i++){const a=.32+(Math.PI-.65)*(i+.5)/(f.scales*D),cnt=9+f.gear;for(let j=0;j<cnt;j++){const t=TAU*(j+.5*(i%2))/cnt;if(sin(t)>.52)continue;const u=[sin(a)*cos(t),cos(a),sin(a)*sin(t)],p=u.map((x,k)=>x*B[k]);plate(torso,(i+j)%4===0?3:2,p,unit(u.map((x,k)=>x/B[k])),B[0]*.15,B[1]*.14,.026)}}
  // Head is not adult scale-down: distinct juvenile muzzle, cheeks, eye orbit, horns and frills.
  ell(head,0,[0,0,0],H,19*D,28*D);
  ell(head,1,[0,-H[1]*.39,H[2]*.63],[H[0]*.76,H[1]*.44,H[2]*.57],12*D,20*D);
  ell(head,0,[0,-H[1]*.16,H[2]*.72],[H[0]*.72,H[1]*.34,H[2]*.57],12*D,20*D);
  for(let s of [-1,1]){
    ell(head,0,[s*H[0]*.63,-H[1]*.09,H[2]*.37],[H[0]*.37,H[1]*.48,H[2]*.41],10,14);
    const e=eyes[s===-1?0:1];const l=lids[s===-1?0:1],center=[s*H[0]*.68,H[1]*.16,H[2]*.63];nodes[e].translation=center;nodes[l].translation=center;
    const front=unit([s*.62,.12,.82]),up=unit(sub([0,1,0],mul(front,dot([0,1,0],front)))),side=unit(cross(up,front)),eyeR=H[1]*(.56-.035*f.gear),basis=[side,up,front];
    ell(e,9,[0,0,0],[eyeR*1.14,eyeR*1.15,eyeR*.52],12,18,basis);
    ell(e,7,mul(front,eyeR*.18),[eyeR,eyeR*.98,eyeR*.49],12,18,basis);
    ell(e,8,mul(front,eyeR*.55),[eyeR*.76,eyeR*.82,eyeR*.24],12,18,basis);
    ell(e,9,mul(front,eyeR*.76),[eyeR*.41,eyeR*.65,eyeR*.13],10,14,basis);
    ell(e,10,add(mul(front,eyeR*.87),add(mul(up,eyeR*.29),mul(side,-eyeR*.27))),[eyeR*.17,eyeR*.17,eyeR*.07],6,10,basis);
    ell(l,0,mul(front,eyeR*.10),[eyeR*1.15,eyeR*1.15,eyeR*.69],10,16,basis);nodes[l].scale=[1,.035,1];
    curved(head,3,add(center,[-s*.06,eyeR*.68,-.06]),add(center,[s*.01,eyeR*1.20,0]),add(center,[s*.14,eyeR*.62,-.13]),.035,.012,8,9);
    ell(head,17,[s*H[0]*.38,-H[1]*.11,H[2]*1.21],[H[0]*.105,H[1]*.067,.027],6,11);
    curved(head,17,[s*H[0]*.11,-H[1]*.39,H[2]*1.13],[s*H[0]*.61,-H[1]*.40,H[2]*.98],[s*H[0]*.80,-H[1]*.20,H[2]*.64],.015,.009,7,10);
    const horn0=[s*H[0]*.53,H[1]*.72,-H[2]*.29];
    curved(head,4,horn0,add(horn0,[s*f.horn*.43,f.horn*.68,-f.horn*.47]),add(horn0,[s*f.horn*.50,f.horn*.95,-f.horn]),H[0]*.15,.001,12*D,9*D);
    for(let i=0;i<3+f.gear;i++){const h=i/(3+f.gear),a=[s*H[0]*.74,H[1]*(.48-.85*h),-H[2]*(.10+.33*h)],b=add(a,[s*(.13+f.horn*.34),.06,-.10]),c=add(a,[s*(.21+f.horn*.61),.10-.14*h,-.22-f.horn*.48]);curved(head,i===0?4:2,a,b,c,.052,.001,8,6)}
  }
  // Tail curled toward one flank; independent scale ridge and crystalline tip.
  const tailPs=[];for(let i=0;i<=18;i++){const t=i/18,a=t*2.50;tailPs.push([f.tail*.52*(1-cos(a)),-B[1]*.12-f.tail*.11*sin(Math.PI*t),-f.tail*.71*sin(a)])}
  tube(tail,0,tailPs,tailPs.map((_,i)=>B[0]*.41*(1-i/19)**1.24+.012),14*D);
  for(let i=2;i<17;i+=2){const p=tailPs[i],r=B[0]*.40*(1-i/19)**1.24;curved(tail,2,add(p,[0,r,0]),add(p,[.02,r+.06,0]),add(p,[.055,r+.10,-.04]),r*.48+.008,.001,7,4)}
  if(f.gear>=2){const p=tailPs[18];ell(tail,14,p,[.075+f.gear*.013,.045,.12],6,8)}
  // Seated limbs with articulated shoulders, toes and horn claws.
  for(let i=0;i<4;i++){const n=legs[i],s=i%2?1:-1,fore=i<2,base=nodes[n].translation,footY=-(bodyY+base[1])+.085,footZ=fore?B[2]*.48:B[2]*.24;
    ell(n,0,[s*.055,footY*.34,0],[B[0]*(fore?.31:.49),Math.abs(footY)*.59+.09,B[2]*(fore?.29:.49)],12*D,16*D);
    tube(n,0,[[0,0,0],[s*.033,footY*.53,footZ*.24],[s*.045,footY,footZ]],[B[0]*.29,B[0]*.24,B[0]*.24],12*D);
    ell(n,0,[s*.045,footY,footZ],[B[0]*.30,.085,B[2]*.34],9,14);
    for(let t=-1;t<=1;t++){const p=[s*.045+t*B[0]*.18,footY-.01,footZ+B[2]*.23];ell(n,2,p,[B[0]*.12,.065,B[2]*.17],6,10);curved(n,4,add(p,[0,.025,.035]),add(p,[0,.01,.12]),add(p,[0,-.035,.15]),.035,.001,8,5)}
  }
  // Membranes are true curved 3D web surfaces, with arched wing bones and scalloped panels.
  for(const [n,s] of [[leftWing,-1],[rightWing,1]]){
    const w=f.wing,origin=[0,0,0],elbow=[s*w*.38,w*.52,-w*.13],crest=[s*w*.77,w*.70,-w*.19];
    const tips=[[s*w*1.02,w*.42,-w*.18],[s*w*.89,w*.11,-w*.27],[s*w*.64,-w*.20,-w*.37],[s*w*.29,-w*.28,-w*.38],[s*w*.06,-w*.07,-w*.18]];
    curved(n,6,origin,elbow,crest,.045+w*.025,.023,12*D,10);
    for(let i=0;i<tips.length;i++){const a=i===0?crest:elbow,b=mix(a,tips[i],.45);b[1]+=w*.065;curved(n,6,a,b,tips[i],.021+w*.009,.001,8,8);if(i<tips.length-1){const g=group(n,5),start=g.p.length/3,res=10*D;const lead=i===0?crest:elbow;for(let r=0;r<=res;r++){const t=r/res;for(let j=0;j<=res;j++){const u=j/res;let border=mix(tips[i],tips[i+1],u);border[1]+=sin(Math.PI*u)*w*.105;const p=mix(lead,border,t);p[2]-=sin(Math.PI*t)*sin(Math.PI*u)*w*.095;v(g,p,[0,0,1])}}for(let r=0;r<res;r++)for(let j=0;j<res;j++){const a=start+r*(res+1)+j,b=a+1,c=a+res+1,d=c+1;face(g,a,b,c);face(g,b,d,c)}if(f.gear>=3){const p=mix(lead,tips[i],.44),b2=mix(lead,tips[i+1],.66);curved(n,11,p,add(mix(p,b2,.5),[0,w*.05,.012]),b2,.004,.003,5,7)}}}
    curved(n,4,crest,add(crest,[s*w*.07,w*.13,0]),add(crest,[s*w*.17,w*.05,-.02]),.033,.001,10,7);
  }
  // A genuine open, jagged eggshell bowl and shell-cap; juvenile wings remain visible.
  if(f.shell){const shell=node("eggshell_bowl",root,[0,.11,.02]),cap=node("eggshell_cap",head,[0,H[1]*.51,0]);
    function eggshell(n,top){const g=group(n,13),r=top?[H[0]*1.04,H[1]*.69,H[2]*.95]:[.58,.49,.56],N=28*D,R=10*D,start=g.p.length/3;for(let i=0;i<=R;i++)for(let j=0;j<N;j++){const t=TAU*j/N,k=(j%5===0?.25:j%3===0?-.13:0),a=top?(.12+(1.22+k)*i/R):(Math.PI-.12-(1.72+k)*i/R);const d=[sin(a)*cos(t),cos(a),sin(a)*sin(t)];v(g,d.map((x,k)=>x*r[k]),d)}for(let i=0;i<R;i++)for(let j=0;j<N;j++){const a=start+i*N+j,b=start+i*N+(j+1)%N;face(g,a,b,a+N);face(g,b,b+N,a+N)}for(let j=0;j<7;j++){const a=TAU*j/7;const p=[r[0]*.94*cos(a),top?r[1]*.28:r[1]*-.08,r[2]*.94*sin(a)];curved(n,11,p,add(p,[.03,-.09,.035]),add(p,[.08,-.14,.02]),.006,.004,5,4)}}
    eggshell(shell,false);eggshell(cap,true);
  }
  // Gear is separate, stage-specific geometry; no physical clearance qualification is asserted.
  if(f.gear){const gear=node("expedition_equipment",torso),z=B[2]*.91;loop(gear,12,[0,B[1]*.12,0],B[0]*.89,B[1]*.52,z,.026+f.gear*.004);
    loop(gear,11,[0,B[1]*.15,0],.11+f.gear*.012,.13+f.gear*.012,z+.035,.018);
    ell(gear,14,[0,B[1]*.15,z+.055],[.10+f.gear*.008,.13+f.gear*.008,.055],8,12);
    for(let s of [-1,1]){const a=[s*B[0]*.67,B[1]*.50,z*.55],b=[s*B[0]*.88,0,-B[2]*.32];curved(gear,12,a,add(b,[0,.15,.17]),b,.037,.034,8,12);curved(gear,11,a,add(b,[0,.17,.17]),b,.010,.009,6,12)}
    for(let i=0;i<Math.min(f.gear,3);i++){const s=i%2?-1:1,center=[s*(B[0]*.86),B[1]*(.02+i*.20),-B[2]*.42-i*.10];ell(gear,12,center,[.21,.19,.25],9,14);loop(gear,11,center,.18,.15,.19,.011);ell(gear,11,add(center,[0,.03,.255]),[.035,.042,.015],5,8)}
    if(f.gear>=2)for(let i=0;i<f.gear-1;i++){const center=[B[0]*(.73+(i%2)*.10),B[1]*(.43+i*.15),-B[2]*.54];tube(gear,16,[add(center,[-.20,0,0]),add(center,[.20,0,0])],[.072,.072],12);for(let s of [-1,1])ell(gear,11,add(center,[s*.20,0,0]),[.028,.077,.077],6,10)}
    if(f.gear>=3){const g=group(gear,15),start=g.p.length/3,N=16;for(let i=0;i<=N;i++)for(let j=0;j<=N;j++){const t=i/N,u=j/N,a=-.95+1.90*u,p=[sin(a)*(B[0]+.07+t*.08),B[1]*(.70-1.16*t),-cos(a)*(B[2]+.07+t*.12)];v(g,p,unit([sin(a),.12,-cos(a)]))}for(let i=0;i<N;i++)for(let j=0;j<N;j++){const a=start+i*(N+1)+j,b=a+1,c=a+N+1;face(g,a,c,b);face(g,b,c,c+1)}
      for(let s of [-1,1])curved(gear,11,[s*B[0]*.82,B[1]*.70,-B[2]*.58],[s*(B[0]+.08),0,-B[2]*.60],[s*(B[0]+.10),-B[1]*.46,-B[2]*.67],.013,.011,7,12)
    }
    if(f.gear>=4){const c=[-B[0]*.95,-.02,B[2]*.36];loop(gear,11,c,.17,.17,0,.012);ell(gear,14,c,[.13,.15,.13],9,14);curved(gear,11,add(c,[0,.17,0]),add(c,[0,.36,-.12]),[-B[0]*.50,B[1]*.54,0],.012,.009,7,9)}
  }
  function buffer(a,target){const pad=(4-bytes%4)%4;if(pad){blocks.push(new Uint8Array(pad));bytes+=pad}const raw=new Uint8Array(a.buffer,a.byteOffset,a.byteLength),i=views.length;views.push({buffer:0,byteOffset:bytes,byteLength:raw.length,...(target?{target}:{})});blocks.push(raw);bytes+=raw.length;return i}
  function accessor(a,type,component,target,bounds=false){const dim={SCALAR:1,VEC3:3,VEC4:4}[type],r={bufferView:buffer(a,target),componentType:component,count:a.length/dim,type};if(bounds){let min=Array(dim).fill(Infinity),max=Array(dim).fill(-Infinity);for(let i=0;i<a.length;i++){const k=i%dim;min[k]=Math.min(min[k],a[i]);max[k]=Math.max(max[k],a[i])}r.min=min;r.max=max}const i=accessors.length;accessors.push(r);return i}
  // Recompute area-weighted normals on curved membrane and mantle panels.
  for(const g of groups.values()){
    if(g.m!==5 && g.m!==15)continue;
    const normals=new Float64Array(g.p.length);
    for(let i=0;i<g.idx.length;i+=3){
      const [a,b,c]=g.idx.slice(i,i+3),p=g.p.slice(a*3,a*3+3),q1=g.p.slice(b*3,b*3+3),r=g.p.slice(c*3,c*3+3);
      let n=cross(sub(q1,p),sub(r,p));
      const hint=g.normal.slice(a*3,a*3+3);
      if(dot(n,hint)<0){g.idx[i+1]=c;g.idx[i+2]=b;n=mul(n,-1)}
      for(const k of [a,b,c])for(let j=0;j<3;j++)normals[k*3+j]+=n[j];
    }
    for(let i=0;i<g.p.length;i+=3){
      const n=Array.from(normals.slice(i,i+3));
      if(dot(n,n)>1e-20)g.normal.splice(i,3,...unit(n));
    }
  }
  const nodeMeshes=new Map();
  for(const g of groups.values()){if(!g.idx.length)continue;let prim={attributes:{POSITION:accessor(new Float32Array(g.p),"VEC3",5126,34962,true),NORMAL:accessor(new Float32Array(g.normal),"VEC3",5126,34962)},indices:accessor(new Uint32Array(g.idx),"SCALAR",5125,34963),material:g.m,mode:4};if(!nodeMeshes.has(g.n))nodeMeshes.set(g.n,[]);nodeMeshes.get(g.n).push(prim);vertices+=g.p.length/3;triangles+=g.idx.length/3;}
  for(const [n,primitives] of nodeMeshes){nodes[n].mesh=meshes.length;meshes.push({name:nodes[n].name,primitives})}
  function anim(name,duration,tracks){const input=accessor(new Float32Array([0,duration*.25,duration*.5,duration*.75,duration]),"SCALAR",5126,undefined,true),samplers=[],channels=[];for(const [n,path,values] of tracks){const output=accessor(new Float32Array(values.flat()),path==="rotation"?"VEC4":"VEC3",5126);channels.push({sampler:samplers.length,target:{node:n,path}});samplers.push({input,output,interpolation:"LINEAR"})}animations.push({name,channels,samplers})}
  const angles=(a,axis=[0,0,1])=>a.map(x=>q(axis,x)),wig=(amp)=>[0,amp,0,-amp,0],wingTrack=(amp)=>[[leftWing,"rotation",angles(wig(amp))],[rightWing,"rotation",angles(wig(-amp))]],blink=[[lids[0],"scale",[[1,.035,1],[1,.035,1],[1,1,1],[1,.035,1],[1,.035,1]]],[lids[1],"scale",[[1,.035,1],[1,.035,1],[1,1,1],[1,.035,1],[1,.035,1]]]];
  anim("IdleBreath",4,[[torso,"translation",[0,.018,0,-.012,0].map(y=>[0,bodyY+y,0])],[head,"rotation",angles(wig(.035),[1,0,0])],[tail,"rotation",angles(wig(.055),[0,1,0])],...wingTrack(.025)]);
  anim("Blink",.50,blink);anim("Snuggle",3.2,[[head,"rotation",angles([0,.12,.19,.12,0],[1,0,0])],[tail,"rotation",angles(wig(.13),[0,1,0])],...wingTrack(.06)]);
  anim("CuriousTilt",2.4,[[head,"rotation",angles([0,.14,.18,.10,0])],[tail,"rotation",angles(wig(.10),[0,1,0])]]);
  anim("HappyBounce",1.4,[[root,"translation",[0,.07,.19,.07,0].map(y=>[0,y,0])],[head,"rotation",angles(wig(.09),[1,0,0])],...wingTrack(.14)]);
  anim("WingStretch",2.6,[...wingTrack(.22+f.gear*.065),[head,"rotation",angles(wig(.045),[1,0,0])]]);
  anim("TailCurl",3,[[tail,"rotation",angles([0,.30,.53,.30,0],[0,1,0])]]);
  anim("Sleep",5,[[head,"rotation",angles([0,.13,.23,.13,0],[1,0,0])],[torso,"translation",[0,-.018,-.045,-.018,0].map(y=>[0,bodyY+y,0])],...blink]);
  if(f.gear>0){anim("ScoutStep",1.1,legs.map((n,i)=>[n,"rotation",angles(wig(i%2?.17:-.17),[1,0,0])]));anim("InspectKnowledge",2.8,[[head,"rotation",angles([0,-.10,-.20,-.10,0],[1,0,0])],[tail,"rotation",angles(wig(.13),[0,1,0])]]);}
  if(f.gear>=2){anim("TakeoffStudy",2.3,[[root,"translation",[0,.12,.48,.88,1.10].map(y=>[0,y,0])],...wingTrack(.48)]);anim("FlightStudy",1.1,[...wingTrack(.47),[tail,"rotation",angles(wig(.08),[1,0,0])]]);anim("LandingStudy",2.2,[[root,"translation",[1.10,.77,.40,.10,0].map(y=>[0,y,0])],...wingTrack(.40)]);}
  const pad=(4-bytes%4)%4;if(pad){blocks.push(new Uint8Array(pad));bytes+=pad}
  const metadata={stage:id,levels:f.levels,detail,vertices,triangles,animations:animations.map(a=>a.name),artisticApproved:false,skinMode:"articulated mesh nodes, not weighted skeletal skin",physicalFlightQualified:false,reference:"Emerald Dragon Evolution Sanctuary"};
  const doc={asset:{version:"2.0",generator:"Skeleton Emerald evolution procedural sculpt v1"},scene:0,scenes:[{nodes:[root]}],nodes,meshes,materials:mats,animations,accessors,bufferViews:views,buffers:[{byteLength:bytes}],extras:metadata};
  const js=JSON.stringify(doc),jsonSize=Math.ceil(js.length/4)*4,out=new Uint8Array(12+8+jsonSize+8+bytes),dv=new DataView(out.buffer);dv.setUint32(0,0x46546c67,true);dv.setUint32(4,2,true);dv.setUint32(8,out.length,true);dv.setUint32(12,jsonSize,true);dv.setUint32(16,0x4e4f534a,true);out.fill(32,20,20+jsonSize);for(let i=0;i<js.length;i++)out[20+i]=js.charCodeAt(i);dv.setUint32(20+jsonSize,bytes,true);dv.setUint32(24+jsonSize,0x004e4942,true);let offset=28+jsonSize;for(const arr of blocks){out.set(arr,offset);offset+=arr.length}
  return {bytes:out,metadata};
}
module.exports={buildForm};
if(require.main===module){const fs=require('node:fs');const path=require('node:path');const crypto=require('node:crypto');const dest=process.argv[2];if(!dest)throw Error('output directory required');const detail=Number(process.argv[3]||2);fs.mkdirSync(dest,{recursive:true});for(const id of ['hatchling','scout','scholar','pathfinder','archivist']){const result=buildForm(id,detail);const file=path.join(dest,id+'.glb');fs.writeFileSync(file,result.bytes,{flag:'wx'});console.log(JSON.stringify({...result.metadata,bytes:result.bytes.length,sha256:crypto.createHash('sha256').update(result.bytes).digest('hex')}));}}
