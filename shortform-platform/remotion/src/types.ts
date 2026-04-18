export type SegmentData = {
  mediaPath: string;         // 절대 경로 (컨테이너 내)
  caption: string;
  captionChunks: string[];
  emphasisWords: string[];
  highlightStat: string;
  reactionEmoji: string;
  role: 'hook' | 'context' | 'body' | 'climax' | 'twist' | 'cta';
  duration: number;          // 초
};

export type NewsProps = {
  hookPhrase: string;
  segments: SegmentData[];
  theme: 'samprotv' | 'youtuber';
  fps: number;
};
