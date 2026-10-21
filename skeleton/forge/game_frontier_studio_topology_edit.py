"""Twenty-five executable terrain-brush and level-topology constructors (151-175).

All routines edit actual canonical palette-indexed tile cells. They never
execute model-provided code; same seed and original StudioProject are replayable.
"""
from __future__ import annotations

from collections import deque
from dataclasses import replace
from typing import Any, Mapping
import math
import random

from .game_frontier_studio import StudioProject, StudioError
from .game_frontier_studio_map_edit import _layer, _rectangle, _tile, _integer, _replace_layer
from .game_frontier_studio_procedural_edit import _fbm, _line, _real, _seed

TERRAIN_TOPOLOGY_ACTIONS = (
    "terrain_dilate_mask", "terrain_erode_mask", "terrain_open_mask",
    "terrain_close_mask", "terrain_majority_eight", "terrain_largest_region",
    "terrain_connect_regions", "terrain_diamond_landmass", "terrain_hex_landmass",
    "terrain_triangular_landmass", "terrain_radial_spokes",
    "terrain_concentric_paths", "terrain_bezier_road", "terrain_spline_river",
    "terrain_random_walker", "terrain_flow_channels", "terrain_edge_falloff",
    "terrain_moat_castle", "terrain_ruin_foundations", "terrain_forest_clusters",
    "terrain_patch_scatter", "terrain_wave_pattern", "terrain_checker_rotated",
    "terrain_mountain_pass", "terrain_archipelago_bridges",
)


def _neighbors(x,y,region,diagonal=False):
    offsets=((1,0),(-1,0),(0,1),(0,-1))
    if diagonal:
        offsets+=((1,1),(1,-1),(-1,1),(-1,-1))
    return [(x+dx,y+dy) for dx,dy in offsets if (x+dx,y+dy) in region]


def edit_topology(project: StudioProject, action: str,
                  args: Mapping[str,Any]) -> StudioProject:
    if not isinstance(project,StudioProject) or action not in TERRAIN_TOPOLOGY_ACTIONS or not isinstance(args,Mapping):
        raise StudioError("unsupported executable world topology authoring command")
    index,layer=_layer(project,args)
    x0,y0,w,h=_rectangle(layer,args)
    floor=_tile(layer,args,"floor")
    wall=_tile(layer,args,"wall")
    if floor==wall:
        raise StudioError("world topology floor/wall palette indexes must differ")
    seed=_seed(args)
    rng=random.Random(seed)
    region={(x,y) for y in range(y0,y0+h) for x in range(x0,x0+w)}
    previous={(x,y):layer.data[y*layer.width+x] for x,y in region}
    chosen={pt for pt,v in previous.items() if v==wall}
    written=dict(previous)
    def paint(pt,value):
        if pt in region:
            written[pt]=value
    def line(a,b,value,width=0):
        for x,y in _line(*a,*b):
            for dx in range(-width,width+1):
                for dy in range(-width,width+1):
                    if dx*dx+dy*dy<=width*width:
                        paint((x+dx,y+dy),value)
    def components(pixels):
        unseen=set(pixels)
        out=[]
        while unseen:
            start=min(unseen,key=lambda p:(p[1],p[0]))
            unseen.remove(start)
            queue=deque([start])
            component={start}
            while queue:
                at=queue.popleft()
                for neighbor in _neighbors(*at,region):
                    if neighbor in unseen:
                        unseen.remove(neighbor)
                        component.add(neighbor)
                        queue.append(neighbor)
            out.append(component)
        return sorted(out,key=lambda s:(-len(s),min(s)))
    if action in ("terrain_dilate_mask","terrain_erode_mask","terrain_open_mask","terrain_close_mask"):
        steps=_integer(args,"iterations",1,12) if "iterations" in args else 1
        def dilate(mask):
            return mask | {neighbor for p in mask for neighbor in _neighbors(*p,region,True)}
        def erode(mask):
            return {p for p in mask if len(_neighbors(*p,region,True))==8 and
                    all(n in mask for n in _neighbors(*p,region,True))}
        mask=set(chosen)
        for _ in range(steps):
            if action=="terrain_dilate_mask":
                mask=dilate(mask)
            elif action=="terrain_erode_mask":
                mask=erode(mask)
            elif action=="terrain_open_mask":
                mask=dilate(erode(mask))
            else:
                mask=erode(dilate(mask))
        for pt in region:
            paint(pt,wall if pt in mask else floor)
    elif action=="terrain_majority_eight":
        for pt in region:
            neighbors=_neighbors(*pt,region,True)
            votes=sum(p in chosen for p in neighbors)
            paint(pt,wall if votes>=max(1,math.ceil(len(neighbors)/2)) else floor)
    elif action in ("terrain_largest_region","terrain_connect_regions"):
        comps=components(chosen)
        if not comps:
            raise StudioError("no authored wall topology to rewrite")
        if action=="terrain_largest_region":
            for pt in region:
                paint(pt,wall if pt in comps[0] else floor)
        else:
            for component in comps[1:]:
                first=min(comps[0],key=lambda q:min(abs(q[0]-p[0])+abs(q[1]-p[1])
                                                   for p in component))
                second=min(component,key=lambda p:abs(first[0]-p[0])+abs(first[1]-p[1]))
                line(first,second,wall)
    elif action in ("terrain_diamond_landmass","terrain_hex_landmass",
                    "terrain_triangular_landmass","terrain_edge_falloff"):
        for x,y in region:
            u=(x-(x0+(w-1)/2))/max(1,w/2)
            v=(y-(y0+(h-1)/2))/max(1,h/2)
            if action=="terrain_diamond_landmass":
                inside=abs(u)+abs(v)<=1
            elif action=="terrain_hex_landmass":
                inside=max(abs(u)*.9+abs(v)*.45,abs(v))<=.87
            elif action=="terrain_triangular_landmass":
                inside=(-.85<=v<=.9 and abs(u)<=(.9-v)*.58)
            else:
                edge=min(x-x0,y-y0,x0+w-1-x,y0+h-1-y)
                inside=edge+(_fbm(seed,x,y,5,3)-.5)*3>=_real(args,"margin",0,128,2)
            paint((x,y),wall if inside else floor)
    elif action in ("terrain_radial_spokes","terrain_concentric_paths"):
        for pt in region:
            paint(pt,wall)
        center=(x0+w//2,y0+h//2)
        count=_integer(args,"count",2,32) if "count" in args else 8
        if action=="terrain_radial_spokes":
            radius=min(w,h)/2
            for k in range(count):
                angle=2*math.pi*k/count
                end=(int(center[0]+radius*math.cos(angle)),
                     int(center[1]+radius*math.sin(angle)))
                line(center,end,floor)
        else:
            for k in range(1,count+1):
                radius=k*min(w,h)/(2*(count+1))
                for step in range(max(16,int(radius*10))):
                    angle=2*math.pi*step/max(16,int(radius*10))
                    paint((round(center[0]+radius*math.cos(angle)),
                           round(center[1]+radius*math.sin(angle))),floor)
    elif action in ("terrain_bezier_road","terrain_spline_river"):
        points=args.get("control_points")
        if (type(points) is not list or len(points) not in (3,4) or
                any(type(p) is not list or len(p)!=2 or
                    any(type(v) is not int for v in p) or tuple(p) not in region
                    for p in points)):
            raise StudioError("authored curve requires three or four in-region XY control points")
        width=_integer(args,"radius",0,8) if "radius" in args else 1
        previous_point=None
        for k in range(max(32,4*(w+h))):
            t=k/max(1,max(32,4*(w+h))-1)
            if len(points)==3:
                a,b,c=points
                px=(1-t)**2*a[0]+2*(1-t)*t*b[0]+t*t*c[0]
                py=(1-t)**2*a[1]+2*(1-t)*t*b[1]+t*t*c[1]
            else:
                a,b,c,d=points
                px=(1-t)**3*a[0]+3*(1-t)**2*t*b[0]+3*(1-t)*t*t*c[0]+t**3*d[0]
                py=(1-t)**3*a[1]+3*(1-t)**2*t*b[1]+3*(1-t)*t*t*c[1]+t**3*d[1]
            at=(round(px),round(py))
            if previous_point is not None:
                line(previous_point,at,floor if action=="terrain_bezier_road" else wall,width)
            previous_point=at
    elif action=="terrain_random_walker":
        count=_integer(args,"steps",1,65536) if "steps" in args else w*h*2
        point=(x0+w//2,y0+h//2)
        for _ in range(count):
            paint(point,floor)
            neighbors=_neighbors(*point,region)
            if neighbors:
                point=rng.choice(neighbors)
    elif action=="terrain_flow_channels":
        # Steepest descent on noise elevation; only paint downhill flow.
        starts=_integer(args,"sources",1,64) if "sources" in args else 6
        for _ in range(starts):
            current=(rng.randrange(x0,x0+w),rng.randrange(y0,y0+h))
            used=set()
            while current not in used:
                used.add(current)
                paint(current,wall)
                candidates=_neighbors(*current,region)
                lower=[p for p in candidates
                       if _fbm(seed,*p,6,4)<_fbm(seed,*current,6,4)]
                if not lower:
                    break
                current=min(lower,key=lambda p:(_fbm(seed,*p,6,4),p))
    elif action=="terrain_moat_castle":
        cx,cy=x0+w//2,y0+h//2
        core=max(1,min(w,h)//4)
        moat=max(1,min(w,h)//8)
        for x,y in region:
            distance=max(abs(x-cx),abs(y-cy))
            paint((x,y),floor if core<=distance<=core+moat else wall)
        # A physical causeway through the moat.
        for x in range(cx,x0+w):
            paint((x,cy),wall)
    elif action=="terrain_ruin_foundations":
        buildings=_integer(args,"buildings",1,128) if "buildings" in args else 8
        for _ in range(buildings):
            px=rng.randrange(x0,x0+w)
            py=rng.randrange(y0,y0+h)
            rw=min(w,2+rng.randrange(1,max(2,min(w,8))))
            rh=min(h,2+rng.randrange(1,max(2,min(h,8))))
            for x in range(px,min(x0+w,px+rw)):
                for y in range(py,min(y0+h,py+rh)):
                    if x in (px,px+rw-1) or y in (py,py+rh-1):
                        if rng.random()>.25:
                            paint((x,y),wall)
    elif action=="terrain_forest_clusters":
        centers=_integer(args,"clusters",1,64) if "clusters" in args else 6
        radius=_real(args,"radius",.5,32,4)
        for _ in range(centers):
            ax=rng.randrange(x0,x0+w)
            ay=rng.randrange(y0,y0+h)
            for x,y in region:
                if math.hypot(x-ax,y-ay)<=radius and rng.random()>.24:
                    paint((x,y),wall)
    elif action=="terrain_patch_scatter":
        count=_integer(args,"patches",1,256) if "patches" in args else 20
        radius=_integer(args,"radius",1,16) if "radius" in args else 2
        for _ in range(count):
            ax=rng.randrange(x0,x0+w)
            ay=rng.randrange(y0,y0+h)
            for x in range(ax-radius,ax+radius+1):
                for y in range(ay-radius,ay+radius+1):
                    if (x-ax)**2+(y-ay)**2<=radius**2:
                        paint((x,y),wall)
    elif action in ("terrain_wave_pattern","terrain_checker_rotated"):
        wavelength=_real(args,"wavelength",2,128,8)
        angle=math.radians(_real(args,"angle_deg",-360,360,30))
        cs,sn=math.cos(angle),math.sin(angle)
        for x,y in region:
            u=cs*(x-x0)-sn*(y-y0)
            v=sn*(x-x0)+cs*(y-y0)
            if action=="terrain_wave_pattern":
                bright=math.sin(u*2*math.pi/wavelength+math.sin(v/wavelength)*2)>0
            else:
                bright=(math.floor(u/wavelength)+math.floor(v/wavelength))%2==0
            paint((x,y),wall if bright else floor)
    elif action=="terrain_mountain_pass":
        for pt in region:
            paint(pt,wall)
        mid=(x0+w//2,y0+h//2)
        left=(x0,mid[1]);right=(x0+w-1,mid[1])
        def width():return _integer(args,"radius",0,8) if "radius" in args else 1
        for x in range(x0,x0+w):
            y=round(mid[1]+math.sin((x-x0)/max(1,w-1)*math.pi*2)*min(3,h/4))
            line((x,y),(x,y),floor,width())
    elif action=="terrain_archipelago_bridges":
        # Detect separate traversable islands and connect nearest shoreline.
        land={pt for pt in region if previous[pt]==wall}
        groups=components_local(land,region)
        if len(groups)<2:
            raise StudioError("bridge requires disconnected authored landmasses")
        for group in groups[1:]:
            current=groups[0]
            first,second=min(((p,q) for p in current for q in group),
                             key=lambda pq:(abs(pq[0][0]-pq[1][0])+
                                            abs(pq[0][1]-pq[1][1]),pq))
            line(first,second,wall)
            groups[0]|=group
    else:
        raise StudioError("unknown level topology algorithm")
    if written==previous:
        raise StudioError("terrain topology operation produced no authored change")
    data=list(layer.data)
    for (x,y),value in written.items():
        data[y*layer.width+x]=value
    return _replace_layer(project,index,replace(layer,data=tuple(data)))


def components_local(points,region):
    unseen=set(points)
    result=[]
    while unseen:
        start=next(iter(unseen))
        unseen.remove(start)
        reached={start}
        pending=[start]
        while pending:
            for neighbor in _neighbors(*pending.pop(),region):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    reached.add(neighbor)
                    pending.append(neighbor)
        result.append(reached)
    return sorted(result,key=lambda s:(-len(s),min(s)))
