import React from 'react';
import {
  AbsoluteFill, Img, useCurrentFrame, interpolate, spring,
  staticFile, OffthreadVideo,
} from 'remotion';
import {SegmentData} from './types';
import {ThemeConfig, ROLE_ACCENT} from './theme';

const isVideo = (path: string) => path.toLowerCase().endsWith('.mp4') || path.endsWith('.webm');

export const Segment: React.FC<{
  seg: SegmentData;
  theme: ThemeConfig;
  width: number;
  height: number;
  durationFrames: number;
  fps: number;
}> = ({seg, theme, width, height, durationFrames, fps}) => {
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
          {isVideo(seg.mediaPath) ? (
            <OffthreadVideo
              src={staticFile(seg.mediaPath)}
              style={{width: '100%', height: '100%', objectFit: 'cover'}}
              muted
            />
          ) : (
            <Img
              src={staticFile(seg.mediaPath)}
              style={{width: '100%', height: '100%', objectFit: 'cover'}}
            />
          )}
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
      <CaptionChunks seg={seg} theme={theme} durationFrames={durationFrames} fps={fps} />

      {/* 수치 팝업 */}
      {seg.highlightStat && (
        <StatPopup
          stat={seg.highlightStat}
          theme={theme}
          roleColor={ROLE_ACCENT[seg.role] || '#FFFFFF'}
        />
      )}

      {/* 이모지 리액션 (climax/twist) */}
      {seg.reactionEmoji && (
        <EmojiReaction emoji={seg.reactionEmoji} theme={theme} durationFrames={durationFrames} fps={fps} />
      )}
    </AbsoluteFill>
  );
};

const CaptionChunks: React.FC<{
  seg: SegmentData;
  theme: ThemeConfig;
  durationFrames: number;
  fps: number;
}> = ({seg, theme, durationFrames, fps}) => {
  const frame = useCurrentFrame();
  const chunks = seg.captionChunks && seg.captionChunks.length > 0
    ? seg.captionChunks
    : [seg.caption];
  const chunkFrames = durationFrames / chunks.length;
  const activeIdx = Math.min(chunks.length - 1, Math.floor(frame / chunkFrames));
  const localFrame = frame - activeIdx * chunkFrames;

  // 슬라이드 업 + 페이드인 (처음 10프레임)
  const enter = spring({frame: localFrame, fps, config: {damping: 15, stiffness: 140}});
  const translateY = interpolate(enter, [0, 1], [30, 0]);
  const opacity = interpolate(enter, [0, 1], [0, 1]);

  const text = chunks[activeIdx] || '';
  const isEmphasized = (t: string) =>
    seg.emphasisWords?.some((w) => w && t.includes(w));

  // 단어별 색칠
  const tokens = text.split(/(\s+)/);

  return (
    <div style={{
      position: 'absolute',
      top: theme.topH + theme.vidH,
      left: 0,
      width: '100%',
      height: theme.botH,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      textAlign: 'center',
      padding: '0 60px',
      opacity,
      transform: `translateY(${translateY}px)`,
    }}>
      <div style={{
        fontFamily: '"Noto Sans CJK KR", sans-serif',
        fontWeight: 900,
        fontSize: theme.captionSize,
        lineHeight: 1.2,
        color: theme.captionColor,
        WebkitTextStroke: `${theme.captionStrokeW}px ${theme.captionStrokeColor}`,
        paintOrder: 'stroke fill',
        // 최대 2줄 제한 (초과 시 말줄임표)
        display: '-webkit-box',
        WebkitLineClamp: 2,
        WebkitBoxOrient: 'vertical',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
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
