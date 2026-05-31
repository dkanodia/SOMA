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
      background: "#171715", border: "1px solid #262624",
      padding: "4px 8px", fontSize: 10, fontFamily: "'IBM Plex Mono', monospace",
    }}>
      <span style={{ color: "#C49A30" }}>{d.axis}: </span>
      <span style={{ color: "#DEDAD3" }}>{(d.value * 100).toFixed(0)}%</span>
    </div>
  );
}

export default function LayerRadarPanel({ state, meta }) {
  const data = useMemo(() => buildRadarData(state, meta), [state, meta]);

  return (
    <div className="panel-inner">
      <div className="panel-header">
        <span className="panel-title">Layer Activation</span>
        <span className="panel-tag">radar</span>
      </div>
      <div className="panel-body panel-body--flush">
        {data.length === 0 ? (
          <p className="panel-placeholder">Waiting for data…</p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart data={data} margin={{ top: 10, right: 20, bottom: 10, left: 20 }}>
              <PolarGrid stroke="#262624" />
              <PolarAngleAxis
                dataKey="axis"
                tick={{ fill: "#807C76", fontSize: 9, fontFamily: "'IBM Plex Mono', monospace" }}
              />
              <PolarRadiusAxis
                angle={90} domain={[0, 1]} tickCount={3}
                tick={{ fill: "#1A1A18", fontSize: 0 }}
                axisLine={false}
              />
              <Radar
                name="Activation"
                dataKey="value"
                stroke="#C49A30"
                fill="#C49A30"
                fillOpacity={0.18}
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
