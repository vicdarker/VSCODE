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

export const THEMES: Record<string, ThemeConfig> = {
  samprotv: {
    topH: 630,
    vidH: 810,
    botH: 480,
    titleColor: '#FFFFFF',
    titleSize: 96,
    captionColor: '#FFF000',
    captionStrokeColor: '#000000',
    captionStrokeW: 5,
    captionSize: 64,
    emphasisColor: '#FFE600',
  },
  youtuber: {
    topH: 290,
    vidH: 1320,
    botH: 310,
    titleColor: '#FFFFFF',
    titleSize: 72,
    captionColor: '#DC1E1E',
    captionStrokeColor: '#FFFFFF',
    captionStrokeW: 8,
    captionSize: 72,
    emphasisColor: '#FFE600',
  },
};

export const ROLE_ACCENT: Record<string, string> = {
  hook: '#FF5050',
  context: '#B4B4B4',
  body: '#FFFFFF',
  climax: '#FFD700',
  twist: '#B464FF',
  cta: '#FF8C00',
};
