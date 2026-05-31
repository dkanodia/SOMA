/**
 * EvasionPanel.jsx
 *
 * Shows the key hackathon narrative:
 *   "Sophisticated attacker EVADES Innate (18%) but NOT Memory (92%)"
 *
 * Displays a grouped bar chart:
 *   X: layers (Innate, Memory, Fusion)
 *   Groups: Obvious vs Sophisticated attack
 *
 * Data comes from meta.evasion_matrix (computed during demo export).
 * Falls back to hardcoded values if not present.
 */

import React, { useMemo } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer, Cell, ReferenceLine,
} from "recharts";

const FALLBACK_MATRIX = {
  obvious:       { innate_tpr: 0.876, memory_tpr: 0.927, fusion_tpr: 0.927 },
  sophisticated: { innate_tpr: 0.185, memory_tpr: 0.927, fusion_tpr: 0.927 },
};

function buildChartData(matrix) {
  const ob = matrix?.obvious       ?? FALLBACK_MATRIX.obvious;
  const so = matrix?.sophisticated ?? FALLBACK_MATRIX.sophisticated;
  return [
    { layer: "Innate",  obvious: ob.innate_tpr, sophisticated: so.innate_tpr },
    { layer: "Memory",  obvious: ob.memory_tpr, sophisticated: so.memory_tpr },
    { layer: "Fusion",  obvious: ob.fusion_tpr, sophisticated: so.fusion_tpr },
  ];
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: "#171715", border: "1px solid #262624",
      padding: "5px 8px", fontSize: 10, fontFamily: "'IBM Plex Mono', monospace",
    }}>
      <div style={{ color: "#807C76", marginBottom: 3 }}>{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} style={{ color: p.fill }}>
          {p.name}: {(p.value * 100).toFixed(1)}%
        </div>
      ))}
    </div>
  );
}

export default function EvasionPanel({ meta }) {
  const data = useMemo(
    () => buildChartData(meta?.evasion_matrix),
    [meta?.evasion_matrix]
  );

  return (
    <div className="panel-inner">
      <div className="panel-header">
        <span className="panel-title">Evasion Matrix</span>
        <span className="panel-tag">detection rate</span>
      </div>
      <div className="panel-body panel-body--flush">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 0 }} barSize={14}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1A1A18" />
            <XAxis dataKey="layer" tick={{ fill: "#807C76", fontSize: 9, fontFamily: "'IBM Plex Mono', monospace" }} />
            <YAxis domain={[0, 1]} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
              tick={{ fill: "#807C76", fontSize: 9, fontFamily: "'IBM Plex Mono', monospace" }} width={32} />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              wrapperStyle={{ fontSize: 9, color: "#807C76", fontFamily: "'IBM Plex Mono', monospace" }}
              iconSize={8}
            />
            <ReferenceLine y={0.9} stroke="#C49A30" strokeDasharray="4 2"
              label={{ value: "92.7%", position: "right", fill: "#C49A30", fontSize: 8 }} />
            <Bar dataKey="obvious"       name="Obvious"       fill="#C49A30" fillOpacity={0.65} />
            <Bar dataKey="sophisticated" name="Sophisticated"  fill="#6452A0" fillOpacity={0.65} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
