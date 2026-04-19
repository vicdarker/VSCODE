import React from 'react';
import {useCurrentFrame, interpolate, spring} from 'remotion';

/**
 * highlightStat 문자열에서 첫 숫자를 감지하여 0→N 카운터 롤업.
 * 예: "+1.79%" → 0.00 → 1.79 증가, 접두/접미 그대로 유지
 *     "869포인트" → 0 → 869
 *     "-11.45%" → 0 → -11.45
 */
const NUM_RE = /([+-]?\d{1,3}(?:,\d{3})*(?:\.\d+)?)/;

export function parseStat(raw: string): {prefix: string; target: number; decimals: number; suffix: string} | null {
  if (!raw) return null;
  const m = raw.match(NUM_RE);
  if (!m) return null;
  const numStr = m[1].replace(/,/g, '');
  const target = parseFloat(numStr);
  if (isNaN(target)) return null;
  const decimals = numStr.includes('.') ? (numStr.split('.')[1]?.length || 0) : 0;
  const start = m.index || 0;
  const prefix = raw.slice(0, start);
  const suffix = raw.slice(start + m[1].length);
  return {prefix, target, decimals, suffix};
}

function formatNum(n: number, decimals: number): string {
  const fixed = n.toFixed(decimals);
  // 천단위 콤마
  const parts = fixed.split('.');
  parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return parts.join('.');
}

export const CounterRollup: React.FC<{
  stat: string;
  fps: number;
  color: string;
  style?: React.CSSProperties;
  rollupFrames?: number;   // 카운터 올라가는데 걸리는 프레임 수
  startFrame?: number;     // 등장 시작 프레임 (세그먼트 기준, 기본 0)
  holdFrames?: number;     // 완료 후 유지 프레임 (페이드아웃 전)
}> = ({stat, fps, color, style, rollupFrames = 30, startFrame = 0, holdFrames = 60}) => {
  const rawFrame = useCurrentFrame();
  const frame = rawFrame - startFrame;
  const parsed = parseStat(stat);

  // 팝업 등장 스프링 (startFrame 이전엔 완전 숨김)
  const scale = spring({
    frame: Math.max(0, frame), fps,
    config: {damping: 9, mass: 0.4, stiffness: 200},
  });
  const pop = interpolate(scale, [0, 1], [0.3, 1]);
  const opacity = frame < 0
    ? 0
    : interpolate(
        frame,
        [0, 6, rollupFrames + holdFrames, rollupFrames + holdFrames + 20],
        [0, 1, 1, 0.3],
        {extrapolateRight: 'clamp'},
      );

  // 카운터 값: ease-out 곡선으로 0→target
  const progress = interpolate(frame, [0, rollupFrames], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  // ease-out cubic
  const eased = 1 - Math.pow(1 - progress, 3);

  let display: string;
  if (parsed) {
    const current = parsed.target * eased;
    display = `${parsed.prefix}${formatNum(current, parsed.decimals)}${parsed.suffix}`;
  } else {
    display = stat;
  }

  return (
    <div style={{
      ...style,
      opacity,
      transform: `scale(${pop})`,
      fontFamily: '"Noto Sans CJK KR", sans-serif',
      fontWeight: 900,
      color,
      WebkitTextStroke: '8px black',
      paintOrder: 'stroke fill',
      fontVariantNumeric: 'tabular-nums',  // 숫자 너비 고정 → 떨림 없음
    }}>
      {display}
    </div>
  );
};
