/**
 * App.jsx — SOMA Cyber Immune Dashboard
 *
 * Layout (3 columns, 2 rows):
 *
 *   ┌─────────────────────────────────────────────────────┐
 *   │  HEADER: title | step scrubber | play controls      │
 *   ├──────────────┬──────────────────────┬───────────────┤
 *   │ LayerRadar   │  NetworkGraph        │ EvasionPanel  │
 *   │ (radar)      │  (D3 CAGE2 topo)     │ (bar chart)   │
 *   ├──────────────┴──────────────────────┴───────────────┤
 *   │  TimelinePanel  (full width — threat per host)      │
 *   ├──────────────┬──────────────────────────────────────┤
 *   │ GalleryPanel │  IncidentPanel                       │
 *   │ (VAE scatter)│  (current step incidents)            │
 *   └──────────────┴──────────────────────────────────────┘
 */

import React from "react";
import NetworkGraph    from "./components/NetworkGraph";
import TimelinePanel   from "./components/TimelinePanel";
import LayerRadarPanel from "./components/LayerRadarPanel";
import EvasionPanel    from "./components/EvasionPanel";
import GalleryPanel    from "./components/GalleryPanel";
import IncidentPanel   from "./components/IncidentPanel";
import useWebSocket    from "./hooks/useWebSocket";
import "./styles/index.css";

export default function App() {
  const {
    state, meta, step, totalSteps, connected,
    playing, play, pause, stepForward, stepBack, setStep,
  } = useWebSocket("ws://localhost:8765");

  const phase    = state?.phase ?? "—";
  const isAttack = state?.is_attack ?? false;

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

        {/* Phase badge */}
        <span className={`phase-badge ${isAttack ? "phase-attack" : "phase-clean"}`}>
          {phase}
        </span>

        <span className={`connection-status ${connected ? "connected" : "disconnected"}`}>
          {connected ? "● LIVE" : "● STATIC"}
        </span>
      </header>

      {/* ── Main Grid ────────────────────────────────────────── */}
      <main className="app-grid">

        {/* Row 1 */}
        <div className="panel panel--radar">
          <LayerRadarPanel state={state} meta={meta} />
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
          <IncidentPanel state={state} step={step} />
        </div>

      </main>
    </div>
  );
}
