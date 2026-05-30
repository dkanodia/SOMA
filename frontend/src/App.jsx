/**
 * App.jsx — SOMA Cyber Immune Dashboard
 *
 * Layout (3 columns, 3 rows):
 *
 *   ┌─────────────────────────────────────────────────────┐
 *   │  HEADER: title | controls | stats bar | toggles     │
 *   ├──────────────┬──────────────────────┬───────────────┤
 *   │ LayerRadar   │  NetworkGraph        │ EvasionPanel  │
 *   ├──────────────┴──────────────────────┴───────────────┤
 *   │  TimelinePanel  (full width)                        │
 *   ├──────────────┬──────────────────────────────────────┤
 *   │ GalleryPanel │  Tab switcher                        │
 *   │ (VAE scatter)│  Incidents | Defense | Drift | Honeypot │
 *   └──────────────┴──────────────────────────────────────┘
 */

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

export default function App() {
  const {
    state, meta, step, totalSteps, connected,
    playing, play, pause, stepForward, stepBack, setStep,
  } = useWebSocket("ws://localhost:8765");

  const [activeTab, setActiveTab]     = useState("incidents");
  const [layerVisible, setLayerVisible] = useState(
    Object.fromEntries(LAYERS.map((l) => [l, true]))
  );

  const toggleLayer = (key) =>
    setLayerVisible((prev) => ({ ...prev, [key]: !prev[key] }));

  const phase    = state?.phase ?? "—";
  const isAttack = state?.is_attack ?? false;

  // Cumulative stats up to current step
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
      {/* ── Header ───────────────────────────────────────────── */}
      <header className="app-header">
        <span className="app-title">SOMA</span>
        <span className="app-subtitle">Cyber Immune Stack</span>

        {/* Step scrubber */}
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
            Step {step}/{Math.max(totalSteps - 1, 0)}
          </span>
        </div>

        {/* Summary stats */}
        <div className="stats-bar">
          <span className="stat-pill">innate {stats.detected}</span>
          <span className="stat-pill" style={{ color: "#f59e0b" }}>decoy {stats.honeypot}</span>
          <span className="stat-pill" style={{ color: "#a855f7" }}>drift {stats.driftAlarms}</span>
        </div>

        {/* Phase badge */}
        <span className={`phase-badge ${isAttack ? "phase-attack" : "phase-clean"}`}>
          {phase}
        </span>

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
          {connected ? "● LIVE" : "● STATIC"}
        </span>
      </header>

      {/* ── Main Grid ────────────────────────────────────────── */}
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
            {/* Tab bar */}
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
            {/* Tab content */}
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
  );
}
