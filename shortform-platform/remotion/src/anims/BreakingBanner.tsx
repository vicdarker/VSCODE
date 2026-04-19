import React from 'react';
import {useCurrentFrame, interpolate, spring} from 'remotion';

/**
 * 영상 맨 위에 빨간 "속보 · BREAKING" 배너 슬라이드인.
 * 등장: 0~0.5s, 유지: 1.5s까지, 퇴장 페이드: 2.0s까지.
 */
export const BreakingBanner: React.FC<{
  width: number;
  fps: number;
  text?: string;
  enterFrames?: number;
  holdUntil?: number;       // 프레임 번호까지 유지
  fadeBy?: number;          // 이 프레임까지 페이드 아웃
}> = ({
  width,
  fps,
  text = '속보 · BREAKING',
  enterFrames = 14,
  holdUntil = 45,
  fadeBy = 60,
}) => {
  const frame = useCurrentFrame();
  // 좌→우 슬라이드 인
  const enter = spring({
    frame,
    fps,
    config: {damping: 18, stiffness: 140},
  });
  const x = interpolate(enter, [0, 1], [-width, 0]);
  const opacity = interpolate(frame, [0, enterFrames, holdUntil, fadeBy],
                              [0, 1, 1, 0], {extrapolateRight: 'clamp'});

  return (
    <div
      style={{
        position: 'absolute',
        top: 12,
        left: 0,
        transform: `translateX(${x}px)`,
        opacity,
        zIndex: 100,
        width: '100%',
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        padding: '14px 28px',
        background: 'linear-gradient(90deg, #dc1414 0%, #c80000 100%)',
        boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
      }}
    >
      {/* 깜빡이는 붉은 점 */}
      <PulseDot />
      <span
        style={{
          fontFamily: '"Noto Sans CJK KR", sans-serif',
          fontWeight: 900,
          fontSize: 52,
          color: '#fff',
          letterSpacing: '0.05em',
          textShadow: '0 2px 4px rgba(0,0,0,0.6)',
        }}
      >
        {text}
      </span>
    </div>
  );
};

const PulseDot: React.FC = () => {
  const frame = useCurrentFrame();
  const pulse = Math.sin(frame / 5) * 0.5 + 0.5;
  return (
    <div
      style={{
        width: 24,
        height: 24,
        borderRadius: '50%',
        background: '#fff',
        opacity: 0.4 + 0.6 * pulse,
        boxShadow: '0 0 12px rgba(255,255,255,0.8)',
      }}
    />
  );
};
