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
        <div className="panel-header">
          <span className="panel-title">Deception / Honeypot</span>
        </div>
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
      <div className="panel-header">
        <span className="panel-title">Deception / Honeypot</span>
        {anyActive && <span className="panel-tag" style={{ color: "var(--warn)" }}>⚠ DECOY ACTIVE</span>}
      </div>

      <div className="panel-body" style={{ overflowY: "auto" }}>
        {hosts.length === 0 && (
          <p className="panel-placeholder">No host data</p>
        )}
        {hosts.map((h) => {
          const score  = scores[h] ?? 0;
          const active = flags[h] ?? false;
          const pct    = Math.min(score * 100, 100);
          const barColor = active
            ? "var(--warn)"
            : score > SUSPICION_THRESHOLD
              ? "var(--warn-dim)"
              : "var(--ok-dim)";

          return (
            <div
              key={h}
              style={{
                marginBottom: "0.4rem",
                padding: "6px 10px",
                background: "var(--panel-2)",
                borderLeft: `3px solid ${active ? "var(--warn)" : "var(--line)"}`,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.3rem" }}>
                <span style={{ fontFamily: "var(--font)", fontWeight: 600, fontSize: "0.72rem", color: "var(--fg)", flex: 1 }}>
                  {HOST_LABELS[h] ?? h}
                </span>
                {active ? (
                  <span style={{
                    fontFamily: "var(--mono)", fontSize: "0.54rem", padding: "1px 5px", borderRadius: 2,
                    background: "var(--warn-dim)", color: "var(--warn)",
                    fontWeight: "500", letterSpacing: "0.06em",
                  }}>
                    DECOY
                  </span>
                ) : (
                  <span style={{ fontFamily: "var(--mono)", fontSize: "0.58rem", color: "var(--fg-3)" }}>inactive</span>
                )}
              </div>

              <div style={{ position: "relative", height: 4, background: "var(--line)", borderRadius: 2 }}>
                <div style={{
                  position: "absolute", left: 0, top: 0, height: "100%",
                  width: `${pct}%`, background: barColor, borderRadius: 2,
                  transition: "width 0.3s ease",
                }} />
                <div style={{
                  position: "absolute", left: `${SUSPICION_THRESHOLD * 100}%`,
                  top: -2, bottom: -2, width: 1,
                  background: "var(--warn)", opacity: 0.5,
                }} />
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", marginTop: 3 }}>
                <span style={{ fontFamily: "var(--mono)", fontSize: "0.56rem", color: "var(--fg-3)" }}>
                  {score.toFixed(3)}
                </span>
                <span style={{ fontFamily: "var(--mono)", fontSize: "0.56rem", color: "var(--fg-3)" }}>
                  thresh {SUSPICION_THRESHOLD}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {note && (
        <div style={{ fontFamily: "var(--mono)", fontSize: "0.56rem", color: "var(--fg-3)", padding: "4px 12px 6px", flexShrink: 0 }}>
          ⓘ {note}
        </div>
      )}
    </div>
  );
}
