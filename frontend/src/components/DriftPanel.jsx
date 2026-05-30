/**
 * DriftPanel.jsx
 *
 * Per-host long-dwell drift distances as a bar chart.
 * Bars are amber when drift_alarms[host] is true, cyan otherwise.
 * Drift distance = L2 norm of centroid_pos vector.
 */
import React from "react";
import {
  BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Cell,
  ReferenceLine, Tooltip,
} from "recharts";

const HOST_SHORT = {
  User0:       "U0",
  User1:       "U1",
  User2:       "U2",
  Enterprise0: "E0",
  Enterprise1: "E1",
  Op_Server0:  "Op",
};

const COLOR_ALARM  = "#f59e0b";
const COLOR_NORMAL = "#22d3ee";

function driftDist(centroid) {
  if (!centroid || centroid.length < 2) return 0;
  return Math.sqrt(centroid[0] ** 2 + centroid[1] ** 2);
}

export default function DriftPanel({ state }) {
  if (!state) {
    return (
      <div className="panel-inner">
        <h3 className="panel-title">Long-Dwell Drift</h3>
        <p className="panel-placeholder">Waiting for data…</p>
      </div>
    );
  }

  const hostNames = Object.keys(state.drift_alarms ?? {});
  const chartData = hostNames.map((h) => ({
    host:  HOST_SHORT[h] ?? h,
    dist:  parseFloat(driftDist(state.centroid_pos?.[h]).toFixed(3)),
    alarm: state.drift_alarms?.[h] ?? false,
  }));

  const anyAlarm = chartData.some((d) => d.alarm);

  return (
    <div className="panel-inner">
      <h3 className="panel-title">
        Long-Dwell Drift
        {anyAlarm && (
          <span style={{ color: "#f59e0b", marginLeft: 8, fontSize: "0.6rem" }}>
            ⚠ DRIFT ALARM
          </span>
        )}
      </h3>
      <div className="panel-content">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
            <XAxis dataKey="host" tick={{ fontSize: 10, fill: "#64748b" }} />
            <YAxis tick={{ fontSize: 10, fill: "#64748b" }} domain={[0, "auto"]} />
            <Tooltip
              contentStyle={{ background: "#111827", border: "1px solid #1e293b", fontSize: 11 }}
              formatter={(v) => [v.toFixed(3), "drift dist"]}
            />
            <ReferenceLine y={1.0} stroke="#f59e0b" strokeDasharray="3 3" />
            <Bar dataKey="dist" radius={[2, 2, 0, 0]}>
              {chartData.map((entry, i) => (
                <Cell
                  key={i}
                  fill={entry.alarm ? COLOR_ALARM : COLOR_NORMAL}
                  fillOpacity={0.8}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
