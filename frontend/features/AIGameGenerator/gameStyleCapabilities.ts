export type GameStyleDimension =
  | 'rendering'
  | 'palette'
  | 'silhouette'
  | 'lighting'
  | 'interface'
  | 'motion';

export type GameStyleId =
  | 'realistic'
  | 'stylized'
  | 'cartoon'
  | 'pixel'
  | 'anime'
  | 'minimalist'
  | 'retro'
  | 'modern'
  | 'neon'
  | 'hand_drawn';

export type MotionStyleId =
  | 'smooth'
  | 'snappy'
  | 'bouncy'
  | 'cinematic'
  | 'retro'
  | 'minimal'
  | 'fluid'
  | 'dynamic';

export interface GameStyleCapability {
  id: GameStyleId;
  label: string;
  summary: string;
  direction: Record<GameStyleDimension, string>;
  avoid: string[];
}

export interface MotionStyleCapability {
  id: MotionStyleId;
  label: string;
  summary: string;
  direction: string;
  avoid: string[];
}

export interface StyleDirection {
  visual: GameStyleCapability;
  motion?: MotionStyleCapability;
  prompt: string;
}

export const GAME_STYLE_CAPABILITIES: readonly GameStyleCapability[] = [
  {
    id: 'realistic',
    label: 'Realistic',
    summary: 'Grounded materials, natural proportions, and physically plausible lighting.',
    direction: {
      rendering: 'Use grounded materials, believable surface response, and restrained detail.',
      palette: 'Favor natural color relationships with controlled saturation.',
      silhouette: 'Keep proportions and object shapes physically credible and immediately readable.',
      lighting: 'Use motivated, physically plausible light with coherent shadow direction.',
      interface: 'Keep UI polished and restrained so it does not fight the world presentation.',
      motion: 'Favor believable weight, inertia, acceleration, and recovery.',
    },
    avoid: ['plastic-looking materials', 'unmotivated glow', 'exaggerated squash and stretch'],
  },
  {
    id: 'stylized',
    label: 'Stylized',
    summary: 'Strong authored shapes, simplified detail, and a cohesive exaggerated visual language.',
    direction: {
      rendering: 'Simplify secondary detail and exaggerate the forms that communicate identity.',
      palette: 'Use a deliberate authored palette with clear warm/cool and focal-point hierarchy.',
      silhouette: 'Push distinctive silhouettes while preserving gameplay readability.',
      lighting: 'Use graphic light and shadow groupings rather than noisy realism.',
      interface: 'Echo the same shape language and palette in icons, panels, and feedback.',
      motion: 'Use readable poses and controlled exaggeration to reinforce personality.',
    },
    avoid: ['generic asset-store realism', 'micro-detail that weakens shape language', 'mixed visual languages'],
  },
  {
    id: 'cartoon',
    label: 'Cartoon',
    summary: 'Bold silhouettes, expressive shapes, bright color, and playful readable feedback.',
    direction: {
      rendering: 'Use clean forms, soft or graphic shading, and expressive feature exaggeration.',
      palette: 'Prefer bright, harmonious colors with clear foreground/background separation.',
      silhouette: 'Make characters and effects readable from silhouette at gameplay distance.',
      lighting: 'Keep lighting simple and supportive of expression rather than photorealism.',
      interface: 'Use friendly iconography, rounded or expressive forms, and obvious state changes.',
      motion: 'Allow tasteful anticipation, overshoot, squash, and stretch for important actions.',
    },
    avoid: ['muddy values', 'tiny unreadable detail', 'realistic motion that feels lifeless against the art style'],
  },
  {
    id: 'pixel',
    label: 'Pixel Art',
    summary: 'Crisp pixel clusters, limited palettes, and deliberate sprite-scale readability.',
    direction: {
      rendering: 'Author crisp low-resolution forms with intentional pixel clusters and no accidental smoothing.',
      palette: 'Use a compact cohesive palette and reuse ramps consistently across assets.',
      silhouette: 'Prioritize sprite readability and strong clusters over fine detail.',
      lighting: 'Represent light with controlled value ramps and selective highlights.',
      interface: 'Align UI elements, borders, and icons to the pixel grid.',
      motion: 'Use intentional frame timing and strong key poses rather than interpolated blur.',
    },
    avoid: ['bilinear blur', 'sub-pixel wobble', 'inconsistent pixel density'],
  },
  {
    id: 'anime',
    label: 'Anime',
    summary: 'Graphic cel shading, expressive posing, clean silhouettes, and controlled impact effects.',
    direction: {
      rendering: 'Use clean line or edge language with cel-like value grouping and selective detail.',
      palette: 'Use clear local colors with purposeful accent colors for focal moments.',
      silhouette: 'Favor expressive posing, readable hair/clothing masses, and recognizable profiles.',
      lighting: 'Use graphic shadow shapes and selective rim or impact lighting.',
      interface: 'Use sharp, expressive presentation without sacrificing text legibility.',
      motion: 'Mix held poses, fast transitions, impact frames, and readable follow-through.',
    },
    avoid: ['indiscriminate bloom', 'overly noisy textures', 'constant extreme motion without pose readability'],
  },
  {
    id: 'minimalist',
    label: 'Minimalist',
    summary: 'Clean geometry, restrained color, strong negative space, and maximum signal per element.',
    direction: {
      rendering: 'Reduce assets to essential forms and remove decorative detail without gameplay value.',
      palette: 'Use a small neutral foundation with one or two purposeful accent families.',
      silhouette: 'Use simple geometric silhouettes with clear scale and hierarchy.',
      lighting: 'Prefer flat or very soft lighting with minimal visual noise.',
      interface: 'Use generous spacing, concise typography, and a strict information hierarchy.',
      motion: 'Animate only when motion communicates state, causality, or navigation.',
    },
    avoid: ['ornamental clutter', 'too many accent colors', 'motion with no informational purpose'],
  },
  {
    id: 'retro',
    label: 'Retro',
    summary: 'Arcade-era visual language with chunky forms, period-inspired UI, and controlled nostalgia.',
    direction: {
      rendering: 'Use simplified chunky forms and era-inspired texture or dithering where appropriate.',
      palette: 'Use saturated limited palettes with strong contrast and recognizable color ramps.',
      silhouette: 'Favor iconic shapes that remain legible at small display sizes.',
      lighting: 'Use simple highlights and graphic contrast rather than physically dense shading.',
      interface: 'Use arcade-inspired framing and typography while retaining modern accessibility.',
      motion: 'Favor stepped, frame-conscious, or deliberately mechanical timing where it reinforces the era.',
    },
    avoid: ['unreadable faux-CRT distortion', 'nostalgia effects over gameplay information', 'mixing incompatible retro eras accidentally'],
  },
  {
    id: 'modern',
    label: 'Modern',
    summary: 'Contemporary polish, clean hierarchy, layered depth, and subtle high-quality feedback.',
    direction: {
      rendering: 'Use clean high-fidelity forms with controlled detail and consistent material treatment.',
      palette: 'Use a cohesive contemporary palette with accessible contrast and restrained gradients.',
      silhouette: 'Keep forms clean, recognizable, and uncluttered across screen sizes.',
      lighting: 'Use subtle depth cues, soft shadows, and selective highlights.',
      interface: 'Use clear spacing, strong typography, clean iconography, and predictable interaction states.',
      motion: 'Use refined easing and short purposeful transitions that preserve responsiveness.',
    },
    avoid: ['gratuitous glass effects', 'low-contrast text', 'decorative animation that delays input'],
  },
  {
    id: 'neon',
    label: 'Neon',
    summary: 'Dark high-contrast foundations with luminous accents and carefully controlled emissive energy.',
    direction: {
      rendering: 'Use dark surfaces with selective emissive materials and sharp high-energy accents.',
      palette: 'Limit luminous hues to a coherent family so glow remains meaningful.',
      silhouette: 'Use rim light and emissive edges to preserve silhouettes against dark scenes.',
      lighting: 'Let emissive sources influence nearby surfaces without washing out values.',
      interface: 'Use luminous accents for focus and state, while keeping text and controls crisp.',
      motion: 'Use light trails and energy pulses selectively for speed, state changes, and impacts.',
    },
    avoid: ['full-screen bloom', 'glow around every element', 'contrast loss in dark scenes'],
  },
  {
    id: 'hand_drawn',
    label: 'Hand Drawn',
    summary: 'Illustrated linework, organic imperfections, textured fills, and a crafted tactile identity.',
    direction: {
      rendering: 'Use visible line character, textured fills, and intentional handmade variation.',
      palette: 'Use pigment-like color relationships with controlled texture and paper-friendly contrast.',
      silhouette: 'Preserve clean outer contours even when interior marks are expressive.',
      lighting: 'Suggest volume with illustrated hatching, washes, or simplified painted shadows.',
      interface: 'Carry the handcrafted language into borders, icons, and panels without hurting usability.',
      motion: 'Allow slight line boil or stepped illustration changes while keeping interactions stable.',
    },
    avoid: ['sterile vector perfection', 'texture over text', 'random wobble that reduces control precision'],
  },
] as const;

export const MOTION_STYLE_CAPABILITIES: readonly MotionStyleCapability[] = [
  {
    id: 'smooth',
    label: 'Smooth',
    summary: 'Continuous, polished movement with gentle acceleration and settling.',
    direction: 'Use coherent easing, continuous arcs, and approximately 180–320 ms UI transitions where appropriate.',
    avoid: ['abrupt snapping', 'inconsistent easing'],
  },
  {
    id: 'snappy',
    label: 'Snappy',
    summary: 'Immediate response with short transitions and decisive poses.',
    direction: 'Bias toward approximately 80–180 ms transitions, fast anticipation, and quick settling after input.',
    avoid: ['long decorative transitions', 'input latency hidden behind animation'],
  },
  {
    id: 'bouncy',
    label: 'Bouncy',
    summary: 'Playful spring motion with controlled overshoot and recovery.',
    direction: 'Use restrained spring timing, anticipation, overshoot, and secondary follow-through on high-value actions.',
    avoid: ['constant bouncing', 'overshoot that changes hit timing or control precision'],
  },
  {
    id: 'cinematic',
    label: 'Cinematic',
    summary: 'Staged motion, camera emphasis, and deliberate timing for high-impact moments.',
    direction: 'Use composed camera movement, stronger anticipation, and slower hero beats while preserving skip or control paths.',
    avoid: ['taking control too often', 'camera motion that obscures gameplay'],
  },
  {
    id: 'retro',
    label: 'Retro',
    summary: 'Frame-conscious, stepped motion inspired by classic sprite and arcade presentation.',
    direction: 'Use intentional frame holds, stepped transitions, and strong key poses instead of modern interpolation everywhere.',
    avoid: ['accidental jitter', 'mixed frame cadence without purpose'],
  },
  {
    id: 'minimal',
    label: 'Minimal',
    summary: 'Only functional motion needed to explain state and navigation.',
    direction: 'Prefer short fades, slides, and state transitions only when they improve comprehension.',
    avoid: ['ornamental loops', 'motion that competes with core content'],
  },
  {
    id: 'fluid',
    label: 'Fluid',
    summary: 'Momentum-preserving transitions with continuity between states.',
    direction: 'Carry velocity and spatial continuity through transitions so movement feels connected rather than reset.',
    avoid: ['hard discontinuities', 'teleporting visual states without feedback'],
  },
  {
    id: 'dynamic',
    label: 'Dynamic',
    summary: 'Energetic scale, camera, particles, and timing while preserving readability.',
    direction: 'Use contrast in timing, scale, parallax, particles, and impact emphasis around meaningful gameplay events.',
    avoid: ['constant maximum intensity', 'effects that hide targets or UI'],
  },
] as const;

const DEFAULT_VISUAL_STYLE: GameStyleId = 'realistic';
const DEFAULT_MOTION_STYLE: MotionStyleId = 'smooth';

export const getGameStyleCapability = (style: string): GameStyleCapability =>
  GAME_STYLE_CAPABILITIES.find(capability => capability.id === style) ??
  GAME_STYLE_CAPABILITIES.find(capability => capability.id === DEFAULT_VISUAL_STYLE)!;

export const getMotionStyleCapability = (style: string): MotionStyleCapability =>
  MOTION_STYLE_CAPABILITIES.find(capability => capability.id === style) ??
  MOTION_STYLE_CAPABILITIES.find(capability => capability.id === DEFAULT_MOTION_STYLE)!;

export const buildStyleDirection = (
  visualStyle: string,
  motionStyle?: string,
): StyleDirection => {
  const visual = getGameStyleCapability(visualStyle);
  const motion = motionStyle ? getMotionStyleCapability(motionStyle) : undefined;
  const dimensions = Object.entries(visual.direction)
    .map(([dimension, direction]) => `${dimension}: ${direction}`)
    .join(' ');
  const avoid = visual.avoid.length ? `Avoid: ${visual.avoid.join('; ')}.` : '';
  const motionDirection = motion
    ? ` Motion (${motion.label}): ${motion.direction} Avoid: ${motion.avoid.join('; ')}.`
    : '';

  return {
    visual,
    motion,
    prompt: `Visual style (${visual.label}): ${visual.summary} ${dimensions} ${avoid}${motionDirection}`.trim(),
  };
};

export const GAME_STYLE_IDS = GAME_STYLE_CAPABILITIES.map(capability => capability.id);
export const MOTION_STYLE_IDS = MOTION_STYLE_CAPABILITIES.map(capability => capability.id);
