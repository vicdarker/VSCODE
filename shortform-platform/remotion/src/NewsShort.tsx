import React from 'react';
import {AbsoluteFill, Sequence, useVideoConfig} from 'remotion';
import {NewsProps} from './types';
import {Segment} from './Segment';
import {TitleBar} from './TitleBar';
import {THEMES} from './theme';

export const NewsShort: React.FC<NewsProps> = ({hookPhrase, segments, theme}) => {
  const {fps, width, height} = useVideoConfig();
  const th = THEMES[theme] || THEMES.samprotv;

  let cumFrames = 0;
  return (
    <AbsoluteFill style={{backgroundColor: 'black'}}>
      {segments.map((seg, i) => {
        const durFrames = Math.round(seg.duration * fps);
        const from = cumFrames;
        cumFrames += durFrames;
        return (
          <Sequence key={i} from={from} durationInFrames={durFrames}>
            <Segment
              seg={seg}
              theme={th}
              width={width}
              height={height}
              durationFrames={durFrames}
              fps={fps}
            />
          </Sequence>
        );
      })}
      {/* 상단 고정 제목 — 전 세그먼트 emphasis_words 합집합을 강조 */}
      <TitleBar
        text={hookPhrase}
        theme={th}
        width={width}
        emphasis={Array.from(new Set(segments.flatMap((s) => s.emphasisWords || [])))}
      />
      {/* 상단 진행 바 */}
      <ProgressBar totalFrames={cumFrames} width={width} />
    </AbsoluteFill>
  );
};

const ProgressBar: React.FC<{totalFrames: number; width: number}> = ({totalFrames, width}) => {
  const {useCurrentFrame} = require('remotion') as typeof import('remotion');
  const frame = useCurrentFrame();
  const pct = Math.min(1, frame / totalFrames);
  return (
    <div
      style={{
        position: 'absolute', top: 0, left: 0,
        width: `${pct * 100}%`, height: 4,
        background: 'white', opacity: 0.9, zIndex: 100,
      }}
    />
  );
};
