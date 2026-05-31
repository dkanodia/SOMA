/**
 * AnomalyPanel.jsx
 * Per-host anomaly score time series up to the current scrubber position.
 * Data source: meta._steps[i].anomaly_scores (already in the static episode).
 */
import React from "react";
import {
  LineChart, Line, XAxis, YAxis, ResponsiveContainer,
  ReferenceLine, Tooltip, Legend,
} from "recharts";

const HOST_COLORS = {
  User0:       "#C49A30",
  User1:       "#B87030",
  User2:       "#CF6070",
  Enterprise0: "#3A7A58",
  Enterprise1: "#6452A0",
  Op_Server0:  "#3A6A8A",
};

const HOST_SHORT = {
  User0: "U0", User1: "U1", User2: "U2",
  Enterprise0: "E0", Enterprise1: "E1", Op_Server0: "Op",
};

const TICK_STYLE = { fontSize: 9, fill: "#807C76", fontFamily: "'IBM Plex Mono', monospace" };
const TOOLTIP_STYLE = { background: "#171715", border: "1px solid #262624", fontSize: 11, fontFamily: "'IBM Plex Mono', monospace" };

export default function AnomalyPanel({ meta, step }) {
  if (!meta?._steps) {
    return (
      <div className="panel-inner">
        <h3 className="panel-title">Anomaly Scores</h3>
        <p className="panel-placeholder">Waiting for data…</p>
      </div>
    );
  }

  const slice = meta._steps.slice(0, step + 1);
  // Support both field names: demo.py uses anomaly_scores, export_demo_cyber.py uses host_innate_scores
  const scoreField = meta._steps[0]?.anomaly_scores ? "anomaly_scores" : "host_innate_scores";
  const hosts = Object.keys(meta._steps[0]?.[scoreField] ?? {});

  // Downsample to ≤120 points so the chart stays responsive
  const stride = Math.max(1, Math.floor(slice.length / 120));
  const chartData = slice
    .filter((_, i) => i % stride === 0 || i === slice.length - 1)
    .map((s, i) => {
      const row = { step: s.step ?? i * stride };
      hosts.forEach((h) => { row[h] = parseFloat((s[scoreField]?.[h] ?? 0).toFixed(4)); });
      return row;
    });

  const threshold = meta.innate_threshold ?? null;
  const anyFired  = slice.some((s) => s.innate_fired);

  return (
    <div className="panel-inner">
      <div className="panel-header">
        <span className="panel-title">Anomaly Scores</span>
        {anyFired && (
          <span className="panel-tag" style={{ color: "var(--gold)" }}>⚠ INNATE FIRED</span>
        )}
      </div>
      <div className="panel-body panel-body--flush">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
            <XAxis dataKey="step" tick={TICK_STYLE} />
            <YAxis tick={TICK_STYLE} domain={[0, "auto"]} />
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              formatter={(v, name) => [v.toFixed(4), HOST_SHORT[name] ?? name]}
            />
            <Legend
              iconSize={8}
              formatter={(name) => HOST_SHORT[name] ?? name}
              wrapperStyle={{ fontSize: 9, fontFamily: "'IBM Plex Mono', monospace" }}
            />
            {threshold !== null && (
              <ReferenceLine
                y={threshold}
                stroke="#C49A30"
                strokeDasharray="3 3"
                label={{ value: "threshold", fontSize: 8, fill: "#C49A30", position: "insideTopRight" }}
              />
            )}
            {hosts.map((h) => (
              <Line
                key={h}
                type="monotone"
                dataKey={h}
                stroke={HOST_COLORS[h] ?? "#888"}
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
