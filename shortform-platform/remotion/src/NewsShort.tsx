import React from 'react';
import {AbsoluteFill, Sequence, useVideoConfig} from 'remotion';
import {TransitionSeries, linearTiming} from '@remotion/transitions';
import {fade} from '@remotion/transitions/fade';
import {NewsProps} from './types';
import {Segment} from './Segment';
import {TitleBar} from './TitleBar';
import {DEFAULT_THEME} from './theme';
import {BreakingBanner} from './anims/BreakingBanner';
import {resolveFontFamily} from './fonts';

const TRANSITION_FRAMES = 8;  // 세그먼트 간 크로스페이드 길이

export const NewsShort: React.FC<NewsProps> = (props) => {
  const {
    hookPhrase, segments, breakingNews,
    layoutTopH, layoutVidH, layoutBotH,
    captionYOffset, captionSize, captionArea,
    captionColor, captionStrokeColor, captionStrokeW, captionFontId,
    titleSize, titleColor, titleAccentLastLine, titleAccentColor, titleFontId,
    bottomBrandText, bottomBrandSize, bottomBrandFontId,
    enableTransitions,
  } = props;
  const {fps, width, height} = useVideoConfig();
  const base = DEFAULT_THEME;
  const th = {
    ...base,
    topH: layoutTopH ?? base.topH,
    vidH: layoutVidH ?? base.vidH,
    botH: layoutBotH ?? base.botH,
    titleColor: titleColor ?? base.titleColor,
    titleSize: titleSize ?? base.titleSize,
    captionColor: captionColor ?? base.captionColor,
    captionStrokeColor: captionStrokeColor ?? base.captionStrokeColor,
    captionStrokeW: captionStrokeW ?? base.captionStrokeW,
    captionSize: captionSize ?? base.captionSize,
  };

  // 각 세그먼트 durationInFrames
  const segDurs = segments.map((s) => Math.round(s.duration * fps));
  // 전환 시 겹침 → 총 프레임 = 합 - (n-1) * transitionFrames (transitions 활성일 때)
  const n = segments.length;
  const transitionOverlap = enableTransitions ? TRANSITION_FRAMES * Math.max(0, n - 1) : 0;
  const totalFrames = segDurs.reduce((a, b) => a + b, 0) - transitionOverlap;

  const renderSegment = (seg: typeof segments[0], i: number, durFrames: number) => (
    <Segment
      seg={seg}
      theme={th}
      width={width}
      height={height}
      durationFrames={durFrames}
      fps={fps}
      captionYOffset={captionYOffset}
      captionArea={captionArea}
      captionFontId={captionFontId}
    />
  );

  return (
    <AbsoluteFill style={{backgroundColor: 'black'}}>
      {enableTransitions && n >= 2 ? (
        <TransitionSeries>
          {segments.map((seg, i) => {
            const isLast = i === n - 1;
            return (
              <React.Fragment key={i}>
                <TransitionSeries.Sequence durationInFrames={segDurs[i]}>
                  {renderSegment(seg, i, segDurs[i])}
                </TransitionSeries.Sequence>
                {!isLast && (
                  <TransitionSeries.Transition
                    presentation={fade()}
                    timing={linearTiming({durationInFrames: TRANSITION_FRAMES})}
                  />
                )}
              </React.Fragment>
            );
          })}
        </TransitionSeries>
      ) : (
        // 무전환 모드: 기존 Sequence 배치
        (() => {
          let cum = 0;
          return segments.map((seg, i) => {
            const from = cum;
            cum += segDurs[i];
            return (
              <Sequence key={i} from={from} durationInFrames={segDurs[i]}>
                {renderSegment(seg, i, segDurs[i])}
              </Sequence>
            );
          });
        })()
      )}

      <TitleBar
        text={hookPhrase}
        theme={th}
        width={width}
        emphasis={Array.from(new Set(segments.flatMap((s) => s.emphasisWords || [])))}
        accentLastLine={titleAccentLastLine}
        accentColor={titleAccentColor}
        fontId={titleFontId}
      />
      {breakingNews && (
        <Sequence from={0} durationInFrames={Math.round(2.0 * fps)}>
          <BreakingBanner width={width} fps={fps} />
        </Sequence>
      )}
      {bottomBrandText && (
        <BottomBrand
          text={bottomBrandText}
          size={bottomBrandSize ?? 86}
          fontId={bottomBrandFontId ?? titleFontId}
          theme={th}
          width={width}
        />
      )}
      <ProgressBar totalFrames={totalFrames} width={width} />
    </AbsoluteFill>
  );
};

const BottomBrand: React.FC<{
  text: string;
  size: number;
  fontId?: string;
  theme: {topH: number; vidH: number; botH: number};
  width: number;
}> = ({text, size, fontId, theme, width}) => {
  const brandH = Math.max(Math.round(theme.botH * 0.4), 120);
  const top = theme.topH + theme.vidH + theme.botH - brandH;
  return (
    <div style={{
      position: 'absolute',
      top,
      left: 0,
      width,
      height: brandH,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      color: '#FFFFFF',
      fontFamily: resolveFontFamily(fontId),
      fontWeight: 900,
      fontSize: size,
      zIndex: 40,
    }}>
      {text}
    </div>
  );
};

const ProgressBar: React.FC<{totalFrames: number; width: number}> = ({totalFrames, width}) => {
  const {useCurrentFrame} = require('remotion') as typeof import('remotion');
  const frame = useCurrentFrame();
  const pct = Math.min(1, frame / Math.max(1, totalFrames));
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
