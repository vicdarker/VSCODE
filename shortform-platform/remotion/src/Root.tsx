import {Composition} from 'remotion';
import {NewsShort} from './NewsShort';
import {NewsProps} from './types';

const DEFAULT_PROPS: NewsProps = {
  hookPhrase: '이란 한 마디에\n월가가 폭발했다',
  fps: 30,
  segments: [
    {
      mediaPath: '',
      caption: '이란이 한마디 한 거예요',
      captionChunks: ['이란이 한마디에', '월가가 터졌다'],
      emphasisWords: ['월가'],
      highlightStat: '',
      reactionEmoji: '💥',
      role: 'hook',
      duration: 3,
    },
  ],
};

export const Root: React.FC = () => {
  return (
    <>
      <Composition
        id="NewsShort"
        component={NewsShort as React.FC<Record<string, unknown>>}
        durationInFrames={90}                 // 동적: 외부에서 override
        fps={30}
        width={1080}
        height={1920}
        defaultProps={DEFAULT_PROPS as unknown as Record<string, unknown>}
        calculateMetadata={({props}) => {
          const p = props as unknown as NewsProps;
          const total = p.segments.reduce((a, s) => a + s.duration, 0);
          return {
            durationInFrames: Math.max(1, Math.round(total * (p.fps || 30))),
            fps: p.fps || 30,
          };
        }}
      />
    </>
  );
};
