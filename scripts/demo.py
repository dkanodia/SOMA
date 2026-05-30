"""
scripts/demo.py
================
WebSocket demo server — streams live SOMA episode state to the React frontend.

Serves on ws://localhost:8765
Frontend connects at http://localhost:3000

Fallback: if WebSocket is unstable on the demo machine, run
  python scripts/demo.py --static
which exports a pre-recorded episode as JSON for the frontend to replay.
The static fallback should always be prepared before the pitch.

Architecture
------------
  CybORGWrapper episode → Layer 1 scores → Layer 2 PPO actions
  → Layer 3 heuristic trigger (NOT game-theoretic policy)
  → Layer 4 drift detection
  → JSON payload → WebSocket → React frontend
"""

import asyncio
import json
import argparse
import numpy as np
from pathlib import Path


async def run_episode(websocket):
    """Stream one CAGE 2 episode to connected frontend client."""
    # TODO: load trained models
    # from soma.layers.innate   import InnateIsolationForest
    # from soma.layers.adaptive import load as load_ppo
    # from soma.layers.deception import heuristic_honeypot_trigger
    # from soma.layers.suppressor import LongDwellDetector
    # from soma.envs.cyborg_wrapper import CybORGWrapper, HOST_NAMES

    # innate    = InnateIsolationForest.load(Path("models/innate/isolation_forest.joblib"))
    # ppo       = load_ppo("models/adaptive/soma_ppo_final")
    # detector  = LongDwellDetector.load(Path("models/innate/drift_detector.joblib"))
    # env       = CybORGWrapper()
    # obs, _    = env.reset()

    for step in range(200):
        # action, _   = ppo.predict(obs)
        # obs, _, done, _, info = env.step(action)

        # anomaly_scores = {h: innate.anomaly_score(obs_per_host[h]) for h in HOST_NAMES}
        # honeypot_flags = {h: heuristic_honeypot_trigger(anomaly_scores[h]) for h in HOST_NAMES}
        # detector.update_all(obs_per_host)
        # drift_alarms   = {h: detector.drift_alarm(h) for h in HOST_NAMES}

        payload = {
            "step":            step,
            "anomaly_scores":  {},   # TODO
            "honeypot_flags":  {},   # TODO — heuristic, labeled in payload
            "drift_alarms":    {},   # TODO
            "honeypot_note":   "heuristic trigger — not signaling game policy",
        }
        await websocket.send(json.dumps(payload))
        await asyncio.sleep(0.1)


async def main_server():
    import websockets
    print("SOMA demo server running on ws://localhost:8765")
    print("Open frontend: cd frontend && npm install && npm start")
    async with websockets.serve(run_episode, "localhost", 8765):
        await asyncio.Future()


def export_static(output_path: Path = Path("results/demo_episode.json")):
    """Pre-record one episode as JSON for static fallback."""
    # TODO: run episode, collect payloads, write to JSON
    raise NotImplementedError("Static export not yet implemented")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--static", action="store_true",
                        help="Export pre-recorded episode JSON instead of live server")
    args = parser.parse_args()

    if args.static:
        export_static()
    else:
        asyncio.run(main_server())
