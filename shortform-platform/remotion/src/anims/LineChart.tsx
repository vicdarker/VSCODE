import React from 'react';
import {useCurrentFrame, interpolate} from 'remotion';
import {getLength} from '@remotion/paths';

/**
 * SVG 꺾은선 그래프를 좌→우로 그리는 애니메이션.
 * strokeDasharray + strokeDashoffset 이용.
 */
export const LineChart: React.FC<{
  values: number[];
  width: number;
  height: number;
  color?: string;
  drawFrames?: number;       // 선 그려지는 총 프레임 수
  startFrame?: number;       // 등장 시작 프레임 (세그먼트 기준, 기본 0)
  bgOpacity?: number;
  style?: React.CSSProperties;
}> = ({
  values,
  width,
  height,
  color = '#ffcc00',
  drawFrames = 45,
  startFrame = 0,
  bgOpacity = 0.45,
  style,
}) => {
  const rawFrame = useCurrentFrame();
  const frame = rawFrame - startFrame;
  if (!values || values.length < 2) return null;
  // startFrame 이전엔 렌더 스킵
  if (frame < 0) return null;

  // 값 정규화
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const padX = 40;
  const padY = 60;
  const innerW = width - padX * 2;
  const innerH = height - padY * 2;

  const points = values.map((v, i) => {
    const x = padX + (i / (values.length - 1)) * innerW;
    const y = padY + (1 - (v - min) / range) * innerH;
    return {x, y};
  });

  // polyline "x1,y1 x2,y2 ..."
  const pointsStr = points.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');

  // SVG path d 속성 (getLength용) — M x y L x y L x y ...
  const pathD = `M ${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)} ` +
    points.slice(1).map(p => `L ${p.x.toFixed(2)} ${p.y.toFixed(2)}`).join(' ');
  // @remotion/paths의 정확한 path 길이 계산
  const totalLen = getLength(pathD);

  const progress = interpolate(frame, [6, 6 + drawFrames], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const visibleLen = totalLen * progress;

  // 마지막 표시된 점 (움직이는 마커)
  let cursor = {x: points[0].x, y: points[0].y};
  let remaining = visibleLen;
  for (let i = 1; i < points.length; i++) {
    const dx = points[i].x - points[i - 1].x;
    const dy = points[i].y - points[i - 1].y;
    const segLen = Math.sqrt(dx * dx + dy * dy);
    if (remaining <= segLen) {
      const t = segLen === 0 ? 0 : remaining / segLen;
      cursor = {x: points[i - 1].x + dx * t, y: points[i - 1].y + dy * t};
      break;
    }
    remaining -= segLen;
    cursor = points[i];
  }

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      style={{
        ...style,
        background: `rgba(10, 10, 15, ${bgOpacity})`,
        borderRadius: 12,
      }}
    >
      {/* 그리드 */}
      <line x1={padX} y1={padY + innerH} x2={padX + innerW} y2={padY + innerH}
            stroke="rgba(255,255,255,0.3)" strokeWidth={2} />
      {/* 선 */}
      <polyline
        points={pointsStr}
        fill="none"
        stroke={color}
        strokeWidth={6}
        strokeLinejoin="round"
        strokeLinecap="round"
        strokeDasharray={totalLen}
        strokeDashoffset={totalLen - visibleLen}
      />
      {/* 끝 마커 (원) */}
      {progress > 0 && progress < 1 && (
        <circle cx={cursor.x} cy={cursor.y} r={10} fill={color} stroke="white" strokeWidth={3} />
      )}
      {progress >= 1 && points.length > 0 && (
        <circle cx={points[points.length - 1].x} cy={points[points.length - 1].y} r={10}
                fill={color} stroke="white" strokeWidth={3} />
      )}
    </svg>
  );
};
