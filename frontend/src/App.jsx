import React, { useMemo, useState } from "react";
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

function formatPhase(phase) {
  return (phase || "clean").replaceAll("_", " ");
}

function ConsoleSidebar({ connected }) {
  return (
    <aside className="console-sidebar">
      <div className="console-brand">
        <strong>SO<span>MA</span></strong>
        <small>Defense Console</small>
      </div>
      <nav className="console-nav" aria-label="Primary">
        <button className="active">Operations</button>
        <button>Incidents</button>
        <button>Assets</button>
        <button>Policies</button>
        <button>Audit Log</button>
      </nav>
      <div className="connection-card">
        <span className={connected ? "status-dot live" : "status-dot"} />
        <div>
          <strong>{connected ? "Live stream" : "Replay mode"}</strong>
          <span>{connected ? "WebSocket connected" : "Using demo episode"}</span>
        </div>
      </div>
    </aside>
  );
}

function TopBar({ state, step, totalSteps, playing, play, pause, stepBack, stepForward, setStep }) {
  const severity = getSeverity(state);
  const topHost = state?.top_threat?.host ?? "None";
  const action = actionLabel(state?.orchestrator?.action_name);

  return (
    <header className="topbar">
      <div>
        <p>Operations</p>
        <h1>Threat Response Center</h1>
      </div>
      <div className="topbar-metrics">
        <div className={`metric ${severity.className}`}>
          <span>Posture</span>
          <strong>{severity.label}</strong>
        </div>
        <div className="metric">
          <span>Top host</span>
          <strong>{topHost}</strong>
        </div>
        <div className="metric action">
          <span>Recommended</span>
          <strong>{action}</strong>
        </div>
      </div>
      <div className="replay-controls">
        <button onClick={stepBack} title="Previous step">◀</button>
        <button className="play" onClick={playing ? pause : play}>
          {playing ? "Pause" : "Play"}
        </button>
        <button onClick={stepForward} title="Next step">▶</button>
        <input
          type="range"
          min={0}
          max={Math.max(totalSteps - 1, 0)}
          value={step}
          onChange={(e) => setStep(parseInt(e.target.value, 10))}
        />
        <span>{step}/{Math.max(totalSteps - 1, 0)}</span>
      </div>
    </header>
  );
}

function IncidentQueue({ state, onSelectHost, selectedHost }) {
  const incidents = state?.incidents ?? [];
  const rows = incidents.length
    ? incidents
    : HOSTS.map((host) => ({
        host,
        confidence: "CLEAR",
        score: 0,
        attack_type: "normal",
        explanation: "No active incident on this host",
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
            <span className="host-name">{inc.host}</span>
            <span className="queue-desc">{inc.attack_type?.replaceAll("_", " ")}</span>
            <span className="queue-score">{inc.confidence} {inc.score ? inc.score.toFixed(2) : ""}</span>
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
        <span className={`approval-badge ${isRemove ? "danger" : "safe"}`}>
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
          ["timeline", "Timeline"],
          ["incidents", "Incidents"],
          ["actions", "Actions"],
          ["drift", "Drift"],
          ["decoys", "Decoys"],
          ["layers", "Layers"],
          ["evasion", "Evasion"],
        ].map(([id, label]) => (
          <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </div>
      <div className="evidence-body">
        {tab === "timeline" && <TimelinePanel state={state} meta={meta} currentStep={step} onStepClick={setStep} />}
        {tab === "incidents" && <IncidentPanel state={state} step={step} />}
        {tab === "actions" && <DefenseActionPanel state={state} meta={meta} step={step} />}
        {tab === "drift" && <DriftPanel state={state} />}
        {tab === "decoys" && <HoneypotPanel state={state} />}
        {tab === "layers" && <LayerRadarPanel state={state} meta={meta} layerVisible={{}} />}
        {tab === "evasion" && <EvasionPanel meta={meta} />}
      </div>
    </section>
  );
}

export default function App() {
  const {
    state, meta, step, totalSteps, connected,
    playing, play, pause, stepForward, stepBack, setStep,
  } = useWebSocket(process.env.REACT_APP_WS_URL || "ws://localhost:8765");

  const currentState = state ?? {};
  const [selectedHost, setSelectedHost] = useState("Op_Server0");

  const currentPhase = formatPhase(currentState.phase);
  const infectedCount = currentState.compromised_hosts?.length ?? 0;
  const incidentCount = currentState.incidents?.length ?? 0;
  const learnedType = currentState.learned_attack_type && currentState.learned_attack_type !== "unknown"
    ? currentState.learned_attack_type.replaceAll("_", " ")
    : "Unclassified";

  const summary = useMemo(() => [
    { label: "Phase", value: currentPhase },
    { label: "Infected", value: infectedCount },
    { label: "Open incidents", value: incidentCount },
    { label: "Signature", value: learnedType },
  ], [currentPhase, infectedCount, incidentCount, learnedType]);

  return (
    <div className="app-root">
      <ConsoleSidebar connected={connected} />
      <main className="console-main">
        <TopBar
          state={currentState}
          step={step}
          totalSteps={totalSteps}
          playing={playing}
          play={play}
          pause={pause}
          stepBack={stepBack}
          stepForward={stepForward}
          setStep={setStep}
        />

        <div className="summary-strip">
          {summary.map((item) => (
            <div key={item.label}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </div>
          ))}
        </div>

        <div className="ops-grid">
          <IncidentQueue state={currentState} selectedHost={selectedHost} onSelectHost={setSelectedHost} />
          <section className="panel map-panel">
            <div className="section-head">
              <div>
                <span>Network map</span>
                <strong>{selectedHost}</strong>
              </div>
              <span className="map-phase">{currentPhase}</span>
            </div>
            <NetworkGraph state={currentState} meta={meta} />
          </section>
          <ResponseApproval state={currentState} selectedHost={selectedHost} />
          <AssetTable state={currentState} selectedHost={selectedHost} onSelectHost={setSelectedHost} />
          <EvidenceTabs state={currentState} meta={meta} step={step} setStep={setStep} />
        </div>
      </main>
    </div>
  );
}
