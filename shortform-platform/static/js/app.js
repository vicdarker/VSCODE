/**
 * 숏폼 자동 생성 플랫폼 - 프론트엔드
 * FastAPI WebSocket으로 실시간 진행 상태를 수신합니다.
 */

const API = "";  // 같은 origin

// ─ 프리셋 카드 그리드 ────────────────────────────────────────────
const PRESET_STORAGE_KEY  = "shortform_selected_preset_v1";
const MY_PRESETS_KEY      = "shortform_my_presets_v1";
let  _allPresets          = [];   // [{id,name,description,vibe_moods,vibe_tones,thumbnail_url}, ...]

function getSelectedPreset() {
  return document.getElementById("theme_id")?.value || "viral_pill";
}

async function setSelectedPreset(id, opts = {}) {
  const th = document.getElementById("theme_id");
  if (th) th.value = id;
  localStorage.setItem(PRESET_STORAGE_KEY, id);
  document.querySelectorAll(".preset-card").forEach(c => {
    c.classList.toggle("selected", c.dataset.id === id);
  });
  // 프리셋 기본값을 UI 슬라이더에 주입 (커스터마이징 리셋)
  // opts.skipReset=true면 스킵 (예: 내 프리셋 snap 적용할 때)
  if (!opts.skipReset) {
    try {
      const r = await fetch(`/api/presets/${encodeURIComponent(id)}/config`);
      if (r.ok) {
        const cfg = await r.json();
        applyPresetConfigToForm(cfg);
      }
    } catch (e) { console.warn("preset config load fail", e); }
    // 내 프리셋에서 가져온 override는 리셋
    window.__userSnapOverrides = null;
  }
  if (typeof schedulePreview === "function") schedulePreview();
}

function applyPresetConfigToForm(cfg) {
  const setVal = (id, v) => {
    const el = document.getElementById(id);
    if (!el || v === undefined || v === null) return;
    if (el.type === "checkbox") el.checked = !!v;
    else el.value = String(v);
  };
  const layout = cfg.layout || {};
  setVal("lay-top", layout.top_h);
  setVal("lay-vid", layout.vid_h);
  setVal("lay-bot", layout.bot_h);
  const cap = cfg.caption || {};
  setVal("cap-area", cap.area);
  setVal("cap-size", cap.size);
  setVal("cap-font", cap.font_id || "");
  setVal("cap-color", cap.color_hex);
  setVal("cap-stroke", cap.stroke_w);
  const ttl = cfg.title || {};
  setVal("ttl-size", ttl.size);
  setVal("ttl-font", ttl.font_id || "");
  setVal("ttl-color", ttl.color_hex);
  setVal("ttl-accent", ttl.accent_last_line);
  setVal("ttl-accent-color", ttl.accent_color_hex);
  setVal("brand-text", cfg.fixed_bottom_text || "");
  const br = cfg.bottom_brand || {};
  setVal("brand-size", br.size);
  // 라벨 업데이트
  ["v-top","v-vid","v-bot","v-cap-size","v-cap-stroke","v-ttl-size","v-brand-size"].forEach(() => {});
  // 각 슬라이더의 input 이벤트 트리거 → 라벨 갱신
  ["lay-top","lay-vid","lay-bot","cap-size","cap-stroke","ttl-size","brand-size"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

function renderPresetCards(recommended = []) {
  const grid = document.getElementById("preset-grid");
  if (!grid) return;
  // 내 프리셋 불러와서 맨 뒤에 추가
  let myPresets = [];
  try { myPresets = JSON.parse(localStorage.getItem(MY_PRESETS_KEY) || "[]"); } catch {}

  const recSet = new Set(recommended);
  const items = _allPresets.map(p => ({ ...p, recommended: recSet.has(p.id) }));
  // 추천 프리셋 상단으로
  items.sort((a, b) => (b.recommended - a.recommended));
  // 내 프리셋 카드 추가 (카드에 source=user 표시)
  const myCards = myPresets.map(mp => ({
    id: `user:${mp.id}`,
    name: "💾 " + (mp.name || mp.id),
    description: "내 저장 프리셋",
    thumbnail_url: "",
    recommended: false,
    user: true, _saved: mp,
  }));

  const currentSel = getSelectedPreset();
  grid.innerHTML = [...items, ...myCards].map(p => {
    const sel = p.id === currentSel ? " selected" : "";
    const rec = p.recommended ? '<span class="badge-rec">매칭</span>' : "";
    const delBtn = p.user ? `<button type="button" class="preset-del" data-id="${p.id}" title="삭제">✕</button>` : "";
    const thumb = p.thumbnail_url
      ? `<img src="${p.thumbnail_url}?t=${Date.now()}" alt="${p.name}" loading="lazy" style="width:100%;aspect-ratio:9/16;object-fit:cover;border-radius:4px;background:#000">`
      : `<div style="width:100%;aspect-ratio:9/16;display:flex;align-items:center;justify-content:center;background:#222;border-radius:4px;color:#888;font-size:12px">커스텀</div>`;
    return `
      <div class="preset-card${sel}" data-id="${p.id}" data-user="${p.user ? 1 : 0}">
        ${rec}${delBtn}
        ${thumb}
        <div class="preset-card-name">${p.name}</div>
      </div>`;
  }).join("");

  // 클릭: 선택
  grid.querySelectorAll(".preset-card").forEach(card => {
    card.addEventListener("click", (e) => {
      // 삭제 버튼 클릭은 선택 이벤트로 전파시키지 않음
      if (e.target.classList.contains("preset-del")) return;
      const id = card.dataset.id;
      const isUser = card.dataset.user === "1";
      if (isUser) {
        const saved = myPresets.find(x => `user:${x.id}` === id);
        if (saved) {
          // base 테마는 폼 리셋 없이 적용 (다음 applyOverrideSnapshot이 값 주입)
          setSelectedPreset(saved.base_theme || "viral_pill", { skipReset: true });
          applyOverrideSnapshot(saved.snap || {});
          return;
        }
      }
      setSelectedPreset(id);
    });
  });

  // 삭제: 내 프리셋 카드의 ✕ 버튼
  grid.querySelectorAll(".preset-del").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const rawId = btn.dataset.id;                 // "user:<ts>"
      const origId = rawId.replace(/^user:/, "");
      const card = btn.closest(".preset-card");
      const name = card?.querySelector(".preset-card-name")?.textContent || "이 프리셋";
      if (!confirm(`'${name}' 삭제할까요?`)) return;
      let list = [];
      try { list = JSON.parse(localStorage.getItem(MY_PRESETS_KEY) || "[]"); } catch {}
      list = list.filter(mp => mp.id !== origId);
      localStorage.setItem(MY_PRESETS_KEY, JSON.stringify(list));
      renderPresetCards([]);
    });
  });
}

async function loadPresets() {
  try {
    const r = await fetch("/api/presets");
    const d = await r.json();
    _allPresets = d.presets || [];
    // 복원: localStorage에 저장된 선택
    const saved = localStorage.getItem(PRESET_STORAGE_KEY);
    if (saved && _allPresets.find(p => p.id === saved)) {
      setSelectedPreset(saved);
    }
    renderPresetCards([]);
  } catch (e) {
    console.warn("preset load fail", e);
  }
}
loadPresets();

// ─ 2축 필터 & 저장 버튼 바인딩 ────────────────────────────
function bindPresetControls() {
  const btnApplyVibe = document.getElementById("btn-apply-vibe");
  if (btnApplyVibe) btnApplyVibe.addEventListener("click", () => {
    const mood = document.getElementById("vibe-mood")?.value || "";
    const tone = document.getElementById("vibe-tone")?.value || "";
    // 클라이언트 필터링: vibe 태그 매칭 점수
    const scored = _allPresets.map(p => {
      let s = 0;
      if (mood && (p.vibe_moods || []).includes(mood)) s += 3;
      if (tone && (p.vibe_tones || []).includes(tone)) s += 2;
      return { id: p.id, score: s };
    }).filter(x => x.score > 0).sort((a, b) => b.score - a.score);
    const matched = scored.map(x => x.id);
    renderPresetCards(matched);
    if (matched[0]) setSelectedPreset(matched[0]);
  });

  const btnSave = document.getElementById("btn-save-preset");
  if (btnSave) btnSave.addEventListener("click", () => {
    const name = prompt("내 프리셋 이름:", "MY 프리셋");
    if (!name) return;
    const snap = (typeof collectThemeOverrides === "function") ? collectThemeOverrides() : null;
    let list = [];
    try { list = JSON.parse(localStorage.getItem(MY_PRESETS_KEY) || "[]"); } catch {}
    list.push({
      id: `${Date.now()}`, name,
      base_theme: getSelectedPreset(),
      snap,
      created_at: new Date().toISOString(),
    });
    localStorage.setItem(MY_PRESETS_KEY, JSON.stringify(list));
    renderPresetCards([]);
    alert(`'${name}' 저장 완료.`);
  });
}

function _rgbaArrayToHex(arr) {
  if (!arr || arr.length < 3) return "#ffffff";
  return "#" + arr.slice(0, 3).map(n => Math.max(0, Math.min(255, Number(n))).toString(16).padStart(2, "0")).join("");
}

function applyOverrideSnapshot(snap) {
  // 저장된 theme_overrides 형식을 UI 폼에 주입
  const setVal = (id, v) => {
    const el = document.getElementById(id);
    if (!el || v === undefined || v === null) return;
    if (el.type === "checkbox") el.checked = !!v;
    else el.value = String(v);
  };
  const lo = snap.layout || {};
  setVal("lay-top", lo.top_h); setVal("lay-vid", lo.vid_h); setVal("lay-bot", lo.bot_h);
  const cap = snap.caption || {};
  setVal("cap-area", cap.area); setVal("cap-size", cap.size); setVal("cap-font", cap.font_id || "");
  if (cap.color) setVal("cap-color", _rgbaArrayToHex(cap.color));
  setVal("cap-stroke", cap.stroke_w);
  const ttl = snap.title || {};
  setVal("ttl-size", ttl.size); setVal("ttl-font", ttl.font_id || "");
  if (ttl.color) setVal("ttl-color", _rgbaArrayToHex(ttl.color));
  setVal("ttl-accent", ttl.accent_last_line);
  if (ttl.accent_color) setVal("ttl-accent-color", _rgbaArrayToHex(ttl.accent_color));
  setVal("brand-text", snap.fixed_bottom_text);
  const br = snap.bottom_brand || {};
  setVal("brand-size", br.size);
  ["lay-top","lay-vid","lay-bot","cap-size","cap-stroke","ttl-size","brand-size"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.dispatchEvent(new Event("input", { bubbles: true }));
  });
  window.__userSnapOverrides = null;
  if (typeof schedulePreview === "function") schedulePreview();
}

bindPresetControls();

// --- 상태 ---
let currentJobId = null;
let ws = null;
let currentTab = "news";
let currentFormat = "mp4";

// --- DOM ---
const form          = document.getElementById("job-form");
const submitBtn     = document.getElementById("submit-btn");
const progressSec   = document.getElementById("progress-section");
const progressMsg   = document.getElementById("progress-message");
const progressPct   = document.getElementById("progress-pct");
const progressBar   = document.getElementById("progress-bar");
const statusBadge   = document.getElementById("status-badge");
const resultsSec    = document.getElementById("results-section");
const clipsGrid     = document.getElementById("clips-grid");
const historyList   = document.getElementById("history-list");

// --- 소스 탭 전환 ---
document.querySelectorAll(".source-tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    currentTab = btn.dataset.tab;
    document.querySelectorAll(".source-tab").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");

    document.getElementById("tab-youtube").classList.toggle("hidden", currentTab !== "youtube");
    document.getElementById("tab-blog").classList.toggle("hidden", currentTab !== "blog");
    document.getElementById("tab-news").classList.toggle("hidden", currentTab !== "news");

    updateOptionVisibility();
  });
});

function updateOptionVisibility() {
  document.querySelectorAll(".youtube-only").forEach(el => {
    el.style.display = currentTab === "youtube" ? "" : "none";
  });
}

// --- 폼 제출 ---
form.addEventListener("submit", async (e) => {
  e.preventDefault();

  let body = {
    source_type:    currentTab,
    clips:          Number(document.getElementById("clips").value),
    duration:       Number(document.getElementById("duration").value),
    style:          document.getElementById("style").value,
    make_thumbnail: document.getElementById("make_thumbnail").checked,
  };

  body.output_format = "mp4";

  if (currentTab === "youtube") {
    const url = document.getElementById("url").value.trim();
    if (!url) { alert("YouTube URL을 입력하세요."); return; }
    body.url = url;
    body.vertical     = document.getElementById("vertical").checked;
    body.caption_mode = document.getElementById("caption_mode").value;
  } else if (currentTab === "news") {
    const newsUrl  = document.getElementById("news_url").value.trim();
    const newsText = document.getElementById("news_text").value.trim();
    if (!newsUrl && !newsText) { alert("뉴스 URL 또는 본문을 입력하세요."); return; }
    body.news_url   = newsUrl;
    body.news_text  = newsText;
    body.news_title = document.getElementById("news_title").value.trim();
    const themeSel  = document.getElementById("theme_id");
    if (themeSel) body.theme_id = themeSel.value;
    const tts = document.getElementById("enable_tts");
    const bgm = document.getElementById("enable_bgm");
    const tr  = document.getElementById("enable_transitions");
    const tk  = document.getElementById("enable_ticker");
    const tp  = document.getElementById("tts_provider");
    const tv  = document.getElementById("tts_voice");
    if (tts) body.enable_tts = tts.checked;
    if (bgm) body.enable_bgm = bgm.checked;
    if (tr)  body.enable_transitions = tr.checked;
    if (tk)  body.enable_ticker = tk.checked;
    const hs = document.getElementById("enable_highlight_stat");
    if (hs) body.enable_highlight_stat = hs.checked;
    if (tp)  body.tts_provider = tp.value;
    if (tv)  body.tts_voice = tv.value;
    // 커스터마이징 오버라이드 (저장된 내 프리셋 snap이 있으면 우선 적용)
    const ov = collectThemeOverrides();
    const userSnap = window.__userSnapOverrides;
    body.theme_overrides = userSnap ? { ...ov, ...userSnap } : ov;
    body.theme_id = getSelectedPreset();
  } else {
    const blogUrl  = document.getElementById("blog_url").value.trim();
    const blogText = document.getElementById("blog_text").value.trim();
    if (!blogUrl && !blogText) { alert("블로그 URL 또는 텍스트를 입력하세요."); return; }
    body.blog_url  = blogUrl;
    body.blog_text = blogText;
  }

  submitBtn.disabled = true;
  submitBtn.textContent = "처리 중...";
  resultsSec.classList.add("hidden");
  clipsGrid.innerHTML = "";

  try {
    const res  = await fetch(`${API}/api/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const job = await res.json();
    startJob(job.job_id);
  } catch (err) {
    alert("서버 오류: " + err.message);
    resetSubmit();
  }
});

// --- 작업 시작: WebSocket 연결 ---
function startJob(jobId) {
  currentJobId = jobId;

  // 진행 UI 표시
  progressSec.classList.remove("hidden");
  setProgress("pending", 0, "대기 중...");

  // 기존 소켓 정리
  if (ws) ws.close();

  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/${jobId}`);

  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    handleEvent(msg.event, msg.data);
  };

  ws.onclose = () => {
    // 소켓 끊겼을 때 폴링으로 최종 상태 확인
    setTimeout(() => pollJob(jobId), 1000);
  };
}

function handleEvent(event, data) {
  if (event === "progress") {
    setProgress(data.status, data.progress, data.message);
  } else if (event === "done") {
    setProgress("done", 100, "완료!");
    renderClips(data.clips, currentJobId);
    resetSubmit();
    loadHistory();
  } else if (event === "error") {
    setProgress("failed", 0, "실패: " + data.message);
    resetSubmit();
  }
}

async function pollJob(jobId) {
  try {
    const res = await fetch(`${API}/api/jobs/${jobId}`);
    const job = await res.json();
    setProgress(job.status, job.progress, job.message);
    if (job.status === "done") {
      renderClips(job.clips, jobId);
      resetSubmit();
      loadHistory();
    } else if (job.status === "failed") {
      resetSubmit();
    }
  } catch (_) {}
}

// --- UI 업데이트 ---
function setProgress(status, pct, message) {
  progressMsg.textContent = message;
  progressPct.textContent = pct + "%";
  progressBar.style.width = pct + "%";
  statusBadge.textContent = status;
  statusBadge.className = `badge badge-${status}`;
}

function renderClips(clips, jobId) {
  resultsSec.classList.remove("hidden");
  clipsGrid.innerHTML = "";

  clips.forEach((clip) => {
    const card = document.createElement("div");
    card.className = "clip-card";
    const duration = (clip.end - clip.start).toFixed(0);
    const tags = clip.hashtags.map(t => `<span class="clip-tag">${t}</span>`).join("");

    card.innerHTML = `
      <video src="${clip.video_url}" controls playsinline poster="${clip.thumbnail_url ?? ''}"></video>
      <div class="clip-info">
        <div class="clip-hook">${clip.hook}</div>
        <div class="clip-meta">Clip ${clip.index} &bull; ${duration}초 (${fmtTime(clip.start)} ~ ${fmtTime(clip.end)})</div>
        <div class="clip-tags">${tags}</div>
        <div class="clip-actions">
          <a class="clip-download" href="${clip.video_url}" download>영상</a>
          ${clip.thumbnail_url ? `<a class="clip-download" href="${clip.thumbnail_url}" download>썸네일</a>` : ""}
        </div>
        <div class="publish-row">
          <label class="pub-label"><input type="checkbox" class="pub-yt" checked /> YouTube</label>
          <label class="pub-label"><input type="checkbox" class="pub-tt" /> TikTok</label>
          <button id="publish-btn-${clip.index}" class="publish-btn">업로드</button>
        </div>
      </div>
    `;

    if (jobId) {
      card.querySelector(`#publish-btn-${clip.index}`).addEventListener("click", () => {
        const platforms = [];
        if (card.querySelector(".pub-yt").checked) platforms.push("youtube");
        if (card.querySelector(".pub-tt").checked) platforms.push("tiktok");
        if (platforms.length === 0) return alert("플랫폼을 선택하세요.");
        publishClip(jobId, clip.index, platforms);
      });
    }

    clipsGrid.appendChild(card);
  });
}

function fmtTime(sec) {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function resetSubmit() {
  submitBtn.disabled = false;
  submitBtn.textContent = "생성 시작";
}

// --- 히스토리 ---
async function loadHistory() {
  try {
    const res  = await fetch(`${API}/api/jobs`);
    const jobs = await res.json();
    historyList.innerHTML = "";

    jobs.slice(0, 10).forEach((job) => {
      const item = document.createElement("div");
      item.className = "history-item";
      const label = job.request?.url || job.request?.news_url || job.request?.blog_url
        || (job.request?.news_title ? job.request.news_title : null)
        || (job.request?.news_text ? job.request.news_text.slice(0, 60) + "…" : null)
        || (job.request?.blog_text ? job.request.blog_text.slice(0, 60) + "…" : null)
        || job.job_id;
      const srcIcon = job.request?.source_type === "blog" ? "📝 "
                    : job.request?.source_type === "news" ? "📰 " : "📺 ";
      item.innerHTML = `
        <span class="history-url">${srcIcon}${label}</span>
        <span class="history-right">
          <span class="badge badge-${job.status}">${job.status}</span>
          <span>${job.clips.length}개 클립</span>
        </span>
      `;
      item.addEventListener("click", () => {
        if (job.status === "done") {
          resultsSec.classList.remove("hidden");
          renderClips(job.clips, job.job_id);
          window.scrollTo({ top: resultsSec.offsetTop, behavior: "smooth" });
        }
      });
      historyList.appendChild(item);
    });
  } catch (_) {}
}

// ── 계정 연결 상태 ──────────────────────────────────────────────────────

async function loadAccountStatus() {
  try {
    const res  = await fetch(`${API}/api/publish/status`);
    const data = await res.json();

    setAccountDot("yt-status", data.youtube);
    setAccountDot("tt-status", data.tiktok);

    if (data.youtube) document.getElementById("yt-connect-btn").textContent = "YouTube 연결됨";
    if (data.tiktok)  document.getElementById("tt-connect-btn").textContent = "TikTok 연결됨";
  } catch (_) {}
}

function setAccountDot(id, connected) {
  const el = document.getElementById(id);
  el.textContent = connected ? "●" : "○";
  el.style.color = connected ? "#6bcb77" : "#666";
}

// ── 클립 업로드 ──────────────────────────────────────────────────────────

async function publishClip(jobId, clipIndex, platforms) {
  const btn = document.getElementById(`publish-btn-${clipIndex}`);
  btn.disabled = true;
  btn.textContent = "업로드 중...";

  try {
    const res  = await fetch(`${API}/api/publish/${jobId}/${clipIndex}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ platforms }),
    });
    const data = await res.json();

    const lines = [];
    for (const [platform, info] of Object.entries(data.results || {})) {
      lines.push(`${platform}: <a href="${info.url}" target="_blank">보기</a>`);
    }
    for (const [platform, err] of Object.entries(data.errors || {})) {
      lines.push(`${platform} 실패: ${err}`);
    }

    btn.insertAdjacentHTML("afterend",
      `<div class="publish-result">${lines.join("<br>")}</div>`
    );
    btn.remove();
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "업로드 재시도";
    alert("업로드 실패: " + err.message);
  }
}

// 페이지 로드 시 히스토리 + 계정 상태
updateOptionVisibility();
loadHistory();
loadAccountStatus();

// ─────────────────────────────────────────────────────────────
// 자막/레이아웃 커스터마이징 패널 로직
// ─────────────────────────────────────────────────────────────

const CUSTOMIZE_STORAGE_KEY = "shortform_theme_customize_v1";

// 16진 → [r,g,b,255]
function hexToRgba(hex) {
  const h = hex.replace("#", "");
  return [parseInt(h.slice(0,2),16), parseInt(h.slice(2,4),16), parseInt(h.slice(4,6),16), 255];
}

// 폼 → theme_overrides 객체
function collectThemeOverrides() {
  const $ = id => document.getElementById(id);
  if (!$("cap-area")) return null;  // 패널 미로드
  const top_h = Number($("lay-top").value);
  const vid_h = Number($("lay-vid").value);
  const bot_h = Number($("lay-bot").value);
  return {
    layout: { top_h, vid_h, bot_h },
    title: {
      size: Number($("ttl-size").value),
      font_id: $("ttl-font").value || undefined,
      color: hexToRgba($("ttl-color").value),
      accent_last_line: $("ttl-accent").checked,
      accent_color: hexToRgba($("ttl-accent-color").value),
    },
    caption: {
      area: $("cap-area").value,
      size: Number($("cap-size").value),
      font_id: $("cap-font").value || undefined,
      color: hexToRgba($("cap-color").value),
      stroke_w: Number($("cap-stroke").value),
    },
    fixed_bottom_text: $("brand-text").value,
    bottom_brand: {
      size: Number($("brand-size").value),
    },
  };
}

// 상태 → 로컬스토리지 저장
function saveCustomize() {
  const snap = {};
  [
    "lay-top","lay-vid","lay-bot",
    "cap-area","cap-size","cap-font","cap-color","cap-stroke",
    "ttl-size","ttl-font","ttl-color","ttl-accent","ttl-accent-color",
    "brand-text","brand-size",
  ].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    snap[id] = el.type === "checkbox" ? el.checked : el.value;
  });
  localStorage.setItem(CUSTOMIZE_STORAGE_KEY, JSON.stringify(snap));
}

// 로컬스토리지 → 상태 복원
function loadCustomize() {
  try {
    const snap = JSON.parse(localStorage.getItem(CUSTOMIZE_STORAGE_KEY) || "{}");
    Object.entries(snap).forEach(([id, v]) => {
      const el = document.getElementById(id);
      if (!el) return;
      if (el.type === "checkbox") el.checked = v;
      else el.value = v;
    });
  } catch {}
}

// 슬라이더 값 라이브 라벨 업데이트
function bindLabel(inputId, labelId) {
  const i = document.getElementById(inputId), l = document.getElementById(labelId);
  if (!i || !l) return;
  const update = () => { l.textContent = i.value; };
  i.addEventListener("input", update); update();
}

// 프리뷰 디바운스 호출
let previewTimer = null;
async function schedulePreview() {
  const st  = document.getElementById("customize-status");
  const st2 = document.getElementById("customize-status-mirror");
  const setStatus = (t) => { if (st) st.textContent = t; if (st2) st2.textContent = t; };
  setStatus("갱신 중...");
  clearTimeout(previewTimer);
  previewTimer = setTimeout(async () => {
    try {
      const theme_id = document.getElementById("theme_id").value;
      const body = { theme_id, theme_overrides: collectThemeOverrides() };
      const res = await fetch("/api/preview-layout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        let detail = "";
        try { detail = (await res.text()).slice(0, 200); } catch {}
        throw new Error("preview " + res.status + " " + detail);
      }
      const blob = await res.blob();
      const img = document.getElementById("layout-preview");
      if (img) img.src = URL.createObjectURL(blob);
      setStatus("");
    } catch (e) {
      setStatus("미리보기 실패: " + e.message);
    }
    saveCustomize();
  }, 300);
}

// 레이아웃 슬라이더: 합=1920 유지
function enforceLayoutSum(changedId) {
  const top = document.getElementById("lay-top");
  const vid = document.getElementById("lay-vid");
  const bot = document.getElementById("lay-bot");
  if (!top || !vid || !bot) return;
  const H = 1920;
  const sum = Number(top.value) + Number(vid.value) + Number(bot.value);
  if (sum === H) return;
  // 바뀌지 않은 두 슬라이더에서 차이 분배
  const diff = H - sum;
  const others = ["lay-top","lay-vid","lay-bot"].filter(x => x !== changedId);
  for (const id of others) {
    const el = document.getElementById(id);
    const nv = Math.max(0, Number(el.value) + Math.round(diff / others.length));
    el.value = String(nv);
  }
  bindLabel("lay-top","v-top"); bindLabel("lay-vid","v-vid"); bindLabel("lay-bot","v-bot");
}

// 초기화
async function initCustomize() {
  if (!document.getElementById("cap-area")) return;
  // 폰트 목록
  try {
    const res = await fetch("/api/fonts");
    const data = await res.json();
    const opts = (data.fonts || []).map(f => `<option value="${f.id}">${f.name}</option>`).join("");
    const cap = document.getElementById("cap-font");
    const ttl = document.getElementById("ttl-font");
    if (cap) cap.innerHTML = `<option value="">(테마 기본)</option>` + opts;
    if (ttl) ttl.innerHTML = `<option value="">(테마 기본)</option>` + opts;
  } catch {}

  loadCustomize();

  // 모든 컨트롤 change → 프리뷰
  [
    "lay-top","lay-vid","lay-bot",
    "cap-area","cap-size","cap-font","cap-color","cap-stroke",
    "ttl-size","ttl-font","ttl-color","ttl-accent","ttl-accent-color",
    "brand-text","brand-size",
    "theme_id",
  ].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    const ev = (el.type === "range" || el.type === "color" || el.tagName === "SELECT" || el.type === "checkbox")
      ? "input" : "change";
    el.addEventListener(ev, () => {
      if (id.startsWith("lay-")) enforceLayoutSum(id);
      schedulePreview();
    });
  });

  // 슬라이더 라벨
  bindLabel("lay-top","v-top"); bindLabel("lay-vid","v-vid"); bindLabel("lay-bot","v-bot");
  bindLabel("cap-size","v-cap-size"); bindLabel("cap-stroke","v-cap-stroke");
  bindLabel("ttl-size","v-ttl-size"); bindLabel("brand-size","v-brand-size");

  // 리셋 버튼
  const reset = document.getElementById("reset-customize");
  if (reset) reset.addEventListener("click", () => {
    localStorage.removeItem(CUSTOMIZE_STORAGE_KEY);
    location.reload();
  });

  // 패널 열릴 때 첫 프리뷰
  const panel = document.querySelector(".customize-panel");
  if (panel) panel.addEventListener("toggle", () => { if (panel.open) schedulePreview(); });

  // 최초 1회 미리보기
  schedulePreview();
}

initCustomize();
