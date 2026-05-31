/**
 * LearningPanel.jsx
 * PPO training loss curve extracted from tb_logs.
 * Data source: meta.learning_curve (embedded by `python scripts/demo.py --static`).
 */
import React from "react";
import {
  LineChart, Line, XAxis, YAxis, ResponsiveContainer,
  Tooltip, ReferenceLine,
} from "recharts";

const TICK_STYLE    = { fontSize: 9, fill: "#807C76", fontFamily: "'IBM Plex Mono', monospace" };
const TOOLTIP_STYLE = { background: "#171715", border: "1px solid #262624", fontSize: 11, fontFamily: "'IBM Plex Mono', monospace" };

function kLabel(v) {
  return v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v);
}

export default function LearningPanel({ meta }) {
  const curve = meta?.learning_curve ?? [];

  if (curve.length === 0) {
    return (
      <div className="panel-inner">
        <h3 className="panel-title">Training Curve</h3>
        <p className="panel-placeholder" style={{ fontSize: 11, lineHeight: 1.6 }}>
          No learning curve data.<br />
          Run: <code>python scripts/demo.py --static</code>
        </p>
      </div>
    );
  }

  const minLoss = Math.min(...curve.map((d) => d.loss));
  const maxLoss = Math.max(...curve.map((d) => d.loss));
  const finalLoss = curve[curve.length - 1]?.loss;

  return (
    <div className="panel-inner">
      <div className="panel-header">
        <span className="panel-title">Training Curve</span>
        <span className="panel-tag" style={{ color: "var(--fg-3)" }}>
          PPO · {kLabel(curve[curve.length - 1]?.step ?? 0)} steps
        </span>
      </div>

      <div style={{ display: "flex", gap: 16, padding: "4px 8px 0", fontSize: 10, fontFamily: "'IBM Plex Mono', monospace", color: "var(--fg-3)" }}>
        <span>Start: <span style={{ color: "#CF6070" }}>{maxLoss.toLocaleString()}</span></span>
        <span>Final: <span style={{ color: "#3A7A58" }}>{finalLoss?.toLocaleString()}</span></span>
        <span>↓ {(((maxLoss - minLoss) / maxLoss) * 100).toFixed(0)}% reduction</span>
      </div>

      <div className="panel-body panel-body--flush">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={curve} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
            <XAxis
              dataKey="step"
              tick={TICK_STYLE}
              tickFormatter={kLabel}
            />
            <YAxis
              tick={TICK_STYLE}
              tickFormatter={kLabel}
              domain={["auto", "auto"]}
            />
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              formatter={(v) => [v.toLocaleString(), "policy loss"]}
              labelFormatter={(v) => `step ${kLabel(v)}`}
            />
            <Line
              type="monotone"
              dataKey="loss"
              stroke="#6452A0"
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
