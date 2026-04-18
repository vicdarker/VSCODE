import {Config} from '@remotion/cli/config';

Config.setVideoImageFormat('jpeg');
Config.setOverwriteOutput(true);
// 모든 CPU 코어 사용 (null) — 4~8배 빨라짐
Config.setConcurrency(null);
// h264 코덱 최적화
Config.setCodec('h264');
