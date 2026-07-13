import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { Counter, Headline, Kicker, PipeNode, ShotCard, Sub, Terminal } from "./components";
import { T } from "./theme";

/* 1 — hook */
export const S1: React.FC = () => (
  <>
    <Kicker>MIA EVAL · Voice-agent evaluation</Kicker>
    <Headline size={116}>
      200 real calls.
      <br />
      Zero guesswork.
    </Headline>
    <Sub delay={14}>An evaluation you can re-run, drill into, and defend.</Sub>
    <div style={{ flex: 1 }} />
    <ShotCard shot="shots/kpis.png" delay={20} height={330} zoomFrom={1.0} zoomTo={1.03} />
  </>
);

/* 2 — ground truth */
export const S2: React.FC = () => (
  <>
    <Kicker>Step 1 · Ground truth</Kicker>
    <Headline>18 hand-labeled calls, one frozen rubric</Headline>
    <div style={{ flex: 1 }} />
    <ShotCard shot="shots/rubric.png" delay={12} height={620} zoomTo={1.05} />
  </>
);

/* 3 — pipeline diagram */
export const S3: React.FC = () => (
  <>
    <Kicker>Step 2 · The pipeline</Kicker>
    <Headline>Observation and judgment, separated</Headline>
    <div style={{ display: "flex", flexDirection: "column", gap: 44, marginTop: 70 }}>
      <PipeNode index={0} label="Pass A — Fact extractor" sub="records what happened · never judges" accent={T.aqua} />
      <PipeNode index={1} label="Pass B — Rubric judge" sub="8 criteria · 5 terminal states · transcript is authority" accent={T.blue} />
      <PipeNode index={2} label="Schema validation" sub="legal verdicts only · retry + JSON repair" accent={T.yellow} />
      <PipeNode index={3} label="Pass C — Containment" sub="unsolicited-transfer classifier" accent={T.orange} />
    </div>
  </>
);

/* 4 — calibration counter */
export const S4: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <>
      <Kicker>Step 3 · Calibrate before you spend</Kicker>
      <Headline>Judge agreement vs human labels</Headline>
      <div
        style={{
          fontSize: 300,
          fontWeight: 700,
          letterSpacing: -6,
          marginTop: 40,
          color: T.ink,
        }}
      >
        <Counter from={95.1} to={99.3} delay={1.2 * fps} durSec={4} />
      </div>
      <div
        style={{
          display: "flex",
          gap: 40,
          color: T.ink2,
          fontSize: 42,
          opacity: interpolate(frame, [5.5 * fps, 6 * fps], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
        }}
      >
        <span>7 disagreements root-caused</span>
        <span style={{ color: T.muted }}>·</span>
        <span>3 prompt boundaries fixed</span>
        <span style={{ color: T.muted }}>·</span>
        <span>terminal states 18/18</span>
      </div>
    </>
  );
};

/* 5 — findings */
export const S5: React.FC = () => (
  <>
    <Kicker>The findings</Kicker>
    <Headline>
      2% true failures — but she repeats herself in <span style={{ color: T.blue }}>1 of 3</span> calls
    </Headline>
    <div style={{ flex: 1 }} />
    <ShotCard shot="shots/charts.png" delay={14} height={540} zoomTo={1.05} />
  </>
);

/* 6 — drill-down / citations */
export const S6: React.FC = () => (
  <>
    <Kicker>Machine-verified citations</Kicker>
    <Headline size={84}>Every number opens the transcript behind it</Headline>
    <div style={{ flex: 1 }} />
    <ShotCard shot="shots/call028.png" delay={12} height={600} pan={620} zoomFrom={1.02} zoomTo={1.02} />
  </>
);

/* 7 — recommendations + measurement (two visuals, solved with time) */
export const S7: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const swap = 5.4 * fps;
  const xfade = interpolate(frame, [swap, swap + 0.6 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <>
      <Kicker>The output</Kicker>
      <Headline size={84}>4 fixes with owners — and a scoreboard to prove they worked</Headline>
      <div style={{ flex: 1 }} />
      <div style={{ position: "relative", height: 560 }}>
        <div style={{ position: "absolute", inset: 0, opacity: 1 - xfade }}>
          <ShotCard shot="shots/tasks.png" delay={10} height={560} zoomTo={1.04} />
        </div>
        <div style={{ position: "absolute", inset: 0, opacity: xfade }}>
          <ShotCard shot="shots/scoreboard.png" delay={0} height={560} zoomTo={1.04} />
        </div>
      </div>
    </>
  );
};

/* 8 — CTA */
export const S8: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const urlIn = interpolate(frame, [5.6 * fps, 6.2 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <>
      <Kicker>Repeatable by construction</Kicker>
      <Headline size={84}>A new batch is one command</Headline>
      <div style={{ marginTop: 60 }}>
        <Terminal command="python3 scripts/new_batch.py new_calls/ --deploy" delay={12} />
      </div>
      <div style={{ flex: 1 }} />
      <div
        style={{
          textAlign: "center",
          fontSize: 66,
          fontWeight: 700,
          color: T.blue,
          opacity: urlIn,
          translate: `0px ${(1 - urlIn) * 30}px`,
          paddingBottom: 20,
        }}
      >
        mia-eval-dashboard.vercel.app
      </div>
    </>
  );
};
