import React from 'react';
import {
  AbsoluteFill, Img, useCurrentFrame, interpolate, spring,
  staticFile, OffthreadVideo,
} from 'remotion';
import {SegmentData} from './types';
import {ThemeConfig, ROLE_ACCENT} from './theme';
import {CounterRollup} from './anims/CounterRollup';
import {LineChart} from './anims/LineChart';
import {resolveFontFamily} from './fonts';

const isVideo = (path: string) => path.toLowerCase().endsWith('.mp4') || path.endsWith('.webm');

export const Segment: React.FC<{
  seg: SegmentData;
  theme: ThemeConfig;
  width: number;
  height: number;
  durationFrames: number;
  fps: number;
  captionYOffset?: number;
  captionSize?: number;
  captionArea?: string;
  captionFontId?: string;
}> = ({seg, theme, width, height, durationFrames, fps,
       captionYOffset, captionSize, captionArea, captionFontId}) => {
  const frame = useCurrentFrame();

  // Ken Burns - 아주 미세한 줌인 (무한 정적 이미지 방지)
  const zoom = interpolate(frame, [0, durationFrames], [1.0, 1.08]);

  return (
    <AbsoluteFill>
      {/* 배경 영상/사진 영역 (중앙 vidH) */}
      <div style={{
        position: 'absolute',
        top: theme.topH,
        left: 0,
        width,
        height: theme.vidH,
        overflow: 'hidden',
      }}>
        <div style={{
          width: '100%', height: '100%',
          transform: `scale(${zoom})`,
          transformOrigin: 'center center',
        }}>
          {(() => {
            const objectPosX = (seg.videoObjectPosX ?? 0.5) * 100;
            const commonStyle: React.CSSProperties = {
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              objectPosition: `${objectPosX}% 50%`,
            };
            return isVideo(seg.mediaPath) ? (
              <OffthreadVideo src={staticFile(seg.mediaPath)} style={commonStyle} muted />
            ) : (
              <Img src={staticFile(seg.mediaPath)} style={commonStyle} />
            );
          })()}
        </div>
      </div>

      {/* 하단 검정 영역 */}
      <div style={{
        position: 'absolute',
        top: theme.topH + theme.vidH,
        left: 0,
        width,
        height: theme.botH,
        backgroundColor: 'black',
      }} />

      {/* 캡션 청크 — 시간대별로 순차 등장 */}
      <CaptionChunks
        seg={seg} theme={theme} durationFrames={durationFrames} fps={fps}
        width={width}
        yOffset={captionYOffset}
        sizeOverride={captionSize}
        areaOverride={captionArea}
        fontId={captionFontId}
      />

      {/* 수치 팝업 — 숫자면 0→N 롤업 카운터 (나레이션 중후반에 카운팅) */}
      {seg.highlightStat && (
        <CounterRollup
          stat={seg.highlightStat}
          fps={fps}
          color={ROLE_ACCENT[seg.role] || '#FFFFFF'}
          startFrame={Math.round(durationFrames * 0.20)}
          rollupFrames={Math.max(Math.round(fps * 0.8), Math.round(durationFrames * 0.45))}
          holdFrames={Math.round(durationFrames * 0.25)}
          style={{
            position: 'absolute',
            top: theme.topH + theme.vidH * 0.18,
            left: 0,
            width: '100%',
            textAlign: 'center',
            fontSize: 180,
            padding: '0 40px',
            zIndex: 30,
          }}
        />
      )}

      {/* 차트 (chartValues 있을 때 영상 상단 우측) — 나레이션 중후반에 그려짐 */}
      {seg.chartValues && seg.chartValues.length >= 2 && (
        <div style={{
          position: 'absolute',
          top: theme.topH + 40,
          right: 40,
          zIndex: 25,
        }}>
          <LineChart
            values={seg.chartValues}
            width={380}
            height={220}
            color={ROLE_ACCENT[seg.role] || '#ffcc00'}
            startFrame={Math.round(durationFrames * 0.15)}
            drawFrames={Math.max(Math.round(fps * 1.0), Math.round(durationFrames * 0.55))}
          />
        </div>
      )}

      {/* 이모지 리액션 (climax/twist) */}
      {seg.reactionEmoji && (
        <EmojiReaction emoji={seg.reactionEmoji} theme={theme} durationFrames={durationFrames} fps={fps} />
      )}

      {/* 출처 크레딧 (저작권 안전 채널 영상용) */}
      {seg.sourceCredit && (
        <div style={{
          position: 'absolute',
          right: 20,
          top: theme.topH + theme.vidH - 50,
          background: 'rgba(0,0,0,0.55)',
          color: '#FFFFFF',
          padding: '4px 12px',
          borderRadius: 6,
          fontSize: 22,
          fontFamily: 'sans-serif',
          fontWeight: 600,
          zIndex: 40,
          letterSpacing: 0.3,
        }}>
          {seg.sourceCredit}
        </div>
      )}
    </AbsoluteFill>
  );
};

const CaptionChunks: React.FC<{
  seg: SegmentData;
  theme: ThemeConfig;
  durationFrames: number;
  fps: number;
  width: number;
  yOffset?: number;
  sizeOverride?: number;
  areaOverride?: string;
  fontId?: string;
}> = ({seg, theme, durationFrames, fps, width, yOffset, sizeOverride, areaOverride, fontId}) => {
  const frame = useCurrentFrame();
  const chunks = seg.captionChunks && seg.captionChunks.length > 0
    ? seg.captionChunks
    : [seg.caption || ''];

  const fontSize = sizeOverride || theme.captionSize;
  const fontFamily = resolveFontFamily(fontId);

  // Python 측에서 이미 한 줄씩 쪼개고 chunkTimings를 정확히 부여한 상태 —
  // 여기선 현재 프레임에 해당하는 청크만 골라 표시.
  const totalDurSec = durationFrames / fps;
  const hasTimings = seg.chunkTimings && seg.chunkTimings.length === chunks.length;
  const curSec = frame / fps;
  let activeIdx = 0;
  let chunkStart = 0;
  if (hasTimings) {
    for (let i = 0; i < seg.chunkTimings!.length; i++) {
      if (curSec >= seg.chunkTimings![i][0]) {
        activeIdx = i;
        chunkStart = seg.chunkTimings![i][0];
      }
    }
  } else {
    const perChunk = totalDurSec / chunks.length;
    activeIdx = Math.min(chunks.length - 1, Math.floor(curSec / perChunk));
    chunkStart = activeIdx * perChunk;
  }
  const chunkStartFrame = Math.round(chunkStart * fps);
  const localFrame = frame - chunkStartFrame;

  // 슬라이드 업 + 페이드인 (청크 시작 시점부터)
  const enter = spring({frame: localFrame, fps, config: {damping: 15, stiffness: 140}});
  const translateY = interpolate(enter, [0, 1], [30, 0]);
  const opacity = interpolate(enter, [0, 1], [0, 1]);

  const text = chunks[activeIdx] || '';
  const isEmphasized = (t: string) =>
    seg.emphasisWords?.some((w) => w && t.includes(w));

  // 단어별 색칠
  const tokens = text.split(/(\s+)/);

  // area별 기본 위치 계산 (PIL renderer와 동일한 개념)
  const area = areaOverride || 'bottom';
  let boxTop: number;
  let boxHeight: number;
  if (area === 'video_bottom_overlay') {
    boxHeight = Math.round(theme.vidH * 0.30);
    boxTop = theme.topH + theme.vidH - boxHeight - 40;
  } else if (area === 'video_bottom_pill') {
    boxHeight = Math.round(theme.vidH * 0.25);
    boxTop = theme.topH + theme.vidH - boxHeight - 50;
  } else {
    boxTop = theme.topH + theme.vidH;
    boxHeight = theme.botH;
  }
  boxTop += (yOffset || 0);

  return (
    <div style={{
      position: 'absolute',
      top: boxTop,
      left: 0,
      width: '100%',
      height: boxHeight,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      textAlign: 'center',
      padding: '0 60px',
      opacity,
      transform: `translateY(${translateY}px)`,
    }}>
      <div style={{
        fontFamily,
        fontWeight: 900,
        fontSize,
        lineHeight: 1.2,
        color: theme.captionColor,
        WebkitTextStroke: `${theme.captionStrokeW}px ${theme.captionStrokeColor}`,
        paintOrder: 'stroke fill',
        // 자연스러운 wrap + 최대 2줄 제한 (Python이 이미 2줄 분량으로 쪼개줌)
        whiteSpace: 'normal',
        wordBreak: 'keep-all',   // 한글: 단어 중간 줄바꿈 방지
        overflowWrap: 'break-word',
        display: '-webkit-box',
        WebkitLineClamp: 2,
        WebkitBoxOrient: 'vertical',
        overflow: 'hidden',
        maxWidth: '100%',
      }}>
        {tokens.map((tk, i) => (
          <span key={i} style={{color: isEmphasized(tk) ? theme.emphasisColor : theme.captionColor}}>
            {tk}
          </span>
        ))}
      </div>
    </div>
  );
};

const StatPopup: React.FC<{stat: string; theme: ThemeConfig; roleColor: string}> = ({
  stat,
  theme,
  roleColor,
}) => {
  const frame = useCurrentFrame();
  const scale = spring({
    frame,
    fps: 30,
    config: {damping: 10, mass: 0.5, stiffness: 180},
  });
  const opacity = interpolate(frame, [0, 8, 60, 75], [0, 1, 1, 0.3], {
    extrapolateRight: 'clamp',
  });

  return (
    <div style={{
      position: 'absolute',
      top: theme.topH + theme.vidH * 0.20,
      left: 0,
      width: '100%',
      display: 'flex',
      justifyContent: 'center',
      opacity,
      transform: `scale(${scale})`,
      zIndex: 30,
    }}>
      <div style={{
        fontFamily: '"Noto Sans CJK KR", sans-serif',
        fontWeight: 900,
        fontSize: 180,
        color: roleColor,
        WebkitTextStroke: '8px black',
        paintOrder: 'stroke fill',
        padding: '0 40px',
        background: 'rgba(0,0,0,0.55)',
        borderRadius: 30,
        lineHeight: 1.1,
      }}>
        {stat}
      </div>
    </div>
  );
};

const EmojiReaction: React.FC<{
  emoji: string;
  theme: ThemeConfig;
  durationFrames: number;
  fps: number;
}> = ({emoji, theme, durationFrames, fps}) => {
  const frame = useCurrentFrame();
  const bounce = spring({frame, fps, config: {damping: 7, stiffness: 120}});
  const rot = interpolate(frame, [0, 30, 60], [-15, 8, 0], {extrapolateRight: 'clamp'});
  const scale = interpolate(bounce, [0, 1], [0.1, 1]);
  const opacity = interpolate(frame, [0, 6, durationFrames - 15, durationFrames],
                              [0, 1, 1, 0], {extrapolateRight: 'clamp'});

  return (
    <div style={{
      position: 'absolute',
      top: theme.topH + 40,
      right: 40,
      fontSize: 200,
      opacity,
      transform: `scale(${scale}) rotate(${rot}deg)`,
      zIndex: 20,
      textShadow: '0 0 30px rgba(0,0,0,0.6)',
      fontFamily: '"Noto Color Emoji", "Apple Color Emoji", sans-serif',
    }}>
      {emoji}
    </div>
  );
};
