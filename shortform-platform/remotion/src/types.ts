export type SegmentData = {
  mediaPath: string;         // 절대 경로 (컨테이너 내)
  caption: string;
  captionChunks: string[];
  emphasisWords: string[];
  highlightStat: string;
  reactionEmoji: string;
  role: 'hook' | 'context' | 'body' | 'climax' | 'twist' | 'cta';
  duration: number;          // 초
  // 애니메이션 옵션 (선택)
  chartValues?: number[];    // 존재 시 영상 위에 꺾은선 그래프 애니메이션
  // 청크별 정확한 (시작, 종료) 초. TTS 단어 타임스탬프 기반. 없으면 균등 분할.
  chunkTimings?: [number, number][];
  // Smart crop: 얼굴 중심 X 비율 (0.0~1.0). 없으면 중앙(0.5).
  videoObjectPosX?: number;
  // 저작권 출처 (화이트리스트 YouTube 영상) — 우하단 작은 텍스트로 표시
  sourceCredit?: string;
};

export type NewsProps = {
  hookPhrase: string;
  segments: SegmentData[];
  fps: number;
  breakingNews?: boolean;    // 전체 영상 첫 1.5초 빨강 "속보" 배너
  // 레이아웃
  layoutTopH?: number;
  layoutVidH?: number;
  layoutBotH?: number;
  // 자막
  captionYOffset?: number;
  captionSize?: number;
  captionArea?: string;
  captionColor?: string;
  captionStrokeColor?: string;
  captionStrokeW?: number;
  captionFontId?: string;       // Google Fonts 매핑 (fonts.ts)
  // 타이틀
  titleSize?: number;
  titleColor?: string;
  titleAccentLastLine?: boolean;
  titleAccentColor?: string;
  titleFontId?: string;
  // 하단 브랜드
  bottomBrandText?: string;
  bottomBrandSize?: number;
  bottomBrandFontId?: string;
  // 전환
  enableTransitions?: boolean;
};
