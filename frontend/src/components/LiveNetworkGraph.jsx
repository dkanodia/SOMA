import React, { useMemo } from "react";

// ---------------------------------------------------------------------------
// Layout constants
// ---------------------------------------------------------------------------

const W       = 580;
const H_REAL  = 250;   // height of the real-network section
const H_GAP   = 36;    // gap + divider between zones
const H_DECOY = 190;   // height of the honeypot / decoy section
const R       = 18;    // node circle radius

// ---------------------------------------------------------------------------
// Real-network node positions
// ---------------------------------------------------------------------------

const POS = {
  Attacker:    { x: 52,  y: 110 },
  User0:       { x: 185, y: 130 },
  User1:       { x: 185, y: 45  },
  User2:       { x: 185, y: 215 },
  Enterprise0: { x: 330, y: 82  },
  Enterprise1: { x: 330, y: 178 },
  Op_Server0:  { x: 470, y: 130 },
};

// Decoy network — mirrors internal nodes, offset into the honeypot section
const DY = H_REAL + H_GAP;  // y-offset for decoy zone

const DPOS = {
  "D-User0":       { x: 185, y: DY + 95  },
  "D-Enterprise0": { x: 330, y: DY + 55  },
  "D-Enterprise1": { x: 330, y: DY + 135 },
  "D-Op_Server0":  { x: 470, y: DY + 95  },
};

// Static edges — real network
const TOPO = [
  ["User0", "Enterprise0"],
  ["User0", "Enterprise1"],
  ["User1", "Enterprise0"],
  ["User2", "Enterprise1"],
  ["Enterprise0", "Op_Server0"],
  ["Enterprise1", "Op_Server0"],
];

// Static edges — decoy network (same topology, different node ids)
const DECOY_TOPO = [
  ["D-User0", "D-Enterprise0"],
  ["D-User0", "D-Enterprise1"],
  ["D-Enterprise0", "D-Op_Server0"],
  ["D-Enterprise1", "D-Op_Server0"],
];

// Display labels — human-readable names for each node
const LABEL = {
  Attacker:        "THREAT",
  User0:           "WS-DK",      // victim host — monitored via psutil (DK's machine)
  User1:           "WS-02",
  User2:           "WS-03",
  Enterprise0:     "FILE-SRV",
  Enterprise1:     "WEB-SRV",
  Op_Server0:      "DC-01",      // domain controller
  "D-User0":       "WS-DK",
  "D-Enterprise0": "FILE-SRV",
  "D-Enterprise1": "WEB-SRV",
  "D-Op_Server0":  "DC-01",
};
// Keep SHORT as an alias so existing references work
const SHORT = LABEL;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function edgePoints(a, b, r = R) {
  const dx = b.x - a.x, dy = b.y - a.y;
  const d  = Math.hypot(dx, dy) || 1;
  return {
    x1: a.x + (dx / d) * r,
    y1: a.y + (dy / d) * r,
    x2: b.x - (dx / d) * (r + 6),
    y2: b.y - (dy / d) * (r + 6),
  };
}

function scoreToColor(score) {
  if (score > 0.75) return { fill: "rgba(182,74,56,.13)", stroke: "#B64A38", label: "#D4604A" };
  if (score > 0.42) return { fill: "rgba(184,112,48,.10)", stroke: "#B87030", label: "#C98040" };
  return { fill: "rgba(77,139,102,.10)", stroke: "#4D8B66", label: "#5DA878" };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function LiveNetworkGraph({ nodes, somaState, honeypotMetrics, victimNode }) {
  const nodeMap = useMemo(
    () => Object.fromEntries((nodes || []).map((n) => [n.id, n])),
    [nodes]
  );

  const attacking  = ["INFECTED", "ISOLATING", "CONTAINED"].includes(somaState);
  const isolating  = ["ISOLATING", "CONTAINED", "PURGED"].includes(somaState);
  const contained  = ["CONTAINED", "PURGED"].includes(somaState);
  const purged     = somaState === "PURGED";

  const totalH = isolating ? H_REAL + H_GAP + H_DECOY : H_REAL;

  // Which real-network nodes to draw
  const realVisible = Object.keys(POS);

  return (
    <div className="lng-wrap">
      <div className="lng-header">
        <span className="lng-title">Attack Graph</span>
        <span className={`lng-state-tag lng-state-${somaState}`}>{somaState.replace("_", " ")}</span>
      </div>

      <div className="lng-svg-wrap">
      <svg viewBox={`0 0 ${W} ${totalH}`} className="lng-svg"
        style={{ transition: "height 0.5s ease" }}>
        <defs>
          {[
            { id: "arr-alert", color: "#B64A38" },
            { id: "arr-ok",    color: "#4D8B66" },
            { id: "arr-warn",  color: "#B87030" },
            { id: "arr-dim",   color: "#303631" },
            { id: "arr-decoy", color: "#2A6A8A" },
          ].map(({ id, color }) => (
            <marker key={id} id={id} markerWidth="7" markerHeight="7"
              refX="5" refY="3.5" orient="auto">
              <path d="M0,0.5 L0,6.5 L7,3.5 z" fill={color} />
            </marker>
          ))}

          <filter id="lng-glow" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="5" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>

          <style>{`
            .lng-attack-line {
              stroke-dasharray: 7 5;
              animation: lng-march .55s linear infinite;
            }
            .lng-redir-line {
              stroke-dasharray: 5 4;
              animation: lng-march .7s linear infinite;
            }
            .lng-decoy-edge {
              stroke-dasharray: 3 3;
            }
            .lng-trapped-line {
              stroke-dasharray: 6 4;
              animation: lng-march .9s linear infinite;
            }
            @keyframes lng-march { to { stroke-dashoffset: -12; } }
            .lng-hp-ring {
              animation: lng-hp-pulse 2s ease-in-out infinite;
            }
            @keyframes lng-hp-pulse {
              0%,100% { opacity: .12; }
              50%      { opacity: .35; }
            }
          `}</style>
        </defs>

        {/* ── Zone divider: EXTERNAL / INTERNAL ─────────────────────────── */}
        <line x1={125} y1={14} x2={125} y2={H_REAL - 14}
          stroke="#252A27" strokeWidth={1} strokeDasharray="3 5" />
        <text x={64} y={13} textAnchor="middle"
          fill="#303631" fontSize={7.5}
          fontFamily="'JetBrains Mono','Fira Code',monospace" letterSpacing="0.5">
          INTERNET
        </text>
        <text x={352} y={13} textAnchor="middle"
          fill="#303631" fontSize={7.5}
          fontFamily="'JetBrains Mono','Fira Code',monospace" letterSpacing="0.5">
          CORPORATE LAN
        </text>

        {/* ── Static real topology edges ─────────────────────────────────── */}
        {TOPO.map(([a, b], i) => {
          const { x1, y1, x2, y2 } = edgePoints(POS[a], POS[b]);
          return (
            <line key={i} x1={x1} y1={y1} x2={x2} y2={y2}
              stroke="#252A27" strokeWidth={1.2} />
          );
        })}

        {/* ── Attack edge: Attacker → victim node ───────────────────────── */}
        {attacking && !contained && (() => {
          const victimPos = POS[victimNode ?? "User0"] ?? POS.User0;
          const { x1, y1, x2, y2 } = edgePoints(POS.Attacker, victimPos);
          return <line x1={x1} y1={y1} x2={x2} y2={y2}
            stroke="#B64A38" strokeWidth={1.8}
            markerEnd="url(#arr-alert)" className="lng-attack-line" />;
        })()}

        {/* ── Redirect: victim → honeypot entry (attacker traffic diverted) */}
        {isolating && !purged && (() => {
          const victimPos = POS[victimNode ?? "User0"] ?? POS.User0;
          const sx = victimPos.x;
          const sy = victimPos.y + R + 2;
          const ex = DPOS["D-User0"].x;
          const ey = DPOS["D-User0"].y - R - 6;
          return (
            <line x1={sx} y1={sy} x2={ex} y2={ey}
              stroke={contained ? "#4D8B66" : "#B87030"} strokeWidth={1.6}
              markerEnd={contained ? "url(#arr-ok)" : "url(#arr-warn)"}
              className="lng-redir-line" />
          );
        })()}

        {/* ── Attacker now trapped: Attacker → D-User0 (contained) ──────── */}
        {contained && !purged && (() => {
          const { x1, y1 } = edgePoints(POS.Attacker, POS.User0);
          const ex = DPOS["D-User0"].x;
          const ey = DPOS["D-User0"].y - R - 6;
          // Curved path from attacker → decoy zone
          const cx = POS.Attacker.x - 10;
          const cy = (POS.Attacker.y + ey) / 2 + 30;
          return (
            <path
              d={`M ${POS.Attacker.x},${POS.Attacker.y + R + 2} C ${cx},${cy} ${cx},${cy} ${ex},${ey}`}
              fill="none"
              stroke="#4D8B66" strokeWidth={1.4} strokeOpacity={0.7}
              markerEnd="url(#arr-ok)" className="lng-trapped-line" />
          );
        })()}

        {/* ── Real network nodes ─────────────────────────────────────────── */}
        {realVisible.map((id) => {
          const { x, y } = POS[id];
          const n      = nodeMap[id];
          const score  = n?.anomaly_score ?? 0;
          const isVic  = id === (victimNode ?? "User0");
          const isAtk  = id === "Attacker";

          // When contained, real User0 shows as recovered
          const isRecovered = isVic && contained;

          let fill, stroke, labelColor;
          if (isAtk) {
            fill       = attacking ? "rgba(182,74,56,.15)" : "rgba(182,74,56,.06)";
            stroke     = attacking ? "#B64A38" : "#4A3030";
            labelColor = attacking ? "#D4604A" : "#6A4040";
          } else if (isRecovered) {
            fill       = "rgba(77,139,102,.12)";
            stroke     = "#4D8B66";
            labelColor = "#5DA878";
          } else {
            ({ fill, stroke, label: labelColor } = scoreToColor(score));
          }

          return (
            <g key={id}>
              {isVic && attacking && !contained && (
                <circle cx={x} cy={y} r={R + 5}
                  fill="#B64A38" fillOpacity={0.08} filter="url(#lng-glow)" />
              )}
              <circle cx={x} cy={y} r={R}
                fill={fill} stroke={stroke} strokeWidth={1.5} />
              <text x={x} y={y + (n ? -3 : 1)}
                textAnchor="middle" dominantBaseline="middle"
                fill={labelColor} fontSize={8.5}
                fontFamily="'JetBrains Mono','Fira Code',monospace"
                fontWeight="600" letterSpacing="0.5">
                {SHORT[id]}
              </text>
              {n && (
                <text x={x} y={y + 7}
                  textAnchor="middle" dominantBaseline="middle"
                  fill={labelColor} fontSize={7}
                  fontFamily="'JetBrains Mono','Fira Code',monospace"
                  fillOpacity={0.75}>
                  {score.toFixed(3)}
                </text>
              )}
              {isVic && (
                <text x={x} y={y - R - 7}
                  textAnchor="middle"
                  fill={isRecovered ? "#4D8B66" : "#B64A38"} fontSize={7}
                  fontFamily="'JetBrains Mono','Fira Code',monospace"
                  fontWeight="700" letterSpacing="1">
                  {isRecovered ? "SECURED" : "VICTIM"}
                </text>
              )}
            </g>
          );
        })}

        {/* ================================================================ */}
        {/* ── Honeypot / Decoy Network Section ────────────────────────────── */}
        {/* ================================================================ */}
        {isolating && (() => {
          const boxX  = 130;
          const boxY  = H_REAL + H_GAP - 8;
          const boxW  = W - boxX - 10;
          const boxH  = H_DECOY - 10;

          return (
            <g>
              {/* Section label */}
              <text x={W / 2} y={H_REAL + 14}
                textAnchor="middle"
                fill="#2A6A8A" fontSize={7.5}
                fontFamily="'JetBrains Mono','Fira Code',monospace"
                letterSpacing="1" fontWeight="600">
                ▼ TRAFFIC REDIRECTED INTO DOCKER HONEYPOT :8766 ▼
              </text>

              {/* Dashed container boundary */}
              <rect x={boxX} y={boxY} width={boxW} height={boxH} rx={6}
                fill="rgba(30,70,100,.07)"
                stroke={contained ? "#2A8A6A" : "#2A6A8A"}
                strokeWidth={1} strokeDasharray="6 4" />

              {/* Container label */}
              <text x={boxX + 8} y={boxY + 13}
                fill={contained ? "#2A8A6A" : "#2A6A8A"} fontSize={7}
                fontFamily="'JetBrains Mono','Fira Code',monospace"
                letterSpacing="0.8" fontWeight="700">
                DOCKER  soma_honeypot  :8766
              </text>

              {/* Decoy topology edges */}
              {DECOY_TOPO.map(([a, b], i) => {
                const { x1, y1, x2, y2 } = edgePoints(DPOS[a], DPOS[b]);
                return (
                  <line key={i} x1={x1} y1={y1} x2={x2} y2={y2}
                    stroke="#1A4A6A" strokeWidth={1} className="lng-decoy-edge" />
                );
              })}

              {/* Decoy nodes */}
              {Object.entries(DPOS).map(([id, { x, y }]) => {
                const isDecoyUser = id === "D-User0";
                const fill       = contained
                  ? "rgba(42,138,106,.15)"
                  : "rgba(42,106,138,.12)";
                const stroke     = contained ? "#2A8A6A" : "#2A6A8A";
                const labelColor = contained ? "#3ABAAA" : "#4A9ACA";

                return (
                  <g key={id}>
                    {/* Pulse ring on decoy user when active */}
                    {isDecoyUser && !purged && (
                      <circle cx={x} cy={y} r={R + 4}
                        fill="none" stroke={stroke} strokeWidth={1}
                        className="lng-hp-ring" />
                    )}
                    <circle cx={x} cy={y} r={R}
                      fill={fill} stroke={stroke} strokeWidth={1.5} />
                    <text x={x} y={y - 3}
                      textAnchor="middle" dominantBaseline="middle"
                      fill={labelColor} fontSize={8}
                      fontFamily="'JetBrains Mono','Fira Code',monospace"
                      fontWeight="600" letterSpacing="0.5">
                      {SHORT[id]}
                    </text>
                    <text x={x} y={y + 6}
                      textAnchor="middle" dominantBaseline="middle"
                      fill={labelColor} fontSize={6.5}
                      fontFamily="'JetBrains Mono','Fira Code',monospace"
                      fillOpacity={0.7}>
                      DECOY
                    </text>
                  </g>
                );
              })}

              {/* Honeypot metrics strip inside the container */}
              {honeypotMetrics && (() => {
                const items = [
                  { label: "CPU",   value: `${Math.round((honeypotMetrics.cpu ?? 0) * 100)}%` },
                  { label: "Procs", value: honeypotMetrics.processes ?? 0 },
                  { label: "Exfil", value: honeypotMetrics.exfil_attempts ?? 0 },
                  { label: "Scans", value: honeypotMetrics.lan_scans ?? 0 },
                ];
                const metY = boxY + boxH - 28;
                const startX = boxX + 20;
                const step = (boxW - 30) / items.length;
                return items.map(({ label, value }, i) => (
                  <g key={label}>
                    <text x={startX + i * step + step / 2} y={metY}
                      textAnchor="middle"
                      fill="#2A6A8A" fontSize={6.5}
                      fontFamily="'JetBrains Mono','Fira Code',monospace">
                      {label}
                    </text>
                    <text x={startX + i * step + step / 2} y={metY + 13}
                      textAnchor="middle"
                      fill={contained ? "#3ABAAA" : "#4A9ACA"} fontSize={9}
                      fontFamily="'JetBrains Mono','Fira Code',monospace"
                      fontWeight="700">
                      {value}
                    </text>
                  </g>
                ));
              })()}

              {/* PURGED overlay */}
              {purged && (
                <>
                  <rect x={boxX} y={boxY} width={boxW} height={boxH} rx={6}
                    fill="rgba(10,20,15,.55)" />
                  <text x={boxX + boxW / 2} y={boxY + boxH / 2 - 6}
                    textAnchor="middle"
                    fill="#B64A38" fontSize={12}
                    fontFamily="'JetBrains Mono','Fira Code',monospace"
                    fontWeight="700" letterSpacing="2">
                    PURGED
                  </text>
                  <text x={boxX + boxW / 2} y={boxY + boxH / 2 + 10}
                    textAnchor="middle"
                    fill="#4D3030" fontSize={7}
                    fontFamily="'JetBrains Mono','Fira Code',monospace">
                    Container destroyed · malware terminated
                  </text>
                </>
              )}
            </g>
          );
        })()}
      </svg>
      </div>
    </div>
  );
}
