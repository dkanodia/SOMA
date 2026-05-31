import React, { useState, useEffect, useCallback } from "react";
import useWebSocket from "./hooks/useWebSocket";
import "./styles/index.css";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const WS_URL = process.env.REACT_APP_WS_URL || "ws://localhost:8765";

const STATE_COLOR = {
  CLEAN:          "var(--ok)",
  EMAIL_RECEIVED: "var(--warn)",
  INFECTED:       "var(--alert)",
  ISOLATING:      "var(--alert)",
  CONTAINED:      "var(--warn)",
  PURGED:         "var(--ok)",
};

const STATE_LABEL = {
  CLEAN:          "System clean",
  EMAIL_RECEIVED: "Email received — threat inbound",
  INFECTED:       "INFECTED — attack detected",
  ISOLATING:      "ISOLATING — honeypot deploying",
  CONTAINED:      "CONTAINED — malware trapped",
  PURGED:         "PURGED — system restored",
};

// ---------------------------------------------------------------------------
// Clock
// ---------------------------------------------------------------------------

function useClock() {
  const [clock, setClock] = useState(() =>
    new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
  );
  useEffect(() => {
    const t = setInterval(() =>
      setClock(new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" }))
    , 1000);
    return () => clearInterval(t);
  }, []);
  return clock;
}

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------

function ConsoleSidebar({ connected, somaState }) {
  const clock = useClock();
  const stateColor = STATE_COLOR[somaState] ?? "var(--fg-3)";

  return (
    <aside className="console-sidebar">
      <div className="console-brand">
        <strong>SO<span>MA</span></strong>
        <small>Immune Defense Platform</small>
      </div>

      <nav className="console-nav" aria-label="Primary">
        <button className="active">
          <span className="nav-icon">⬡</span>
          Live Demo
        </button>
        <button disabled style={{ opacity: 0.4 }}>
          <span className="nav-icon">⚠</span>
          Incidents
        </button>
        <button disabled style={{ opacity: 0.4 }}>
          <span className="nav-icon">□</span>
          Assets
        </button>
      </nav>

      <div className="sidebar-state-badge" style={{ borderColor: stateColor, color: stateColor }}>
        <span className="live-dot" style={{ background: stateColor }} />
        {somaState}
      </div>

      <div className="sidebar-footer">
        <div className="analyst-card">
          <div className="analyst-avatar">DK</div>
          <div>
            <strong>Analyst on duty</strong>
            <span>D. Kanodia</span>
          </div>
        </div>
        <div className="connection-card">
          <span className={connected ? "status-dot live" : "status-dot"} />
          <div>
            <strong>{connected ? "Live feed" : "Connecting…"}</strong>
            <span>{connected ? clock : "Awaiting server"}</span>
          </div>
        </div>
      </div>
    </aside>
  );
}

// ---------------------------------------------------------------------------
// Email notification banner
// ---------------------------------------------------------------------------

function EmailBanner({ notification, onDownload }) {
  if (!notification) return null;
  return (
    <div className="email-banner">
      <div className="email-banner-icon">✉</div>
      <div className="email-banner-body">
        <div className="email-banner-title">
          <strong>NEW EMAIL DETECTED</strong>
          <span className="email-from">From: {notification.from}</span>
        </div>
        <div className="email-subject">{notification.subject}</div>
        <div className="email-attachment">📎 soma_security_patch.command</div>
      </div>
      <button className="download-btn" onClick={onDownload}>
        Download File
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Node card
// ---------------------------------------------------------------------------

function NodeCard({ node, isVictim, somaState }) {
  const pulsing = isVictim && (somaState === "INFECTED" || somaState === "ISOLATING");
  const score = node.anomaly_score ?? 0;
  const borderColor =
    node.status === "red"    ? "var(--alert)" :
    node.status === "yellow" ? "var(--warn)"  : "var(--line)";

  const cpuPct = Math.round((node.cpu ?? 0) * 100);
  const scoreBarWidth = Math.round(score * 100);

  return (
    <div
      className={`node-card${pulsing ? " node-card--pulse" : ""}`}
      style={{ borderColor }}
    >
      <div className="node-card-header">
        <span className="node-name">{node.id}</span>
        {isVictim && (
          <span className="victim-tag">VICTIM</span>
        )}
        <span
          className="node-status-dot"
          style={{ background: borderColor }}
        />
      </div>

      <div className="node-metric-row">
        <span className="node-metric-label">CPU</span>
        <div className="node-bar-track">
          <div
            className="node-bar-fill"
            style={{
              width: `${cpuPct}%`,
              background: node.status === "red" ? "var(--alert)" : node.status === "yellow" ? "var(--warn)" : "var(--ok)",
            }}
          />
        </div>
        <span className="node-metric-value">{cpuPct}%</span>
      </div>

      <div className="node-metric-row">
        <span className="node-metric-label">Procs</span>
        <span className="node-metric-value mono">{node.processes ?? "—"}</span>
      </div>

      <div className="node-metric-row">
        <span className="node-metric-label">Score</span>
        <div className="node-bar-track">
          <div
            className="node-bar-fill score-bar"
            style={{
              width: `${scoreBarWidth}%`,
              background: score > 0.75 ? "var(--alert)" : score > 0.5 ? "var(--warn)" : "var(--ok)",
            }}
          />
        </div>
        <span className="node-metric-value">{score.toFixed(3)}</span>
      </div>

      {pulsing && (
        <div className="node-threat-tip">
          CPU spike · Unexpected outbound · Anomaly: {score.toFixed(2)}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Node grid
// ---------------------------------------------------------------------------

function NodeGrid({ nodes, somaState }) {
  if (nodes.length === 0) {
    return (
      <div className="node-grid-empty">
        Waiting for live metrics…
      </div>
    );
  }
  return (
    <div className="node-grid">
      {nodes.map((node) => (
        <NodeCard
          key={node.id}
          node={node}
          isVictim={node.id === "User0"}
          somaState={somaState}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Honeypot panel
// ---------------------------------------------------------------------------

function HoneypotPanel({ metrics, onPurge }) {
  if (!metrics) return null;
  return (
    <div className="honeypot-panel">
      <div className="honeypot-header">
        <span className="honeypot-title">
          <span className="honeypot-dot" />
          HONEYPOT ACTIVE — :8766
        </span>
        <span className="honeypot-sub">Docker sandbox capturing malicious activity</span>
      </div>
      <div className="honeypot-metrics">
        <div className="hp-metric">
          <span>CPU telemetry</span>
          <strong>{Math.round((metrics.cpu ?? 0) * 100)}%</strong>
        </div>
        <div className="hp-metric">
          <span>Process count</span>
          <strong>{metrics.processes ?? 0}</strong>
        </div>
        <div className="hp-metric">
          <span>Exfil attempts</span>
          <strong>{metrics.exfil_attempts ?? 0}</strong>
        </div>
        <div className="hp-metric">
          <span>LAN scans</span>
          <strong>{metrics.lan_scans ?? 0}</strong>
        </div>
      </div>
      <button className="purge-btn" onClick={onPurge}>
        Purge &amp; Destroy
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Status bar
// ---------------------------------------------------------------------------

function StatusBar({ connected, somaState }) {
  const clock = useClock();
  const color = STATE_COLOR[somaState] ?? "var(--fg-3)";
  const label = STATE_LABEL[somaState] ?? somaState;

  return (
    <div className="status-bar">
      <span className={`live-pill ${connected ? "live" : "replay"}`}>
        <span className="live-dot" />
        {connected ? "Live" : "Disconnected"}
      </span>
      <span className="sb-sep" />
      <span className="sb-item" style={{ color, fontWeight: 600 }}>{label}</span>
      <span className="sb-sep" />
      <span className="sb-item">{clock}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Top bar
// ---------------------------------------------------------------------------

function TopBar({ somaState, nodes }) {
  const redCount    = nodes.filter((n) => n.status === "red").length;
  const maxScore    = nodes.reduce((m, n) => Math.max(m, n.anomaly_score ?? 0), 0);
  const isAttacking = ["INFECTED", "ISOLATING", "CONTAINED"].includes(somaState);

  return (
    <header className="topbar">
      <div className="topbar-title">
        <p>SOMA / Live Demo</p>
        <h1>Security Operations Center</h1>
      </div>
      <div className="topbar-metrics">
        <div className={`metric ${isAttacking ? "critical" : "nominal"}`}>
          <span>Posture</span>
          <strong>{isAttacking ? "Critical" : somaState === "PURGED" ? "Restored" : "Nominal"}</strong>
        </div>
        <div className="metric">
          <span>Hosts at risk</span>
          <strong>{redCount} / {nodes.length}</strong>
        </div>
        <div className="metric">
          <span>Peak anomaly</span>
          <strong>{maxScore.toFixed(3)}</strong>
        </div>
      </div>
    </header>
  );
}

// ---------------------------------------------------------------------------
// Main App
// ---------------------------------------------------------------------------

export default function App() {
  const {
    connected,
    somaState,
    emailNotification,
    nodes,
    honeypotMetrics,
    sendMessage,
  } = useWebSocket(WS_URL);

  const [downloaded, setDownloaded] = useState(false);

  const handleDownload = useCallback(() => {
    window.location.href = "http://localhost:8765/download/virus.command";
    setDownloaded(true);
    // Clear banner after download
    setTimeout(() => {}, 0);
  }, []);

  const handlePurge = useCallback(() => {
    sendMessage({ type: "purge" });
  }, [sendMessage]);

  // Clear email banner after download
  const showBanner = emailNotification && !downloaded;

  return (
    <div className="app-root">
      <ConsoleSidebar connected={connected} somaState={somaState} />
      <main className="console-main">
        <TopBar somaState={somaState} nodes={nodes} />

        {showBanner && (
          <EmailBanner
            notification={emailNotification}
            onDownload={handleDownload}
          />
        )}

        <div className="live-demo-body">
          <section className="panel live-section">
            <div className="section-head">
              <div>
                <span>Network nodes</span>
                <strong>Real-time telemetry</strong>
              </div>
            </div>
            <NodeGrid nodes={nodes} somaState={somaState} />
          </section>

          <HoneypotPanel metrics={honeypotMetrics} onPurge={handlePurge} />
        </div>

        <StatusBar connected={connected} somaState={somaState} />
      </main>
    </div>
  );
}
