import React, { useMemo, useState, useEffect } from "react";
import NetworkGraph       from "./components/NetworkGraph";
import TimelinePanel      from "./components/TimelinePanel";
import IncidentPanel      from "./components/IncidentPanel";
import DefenseActionPanel from "./components/DefenseActionPanel";
import DriftPanel         from "./components/DriftPanel";
import HoneypotPanel      from "./components/HoneypotPanel";
import LayerRadarPanel    from "./components/LayerRadarPanel";
import EvasionPanel       from "./components/EvasionPanel";
import useWebSocket       from "./hooks/useWebSocket";
import "./styles/index.css";

const HOSTS = ["User0", "User1", "User2", "Enterprise0", "Enterprise1", "Op_Server0"];

// Base session time: today at 08:00 local
const SESSION_BASE = (() => {
  const d = new Date();
  d.setHours(8, 0, 0, 0);
  return d.getTime();
})();

function stepToTimestamp(step) {
  const t = new Date(SESSION_BASE + step * 30_000); // 30 s per step
  return t.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function stepToDate(step) {
  const t = new Date(SESSION_BASE + step * 30_000);
  return t.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

function actionLabel(actionName) {
  if (!actionName || actionName === "Monitor") return "Monitor";
  return actionName.replace("_", " ");
}

function getSeverity(state) {
  const score = state?.top_threat?.score ?? 0;
  if (score >= 0.75) return { label: "Critical", className: "critical" };
  if (score >= 0.45) return { label: "Elevated", className: "elevated" };
  if (state?.is_attack) return { label: "Investigating", className: "elevated" };
  return { label: "Nominal", className: "nominal" };
}

function incidentId(host, step) {
  // Deterministic ticket ID from host + step
  const n = (host.charCodeAt(0) * 31 + (step ?? 0)) % 9000 + 1000;
  return `INC-${n}`;
}

function ConsoleSidebar({ connected }) {
  const [clock, setClock] = React.useState(() =>
    new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
  );
  useEffect(() => {
    const t = setInterval(() =>
      setClock(new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" }))
    , 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <aside className="console-sidebar">
      <div className="console-brand">
        <strong>SO<span>MA</span></strong>
        <small>Immune Defense Platform</small>
      </div>
      <nav className="console-nav" aria-label="Primary">
        <button className="active">Operations</button>
        <button>Incidents</button>
        <button>Assets</button>
        <button>Policies</button>
        <button>Audit Log</button>
      </nav>
      <div className="sidebar-spacer" />
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
          <strong>{connected ? "Live feed" : "Session replay"}</strong>
          <span>{connected ? clock : "Historical analysis"}</span>
        </div>
      </div>
    </aside>
  );
}

function TopBar({ state, step }) {
  const severity = getSeverity(state);
  const topHost  = state?.top_threat?.host ?? "—";
  const action   = actionLabel(state?.orchestrator?.action_name);
  const ts       = stepToTimestamp(step);
  const date     = stepToDate(step);

  return (
    <header className="topbar">
      <div className="topbar-title">
        <p>Operations / Threat Response</p>
        <h1>Security Operations Center</h1>
      </div>
      <div className="topbar-metrics">
        <div className={`metric ${severity.className}`}>
          <span>Posture</span>
          <strong>{severity.label}</strong>
        </div>
        <div className="metric">
          <span>Priority host</span>
          <strong>{topHost}</strong>
        </div>
        <div className="metric action">
          <span>Recommended action</span>
          <strong>{action}</strong>
        </div>
      </div>
      <div className="topbar-clock">
        <div className="clock-time">{ts}</div>
        <div className="clock-date">{date}</div>
      </div>
    </header>
  );
}

function IncidentQueue({ state, onSelectHost, selectedHost, step }) {
  const incidents = state?.incidents ?? [];
  const rows = incidents.length
    ? incidents
    : HOSTS.map((host) => ({
        host,
        confidence: "CLEAR",
        score: 0,
        attack_type: "No threats detected",
        explanation: "All systems nominal",
      }));

  return (
    <section className="panel queue-panel">
      <div className="section-head">
        <div>
          <span>Incident queue</span>
          <strong>{incidents.length ? `${incidents.length} active` : "All clear"}</strong>
        </div>
        <button className="small-button">Filter</button>
      </div>
      <div className="queue-list">
        {rows.slice(0, 8).map((inc) => (
          <button
            key={`${inc.host}-${inc.attack_type}`}
            className={`queue-row ${selectedHost === inc.host ? "selected" : ""} ${inc.confidence?.toLowerCase()}`}
            onClick={() => onSelectHost(inc.host)}
          >
            <div className="queue-row-top">
              <span className="host-name">{inc.host}</span>
              <span className={`inc-conf ${inc.confidence}`}>{inc.confidence}</span>
            </div>
            <span className="queue-desc">{inc.attack_type?.replaceAll("_", " ")}</span>
            <div className="queue-row-foot">
              <span className="queue-ticket">{incidentId(inc.host, step)}</span>
              <span className="queue-score">{inc.score ? inc.score.toFixed(3) : "—"}</span>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}

function ResponseApproval({ state, selectedHost }) {
  const orch = state?.orchestrator ?? {};
  const actionName = orch.action_name ?? "Monitor";
  const isRemove = actionName.startsWith("Remove");
  const suppressed = state?.tolerance_suppressed ?? [];
  const breached = state?.tolerance_breached ?? [];

  return (
    <section className="panel approval-panel">
      <div className="section-head">
        <div>
          <span>Response approval</span>
          <strong>{actionLabel(actionName)}</strong>
        </div>
        <span className={`approval-badge ${isRemove ? "danger" : ""}`}>
          {isRemove ? "Needs admin approval" : "Auto-safe"}
        </span>
      </div>

      <div className="approval-body">
        <div className="approval-summary">
          <span>Target</span>
          <strong>{orch.host || selectedHost || "Network"}</strong>
          <p>{orch.reason || "No active incidents detected. Continue monitoring."}</p>
        </div>
        <div className="approval-actions">
          <button className="primary-action">{isRemove ? "Approve removal" : "Keep monitoring"}</button>
          <button>Open host details</button>
          <button>Suppress for 1 hour</button>
        </div>
      </div>

      <div className="guardrails">
        <div>
          <strong>{suppressed.length}</strong>
          <span>suppressed as normal</span>
        </div>
        <div>
          <strong>{breached.length}</strong>
          <span>role breaches</span>
        </div>
        <div>
          <strong>{orch.confidence ?? "NONE"}</strong>
          <span>confidence gate</span>
        </div>
      </div>
    </section>
  );
}

function AssetTable({ state, selectedHost, onSelectHost }) {
  const compromised = new Set(state?.compromised_hosts ?? []);
  const driftScores = state?.drift_scores ?? {};
  const hostScores = state?.host_innate_scores ?? {};
  const breached = new Set(state?.tolerance_breached ?? []);
  const suppressed = new Set(state?.tolerance_suppressed ?? []);

  return (
    <section className="panel asset-panel">
      <div className="section-head">
        <div>
          <span>Protected assets</span>
          <strong>{HOSTS.length} hosts</strong>
        </div>
        <button className="small-button">Export</button>
      </div>
      <div className="asset-table">
        <div className="asset-row asset-header">
          <span>Host</span>
          <span>Status</span>
          <span>Anomaly</span>
          <span>Drift</span>
        </div>
        {HOSTS.map((host) => {
          const status = compromised.has(host)
            ? "Compromised"
            : breached.has(host)
              ? "Role breach"
              : suppressed.has(host)
                ? "Tolerated"
                : "Healthy";
          return (
            <button
              key={host}
              className={`asset-row ${selectedHost === host ? "selected" : ""}`}
              onClick={() => onSelectHost(host)}
            >
              <span>{host}</span>
              <span className={`asset-status ${status.toLowerCase().replace(" ", "-")}`}>{status}</span>
              <span>{(hostScores[host] ?? 0).toFixed(2)}</span>
              <span>{(driftScores[host] ?? 0).toFixed(1)}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function EvidenceTabs({ state, meta, step, setStep }) {
  const [tab, setTab] = useState("timeline");
  return (
    <section className="panel evidence-panel">
      <div className="tab-strip">
        {[
          ["timeline",  "Timeline"],
          ["incidents", "Incidents"],
          ["actions",   "Actions"],
          ["drift",     "Drift"],
          ["decoys",    "Decoys"],
          ["layers",    "Layers"],
          ["evasion",   "Evasion"],
        ].map(([id, label]) => (
          <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </div>
      <div className="evidence-body">
        {tab === "timeline"  && <TimelinePanel state={state} meta={meta} currentStep={step} onStepClick={setStep} />}
        {tab === "incidents" && <IncidentPanel state={state} step={step} />}
        {tab === "actions"   && <DefenseActionPanel state={state} meta={meta} step={step} />}
        {tab === "drift"     && <DriftPanel state={state} />}
        {tab === "decoys"    && <HoneypotPanel state={state} />}
        {tab === "layers"    && <LayerRadarPanel state={state} meta={meta} />}
        {tab === "evasion"   && <EvasionPanel meta={meta} />}
      </div>
    </section>
  );
}

export default function App() {
  const {
    state, meta, step, totalSteps, connected, setStep,
  } = useWebSocket(process.env.REACT_APP_WS_URL || "ws://localhost:8765");

  const currentState = state ?? {};
  const [selectedHost, setSelectedHost] = useState("Op_Server0");

  const compromisedCount = currentState.compromised_hosts?.length ?? 0;
  const incidentCount    = currentState.incidents?.length ?? 0;
  const learnedType      = currentState.learned_attack_type && currentState.learned_attack_type !== "unknown"
    ? currentState.learned_attack_type.replaceAll("_", " ")
    : "Unclassified";
  const detectionRate    = totalSteps > 0
    ? `${Math.round((step / Math.max(totalSteps - 1, 1)) * 100)}%`
    : "—";

  const summary = useMemo(() => [
    { label: "Monitored assets",   value: `${HOSTS.length} hosts` },
    { label: "Compromised",        value: compromisedCount },
    { label: "Active alerts",      value: incidentCount },
    { label: "Threat intelligence",value: learnedType },
  ], [compromisedCount, incidentCount, learnedType]);

  return (
    <div className="app-root">
      <ConsoleSidebar connected={connected} />
      <main className="console-main">
        <TopBar state={currentState} step={step} />

        <div className="summary-strip">
          {summary.map((item) => (
            <div key={item.label}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </div>
          ))}
        </div>

        <div className="ops-grid">
          <IncidentQueue state={currentState} selectedHost={selectedHost} onSelectHost={setSelectedHost} step={step} />
          <section className="panel map-panel">
            <div className="section-head">
              <div>
                <span>Network topology</span>
                <strong>{selectedHost}</strong>
              </div>
              <span className="map-phase">{stepToTimestamp(step)}</span>
            </div>
            <NetworkGraph state={currentState} meta={meta} />
          </section>
          <ResponseApproval state={currentState} selectedHost={selectedHost} />
          <AssetTable state={currentState} selectedHost={selectedHost} onSelectHost={setSelectedHost} />
          <EvidenceTabs state={currentState} meta={meta} step={step} setStep={setStep} />
        </div>

        <div className="status-bar">
          <span className={connected ? "live-pill live" : "live-pill replay"}>
            <span className="live-dot" />
            {connected ? "Live" : "Replaying session"}
          </span>
          <span className="sb-sep" />
          <span className="sb-item">{stepToTimestamp(step)}</span>
          <span className="sb-sep" />
          <span className="sb-item">{step + 1} of {Math.max(totalSteps, 1)} events</span>
          <span className="sb-sep" />
          <span className="sb-item">{totalSteps > 0 ? `${HOSTS.length} hosts monitored` : "Connecting…"}</span>
        </div>
      </main>
    </div>
  );
}
