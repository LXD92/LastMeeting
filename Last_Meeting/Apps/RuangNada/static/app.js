const $ = (selector) => document.querySelector(selector);
const formats = {
  audio: ["mp3", "wav", "flac", "m4a", "aac", "opus", "ogg"],
  video: ["mp4", "webm", "mkv", "mov"],
};
const labels = {
  queued: "Menunggu antrean",
  running: "Sedang diproses",
  completed: "Selesai",
  failed: "Gagal",
  cancelled: "Dibatalkan",
};
const stages = {
  queued: "Menunggu antrean",
  validating: "Memvalidasi URL",
  downloading: "Mengunduh media",
  converting: "Mengonversi format",
  processing: "Memproses gambar",
  preparing: "Menyiapkan file",
  completed: "Selesai",
  failed: "Gagal",
  cancelled: "Dibatalkan",
};
let currentKind = "audio";
let analyzedMedia = null;
let currentJobId = null;
let pollTimer = null;
let toastTimer = null;

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.add("hidden"), 3600);
}

async function api(url, options = {}) {
  let response;
  try {
    response = await fetch(url, options);
  } catch {
    throw new Error("Server tidak dapat dijangkau. Pastikan aplikasi berjalan di VS Code.");
  }
  const data = response.headers.get("content-type")?.includes("application/json")
    ? await response.json()
    : null;
  if (!response.ok) throw new Error(data?.detail || "Permintaan gagal. Coba lagi.");
  return data;
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds)) return "Durasi tidak tersedia";
  const total = Math.floor(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}` : `${minutes}:${String(secs).padStart(2, "0")}`;
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function optionsChanged() {
  const isImage = currentKind === "image";
  const isVideo = currentKind === "video";
  const format = $("#format-select").value;
  const mp3Vbr = currentKind === "audio" && format === "mp3" && $("#mode-select").value === "vbr";
  $("#url-settings").classList.toggle("hidden", isImage);
  $("#image-settings").classList.toggle("hidden", !isImage);
  $("#video-quality-field").classList.toggle("hidden", !isVideo);
  $("#preset-field").classList.toggle("hidden", isVideo || isImage || format === "wav");
  $("#bitrate-field").classList.toggle("hidden", isVideo || isImage || mp3Vbr || !["mp3", "m4a", "aac", "opus"].includes(format));
  $("#bitrate-label").textContent = format === "mp3" ? "Bitrate MP3 (CBR)" : `Bitrate ${format.toUpperCase()}`;
  $("#sample-rate-field").classList.toggle("hidden", isVideo || isImage);
  $("#channels-field").classList.toggle("hidden", isVideo || isImage);
  $("#mode-field").classList.toggle("hidden", isVideo || isImage || format !== "mp3");
  const showEncoderQuality = !isVideo && !isImage && (format === "ogg" || format === "flac" || mp3Vbr);
  $("#encoder-quality-field").classList.toggle("hidden", !showEncoderQuality);
  if (showEncoderQuality) {
    const quality = $("#encoder-quality-select");
    const qualityMode = mp3Vbr ? "mp3-vbr" : format;
    if (quality.dataset.qualityMode !== qualityMode) {
      quality.dataset.qualityMode = qualityMode;
      quality.replaceChildren();
      const options = mp3Vbr
        ? Array.from({ length: 10 }, (_, value) => ({ value, label: `${value} · ${value < 3 ? "tertinggi" : value < 6 ? "tinggi" : "lebih kecil"}` }))
        : format === "flac"
          ? [0, 5, 8, 12].map((value) => ({ value, label: `${value} · ${value < 5 ? "cepat" : value < 10 ? "seimbang" : "kompresi tinggi"}` }))
          : [-1, 0, 3, 5, 7, 9, 10].map((value) => ({ value, label: `${value} · ${value < 3 ? "kecil" : value < 7 ? "seimbang" : "tinggi"}` }));
      options.forEach(({ value, label }) => {
        const option = document.createElement("option");
        option.value = String(value);
        option.textContent = label;
        quality.append(option);
      });
      quality.value = mp3Vbr ? "4" : "5";
    }
    $("#encoder-quality-label").textContent = mp3Vbr
      ? "Kualitas VBR MP3"
      : format === "flac" ? "Kompresi FLAC (lossless)" : "Kualitas encoder OGG";
  }
  $("#quality-note").textContent = format === "wav"
    ? "WAV menggunakan PCM; sample rate dan kanal menentukan resolusi hasil."
    : "Bitrate lebih tinggi tidak menambah detail yang sudah hilang dari sumber audio terkompresi.";
  $("#quality-note").classList.toggle("hidden", isVideo || isImage);
  $("#start-button").disabled = isImage ? !$("#image-file").files.length : !analyzedMedia;
}

function populateFormats() {
  const select = $("#format-select");
  select.replaceChildren();
  for (const format of formats[currentKind] || formats.audio) {
    const option = document.createElement("option");
    option.value = format;
    option.textContent = format.toUpperCase();
    select.append(option);
  }
  if (currentKind === "audio") {
    const savedFormat = localStorage.getItem("ruangnada-format");
    if ([...select.options].some((option) => option.value === savedFormat)) select.value = savedFormat;
  }
  optionsChanged();
}

function restoreSelect(selector, key) {
  const select = $(selector);
  const value = localStorage.getItem(key);
  if ([...select.options].some((option) => option.value === value)) select.value = value;
}

function saveSelect(selector, key) {
  localStorage.setItem(key, $(selector).value);
}

function renderMetadata(data) {
  analyzedMedia = data;
  $("#media-title").textContent = data.title || "Judul tidak tersedia";
  const details = [
    data.uploader,
    formatDuration(data.duration),
    data.source_format ? `Sumber ${data.source_format.toUpperCase()}` : null,
    data.source_size ? formatBytes(data.source_size) : null,
  ].filter(Boolean);
  $("#media-meta").textContent = details.join(" · ");
  const image = $("#thumbnail");
  if (data.thumbnail) {
    image.src = data.thumbnail;
    image.classList.remove("hidden");
    image.onerror = () => image.classList.add("hidden");
  } else {
    image.classList.add("hidden");
  }
  $("#media-card").classList.remove("hidden");
  const heights = data.available_heights || [];
  const quality = $("#video-quality-select");
  quality.replaceChildren();
  const automatic = document.createElement("option");
  automatic.value = "0";
  automatic.textContent = "Otomatis";
  quality.append(automatic);
  heights.forEach((height) => {
    const option = document.createElement("option");
    option.value = String(height);
    option.textContent = `${height}p`;
    quality.append(option);
  });
  optionsChanged();
}

$("#analyze-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const url = $("#media-url").value.trim();
  const message = $("#analyze-message");
  const button = $("#analyze-button");
  message.classList.add("hidden");
  if (!/^https:\/\/(www\.|music\.)?(youtube\.com|youtu\.be)\//i.test(url)) {
    message.textContent = "Masukkan tautan HTTPS video YouTube yang valid.";
    message.classList.remove("hidden");
    message.classList.add("error");
    return;
  }
  button.disabled = true;
  button.querySelector("span").textContent = "Menganalisis...";
  try {
    const data = await api("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    renderMetadata(data);
    message.classList.add("hidden");
    showToast("Informasi media berhasil diambil.");
  } catch (error) {
    analyzedMedia = null;
    optionsChanged();
    message.textContent = error.message;
    message.classList.remove("hidden");
    message.classList.add("error");
  } finally {
    button.disabled = false;
    button.querySelector("span").textContent = "Analisis media";
  }
});

$("#paste-button").addEventListener("click", async () => {
  try {
    $("#media-url").value = await navigator.clipboard.readText();
    $("#media-url").focus();
    showToast("Tautan ditempel dari clipboard.");
  } catch {
    showToast("Clipboard tidak tersedia. Tempel tautan secara manual.");
  }
});

$("#clear-media").addEventListener("click", () => {
  analyzedMedia = null;
  $("#media-card").classList.add("hidden");
  $("#media-url").value = "";
  optionsChanged();
});

document.querySelectorAll(".kind-tab").forEach((tab) => tab.addEventListener("click", () => {
  currentKind = tab.dataset.kind;
  document.querySelectorAll(".kind-tab").forEach((item) => {
    const active = item === tab;
    item.classList.toggle("active", active);
    item.setAttribute("aria-selected", String(active));
  });
  populateFormats();
  $("#job-panel").classList.add("hidden");
  $("#start-button").classList.remove("hidden");
  optionsChanged();
}));

$("#format-select").addEventListener("change", () => {
  const applyPreset = currentKind === "audio" && $("#preset-select").value !== "custom" && $("#format-select").value !== "wav";
  if (currentKind === "audio") {
    localStorage.setItem("ruangnada-format", $("#format-select").value);
  }
  optionsChanged();
  if (applyPreset) $("#preset-select").dispatchEvent(new Event("change"));
});
$("#preset-select").addEventListener("change", () => saveSelect("#preset-select", "ruangnada-preset"));
$("#bitrate-select").addEventListener("change", () => saveSelect("#bitrate-select", "ruangnada-bitrate"));
$("#sample-rate-select").addEventListener("change", () => saveSelect("#sample-rate-select", "ruangnada-sample-rate"));
$("#channels-select").addEventListener("change", () => saveSelect("#channels-select", "ruangnada-channels"));
$("#mode-select").addEventListener("change", () => {
  saveSelect("#mode-select", "ruangnada-audio-mode");
  optionsChanged();
  if ($("#preset-select").value !== "custom") $("#preset-select").dispatchEvent(new Event("change"));
});
$("#encoder-quality-select").addEventListener("change", () => saveSelect("#encoder-quality-select", "ruangnada-encoder-quality"));
$("#preset-select").addEventListener("change", () => {
  const preset = $("#preset-select").value;
  const defaultBitrate = { automatic: "320", economy: "96", standard: "192", high: "320" }[preset];
  if (defaultBitrate) $("#bitrate-select").value = defaultBitrate;
  const encoderQuality = { automatic: "2", economy: "7", standard: "4", high: "0" }[preset];
  if (encoderQuality && $("#format-select").value === "mp3" && $("#mode-select").value === "vbr") {
    $("#encoder-quality-select").value = encoderQuality;
  } else if (encoderQuality && $("#format-select").value === "ogg") {
    $("#encoder-quality-select").value = { automatic: "5", economy: "3", standard: "5", high: "9" }[preset];
  } else if (preset !== "custom" && $("#format-select").value === "flac") {
    $("#encoder-quality-select").value = { automatic: "5", economy: "12", standard: "5", high: "0" }[preset];
  }
  saveSelect("#preset-select", "ruangnada-preset");
  saveSelect("#bitrate-select", "ruangnada-bitrate");
  saveSelect("#encoder-quality-select", "ruangnada-encoder-quality");
});

function bytesPerSecond(value) {
  if (!Number.isFinite(value) || value <= 0) return "";
  return `${formatBytes(value)}/s`;
}

function renderJob(job) {
  currentJobId = job.job_id;
  $("#job-panel").classList.remove("hidden");
  $("#job-status").textContent = labels[job.status] || job.status;
  $("#job-stage").textContent = stages[job.stage] || job.stage;
  const hasProgress = Number.isFinite(job.progress);
  $("#progress-bar").style.width = hasProgress ? `${Math.max(0, Math.min(100, job.progress))}%` : (job.status === "running" ? "14%" : "0%");
  $("#job-percent").textContent = hasProgress ? `${job.progress}%` : "—";
  const downloaded = formatBytes(job.downloaded);
  const total = formatBytes(job.total);
  const speed = bytesPerSecond(job.speed);
  const eta = Number.isFinite(job.eta) ? `sisa ${formatDuration(job.eta)}` : "";
  $("#job-details").textContent = [downloaded && total ? `${downloaded} / ${total}` : downloaded, speed, eta].filter(Boolean).join(" · ");
  $("#cancel-button").classList.toggle("hidden", !["queued", "running"].includes(job.status));
  $("#job-error").classList.toggle("hidden", !job.error);
  $("#job-error").textContent = job.error || "";
  const result = $("#download-result");
  if (job.status === "completed" && job.file_id) {
    result.href = `/api/files/${encodeURIComponent(job.file_id)}`;
    result.classList.remove("hidden");
  } else {
    result.classList.add("hidden");
  }
  if (["completed", "failed", "cancelled"].includes(job.status)) {
    clearTimeout(pollTimer);
    $("#start-button").classList.remove("hidden");
    if (job.status === "completed") showToast("File berhasil diproses dan siap diunduh.");
    loadHistory();
  }
}

async function pollJob(jobId) {
  try {
    const job = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
    renderJob(job);
    if (["queued", "running"].includes(job.status)) pollTimer = setTimeout(() => pollJob(jobId), 900);
  } catch (error) {
    showToast(error.message);
  }
}

$("#start-button").addEventListener("click", async () => {
  if (currentKind !== "image" && !analyzedMedia) {
    showToast("Analisis URL terlebih dahulu.");
    return;
  }
  $("#start-button").disabled = true;
  $("#start-button").querySelector("span").textContent = "Memulai...";
  const filename = $("#filename-input").value.trim() || analyzedMedia?.title || "media";
  try {
    let job;
    if (currentKind === "image") {
      const file = $("#image-file").files[0];
      if (!file) throw new Error("Pilih file gambar terlebih dahulu.");
      const response = await fetch(`/api/images/convert?format=${encodeURIComponent($("#image-format-select").value)}&filename=${encodeURIComponent(file.name)}`, {
        method: "POST",
        headers: { "Content-Type": file.type || "application/octet-stream" },
        body: file,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Konversi gambar gagal.");
      job = data;
    } else {
      job = await api("/api/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: $("#media-url").value.trim(),
          kind: currentKind,
          format: $("#format-select").value,
          preset: $("#preset-select").value,
          bitrate: Number($("#bitrate-select").value),
          sample_rate: Number($("#sample-rate-select").value),
          channels: Number($("#channels-select").value),
          audio_mode: $("#mode-select").value,
          encoder_quality: Number($("#encoder-quality-select").value),
          video_height: Number($("#video-quality-select").value),
          filename,
        }),
      });
    }
    $("#start-button").classList.add("hidden");
    $("#job-panel").classList.remove("hidden");
    renderJob({ ...job, stage: "queued" });
    pollJob(job.job_id);
  } catch (error) {
    showToast(error.message);
    $("#start-button").disabled = false;
  } finally {
    $("#start-button").querySelector("span").textContent = "Mulai proses";
  }
});

$("#cancel-button").addEventListener("click", async () => {
  if (!currentJobId) return;
  try {
    await api(`/api/jobs/${encodeURIComponent(currentJobId)}/cancel`, { method: "POST" });
    $("#job-status").textContent = "Membatalkan...";
    showToast("Permintaan pembatalan dikirim.");
  } catch (error) {
    showToast(error.message);
  }
});

$("#image-file").addEventListener("change", () => {
  const file = $("#image-file").files[0];
  $("#upload-label").textContent = file ? file.name : "Pilih gambar dari perangkat";
  optionsChanged();
});

function renderHistory(items) {
  const container = $("#history-list");
  container.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "history-empty";
    empty.innerHTML = "<span>◷</span><p>Belum ada proses. Media yang selesai akan muncul di sini.</p>";
    container.append(empty);
    return;
  }
  items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "history-row";
    const icon = document.createElement("span");
    icon.className = "history-kind";
    icon.textContent = item.kind === "video" ? "▣" : item.kind === "image" ? "▧" : "♫";
    const copy = document.createElement("div");
    copy.className = "history-copy";
    const title = document.createElement("strong");
    title.textContent = item.details?.title || item.details?.filename || item.source_url || "Media";
    const details = document.createElement("small");
    const date = new Date(item.created_at).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" });
    details.textContent = `${String(item.output_format || "").toUpperCase()} · ${labels[item.status] || item.status} · ${date}`;
    copy.append(title, details);
    const status = document.createElement("span");
    status.className = "history-status";
    status.textContent = item.error ? "Gagal" : item.available ? "File tersedia" : labels[item.status] || item.status;
    const actions = document.createElement("div");
    actions.className = "history-actions";
    if (item.available && item.file_id) {
      const link = document.createElement("a");
      link.href = `/api/files/${encodeURIComponent(item.file_id)}`;
      link.setAttribute("aria-label", "Unduh ulang file");
      link.textContent = "↓";
      actions.append(link);
    }
    const remove = document.createElement("button");
    remove.type = "button";
    remove.setAttribute("aria-label", "Hapus riwayat");
    remove.textContent = "×";
    remove.addEventListener("click", async () => {
      try {
        await api(`/api/history/${encodeURIComponent(item.job_id)}`, { method: "DELETE" });
        await loadHistory();
      } catch (error) {
        showToast(error.message);
      }
    });
    actions.append(remove);
    row.append(icon, copy, status, actions);
    container.append(row);
  });
}

async function loadHistory() {
  try {
    const data = await api("/api/history");
    renderHistory(data.items);
  } catch (error) {
    showToast(error.message);
  }
}

$("#refresh-history").addEventListener("click", loadHistory);
$("#theme-toggle").addEventListener("click", () => {
  document.body.classList.toggle("light");
  localStorage.setItem("ruangnada-theme", document.body.classList.contains("light") ? "light" : "dark");
});
if (localStorage.getItem("ruangnada-theme") === "light") document.body.classList.add("light");
populateFormats();
restoreSelect("#preset-select", "ruangnada-preset");
restoreSelect("#bitrate-select", "ruangnada-bitrate");
restoreSelect("#sample-rate-select", "ruangnada-sample-rate");
restoreSelect("#channels-select", "ruangnada-channels");
restoreSelect("#mode-select", "ruangnada-audio-mode");
restoreSelect("#encoder-quality-select", "ruangnada-encoder-quality");
restoreSelect("#image-format-select", "ruangnada-image-format");
optionsChanged();
$("#preset-select").dispatchEvent(new Event("change"));
$("#image-format-select").addEventListener("change", () => saveSelect("#image-format-select", "ruangnada-image-format"));
loadHistory();
