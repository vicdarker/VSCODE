import React from 'react';
import {ThemeConfig} from './theme';
import {resolveFontFamily} from './fonts';

export const TitleBar: React.FC<{
  text: string;
  theme: ThemeConfig;
  width: number;
  emphasis?: string[];
  accentLastLine?: boolean;
  accentColor?: string;
  fontId?: string;
}> = ({text, theme, width, emphasis = [], accentLastLine = false, accentColor, fontId}) => {
  const lines = text.split('\n');
  const lastIdx = lines.length - 1;
  const emphColor = accentColor || theme.emphasisColor;

  const renderTokens = () =>
    lines.map((line, li) => {
      const tokens = line.split(/(\s+)/);
      // accentLastLine 모드: 마지막 줄은 accentColor로 통째로
      if (accentLastLine && li === lastIdx && lines.length >= 2) {
        return (
          <React.Fragment key={li}>
            <span style={{color: emphColor}}>{line}</span>
            {li < lastIdx && <br />}
          </React.Fragment>
        );
      }
      return (
        <React.Fragment key={li}>
          {tokens.map((tk, i) => {
            const hit = emphasis.some((w) => w && tk.includes(w));
            return (
              <span
                key={i}
                style={{color: hit ? theme.emphasisColor : theme.titleColor}}
              >
                {tk}
              </span>
            );
          })}
          {li < lastIdx && <br />}
        </React.Fragment>
      );
    });

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width,
        height: theme.topH,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        textAlign: 'center',
        backgroundColor: 'black',
        zIndex: 50,
      }}
    >
      <div
        style={{
          fontFamily: resolveFontFamily(fontId),
          fontWeight: 900,
          fontSize: theme.titleSize,
          lineHeight: 1.15,
          padding: '0 40px',
        }}
      >
        {renderTokens()}
      </div>
    </div>
  );
};
