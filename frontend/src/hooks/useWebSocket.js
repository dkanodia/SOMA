/**
 * hooks/useWebSocket.js
 *
 * Live demo WebSocket hook — connects to ws://localhost:8765/dashboard
 * and routes the SOMA live-demo message protocol.
 *
 * State exposed:
 *   connected          bool
 *   somaState          "CLEAN"|"EMAIL_RECEIVED"|"INFECTED"|"ISOLATING"|"CONTAINED"|"PURGED"
 *   emailNotification  null | {from, subject}
 *   nodes              array of 6 {id, cpu, processes, anomaly_score, status}
 *   honeypotMetrics    null | {cpu, processes, exfil_attempts, lan_scans}
 *   sendMessage        (obj) => void
 */
import { useState, useEffect, useRef, useCallback } from "react";

const RECONNECT_DELAY_MS = 3000;

export default function useWebSocket(url) {
  const [connected,          setConnected]          = useState(false);
  const [somaState,          setSomaState]          = useState("CLEAN");
  const [emailNotification,  setEmailNotification]  = useState(null);
  const [nodes,              setNodes]              = useState([]);
  const [honeypotMetrics,    setHoneypotMetrics]    = useState(null);

  const wsRef        = useRef(null);
  const reconnectRef = useRef(null);
  const mountedRef   = useRef(true);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    // Connect to the /dashboard path
    const wsUrl = url.replace(/\/?$/, "") + "/dashboard";
    let ws;
    try {
      ws = new WebSocket(wsUrl);
    } catch {
      return;
    }
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) { ws.close(); return; }
      console.log("[SOMA] Dashboard connected");
      setConnected(true);
    };

    ws.onmessage = (e) => {
      let msg;
      try { msg = JSON.parse(e.data); } catch { return; }

      switch (msg.type) {
        case "email_notification":
          setEmailNotification({ from: msg.from, subject: msg.subject });
          break;
        case "node_metrics":
          setNodes(msg.nodes ?? []);
          break;
        case "state_change":
          setSomaState(msg.state);
          break;
        case "honeypot_active":
          setHoneypotMetrics(msg.metrics ?? null);
          break;
        case "purge_complete":
          setHoneypotMetrics(null);
          setSomaState("PURGED");
          break;
        default:
          break;
      }
    };

    ws.onclose = () => {
      setConnected(false);
      if (mountedRef.current) {
        reconnectRef.current = setTimeout(connect, RECONNECT_DELAY_MS);
      }
    };

    ws.onerror = () => {
      setConnected(false);
    };
  }, [url]);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const sendMessage = useCallback((obj) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(obj));
    }
  }, []);

  return {
    connected,
    somaState,
    emailNotification,
    nodes,
    honeypotMetrics,
    sendMessage,
  };
}
