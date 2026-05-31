import React, { useState, useEffect } from "react";

const KAPPA_COLOR = ["#22d3ee", "#a855f7", "#f59e0b"];

function delta(learned, pbe) {
  const d = Math.abs(learned - pbe);
  const color = d < 0.05 ? "#22d3ee" : d < 0.15 ? "#f59e0b" : "#ef4444";
  const label = d < 0.05 ? "converged" : d < 0.15 ? "close" : "diverged";
  return { d: d.toFixed(3), color, label };
}

export default function ConvergencePanel() {
  const [comparison, setComparison] = useState(null);
  const [imgError, setImgError]     = useState({});

  useEffect(() => {
    fetch("/comparison.json")
      .then((r) => r.json())
      .then(setComparison)
      .catch(() => {});
  }, []);

  const rows = comparison
    ? Object.values(comparison).sort((a, b) => a.kappa - b.kappa)
    : null;

  return (
    <div className="panel-inner" style={{ overflowY: "auto" }}>
      <h3 className="panel-title">Layer 3 — Signaling Game: RL vs PBE</h3>

      {/* Hero convergence plot */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 11, color: "var(--fg-3)", marginBottom: 6 }}>
          Learned honeypot baiting rate r converging toward PBE equilibrium r*
        </div>
        {imgError.convergence ? (
          <div style={placeholderStyle}>convergence_plot.png — run train_deception.py to generate</div>
        ) : (
          <img
            src="/convergence_plot.png"
            alt="RL convergence to PBE"
            style={{ width: "100%", borderRadius: 4, border: "1px solid var(--border)" }}
            onError={() => setImgError((e) => ({ ...e, convergence: true }))}
          />
        )}
      </div>

      {/* κ sweep (theoretical) */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 11, color: "var(--fg-3)", marginBottom: 6 }}>
          Theoretical κ sweep — optimal r* and μ* vs attacker attention cost
        </div>
        {imgError.kappa ? (
          <div style={placeholderStyle}>kappa_sweep.png — run train_deception.py to generate</div>
        ) : (
          <img
            src="/kappa_sweep.png"
            alt="κ sweep"
            style={{ width: "100%", borderRadius: 4, border: "1px solid var(--border)" }}
            onError={() => setImgError((e) => ({ ...e, kappa: true }))}
          />
        )}
      </div>

      {/* Comparison table */}
      <div>
        <div style={{ fontSize: 11, color: "var(--fg-3)", marginBottom: 8 }}>
          RL vs PBE mixing rates — primary validation of deception layer theory
        </div>
        {rows ? (
          <table style={tableStyle}>
            <thead>
              <tr>
                {["κ", "Learned q", "PBE q*", "Learned r", "PBE r*", "Δr", ""].map((h) => (
                  <th key={h} style={thStyle}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => {
                const { d, color, label } = delta(row.learned_r, row.pbe_r_star);
                return (
                  <tr key={row.kappa} style={{ borderTop: "1px solid var(--border)" }}>
                    <td style={tdStyle}>
                      <span style={{ color: KAPPA_COLOR[i] }}>{row.kappa.toFixed(1)}</span>
                    </td>
                    <td style={tdStyle}>{row.learned_q.toFixed(3)}</td>
                    <td style={{ ...tdStyle, color: "var(--fg-3)" }}>{row.pbe_q_star.toFixed(3)}</td>
                    <td style={tdStyle}>{row.learned_r.toFixed(3)}</td>
                    <td style={{ ...tdStyle, color: "var(--fg-3)" }}>{row.pbe_r_star.toFixed(3)}</td>
                    <td style={{ ...tdStyle, color }}>{d}</td>
                    <td style={{ ...tdStyle, color, fontSize: 10 }}>{label}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <div style={placeholderStyle}>
            comparison.json not found — run scripts/train_deception.py to generate
          </div>
        )}
      </div>

      <div style={{ marginTop: 12, fontSize: 10, color: "var(--fg-3)", lineHeight: 1.5 }}>
        Δr &lt; 0.05 = converged · &lt; 0.15 = close · ≥ 0.15 = diverged
        <br />
        Heuristic bridge to CybORG uses threshold trigger (score &gt; 0.7), not the game policy —
        B_lineAgent does not respond to signals.
      </div>
    </div>
  );
}

const placeholderStyle = {
  padding: "12px 16px",
  background: "var(--surface-2)",
  borderRadius: 4,
  fontSize: 11,
  color: "var(--fg-3)",
  fontStyle: "italic",
};

const tableStyle = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: 12,
};

const thStyle = {
  padding: "4px 8px",
  textAlign: "left",
  color: "var(--fg-3)",
  fontWeight: 500,
  fontSize: 11,
  borderBottom: "1px solid var(--border)",
};

const tdStyle = {
  padding: "5px 8px",
  fontFamily: "monospace",
};
