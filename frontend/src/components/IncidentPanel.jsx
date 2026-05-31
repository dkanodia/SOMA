/**
 * IncidentPanel.jsx
 *
 * Shows current-step fused incidents with:
 *   - Host + confidence badge + layer scores
 *   - Explanation (reason from ImmuneExplainer)
 *   - Kill-chain summary
 *
 * Incidents are sorted HIGH → MEDIUM → LOW.
 */

import React from "react";

const CONF_ORDER = { HIGH: 0, MEDIUM: 1, LOW: 2 };

function sortIncidents(incidents) {
  return [...(incidents ?? [])].sort(
    (a, b) => (CONF_ORDER[a.confidence] ?? 3) - (CONF_ORDER[b.confidence] ?? 3)
  );
}

function IncidentCard({ inc }) {
  const layers = (inc.layers_fired ?? []).join(" + ") || "none";
  return (
    <div className={`incident-card ${inc.confidence}`}>
      <div className="incident-header">
        <span className="inc-host">{inc.host}</span>
        <span className="inc-score">score={inc.score?.toFixed(2)}</span>
        <span className={`inc-conf ${inc.confidence}`}>{inc.confidence}</span>
        {inc.attack_type && inc.attack_type !== "unknown" && (
          <span style={{ fontSize: "0.6rem", color: "#34d399" }}>{inc.attack_type}</span>
        )}
      </div>
      <div className="inc-layers">Layers: {layers}</div>
      {inc.explanation && (
        <div className="inc-reason">{inc.explanation}</div>
      )}
    </div>
  );
}

function KillChainSummary({ killChain }) {
  if (!killChain?.length) return null;
  return (
    <div style={{ marginTop: "0.5rem", borderTop: "1px solid var(--line)", paddingTop: "0.4rem" }}>
      <div style={{ fontSize: "0.56rem", color: "var(--fg-3)", marginBottom: "0.2rem", textTransform: "uppercase", letterSpacing: "0.1em", fontFamily: "var(--mono)" }}>
        Kill Chain ({killChain.length} edge{killChain.length !== 1 ? "s" : ""})
      </div>
      {killChain.slice(0, 4).map((e, i) => (
        <div key={i} className="kc-edge">
          {e.source} → {e.target}
          <span style={{ color: "var(--fg-3)", marginLeft: 6 }}>
            [{e.phase}] conf={e.confidence?.toFixed(2)} t={e.t_source}→{e.t_target}
          </span>
        </div>
      ))}
      {killChain.length > 4 && (
        <div style={{ fontSize: "0.6rem", color: "var(--fg-3)" }}>
          +{killChain.length - 4} more…
        </div>
      )}
    </div>
  );
}

export default function IncidentPanel({ state, step }) {
  const incidents  = sortIncidents(state?.incidents);
  const killChain  = state?.kill_chain ?? [];
  const topThreat  = state?.top_threat;
  const isAttack   = state?.is_attack ?? false;
  const explanation = state?.explanation;

  return (
    <div className="panel-inner">
      <div className="panel-header">
        <span className="panel-title">
          Incidents
          {isAttack && <span style={{ color: "var(--alert)", marginLeft: 8 }}>⚠ ATTACK</span>}
        </span>
        {topThreat && (
          <span className="panel-tag" style={{ color: "var(--gold)" }}>
            Top: {topThreat.host} ({topThreat.score?.toFixed(2)})
          </span>
        )}
      </div>
      <div className="panel-body incident-list">
        {incidents.length === 0 ? (
          <p className="no-incidents">✓ No active incidents</p>
        ) : (
          incidents.map((inc, i) => <IncidentCard key={i} inc={inc} />)
        )}

        <KillChainSummary killChain={killChain} />

        {explanation && (
          <div style={{ marginTop: "0.5rem", borderTop: "1px solid var(--line)", paddingTop: "0.4rem" }}>
            <div style={{ fontSize: "0.56rem", color: "var(--fg-3)", marginBottom: "0.2rem", textTransform: "uppercase", letterSpacing: "0.1em", fontFamily: "var(--mono)" }}>
              Why did it fire?
            </div>
            {Object.entries(explanation).map(([layer, expl]) => (
              expl?.reason ? (
                <div key={layer} style={{ fontFamily: "var(--mono)", fontSize: "0.62rem", marginBottom: "0.25rem" }}>
                  <span style={{ color: layerColor(layer) }}>{layer}: </span>
                  <span style={{ color: "var(--fg-2)" }}>{expl.reason}</span>
                </div>
              ) : null
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function layerColor(layer) {
  const map = {
    innate:          "#C49A30",
    memory:          "#6452A0",
    tolerance:       "#B87030",
    learned_attacks: "#3A7A58",
  };
  return map[layer] ?? "#807C76";
}
