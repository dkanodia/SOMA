/**
 * App.jsx — Root layout for SOMA demo UI
 *
 * Four panels arranged around a central network graph:
 *   Top-left:    AnomalyPanel    (Layer 1 reconstruction error time series)
 *   Top-right:   ConvergencePanel (Layer 3 RL vs PBE — HERO VISUAL, largest panel)
 *   Bottom-left: LearningPanel   (Layer 2 PPO reward curve)
 *   Bottom-right: DriftPanel     (Layer 4 centroid trajectory scatter)
 *   Center:      NetworkGraph    (D3 force-directed, live episode state)
 *
 * WebSocket connects to ws://localhost:8765 (scripts/demo.py).
 * Falls back to static JSON replay if socket unavailable.
 *
 * Color system (CSS vars defined in styles/index.css):
 *   --healthy:    #22d3ee  (cyan)
 *   --compromised:#ef4444  (red)
 *   --honeypot:   #f59e0b  (amber  — heuristic trigger, labeled)
 *   --pbe-line:   #a855f7  (purple — PBE equilibrium benchmark)
 *   --rl-line:    #22d3ee  (cyan   — learned RL policy)
 */

import React, { useState } from "react";
import NetworkGraph     from "./components/NetworkGraph";
import AnomalyPanel     from "./components/AnomalyPanel";
import ConvergencePanel from "./components/ConvergencePanel";
import LearningPanel    from "./components/LearningPanel";
import DriftPanel       from "./components/DriftPanel";
import useWebSocket     from "./hooks/useWebSocket";
import "./styles/index.css";

export default function App() {
  const { state, connected } = useWebSocket("ws://localhost:8765");

  return (
    <div className="app-root">
      <header className="app-header">
        <span className="app-title">SOMA</span>
        <span className="app-subtitle">Signaling-Optimal Memory Architecture</span>
        <span className={`connection-status ${connected ? "connected" : "disconnected"}`}>
          {connected ? "● LIVE" : "● STATIC"}
        </span>
      </header>

      <main className="app-grid">
        {/* Hero visual — largest panel */}
        <div className="panel panel--hero">
          <ConvergencePanel data={state?.convergence} />
        </div>

        <div className="panel panel--network">
          <NetworkGraph hosts={state?.hosts} />
        </div>

        <div className="panel panel--anomaly">
          <AnomalyPanel scores={state?.anomaly_scores} />
        </div>

        <div className="panel panel--learning">
          <LearningPanel rewardHistory={state?.reward_history} />
        </div>

        <div className="panel panel--drift">
          <DriftPanel trajectories={state?.centroid_trajectories} />
        </div>
      </main>
    </div>
  );
}
