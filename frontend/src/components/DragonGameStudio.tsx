import React, { useCallback, useState } from "react";
import DragonCompanion, { type DragonFrame } from "./DragonCompanion";
import GameplayRecorder, { type GameplayRecording } from "./GameplayRecorder";

/**
 * Dragon studio: explicit user-mediated bridge from screen capture to
 * mechanics analysis and game taste review.
 *
 * No invented vision inference. A host-provided analyzer must return
 * timestamped observations. A user must approve individual preferences
 * before the host persists them or sends them to the game builder.
 */
export type GameMechanicObservation = {
  timestampMs: number;
  mechanic: string;
  description: string;
  confidence: number;
};

export type TasteDecision = "enjoyed" | "disliked" | "neutral" | "unknown";

export type ReviewedMechanic = GameMechanicObservation & {
  preference: TasteDecision;
  userConfirmed: boolean;
};

export type DragonGameStudioProps = {
  frame: DragonFrame;
  analyzeRecording: (recording: GameplayRecording) =>
    Promise<readonly GameMechanicObservation[]>;
  onApproveObservations: (observations: readonly ReviewedMechanic[]) =>
    Promise<void>;
  onResearch?: (topic: string) => void;
  onRest?: () => void;
};

const validObservation = (
  value: GameMechanicObservation,
  durationMs: number,
): boolean =>
  Number.isFinite(value.timestampMs) &&
  value.timestampMs >= 0 &&
  value.timestampMs <= durationMs &&
  typeof value.mechanic === "string" &&
  value.mechanic.length > 0 &&
  value.mechanic.length <= 80 &&
  typeof value.description === "string" &&
  value.description.length > 0 &&
  value.description.length <= 500 &&
  Number.isFinite(value.confidence) &&
  value.confidence >= 0 && value.confidence <= 1;

export default function DragonGameStudio({
  frame, analyzeRecording, onApproveObservations, onResearch, onRest,
}: DragonGameStudioProps) {
  const [recording, setRecording] = useState<GameplayRecording | null>(null);
  const [observations, setObservations] = useState<ReviewedMechanic[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [approved, setApproved] = useState(false);

  const analyze = useCallback(async () => {
    if (!recording || busy) return;
    setBusy(true);
    setError("");
    setApproved(false);
    try {
      const result = await analyzeRecording(recording);
      if (!Array.isArray(result) || result.length > 2000 ||
          !result.every(x => validObservation(x, recording.durationMs))) {
        throw new Error("Analyzer returned invalid gameplay observations");
      }
      setObservations(result.map(x => ({
        ...x, preference: "unknown", userConfirmed: false,
      })));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Analysis failed");
    } finally {
      setBusy(false);
    }
  }, [recording, analyzeRecording, busy]);

  const decide = (index: number, preference: TasteDecision) => {
    setApproved(false);
    setObservations(items => items.map((item, i) =>
      i === index ? {
        ...item, preference,
        userConfirmed: preference !== "unknown",
      } : item,
    ));
  };

  const approve = async () => {
    if (busy || !observations.length) return;
    setBusy(true);
    setError("");
    try {
      await onApproveObservations(observations);
      setApproved(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Approval failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{
      display:"grid", gap:18, maxWidth:900,
      margin:"0 auto", fontFamily:"system-ui, sans-serif",
    }}>
      <DragonCompanion frame={frame} onResearch={onResearch} onRest={onRest}/>
      <GameplayRecorder
        disabled={busy}
        onRecordingReady={value => {
          setRecording(value);
          setObservations([]);
          setApproved(false);
          setError("");
        }}
      />
      {recording && (
        <section style={{padding:18,border:"1px solid #b6d9c2",borderRadius:16}}>
          <h3>Review your recording</h3>
          <p>
            The selected recording remains local unless the connected analyzer
            explicitly transfers it. Review that analyzer's privacy policy
            before continuing.
          </p>
          <button type="button" onClick={analyze} disabled={busy}>
            {busy ? "Processing…" : "Analyze game mechanics"}
          </button>
        </section>
      )}
      {observations.length > 0 && (
        <section aria-label="Mechanics and taste review"
          style={{padding:18,border:"1px solid #b6d9c2",borderRadius:16}}>
          <h3>What did you actually enjoy?</h3>
          <p>
            Observations are hypotheses, not proof of your preferences.
            Choose your response for each mechanic.
          </p>
          <ul style={{listStyle:"none",padding:0,display:"grid",gap:12}}>
            {observations.map((item, index) => (
              <li key={index} style={{
                border:"1px solid #d3dfd8",borderRadius:12,padding:12,
              }}>
                <strong>{item.mechanic.replaceAll("_", " ")}</strong>
                <p>{item.description}</p>
                <small>
                  {(item.timestampMs / 1000).toFixed(1)}s ·
                  confidence {(item.confidence * 100).toFixed(0)}%
                </small>
                <div>
                  <label htmlFor={`dragon-taste-${index}`}> Your preference: </label>
                  <select
                    id={`dragon-taste-${index}`}
                    value={item.preference}
                    onChange={e => decide(index, e.target.value as TasteDecision)}
                  >
                    <option value="unknown">Not sure</option>
                    <option value="enjoyed">Enjoyed</option>
                    <option value="disliked">Disliked</option>
                    <option value="neutral">Neutral</option>
                  </select>
                </div>
              </li>
            ))}
          </ul>
          <button type="button" disabled={busy || approved} onClick={approve}>
            {approved ? "Review saved" : "Approve mechanics and taste"}
          </button>
        </section>
      )}
      {error && <p role="alert" style={{color:"#a32929"}}>{error}</p>}
      {approved && <p role="status">
        Your reviewed observations were accepted by the connected host.
      </p>}
    </div>
  );
}
