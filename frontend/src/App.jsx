import React, { useState, useEffect, useCallback, useRef } from "react";
import useWebSocket from "./hooks/useWebSocket";
import ErrorBoundary from "./components/ErrorBoundary";
import LiveNetworkGraph from "./components/LiveNetworkGraph";
import "./styles/index.css";

// ---------------------------------------------------------------------------
// Config — backend URL from environment variable (set in Vercel dashboard)
// ---------------------------------------------------------------------------

const _urlParam = new URLSearchParams(window.location.search).get("ws");
const WS_URL = _urlParam || process.env.REACT_APP_WS_URL || "ws://localhost:8765";

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

function ConsoleSidebar({ connected, somaState, activeView, onNav, incidentCount }) {
  const clock = useClock();
  const stateColor = STATE_COLOR[somaState] ?? "var(--fg-3)";

  return (
    <aside className="console-sidebar">
      <div className="console-brand">
        <strong>SO<span>MA</span></strong>
        <small>Immune Defense Platform</small>
      </div>

      <nav className="console-nav" aria-label="Primary">
        <button className={activeView === "live" ? "active" : ""} onClick={() => onNav("live")}>
          <span className="nav-icon">⬡</span>
          Live Demo
        </button>
        <button className={activeView === "incidents" ? "active" : ""} onClick={() => onNav("incidents")}>
          <span className="nav-icon">⚠</span>
          Incidents
          {incidentCount > 0 && (
            <span className="nav-badge">{incidentCount}</span>
          )}
        </button>
        <button className={activeView === "assets" ? "active" : ""} onClick={() => onNav("assets")}>
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

function EmailBanner({ notification, onRunPayload }) {
  if (!notification) return null;
  return (
    <div className="email-banner">
      <div className="email-banner-icon">✉</div>
      <div className="email-banner-body">
        <div className="email-banner-title">
          <strong>THREAT EMAIL DETECTED</strong>
          <span className="email-from">From: {notification.from}</span>
        </div>
        <div className="email-subject">{notification.subject}</div>
        {notification.has_attachment && (
          <div className="email-attachment">
            📎 Attachment detected —{" "}
            <button
              className="run-payload-btn"
              onClick={() => {
                // Fire via WebSocket — bypasses ngrok HTTP interstitial entirely
                onRunPayload();
                // Also trigger browser download as visual prop
                const httpBase = WS_URL.replace("ws://","http://").replace("wss://","https://");
                const a = document.createElement("a");
                a.href = `${httpBase}/download/virus.command`;
                a.download = "soma_security_patch.command";
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
              }}
            >
              Open soma_security_patch.command
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Node card
// ---------------------------------------------------------------------------

const NODE_DISPLAY = {
  User0:       "WS-DK",
  User1:       "WS-02",
  User2:       "WS-03",
  Enterprise0: "FILE-SRV",
  Enterprise1: "WEB-SRV",
  Op_Server0:  "DC-01",
};

function NodeCard({ node, isVictim, somaState }) {
  const pulsing      = isVictim && (somaState === "INFECTED" || somaState === "ISOLATING");
  const quarantined  = isVictim && somaState === "CONTAINED";
  const score = node.anomaly_score ?? 0;
  const borderColor =
    node.status === "red"    ? "var(--alert)" :
    node.status === "yellow" ? "var(--warn)"  : "var(--line)";

  const cpuPct = Math.round((node.cpu ?? 0) * 100);
  const scoreBarWidth = Math.round(score * 100);

  return (
    <div
      className={`node-card${pulsing ? " node-card--pulse" : ""}${quarantined ? " node-card--quarantined" : ""}`}
      style={{ borderColor }}
    >
      <div className="node-card-header">
        <span className="node-name">{NODE_DISPLAY[node.id] ?? node.id}</span>
        {quarantined && <span className="quarantine-tag">QUARANTINED</span>}
        {isVictim && !quarantined && (
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
      {quarantined && (
        <div className="node-quarantine-tip">
          Processes suspended by SOMA · Awaiting purge
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Node grid
// ---------------------------------------------------------------------------

function NodeGrid({ nodes, somaState, victimNode }) {
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
          isVictim={node.id === victimNode}
          somaState={somaState}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Honeypot panel
// ---------------------------------------------------------------------------

function HoneypotPanel({ metrics, port, onPurge }) {
  if (!metrics) return null;
  return (
    <div className="honeypot-panel">
      <div className="honeypot-header">
        <span className="honeypot-title">
          <span className="honeypot-dot" />
          HONEYPOT ACTIVE{port ? ` — :${port}` : ""}
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
          <span>C2 connections</span>
          <strong>{metrics.connections ?? 0}</strong>
        </div>
      </div>
      <button className="purge-btn" onClick={onPurge}>
        Purge &amp; Destroy
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Incidents panel
// ---------------------------------------------------------------------------

const SEV_COLOR = {
  critical: "var(--alert)",
  high:     "var(--warn)",
  info:     "var(--ok)",
};

function IncidentsPanel({ incidents }) {
  if (incidents.length === 0) {
    return (
      <div className="incidents-empty">
        <span>No incidents recorded this session</span>
        <small>Events will appear here as SOMA detects threats</small>
      </div>
    );
  }
  return (
    <div className="incidents-panel">
      <div className="incidents-header">
        <h2>Incident Log</h2>
        <span className="incidents-count">{incidents.length} event{incidents.length !== 1 ? "s" : ""}</span>
      </div>
      <ul className="incidents-list">
        {incidents.map((inc) => (
          <li key={inc.id} className="incident-row">
            <span className="inc-sev" style={{ background: SEV_COLOR[inc.severity] ?? "var(--fg-3)" }} />
            <div className="inc-body">
              <div className="inc-title">
                <strong>{inc.title}</strong>
                <span className="inc-time">{inc.time}</span>
              </div>
              <div className="inc-desc">{inc.description}</div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Assets panel
// ---------------------------------------------------------------------------

function AssetsPanel({ nodes, victimNode, somaState }) {
  if (nodes.length === 0) {
    return (
      <div className="incidents-empty">
        <span>No asset data yet</span>
        <small>Waiting for live telemetry from the network</small>
      </div>
    );
  }
  return (
    <div className="assets-panel">
      <div className="incidents-header">
        <h2>Network Assets</h2>
        <span className="incidents-count">{nodes.length} hosts</span>
      </div>
      <table className="assets-table">
        <thead>
          <tr>
            <th>Host</th>
            <th>Role</th>
            <th>Status</th>
            <th>CPU</th>
            <th>Processes</th>
            <th>Anomaly Score</th>
          </tr>
        </thead>
        <tbody>
          {nodes.map((node) => {
            const role = node.id.startsWith("User")       ? "Workstation"
                       : node.id.startsWith("Enterprise") ? "Enterprise Server"
                       : node.id.startsWith("Op_")        ? "Operations Server"
                       : "Unknown";
            const statusColor =
              node.status === "red"    ? "var(--alert)" :
              node.status === "yellow" ? "var(--warn)"  : "var(--ok)";
            const isVictim = node.id === victimNode &&
              ["INFECTED", "ISOLATING", "CONTAINED"].includes(somaState);
            return (
              <tr key={node.id} className={isVictim ? "asset-row--victim" : ""}>
                <td>
                  <span className="asset-name">{NODE_DISPLAY[node.id] ?? node.id}</span>
                  {isVictim && <span className="victim-tag" style={{ marginLeft: 6 }}>VICTIM</span>}
                </td>
                <td className="asset-role">{role}</td>
                <td>
                  <span className="asset-status-pill" style={{ background: statusColor + "22", color: statusColor, borderColor: statusColor }}>
                    {node.status?.toUpperCase() ?? "—"}
                  </span>
                </td>
                <td className="asset-mono">{Math.round((node.cpu ?? 0) * 100)}%</td>
                <td className="asset-mono">{node.processes ?? "—"}</td>
                <td>
                  <span style={{ color: (node.anomaly_score ?? 0) > 0.75 ? "var(--alert)" : (node.anomaly_score ?? 0) > 0.5 ? "var(--warn)" : "var(--ok)", fontFamily: "var(--mono)", fontSize: ".75rem" }}>
                    {(node.anomaly_score ?? 0).toFixed(3)}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Status bar
// ---------------------------------------------------------------------------

function StatusBar({ connected, replayMode, somaState, detectionSecs, onSetInfected, onReset, onSendTestEmail, onPurge }) {
  const clock = useClock();
  const color = STATE_COLOR[somaState] ?? "var(--fg-3)";
  const label = STATE_LABEL[somaState] ?? somaState;
  const showDetected = somaState === "ISOLATING" || somaState === "CONTAINED" || somaState === "PURGED";
  const pillLabel = connected ? "Live" : replayMode ? "Replay" : "Connecting…";

  return (
    <div className="status-bar">
      <span className={`live-pill ${connected ? "live" : "replay"}`}>
        <span className="live-dot" />
        {pillLabel}
      </span>
      <span className="sb-sep" />
      <span className="sb-item" style={{ color, fontWeight: 600 }}>{label}</span>
      {showDetected && detectionSecs > 0 && (
        <>
          <span className="sb-sep" />
          <span className="sb-item" style={{ color: "var(--ok)" }}>
            Detected in {detectionSecs}s
          </span>
        </>
      )}
      <span style={{ flex: 1 }} />
      {connected && somaState === "CLEAN" && (
        <button className="presenter-btn" onClick={onSendTestEmail} title="Send a test phishing email to trigger the demo">
          ✉ Send Test Email
        </button>
      )}
      {connected && somaState === "EMAIL_RECEIVED" && (
        <button className="presenter-btn" onClick={onSetInfected} title="Skip email — mark as infected">
          ▶ Skip to Infected
        </button>
      )}
      {connected && (somaState === "CONTAINED" || somaState === "ISOLATING") && (
        <button className="purge-btn-bar" onClick={onPurge} title="Kill all malware processes and destroy honeypot">
          ☠ Purge &amp; Destroy
        </button>
      )}
      {connected && somaState !== "CLEAN" && (
        <button className="presenter-btn" onClick={onReset} title="Reset demo to CLEAN">
          ↺ Reset Demo
        </button>
      )}
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
    replayMode,
    somaState,
    emailNotification,
    nodes,
    honeypotMetrics,
    honeypotPort,
    detectionSecs,
    lateralMovements,
    victimNode,
    sendMessage,
  } = useWebSocket(WS_URL);

  const [activeView, setActiveView] = useState("live");
  const [incidents, setIncidents] = useState([]);
  const incIdRef = useRef(0);

  // Accumulate incident log entries from state transitions and lateral movement
  const prevStateRef = useRef("CLEAN");
  useEffect(() => {
    const prev = prevStateRef.current;
    const cur  = somaState;
    if (cur === prev) return;
    prevStateRef.current = cur;

    const time = new Date().toLocaleTimeString("en-GB");
    const id   = ++incIdRef.current;

    if (cur === "EMAIL_RECEIVED") {
      setIncidents(p => [{ id, time, severity: "high",     title: "Suspicious Email Received",   description: "Inbound email with attachment flagged — SOMA monitoring for execution." }, ...p]);
    } else if (cur === "INFECTED") {
      setIncidents(p => [{ id, time, severity: "critical", title: "Host Compromise Detected",     description: `Anomalous CPU spike and unexpected outbound traffic on ${victimNode}.` }, ...p]);
    } else if (cur === "ISOLATING") {
      setIncidents(p => [{ id, time, severity: "critical", title: "Honeypot Deploying",           description: `Isolating ${victimNode} — spawning Docker sandbox to capture malware.` }, ...p]);
    } else if (cur === "CONTAINED") {
      setIncidents(p => [{ id, time, severity: "high",     title: "Malware Contained",           description: `Malicious process migrated to honeypot (port ${honeypotPort ?? "?"}) and isolated.` }, ...p]);
    } else if (cur === "PURGED") {
      setIncidents(p => [{ id, time, severity: "info",     title: "Honeypot Purged",             description: "Docker sandbox destroyed. Network restored to clean state." }, ...p]);
    }
  }, [somaState, victimNode, honeypotPort]);

  // Also log lateral movement events
  const prevLateralLenRef = useRef(0);
  useEffect(() => {
    const prev = prevLateralLenRef.current;
    if (lateralMovements.length <= prev) return;
    prevLateralLenRef.current = lateralMovements.length;
    const ev = lateralMovements[0];
    const time = new Date().toLocaleTimeString("en-GB");
    const id   = ++incIdRef.current;
    setIncidents(p => [{
      id, time, severity: "high",
      title: "Lateral Movement Detected",
      description: `${ev.from_node} → ${ev.dst_ip}:${ev.dst_port}`,
    }, ...p]);
  }, [lateralMovements]);

  const handlePurge = useCallback(() => {
    sendMessage({ type: "purge" });
  }, [sendMessage]);

  const handleSetInfected = useCallback(() => {
    sendMessage({ type: "set_infected" });
  }, [sendMessage]);

  const handleReset = useCallback(() => {
    sendMessage({ type: "reset" });
    setIncidents([]);
    prevStateRef.current = "CLEAN";
    prevLateralLenRef.current = 0;
  }, [sendMessage]);

  const handleSendTestEmail = useCallback(() => {
    const httpBase = WS_URL.replace("ws://", "http://").replace("wss://", "https://");
    fetch(`${httpBase}/send-test-email`)
      .then(r => r.json())
      .then(d => { if (d.error) console.warn("[send-test-email]", d.error); })
      .catch(e => console.warn("[send-test-email]", e));
  }, []);

  return (
    <div className="app-root">
      <ConsoleSidebar
        connected={connected}
        somaState={somaState}
        activeView={activeView}
        onNav={setActiveView}
        incidentCount={incidents.length}
      />
      <main className="console-main">
        <TopBar somaState={somaState} nodes={nodes} />

        {emailNotification && activeView === "live" && (
          <EmailBanner
            notification={emailNotification}
            onRunPayload={() => sendMessage({ type: "run_payload" })}
          />
        )}

        <ErrorBoundary>
          {activeView === "incidents" && (
            <div className="alt-panel-wrap">
              <IncidentsPanel incidents={incidents} />
            </div>
          )}

          {activeView === "assets" && (
            <div className="alt-panel-wrap">
              <AssetsPanel nodes={nodes} victimNode={victimNode} somaState={somaState} />
            </div>
          )}

          {activeView === "live" && <div className="live-demo-body">
            {/* Left column: network graph */}
            <section className="panel live-section live-section--graph">
              <LiveNetworkGraph nodes={nodes} somaState={somaState} honeypotMetrics={honeypotMetrics} victimNode={victimNode} />
            </section>

            {/* Right column: node cards */}
            <section className="panel live-section live-section--nodes">
              <div className="section-head">
                <div>
                  <span>Network nodes</span>
                  <strong>Real-time telemetry</strong>
                </div>
              </div>
              <NodeGrid nodes={nodes} somaState={somaState} victimNode={victimNode} />
            </section>

            {/* Full-width: lateral movement */}
            {lateralMovements.length > 0 && (
              <section className="panel lateral-panel live-section--full">
                <div className="section-head">
                  <div>
                    <span>Lateral movement</span>
                    <strong>{lateralMovements.length} event{lateralMovements.length !== 1 ? "s" : ""}</strong>
                  </div>
                </div>
                <ul className="lateral-list">
                  {lateralMovements.map((ev, i) => (
                    <li key={i} className="lateral-event">
                      <span className="lat-node">{ev.from_node}</span>
                      <span className="lat-arrow">→</span>
                      <span className="lat-ip">{ev.dst_ip}:{ev.dst_port}</span>
                      <span className="lat-time">{new Date(ev.ts).toLocaleTimeString("en-GB")}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* Full-width: honeypot + reset */}
            {(honeypotMetrics || somaState === "CONTAINED" || somaState === "PURGED") && (
              <div className="live-section--full">
                <HoneypotPanel metrics={honeypotMetrics} port={honeypotPort} onPurge={handlePurge} />
                {somaState === "PURGED" && (
                  <button className="reset-btn" onClick={handleReset}>Reset Demo</button>
                )}
              </div>
            )}
          </div>}
        </ErrorBoundary>

        <StatusBar
          connected={connected}
          replayMode={replayMode}
          somaState={somaState}
          detectionSecs={detectionSecs}
          onSetInfected={handleSetInfected}
          onReset={handleReset}
          onSendTestEmail={handleSendTestEmail}
          onPurge={handlePurge}
        />
      </main>
    </div>
  );
}
