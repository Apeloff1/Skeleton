"""Exact triangle contact witnesses and bounded BVH for sampled Emerald anatomy.

Screening uses selected classified triangle pools at sampled rig poses.
It does not certify continuous skeletal motion, seams, or equipment clearance.
"""
import math
import time
import numpy as np

class IncompleteAudit(ValueError):pass

def dot(a,b):return float(np.dot(a,b))

def segment_dist2(a,b,c,d):
 u=b-a;v=d-c;w=a-c;A=dot(u,u);B=dot(u,v);C=dot(v,v);D=dot(u,w);E=dot(v,w)
 if A<1e-12 and C<1e-12:return dot(w,w)
 if A<1e-12:s=0.;t=float(np.clip(E/max(C,1e-12),0,1))
 elif C<1e-12:t=0.;s=float(np.clip(-D/A,0,1))
 else:
  den=A*C-B*B;s=float(np.clip((B*E-C*D)/den,0,1)) if abs(den)>1e-12 else 0.
  t=(B*s+E)/C
  if t<0:t=0.;s=float(np.clip(-D/A,0,1))
  elif t>1:t=1.;s=float(np.clip((B-D)/A,0,1))
 x=w+s*u-t*v
 return max(0.,dot(x,x))

def point_tri2(p,tri):
 a,b,c=tri;ab=b-a;ac=c-a;ap=p-a;d1=dot(ab,ap);d2=dot(ac,ap)
 if d1<=0 and d2<=0:return dot(ap,ap)
 bp=p-b;d3=dot(ab,bp);d4=dot(ac,bp)
 if d3>=0 and d4<=d3:return dot(bp,bp)
 vc=d1*d4-d3*d2
 if vc<=0 and d1>=0 and d3<=0:
  v=d1/max(1e-12,d1-d3);x=p-(a+v*ab);return dot(x,x)
 cp=p-c;d5=dot(ab,cp);d6=dot(ac,cp)
 if d6>=0 and d5<=d6:return dot(cp,cp)
 vb=d5*d2-d1*d6
 if vb<=0 and d2>=0 and d6<=0:
  w=d2/max(1e-12,d2-d6);x=p-(a+w*ac);return dot(x,x)
 va=d3*d6-d5*d4
 if va<=0 and d4-d3>=0 and d5-d6>=0:
  w=(d4-d3)/max(1e-12,(d4-d3)+(d5-d6));x=p-(b+w*(c-b));return dot(x,x)
 den=max(1e-12,va+vb+vc);x=p-(a+ab*(vb/den)+ac*(vc/den));return dot(x,x)

def edge_face(p,q,tri):
 a,b,c=tri;direction=q-p;u=b-a;v=c-a;h=np.cross(direction,v);det=dot(u,h)
 if abs(det)<1e-11:return False
 f=1/det;s=p-a;t=f*dot(s,h)
 if t<-1e-11 or t>1+1e-11:return False
 h=np.cross(s,u);r=f*dot(direction,h)
 return r>=-1e-11 and r+t<=1+1e-11 and -1e-11<=f*dot(v,h)<=1+1e-11

def triangle_dist2(a,b):
 if a.shape!=(3,3) or b.shape!=(3,3):raise ValueError('triangle shape')
 for k in range(3):
  if edge_face(a[k],a[(k+1)%3],b) or edge_face(b[k],b[(k+1)%3],a):return 0.
 v=min([point_tri2(x,b) for x in a]+[point_tri2(x,a) for x in b])
 for i in range(3):
  for j in range(3):v=min(v,segment_dist2(a[i],a[(i+1)%3],b[j],b[(j+1)%3]))
 return max(0.,v)

def contact_pairs(a,b,margin=.008,max_pairs=200000,deadline=None):
 """Conservative triangle AABB BVH; exhaustively returns pairs or fails."""
 if a.ndim!=3 or b.ndim!=3 or a.shape[1:]!=(3,3) or b.shape[1:]!=(3,3):raise ValueError('triangle pools')
 if not (0<=margin<=.25 and 1<=max_pairs<=2000000):raise ValueError('policy')
 if not len(a) or not len(b):return [],0
 amin=a.min(axis=1);amax=a.max(axis=1);bmin=b.min(axis=1);bmax=b.max(axis=1)
 if np.any(amin.min(0)-margin>bmax.max(0)) or np.any(bmin.min(0)-margin>amax.max(0)):return [],0
 mid=(bmin+bmax)/2;tree=[]
 def build(ids):
  k=len(tree);tree.append(None);lo=bmin[ids].min(0);hi=bmax[ids].max(0)
  if len(ids)<=32:tree[k]=(lo,hi,None,None,ids)
  else:
   axis=int(np.argmax(np.ptp(mid[ids],axis=0)));order=ids[np.argsort(mid[ids,axis],kind='stable')];split=len(order)//2
   l=build(order[:split]);r=build(order[split:]);tree[k]=(lo,hi,l,r,None)
  return k
 root=build(np.arange(len(b),dtype=np.int32));pairs=[];probes=visits=0
 for i in range(len(a)):
  if deadline is not None and i%256==0 and time.monotonic()>deadline:raise IncompleteAudit('pose deadline exceeded')
  stack=[root]
  while stack:
   visits+=1
   if visits%8192==0 and deadline is not None and time.monotonic()>deadline:raise IncompleteAudit('BVH deadline exceeded')
   if visits>max(1000000,50*max_pairs):raise IncompleteAudit('BVH visit quota')
   lo,hi,l,r,ids=tree[stack.pop()]
   if np.any(amin[i]-margin>hi) or np.any(lo-margin>amax[i]):continue
   if ids is None:stack.append(l);stack.append(r);continue
   probes+=len(ids)
   mask=np.all((amin[i]-margin<=bmax[ids]) & (bmin[ids]-margin<=amax[i]),axis=1)
   for j in ids[mask]:
    pairs.append((i,int(j)))
    if len(pairs)>max_pairs:raise IncompleteAudit('actual AABB pair quota')
 return pairs,probes

def witness(a,b,ia,ib,margin=.008,max_pairs=200000,deadline=None):
 pairs,probes=contact_pairs(a,b,margin,max_pairs,deadline);contacts=near=center=distal=0;examples=[];d=float('inf')
 for k,(i,j) in enumerate(pairs):
  if k%256==0 and deadline is not None and time.monotonic()>deadline:raise IncompleteAudit('narrow phase deadline')
  ds=triangle_dist2(a[i],b[j]);d=min(d,ds)
  if ds<=1e-16:
   contacts+=1;z=abs(float((a[i].mean(0)[2]+b[j].mean(0)[2])/2))
   if z<=.025:center+=1
   else:distal+=1
   if len(examples)<32:examples.append({'faces':[int(ia[i]),int(ib[j])], 'center_m':((a[i].mean(0)+b[j].mean(0))/2).tolist()})
  elif ds<=margin*margin:near+=1
 return {'broadphase_tests':probes,'candidate_pairs':len(pairs),'contact_count':contacts,
         'near_count':near,'root_centerline_contacts':center,'distal_contacts':distal,
         'minimum_candidate_distance_m':math.sqrt(d) if math.isfinite(d) else None,
         'contact_examples':examples}
