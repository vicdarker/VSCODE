export type ThemeConfig = {
  topH: number;
  vidH: number;
  botH: number;
  titleColor: string;
  titleSize: number;
  captionColor: string;
  captionStrokeColor: string;
  captionStrokeW: number;
  captionSize: number;
  emphasisColor: string;
};

// 단일 기본 테마 — 사용자 overrides로 모든 속성 치환 가능
export const DEFAULT_THEME: ThemeConfig = {
  topH: 290,
  vidH: 1280,
  botH: 350,
  titleColor: '#FFFFFF',
  titleSize: 92,
  captionColor: '#FFF000',
  captionStrokeColor: '#000000',
  captionStrokeW: 8,
  captionSize: 72,
  emphasisColor: '#FFE600',
};

export const THEMES = {default: DEFAULT_THEME};

export const ROLE_ACCENT: Record<string, string> = {
  hook: '#FF5050',
  context: '#B4B4B4',
  body: '#FFFFFF',
  climax: '#FFD700',
  twist: '#B464FF',
  cta: '#FF8C00',
};
