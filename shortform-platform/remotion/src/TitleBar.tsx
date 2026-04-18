import React from 'react';
import {ThemeConfig} from './theme';

// 단어별 컬러링 (emphasis 단어는 노랑)
const HighlightText: React.FC<{text: string; emphasis?: string[]; color: string}> = ({
  text,
  emphasis = [],
  color,
}) => {
  const EMP = '#FFE600';
  const tokens = text.split(/(\s+|\n)/);
  return (
    <>
      {tokens.map((tk, i) => {
        if (tk === '\n') return <br key={i} />;
        const hit = emphasis.some((w) => w && tk.includes(w));
        return (
          <span key={i} style={{color: hit ? EMP : color}}>
            {tk}
          </span>
        );
      })}
    </>
  );
};

export const TitleBar: React.FC<{
  text: string;
  theme: ThemeConfig;
  width: number;
  emphasis?: string[];
}> = ({text, theme, width, emphasis = []}) => {
  // 단어 단위로 강조 (공백과 \n 보존)
  const renderTokens = () => {
    const lines = text.split('\n');
    return lines.map((line, li) => {
      const tokens = line.split(/(\s+)/);
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
          {li < lines.length - 1 && <br />}
        </React.Fragment>
      );
    });
  };

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
          fontFamily: '"Noto Sans CJK KR", "Noto Sans", sans-serif',
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
