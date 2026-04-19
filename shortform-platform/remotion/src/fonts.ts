// Google Fonts를 Remotion 렌더에서 실제로 사용할 수 있게 로드.
// font_id (PIL 쪽 FONT_REGISTRY와 매칭) → CSS fontFamily 문자열.
import {loadFont as loadBlackHanSans} from '@remotion/google-fonts/BlackHanSans';
import {loadFont as loadJua} from '@remotion/google-fonts/Jua';
import {loadFont as loadDoHyeon} from '@remotion/google-fonts/DoHyeon';
import {loadFont as loadGasoekOne} from '@remotion/google-fonts/GasoekOne';
import {loadFont as loadGugi} from '@remotion/google-fonts/Gugi';
import {loadFont as loadNanumGothic} from '@remotion/google-fonts/NanumGothic';
import {loadFont as loadNanumMyeongjo} from '@remotion/google-fonts/NanumMyeongjo';
import {loadFont as loadNanumPenScript} from '@remotion/google-fonts/NanumPenScript';
import {loadFont as loadNanumBrushScript} from '@remotion/google-fonts/NanumBrushScript';
import {loadFont as loadNotoSansKR} from '@remotion/google-fonts/NotoSansKR';
import {loadFont as loadNotoSerifKR} from '@remotion/google-fonts/NotoSerifKR';
// 추가 Google Fonts Korean
import {loadFont as loadBagelFatOne} from '@remotion/google-fonts/BagelFatOne';
import {loadFont as loadCuteFont} from '@remotion/google-fonts/CuteFont';
import {loadFont as loadDokdo} from '@remotion/google-fonts/Dokdo';
import {loadFont as loadDongle} from '@remotion/google-fonts/Dongle';
import {loadFont as loadEastSeaDokdo} from '@remotion/google-fonts/EastSeaDokdo';
import {loadFont as loadGaegu} from '@remotion/google-fonts/Gaegu';
import {loadFont as loadGamjaFlower} from '@remotion/google-fonts/GamjaFlower';
import {loadFont as loadGowunBatang} from '@remotion/google-fonts/GowunBatang';
import {loadFont as loadGowunDodum} from '@remotion/google-fonts/GowunDodum';
import {loadFont as loadHahmlet} from '@remotion/google-fonts/Hahmlet';
import {loadFont as loadHiMelody} from '@remotion/google-fonts/HiMelody';
import {loadFont as loadIBMPlexSansKR} from '@remotion/google-fonts/IBMPlexSansKR';
import {loadFont as loadKirangHaerang} from '@remotion/google-fonts/KirangHaerang';
import {loadFont as loadPoorStory} from '@remotion/google-fonts/PoorStory';
import {loadFont as loadSingleDay} from '@remotion/google-fonts/SingleDay';
import {loadFont as loadSongMyung} from '@remotion/google-fonts/SongMyung';
import {loadFont as loadStylish} from '@remotion/google-fonts/Stylish';
import {loadFont as loadSunflower} from '@remotion/google-fonts/Sunflower';
import {loadFont as loadYeonSung} from '@remotion/google-fonts/YeonSung';

// 모듈 로드 시 한 번만 실행 → Remotion 렌더러가 폰트 다운로드 완료까지 자동 대기
const blackHanSans = loadBlackHanSans().fontFamily;
const jua = loadJua().fontFamily;
const doHyeon = loadDoHyeon().fontFamily;
const gasoekOne = loadGasoekOne().fontFamily;
const gugi = loadGugi().fontFamily;
const nanumGothic700 = loadNanumGothic('normal', {weights: ['700']}).fontFamily;
const nanumGothic800 = loadNanumGothic('normal', {weights: ['800']}).fontFamily;
const nanumMyeongjo700 = loadNanumMyeongjo('normal', {weights: ['700']}).fontFamily;
const nanumMyeongjo800 = loadNanumMyeongjo('normal', {weights: ['800']}).fontFamily;
const nanumPen = loadNanumPenScript().fontFamily;
const nanumBrush = loadNanumBrushScript().fontFamily;
const notoSansKR = loadNotoSansKR('normal', {weights: ['900']}).fontFamily;
const notoSerifKR = loadNotoSerifKR('normal', {weights: ['900']}).fontFamily;
// 추가 Google Fonts Korean
const bagelFatOne = loadBagelFatOne().fontFamily;
const cuteFont = loadCuteFont().fontFamily;
const dokdo = loadDokdo().fontFamily;
const dongle = loadDongle('normal', {weights: ['700']}).fontFamily;
const eastSeaDokdo = loadEastSeaDokdo().fontFamily;
const gaegu = loadGaegu('normal', {weights: ['700']}).fontFamily;
const gamjaFlower = loadGamjaFlower().fontFamily;
const gowunBatang = loadGowunBatang('normal', {weights: ['700']}).fontFamily;
const gowunDodum = loadGowunDodum().fontFamily;
const hahmlet = loadHahmlet('normal', {weights: ['700']}).fontFamily;
const hiMelody = loadHiMelody().fontFamily;
const ibmPlexSansKR = loadIBMPlexSansKR('normal', {weights: ['700']}).fontFamily;
const kirangHaerang = loadKirangHaerang().fontFamily;
const poorStory = loadPoorStory().fontFamily;
const singleDay = loadSingleDay().fontFamily;
const songMyung = loadSongMyung().fontFamily;
const stylish = loadStylish().fontFamily;
const sunflower = loadSunflower('normal', {weights: ['700']}).fontFamily;
const yeonSung = loadYeonSung().fontFamily;

// Pretendard는 Google Fonts 미제공 — NotoSansKR로 폴백 (둘 다 현대 한글 고딕)
// Weight별 미세 차이는 Remotion 렌더에서 반영 안 됨(PIL 프리뷰에서만 정확)
const pretendardFallback900 = loadNotoSansKR('normal', {weights: ['900']}).fontFamily;
const pretendardFallback700 = loadNotoSansKR('normal', {weights: ['700']}).fontFamily;
const pretendardFallback500 = loadNotoSansKR('normal', {weights: ['500']}).fontFamily;
const pretendardFallback400 = loadNotoSansKR('normal', {weights: ['400']}).fontFamily;
const pretendardFallback300 = loadNotoSansKR('normal', {weights: ['300']}).fontFamily;
const pretendardFallback200 = loadNotoSansKR('normal', {weights: ['200']}).fontFamily;
const pretendardFallback100 = loadNotoSansKR('normal', {weights: ['100']}).fontFamily;

export const FONT_BY_ID: Record<string, string> = {
  // Pretendard 9 weights — Remotion은 Noto Sans KR 해당 weight로 폴백
  pretendard_thin: pretendardFallback100,
  pretendard_extralight: pretendardFallback200,
  pretendard_light: pretendardFallback300,
  pretendard_regular: pretendardFallback400,
  pretendard_medium: pretendardFallback500,
  pretendard_semibold: pretendardFallback700,
  pretendard_bold: pretendardFallback700,
  pretendard_extrabold: pretendardFallback900,
  pretendard_black: pretendardFallback900,
  // 배민 시리즈 — Google Fonts 미제공 → 근접 폴백
  bm_dohyeon: doHyeon,                    // Do Hyeon이 배민 도현의 원본
  bm_jua: jua,                            // Jua가 배민 주아의 원본
  bm_hanna: blackHanSans,                 // Black Han Sans가 배민 한나의 원본
  bm_yeonsung: yeonSung,                  // Yeon Sung이 배민 연성의 원본
  bm_euljiro: gasoekOne,                  // 을지로체 ≈ 임팩트 굵은체
  // 여기어때 잘난체 — Google Fonts 미제공, 초굵 블록체 → BlackHanSans 폴백
  jalnan_gothic: blackHanSans,
  // Cafe24 시리즈 — Google Fonts 미제공 → 근접 폴백
  cafe24_dangdanghae: blackHanSans,
  cafe24_ssurround: jua,
  cafe24_ohsquare: doHyeon,
  cafe24_syongsyong: gaegu,
  // 산세리프 (고딕)
  noto_sans_bold: notoSansKR,
  nanum_gothic_b: nanumGothic700,
  nanum_gothic_extra_b: nanumGothic800,
  nanum_barun_gothic_b: nanumGothic700,    // BarunGothic은 Google 미제공 → NanumGothic 폴백
  nanum_square_eb: nanumGothic800,         // NanumSquare는 Google 미제공
  nanum_square_round_eb: nanumGothic800,   // NanumSquareRound도 미제공
  // 임팩트
  black_han_sans: blackHanSans,
  gasoek_one: gasoekOne,
  // 둥글고 캐주얼
  jua,
  do_hyeon: doHyeon,
  // 손글씨
  gugi,
  nanum_pen: nanumPen,
  nanum_barunpen_b: nanumPen,              // Barunpen은 미제공 → NanumPen 폴백
  nanum_brush: nanumBrush,
  // 명조
  nanum_myeongjo_b: nanumMyeongjo700,
  nanum_myeongjo_eb: nanumMyeongjo800,
  noto_serif_bold: notoSerifKR,
  // ─ 추가 Google Fonts Korean ─
  bagel_fat_one: bagelFatOne,
  cute_font: cuteFont,
  dokdo: dokdo,
  dongle: dongle,
  east_sea_dokdo: eastSeaDokdo,
  gaegu: gaegu,
  gamja_flower: gamjaFlower,
  gowun_batang: gowunBatang,
  gowun_dodum: gowunDodum,
  hahmlet: hahmlet,
  hi_melody: hiMelody,
  ibm_plex_sans_kr: ibmPlexSansKR,
  kirang_haerang: kirangHaerang,
  poor_story: poorStory,
  single_day: singleDay,
  song_myung: songMyung,
  stylish: stylish,
  sunflower: sunflower,
  yeon_sung: yeonSung,
};

export const DEFAULT_FONT = notoSansKR;

export function resolveFontFamily(fontId?: string): string {
  if (!fontId) return DEFAULT_FONT;
  return FONT_BY_ID[fontId] || DEFAULT_FONT;
}
