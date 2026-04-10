/**
 * 숏폼 자동 생성 플랫폼 - 프론트엔드
 * FastAPI WebSocket으로 실시간 진행 상태를 수신합니다.
 */

const API = "";  // 같은 origin

// --- 상태 ---
let currentJobId = null;
let ws = null;
let currentTab = "youtube";

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

// --- 탭 전환 ---
document.querySelectorAll(".source-tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    currentTab = btn.dataset.tab;
    document.querySelectorAll(".source-tab").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");

    document.getElementById("tab-youtube").classList.toggle("hidden", currentTab !== "youtube");
    document.getElementById("tab-blog").classList.toggle("hidden", currentTab !== "blog");

    // YouTube 전용 옵션 표시/숨김
    document.querySelectorAll(".youtube-only").forEach(el => {
      el.style.display = currentTab === "youtube" ? "" : "none";
    });
  });
});

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

  if (currentTab === "youtube") {
    const url = document.getElementById("url").value.trim();
    if (!url) { alert("YouTube URL을 입력하세요."); return; }
    body.url          = url;
    body.vertical     = document.getElementById("vertical").checked;
    body.caption_mode = document.getElementById("caption_mode").value;
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

    // 업로드 버튼 이벤트
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
      const label = job.request?.url || job.request?.blog_url
        || (job.request?.blog_text ? job.request.blog_text.slice(0, 60) + "…" : null)
        || job.job_id;
      const srcIcon = job.request?.source_type === "blog" ? "📝 " : "📺 ";
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
loadHistory();
loadAccountStatus();
