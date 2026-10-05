import React, { useRef, useCallback, useEffect } from 'react';
import { View, PanResponder, StyleSheet, Text, TouchableOpacity, AppState } from 'react-native';
import { GLView } from 'expo-gl';
import { onMemoryPressure, effectiveLimits, reportFrameTime } from '../../utils/memoryGuard';
import { Renderer } from 'expo-three';
import { Ionicons } from '@expo/vector-icons';
import * as THREE from 'three';

type Part = { type: string; pos: number[]; size: number[]; color?: string; rot?: number[]; metalness?: number; roughness?: number; emissive?: number; decal?: boolean };

interface Props {
  geometry: Part[];
  palette: string[];
  partColors?: Record<number, string>;
  selectedPart?: number | null;
  surface?: { roughness?: number; metalness?: number; emissive?: number };
  vfx?: string;
  onSelectPart?: (index: number) => void;
  height?: number;
}

/**
 * Bleeding-edge three.js viewport (expo-gl) with FULL camera control:
 *  • single-finger drag → orbit (azimuth/polar)
 *  • two-finger pinch  → dolly zoom · two-finger drag → pan the target
 *  • on-screen + / − / reset buttons (works on web where pinch is unavailable)
 * Rendering: PBR MeshStandardMaterial, ACES tone-mapping + sRGB, PCF soft
 * shadows, hemisphere+key+fill+rim lights, gradient sky dome, ground grid,
 * MSAA ×4, gentle auto-rotate (pauses while interacting), tap-to-select mesh.
 * NOTE: full fidelity needs a real device / dev build (Expo Go / web is best-effort).
 */
export default function Construct3DView({
  geometry, palette, partColors, selectedPart, surface, vfx, onSelectPart, height = 320,
}: Props) {
  // Spherical orbit camera state.
  const MAX_RENDER_PX = 512;   // hard cap on the GL render buffer's long edge
  const MAX_PARTS = 80;        // hard cap on mesh count (bounds geometry VRAM)
  const cam = useRef({ theta: 0.9, phi: 1.15, radius: 17, tx: 0, ty: 2.4, tz: 0 });
  const inter = useRef({ touching: false, moved: false, tapX: 0, tapY: 0, pinch: 0, panX: 0, panY: 0 });
  const layout = useRef({ w: 1, h: 1 });
  const refs = useRef<{
    camera?: THREE.PerspectiveCamera; group?: THREE.Group; meshes: THREE.Mesh[];
    scene?: THREE.Scene; renderer?: any; gl?: any; raf?: number;
    alive: boolean; paused: boolean; last: number;
  }>({ meshes: [], alive: false, paused: false, last: 0 });

  const clampPhi = (p: number) => Math.max(0.18, Math.min(Math.PI / 2 + 0.25, p));
  const clampR = (r: number) => Math.max(6, Math.min(48, r));

  const resolveColor = useCallback((i: number, p: Part) => {
    if (partColors && partColors[i]) return partColors[i];
    if (palette && palette.length) return palette[i % palette.length];
    return p.color || '#999999';
  }, [partColors, palette]);

  const doTap = useCallback(() => {
    const { camera, meshes } = refs.current;
    if (!camera || !onSelectPart) return;
    const ndc = new THREE.Vector2(
      (inter.current.tapX / layout.current.w) * 2 - 1,
      -(inter.current.tapY / layout.current.h) * 2 + 1,
    );
    const ray = new THREE.Raycaster();
    ray.setFromCamera(ndc, camera);
    const hits = ray.intersectObjects(meshes, false);
    if (hits.length) {
      const idx = (hits[0].object as any).userData?.partIndex;
      if (typeof idx === 'number') onSelectPart(idx);
    }
  }, [onSelectPart]);

  const dist = (t: any[]) => {
    const dx = t[0].pageX - t[1].pageX; const dy = t[0].pageY - t[1].pageY;
    return Math.sqrt(dx * dx + dy * dy);
  };

  const pan = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: (e) => {
        inter.current.touching = true; inter.current.moved = false;
        inter.current.tapX = e.nativeEvent.locationX; inter.current.tapY = e.nativeEvent.locationY;
        inter.current.pinch = 0; inter.current.panX = 0; inter.current.panY = 0;
      },
      onPanResponderMove: (e, g) => {
        const touches = (e.nativeEvent as any).touches || [];
        if (touches.length >= 2) {
          inter.current.moved = true;
          const d = dist(touches);
          if (inter.current.pinch > 0) {
            cam.current.radius = clampR(cam.current.radius * (inter.current.pinch / d));
          }
          inter.current.pinch = d;
          // two-finger drag → pan target on camera's right/up
          const k = cam.current.radius * 0.0009;
          cam.current.tx -= g.vx * k * 4;
          cam.current.ty += g.vy * k * 4;
        } else {
          if (Math.abs(g.dx) + Math.abs(g.dy) > 6) inter.current.moved = true;
          cam.current.theta -= g.dx * 0.008;
          cam.current.phi = clampPhi(cam.current.phi - g.dy * 0.008);
        }
      },
      onPanResponderRelease: () => {
        if (!inter.current.moved) doTap();
        inter.current.touching = false; inter.current.pinch = 0;
      },
      onPanResponderTerminate: () => { inter.current.touching = false; inter.current.pinch = 0; },
    }),
  ).current;

  const zoom = (f: number) => { cam.current.radius = clampR(cam.current.radius * f); };
  const reset = () => { cam.current = { theta: 0.9, phi: 1.15, radius: 17, tx: 0, ty: 2.4, tz: 0 }; };

  const buildMesh = useCallback((p: Part, i: number): THREE.Mesh => {
    const [w, h, d] = p.size || [1, 1, 1];
    let geo: THREE.BufferGeometry;
    switch (p.type) {
      case 'cylinder': geo = new THREE.CylinderGeometry((w || 1) / 2, (w || 1) / 2, h || 1, 24); break;
      case 'cone': geo = new THREE.ConeGeometry((w || 1) / 2, h || 1, 26); break;
      case 'prism': geo = new THREE.ConeGeometry((Math.max(w, d) || 1) / 1.35, h || 1, 4); break;
      case 'sphere': geo = new THREE.SphereGeometry((w || 1) / 2, 28, 20); break;
      case 'torus': geo = new THREE.TorusGeometry((w || 1) / 2, (d || 0.2), 16, 36); break;
      case 'plane': geo = new THREE.BoxGeometry(w || 4, 0.12, d || 4); break;
      default: geo = new THREE.BoxGeometry(w || 1, h || 1, d || 1);
    }
    let col = 0x999999;
    try { col = new THREE.Color(resolveColor(i, p)).getHex(); } catch { /* default */ }
    const glow = ['glow', 'torchlight', 'embers', 'fog'].includes(vfx || '');
    const pEmis = typeof p.emissive === 'number' ? p.emissive : null;
    const baseEmis = glow ? 0.18 : 0.02;
    const mat = new THREE.MeshStandardMaterial({
      color: col,
      roughness: p.roughness ?? surface?.roughness ?? 0.7,
      metalness: p.metalness ?? surface?.metalness ?? 0.15,
      emissive: new THREE.Color(col).multiplyScalar(pEmis != null ? Math.max(0.25, pEmis) : baseEmis),
      emissiveIntensity: selectedPart === i ? 1.5 : (pEmis != null ? Math.max(0.5, pEmis * 1.4) : (glow ? 0.6 : 0.25)),
    });
    const mesh = new THREE.Mesh(geo, mat);
    const [x, y, z] = p.pos || [0, 0, 0];
    mesh.position.set(x, y, z);
    if (p.rot && p.rot.length === 3) mesh.rotation.set(p.rot[0], p.rot[1], p.rot[2]);
    mesh.castShadow = true; mesh.receiveShadow = true;
    mesh.userData.partIndex = i;
    if (selectedPart === i) mesh.scale.setScalar(1.05);
    return mesh;
  }, [resolveColor, surface, vfx, selectedPart]);

  // ── Aggressive GPU cleanup (prevents VRAM leak / OOM crash on S20) ──────
  const disposeGroup = useCallback(() => {
    const r = refs.current;
    if (r.group) {
      r.group.traverse((o: any) => {
        if (o.geometry) { try { o.geometry.dispose(); } catch {} }
        const m = o.material;
        if (m) (Array.isArray(m) ? m : [m]).forEach((mm: any) => { try { mm.dispose(); } catch {} });
      });
      try { r.scene?.remove(r.group); } catch {}
    }
    r.group = undefined; r.meshes = [];
  }, []);

  const rebuildGroup = useCallback(() => {
    const r = refs.current;
    if (!r.scene) return; // context not ready yet — initial build happens in onContextCreate
    disposeGroup();
    const group = new THREE.Group();
    const meshes: THREE.Mesh[] = [];
    (geometry || []).slice(0, effectiveLimits().maxParts).forEach((p, i) => { const m = buildMesh(p, i); group.add(m); meshes.push(m); });
    r.scene.add(group);
    r.group = group; r.meshes = meshes;
  }, [geometry, buildMesh, disposeGroup]);

  const disposeScene = useCallback(() => {
    const r = refs.current;
    r.alive = false;
    if (r.raf != null) { try { cancelAnimationFrame(r.raf); } catch {} r.raf = undefined; }
    try {
      r.scene?.traverse((o: any) => {
        if (o.geometry) { try { o.geometry.dispose(); } catch {} }
        const m = o.material;
        if (m) (Array.isArray(m) ? m : [m]).forEach((mm: any) => {
          ['map', 'normalMap', 'roughnessMap', 'metalnessMap', 'emissiveMap', 'aoMap'].forEach(k => { try { mm[k]?.dispose?.(); } catch {} });
          try { mm.dispose(); } catch {}
        });
      });
    } catch {}
    try { r.renderer?.dispose?.(); } catch {}
    try { r.renderer?.forceContextLoss?.(); } catch {}
    try { r.gl?.getExtension?.('WEBGL_lose_context')?.loseContext?.(); } catch {}
    r.scene = undefined; r.renderer = undefined; r.gl = undefined;
    r.group = undefined; r.camera = undefined; r.meshes = [];
  }, []);

  const onContextCreate = useCallback(async (gl: any) => {
    try {
      const rawW = gl.drawingBufferWidth || 1, rawH = gl.drawingBufferHeight || 1;
      // SAFE, tier+stress-aware render-buffer cap (lower edge under pressure) —
      // bounds GPU/VRAM/thermal on low-end devices. Aspect kept via camera.
      const lim = effectiveLimits();
      const sc = Math.min(1, lim.maxRenderPx / Math.max(rawW, rawH));
      const width = Math.max(1, Math.round(rawW * sc));
      const dh = Math.max(1, Math.round(rawH * sc));
      layout.current = { w: rawW, h: rawH };
      const renderer = new Renderer({ gl, antialias: lim.antialias });
      renderer.setSize(width, dh);
      refs.current.gl = gl; refs.current.renderer = renderer;
      (renderer as any).outputColorSpace = THREE.SRGBColorSpace;
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.18;
      renderer.shadowMap.enabled = lim.shadows;
      renderer.shadowMap.type = THREE.PCFSoftShadowMap;

      const scene = new THREE.Scene();
      refs.current.scene = scene;
      scene.fog = new THREE.Fog(0x0a0f1c, 28, 70);

      const sky = new THREE.Mesh(
        new THREE.SphereGeometry(80, 32, 16),
        new THREE.ShaderMaterial({
          side: THREE.BackSide, depthWrite: false,
          uniforms: { top: { value: new THREE.Color('#243657') }, bot: { value: new THREE.Color('#060a12') } },
          vertexShader: 'varying vec3 vP; void main(){ vP=position; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }',
          fragmentShader: 'varying vec3 vP; uniform vec3 top; uniform vec3 bot; void main(){ float h=clamp(normalize(vP).y*0.5+0.5,0.0,1.0); gl_FragColor=vec4(mix(bot,top,pow(h,0.85)),1.0); }',
        }),
      );
      scene.add(sky);

      const camera = new THREE.PerspectiveCamera(46, width / dh, 0.1, 1000);
      refs.current.camera = camera;

      scene.add(new THREE.HemisphereLight(0xbcd3ff, 0x33304a, 0.9));
      const key = new THREE.DirectionalLight(0xffffff, 2.1);
      key.position.set(9, 17, 10); key.castShadow = true;
      key.shadow.mapSize.set(1536, 1536);
      Object.assign(key.shadow.camera, { left: -16, right: 16, top: 16, bottom: -16, near: 1, far: 70 });
      key.shadow.bias = -0.0004; scene.add(key);
      const fill = new THREE.DirectionalLight(0x88aaff, 0.55); fill.position.set(-10, 6, -7); scene.add(fill);
      const rim = new THREE.DirectionalLight(0xffe6b0, 0.75); rim.position.set(0, 7, -13); scene.add(rim);

      const ground = new THREE.Mesh(
        new THREE.CircleGeometry(20, 56),
        new THREE.MeshStandardMaterial({ color: 0x141c2e, roughness: 0.96, metalness: 0.0 }),
      );
      ground.rotation.x = -Math.PI / 2; ground.position.y = -0.06; ground.receiveShadow = true;
      scene.add(ground);
      const grid = new THREE.GridHelper(40, 40, 0x2a3a5a, 0x1a2438);
      (grid.material as any).opacity = 0.35; (grid.material as any).transparent = true;
      grid.position.y = -0.04; scene.add(grid);

      const group = new THREE.Group();
      const meshes: THREE.Mesh[] = [];
      (geometry || []).slice(0, lim.maxParts).forEach((p, i) => { const m = buildMesh(p, i); group.add(m); meshes.push(m); });
      scene.add(group);
      refs.current.group = group; refs.current.meshes = meshes;

      const target = new THREE.Vector3();
      const sph = new THREE.Spherical();
      refs.current.alive = true; refs.current.last = 0;
      const FRAME_MS = lim.frameMs; // tier+stress fps cap → lower CPU/GPU/thermal
      const render = (t: number) => {
        if (!refs.current.alive) return;              // hard stop after dispose
        refs.current.raf = requestAnimationFrame(render);
        if (refs.current.paused) return;              // paused in background
        const dt = t - refs.current.last;
        if (dt < FRAME_MS) return;                    // throttle
        reportFrameTime(dt, FRAME_MS);                // thermal/CPU proxy → stress
        refs.current.last = t;
        if (!inter.current.touching) cam.current.theta += 0.0026;
        sph.set(cam.current.radius, cam.current.phi, cam.current.theta);
        const off = new THREE.Vector3().setFromSpherical(sph);
        target.set(cam.current.tx, cam.current.ty, cam.current.tz);
        camera.position.copy(target).add(off);
        camera.lookAt(target);
        try { renderer.render(scene, camera); gl.endFrameEXP(); }
        catch { refs.current.alive = false; }         // context lost → stop cleanly
      };
      refs.current.raf = requestAnimationFrame(render);
    } catch { /* non-GL env fallback */ }
  }, [geometry, buildMesh]);

  const hasGeo = (geometry || []).length > 0;

  // Rebuild meshes IN-PLACE when the spec changes — no GLView remount (the old
  // dynamic `key` leaked a fresh GL context + render loop on every change).
  useEffect(() => { rebuildGroup(); }, [rebuildGroup]);
  // Pause loop in background; fully dispose GPU resources on unmount.
  useEffect(() => {
    const sub = AppState.addEventListener('change', s => { refs.current.paused = s !== 'active'; });
    return () => { try { sub.remove(); } catch {} disposeScene(); };
  }, [disposeScene]);
  // Dispose when the asset is cleared (viewport returns to empty state).
  useEffect(() => { if (!hasGeo) disposeScene(); }, [hasGeo, disposeScene]);
  // OOM guardrail: when the OS signals memory pressure, pause GPU work for a
  // few seconds (sheds rendering load during the danger window, auto-resumes).
  useEffect(() => onMemoryPressure(() => {
    refs.current.paused = true;
    setTimeout(() => { refs.current.paused = false; }, 4000);
  }), []);

  // Strict lazy-init: viewport stays EMPTY (no GL context, no render loop)
  // until an asset is actually selected — saves RAM + GPU on the catalog grid.
  if (!hasGeo) {
    return (
      <View style={[styles.wrap, styles.empty, { height }]}>
        <Ionicons name="cube-outline" size={34} color="#3a4a6a" />
        <Text style={styles.emptyText}>Select an asset to load the 3D viewport</Text>
      </View>
    );
  }

  return (
    <View
      style={[styles.wrap, { height }]}
      onLayout={(e) => { layout.current = { w: e.nativeEvent.layout.width, h: e.nativeEvent.layout.height }; }}
      {...pan.panHandlers}
    >
      <GLView style={StyleSheet.absoluteFill} msaaSamples={4} onContextCreate={onContextCreate} />
      <View style={[styles.controls, { pointerEvents: 'box-none' }]}>
        <TouchableOpacity style={styles.ctrlBtn} onPress={() => zoom(0.82)} testID="cf-zoom-in"><Ionicons name="add" size={20} color="#fff" /></TouchableOpacity>
        <TouchableOpacity style={styles.ctrlBtn} onPress={() => zoom(1.22)} testID="cf-zoom-out"><Ionicons name="remove" size={20} color="#fff" /></TouchableOpacity>
        <TouchableOpacity style={styles.ctrlBtn} onPress={reset} testID="cf-cam-reset"><Ionicons name="scan-outline" size={17} color="#fff" /></TouchableOpacity>
      </View>
      <Text style={styles.hint}>drag · pinch zoom · 2-finger pan{onSelectPart ? ' · tap a part' : ''}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { width: '100%', borderRadius: 14, overflow: 'hidden', backgroundColor: '#060a12' },
  empty: { alignItems: 'center', justifyContent: 'center', gap: 10, borderWidth: 1, borderColor: '#1a2438' },
  emptyText: { color: '#5a6a8a', fontSize: 12, fontWeight: '700' },
  controls: { position: 'absolute', top: 10, right: 10, gap: 8 },
  ctrlBtn: { width: 38, height: 38, borderRadius: 19, backgroundColor: '#0008', borderWidth: 1, borderColor: '#ffffff22', alignItems: 'center', justifyContent: 'center' },
  hint: { position: 'absolute', bottom: 6, left: 10, color: '#ffffff77', fontSize: 10, fontWeight: '700' },
});
