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
      background: "#111827", border: "1px solid #1e293b",
      padding: "5px 8px", fontSize: 10,
    }}>
      <div style={{ color: "#64748b", marginBottom: 3 }}>{label}</div>
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
      <div className="panel-title">Evasion Matrix — Detection Rate</div>
      <div className="panel-content">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 0 }} barSize={14}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="layer" tick={{ fill: "#64748b", fontSize: 9 }} />
            <YAxis domain={[0, 1]} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
              tick={{ fill: "#64748b", fontSize: 9 }} width={32} />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              wrapperStyle={{ fontSize: 9, color: "#64748b" }}
              iconSize={8}
            />
            <ReferenceLine y={0.9} stroke="#22d3ee" strokeDasharray="4 2"
              label={{ value: "92.7%", position: "right", fill: "#22d3ee", fontSize: 8 }} />
            <Bar dataKey="obvious"       name="Obvious"       fill="#22d3ee" fillOpacity={0.7} />
            <Bar dataKey="sophisticated" name="Sophisticated"  fill="#a855f7" fillOpacity={0.7} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
