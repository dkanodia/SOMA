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
  if (!state) return [];

  const innateThresh = meta?.innate_threshold ?? 0.5;
  const memThresh    = meta?.memory_threshold  ?? 1.0;
  const nHosts       = meta?.n_hosts ?? 6;

  // Support both enriched state (anomaly_score float) and raw (anomaly_scores dict)
  const innateScore = state.anomaly_score != null
    ? state.anomaly_score
    : Math.max(0, ...Object.values(state.anomaly_scores ?? {}));
  const innate = clamp01(innateScore / innateThresh);

  // Support both enriched (drift_scores) and raw (centroid_pos)
  let maxDrift = 0;
  if (state.drift_scores) {
    maxDrift = Math.max(0, ...Object.values(state.drift_scores));
  } else {
    for (const pos of Object.values(state.centroid_pos ?? {})) {
      if (pos) maxDrift = Math.max(maxDrift, Math.sqrt(pos[0] ** 2 + pos[1] ** 2));
    }
  }
  const memory = clamp01(maxDrift / memThresh);

  const tolBreach = (state.tolerance_breached ?? []).length;
  const tolerance = clamp01(tolBreach / nHosts);
  const learned   = clamp01(state.learned_attack_conf ?? 0);
  const fusScore  = state.top_threat?.score ?? 0;
  const fusion    = clamp01(fusScore);    // already 0-1

  return [
    { axis: "Innate",    value: innate,    pct: (innate    * 100).toFixed(0) },
    { axis: "Memory",    value: memory,    pct: (memory    * 100).toFixed(0) },
    { axis: "Tolerance", value: tolerance, pct: (tolerance * 100).toFixed(0) },
    { axis: "Learned",   value: learned,   pct: (learned   * 100).toFixed(0) },
    { axis: "Fusion",    value: fusion,    pct: (fusion    * 100).toFixed(0) },
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
      <span style={{ color: "#DEDAD3" }}>{d.pct}%</span>
    </div>
  );
}

const LAYER_COLORS = {
  Innate:    "#C49A30",
  Memory:    "#6452A0",
  Tolerance: "#B87030",
  Learned:   "#3A7A58",
  Fusion:    "#A83D2E",
};

export default function LayerRadarPanel({ state, meta }) {
  const data = useMemo(() => buildRadarData(state, meta), [state, meta]);

  return (
    <div className="panel-inner">
      <div className="panel-header">
        <span className="panel-title">Layer activation — immune response strength</span>
        <span className="panel-tag">current step</span>
      </div>
      <div style={{ display: "flex", flex: 1, minHeight: 0, overflow: "hidden" }}>
        {/* Radar chart */}
        <div style={{ flex: 1, minWidth: 0 }}>
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
                <PolarRadiusAxis angle={90} domain={[0, 1]} tickCount={3}
                  tick={{ fontSize: 0 }} axisLine={false} />
                <Radar name="Activation" dataKey="value"
                  stroke="#C49A30" fill="#C49A30" fillOpacity={0.2} strokeWidth={2}
                  isAnimationActive={false} />
                <Tooltip content={<CustomTooltip />} />
              </RadarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Per-layer value list */}
        {data.length > 0 && (
          <div style={{
            display: "flex", flexDirection: "column", justifyContent: "center",
            gap: 6, padding: "8px 14px 8px 0", flexShrink: 0, width: 110,
          }}>
            {data.map((d) => (
              <div key={d.axis} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <div style={{
                  width: 48, height: 3, borderRadius: 2, flexShrink: 0,
                  background: LAYER_COLORS[d.axis] ?? "#807C76",
                  opacity: 0.3 + d.value * 0.7,
                }} />
                <span style={{ fontSize: 9, color: "#807C76", fontFamily: "'IBM Plex Mono',monospace", flex: 1 }}>
                  {d.axis}
                </span>
                <span style={{
                  fontSize: 10, fontFamily: "'IBM Plex Mono',monospace", fontWeight: 600,
                  color: d.value > 0.5 ? (LAYER_COLORS[d.axis] ?? "#C49A30") : "#807C76",
                }}>
                  {d.pct}%
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
