/**
 * HoneypotPanel.jsx
 *
 * Per-host honeypot activation state.
 * Shows anomaly score bar (0–1) with a threshold marker at 0.7,
 * and a "DECOY ACTIVE" badge when honeypot_flags[host] is true.
 *
 * Note: the heuristic trigger is NOT the signaling game policy.
 * B_lineAgent ignores signals; this is a threshold-based heuristic.
 */
import React from "react";

const SUSPICION_THRESHOLD = 0.7;

const HOST_LABELS = {
  User0:       "User 0",
  User1:       "User 1",
  User2:       "User 2",
  Enterprise0: "Enterprise 0",
  Enterprise1: "Enterprise 1",
  Op_Server0:  "Op Server",
};

export default function HoneypotPanel({ state }) {
  if (!state) {
    return (
      <div className="panel-inner">
        <h3 className="panel-title">Deception / Honeypot</h3>
        <p className="panel-placeholder">Waiting for data…</p>
      </div>
    );
  }

  const hosts      = Object.keys(state.honeypot_flags ?? {});
  const scores     = state.anomaly_scores ?? {};
  const flags      = state.honeypot_flags ?? {};
  const note       = state.honeypot_note ?? "";
  const anyActive  = hosts.some((h) => flags[h]);

  return (
    <div className="panel-inner">
      <h3 className="panel-title">
        Deception / Honeypot
        {anyActive && (
          <span style={{ color: "#f59e0b", marginLeft: 8, fontSize: "0.6rem" }}>
            ⚠ DECOY ACTIVE
          </span>
        )}
      </h3>

      <div className="panel-content" style={{ overflowY: "auto" }}>
        {hosts.map((h) => {
          const score  = scores[h] ?? 0;
          const active = flags[h] ?? false;
          const pct    = Math.min(score * 100, 100);
          const barColor = active ? "#f59e0b" : score > SUSPICION_THRESHOLD ? "#f59e0b88" : "#22d3ee55";

          return (
            <div
              key={h}
              style={{
                marginBottom: "0.45rem",
                padding: "0.3rem 0.4rem",
                background: "#0f172a",
                border: "1px solid #1e293b",
                borderLeft: `3px solid ${active ? "#f59e0b" : "#1e293b"}`,
                borderRadius: 4,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.3rem" }}>
                <span style={{ fontSize: "0.72rem", color: "#e2e8f0", flex: 1 }}>
                  {HOST_LABELS[h] ?? h}
                </span>
                {active ? (
                  <span style={{
                    fontSize: "0.58rem", padding: "1px 5px", borderRadius: 2,
                    background: "rgba(245,158,11,0.2)", color: "#f59e0b",
                    fontWeight: "bold", letterSpacing: "0.06em",
                  }}>
                    DECOY ACTIVE
                  </span>
                ) : (
                  <span style={{ fontSize: "0.6rem", color: "#475569" }}>inactive</span>
                )}
              </div>

              {/* Score bar */}
              <div style={{ position: "relative", height: 6, background: "#1e293b", borderRadius: 3 }}>
                <div style={{
                  position: "absolute", left: 0, top: 0, height: "100%",
                  width: `${pct}%`, background: barColor, borderRadius: 3,
                  transition: "width 0.3s ease",
                }} />
                {/* Threshold marker at 70% */}
                <div style={{
                  position: "absolute", left: `${SUSPICION_THRESHOLD * 100}%`,
                  top: -2, bottom: -2, width: 1,
                  background: "#f59e0b", opacity: 0.6,
                }} />
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", marginTop: 2 }}>
                <span style={{ fontSize: "0.58rem", color: "#475569" }}>
                  score={score.toFixed(3)}
                </span>
                <span style={{ fontSize: "0.58rem", color: "#475569" }}>
                  thresh={SUSPICION_THRESHOLD}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {note && (
        <div style={{ fontSize: "0.58rem", color: "#475569", marginTop: "0.25rem", flexShrink: 0 }}>
          ⓘ {note}
        </div>
      )}
    </div>
  );
}
