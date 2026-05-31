import React, { useState, useMemo } from "react";
import NetworkGraph       from "./components/NetworkGraph";
import TimelinePanel      from "./components/TimelinePanel";
import LayerRadarPanel    from "./components/LayerRadarPanel";
import EvasionPanel       from "./components/EvasionPanel";
import GalleryPanel       from "./components/GalleryPanel";
import IncidentPanel      from "./components/IncidentPanel";
import DefenseActionPanel from "./components/DefenseActionPanel";
import DriftPanel         from "./components/DriftPanel";
import HoneypotPanel      from "./components/HoneypotPanel";
import useWebSocket       from "./hooks/useWebSocket";
import "./styles/index.css";

const TABS = ["incidents", "defense", "drift", "honeypot"];
const TAB_LABELS = { incidents: "Incidents", defense: "Defense", drift: "Drift", honeypot: "Honeypot" };

const LAYERS = ["innate", "memory", "tolerance", "learned", "orchestrator"];

const NAV_SECTIONS = [
  { label: "Analysis", items: [
    { id: "network",   name: "Network Graph" },
    { id: "radar",     name: "Layer Radar" },
    { id: "timeline",  name: "Timeline" },
  ]},
  { label: "Detection", items: [
    { id: "incidents", name: "Incidents" },
    { id: "drift",     name: "Drift Monitor" },
    { id: "evasion",   name: "Evasion Matrix" },
  ]},
  { label: "Response", items: [
    { id: "defense",   name: "Defense Actions" },
    { id: "honeypot",  name: "Honeypot" },
    { id: "gallery",   name: "VAE Scatter" },
  ]},
];

export default function App() {
  const {
    state, meta, step, totalSteps, connected,
    playing, play, pause, stepForward, stepBack, setStep,
  } = useWebSocket(process.env.REACT_APP_WS_URL || "ws://localhost:8765");

  const [activeTab, setActiveTab]     = useState("incidents");
  const [layerVisible, setLayerVisible] = useState(
    Object.fromEntries(LAYERS.map((l) => [l, true]))
  );

  const toggleLayer = (key) =>
    setLayerVisible((prev) => ({ ...prev, [key]: !prev[key] }));

  const phase    = state?.phase ?? "—";
  const isAttack = state?.is_attack ?? false;

  const stats = useMemo(() => {
    const slice = (meta?._steps ?? []).slice(0, step + 1);
    return {
      detected:    slice.filter((s) => s.innate_fired).length,
      honeypot:    slice.filter((s) => Object.values(s.honeypot_flags ?? {}).some(Boolean)).length,
      driftAlarms: slice.filter((s) => Object.values(s.drift_alarms ?? {}).some(Boolean)).length,
    };
  }, [meta, step]);

  return (
    <div className="app-root">

      {/* ── Sidebar ────────────────────────────────────────────── */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <span className="sidebar-wordmark">SO<span>MA</span></span>
          <span className="sidebar-tagline">Cyber Immune Stack</span>
        </div>

        <nav className="sidebar-nav">
          {NAV_SECTIONS.map((sec) => (
            <div key={sec.label}>
              <div className="nav-section-label">{sec.label}</div>
              {sec.items.map((item) => (
                <div
                  key={item.id}
                  className={`nav-item ${activeTab === item.id ? "active" : ""}`}
                  onClick={() => {
                    if (TABS.includes(item.id)) setActiveTab(item.id);
                  }}
                >
                  <span className="nav-dot" />
                  {item.name}
                </div>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-status">
          <div className="status-row">
            <span className="status-label">Status</span>
            <span className={`status-badge ${connected ? "live" : "static"}`}>
              {connected ? "LIVE" : "STATIC"}
            </span>
          </div>
          <div className="status-row">
            <span className="status-label">Step</span>
            <span className="status-val">{step} / {Math.max(totalSteps - 1, 0)}</span>
          </div>
          <div className="status-row">
            <span className="status-label">Phase</span>
            <span className={`status-badge ${isAttack ? "live" : ""}`}
              style={isAttack ? { background: "var(--alert-dim)", color: "var(--alert)" } : {}}>
              {phase}
            </span>
          </div>
          <div className="status-row" style={{ marginTop: 6 }}>
            <span className="status-label">Innate</span>
            <span className="status-val" style={{ color: stats.detected > 0 ? "var(--gold)" : "var(--fg-3)" }}>
              {stats.detected}
            </span>
          </div>
          <div className="status-row">
            <span className="status-label">Decoy</span>
            <span className="status-val" style={{ color: stats.honeypot > 0 ? "var(--warn)" : "var(--fg-3)" }}>
              {stats.honeypot}
            </span>
          </div>
          <div className="status-row">
            <span className="status-label">Drift</span>
            <span className="status-val" style={{ color: stats.driftAlarms > 0 ? "var(--mem)" : "var(--fg-3)" }}>
              {stats.driftAlarms}
            </span>
          </div>
          <div className="sidebar-version">v0.4 — CybORG CAGE 2</div>
        </div>
      </aside>

      {/* ── Main area ──────────────────────────────────────────── */}
      <div className="app-main">

        {/* Header */}
        <header className="app-header">
          <span className="header-breadcrumb">
            <strong>Autonomous Defense</strong> / Live Episode
          </span>
          <div className="header-sep" />

          {/* Playback controls */}
          <div className="controls">
            <button className="ctrl-btn" onClick={stepBack}   title="Step back">◀</button>
            <button className="ctrl-btn" onClick={playing ? pause : play} title={playing ? "Pause" : "Play"}>
              {playing ? "⏸" : "▶"}
            </button>
            <button className="ctrl-btn" onClick={stepForward} title="Step forward">▶▶</button>
            <input
              type="range"
              className="scrubber"
              min={0}
              max={Math.max(totalSteps - 1, 0)}
              value={step}
              onChange={(e) => setStep(parseInt(e.target.value))}
            />
            <span className="step-counter">
              {step} / {Math.max(totalSteps - 1, 0)}
            </span>
          </div>

          <div className="header-sep" />

          {/* Layer toggles */}
          <div className="layer-toggles">
            {LAYERS.map((l) => (
              <button
                key={l}
                className={`ctrl-btn layer-toggle ${layerVisible[l] ? "active" : "dim"}`}
                onClick={() => toggleLayer(l)}
                title={`Toggle ${l} layer`}
              >
                {l}
              </button>
            ))}
          </div>

          <span className={`connection-status ${connected ? "connected" : "disconnected"}`}>
            {connected ? "● LIVE" : "● OFFLINE"}
          </span>
        </header>

        {/* Grid */}
        <main className="app-grid">

          {/* Row 1 */}
          <div className="panel panel--radar">
            <LayerRadarPanel state={state} meta={meta} layerVisible={layerVisible} />
          </div>

          <div className="panel panel--network">
            <NetworkGraph state={state} meta={meta} />
          </div>

          <div className="panel panel--evasion">
            <EvasionPanel meta={meta} />
          </div>

          {/* Row 2 — full-width timeline */}
          <div className="panel panel--timeline">
            <TimelinePanel
              state={state}
              meta={meta}
              currentStep={step}
              onStepClick={setStep}
            />
          </div>

          {/* Row 3 */}
          <div className="panel panel--gallery">
            <GalleryPanel state={state} meta={meta} />
          </div>

          <div className="panel panel--incident">
            <div className="panel-inner">
              <div className="panel-tabs">
                {TABS.map((t) => (
                  <button
                    key={t}
                    className={`tab-btn ${activeTab === t ? "active" : ""}`}
                    onClick={() => setActiveTab(t)}
                  >
                    {TAB_LABELS[t]}
                  </button>
                ))}
              </div>
              <div className="tab-content">
                {activeTab === "incidents" && <IncidentPanel state={state} step={step} />}
                {activeTab === "defense"   && (
                  <DefenseActionPanel state={state} meta={meta} step={step} layerVisible={layerVisible} />
                )}
                {activeTab === "drift"     && <DriftPanel state={state} />}
                {activeTab === "honeypot"  && <HoneypotPanel state={state} />}
              </div>
            </div>
          </div>

        </main>
      </div>
    </div>
  );
}
