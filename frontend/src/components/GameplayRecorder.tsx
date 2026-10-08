import React, { useCallback, useEffect, useRef, useState } from "react";

/**
 * Opt-in screen recording for gameplay study.
 * A direct user click triggers getDisplayMedia; the user chooses the screen.
 * The recording stays local until the user explicitly exports it or passes
 * it to an analysis handler. No automatic upload, background capture,
 * camera capture or microphone capture.
 */
export type GameplayRecording = {
  blob: Blob;
  mimeType: string;
  durationMs: number;
  capturedAt: string;
};

export type GameplayRecorderProps = {
  onRecordingReady?: (recording: GameplayRecording) => void;
  maxDurationSeconds?: number;
  disabled?: boolean;
};

type CaptureStatus = "idle" | "requesting" | "recording" | "ready" | "error";

const chooseMimeType = (): string => {
  if (typeof MediaRecorder === "undefined") return "";
  const types = [
    "video/webm;codecs=vp9",
    "video/webm;codecs=vp8",
    "video/webm",
    "video/mp4",
  ];
  return types.find(type => MediaRecorder.isTypeSupported(type)) || "";
};

export default function GameplayRecorder({
  onRecordingReady, maxDurationSeconds = 900, disabled = false,
}: GameplayRecorderProps) {
  const [status, setStatus] = useState<CaptureStatus>("idle");
  const [error, setError] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [recording, setRecording] = useState<GameplayRecording | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startedAtRef = useRef(0);
  const maxDuration = Math.max(1, Math.min(3600, maxDurationSeconds));
  const active = status === "recording" || status === "requesting";

  const stop = useCallback(() => {
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") recorder.stop();
    streamRef.current?.getTracks().forEach(track => track.stop());
    streamRef.current = null;
  }, []);

  useEffect(() => () => {
    const recorder = recorderRef.current;
    if (recorder) {
      recorder.ondataavailable = null;
      recorder.onstop = null;
      if (recorder.state !== "inactive") recorder.stop();
    }
    streamRef.current?.getTracks().forEach(track => track.stop());
  }, []);

  useEffect(() => {
    if (status !== "recording") return;
    const id = window.setInterval(() => {
      const seconds = Math.floor((performance.now() - startedAtRef.current) / 1000);
      setElapsed(seconds);
      if (seconds >= maxDuration) stop();
    }, 250);
    return () => window.clearInterval(id);
  }, [status, maxDuration, stop]);

  const start = async () => {
    if (disabled || active) return;
    setError("");
    setRecording(null);
    setElapsed(0);
    if (!navigator.mediaDevices?.getDisplayMedia ||
        typeof MediaRecorder === "undefined") {
      setError("Screen recording is not supported in this browser.");
      setStatus("error");
      return;
    }
    setStatus("requesting");
    let stream: MediaStream | null = null;
    try {
      // The browser presents its own screen/window/tab permission picker.
      stream = await navigator.mediaDevices.getDisplayMedia({
        video: { frameRate: { ideal: 15, max: 30 } },
        audio: false,
      });
      streamRef.current = stream;
      chunksRef.current = [];
      const mimeType = chooseMimeType();
      const recorder = mimeType ?
        new MediaRecorder(stream, { mimeType }) :
        new MediaRecorder(stream);
      recorderRef.current = recorder;
      const capturedAt = new Date().toISOString();
      recorder.ondataavailable = event => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onerror = () => {
        setError("The recording was interrupted.");
        setStatus("error");
        streamRef.current?.getTracks().forEach(track => track.stop());
      };
      recorder.onstop = () => {
        const durationMs = Math.max(1, Math.round(
          performance.now() - startedAtRef.current,
        ));
        const blob = new Blob(chunksRef.current, {
          type: recorder.mimeType || "video/webm",
        });
        streamRef.current?.getTracks().forEach(track => track.stop());
        streamRef.current = null;
        if (blob.size === 0) {
          setError("No gameplay frames were captured.");
          setStatus("error");
          return;
        }
        const result = {
          blob, mimeType: blob.type, durationMs, capturedAt,
        };
        setRecording(result);
        setStatus("ready");
        onRecordingReady?.(result);
      };
      stream.getVideoTracks().forEach(track => {
        track.addEventListener("ended", stop, { once: true });
      });
      startedAtRef.current = performance.now();
      recorder.start(1000);
      setStatus("recording");
    } catch (cause) {
      stream?.getTracks().forEach(track => track.stop());
      streamRef.current = null;
      setStatus("error");
      setError(cause instanceof Error ? cause.message : "Screen capture was cancelled.");
    }
  };

  const download = () => {
    if (!recording) return;
    const url = URL.createObjectURL(recording.blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `dragon-gameplay-${recording.capturedAt.replace(/[:.]/g, "-")}.webm`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return (
    <section aria-label="Dragon gameplay recording" style={{
      borderRadius: 18, border: "1px solid #b6d9c2",
      padding: 18, background: "#f5fbf6", color: "#29443a",
      fontFamily: "system-ui, sans-serif",
    }}>
      <h3 style={{margin:"0 0 8px"}}>Teach your dragon a game</h3>
      <p style={{fontSize:13, lineHeight:1.5}}>
        Choose a game window or screen. The dragon can learn mechanics
        from observations you approve. Recording is local and never
        starts without your permission. Audio is off.
      </p>
      <div role="status" aria-live="polite" style={{fontSize:13, marginBottom:12}}>
        {status === "recording" ?
          `Recording · ${elapsed}s / ${maxDuration}s` :
          status === "ready" ? "Recording ready for review" :
          status === "requesting" ? "Waiting for screen selection" :
          status === "error" ? error : "Not recording"}
      </div>
      <div style={{display:"flex", gap:8, flexWrap:"wrap"}}>
        {!active && (
          <button type="button" onClick={start} disabled={disabled}
            style={{borderRadius:10,padding:"9px 14px"}}>
            Start screen recording
          </button>
        )}
        {status === "recording" && (
          <button type="button" onClick={stop}
            style={{borderRadius:10,padding:"9px 14px"}}>
            Stop recording
          </button>
        )}
        {recording && status === "ready" && (
          <>
            <button type="button" onClick={download}
              style={{borderRadius:10,padding:"9px 14px"}}>
              Save recording
            </button>
            <button type="button" onClick={() => {
              setRecording(null);
              setStatus("idle");
            }} style={{borderRadius:10,padding:"9px 14px"}}>
              Discard
            </button>
          </>
        )}
      </div>
      <p style={{fontSize:12,opacity:.75}}>
        Stop sharing in your browser at any time. Avoid capturing passwords,
        private messages, copyrighted cinematics, or other people's data.
      </p>
    </section>
  );
}
