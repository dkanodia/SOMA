/**
 * hooks/useWebSocket.js
 *
 * Loads static demo data immediately so the UI is never blank, then attempts
 * a live WebSocket connection in the background.
 *
 * If the WS connects (within WS_TIMEOUT_MS): switches to live mode.
 * If not: stays in static replay mode and schedules one silent retry after
 * COLD_RETRY_MS — enough time for a Render free-tier cold start (~30-60 s).
 */
import { useState, useEffect, useRef, useCallback } from "react";

const STEP_INTERVAL_MS = 800;   // static auto-advance rate
const WS_TIMEOUT_MS    = 30000; // wait up to 30 s for WS (Render cold start)
const COLD_RETRY_MS    = 35000; // silent retry 35 s after timeout fires

export default function useWebSocket(url) {
  const [steps,        setSteps]       = useState([]);
  const [meta,         setMeta]        = useState(null);
  const [step,         setStepIdx]     = useState(0);
  const [connected,    setConnected]   = useState(false);
  const [warming,      setWarming]     = useState(true);
  const [reconnectKey, setReconnectKey] = useState(0);

  const wsRef           = useRef(null);
  const timerRef        = useRef(null);
  const stepsRef        = useRef([]);
  const pausedRef       = useRef(false);
  const retryRef        = useRef(0);
  const retriedColdRef  = useRef(false); // only one cold-start retry per mount

  useEffect(() => { stepsRef.current = steps; }, [steps]);

  // ------------------------------------------------------------------
  // Static data — loaded immediately so the UI always has content
  // ------------------------------------------------------------------
  const loadStatic = useCallback(() => {
    fetch("/demo_episode.json")
      .then((r) => r.json())
      .then((data) => {
        setMeta(data.meta);
        setSteps(data.steps || []);
        setStepIdx(0);
        pausedRef.current = false;
      })
      .catch((e) => console.warn("[SOMA] Could not load demo_episode.json:", e));
  }, []);

  // ------------------------------------------------------------------
  // WebSocket — background connection attempt alongside static data
  // ------------------------------------------------------------------
  useEffect(() => {
    let wsConnected = false;
    let wsTimer;
    let coldRetryTimer;

    // Always load static first — user sees content immediately
    loadStatic();

    // Only show the "warming" indicator on the initial connection attempt
    setWarming(reconnectKey === 0);

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        wsConnected = true;
        retryRef.current = 0;
        setConnected(true);
        setWarming(false);
        clearTimeout(wsTimer);
      };

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          if (msg.steps) {
            setMeta(msg.meta); setSteps(msg.steps);
          } else if (msg.step !== undefined && !msg.error) {
            if (msg.meta) setMeta(msg.meta);
            setSteps((prev) => { const n = [...prev]; n[msg.step] = msg; return n; });
            setStepIdx(msg.step);
          } else if (msg.meta) {
            setMeta(msg.meta);
          }
        } catch (err) {
          console.warn("[SOMA] WebSocket message parse error:", err);
        }
      };

      ws.onclose = () => {
        setConnected(false);
        if (wsConnected && retryRef.current < 3) {
          retryRef.current++;
          setTimeout(() => setReconnectKey((k) => k + 1), 2000);
        }
      };
      ws.onerror = () => { setConnected(false); };

      // Give WS 30 s to connect; if not, close it and schedule one cold retry
      wsTimer = setTimeout(() => {
        if (!wsConnected) {
          ws.close();
          setWarming(false);
          if (!retriedColdRef.current) {
            retriedColdRef.current = true;
            coldRetryTimer = setTimeout(
              () => setReconnectKey((k) => k + 1),
              COLD_RETRY_MS,
            );
          }
        }
      }, WS_TIMEOUT_MS);
    } catch {
      setWarming(false);
    }

    return () => {
      clearTimeout(wsTimer);
      clearTimeout(coldRetryTimer);
      wsRef.current?.close();
    };
  }, [url, loadStatic, reconnectKey]);

  // ------------------------------------------------------------------
  // Auto-advance (static replay only — live WS drives step via onmessage)
  // ------------------------------------------------------------------
  useEffect(() => {
    if (connected) return;
    if (stepsRef.current.length === 0) return;

    timerRef.current = setInterval(() => {
      if (pausedRef.current) return;
      setStepIdx((prev) => {
        if (prev + 1 >= stepsRef.current.length) return 0;
        return prev + 1;
      });
    }, STEP_INTERVAL_MS);

    return () => clearInterval(timerRef.current);
  }, [connected, steps.length]);

  // ------------------------------------------------------------------
  // Timeline click — jump to step, resume after 3 s
  // ------------------------------------------------------------------
  const resumeTimer = useRef(null);
  const setStep = useCallback((n) => {
    pausedRef.current = true;
    setStepIdx(Math.max(0, Math.min(n, stepsRef.current.length - 1)));
    clearTimeout(resumeTimer.current);
    resumeTimer.current = setTimeout(() => { pausedRef.current = false; }, 3000);
  }, []);

  const state = steps[step] ?? null;
  const metaWithSteps = meta ? { ...meta, _steps: steps } : null;

  return { state, meta: metaWithSteps, step, totalSteps: steps.length, connected, warming, setStep };
}
