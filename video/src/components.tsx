import React from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { T } from "./theme";

const EASE = Easing.bezier(0.16, 1, 0.3, 1);

/** Scene wrapper: fade in over 0.4s, fade out over the last 0.3s. */
export const SceneShell: React.FC<{
  durationInFrames: number;
  children: React.ReactNode;
}> = ({ durationInFrames, children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const opacity =
    interpolate(frame, [0, 0.4 * fps], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: EASE,
    }) *
    interpolate(frame, [durationInFrames - 0.3 * fps, durationInFrames], [1, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  return (
    <AbsoluteFill
      style={{
        backgroundColor: T.page,
        fontFamily: T.sans,
        opacity,
        padding: "90px 120px",
      }}
    >
      {children}
    </AbsoluteFill>
  );
};

/** Small blue uppercase label above the headline. */
export const Kicker: React.FC<{ children: React.ReactNode; delay?: number }> = ({
  children,
  delay = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <div
      style={{
        color: T.blue,
        fontSize: 34,
        fontWeight: 700,
        letterSpacing: 6,
        textTransform: "uppercase",
        marginBottom: 22,
        opacity: interpolate(frame, [delay, delay + 0.4 * fps], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: EASE,
        }),
      }}
    >
      {children}
    </div>
  );
};

/** Big headline, slides up + fades. */
export const Headline: React.FC<{
  children: React.ReactNode;
  delay?: number;
  size?: number;
}> = ({ children, delay = 4, size = 96 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <div
      style={{
        color: T.ink,
        fontSize: size,
        fontWeight: 700,
        lineHeight: 1.12,
        letterSpacing: -1.5,
        maxWidth: 1500,
        opacity: interpolate(frame, [delay, delay + 0.5 * fps], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: EASE,
        }),
        translate: `0px ${interpolate(frame, [delay, delay + 0.5 * fps], [36, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: EASE,
        })}px`,
      }}
    >
      {children}
    </div>
  );
};

export const Sub: React.FC<{ children: React.ReactNode; delay?: number }> = ({
  children,
  delay = 10,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <div
      style={{
        color: T.ink2,
        fontSize: 46,
        lineHeight: 1.4,
        marginTop: 26,
        maxWidth: 1400,
        opacity: interpolate(frame, [delay, delay + 0.5 * fps], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: EASE,
        }),
      }}
    >
      {children}
    </div>
  );
};

/**
 * Screenshot in a rounded card, rising in with a slow Ken-Burns drift.
 * pan: vertical drift of the IMAGE inside the card (px, over the scene).
 */
export const ShotCard: React.FC<{
  shot: string;
  delay?: number;
  height: number;
  width?: number | string;
  zoomFrom?: number;
  zoomTo?: number;
  pan?: number;
  align?: "top" | "center";
}> = ({ shot, delay = 8, height, width = "100%", zoomFrom = 1, zoomTo = 1.04, pan = 0, align = "top" }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const enter = interpolate(frame, [delay, delay + 0.6 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE,
  });
  const drift = interpolate(frame, [delay, durationInFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div
      style={{
        height,
        width,
        borderRadius: 18,
        border: `1px solid ${T.border}`,
        overflow: "hidden",
        backgroundColor: T.surface,
        boxShadow: "0 30px 80px rgba(0,0,0,0.55)",
        opacity: enter,
        translate: `0px ${(1 - enter) * 60}px`,
      }}
    >
      <Img
        src={staticFile(shot)}
        style={{
          width: "100%",
          display: "block",
          objectFit: "cover",
          objectPosition: align === "top" ? "top" : "center",
          scale: String(zoomFrom + (zoomTo - zoomFrom) * drift),
          translate: `0px ${-pan * drift}px`,
        }}
      />
    </div>
  );
};

/** Animated percentage counter. */
export const Counter: React.FC<{
  from: number;
  to: number;
  delay: number;
  durSec: number;
}> = ({ from, to, delay, durSec }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const v = interpolate(frame, [delay, delay + durSec * fps], [from, to], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.3, 0, 0.2, 1),
  });
  return (
    <span style={{ color: T.ink, fontWeight: 700 }}>
      {v.toFixed(1)}
      <span style={{ color: T.blue }}>%</span>
    </span>
  );
};

/** One node of the pipeline diagram. */
export const PipeNode: React.FC<{
  label: string;
  sub: string;
  index: number;
  accent?: string;
}> = ({ label, sub, index, accent = T.blue }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const delay = 8 + index * 0.55 * fps;
  const enter = interpolate(frame, [delay, delay + 0.5 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE,
  });
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 26,
        opacity: enter,
        translate: `${(1 - enter) * -50}px 0px`,
      }}
    >
      <div
        style={{
          width: 16,
          height: 16,
          borderRadius: 99,
          backgroundColor: accent,
          flexShrink: 0,
        }}
      />
      <div>
        <div style={{ color: T.ink, fontSize: 52, fontWeight: 700 }}>{label}</div>
        <div style={{ color: T.muted, fontSize: 34, marginTop: 2 }}>{sub}</div>
      </div>
    </div>
  );
};

/** Terminal card with typewriter command. */
export const Terminal: React.FC<{ command: string; delay?: number }> = ({
  command,
  delay = 8,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const chars = Math.floor(
    interpolate(frame, [delay, delay + 2.2 * fps], [0, command.length], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );
  const cursorOn = Math.floor(frame / (0.5 * fps)) % 2 === 0;
  return (
    <div
      style={{
        backgroundColor: T.surface,
        border: `1px solid ${T.border}`,
        borderRadius: 18,
        padding: "44px 52px",
        fontFamily: T.mono,
        fontSize: 44,
        color: T.ink2,
        boxShadow: "0 30px 80px rgba(0,0,0,0.55)",
      }}
    >
      <div style={{ display: "flex", gap: 12, marginBottom: 30 }}>
        {[T.critical, T.yellow, T.good].map((c) => (
          <div key={c} style={{ width: 20, height: 20, borderRadius: 99, backgroundColor: c }} />
        ))}
      </div>
      <div>
        <span style={{ color: T.aqua }}>$ </span>
        <span style={{ color: T.ink }}>{command.slice(0, chars)}</span>
        <span style={{ opacity: cursorOn ? 1 : 0, color: T.blue }}>▍</span>
      </div>
    </div>
  );
};
