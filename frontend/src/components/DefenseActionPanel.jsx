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
  Remove:  "#A83D2E",
  Analyze: "#B87030",
  Restore: "#6452A0",
  Monitor: "#3E3D3A",
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
    <div className="panel-inner">
      <div className="panel-header">
        <span className="panel-title">Defense Actions</span>
        <span className="panel-tag">PPO + Orchestrator</span>
      </div>

      {/* Orchestrator recommendation */}
      {orch && (
        <div style={{
          background: "var(--panel-2)",
          borderLeft: `3px solid ${actionColor(orch.action_name)}`,
          padding: "6px 12px",
          flexShrink: 0,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.2rem" }}>
            <span style={{ fontSize: "0.56rem", color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.1em", fontFamily: "var(--mono)" }}>
              Orchestrator
            </span>
            <span style={{ fontFamily: "var(--font)", fontWeight: "700", color: actionColor(orch.action_name), fontSize: "0.78rem" }}>
              {orch.action_name}
            </span>
            <span className={`inc-conf ${orch.confidence}`}>{orch.confidence}</span>
          </div>
          <div style={{ fontSize: "0.6rem", color: "var(--fg-2)", fontFamily: "var(--mono)", lineHeight: 1.4 }}>{orch.reason}</div>
        </div>
      )}

      {/* PPO action log */}
      <div
        ref={logRef}
        style={{ flex: 1, overflowY: "auto", minHeight: 0, padding: "4px 12px" }}
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
                  padding: "3px 0",
                  borderBottom: "1px solid var(--line-dim)",
                  opacity: i === 0 ? 1 : Math.max(0.35, 1 - i * 0.04),
                }}
              >
                <span style={{ fontSize: "0.58rem", color: "var(--fg-3)", fontFamily: "var(--mono)", width: 26, flexShrink: 0 }}>
                  {idx}
                </span>
                <span
                  style={{
                    fontSize: "0.68rem",
                    fontFamily: "var(--mono)",
                    color: i === 0 ? color : "var(--fg-2)",
                    fontWeight: i === 0 ? "500" : "300",
                  }}
                >
                  {name}
                </span>
                {s.reward !== undefined && (
                  <span style={{ fontSize: "0.58rem", color: "var(--fg-3)", fontFamily: "var(--mono)", marginLeft: "auto" }}>
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
