import React from "react";
import { Audio } from "@remotion/media";
import { AbsoluteFill, Sequence, staticFile, useVideoConfig } from "remotion";
import { SceneShell } from "./components";
import { S1, S2, S3, S4, S5, S6, S7, S8 } from "./scenes";
import { T } from "./theme";
import timings from "./timings.json";

const SCENES: React.FC[] = [S1, S2, S3, S4, S5, S6, S7, S8];

export const Main: React.FC = () => {
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill style={{ backgroundColor: T.page }}>
      {timings.scenes.map((s, i) => {
        const from = Math.round(s.start * fps);
        const dur = Math.round(s.dur * fps);
        const SceneComp = SCENES[i];
        return (
          <Sequence key={s.scene} from={from} durationInFrames={dur}>
            <Audio src={staticFile(s.file)} />
            <SceneShell durationInFrames={dur}>
              <SceneComp />
            </SceneShell>
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
