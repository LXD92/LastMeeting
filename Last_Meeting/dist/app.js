(() => {
  "use strict";

  const PAGE_CONFIG = window.LAST_MEETING_CONFIG || {};
  const API_BASE_URL = String(PAGE_CONFIG.apiBaseUrl || "").replace(/\/$/, "");
  const USE_MENU_API = PAGE_CONFIG.useMenuApi !== false;
  const apiUrl = (path) => API_BASE_URL ? `${API_BASE_URL}${path}` : path;
  const FALLBACK_APPS = [
    {
      id: "hanacaraka", name: "Hanacaraka", description: "Transliterasi Latin ke Aksara Jawa, langsung di browser.",
      category: "Produktivitas", runtime: "browser", launch: "static", url: "./apps/hanacaraka/index.html",
      icon: null, configured: true, config_error: null, running: false
    },
    {
      id: "ruangnada", name: "RuangNada", description: "Studio untuk mengolah audio, video, dan gambar.",
      category: "Multimedia", runtime: "python", launch: "module", url: String(PAGE_CONFIG.ruangNadaUrl || ""),
      icon: null, configured: Boolean(PAGE_CONFIG.ruangNadaUrl), config_error: "RuangNada memerlukan backend Python yang belum dikonfigurasi.", running: false
    }
  ];
  const DEFAULT_PREFERENCES = { theme: "dark", view: "grid", favorites: [], recent: [], order: [], sort: "name", category: "Semua" };
  const state = { apps: [], preferences: {}, category: "Semua", page: "home", material: [], remote: false };
  const pageNames = { home: "Beranda", apps: "Semua aplikasi", favorites: "Favorit", recent: "Terakhir dibuka", material: "Material", settings: "Pengaturan", about: "Tentang Last_Meeting" };
  let toastTimer;

  async function request(url, options = {}) {
    const response = await fetch(url, { ...options, headers: { "Content-Type": "application/json", ...options.headers } });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.detail || `Permintaan gagal (${response.status}).`);
    return result;
  }

  function showToast(message) {
    const toast = document.querySelector("#toast");
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 3600);
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
  }

  function readLocalPreferences() {
    try {
      return { ...DEFAULT_PREFERENCES, ...JSON.parse(localStorage.getItem("last-meeting-preferences") || "{}") };
    } catch {
      return { ...DEFAULT_PREFERENCES };
    }
  }

  async function savePreferences(updates) {
    if (state.remote) {
      state.preferences = await request(apiUrl("/api/preferences"), { method: "PUT", body: JSON.stringify(updates) });
    } else {
      state.preferences = { ...state.preferences, ...updates };
      localStorage.setItem("last-meeting-preferences", JSON.stringify(state.preferences));
    }
    applyPreferences();
    render();
  }

  function appCard(app) {
    const configured = app.configured;
    const mark = app.id === "hanacaraka" ? "ꦲ" : app.id === "ruangnada" ? "♫" : escapeHtml(app.name.slice(0, 1).toUpperCase());
    const running = app.running;
    const status = !configured
      ? `<span class="status-tag unconfigured">${app.config_error ? "Belum tersedia" : "Belum dikonfigurasi"}</span>`
      : `<span class="status-tag ${running ? "running" : ""}">${running ? "Berjalan" : "Siap dibuka"}</span>`;
    const launchButton = running
      ? `<button class="stop-button" data-action="stop" data-id="${escapeHtml(app.id)}">Hentikan</button>`
      : `<button class="launch-button" data-action="launch" data-id="${escapeHtml(app.id)}" ${configured ? "" : "disabled"}>${configured ? "Buka aplikasi" : "Tidak tersedia"}</button>`;
    return `<article class="app-card">
      <div class="card-head"><div class="app-icon ${escapeHtml(app.id)}">${mark}</div><div class="card-tools">
        <button class="mini-button ${app.favorite ? "favorite" : ""}" data-action="favorite" data-id="${escapeHtml(app.id)}" aria-label="${app.favorite ? "Hapus dari" : "Tambah ke"} favorit" title="Favorit">${app.favorite ? "★" : "☆"}</button>
        <button class="mini-button" data-action="details" data-id="${escapeHtml(app.id)}" aria-label="Informasi aplikasi" title="Informasi">···</button>
      </div></div>
      <h3>${escapeHtml(app.name)}</h3><p>${escapeHtml(app.description || "Belum ada deskripsi.")}</p>
      <div class="app-tags"><span class="tag">${escapeHtml(app.category)}</span>${status}</div>
      <div class="card-actions">${launchButton}<span class="card-hint">${configured ? escapeHtml(app.runtime) : "Backend diperlukan"}</span></div>
    </article>`;
  }

  function renderCards(containerId, apps, emptyMessage) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = apps.length ? apps.map(appCard).join("") : `<div class="empty-state">${escapeHtml(emptyMessage)}</div>`;
    container.classList.toggle("list-view", state.preferences.view === "list");
  }

  function renderCategories() {
    const container = document.querySelector("#category-filters");
    const categories = ["Semua", ...new Set(state.apps.map((app) => app.category))];
    container.innerHTML = categories.map((category) => `<button class="category-button ${category === state.category ? "active" : ""}" data-category="${escapeHtml(category)}">${escapeHtml(category)}</button>`).join("");
  }

  function render() {
    const search = document.querySelector("#search-input").value.trim().toLocaleLowerCase("id");
    const matches = state.apps.filter((app) => `${app.name} ${app.description} ${app.category}`.toLocaleLowerCase("id").includes(search) && (state.category === "Semua" || app.category === state.category));
    const favorites = state.apps.filter((app) => app.favorite);
    const recentApps = (state.preferences.recent || []).map((id) => state.apps.find((app) => app.id === id)).filter(Boolean);
    renderCards("favorite-grid", favorites.slice(0, 3), "Belum ada favorit. Tandai aplikasi dengan bintang.");
    renderCards("recent-grid", recentApps.slice(0, 3), "Aplikasi yang dibuka akan muncul di sini.");
    renderCards("home-grid", state.apps.slice(0, 3), "Belum ada aplikasi yang tersedia.");
    renderCards("catalog-grid", matches, "Tidak ada aplikasi yang cocok dengan pencarian atau kategori.");
    renderCards("favorites-page-grid", favorites, "Belum ada aplikasi favorit.");
    renderCards("recent-page-grid", recentApps, "Belum ada riwayat aplikasi.");
    renderCategories();
    document.querySelector("#stat-apps").textContent = state.apps.length;
    document.querySelector("#stat-running").textContent = state.remote ? state.apps.filter((item) => item.running).length : "—";
    document.querySelector("#stat-favorites").textContent = favorites.length;
    document.querySelector("#nav-app-count").textContent = state.apps.length;
    document.querySelector("#about-material-count").textContent = `${state.material.length} kategori`;
    document.querySelector("#material-list").innerHTML = state.material.length ? state.material.map((item) => `<article class="material-card"><span class="material-icon">▧</span><div><h3>${escapeHtml(item.name)}</h3><p>${item.items} file tersedia</p></div></article>`).join("") : `<div class="empty-state">Belum ada material bersama.</div>`;
    document.querySelectorAll(".view-switch button").forEach((button) => button.classList.toggle("active", button.dataset.view === (state.preferences.view || "grid")));
  }

  function applyPreferences() {
    document.documentElement.dataset.theme = state.preferences.theme || "dark";
    document.querySelector("#theme-select").value = state.preferences.theme || "dark";
    document.querySelector("#view-select").value = state.preferences.view || "grid";
    document.querySelector("#sort-select").value = state.preferences.sort || "name";
    document.querySelector("#theme-toggle").textContent = state.preferences.theme === "light" ? "☾" : "☼";
  }

  async function load() {
    try {
      if (!USE_MENU_API) throw new Error("Menu API nonaktif di deployment statis.");
      const [catalog, material] = await Promise.all([request(apiUrl("/api/apps")), request(apiUrl("/api/material"))]);
      state.remote = true;
      state.apps = catalog.items;
      state.preferences = catalog.preferences;
      state.category = catalog.preferences.category || "Semua";
      state.material = material.categories;
      document.querySelector("#system-status").textContent = catalog.managed_running ? `${catalog.managed_running} aplikasi berjalan` : "Siap digunakan";
    } catch {
      state.remote = false;
      state.preferences = readLocalPreferences();
      state.category = state.preferences.category || "Semua";
      state.apps = FALLBACK_APPS.map((app) => ({ ...app, favorite: state.preferences.favorites.includes(app.id), recent: state.preferences.recent.includes(app.id) }));
      state.material = [];
      document.querySelector("#system-status").textContent = "Mode web";
    }
    applyPreferences();
    render();
  }

  function navigate(page) {
    if (!pageNames[page]) return;
    state.page = page;
    document.querySelectorAll(".page").forEach((section) => section.classList.toggle("active", section.id === `${page}-page`));
    document.querySelectorAll(".nav-item[data-page]").forEach((button) => button.classList.toggle("active", button.dataset.page === page));
    document.querySelector("#page-title").textContent = pageNames[page];
  }

  async function handleAction(button) {
    const id = button.dataset.id;
    const item = state.apps.find((app) => app.id === id);
    if (!item) return;
    let browserTab = null;
    try {
      if (button.dataset.action === "favorite") {
        const favorites = state.apps.filter((app) => app.favorite).map((app) => app.id);
        await savePreferences({ favorites: item.favorite ? favorites.filter((appId) => appId !== id) : [...favorites, id] });
      } else if (button.dataset.action === "launch") {
        if (!item.configured) {
          showToast(item.config_error || "Aplikasi belum tersedia.");
          return;
        }
        // Create the new tab during the user click. Never navigate the menu tab.
        if (state.remote) {
          browserTab = window.open("about:blank", "_blank");
          const result = await request(apiUrl(`/api/apps/${encodeURIComponent(id)}/launch`), { method: "POST" });
          if (!result.url) throw new Error(result.message || "URL aplikasi tidak tersedia.");
          if (browserTab) {
            browserTab.opener = null;
            browserTab.location.replace(result.url);
          } else showToast("Tab aplikasi diblokir browser. Izinkan pop-up untuk situs ini.");
          if (result.status === "external") showToast(result.message);
        } else if (item.url) {
          window.open(item.url, "_blank", "noopener,noreferrer");
        } else {
          showToast(item.config_error || "Aplikasi belum tersedia.");
          return;
        }
        const recent = [id, ...(state.preferences.recent || []).filter((appId) => appId !== id)].slice(0, 12);
        await savePreferences({ recent });
        if (state.remote) await load();
      } else if (button.dataset.action === "stop") {
        if (!state.remote) return;
        const result = await request(apiUrl(`/api/apps/${encodeURIComponent(id)}/stop`), { method: "POST" });
        showToast(result.message);
        await load();
      } else if (button.dataset.action === "details") {
        document.querySelector("#details-content").innerHTML = `<p class="eyebrow">INFORMASI APLIKASI</p><h2>${escapeHtml(item.name)}</h2><p>${escapeHtml(item.description || "Belum ada deskripsi.")}</p><p>Kategori: <strong>${escapeHtml(item.category)}</strong><br>Status: <strong>${item.running ? "Berjalan" : item.configured ? "Siap dibuka" : "Belum tersedia"}</strong><br>Runtime: <strong>${escapeHtml(item.runtime || "—")}</strong><br>Metode: <strong>${escapeHtml(item.launch || "—")}</strong></p>`;
        document.querySelector("#details-dialog").showModal();
      }
    } catch (error) {
      if (browserTab) browserTab.close();
      showToast(error.message);
    }
  }

  document.addEventListener("click", (event) => {
    const pageButton = event.target.closest("[data-page]");
    if (pageButton) navigate(pageButton.dataset.page);
    const actionButton = event.target.closest("[data-action]");
    if (actionButton) handleAction(actionButton);
    const categoryButton = event.target.closest("[data-category]");
    if (categoryButton) { state.category = categoryButton.dataset.category; savePreferences({ category: state.category }).catch((error) => showToast(error.message)); }
    const viewButton = event.target.closest("[data-view]");
    if (viewButton) savePreferences({ view: viewButton.dataset.view }).catch((error) => showToast(error.message));
  });
  document.querySelector("#search-input").addEventListener("input", render);
  document.querySelector("#theme-select").addEventListener("change", (event) => savePreferences({ theme: event.target.value }).catch((error) => showToast(error.message)));
  document.querySelector("#view-select").addEventListener("change", (event) => savePreferences({ view: event.target.value }).catch((error) => showToast(error.message)));
  document.querySelector("#sort-select").addEventListener("change", (event) => savePreferences({ sort: event.target.value }).catch((error) => showToast(error.message)));
  document.querySelector("#theme-toggle").addEventListener("click", () => savePreferences({ theme: state.preferences.theme === "dark" ? "light" : "dark" }).catch((error) => showToast(error.message)));
  document.querySelector("#manifest-help").addEventListener("click", (event) => { event.preventDefault(); showToast("Katalog aplikasi dikelola melalui konfigurasi deployment."); });
  document.addEventListener("keydown", (event) => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); document.querySelector("#search-input").focus(); } });

  state.preferences = readLocalPreferences();
  load();
  setInterval(() => { if (state.remote) load(); }, 3000);
})();
