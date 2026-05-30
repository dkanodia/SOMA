/**
 * LayerRadarPanel.jsx
 *
 * Spider/radar chart showing current-step activation across all 5 immune layers.
 * Axes: Innate | Memory | Tolerance | LearnedAttacks | Fusion
 *
 * Values normalized 0→1:
 *   Innate:         anomaly_score / innate_threshold  (capped 1)
 *   Memory:         max(drift_scores) / memory_threshold (capped 1)
 *   Tolerance:      breach_count / n_hosts
 *   LearnedAttacks: learned_attack_conf
 *   Fusion:         top_threat.score / 5  (capped 1; scale is 0..5)
 */

import React, { useMemo } from "react";
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Tooltip,
} from "recharts";

function clamp01(v) { return Math.max(0, Math.min(1, v || 0)); }

function buildRadarData(state, meta) {
  if (!state || !meta) return [];

  const innateThresh = meta.innate_threshold || 0.5;
  const memThresh    = meta.memory_threshold  || 1.0;
  const nHosts       = meta.n_hosts            || 6;

  const innate = clamp01(state.anomaly_score / innateThresh);
  const maxDrift = Math.max(0, ...Object.values(state.drift_scores ?? {}));
  const memory   = clamp01(maxDrift / memThresh);
  const tolBreach = (state.tolerance_breached ?? []).length;
  const tolerance = clamp01(tolBreach / nHosts);
  const learned   = clamp01(state.learned_attack_conf ?? 0);
  const fusScore  = state.top_threat?.score ?? 0;
  const fusion    = clamp01(fusScore / 5.0);

  return [
    { axis: "Innate",      value: innate },
    { axis: "Memory",      value: memory },
    { axis: "Tolerance",   value: tolerance },
    { axis: "Learned",     value: learned },
    { axis: "Fusion",      value: fusion },
  ];
}

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  return (
    <div style={{
      background: "#111827", border: "1px solid #1e293b",
      padding: "4px 8px", fontSize: 10,
    }}>
      <span style={{ color: "#22d3ee" }}>{d.axis}: </span>
      <span style={{ color: "#e2e8f0" }}>{(d.value * 100).toFixed(0)}%</span>
    </div>
  );
}

export default function LayerRadarPanel({ state, meta }) {
  const data = useMemo(() => buildRadarData(state, meta), [state, meta]);

  return (
    <div className="panel-inner">
      <div className="panel-title">Layer Activation</div>
      <div className="panel-content">
        {data.length === 0 ? (
          <p className="panel-placeholder">Waiting for data…</p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart data={data} margin={{ top: 10, right: 20, bottom: 10, left: 20 }}>
              <PolarGrid stroke="#1e293b" />
              <PolarAngleAxis
                dataKey="axis"
                tick={{ fill: "#64748b", fontSize: 9 }}
              />
              <PolarRadiusAxis
                angle={90} domain={[0, 1]} tickCount={3}
                tick={{ fill: "#1e293b", fontSize: 0 }}
                axisLine={false}
              />
              <Radar
                name="Activation"
                dataKey="value"
                stroke="#22d3ee"
                fill="#22d3ee"
                fillOpacity={0.25}
                strokeWidth={1.5}
              />
              <Tooltip content={<CustomTooltip />} />
            </RadarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
