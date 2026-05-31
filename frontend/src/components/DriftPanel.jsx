/**
 * DriftPanel.jsx
 *
 * Two views:
 *   Top — bar chart: current-step L2 drift distance per host (alarm = amber)
 *   Bottom — line chart: drift history over all steps for each host
 *
 * Drift distance = L2 norm of centroid_pos[host] vector.
 * drift_alarms[host] = true when long-dwell threshold exceeded.
 */
import React, { useMemo } from "react";
import {
  BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Cell,
  ReferenceLine, Tooltip, LineChart, Line, CartesianGrid, Legend,
} from "recharts";

const HOST_SHORT = {
  User0: "U0", User1: "U1", User2: "U2",
  Enterprise0: "E0", Enterprise1: "E1", Op_Server0: "Op",
};

const HOST_COLORS = {
  User0: "#3A7A58", User1: "#5F8D6F", User2: "#8BA778",
  Enterprise0: "#6452A0", Enterprise1: "#8071B8", Op_Server0: "#A83D2E",
};

const COLOR_ALARM  = "#B87030";
const COLOR_NORMAL = "#3A7A58";
const DRIFT_THRESH = 1.0;

function driftDist(centroid) {
  if (!centroid || centroid.length < 2) return 0;
  return Math.sqrt(centroid[0] ** 2 + centroid[1] ** 2);
}

export default function DriftPanel({ state, meta }) {
  if (!state) {
    return (
      <div className="panel-inner">
        <div className="panel-header"><span className="panel-title">Immunological Memory — Long-Dwell Drift</span></div>
        <p className="panel-placeholder">Waiting for data…</p>
      </div>
    );
  }

  const allSteps  = meta?._steps ?? [];
  const hostNames = Object.keys(state.drift_alarms ?? {});

  // Current-step bar data
  const barData = hostNames.map((h) => {
    const dist = state.drift_scores?.[h]   // enriched
      ?? driftDist(state.centroid_pos?.[h]); // raw fallback
    return { host: HOST_SHORT[h] ?? h, fullHost: h, dist: parseFloat(dist.toFixed(3)), alarm: state.drift_alarms?.[h] ?? false };
  });

  // History line data (from all steps)
  const histData = useMemo(() => {
    if (!allSteps.length) return [];
    return allSteps.map((s) => {
      const row = { step: s.step };
      for (const h of hostNames) {
        row[h] = s.drift_scores?.[h] ?? driftDist(s.centroid_pos?.[h]);
      }
      return row;
    });
  }, [allSteps, hostNames]);

  const anyAlarm = barData.some((d) => d.alarm);

  return (
    <div className="panel-inner">
      <div className="panel-header">
        <span className="panel-title">Immunological memory — long-dwell drift</span>
        {anyAlarm && <span className="panel-tag" style={{ color: "var(--warn)" }}>⚠ Drift alarm</span>}
      </div>

      {/* Current snapshot bar */}
      <div style={{ height: 110, flexShrink: 0, padding: "0 4px" }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={barData} margin={{ top: 4, right: 8, left: -22, bottom: 0 }}>
            <XAxis dataKey="host" tick={{ fontSize: 9, fill: "#807C76", fontFamily: "'IBM Plex Mono',monospace" }} />
            <YAxis tick={{ fontSize: 9, fill: "#807C76", fontFamily: "'IBM Plex Mono',monospace" }} domain={[0, "auto"]} />
            <Tooltip contentStyle={{ background: "#171715", border: "1px solid #262624", fontSize: 10, fontFamily: "'IBM Plex Mono',monospace" }}
              formatter={(v, _n, p) => [`${v.toFixed(3)} (${p.payload.alarm ? "ALARM" : "ok"})`, p.payload.fullHost]} />
            <ReferenceLine y={DRIFT_THRESH} stroke="#B87030" strokeDasharray="3 3"
              label={{ value: "θ", position: "right", fill: "#B87030", fontSize: 9 }} />
            <Bar dataKey="dist" radius={[2, 2, 0, 0]} isAnimationActive={false}>
              {barData.map((e, i) => (
                <Cell key={i} fill={e.alarm ? COLOR_ALARM : COLOR_NORMAL} fillOpacity={0.8} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Drift history over time */}
      <div style={{ flex: 1, minHeight: 0, padding: "0 4px 4px" }}>
        {histData.length > 1 ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={histData} margin={{ top: 4, right: 8, left: -22, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1A1A18" />
              <XAxis dataKey="step" tick={{ fontSize: 8, fill: "#807C76", fontFamily: "'IBM Plex Mono',monospace" }} />
              <YAxis tick={{ fontSize: 8, fill: "#807C76", fontFamily: "'IBM Plex Mono',monospace" }} />
              <Tooltip contentStyle={{ background: "#171715", border: "1px solid #262624", fontSize: 9, fontFamily: "'IBM Plex Mono',monospace" }}
                formatter={(v) => v.toFixed(3)} />
              <ReferenceLine y={DRIFT_THRESH} stroke="#B87030" strokeDasharray="3 3" />
              {hostNames.map((h) => (
                <Line key={h} type="monotone" dataKey={h} name={HOST_SHORT[h] ?? h}
                  stroke={HOST_COLORS[h] ?? "#807C76"} strokeWidth={1.2}
                  dot={false} isAnimationActive={false} strokeOpacity={0.7} />
              ))}
              <Legend iconSize={7}
                wrapperStyle={{ fontSize: 8, color: "#807C76", fontFamily: "'IBM Plex Mono',monospace" }} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p className="panel-placeholder" style={{ fontSize: "0.6rem" }}>Accumulating history…</p>
        )}
      </div>
    </div>
  );
}
