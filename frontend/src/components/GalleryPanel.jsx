/**
 * GalleryPanel.jsx
 *
 * 2D scatter plot of VAE attack embedding gallery (first 2 latent dimensions).
 * Shows each learned attack type as a labeled dot.
 * Current episode's recognized attack type is highlighted with a ring.
 *
 * Data:
 *   meta.gallery_initial  — [{attack_type, n_steps, embedding: [4 floats]}]
 *   state.gallery_snapshot — same, updated at key steps
 */

import React, { useMemo } from "react";
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell,
} from "recharts";

const TYPE_COLORS = {
  "lateral_move_obvious":      "#22d3ee",
  "lateral_move_sophisticated":"#67e8f9",
  "privilege_escalation":      "#a855f7",
  "direct_impact":             "#ef4444",
  "lateral_move":              "#34d399",
  "obvious":                   "#f59e0b",
  "unknown":                   "#64748b",
};
const DEFAULT_COLOR = "#94a3b8";

function galleryToPoints(gallery) {
  return (gallery ?? []).map((entry) => ({
    x:    entry.embedding?.[0] ?? 0,
    y:    entry.embedding?.[1] ?? 0,
    type: entry.attack_type,
    n:    entry.n_steps,
  }));
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
      <div style={{ color: TYPE_COLORS[d.type] ?? DEFAULT_COLOR }}>{d.type}</div>
      <div style={{ color: "#64748b" }}>n_steps={d.n}  z0={d.x.toFixed(3)}  z1={d.y.toFixed(3)}</div>
    </div>
  );
}

export default function GalleryPanel({ state, meta }) {
  // Use the most recent gallery snapshot, falling back to meta.gallery_initial
  const gallery = state?.gallery_snapshot ?? meta?.gallery_initial ?? [];
  const points  = useMemo(() => galleryToPoints(gallery), [gallery]);

  const currentType = state?.learned_attack_type;

  return (
    <div className="panel-inner">
      <div className="panel-title">
        Attack Gallery — VAE Latent Space (z₀ × z₁)
        {gallery.length > 0 && (
          <span style={{ color: "#34d399", marginLeft: 6 }}>
            {gallery.length} signature{gallery.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>
      <div className="panel-content">
        {points.length === 0 ? (
          <p className="panel-placeholder">Gallery empty — no attack signatures learned yet</p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 8, right: 10, bottom: 8, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis type="number" dataKey="x" name="z₀"
                tick={{ fill: "#64748b", fontSize: 8 }}
                label={{ value: "z₀", position: "insideBottomRight", fill: "#64748b", fontSize: 9, offset: -2 }} />
              <YAxis type="number" dataKey="y" name="z₁"
                tick={{ fill: "#64748b", fontSize: 8 }} width={28}
                label={{ value: "z₁", angle: -90, position: "insideLeft", fill: "#64748b", fontSize: 9 }} />
              <Tooltip content={<CustomTooltip />} />
              <Scatter data={points} shape="circle">
                {points.map((p, i) => {
                  const color = TYPE_COLORS[p.type] ?? DEFAULT_COLOR;
                  const isCurrent = p.type === currentType;
                  return (
                    <Cell
                      key={i}
                      fill={color}
                      fillOpacity={isCurrent ? 0.95 : 0.55}
                      stroke={isCurrent ? "#fff" : color}
                      strokeWidth={isCurrent ? 2 : 0}
                      r={isCurrent ? 7 : 5}
                    />
                  );
                })}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        )}
        {/* Type legend */}
        {points.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 10px", marginTop: 2 }}>
            {[...new Set(points.map((p) => p.type))].map((t) => (
              <span key={t} style={{ fontSize: 8, color: TYPE_COLORS[t] ?? DEFAULT_COLOR }}>
                ● {t}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
