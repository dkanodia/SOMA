/**
 * TimelinePanel.jsx
 *
 * Full-width threat timeline: anomaly score + memory drift per host over time.
 * Recharts ComposedChart with:
 *   - Gray reference area marking the attack window
 *   - Global innate anomaly score (cyan line)
 *   - Memory drift for each host (one line each, dimmed)
 *   - Red reference line for innate threshold
 *   - Click on chart → jump to that step
 */

import React, { useMemo } from "react";
import {
  ComposedChart, Line, Area, ReferenceLine, ReferenceArea,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from "recharts";

const HOST_COLORS = {
  User0:       "#3A7A58",
  User1:       "#5F8D6F",
  User2:       "#8BA778",
  Enterprise0: "#6452A0",
  Enterprise1: "#8071B8",
  Op_Server0:  "#A83D2E",
};

const FEATURE_NAMES = ["activity","compromised","sessions","processes","network_pos"];

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: "#171715", border: "1px solid #262624",
      padding: "6px 10px", fontSize: 10, lineHeight: 1.6,
    }}>
      <div style={{ color: "#807C76" }}>Step {label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} style={{ color: p.color }}>
          {p.name}: {typeof p.value === "number" ? p.value.toFixed(3) : p.value}
        </div>
      ))}
    </div>
  );
}

export default function TimelinePanel({ state, meta, currentStep, onStepClick }) {
  // Build timeline data from ALL steps stored in meta (we don't have all steps here).
  // Instead we use a sliding window approach: the component shows a "ghost" line
  // from the current step's obs only.
  //
  // For full timeline we need the parent to pass all steps, but to keep the API simple
  // we accept meta.steps if present (injected by App from the full episode).
  // Fallback: show just current step as a single point.

  const allSteps = meta?._steps ?? [];   // injected by App.jsx if available

  const chartData = useMemo(() => {
    if (!allSteps.length) {
      if (!state) return [];
      return [{
        step: state.step,
        anomaly: state.anomaly_score,
        ...Object.fromEntries(
          Object.entries(state.drift_scores ?? {}).map(([h, v]) => [`drift_${h}`, v])
        ),
      }];
    }
    return allSteps.map((s) => ({
      step:   s.step,
      anomaly: s.anomaly_score ?? 0,
      is_attack: s.is_attack ? 1 : 0,
      ...Object.fromEntries(
        Object.entries(s.drift_scores ?? {}).map(([h, v]) => [`drift_${h}`, v])
      ),
    }));
  }, [allSteps, state]);

  const attackStart = meta?.attack_start ?? null;
  const totalSteps  = meta?.episode_length ?? chartData.length;
  const innateThresh = meta?.innate_threshold ?? 0.5;
  const memThresh    = meta?.memory_threshold  ?? 1.0;

  const hostNames = meta?.host_names ?? Object.keys(HOST_COLORS);

  function handleClick(data) {
    if (data?.activePayload?.[0] && onStepClick) {
      onStepClick(data.activeLabel);
    }
  }

  return (
    <div className="panel-inner">
      <div className="panel-title">Threat Timeline — Anomaly &amp; Drift per Host</div>
      <div className="panel-content">
        {chartData.length === 0 ? (
          <p className="panel-placeholder">Waiting for episode data…</p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 4, right: 10, bottom: 4, left: 0 }}
              onClick={handleClick}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1A1A18" />
              <XAxis dataKey="step" stroke="#262624" tick={{ fill: "#807C76", fontSize: 9 }}
                label={{ value: "Step", position: "insideBottomRight", offset: -5, fill: "#807C76", fontSize: 9 }} />
              <YAxis stroke="#262624" tick={{ fill: "#807C76", fontSize: 9 }} width={32} />
              <Tooltip content={<CustomTooltip />} />

              {/* Attack window */}
              {attackStart != null && (
                <ReferenceArea
                  x1={attackStart} x2={totalSteps - 1}
                  fill="#A83D2E" fillOpacity={0.06}
                  label={{ value: "attack", position: "insideTopRight", fill: "#A83D2E", fontSize: 8 }}
                />
              )}

              {/* Current step marker */}
              {currentStep != null && (
                <ReferenceLine x={currentStep} stroke="#C49A30" strokeDasharray="4 2" strokeWidth={1.5} />
              )}

              {/* Innate threshold */}
              <ReferenceLine y={innateThresh} stroke="#C49A30" strokeDasharray="4 2"
                label={{ value: "theta inn", position: "right", fill: "#C49A30", fontSize: 8 }} />

              {/* Memory threshold */}
              <ReferenceLine y={memThresh} stroke="#6452A0" strokeDasharray="4 2"
                label={{ value: "theta mem", position: "right", fill: "#6452A0", fontSize: 8 }} />

              {/* Global innate anomaly score */}
              <Line type="monotone" dataKey="anomaly" name="Innate"
                stroke="#C49A30" strokeWidth={1.8} dot={false} />

              {/* Per-host drift scores */}
              {hostNames.map((h) => (
                <Line key={h}
                  type="monotone"
                  dataKey={`drift_${h}`}
                  name={`Drift:${h}`}
                  stroke={HOST_COLORS[h] ?? "#807C76"}
                  strokeWidth={1}
                  strokeOpacity={0.55}
                  dot={false}
                />
              ))}
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
