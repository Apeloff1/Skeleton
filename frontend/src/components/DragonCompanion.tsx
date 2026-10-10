import React, { useEffect, useMemo, useState } from "react";

/**
 * Baby Dragon research companion.
 *
 * The UI consumes authoritative progress from the companion runtime.
 * It does not simulate completed crawls, approval or memory writes.
 * Reduced-motion preferences disable continuous decorative animation.
 */
export type DragonPhase =
  | "nesting" | "listening" | "searching" | "acquiring"
  | "burning" | "distilling" | "verifying" | "awaiting_approval"
  | "remembering" | "resting" | "error";

export type DragonFrame = {
  phase: DragonPhase;
  mood: string;
  egg: { half_hatched: boolean; hat: boolean };
  glasses: { visible: boolean; white_tape: boolean };
  fire: { visible: boolean; sparks: number };
  progress: number;
  topic: string;
  accessible_status: string;
};

export type DragonCompanionProps = {
  frame: DragonFrame;
  onResearch?: (topic: string) => void;
  onApprove?: () => void;
  onRest?: () => void;
  disabled?: boolean;
};

const COLORS = {
  shell: "#f6e4c7",
  shellShade: "#e3c7a6",
  dragon: "#8ec9a0",
  dragonShade: "#5fa980",
  belly: "#f5d9b8",
  ink: "#394a47",
  flame: "#ff9c57",
};

export default function DragonCompanion({
  frame, onResearch, onApprove, onRest, disabled = false,
}: DragonCompanionProps) {
  const [topic, setTopic] = useState("");
  const [reducedMotion, setReducedMotion] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReducedMotion(query.matches);
    sync();
    query.addEventListener?.("change", sync);
    return () => query.removeEventListener?.("change", sync);
  }, []);
  const busy = [
    "searching", "acquiring", "burning", "distilling",
    "verifying", "remembering",
  ].includes(frame.phase);
  const label = useMemo(() => {
    if (frame.phase === "awaiting_approval") return "Review needed";
    if (frame.phase === "error") return "Research interrupted";
    return frame.accessible_status;
  }, [frame.phase, frame.accessible_status]);
  const pct = Math.max(0, Math.min(100, Math.round(frame.progress * 100)));
  return (
    <section
      aria-label="Baby dragon research companion"
      style={{
        maxWidth: 440, margin: "0 auto", borderRadius: 26,
        padding: 22, background: "linear-gradient(145deg,#fff9f0,#e9f6ed)",
        color: COLORS.ink, boxShadow: "0 18px 48px #29463b20",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <style>{`
        @keyframes dragonBreathe { 0%,100% {transform:translateY(0)}
          50% {transform:translateY(-7px)} }
        @keyframes dragonSpark { 0% {opacity:0;transform:translateY(12px) scale(.4)}
          40% {opacity:1} 100% {opacity:0;transform:translateY(-45px) scale(1.2)} }
        @keyframes dragonBlink { 0%,44%,48%,100% {transform:scaleY(1)}
          46% {transform:scaleY(.08)} }
        @keyframes dragonFloat { 0%,100% {transform:rotate(-2deg)}
          50% {transform:rotate(3deg)} }
      `}</style>
      <div style={{ textAlign: "center" }}>
        <div style={{ fontSize: 12, letterSpacing: 2, fontWeight: 750 }}>
          YOUR LITTLE RESEARCH DRAGON
        </div>
        <div
          role="img"
          aria-label={`Baby dragon in a half-hatched egg. ${label}`}
          style={{
            height: 285, position: "relative", overflow: "hidden",
            display: "flex", justifyContent: "center", alignItems: "center",
          }}
        >
          <svg
            width="290" height="260" viewBox="0 0 290 260"
            aria-hidden="true"
            style={{
              overflow: "visible",
              animation: reducedMotion ? "none" :
                "dragonBreathe 3.8s ease-in-out infinite",
            }}
          >
            <ellipse cx="145" cy="238" rx="102" ry="13" fill="#b4cdbd" opacity=".35" />
            <path d="M74 130Q43 191 83 228Q145 255 209 228Q247 183 216 130Z"
              fill={COLORS.shell} stroke={COLORS.shellShade} strokeWidth="5" />
            <path d="M74 130l20 13 15-17 18 17 18-18 17 19 18-17 18 16 18-13"
              fill="none" stroke="#d7b997" strokeWidth="6" strokeLinejoin="round" />
            <path d="M98 122Q70 97 91 73L113 94M192 121Q219 97 201 73L178 93"
              fill={COLORS.dragonShade} />
            <ellipse cx="145" cy="132" rx="67" ry="82" fill={COLORS.dragon}
              stroke={COLORS.dragonShade} strokeWidth="4" />
            <ellipse cx="145" cy="171" rx="42" ry="45" fill={COLORS.belly} />
            <path d="M90 129Q61 140 71 177Q79 193 101 173M200 129Q229 140 219 177Q211 193 189 173"
              fill={COLORS.dragon} stroke={COLORS.dragonShade} strokeWidth="4" />
            <path d="M107 61L117 30L132 54L148 24L161 54L178 31L187 64"
              fill={COLORS.dragonShade} />
            <ellipse cx="121" cy="113" rx="8" ry="12" fill={COLORS.ink}
              style={{transformOrigin:"121px 113px",
                animation:reducedMotion?"none":"dragonBlink 6s infinite"}} />
            <ellipse cx="169" cy="113" rx="8" ry="12" fill={COLORS.ink}
              style={{transformOrigin:"169px 113px",
                animation:reducedMotion?"none":"dragonBlink 6s infinite"}} />
            <circle cx="118" cy="109" r="3" fill="white" />
            <circle cx="166" cy="109" r="3" fill="white" />
            <ellipse cx="100" cy="135" rx="12" ry="6" fill="#efad9d" opacity=".65" />
            <ellipse cx="190" cy="135" rx="12" ry="6" fill="#efad9d" opacity=".65" />
            <path d="M135 142Q145 154 155 142" fill="none"
              stroke={COLORS.ink} strokeWidth="3" strokeLinecap="round" />
            {frame.egg.hat && (
              <g transform="rotate(-11 143 45)">
                <path d="M105 56L113 24 133 33 145 14 160 34 181 23 188 57Z"
                  fill={COLORS.shell} stroke={COLORS.shellShade} strokeWidth="4" />
                <path d="M105 56Q144 67 188 57" fill="none"
                  stroke={COLORS.shellShade} strokeWidth="4" />
              </g>
            )}
            {frame.glasses.visible && (
              <g stroke={COLORS.ink} strokeWidth="4" fill="#dff5f4" fillOpacity=".35">
                <rect x="100" y="100" width="38" height="30" rx="10" />
                <rect x="152" y="100" width="38" height="30" rx="10" />
                <path d="M138 108Q145 102 152 108" fill="none" />
                {frame.glasses.white_tape && (
                  <rect x="141" y="99" width="9" height="18" rx="2"
                    fill="#fff" stroke="#fff" strokeWidth="1"
                    transform="rotate(8 145 108)" />
                )}
              </g>
            )}
            {frame.fire.visible && (
              <g style={{animation:reducedMotion?"none":"dragonFloat 1.4s infinite"}}>
                <path d="M145 152Q117 185 146 210Q178 189 159 168Q159 185 149 183Z"
                  fill={COLORS.flame} />
                <path d="M146 177Q136 195 149 207Q161 195 152 186Z"
                  fill="#ffe5a0" />
              </g>
            )}
          </svg>
          {frame.fire.visible && !reducedMotion && Array.from({
            length: Math.min(12, frame.fire.sparks),
          }, (_, i) => (
            <span key={i} aria-hidden="true" style={{
              position: "absolute", left: `${28 + (i * 17) % 44}%`,
              top: `${48 + (i * 11) % 25}%`,
              width: 5, height: 5, borderRadius: "50%",
              background: i % 2 ? "#f6c35c" : "#ff8d69",
              animation: `dragonSpark ${1.1 + i * .09}s ${i * .13}s infinite`,
            }} />
          ))}
        </div>
        <p aria-live="polite" style={{fontWeight: 700, margin: "0 0 8px"}}>{label}</p>
        {frame.topic && (
          <p style={{fontSize: 13, margin: "0 0 12px", opacity: .8}}>
            Curious about: {frame.topic}
          </p>
        )}
        <div
          role="progressbar" aria-label="Research progress"
          aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}
          style={{height: 8, borderRadius: 8, background: "#d9e6dc",
            overflow: "hidden", marginBottom: 8}}
        >
          <div style={{
            width: `${pct}%`, height: "100%", borderRadius: 8,
            background: COLORS.dragonShade, transition: reducedMotion ?
              "none" : "width .4s ease",
          }} />
        </div>
        <div style={{fontSize: 12, opacity: .7, marginBottom: 16}}>
          {pct}% · {frame.phase.replaceAll("_", " ")}
        </div>
        {onResearch && (
          <form onSubmit={e => {
            e.preventDefault();
            if (!disabled && !busy && topic.trim().length >= 2) {
              onResearch(topic.trim());
            }
          }} style={{display:"flex", gap:8, marginBottom:12}}>
            <input aria-label="Research topic" value={topic}
              onChange={e=>setTopic(e.target.value)}
              placeholder="What should I learn about?"
              maxLength={240} disabled={disabled || busy}
              style={{flex:1, minWidth:0, padding:"11px 13px",
                border:"1px solid #bad4c4", borderRadius:12}} />
            <button type="submit" disabled={disabled || busy || topic.trim().length < 2}
              style={{padding:"11px 16px", border:0, borderRadius:12,
                background:COLORS.dragonShade, color:"white", fontWeight:700}}>
              Explore
            </button>
          </form>
        )}
        {frame.phase === "awaiting_approval" && onApprove && (
          <button type="button" disabled={disabled} onClick={onApprove}
            style={{padding:"10px 16px", borderRadius:12,
              background:"#f0d8ac", border:"1px solid #c8a46c"}}>
            Review evidence
          </button>
        )}
        {onRest && !busy && (
          <button type="button" disabled={disabled} onClick={onRest}
            style={{marginLeft:8, padding:"10px 16px", borderRadius:12,
              background:"transparent", border:"1px solid #bad4c4"}}>
            Snuggle & rest
          </button>
        )}
      </div>
    </section>
  );
}
