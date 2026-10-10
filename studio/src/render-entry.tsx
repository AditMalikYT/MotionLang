import React from "react";
import { Composition, registerRoot } from "remotion";
import { Timeline, type TimelineProps } from "./Timeline";
import { EMPTY_COMPOSITION } from "./types";

// Remotion CLI entry. `calculateMetadata` lets a bundled render adapt to the
// width/height/fps/duration carried inside composition.json.
const Root: React.FC = () => {
  return (
    <Composition
      id="MotionComposition"
      component={Timeline as any}
      durationInFrames={150}
      fps={30}
      width={1280}
      height={720}
      defaultProps={{ data: EMPTY_COMPOSITION } as TimelineProps}
      calculateMetadata={({ props }: any) => {
        const m = props.data?.meta || EMPTY_COMPOSITION.meta;
        return {
          width: m.width,
          height: m.height,
          fps: m.fps,
          durationInFrames: Math.max(1, Math.round(m.duration * m.fps)),
        };
      }}
    />
  );
};

registerRoot(Root);
