/**
 * DefenseActionPanel.jsx
 *
 * Two sections:
 *   Top — scrollable log of PPO actions taken each step, decoded to names.
 *   Bottom — current orchestrator recommendation (action + confidence + reason).
 */
import React, { useRef, useEffect } from "react";

// BLUE_ACTIONS mirrored from soma/envs/cyborg_wrapper.py (index = action int)
const BLUE_ACTIONS = [
  "Monitor",
  "Analyze_User0",    "Analyze_User1",    "Analyze_User2",
  "Analyze_Enterprise0", "Analyze_Enterprise1", "Analyze_Op_Server0",
  "Remove_User0",     "Remove_User1",     "Remove_User2",
  "Remove_Enterprise0", "Remove_Enterprise1", "Remove_Op_Server0",
  "Restore_User0",    "Restore_User1",    "Restore_User2",
  "Restore_Enterprise0", "Restore_Enterprise1", "Restore_Op_Server0",
];

const ACTION_COLORS = {
  Remove:  "#ef4444",
  Analyze: "#f59e0b",
  Restore: "#a855f7",
  Monitor: "#22d3ee",
};

function actionColor(name) {
  const prefix = (name ?? "Monitor").split("_")[0];
  return ACTION_COLORS[prefix] ?? "#64748b";
}

function actionName(idx) {
  return BLUE_ACTIONS[idx] ?? "Monitor";
}

export default function DefenseActionPanel({ state, meta, step }) {
  const logRef = useRef(null);

  const allSteps = meta?._steps ?? [];
  const logSteps = allSteps.slice(0, (step ?? 0) + 1);

  // Auto-scroll log to top when step advances (most recent entry is at top)
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = 0;
    }
  }, [step]);

  const orch = state?.orchestrator;

  if (!state) {
    return (
      <div className="panel-inner">
        <h3 className="panel-title">Defense Actions</h3>
        <p className="panel-placeholder">Waiting for data…</p>
      </div>
    );
  }

  return (
    <div className="panel-inner" style={{ gap: "0.4rem" }}>
      <h3 className="panel-title">Defense Actions — PPO + Orchestrator</h3>

      {/* Orchestrator recommendation */}
      {orch && (
        <div style={{
          background: "#0f172a",
          border: "1px solid #1e293b",
          borderLeft: `3px solid ${actionColor(orch.action_name)}`,
          borderRadius: 4,
          padding: "0.35rem 0.5rem",
          flexShrink: 0,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.2rem" }}>
            <span style={{ fontSize: "0.6rem", color: "#64748b", textTransform: "uppercase", letterSpacing: "0.08em" }}>
              Orchestrator
            </span>
            <span style={{ fontWeight: "bold", color: actionColor(orch.action_name), fontSize: "0.78rem" }}>
              {orch.action_name}
            </span>
            <span className={`inc-conf ${orch.confidence}`}>{orch.confidence}</span>
          </div>
          <div style={{ fontSize: "0.62rem", color: "#94a3b8" }}>{orch.reason}</div>
        </div>
      )}

      {/* PPO action log */}
      <div
        ref={logRef}
        style={{ flex: 1, overflowY: "auto", minHeight: 0 }}
      >
        {logSteps.length === 0 ? (
          <p className="panel-placeholder">No steps yet…</p>
        ) : (
          [...logSteps].reverse().map((s, i) => {
            const name  = actionName(s.action);
            const color = actionColor(name);
            const idx   = logSteps.length - 1 - i;
            return (
              <div
                key={idx}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.4rem",
                  padding: "2px 4px",
                  borderBottom: "1px solid #1e293b",
                  opacity: i === 0 ? 1 : 0.65 + (0.35 * (logSteps.length - i) / logSteps.length),
                }}
              >
                <span style={{ fontSize: "0.6rem", color: "#475569", width: 28, flexShrink: 0 }}>
                  {idx}
                </span>
                <span
                  style={{
                    fontSize: "0.68rem",
                    color,
                    fontWeight: i === 0 ? "bold" : "normal",
                  }}
                >
                  {name}
                </span>
                {s.reward !== undefined && (
                  <span style={{ fontSize: "0.6rem", color: "#475569", marginLeft: "auto" }}>
                    r={s.reward.toFixed(1)}
                  </span>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
