/**
 * NetworkGraph.jsx
 *
 * Fixed-position SVG graph of the CAGE 2 Scenario 1b network topology.
 * Nodes colored by per-host anomaly / compromise status.
 * Kill-chain edges drawn as directed arrows with confidence weighting.
 *
 * CAGE 2 layout (fixed positions — no force simulation needed):
 *
 *       [Op_Server0]
 *       /           \
 * [Enterprise0]  [Enterprise1]
 *   /     \          /    \
 * [User0] [User1] [User2] (User0 also linked to Ent1)
 */

import React, { useMemo } from "react";

// Fixed node positions in a 320×220 SVG canvas
const NODE_POS = {
  Op_Server0:  { x: 160, y: 28 },
  Enterprise0: { x: 90,  y: 100 },
  Enterprise1: { x: 230, y: 100 },
  User0:       { x: 50,  y: 188 },
  User1:       { x: 130, y: 188 },
  User2:       { x: 270, y: 188 },
};

// Static topology edges (bidirectional — drawn once)
const TOPO_EDGES = [
  ["Enterprise0", "Op_Server0"],
  ["Enterprise1", "Op_Server0"],
  ["User0",       "Enterprise0"],
  ["User1",       "Enterprise0"],
  ["User0",       "Enterprise1"],
  ["User2",       "Enterprise1"],
];

const NODE_RADIUS = 22;

// Color logic
function nodeColor(host, state, meta) {
  if (!state) return "#1e293b";
  const compHosts = state.compromised_hosts ?? [];
  const innateScore = state.host_innate_scores?.[host] ?? 0;
  const innateThresh = meta?.innate_threshold ?? 0.5;
  const driftScore = state.drift_scores?.[host] ?? 0;
  const memThresh = meta?.memory_threshold ?? 1.0;

  if (compHosts.includes(host))     return "#ef4444";  // red: confirmed compromised
  if (driftScore > memThresh)        return "#a855f7";  // purple: memory alarm
  if (innateScore > innateThresh)    return "#f59e0b";  // amber: innate alarm
  if (state.tolerance_breached?.includes(host)) return "#f59e0b";
  return "#22d3ee";                                      // cyan: healthy
}

function nodeGlow(host, state, meta) {
  if (!state) return null;
  const compHosts = state.compromised_hosts ?? [];
  if (compHosts.includes(host)) return "#ef4444";
  const driftScore = state.drift_scores?.[host] ?? 0;
  const memThresh = meta?.memory_threshold ?? 1.0;
  if (driftScore > memThresh) return "#a855f7";
  return null;
}

// Arrow marker head
function arrowId(color) {
  return color === "#ef4444" ? "arrow-red" : "arrow-amber";
}

// Offset line endpoints so arrows don't overlap nodes
function offsetEndpoint(src, tgt, r) {
  const dx = tgt.x - src.x;
  const dy = tgt.y - src.y;
  const d  = Math.sqrt(dx * dx + dy * dy) || 1;
  return {
    x1: src.x + (dx / d) * r,
    y1: src.y + (dy / d) * r,
    x2: tgt.x - (dx / d) * (r + 4),
    y2: tgt.y - (dy / d) * (r + 4),
  };
}

// Short display label
function label(host) {
  return host.replace("Enterprise", "Ent").replace("Op_Server0", "Srv0");
}

export default function NetworkGraph({ state, meta }) {
  const killChain = state?.kill_chain ?? [];
  const topThreat = state?.top_threat ?? null;

  // Deduplicate kill-chain edges by (source, target)
  const kcEdges = useMemo(() => {
    const seen = new Set();
    return killChain.filter((e) => {
      const k = `${e.source}→${e.target}`;
      if (seen.has(k)) return false;
      seen.add(k); return true;
    });
  }, [killChain]);

  const hostNames = Object.keys(NODE_POS);

  return (
    <div className="panel-inner">
      <div className="panel-title">Network Topology</div>
      <div className="panel-content" style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
        <svg viewBox="0 0 320 220" style={{ width: "100%", height: "100%", maxHeight: 210 }}>
          <defs>
            {/* Arrow markers */}
            <marker id="arrow-red" markerWidth="8" markerHeight="8"
                    refX="6" refY="3" orient="auto">
              <path d="M0,0 L0,6 L8,3 z" fill="#ef4444" />
            </marker>
            <marker id="arrow-amber" markerWidth="8" markerHeight="8"
                    refX="6" refY="3" orient="auto">
              <path d="M0,0 L0,6 L8,3 z" fill="#f59e0b" />
            </marker>
            {/* Glow filter */}
            <filter id="glow" x="-40%" y="-40%" width="180%" height="180%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>

          {/* Static topology edges */}
          {TOPO_EDGES.map(([a, b], i) => {
            const pa = NODE_POS[a], pb = NODE_POS[b];
            return (
              <line key={i}
                x1={pa.x} y1={pa.y} x2={pb.x} y2={pb.y}
                stroke="#1e293b" strokeWidth={1.5}
              />
            );
          })}

          {/* Kill-chain directed edges */}
          {kcEdges.map((e, i) => {
            const ps = NODE_POS[e.source], pt = NODE_POS[e.target];
            if (!ps || !pt) return null;
            const { x1, y1, x2, y2 } = offsetEndpoint(ps, pt, NODE_RADIUS);
            const color = "#ef4444";
            const opacity = Math.max(0.4, e.confidence);
            return (
              <line key={`kc-${i}`}
                x1={x1} y1={y1} x2={x2} y2={y2}
                stroke={color}
                strokeWidth={Math.max(1, 3 * e.confidence)}
                strokeOpacity={opacity}
                markerEnd={`url(#${arrowId(color)})`}
                strokeDasharray="4 2"
              />
            );
          })}

          {/* Nodes */}
          {hostNames.map((h) => {
            const { x, y } = NODE_POS[h];
            const color = nodeColor(h, state, meta);
            const glow  = nodeGlow(h, state, meta);
            const isTop = topThreat?.host === h;

            return (
              <g key={h}>
                {/* Outer ring for top threat */}
                {isTop && (
                  <circle cx={x} cy={y} r={NODE_RADIUS + 5}
                    fill="none" stroke="#ef4444" strokeWidth={1.5}
                    strokeOpacity={0.6} strokeDasharray="3 2" />
                )}
                {/* Glow halo */}
                {glow && (
                  <circle cx={x} cy={y} r={NODE_RADIUS + 2}
                    fill={glow} fillOpacity={0.18} filter="url(#glow)" />
                )}
                {/* Node body */}
                <circle cx={x} cy={y} r={NODE_RADIUS}
                  fill={color} fillOpacity={0.18}
                  stroke={color} strokeWidth={2}
                />
                {/* Label */}
                <text x={x} y={y + 1}
                  textAnchor="middle" dominantBaseline="middle"
                  fill={color} fontSize={9} fontFamily="monospace" fontWeight="bold">
                  {label(h)}
                </text>
                {/* Anomaly score micro-badge */}
                {state?.host_innate_scores?.[h] != null && (
                  <text x={x} y={y + NODE_RADIUS + 10}
                    textAnchor="middle"
                    fill="#64748b" fontSize={7.5} fontFamily="monospace">
                    {state.host_innate_scores[h].toFixed(2)}
                  </text>
                )}
              </g>
            );
          })}

          {/* Legend */}
          {[
            { color: "#22d3ee", label: "Healthy" },
            { color: "#f59e0b", label: "Innate" },
            { color: "#a855f7", label: "Memory" },
            { color: "#ef4444", label: "Compromised" },
          ].map((l, i) => (
            <g key={l.label} transform={`translate(${8 + i * 76}, 210)`}>
              <circle cx={5} cy={0} r={4} fill={l.color} fillOpacity={0.7} />
              <text x={12} y={3} fill="#64748b" fontSize={8} fontFamily="monospace">
                {l.label}
              </text>
            </g>
          ))}
        </svg>
      </div>
    </div>
  );
}
