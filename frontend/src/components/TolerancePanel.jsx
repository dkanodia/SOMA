/**
 * TolerancePanel.jsx
 *
 * Layer 3a — Immune Tolerance visualization.
 *
 * Per-host status uses the `tolerance_suppressed` and `tolerance_breached`
 * arrays from the demo episode payload:
 *   BREACHED   → host behaviour exceeds breach_sigma=3.0 (HIGH alert)
 *   SUPPRESSED → host behaviour within suppress_sigma=1.5 (self-like, muted)
 *   NORMAL     → between the two thresholds (monitoring)
 *
 * Top:    bar chart — current step per-host status
 * Bottom: stacked area history — fraction of hosts in each state over time
 */
import React, { useMemo } from "react";
import {
  BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Cell, Tooltip,
  AreaChart, Area, CartesianGrid, Legend,
} from "recharts";

const HOST_SHORT = {
  User0: "U0", User1: "U1", User2: "U2",
  Enterprise0: "E0", Enterprise1: "E1", Op_Server0: "Op",
};

const ALL_HOSTS = ["User0", "User1", "User2", "Enterprise0", "Enterprise1", "Op_Server0"];

const COLOR_BREACHED   = "#A83D2E";
const COLOR_SUPPRESSED = "#5A6FA8";
const COLOR_NORMAL     = "#3A7A58";

// 0 = normal, 0.5 = suppressed, 1 = breached — used for the bar heights
function hostStatusValue(host, suppressed, breached) {
  if ((breached ?? []).includes(host))   return 1;
  if ((suppressed ?? []).includes(host)) return 0.5;
  return 0;
}

function hostStatusLabel(val) {
  if (val >= 1)   return "BREACHED";
  if (val >= 0.5) return "SUPPRESSED";
  return "NORMAL";
}

function hostStatusColor(val) {
  if (val >= 1)   return COLOR_BREACHED;
  if (val >= 0.5) return COLOR_SUPPRESSED;
  return COLOR_NORMAL;
}

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div style={{
      background: "#171715", border: "1px solid #262624",
      fontSize: 10, fontFamily: "'IBM Plex Mono',monospace", padding: "4px 8px",
    }}>
      <div style={{ color: hostStatusColor(d.val) }}>{d.fullHost}: {hostStatusLabel(d.val)}</div>
    </div>
  );
};

export default function TolerancePanel({ state, meta }) {
  if (!state) {
    return (
      <div className="panel-inner">
        <div className="panel-header">
          <span className="panel-title">Immune Tolerance — Self-Model</span>
        </div>
        <p className="panel-placeholder">Waiting for data…</p>
      </div>
    );
  }

  const suppressed = state.tolerance_suppressed ?? [];
  const breached   = state.tolerance_breached   ?? [];

  const barData = ALL_HOSTS.map((h) => {
    const val = hostStatusValue(h, suppressed, breached);
    return { host: HOST_SHORT[h] ?? h, fullHost: h, val, color: hostStatusColor(val) };
  });

  const allSteps = meta?._steps ?? [];

  const histData = useMemo(() => {
    if (!allSteps.length) return [];
    return allSteps.map((s) => {
      const sup = s.tolerance_suppressed ?? [];
      const brc = s.tolerance_breached   ?? [];
      const n   = ALL_HOSTS.length;
      return {
        step:       s.step,
        breached:   parseFloat((brc.length / n).toFixed(3)),
        suppressed: parseFloat((sup.length / n).toFixed(3)),
        normal:     parseFloat(((n - sup.length - brc.length) / n).toFixed(3)),
      };
    });
  }, [allSteps]);

  const nBreached   = breached.length;
  const nSuppressed = suppressed.length;
  const nNormal     = ALL_HOSTS.length - nBreached - nSuppressed;

  return (
    <div className="panel-inner">
      <div className="panel-header">
        <span className="panel-title">Immune tolerance — self-model (σ_breach = 3.0)</span>
        {nBreached > 0 && (
          <span className="panel-tag" style={{ color: COLOR_BREACHED }}>
            ⚠ {nBreached} breached
          </span>
        )}
        {nSuppressed > 0 && nBreached === 0 && (
          <span className="panel-tag" style={{ color: COLOR_SUPPRESSED }}>
            {nSuppressed} suppressed
          </span>
        )}
      </div>

      {/* Legend */}
      <div style={{ display: "flex", gap: 12, padding: "2px 8px 4px", fontSize: 9, fontFamily: "'IBM Plex Mono',monospace" }}>
        {[["BREACHED", COLOR_BREACHED, nBreached], ["SUPPRESSED", COLOR_SUPPRESSED, nSuppressed], ["NORMAL", COLOR_NORMAL, nNormal]].map(([label, color, count]) => (
          <span key={label} style={{ color, display: "flex", alignItems: "center", gap: 3 }}>
            <span style={{ display: "inline-block", width: 8, height: 8, background: color, borderRadius: 1 }} />
            {label} ({count})
          </span>
        ))}
      </div>

      {/* Current-step bar chart */}
      <div style={{ height: 100, flexShrink: 0, padding: "0 4px" }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={barData} margin={{ top: 2, right: 8, left: -22, bottom: 0 }}>
            <XAxis dataKey="host" tick={{ fontSize: 9, fill: "#807C76", fontFamily: "'IBM Plex Mono',monospace" }} />
            <YAxis tick={{ fontSize: 9, fill: "#807C76", fontFamily: "'IBM Plex Mono',monospace" }}
              domain={[0, 1]} ticks={[0, 0.5, 1]}
              tickFormatter={(v) => v === 1 ? "breach" : v === 0.5 ? "supp" : "ok"} />
            <Tooltip content={<CustomTooltip />} />
            <Bar dataKey="val" radius={[2, 2, 0, 0]} isAnimationActive={false} maxBarSize={32}>
              {barData.map((e, i) => (
                <Cell key={i} fill={e.color} fillOpacity={0.85} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* History area chart */}
      <div style={{ flex: 1, minHeight: 0, padding: "0 4px 4px" }}>
        {histData.length > 1 ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={histData} margin={{ top: 4, right: 8, left: -22, bottom: 0 }} stackOffset="expand">
              <CartesianGrid strokeDasharray="3 3" stroke="#1A1A18" />
              <XAxis dataKey="step" tick={{ fontSize: 8, fill: "#807C76", fontFamily: "'IBM Plex Mono',monospace" }} />
              <YAxis tick={{ fontSize: 8, fill: "#807C76", fontFamily: "'IBM Plex Mono',monospace" }}
                tickFormatter={(v) => `${Math.round(v * 100)}%`} />
              <Tooltip
                contentStyle={{ background: "#171715", border: "1px solid #262624", fontSize: 9, fontFamily: "'IBM Plex Mono',monospace" }}
                formatter={(v) => `${(v * 100).toFixed(0)}%`}
              />
              <Area type="monotone" dataKey="normal"     stackId="1" stroke={COLOR_NORMAL}     fill={COLOR_NORMAL}     fillOpacity={0.5} isAnimationActive={false} name="Normal" />
              <Area type="monotone" dataKey="suppressed" stackId="1" stroke={COLOR_SUPPRESSED} fill={COLOR_SUPPRESSED} fillOpacity={0.6} isAnimationActive={false} name="Suppressed" />
              <Area type="monotone" dataKey="breached"   stackId="1" stroke={COLOR_BREACHED}   fill={COLOR_BREACHED}   fillOpacity={0.7} isAnimationActive={false} name="Breached" />
              <Legend iconSize={7}
                wrapperStyle={{ fontSize: 8, color: "#807C76", fontFamily: "'IBM Plex Mono',monospace" }} />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <p className="panel-placeholder" style={{ fontSize: "0.6rem" }}>Accumulating history…</p>
        )}
      </div>
    </div>
  );
}
