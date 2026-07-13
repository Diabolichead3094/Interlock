import React from "react";
import { Composition } from "remotion";
import { Main } from "./Main";
import timings from "./timings.json";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="MiaExplainer"
      component={Main}
      durationInFrames={Math.ceil(timings.total * timings.fps)}
      fps={timings.fps}
      width={1920}
      height={1080}
    />
  );
};
