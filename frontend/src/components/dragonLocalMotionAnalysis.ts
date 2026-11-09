import type { GameplayRecording } from "./GameplayRecorder";
import type { GameMechanicObservation } from "./DragonGameStudio";

/**
 * Local visual motion analyzer.
 *
 * Decodes the user's recording in-browser and samples low-resolution frames.
 * Detects scene-change and motion events only; it does NOT label combat,
 * platforming, puzzle solving or player enjoyment without a specialized
 * vision model and independent corroboration.
 */
export type MotionAnalysisPolicy = {
  sampleIntervalMs: number;
  maxSamples: number;
  width: number;
  height: number;
  sceneChangeThreshold: number;
};

export const DEFAULT_MOTION_POLICY: MotionAnalysisPolicy = {
  sampleIntervalMs: 500,
  maxSamples: 240,
  width: 64,
  height: 36,
  sceneChangeThreshold: 0.22,
};

export type MotionEvent = {
  timestampMs: number;
  changedPixelRatio: number;
  meanPixelDelta: number;
  sceneChange: boolean;
};

export type MotionAnalysis = {
  events: readonly MotionEvent[];
  framesAnalyzed: number;
  durationMs: number;
  warnings: readonly string[];
};

export async function analyzeMotionLocally(
  recording: GameplayRecording,
  policy: MotionAnalysisPolicy = DEFAULT_MOTION_POLICY,
): Promise<MotionAnalysis> {
  if (!Number.isInteger(policy.maxSamples) || policy.maxSamples < 2 ||
      policy.maxSamples > 1000 ||
      !Number.isInteger(policy.sampleIntervalMs) ||
      policy.sampleIntervalMs < 100 ||
      policy.sampleIntervalMs > 10000 ||
      !Number.isInteger(policy.width) || policy.width < 8 || policy.width > 256 ||
      !Number.isInteger(policy.height) || policy.height < 8 || policy.height > 256 ||
      !Number.isFinite(policy.sceneChangeThreshold) ||
      policy.sceneChangeThreshold <= 0 || policy.sceneChangeThreshold >= 1) {
    throw new Error("Invalid motion analysis budget");
  }
  if (!recording.blob.size || recording.durationMs <= 0) {
    throw new Error("Empty gameplay recording");
  }
  if (typeof document === "undefined") {
    throw new Error("Local video decoding requires a browser");
  }
  const url = URL.createObjectURL(recording.blob);
  const video = document.createElement("video");
  video.preload = "auto";
  video.muted = true;
  video.playsInline = true;
  video.src = url;
  const canvas = document.createElement("canvas");
  canvas.width = policy.width;
  canvas.height = policy.height;
  const context = canvas.getContext("2d", {willReadFrequently:true});
  if (!context) {
    URL.revokeObjectURL(url);
    throw new Error("Canvas video analysis is unavailable");
  }
  const waitFor = (event: string) => new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(() => {
      cleanup();
      reject(new Error(`Video decode timed out: ${event}`));
    }, 15000);
    const cleanup = () => {
      window.clearTimeout(timer);
      video.removeEventListener(event, success);
      video.removeEventListener("error", failure);
    };
    const success = () => {cleanup();resolve();};
    const failure = () => {cleanup();reject(new Error("Video decode failed"));};
    video.addEventListener(event, success, {once:true});
    video.addEventListener("error", failure, {once:true});
  });
  try {
    if (video.readyState < HTMLMediaElement.HAVE_METADATA) {
      await waitFor("loadedmetadata");
    }
    if (!Number.isFinite(video.duration) || video.duration <= 0) {
      throw new Error("Recording has invalid duration");
    }
    const totalMs = Math.min(recording.durationMs, video.duration * 1000);
    const frames = Math.min(
      policy.maxSamples,
      Math.ceil(totalMs / policy.sampleIntervalMs),
    );
    const events: MotionEvent[] = [];
    let previous: Uint8ClampedArray | null = null;
    for (let i = 0; i < frames; i++) {
      const ms = Math.min(
        totalMs - 1, i * policy.sampleIntervalMs,
      );
      if (ms < 0) break;
      const seconds = ms / 1000;
      if (Math.abs(video.currentTime - seconds) > 0.01) {
        const seeking = waitFor("seeked");
        video.currentTime = seconds;
        await seeking;
      }
      context.drawImage(video, 0, 0, policy.width, policy.height);
      const pixels = context.getImageData(
        0, 0, policy.width, policy.height,
      ).data;
      if (previous) {
        let changed = 0;
        let sum = 0;
        const count = policy.width * policy.height;
        for (let offset = 0; offset < pixels.length; offset += 4) {
          const delta = (
            Math.abs(pixels[offset] - previous[offset]) +
            Math.abs(pixels[offset + 1] - previous[offset + 1]) +
            Math.abs(pixels[offset + 2] - previous[offset + 2])
          ) / (3 * 255);
          sum += delta;
          if (delta > 0.12) changed++;
        }
        const ratio = changed / count;
        events.push({
          timestampMs: Math.round(ms),
          changedPixelRatio: Number(ratio.toFixed(4)),
          meanPixelDelta: Number((sum / count).toFixed(4)),
          sceneChange: ratio >= policy.sceneChangeThreshold,
        });
      }
      previous = new Uint8ClampedArray(pixels);
    }
    return {
      events,
      framesAnalyzed: frames,
      durationMs: totalMs,
      warnings: [
        "Motion is not proof of a particular gameplay mechanic.",
        "Camera cuts, menus and animation can resemble player actions.",
        "No player preferences can be inferred without user confirmation.",
      ],
    };
  } finally {
    video.pause();
    video.removeAttribute("src");
    video.load();
    URL.revokeObjectURL(url);
  }
}

/**
 * Conservative adapter for the studio's observation interface.
 * All motion events are labelled as unclassified scene changes.
 */
export async function discoverVisualEvents(
  recording: GameplayRecording,
): Promise<readonly GameMechanicObservation[]> {
  const result = await analyzeMotionLocally(recording);
  return result.events.filter(event => event.sceneChange).map(event => ({
    timestampMs: event.timestampMs,
    mechanic: "unclassified_visual_change",
    description: `Visual change: ${Math.round(
      event.changedPixelRatio * 100,
    )}% of sampled pixels changed. Mechanic classification needs review.`,
    confidence: Math.min(0.8, event.changedPixelRatio),
  }));
}
