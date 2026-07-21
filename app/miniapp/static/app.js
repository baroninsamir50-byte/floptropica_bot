const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
  tg.enableClosingConfirmation();
  tg.setHeaderColor?.("#120d1d");
  tg.setBackgroundColor?.("#0c0814");
}

const state = {
  data: null,
  view: "home",
  protectedImages: new Map(),
  tarot: null,
  tarotQuestion: "",
  tarotOffered: null,
  estate: null,
  npcs: null,
  friends: null,
  friendsLoading: false,
  friendsError: null,
  selectedFriend: null,
  selectedStory: null,
  storyIndex: 0,
  statistics: null,
  adminPlayers: null,
  projectAdmins: null,
  duels: null,
  duelStyle: "guardian",
  duelPoll: null,
  workTimer: null
};
const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[char]));
const content = $("content");
const initData = tg?.initData || "";

function createParticles() {
  const container = $("particles");
  if (!container) return;
  for (let i = 0; i < 34; i++) {
    const p = document.createElement("span");
    p.className = "particle";
    p.style.left = `${Math.random() * 100}%`;
    p.style.animationDuration = `${8 + Math.random() * 14}s`;
    p.style.animationDelay = `${-Math.random() * 20}s`;
    p.style.opacity = `${0.25 + Math.random() * 0.55}`;
    p.style.transform = `scale(${0.5 + Math.random() * 1.4})`;
    container.appendChild(p);
  }
}

function toast(message) {
  const node = $("toast");
  node.textContent = message;
  node.classList.remove("hidden");
  tg?.HapticFeedback?.notificationOccurred?.("success");
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => node.classList.add("hidden"), 2700);
}

async function api(path, options = {}) {
  const response = await fetch(`/api/miniapp${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": initData,
      ...(options.headers || {})
    }
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || "Ошибка сервера");
  return body;
}


function formatCountdown(totalSeconds) {
  const seconds = Math.max(0, Number(totalSeconds) || 0);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  return [hours, minutes, secs].map(value => String(value).padStart(2, "0")).join(":");
}

function startWorkCountdown() {
  clearInterval(state.workTimer);
  state.workTimer = null;
  const timerNode = document.querySelector("[data-work-countdown]");
  if (!timerNode || !state.data?.work?.active) return;
  let remaining = Math.max(0, Number(state.data.work.remaining_seconds) || 0);
  const update = () => {
    timerNode.textContent = remaining > 0 ? formatCountdown(remaining) : "Смена завершена";
    if (remaining <= 0) {
      clearInterval(state.workTimer);
      state.workTimer = null;
      state.data.work.remaining_seconds = 0;
      return;
    }
    remaining -= 1;
    state.data.work.remaining_seconds = remaining;
  };
  update();
  state.workTimer = setInterval(update, 1000);
}

async function protectedImage(path) {
  if (state.protectedImages.has(path)) {
    return state.protectedImages.get(path);
  }
  const response = await fetch(`/api/miniapp${path}`, {
    headers: { "X-Telegram-Init-Data": initData }
  });
  if (!response.ok) return null;
  const url = URL.createObjectURL(await response.blob());
  state.protectedImages.set(path, url);
  return url;
}

async function hydrateProtectedImages() {
  const nodes = [...document.querySelectorAll("[data-protected-image]")];
  await Promise.all(nodes.map(async node => {
    const url = await protectedImage(node.dataset.protectedImage);
    if (url) {
      node.src = url;
      node.classList.remove("image-loading");
    } else {
      node.closest(".portrait-stage, .house-photo-stage")?.classList.add("image-missing");
    }
  }));
}

function applyThemeMedia() {
  const media = state.data?.media || {};
  const root = document.documentElement;
  const setImage = (name, key) => {
    root.style.setProperty(name, media[key] ? `url("${media[key]}")` : "none");
  };

  setImage("--theme-card-texture", "card_texture");
  setImage("--theme-topbar-bg", "topbar_bg");
  setImage("--theme-nav-bg", "nav_bg");
  setImage("--theme-loading-bg", "loading_bg");

  const logo = $("loadingLogo");
  const emoji = $("loadingEmoji");
  if (media.app_logo && logo) {
    logo.src = media.app_logo;
    logo.classList.remove("hidden");
    emoji?.classList.add("hidden");
  }
}

const statLabels = {
  health: "❤️ Здоровье",
  mana: "🔮 Мана",
  strength: "💪 Сила",
  intelligence: "🧠 Интеллект",
  agility: "🏃 Ловкость",
  magic: "✨ Магия",
  luck: "🍀 Удача",
  endurance: "🛡 Выносливость",
  charisma: "🎭 Харизма"
};

const section = (title, body) =>
  `<div class="page-enter"><h2 class="section-title">${title}</h2>${body}</div>`;

function mediaUrl(key) {
  return state.data?.media?.[key] || null;
}

function visualIcon(key, fallback) {
  const url = mediaUrl(key);
  return url
    ? `<img class="custom-icon" src="${url}" alt="">`
    : fallback;
}

function bgStyle(key) {
  const url = mediaUrl(key);
  return url ? `style="background-image:linear-gradient(180deg,rgba(8,5,15,.22),rgba(8,5,15,.9)),url('${url}')"` : "";
}


function openUpload(kind) {
  const username = state.data?.bot_username;
  if (!username) {
    toast("Не удалось определить имя бота");
    return;
  }
  const payload = kind === "house" ? "upload_house" : "upload_portrait";
  tg?.openTelegramLink?.(`https://t.me/${username}?start=${payload}`);
}

function showStreakInfo() {
  tg?.showPopup?.({
    title: "Серия входов",
    message: "Заходите в игру каждый день. На 7-й день дополнительно выдаются очки развития.",
    buttons: [{ type: "ok", text: "Понятно" }]
  });
}

window.openImageViewer = url => {
  if (!url) {
    toast("Изображение ещё не загружено");
    return;
  }
  $("viewerImage").src = url;
  $("imageViewer").classList.remove("hidden");
  document.body.classList.add("viewer-open");
};

window.closeImageViewer = () => {
  $("imageViewer").classList.add("hidden");
  $("viewerImage").src = "";
  document.body.classList.remove("viewer-open");
};

function applyActiveScreenBackground() {
  const keyByView = {
    home: "home_bg",
    hero: "hero_bg",
    house: "house_bg",
    treasury: "treasury",
    shop: "shop",
    development: "development",
    factions: "factions",
    map: "map",
    games: "games_bg",
    tarot: "tarot_bg",
    npcs: "npc_bg",
    inventory: "inventory_bg",
    more: "home_bg"
  };
  const url = mediaUrl(keyByView[state.view]);
  document.documentElement.style.setProperty(
    "--active-screen-bg",
    url ? `url("${url}")` : "none"
  );
  document.body.classList.toggle("home-screen", state.view === "home");
}

function quick(icon, title, subtitle, view, mediaKey=null) {
  return `
    <button class="quick-card" onclick="go('${view}')">
      <span class="quick-icon">${mediaKey ? visualIcon(mediaKey, icon) : icon}</span>
      <b>${title}</b>
      <small>${subtitle}</small>
    </button>`;
}

function dailyStreakLine(streak) {
  const completed = Math.min(7, Math.max(0, streak % 7 || (streak ? 7 : 0)));
  return `<div class="streak-track">${Array.from({length: 7}, (_, index) =>
    `<span class="streak-segment ${index < completed ? "complete" : ""}"></span>`
  ).join("")}</div>`;
}

function homeView() {
  const d = state.data;
  const h = d.hero;
  const house = d.house;
  return `
    <div class="page-enter">
      <section class="hero-banner home-hero-banner" ${bgStyle("home_bg")}>
        <div class="eyebrow">ГРАЖДАНИН КОРОЛЕВСТВА</div>
        <h2>${h.name}</h2>
        <p>${h.title} · Уровень ${h.level}</p>
        <div class="home-resource-row">
          <span>🪙 ${h.gold}</span><span>✨ ${h.experience}/${h.experience_next}</span><span>🚩 ${h.faction}</span>
        </div>
      </section>

      <div class="daily-reward-card">
        <div class="daily-reward-head">
          <div><div class="eyebrow">ЕЖЕДНЕВНАЯ НАГРАДА</div><b>Серия: ${h.login_streak} дн.</b></div>
          <button class="info-btn" onclick="showStreakInfo()">i</button>
        </div>
        ${dailyStreakLine(h.login_streak)}
        <div class="daily-reward-foot">
          <small>На 7-й день дополнительно выдаются очки развития.</small>
          <button class="btn gold" onclick="claimDaily()" ${h.daily_reward_available ? "" : "disabled"}>
            ${h.daily_reward_available ? "🎁 Получить награду" : "✓ Получено"}
          </button>
        </div>
      </div>

      <div class="quick-grid">
        ${quick("👤", "Герой", `${h.development_points} очков развития`, "hero", "icon_hero")}
        ${quick("🏰", "Владение", `Прочность ${house.integrity ?? 0}%`, "house", "icon_house")}
        ${quick("👥", "Друзья", "Все жители Королевства", "friends")}
        ${quick("📊", "Статистика", "Результаты персонажа", "statistics")}
        ${quick("💰", "Казна", `${h.gold} золота`, "treasury", "icon_treasury")}
        ${quick("🛒", "Магазин", "5 товаров дня", "shop", "icon_shop")}
        ${quick("🗺", "Карта", "Королевство", "map", "icon_map")}
        ${quick("🎲", "Игры", "Дуэли и походы", "games", "icon_games")}
        ${quick("🚩", "Фракции", h.faction, "factions", "icon_factions")}
        ${quick("🎒", "Снаряжение", `${d.inventory.length} предметов`, "inventory", "icon_inventory")}
        ${quick("🔮", "Зал Предсказаний", "Неограниченные расклады", "tarot", "icon_tarot")}
        ${quick("👥", "NPC", "Стражники и крестьяне", "npcs", "icon_npc")}
      </div>
    </div>`;
}
function equipmentSlot(slot, icon, label) {
  const item = state.data.inventory.find(entry => entry.equipped && entry.slot === slot);
  return `<button class="equipment-slot" onclick="go('inventory')">
    <span class="equipment-icon">${item ? "✦" : icon}</span>
    <small>${label}</small><b>${item ? item.name : "Пусто"}</b>
  </button>`;
}

function heroView() {
  const h = state.data.hero;
  const compactStats = Object.entries(h.stats).map(([key, value]) => `
    <div class="compact-stat"><span>${statLabels[key]}</span><b>${value}</b></div>`).join("");
  return section("👤 Герой", `
    <div class="hero-redesign">
      <div class="portrait-stage hero-large-portrait" ${bgStyle("hero_bg")}>
        ${h.portrait_available ? `<img class="hero-portrait image-loading" data-protected-image="/hero-image" alt="${h.name}">`
        : `<div class="upload-placeholder"><div class="upload-symbol">👤</div><h3>Портрет не загружен</h3><button class="btn gold" onclick="openUpload('portrait')">Загрузить</button></div>`}
        ${mediaUrl("frame_hero") ? `<img class="decorative-frame" src="${mediaUrl("frame_hero")}" alt="">` : ""}
      </div>
      <div class="hero-summary panel">
        <div class="eyebrow">ПРОФИЛЬ ГЕРОЯ</div><h2>${h.name}</h2>
        <div class="hero-badges"><span class="badge">${h.title}</span><span class="badge">Ур. ${h.level}</span><span class="badge">${h.faction}</span></div>
        <div class="stat"><div class="stat-head"><span>Опыт</span><b>${h.experience}/${h.experience_next}</b></div>
          <div class="bar"><i style="width:${Math.min(100, h.experience / h.experience_next * 100)}%"></i></div></div>
        <div class="compact-stats-grid">${compactStats}</div>
      </div>
    </div>
    <div class="panel equipment-panel">
      <div class="row"><h3>Снаряжение</h3><button class="text-button" onclick="go('inventory')">Открыть инвентарь</button></div>
      <div class="equipment-grid">
        ${equipmentSlot("weapon", "⚔", "Оружие")}${equipmentSlot("armor", "🛡", "Броня")}
        ${equipmentSlot("ring", "💍", "Кольцо")}${equipmentSlot("amulet", "📿", "Амулет")}
        ${equipmentSlot("boots", "👢", "Обувь")}
      </div>
    </div>
    <div class="compact-development panel"><span>Свободные очки развития</span><b>${h.development_points}</b>
      <button class="btn gold" onclick="go('development')">Распределить</button></div>`);
}
async function loadEstate(silent=false) {
  try {
    state.estate = await api("/estate");
    if (!silent) render();
  } catch (error) {
    toast(error.message);
  }
}

function roomCard(room) {
  return `<article class="room-card">
    <div class="room-image">
      ${room.image_url
        ? `<img class="image-loading" data-protected-image="/estate/rooms/${room.id}/image" alt="${room.name}">`
        : `<span>🚪</span>`}
    </div>
    <div>
      <h3>${room.name}</h3>
      <p>${room.description || "Личная комната владения."}</p>
      <small>Чистота: ${room.cleanliness}/100</small>
    </div>
  </article>`;
}

function monsterBattle(attack) {
  const fighting = attack.status === "player_fighting";
  const waiting = attack.status === "waiting";
  return `<div class="monster-arena panel">
    <div class="eyebrow">НАПАДЕНИЕ НА ВЛАДЕНИЕ</div>
    <div class="monster-stage">
      <img src="${attack.enemy_image_url}" alt="${attack.enemy_name}" onerror="this.style.display='none'">
      <div>
        <h2>${attack.enemy_name}</h2>
        <p>Сила: ${attack.enemy_power}</p>
        <div class="stat-head"><span>❤️ Враг</span><b>${attack.enemy_hp}</b></div>
        <div class="bar"><i style="width:${Math.min(100,attack.enemy_hp)}%"></i></div>
      </div>
    </div>
    ${waiting ? `<button class="btn gold" onclick="startMonsterFight()">⚔ Вступить в бой</button>` : ""}
    ${attack.status === "guards_fighting" ? `<div class="badge">👮 Стражники уже сражаются</div>` : ""}
    ${fighting ? `
      <div class="monster-player-stats">
        <span>❤️ ${attack.player_hp}</span>
        <span>🔮 ${attack.player_mana}</span>
      </div>
      <div class="monster-actions">
        <button onclick="monsterAction('attack')">⚔ Атака</button>
        <button onclick="monsterAction('magic')">✨ Магия</button>
        <button onclick="monsterAction('defend')">🛡 Защита</button>
        <button onclick="monsterAction('dodge')">🏃 Уклонение</button>
        <button onclick="monsterAction('critical')">💥 Крит</button>
        <button onclick="monsterAction('potion')">🧪 Зелье</button>
      </div>` : ""}
  </div>`;
}

function houseView() {
  const h = state.data.house;
  const estate = state.estate;

  if (!h.name) {
    return section("🏰 Владение", `<div class="panel muted">Дом не найден</div>`);
  }
  if (!estate) {
    setTimeout(() => loadEstate(), 0);
    return section("🏰 Владение", `<div class="panel center-panel">Загружаем владение…</div>`);
  }

  const roomLimit = estate.room_limit;
  const rooms = estate.rooms.map(roomCard).join("");
  return section("🏰 Владение", `
    <div class="house-photo-stage estate-main-banner" ${bgStyle("house_bg")}>
      ${h.image_available ? `
        <img class="house-photo image-loading" data-protected-image="/house-image" alt="${h.name}">
      ` : `
        <div class="upload-placeholder house-upload">
          <div class="upload-symbol">🏰</div>
          <h3>Фото владения не загружено</h3>
          <button class="btn gold" onclick="openUpload('house')">Загрузить</button>
        </div>
      `}
      ${mediaUrl("frame_house") ? `<img class="decorative-frame house-frame" src="${mediaUrl("frame_house")}" alt="">` : ""}
      <div class="house-photo-caption">
        <div class="eyebrow">ВНЕШНИЙ ВИД ВЛАДЕНИЯ</div>
        <h2>${h.name}</h2>
        <p>${h.location}</p>
        ${h.image_available ? `<button class="house-change-photo" onclick="openUpload('house')">📷 Заменить фото</button>` : ""}
      </div>
    </div>

    ${estate.household?.shared ? `<div class="panel shared-household-banner">💍 Совместный дом с <b>${estate.household.spouse_name}</b>. Комнаты, NPC и бюджет объединены.</div>` : ""}
    ${estate.attack ? monsterBattle(estate.attack) : ""}

    <div class="panel estate-status">
      <div class="row"><span>🏗 Прочность</span><b>${h.integrity}/100</b></div>
      <div class="row"><span>🧹 Чистота</span><b>${estate.house.cleanliness}/100</b></div>
      <div class="row"><span>👹 Уровень угрозы</span><b>${estate.house.threat_level}</b></div>
      <div class="estate-actions-grid">
        <button class="btn gold" onclick="repairEstate()" ${h.integrity >= 100 ? "disabled" : ""}>🔨 Ремонт · 15 🪙</button>
        <button class="btn magic" onclick="repairEstatePotion()" ${(h.integrity >= 100 || !estate.repair_potions) ? "disabled" : ""}>🧪 Зелье ремонта · ${estate.repair_potions}</button>
        <button class="btn secondary" onclick="cleanEstate('self')" ${estate.house.cleaning_available ? "" : "disabled"}>🧹 Убраться</button>
        <button class="btn secondary" onclick="cleanEstate('peasant')" ${estate.house.cleaning_available ? "" : "disabled"}>🌾 Фермер</button>
        <button class="btn secondary" onclick="go('npcs')">👥 NPC</button>
      </div>
    </div>

    <div class="row room-heading">
      <h3>🚪 Комнаты · ${estate.rooms.length}/${roomLimit}</h3>
      <button class="btn secondary" onclick="openRoomUpload()" ${estate.rooms.length >= roomLimit ? "disabled" : ""}>＋ Добавить</button>
    </div>
    <div class="room-list">${rooms || '<div class="panel muted">Добавьте первую комнату.</div>'}</div>
  `);
}

window.repairEstate = async () => {
  try {
    const result = await api("/estate/repair", { method: "POST" });
    toast(`Восстановлено ${result.restored} прочности за ${result.cost} золота`);
    await refresh(); await loadEstate(true); render();
  } catch (error) { toast(error.message); }
};

window.repairEstatePotion = async () => {
  try {
    const result = await api("/estate/repair-potion", { method: "POST" });
    toast(result.message);
    await refresh(); await loadEstate(true); render();
  } catch (error) { toast(error.message); }
};

window.startMonsterFight = async () => {
  try {
    await api("/estate/attack/start", {method:"POST"});
    toast("Бой начался");
    await loadEstate(true);
    render();
  } catch (error) { toast(error.message); }
};

window.monsterAction = async action => {
  try {
    const result = await api("/estate/attack/action", {
      method:"POST", body:JSON.stringify({action})
    });
    toast(`${result.player_log || ""} ${result.enemy_log || ""}`.trim());
    await refresh();
    await loadEstate(true);
    render();
  } catch (error) { toast(error.message); }
};

window.cleanEstate = async method => {
  try {
    await api("/estate/clean", {method:"POST", body:JSON.stringify({method})});
    toast("Уборка завершена");
    await loadEstate(true);
    render();
  } catch (error) { toast(error.message); }
};

window.openRoomUpload = () => {
  const modal=document.createElement("div");
  modal.className="tarot-upload-modal"; modal.id="roomUploadModal";
  modal.innerHTML=`<form class="tarot-upload-form" onsubmit="uploadRoom(event)">
    <button type="button" class="viewer-close" onclick="closeRoomUpload()">✕</button>
    <h2>Новая комната</h2>
    <input name="name" maxlength="100" placeholder="Название комнаты" required>
    <textarea name="description" maxlength="2000" placeholder="Описание"></textarea>
    <label class="tarot-file-label">Изображение комнаты
      <input name="file" type="file" accept="image/*">
    </label>
    <button class="btn gold">Добавить комнату</button>
  </form>`;
  document.body.appendChild(modal); document.body.classList.add("viewer-open");
};
window.closeRoomUpload=()=>{$("roomUploadModal")?.remove();document.body.classList.remove("viewer-open")};
window.uploadRoom=async event=>{
  event.preventDefault();
  try{
    const response=await fetch("/api/miniapp/estate/rooms",{
      method:"POST",headers:{"X-Telegram-Init-Data":initData},body:new FormData(event.currentTarget)
    });
    const body=await response.json().catch(()=>({}));
    if(!response.ok) throw new Error(body.detail||"Ошибка");
    closeRoomUpload(); toast("Комната добавлена"); await loadEstate(true); render();
  }catch(error){toast(error.message)}
};

function developmentView() {
  const h = state.data.hero;

  const favored = new Set(h.faction_bonus?.favored_stats || []);
  const cards = Object.entries(h.stats).map(([key, value]) => `
    <div class="card ${favored.has(key) ? "faction-favored-stat" : ""}">
      <div class="row">
        <b>${statLabels[key]}</b>
        <span class="badge">${value}</span>
      </div>
      ${favored.has(key) ? '<small class="faction-bonus-label">Бонус фракции</small>' : ''}
      <div class="action-grid">
        <button class="btn secondary" onclick="develop('${key}',1)"
          ${h.development_points < 1 ? "disabled" : ""}>+1</button>
        <button class="btn gold" onclick="develop('${key}',5)"
          ${h.development_points < 5 ? "disabled" : ""}>${favored.has(key) ? "+6 за 5" : "+5"}</button>
      </div>
    </div>`).join("");

  return section(`🏋 Развитие · осталось ${h.development_points}`, `
    <div class="panel faction-development-panel" ${bgStyle("development")}>
      <div class="eyebrow">${h.faction_bonus?.icon || '🚩'} ${h.faction_bonus?.name || h.faction}</div>
      <h3>${h.faction_bonus?.description || 'Фракцию назначает создатель.'}</h3>
      <p>${h.faction_bonus?.bonus_text || ''}</p>
    </div>
    <div class="cards">${cards}</div>`);
}

function treasuryView() {
  const d = state.data;
  const work = d.work;

  const professions = d.professions.map(p => `
    <div class="card">
      <div class="row">
        <h3>${p.label}</h3>
        ${d.hero.profession === p.name ? '<span class="badge">Выбрано</span>' : ""}
      </div>
      <p>${p.gold[0]}–${p.gold[1]} 🪙 · ${p.xp[0]}–${p.xp[1]} XP</p>
      ${p.role_bonus > 0 ? `<small class="role-income-bonus">Бонус титула: +${Math.round(p.role_bonus*100)}% к доходу</small>` : ""}
      <button class="btn secondary" onclick="chooseProfession('${p.key}')">
        Выбрать профессию
      </button>
    </div>`).join("");

  return section("💰 Казна", `
    <div class="section-visual-large treasury-visual" ${bgStyle("treasury")}>
      <div class="visual-overlay">
        <div class="eyebrow">КОРОЛЕВСКАЯ СЛУЖБА</div>
        <div class="compact-meta">
          <span>${d.hero.profession}</span>
          <span>${work.count}/6 смен</span>
          <span class="work-status">${work.active ? `Работа идёт · <b data-work-countdown>${formatCountdown(work.remaining_seconds)}</b>` : "Свободен"}</span>
        </div>
        <div class="action-grid">
          <button class="btn gold" onclick="startWork()">Начать смену</button>
          <button class="btn secondary" onclick="claimWork()">Получить награду</button>
        </div>
      </div>
    </div>
    <div class="panel title-work-benefits">
      <b>Бонус титула</b>
      <p>${["Король","Королева"].includes(d.hero.title) ? "👑 +50% к доходу каждой смены." : d.hero.title === "Лидер фракции" ? "🚩 Открыты Дебаты, Развитие фракции и Председатель сената. Эти смены дают +20%." : ["Хорги","Чародей","Волшебник"].includes(d.hero.title) ? "🧪 Раз в сутки после смены выдаётся зелье здоровья или ремонта дома." : "Любая обычная профессия доступна без ограничений."}</p>
    </div>

    <div class="cards profession-list">${professions}</div>`);
}

function shopView() {
  const items = state.data.shop.items.map(item => `
    <div class="card">
      <div class="row">
        <h3>${item.name}</h3>
        <span class="badge">${item.rarity}</span>
      </div>
      <p>${item.description}</p>
      <div class="row">
        <b>${item.price} 🪙</b>
        <button class="btn gold" onclick="buy(${item.id})">Купить</button>
      </div>
    </div>`).join("");

  return section(`🛒 Магазин дня · ${state.data.shop.date}`,
    `<div class="section-visual-large shop-visual" ${bgStyle("shop")}>
      <div class="visual-overlay">
        <div class="eyebrow">МАГАЗИН ДНЯ</div>
        <h3>Магический ассортимент</h3>
        <p>Цены снижены. Каждый день дополнительно появляется один предмет для комплекта улучшения стражника или фермера.</p>
      </div>
    </div>
    <div class="cards shop-list">${items}</div>`);
}

function inventoryView() {
  const items = state.data.inventory.length
    ? state.data.inventory.map(item => `
      <div class="card">
        <div class="row">
          <h3>${item.name} ×${item.quantity}</h3>
          <span class="badge">${item.rarity}</span>
        </div>
        <p>${item.description}</p>
        ${item.slot ? `
          <button class="btn ${item.equipped ? "secondary" : "gold"}"
            onclick="equip(${item.inventory_id})">
            ${item.equipped ? "Снять" : "Надеть"}
          </button>` : ""}
        ${["healing_potion","greater_healing_potion"].includes(item.slug) ? `<button class="btn magic" onclick="useInventoryItem(${item.inventory_id})">🧪 Использовать</button>` : ""}
        ${item.slug === "house_repair_potion" ? `<button class="btn magic" onclick="go('house')">🏰 Использовать во владении</button>` : ""}
      </div>`).join("")
    : `<div class="panel muted">Инвентарь пуст</div>`;

  return section("🎒 Снаряжение", `<div class="panel media-panel inventory-cover" ${bgStyle("inventory_bg")}><p>Арсенал и магические предметы персонажа.</p></div><div class="cards">${items}</div>`);
}

function mapView() {
  const mapUrl = mediaUrl("map");
  return section("🗺 Карта Королевства", `
    <div class="map-stage ${mapUrl ? "" : "map-empty"}">
      ${mapUrl ? `
        <img class="map-image" src="${mapUrl}" alt="Карта Королевства">
        <button class="map-expand-btn" onclick="openImageViewer('${mapUrl}')">⛶ Открыть полностью</button>
      ` : `
        <div class="upload-placeholder">
          <div class="upload-symbol">🗺</div>
          <h3>Карта ещё не загружена</h3>
          <p>Создатель может добавить карту через панель администратора.</p>
        </div>
      `}
    </div>`);
}

function factionsView() {
  return section("🚩 Фракции", `
    <div class="cards">
      <div class="card">
        <h3>🌅 ЗАПАДНАЯ ФРАКЦИЯ</h3>
        <p>Бонус развития: сила, выносливость и ловкость получают +6 при вложении 5 очков.</p>
      </div>
      <div class="card">
        <h3>🕊 НЕЙТРАЛЬНЫЙ ДИАЛОГ</h3>
        <p>Бонус развития: интеллект, харизма и магия получают +6 при вложении 5 очков.</p>
      </div>
      <div class="panel">
        <div class="row">
          <span>Ваша фракция</span>
          <b>${state.data.hero.faction}</b>
        </div>
      </div>
    </div>`);
}


async function loadDuelCenter(silent=false) {
  try {
    state.duels = await api("/duels");
    if (state.view === "games") render();
  } catch (error) {
    if (!silent) toast(error.message);
  }
}

function duelStyleSelect(selected=state.duelStyle) {
  const styles=state.duels?.styles || [];
  return `<div class="style-grid">${styles.map(style=>`
    <button class="style-card ${selected===style.key?'selected':''}" onclick="state.duelStyle='${style.key}';render()">
      <b>${style.name}</b>
      <small>${{
        berserk:'+25% урон · −15% защита',
        guardian:'+30% защита · −10% урон',
        magister:'+25% магия · −10% физический урон',
        duelist:'+уклонение и мобильность'
      }[style.key]||''}</small>
    </button>`).join('')}</div>`;
}

function duelPortrait(character, sideClass='') {
  return `<div class="duel-fighter ${sideClass}">
    <div class="duel-portrait-wrap">
      <img class="duel-portrait image-loading" data-protected-image="/duel-image/${character.id}" alt="${character.name}">
      ${mediaUrl('duel_frame')?`<img class="duel-frame" src="${mediaUrl('duel_frame')}" alt="">`:''}
    </div>
    <h3>${character.name}</h3>
    <p>Ур. ${character.level} · ${character.title}</p>
    <span class="badge">🏆 ${character.rating}</span>
  </div>`;
}

function duelBattleView(duel) {
  const b=duel.battle, c=duel.challenger, o=duel.opponent;
  const mySide=duel.viewer_side, myTurn=duel.is_my_turn;
  const actions=[
    ['attack','⚔','Атака'],['magic','✨','Магия'],['defend','🛡','Защита'],
    ['dodge','🏃','Уклонение'],['critical','💥','Крит'],['potion','🧪','Зелье']
  ];
  const maxHp=Math.max(c.stats.health+c.stats.endurance*3+c.level*8,o.stats.health+o.stats.endurance*3+o.level*8,1);
  return `<div class="duel-arena" ${bgStyle('duel_bg')}>
    <div class="duel-versus-grid">
      ${duelPortrait(c,'left')}
      <div class="versus-mark">${mediaUrl('duel_vs')?`<img src="${mediaUrl('duel_vs')}" alt="VS">`:'VS'}</div>
      ${duelPortrait(o,'right')}
    </div>
    <div class="duel-bars-grid">
      <div>${combatBars(c,b.challenger_hp,b.challenger_mana,b.challenger_stamina,maxHp)}</div>
      <div>${combatBars(o,b.opponent_hp,b.opponent_mana,b.opponent_stamina,maxHp)}</div>
    </div>
    <div class="turn-banner ${myTurn?'my-turn':''}">${duel.status==='finished' ? (duel.winner_id===state.duels.me.id?'🏆 Победа':'💀 Поражение') : (myTurn?'Ваш ход':'Ход соперника')}</div>
    ${duel.status==='active'?`<div class="duel-actions">${actions.map(([key,icon,label])=>`<button onclick="duelAction(${duel.id},'${key}')" ${myTurn?'':'disabled'}><span>${icon}</span><b>${label}</b></button>`).join('')}</div>`:''}
    <div class="battle-log"><h3>📜 Ход боя</h3>${(b.log||[]).slice(-8).reverse().map(x=>`<p>${x}</p>`).join('')||'<p>Дуэль ещё не началась.</p>'}</div>
  </div>`;
}

function combatBars(character,hp,mana,stamina,maxHp) {
  return `<div class="combat-bars"><b>${character.name}</b>
    <div class="combat-line hp"><span style="width:${Math.max(0,Math.min(100,hp/maxHp*100))}%"></span><em>❤️ ${hp}</em></div>
    <div class="combat-line mana"><span style="width:${Math.max(0,Math.min(100,mana/250*100))}%"></span><em>🔮 ${mana}</em></div>
    <div class="combat-line stamina"><span style="width:${Math.max(0,Math.min(100,stamina/160*100))}%"></span><em>⚡ ${stamina}</em></div>
  </div>`;
}

window.challengePlayer=async opponentId=>{
  try{await api('/duels/challenge',{method:'POST',body:JSON.stringify({opponent_id:opponentId,style:state.duelStyle})});toast('Вызов отправлен');await loadDuelCenter();}catch(e){toast(e.message)}
};
window.acceptDuel=async duelId=>{
  try{await api(`/duels/${duelId}/accept`,{method:'POST',body:JSON.stringify({style:state.duelStyle})});toast('Дуэль началась');await loadDuelCenter();}catch(e){toast(e.message)}
};
window.declineDuel=async duelId=>{
  try{await api(`/duels/${duelId}/decline`,{method:'POST'});await loadDuelCenter();}catch(e){toast(e.message)}
};
window.duelAction=async(duelId,action)=>{
  try{state.duels.active=await api(`/duels/${duelId}/action`,{method:'POST',body:JSON.stringify({action})});render();}catch(e){toast(e.message)}
};


async function hydrateStudioPreviews() {
  const nodes = [...document.querySelectorAll('[data-studio-protected]')];
  await Promise.all(nodes.map(async node => {
    const url = await protectedImage(node.dataset.studioProtected);
    if (url) {
      node.style.backgroundImage = `url("${url}")`;
      node.classList.add('loaded');
    }
  }));
}

async function loadProjectAdmins(silent=false) {
  if (!state.data?.is_owner) return;
  try {
    state.projectAdmins = await api("/admin/project-admins");
    if (!silent && state.view === "customization") render();
  } catch (error) { if (!silent) toast(error.message); }
}

function projectAdminPanel() {
  if (!state.data?.is_owner) return "";
  if (!state.projectAdmins) {
    setTimeout(() => loadProjectAdmins(), 0);
    return `<div class="panel"><h3>👑 Администраторы проекта</h3><p class="muted">Загружаем список игроков…</p></div>`;
  }
  const rows = state.projectAdmins.users.map(item => `
    <div class="project-admin-row">
      <div><b>${item.character_name || item.first_name}</b><small>${item.username ? '@'+item.username : 'ID '+item.telegram_id}</small></div>
      ${item.is_owner ? '<span class="badge">Создатель</span>' : `<button class="btn ${item.is_project_admin ? 'secondary' : 'gold'}" onclick="toggleProjectAdmin(${item.telegram_id},${!item.is_project_admin})">${item.is_project_admin ? 'Снять права' : 'Назначить админом'}</button>`}
    </div>`).join("");
  return `<div class="panel project-admin-panel"><div class="eyebrow">УПРАВЛЕНИЕ ДОСТУПОМ</div><h3>👑 Администраторы проекта</h3><p class="muted">Администратор получает кнопку ⚙ и может менять фоны, иконки, карты, модели врагов и облики NPC.</p><div class="project-admin-list">${rows}</div></div>`;
}

window.toggleProjectAdmin = async (telegram_id, enabled) => {
  try {
    await api("/admin/project-admins", {method:"POST",body:JSON.stringify({telegram_id,enabled})});
    toast(enabled ? "Администратор назначен" : "Права администратора сняты");
    await loadProjectAdmins(true); render();
  } catch (error) { toast(error.message); }
};

function customizationView() {
  if (!state.data.is_admin) {
    return section('⚙ Кастомизация','<div class="panel">Недостаточно прав.</div>');
  }

  const labels = {
    home_bg:'Фон главной', hero_bg:'Фон героя', house_bg:'Фон владения',
    treasury:'Фон казны', shop:'Фон магазина', development:'Фон развития',
    factions:'Фон фракций', map:'Карта', games_bg:'Фон игр',
    inventory_bg:'Фон инвентаря', loading_bg:'Фон загрузки', app_logo:'Эмблема',
    topbar_bg:'Верхняя панель', nav_bg:'Нижнее меню', card_texture:'Текстура карточек',
    frame_hero:'Рамка героя', frame_house:'Рамка дома', duel_bg:'Фон дуэли',
    duel_frame:'Рамка бойца', duel_vs:'Знак VS', icon_customization:'Иконка кастомизации',
    tarot_bg:'Фон Зала Предсказаний', tarot_back:'Рубашка Таро', icon_tarot:'Иконка Таро',
    npc_bg:'Фон NPC', icon_npc:'Иконка NPC', room_bg:'Фон комнат',
    enemy_dragon_1:'Дракон 1',enemy_dragon_2:'Дракон 2',enemy_dragon_3:'Дракон 3',
    enemy_monster_1:'Монстр 1',enemy_monster_2:'Монстр 2',enemy_monster_3:'Монстр 3',
    enemy_anomaly_1:'Аномалия 1',enemy_anomaly_2:'Аномалия 2',enemy_anomaly_3:'Аномалия 3',
    guard_model_1:'Стражник 1',guard_model_2:'Стражник 2',guard_model_3:'Стражник 3',
    peasant_model_1:'Крестьянин 1',peasant_model_2:'Крестьянин 2',peasant_model_3:'Крестьянин 3',
    npc_peasant_1:'Крестьянин — облик 1',
    npc_peasant_2:'Крестьянин — облик 2',
    npc_peasant_3:'Крестьянин — облик 3',
    npc_farmer_1:'Фермер — облик 1',
    npc_farmer_2:'Фермер — облик 2',
    npc_farmer_3:'Фермер — облик 3',
    npc_gardener_1:'Садовник — облик 1',
    npc_gardener_2:'Садовник — облик 2',
    npc_gardener_3:'Садовник — облик 3',
    npc_forester_1:'Лесник — облик 1',
    npc_forester_2:'Лесник — облик 2',
    npc_forester_3:'Лесник — облик 3',
    npc_miner_1:'Шахтёр — облик 1',
    npc_miner_2:'Шахтёр — облик 2',
    npc_miner_3:'Шахтёр — облик 3',
    npc_fisher_1:'Рыбак — облик 1',
    npc_fisher_2:'Рыбак — облик 2',
    npc_fisher_3:'Рыбак — облик 3',
    npc_cook_1:'Повар — облик 1',
    npc_cook_2:'Повар — облик 2',
    npc_cook_3:'Повар — облик 3',
    npc_recruit_1:'Новобранец — облик 1',
    npc_recruit_2:'Новобранец — облик 2',
    npc_recruit_3:'Новобранец — облик 3',
    npc_guard_1:'Стражник — облик 1',
    npc_guard_2:'Стражник — облик 2',
    npc_guard_3:'Стражник — облик 3',
    npc_veteran_1:'Ветеран — облик 1',
    npc_veteran_2:'Ветеран — облик 2',
    npc_veteran_3:'Ветеран — облик 3',
    npc_archer_1:'Лучник — облик 1',
    npc_archer_2:'Лучник — облик 2',
    npc_archer_3:'Лучник — облик 3',
    npc_rider_1:'Всадник — облик 1',
    npc_rider_2:'Всадник — облик 2',
    npc_rider_3:'Всадник — облик 3',
    npc_paladin_1:'Паладин — облик 1',
    npc_paladin_2:'Паладин — облик 2',
    npc_paladin_3:'Паладин — облик 3',
    npc_dragon_tamer_1:'Укротитель драконов — облик 1',
    npc_dragon_tamer_2:'Укротитель драконов — облик 2',
    npc_dragon_tamer_3:'Укротитель драконов — облик 3',
    npc_mage_1:'Маг — облик 1',
    npc_mage_2:'Маг — облик 2',
    npc_mage_3:'Маг — облик 3',
    npc_seer_1:'Провидец — облик 1',
    npc_seer_2:'Провидец — облик 2',
    npc_seer_3:'Провидец — облик 3',
    npc_alchemist_1:'Алхимик — облик 1',
    npc_alchemist_2:'Алхимик — облик 2',
    npc_alchemist_3:'Алхимик — облик 3',
    npc_exorcist_1:'Экзорцист — облик 1',
    npc_exorcist_2:'Экзорцист — облик 2',
    npc_exorcist_3:'Экзорцист — облик 3',
    npc_archmage_1:'Архимаг — облик 1',
    npc_archmage_2:'Архимаг — облик 2',
    npc_archmage_3:'Архимаг — облик 3',
    npc_merchant_1:'Торговец — облик 1',
    npc_merchant_2:'Торговец — облик 2',
    npc_merchant_3:'Торговец — облик 3',
    npc_banker_1:'Банкир — облик 1',
    npc_banker_2:'Банкир — облик 2',
    npc_banker_3:'Банкир — облик 3',
    npc_quartermaster_1:'Интендант — облик 1',
    npc_quartermaster_2:'Интендант — облик 2',
    npc_quartermaster_3:'Интендант — облик 3',
    npc_treasurer_1:'Казначей — облик 1',
    npc_treasurer_2:'Казначей — облик 2',
    npc_treasurer_3:'Казначей — облик 3',
    npc_judge_1:'Судья — облик 1',
    npc_judge_2:'Судья — облик 2',
    npc_judge_3:'Судья — облик 3',
    npc_scribe_1:'Писарь — облик 1',
    npc_scribe_2:'Писарь — облик 2',
    npc_scribe_3:'Писарь — облик 3',
    npc_advisor_1:'Советник — облик 1',
    npc_advisor_2:'Советник — облик 2',
    npc_advisor_3:'Советник — облик 3',
    npc_chancellor_1:'Канцлер — облик 1',
    npc_chancellor_2:'Канцлер — облик 2',
    npc_chancellor_3:'Канцлер — облик 3',
    npc_bard_1:'Бард — облик 1',
    npc_bard_2:'Бард — облик 2',
    npc_bard_3:'Бард — облик 3',
    npc_artist_1:'Художник — облик 1',
    npc_artist_2:'Художник — облик 2',
    npc_artist_3:'Художник — облик 3',
    npc_librarian_1:'Библиотекарь — облик 1',
    npc_librarian_2:'Библиотекарь — облик 2',
    npc_librarian_3:'Библиотекарь — облик 3',
    npc_architect_1:'Архитектор — облик 1',
    npc_architect_2:'Архитектор — облик 2',
    npc_architect_3:'Архитектор — облик 3',
    npc_dog_1:'Пёс — облик 1',
    npc_dog_2:'Пёс — облик 2',
    npc_dog_3:'Пёс — облик 3',
    npc_cat_1:'Кот — облик 1',
    npc_cat_2:'Кот — облик 2',
    npc_cat_3:'Кот — облик 3',
    npc_falcon_1:'Сокол — облик 1',
    npc_falcon_2:'Сокол — облик 2',
    npc_falcon_3:'Сокол — облик 3',
    npc_small_dragon_1:'Маленький дракон — облик 1',
    npc_small_dragon_2:'Маленький дракон — облик 2',
    npc_small_dragon_3:'Маленький дракон — облик 3',
    npc_royal_architect_1:'Королевский архитектор — облик 1',
    npc_royal_architect_2:'Королевский архитектор — облик 2',
    npc_royal_architect_3:'Королевский архитектор — облик 3',
    npc_great_magister_1:'Великий магистр — облик 1',
    npc_great_magister_2:'Великий магистр — облик 2',
    npc_great_magister_3:'Великий магистр — облик 3',
    npc_royal_general_1:'Генерал Королевства — облик 1',
    npc_royal_general_2:'Генерал Королевства — облик 2',
    npc_royal_general_3:'Генерал Королевства — облик 3',
    npc_forest_keeper_1:'Хранитель леса — облик 1',
    npc_forest_keeper_2:'Хранитель леса — облик 2',
    npc_forest_keeper_3:'Хранитель леса — облик 3',
    npc_angel_of_light_1:'Ангел света — облик 1',
    npc_angel_of_light_2:'Ангел света — облик 2',
    npc_angel_of_light_3:'Ангел света — облик 3'
  };

  const themeCards = Object.entries(labels).map(([key,label]) => {
    const url = state.data.media[key];
    const npcAppearance = key.startsWith('npc_') && key !== 'npc_bg';
    return `<article class="theme-item ${npcAppearance ? 'npc-appearance-item' : 'base-theme-item'}">
      ${npcAppearance ? '<span class="npc-appearance-badge">NPC</span>' : ''}
      <button class="theme-preview ${url ? '' : 'empty'}"
        ${url ? `style="background-image:url('${url}')" onclick="openImageViewer('${url}')"` : ''}>
        ${url
          ? '<span>Нажмите для просмотра</span>'
          : `<span class="${npcAppearance ? 'npc-empty-preview' : ''}">
              ${npcAppearance ? '👤<br>Загрузить облик' : 'Изображение не задано'}
            </span>`}
      </button>
      <b>${label}</b>
      <div class="theme-actions">
        <label class="studio-btn upload">📤 Загрузить
          <input type="file" accept="image/*" onchange="uploadTheme('${key}',this.files[0]);this.value=''">
        </label>
        <button class="studio-btn" onclick="previewTheme('${key}')" ${url ? '' : 'disabled'}>👁 Просмотр</button>
        <button class="studio-btn danger" onclick="deleteTheme('${key}')" ${url ? '' : 'disabled'}>🗑 Удалить</button>
      </div>
    </article>`;
  }).join('');

  const portraitUrl = state.data.hero.portrait_available ? '/api/miniapp/hero-image' : null;
  const houseUrl = state.data.house.image_available ? '/api/miniapp/house-image' : null;

  return section('⚙ Студия оформления',`
    <div class="panel studio-intro">
      <h3>Оформление Mini App</h3>
      <p>Загружайте, просматривайте и удаляйте изображения прямо здесь. Изменения применяются после обновления данных приложения.</p>
    </div>

    ${projectAdminPanel()}

    <h3 class="subheading">Мои изображения</h3>
    <div class="theme-grid personal-media-grid">
      <article class="theme-item">
        <div class="theme-preview protected-preview" data-studio-protected="/hero-image">
          <span>${portraitUrl ? 'Портрет персонажа' : 'Портрет не загружен'}</span>
        </div>
        <b>Портрет героя</b>
        <div class="theme-actions">
          <button class="studio-btn upload" onclick="openUpload('portrait')">📤 Загрузить</button>
          <button class="studio-btn" onclick="previewProtected('/hero-image')" ${portraitUrl ? '' : 'disabled'}>👁 Просмотр</button>
          <button class="studio-btn danger" onclick="deleteProfileImage('portrait')" ${portraitUrl ? '' : 'disabled'}>🗑 Удалить</button>
        </div>
      </article>

      <article class="theme-item">
        <div class="theme-preview protected-preview" data-studio-protected="/house-image">
          <span>${houseUrl ? 'Фото владения' : 'Фото не загружено'}</span>
        </div>
        <b>Фотография дома</b>
        <div class="theme-actions">
          <button class="studio-btn upload" onclick="openUpload('house')">📤 Загрузить</button>
          <button class="studio-btn" onclick="previewProtected('/house-image')" ${houseUrl ? '' : 'disabled'}>👁 Просмотр</button>
          <button class="studio-btn danger" onclick="deleteProfileImage('house')" ${houseUrl ? '' : 'disabled'}>🗑 Удалить</button>
        </div>
      </article>
    </div>

    <div class="studio-tabs">
      <button class="studio-tab active" onclick="filterStudio('all', this)">Все</button>
      <button class="studio-tab" onclick="filterStudio('base', this)">Интерфейс</button>
      <button class="studio-tab" onclick="filterStudio('npc', this)">Облики NPC</button>
    </div>

    <div class="studio-counter">
      <span>Элементы интерфейса: <b>${document.createElement ? Object.keys(labels).filter(key => !(key.startsWith('npc_') && key !== 'npc_bg')).length : 0}</b></span>
      <span>Карточки обликов NPC: <b>${Object.keys(labels).filter(key => key.startsWith('npc_') && key !== 'npc_bg').length}</b></span>
    </div>

    <div class="theme-grid" id="themeGrid">${themeCards}</div>${adminPlayerManager()}
  `);
}

window.uploadTheme = async (key,file) => {
  if (!file) return;
  const form = new FormData();
  form.append('file',file);
  try {
    const response = await fetch(`/api/miniapp/admin/theme/${key}`,{
      method:'POST',
      headers:{'X-Telegram-Init-Data':initData},
      body:form
    });
    const body = await response.json().catch(()=>({}));
    if (!response.ok) throw new Error(body.detail || 'Ошибка загрузки');
    toast('Оформление обновлено');
    await refresh();
    go('customization');
  } catch (e) {
    toast(e.message);
  }
};


window.filterStudio = (mode, button) => {
  document.querySelectorAll(".studio-tab").forEach(item => {
    item.classList.remove("active");
  });
  button?.classList.add("active");

  document.querySelectorAll("#themeGrid .theme-item").forEach(item => {
    const isNpc = item.classList.contains("npc-appearance-item");
    const shouldHide =
      (mode === "npc" && !isNpc) ||
      (mode === "base" && isNpc);
    item.classList.toggle("hidden", shouldHide);
  });
};

window.previewTheme = key => {
  const url = state.data?.media?.[key];
  if (url) openImageViewer(url);
};

window.deleteTheme = async key => {
  if (!confirm('Удалить это изображение оформления?')) return;
  try {
    await api(`/admin/theme/${key}`, { method:'DELETE' });
    toast('Изображение удалено');
    await refresh();
    go('customization');
  } catch (e) {
    toast(e.message);
  }
};

window.previewProtected = async path => {
  const url = await protectedImage(path);
  if (url) openImageViewer(url);
  else toast('Изображение не загружено');
};

window.deleteProfileImage = async kind => {
  if (!confirm(kind === 'house' ? 'Удалить фотографию дома?' : 'Удалить портрет героя?')) return;
  try {
    const path = kind === 'house' ? '/profile/house-image' : '/profile/portrait';
    await api(path, { method:'DELETE' });
    const protectedPath = kind === 'house' ? '/house-image' : '/hero-image';
    const oldUrl = state.protectedImages.get(protectedPath);
    if (oldUrl) URL.revokeObjectURL(oldUrl);
    state.protectedImages.delete(protectedPath);
    toast('Изображение удалено');
    await refresh();
    go('customization');
  } catch (e) {
    toast(e.message);
  }
};

async function loadNpcs(silent=false){
  try{state.npcs=await api("/npcs");if(!silent)render()}catch(error){toast(error.message)}
}
function npcCard(npc){
  const dead=!npc.alive;
  const materials=(npc.upgrade_materials||[]).map(item=>`<span class="npc-material ${item.owned?'owned':'missing'}">${item.owned?'✓':'○'} ${item.name}</span>`).join('');
  const stats=npc.stats||{};
  const upgradeContent = npc.max_level
    ? `<div class="npc-max-rank">🏆 Максимальный 50-й уровень</div>`
    : npc.requires_kit
      ? `<div class="npc-upgrade-box npc-ascension-box">
          <b>✨ Возвышение до ${npc.next_level}-го уровня</b>
          <div class="npc-material-list">${materials}</div>
          <button class="btn gold" onclick="upgradeNpc(${npc.id})" ${npc.upgrade_ready?'':'disabled'}>Возвысить NPC</button>
        </div>`
      : `<div class="npc-quick-upgrade">
          <span>Ур. ${npc.level} → ${npc.next_level} · <b>${npc.upgrade_cost} 🪙</b></span>
          <button class="btn gold" onclick="upgradeNpc(${npc.id})">⬆ Улучшить</button>
        </div>`;
  return `<article class="npc-card compact-npc-card ${dead?'dead':''}">
    <div class="npc-model">
      <img src="${npc.model_url}" alt="${escapeHtml(npc.name)}" onerror="this.style.display='none'">
      <span>${npc.type==='guard'?'🛡':'🌾'}</span>
    </div>
    <div class="npc-copy">
      <div class="row npc-title-row"><h3>${escapeHtml(npc.name)}</h3><span class="badge">Ур. ${npc.level}</span></div>
      ${npc.owner_name ? `<small class="npc-owner">Владелец: ${escapeHtml(npc.owner_name)}</small>` : ''}
      <div class="npc-power-line">⚡ Сила: <b>${npc.power}</b></div>
      <div class="npc-stats-grid compact">
        <span>Сила <b>${stats.strength??0}</b></span><span>Выносливость <b>${stats.endurance??0}</b></span>
        <span>Ловкость <b>${stats.agility??0}</b></span><span>${npc.type==='guard'?'Защита':'Навык'} <b>${stats.skill??0}</b></span>
      </div>
      <div class="npc-fatigue-compact"><span>Усталость</span><b>${npc.fatigue}/100</b></div>
      <div class="bar fatigue compact"><i style="width:${npc.fatigue}%"></i></div>
      <small class="npc-status">${dead?'Погиб':npc.status==='idle'?'Свободен':`Занят: ${npc.assignment||npc.status}`}</small>
      ${upgradeContent}
      ${!dead ? (npc.type==='guard'
        ? `<div class="npc-task-grid one-action"><button class="btn gold" onclick="npcAction(${npc.id},'rest')">🛏 Отдых</button></div>`
        : `<div class="npc-task-grid compact-actions">
          <button onclick="npcAction(${npc.id},'field')">🌾 Поле</button>
          <button onclick="npcAction(${npc.id},'clean')">🧹 Уборка</button>
          <button onclick="npcAction(${npc.id},'garden')">🌿 Сад</button>
          <button onclick="npcAction(${npc.id},'toilets')">🚽 Туалеты</button>
          <button onclick="npcAction(${npc.id},'rest')">🛏 Отдых</button>
        </div>`) : ''}
    </div>
  </article>`;
}

function npcsView(){
  if(!state.npcs){setTimeout(()=>loadNpcs(),0);return section("👥 NPC",'<div class="panel">Загружаем NPC…</div>')}
  const d=state.npcs;
  return section("👥 NPC",`
    <div class="section-visual-large" ${bgStyle("npc_bg")}><div class="visual-overlay">
      <div class="eyebrow">СЛУГИ И ЗАЩИТНИКИ</div><h3>Управление NPC</h3>
      <p>Стражники защищают дом, фермеры выполняют хозяйственные поручения.</p>
    </div></div>
    ${d.shared_with ? `<div class="panel shared-household-banner">💍 Общие NPC с ${d.shared_with}</div>` : ''}
    ${d.festival?.active ? `<div class="panel festival-card"><div><div class="eyebrow">ФЕСТИВАЛЬ ЛЕТА</div><h3>Бесплатный стражник</h3><p>Награду можно забрать до ${d.festival.ends_at} включительно.</p></div><button class="btn gold" onclick="claimSummerGuard()" ${d.festival.can_claim?'':'disabled'}>${d.festival.claimed?'Получено':'Забрать'}</button></div>` : ''}
    <div class="npc-shop action-grid">
      <button class="btn gold" onclick="buyNpc('guard')">🛡 Стражник · ${d.prices.guard} 🪙</button>
      <button class="btn gold" onclick="buyNpc('peasant')">🌾 Фермер · ${d.prices.peasant} 🪙</button>
    </div>
    <div class="panel npc-rules compact-rules"><p>${d.rules.guard_time}</p><p>${d.rules.fatigue}</p></div>
    <div class="npc-list">${d.units.map(npcCard).join("")||'<div class="panel muted">У вас пока нет NPC.</div>'}</div>
  `)
}
window.buyNpc=async npc_type=>{try{await api("/npcs/buy",{method:"POST",body:JSON.stringify({npc_type})});toast("NPC приобретён");await refresh();await loadNpcs(true);render()}catch(error){toast(error.message)}};
window.npcAction=async(npc_id,action)=>{try{const r=await api("/npcs/action",{method:"POST",body:JSON.stringify({npc_id,action})});toast(r.message);await refresh();await loadNpcs(true);render()}catch(error){toast(error.message)}};
window.upgradeNpc=async npc_id=>{try{const r=await api("/npcs/upgrade",{method:"POST",body:JSON.stringify({npc_id})});toast(r.message);await refresh();await loadNpcs(true);render()}catch(error){toast(error.message)}};
window.claimSummerGuard=async()=>{try{const r=await api("/festival/summer-guard",{method:"POST"});toast(r.message);await loadNpcs(true);render()}catch(error){toast(error.message)}};

function gamesView() {
  const d=state.duels;
  if (!d) {
    setTimeout(()=>loadDuelCenter(),0);
    return section("⚔ Королевская дуэль", `<div class="panel center-panel">Загружаем арену…</div>`);
  }
  if (d.active) return section("⚔ Королевская дуэль", duelBattleView(d.active));
  const incoming=d.incoming.map(x=>`<div class="card"><div class="row"><b>${x.challenger.name} вызывает вас</b><span class="badge">Ур. ${x.challenger.level}</span></div>${duelStyleSelect()}<div class="action-grid"><button class="btn gold" onclick="acceptDuel(${x.id})">Принять</button><button class="btn secondary" onclick="declineDuel(${x.id})">Отклонить</button></div></div>`).join('');
  const players=d.players.map(p=>`<div class="duel-player-card"><img class="image-loading" data-protected-image="/duel-image/${p.id}" alt="${p.name}"><div><b>${p.name}</b><small>Ур. ${p.level} · 🏆 ${p.rating}</small><small>${p.wins} побед · ${p.losses} поражений</small></div><button class="btn gold" onclick="challengePlayer(${p.id})">Вызвать</button></div>`).join('');
  return section("⚔ Королевская дуэль", `<div class="panel duel-intro" ${bgStyle('duel_bg')}><div class="eyebrow">50% РАЗВИТИЕ · 50% СУДЬБА</div><h2>Арена Флоптропики</h2><p>Уровень, характеристики и экипировка дают половину результата. Вторая половина каждого действия определяется удачей и случайностью.</p>${duelStyleSelect()}</div>${incoming?`<h3 class="subheading">Входящие вызовы</h3><div class="cards">${incoming}</div>`:''}<h3 class="subheading">Выберите соперника</h3><div class="duel-player-list">${players||'<div class="panel">Других игроков пока нет.</div>'}</div>${d.outgoing.length?`<div class="panel">⏳ Ожидают ответа: ${d.outgoing.map(x=>x.opponent.name).join(', ')}</div>`:''}`);
}



async function loadTarotCenter() {
  try {
    state.tarot = await api("/tarot");
    render();
  } catch (error) {
    toast(error.message);
  }
}

function tarotCardVisual(card, compact=false) {
  const image = card.image_url
    ? (card.image_protected
      ? `<img class="tarot-card-image image-loading" data-protected-image="/tarot/cards/${card.id}/image" alt="${card.name}">`
      : `<img class="tarot-card-image" src="${card.image_url}" alt="${card.name}" loading="lazy" onerror="this.closest('.tarot-card-art').classList.add('image-failed');this.remove()">`)
    : `<div class="tarot-card-symbol">✦</div>`;
  return `<article class="tarot-gallery-card ${compact ? "compact" : ""}">
    <div class="tarot-card-art">${image}</div>
    <div class="tarot-card-copy">
      <span class="badge">${card.suit}</span>
      <h3>${card.name}</h3>
      <small>Добавил: ${card.owner_name}</small>
      ${compact ? "" : `<p>${card.description || card.upright_meaning}</p>`}
    </div>
  </article>`;
}

function tarotReadingResult(reading) {
  const orientation = reading.orientation === "upright"
    ? "Прямое положение"
    : "Перевёрнутое положение";
  return `<div class="tarot-result panel">
    <div class="eyebrow">ПРЕДСКАЗАНИЕ НА ${reading.reading_date}</div>
    ${tarotCardVisual(reading.card, true)}
    <h3>${orientation}</h3>
    <p><b>Ваш вопрос:</b> ${reading.question}</p>
    <p>${reading.prediction}</p>
    <div class="tarot-disclaimer">🔮 ${state.tarot.disclaimer}</div>
  </div>`;
}

function tarotView() {
  const data = state.tarot;
  if (!data) {
    setTimeout(() => loadTarotCenter(), 0);
    return section("🔮 Зал Предсказаний",
      `<div class="panel center-panel">Подготавливаем колоду…</div>`);
  }

  const userCards = data.cards.filter(card => !card.is_standard);
  const standardCards = data.cards.filter(card => card.is_standard);

  const gallery = userCards.length
    ? userCards.map(card => tarotCardVisual(card)).join("")
    : `<div class="panel muted">Игроки ещё не добавили авторские карты.</div>`;

  const history = data.history.length
    ? data.history.slice(0, 8).map(item => `
      <button class="tarot-history-item" onclick='showTarotHistory(${JSON.stringify(item.id)})'>
        <b>${item.card.name}</b>
        <span>${item.reading_date}</span>
        <small>${item.question}</small>
      </button>`).join("")
    : `<div class="muted">История раскладов пока пуста.</div>`;

  const readingArea = `
    ${data.today_reading ? tarotReadingResult(data.today_reading) : ""}
    <div class="tarot-question panel">
      <div class="eyebrow">НОВЫЙ РАСКЛАД</div>
      <h2>Что вы хотите спросить у колоды?</h2>
      <textarea id="tarotQuestionInput" maxlength="500"
        placeholder="Например: что сегодня важно для моей фракции?">${state.tarotQuestion || ""}</textarea>
      <button class="btn gold" onclick="offerTarotCards()">Перемешать колоду</button>
    </div>`;

  return section("🔮 Зал Предсказаний", `
    <div class="tarot-hero" ${bgStyle("tarot_bg")}>
      <div>
        <div class="eyebrow">МАГИЧЕСКИЙ ЗАЛ</div>
        <h2>Карта дня</h2>
        <p>Задавайте вопросы без ограничений и выбирайте одну из трёх закрытых карт.</p>
      </div>
    </div>

    ${readingArea}

    <div class="panel tarot-upload-panel">
      <div>
        <h3>Добавить свою карту</h3>
        <p>Все загруженные карты сразу появляются в общей галерее и доступны всем игрокам.</p>
      </div>
      <button class="btn secondary" onclick="openTarotUpload()">＋ Добавить карту</button>
    </div>

    <h3 class="subheading">Карты граждан</h3>
    <div class="tarot-gallery">${gallery}</div>

    <details class="panel tarot-standard-details">
      <summary>Стандартная колода · ${standardCards.length} карт</summary>
      <div class="tarot-standard-grid">
        ${standardCards.map(card => tarotCardVisual(card, true)).join("")}
      </div>
    </details>

    <h3 class="subheading">История предсказаний</h3>
    <div class="tarot-history">${history}</div>

    <div class="tarot-disclaimer">🔮 ${data.disclaimer}</div>
  `);
}

window.offerTarotCards = async () => {
  const input = $("tarotQuestionInput");
  const question = (input?.value || "").trim();
  if (question.length < 3) {
    toast("Введите вопрос");
    return;
  }
  try {
    state.tarotQuestion = question;
    state.tarotOffered = await api("/tarot/offer", {
      method: "POST",
      body: JSON.stringify({ question })
    });
    const back = state.data.media.tarot_back;
    content.innerHTML = section("🔮 Выберите карту", `
      <div class="tarot-pick-screen" ${bgStyle("tarot_bg")}>
        <h2>${question}</h2>
        <p>Выберите одну карту. После открытия изменить выбор нельзя.</p>
        <div class="tarot-pick-grid">
          ${state.tarotOffered.cards.map(card => `
            <button class="tarot-back" onclick="chooseTarotCard(${card.position})"
              ${back ? `style="background-image:url('${back}')"` : ""}>
              <span>✦</span>
            </button>`).join("")}
        </div>
      </div>`);
  } catch (error) {
    toast(error.message);
  }
};

window.chooseTarotCard = async index => {
  try {
    const result = await api("/tarot/reading", {
      method: "POST",
      body: JSON.stringify({
        question: state.tarotQuestion,
        choice_index: index
      })
    });
    toast("Карта открыта");
    state.tarot = await api("/tarot");
    state.tarotOffered = null;
    render();
  } catch (error) {
    toast(error.message);
  }
};

window.openTarotUpload = () => {
  const modal = document.createElement("div");
  modal.className = "tarot-upload-modal";
  modal.id = "tarotUploadModal";
  modal.innerHTML = `
    <form class="tarot-upload-form" onsubmit="uploadTarotCard(event)">
      <button type="button" class="viewer-close" onclick="closeTarotUpload()">✕</button>
      <h2>Новая карта</h2>
      <input name="name" maxlength="100" placeholder="Название карты" required>
      <input name="suit" maxlength="64" placeholder="Масть или категория">
      <textarea name="description" maxlength="2000" placeholder="Краткое описание"></textarea>
      <textarea name="upright_meaning" maxlength="2000" placeholder="Значение в прямом положении" required></textarea>
      <textarea name="reversed_meaning" maxlength="2000" placeholder="Значение в перевёрнутом положении" required></textarea>
      <label class="tarot-file-label">Изображение карты
        <input name="file" type="file" accept="image/*" required>
      </label>
      <button class="btn gold" type="submit">Добавить в общую галерею</button>
    </form>`;
  document.body.appendChild(modal);
  document.body.classList.add("viewer-open");
};

window.closeTarotUpload = () => {
  $("tarotUploadModal")?.remove();
  document.body.classList.remove("viewer-open");
};

window.uploadTarotCard = async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  try {
    const response = await fetch("/api/miniapp/tarot/cards", {
      method: "POST",
      headers: { "X-Telegram-Init-Data": initData },
      body: data
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.detail || "Не удалось добавить карту");
    closeTarotUpload();
    toast("Карта добавлена и видна всем игрокам");
    state.tarot = await api("/tarot");
    render();
  } catch (error) {
    toast(error.message);
  }
};

window.showTarotHistory = id => {
  const item = state.tarot?.history.find(entry => entry.id === id);
  if (!item) return;
  openImageViewer(item.card.image_url || state.data.media.tarot_back);
};

async function loadFriends() {
  if (state.friendsLoading) return;
  state.friendsLoading = true;
  state.friendsError = null;
  try {
    state.friends = await api("/friends");
  } catch (error) {
    state.friendsError = error.message;
  } finally {
    state.friendsLoading = false;
    if (state.view === "friends") render();
  }
}

function friendCard(player) {
  return `<article class="friend-card">
    <div class="friend-avatar">
      ${player.portrait_available
        ? `<img class="image-loading" data-protected-image="/friends/${player.id}/portrait" alt="${player.name}">`
        : `<span>👤</span>`}
    </div>
    <div class="friend-copy">
      <div class="row">
        <h3>${player.name}</h3>
        <span class="badge">Ур. ${player.level}</span>
      </div>
      <p>${player.title}${player.is_me ? ' · Это вы' : ''}</p>
      <small>${player.faction}</small>
      <div class="friend-card-actions">
        <button class="btn secondary" onclick="openFriend(${player.id})">Подробнее</button>
        ${player.story_available ? `<button class="btn gold" onclick="openFriendStory(${player.id})">📖 Рассказать историю</button>` : ""}
      </div>
    </div>
  </article>`;
}

function friendsView() {
  if (state.friendsError) {
    return section("👥 Друзья", `<div class="panel error-panel">
      <h3>Не удалось загрузить игроков</h3>
      <p>${state.friendsError}</p>
      <button class="btn gold" onclick="retryFriends()">Повторить</button>
    </div>`);
  }
  if (!state.friends) {
    if (!state.friendsLoading) setTimeout(loadFriends, 0);
    return section("👥 Друзья", `<div class="panel">Загружаем всех зарегистрированных игроков…</div>`);
  }
  return section("👥 Друзья", `
    <div class="friends-summary">Зарегистрировано: <b>${state.friends.players.length}</b></div>
    <div class="friends-list">
      ${state.friends.players.map(friendCard).join("") || '<div class="panel muted">Игроки ещё не зарегистрированы.</div>'}
    </div>`);
}

window.retryFriends = () => {
  state.friends = null;
  state.friendsError = null;
  loadFriends();
  render();
};

window.openFriend = id => {
  state.selectedFriend = state.friends?.players.find(player => player.id === id);
  if (!state.selectedFriend) return;
  state.view = "friend-detail";
  reportPresence("friend-detail");
  render();
};

function friendDetailView() {
  const player = state.selectedFriend;
  if (!player) {
    state.view = "friends";
    return friendsView();
  }
  const house = player.house;
  const rooms=(house?.rooms||[]).map(room=>`<article class="friend-room-card">
    <div class="friend-room-image">${room.image_available?`<img class="image-loading" data-protected-image="/friends/${player.id}/rooms/${room.id}/image" alt="${room.name}">`:'🚪'}</div>
    <div><b>${room.name}</b><small>${room.description||'Комната владения'}</small></div>
  </article>`).join('');
  return section(`👤 ${player.name}`, `
    <div class="friend-profile-hero">
      <div class="friend-profile-portrait">
        ${player.portrait_available
          ? `<img class="image-loading" data-protected-image="/friends/${player.id}/portrait" alt="${player.name}">`
          : `<span>👤</span>`}
      </div>
      <div class="panel">
        <h2>${player.name}</h2>
        <p><span class="badge">${player.title}</span> <span class="badge">Ур. ${player.level}</span></p>
        <div class="row"><span>Фракция</span><b>${player.faction}</b></div>
        <div class="row"><span>Репутация</span><b>${player.reputation}</b></div>
        ${player.spouse?`<div class="row"><span>💍 В браке</span><b>${player.spouse.name}</b></div>`:''}
      </div>
    </div>
    ${player.story_available ? `<button class="btn story-button" onclick="openFriendStory(${player.id})">📖 Рассказать историю ${escapeHtml(player.name)}</button>` : ""}
    <h3 class="subheading">🏰 В гостях</h3>
    <div class="friend-house-banner">
      ${house?.image_available
        ? `<img class="image-loading" data-protected-image="/friends/${player.id}/house-image" alt="${house.name}">`
        : `<div class="upload-placeholder"><span class="upload-symbol">🏰</span><p>Фото владения не загружено</p></div>`}
      <div class="house-photo-caption"><h2>${house?.name || "Владение не создано"}</h2><p>${house?.location || ""}</p></div>
    </div>
    ${house ? `<div class="panel">
      <div class="row"><span>Уровень дома</span><b>${house.level}</b></div>
      <div class="row"><span>Прочность</span><b>${house.integrity}/100</b></div>
      <div class="row"><span>Чистота</span><b>${house.cleanliness}/100</b></div>
      <p>${house.description || ""}</p>
      ${!player.is_me ? `<button class="btn gold" onclick="repairFriendHouse(${player.id})" ${house.integrity>=100?'disabled':''}>🤝 Помочь с ремонтом · 12 🪙</button>` : ''}
    </div>
    <h3 class="subheading">🚪 Комнаты</h3><div class="friend-room-list">${rooms||'<div class="panel muted">Комнат пока нет.</div>'}</div>` : ""}
    <button class="btn secondary" onclick="go('friends')">← Вернуться к игрокам</button>`);
}

window.openFriendStory = async id => {
  try {
    state.selectedStory = await api(`/friends/${id}/story`);
    state.selectedStory.completion_reported = false;
    state.storyIndex = 0;
    if (state.selectedStory.parts.length === 1) reportStoryCompleted(state.selectedStory);
    state.view = "friend-story";
    reportPresence("friend-story");
    render();
  } catch (error) { toast(error.message); }
};

async function reportStoryCompleted(story) {
  if (!story || story.completion_reported) return;
  story.completion_reported = true;
  try {
    const result = await api(`/friends/${story.character.id}/story/complete`, {method: "POST"});
    if (result.achievement_unlocked) {
      await refresh();
      state.view = "friend-story";
      toast(`🏆 Секретная ачивка открыта: прочитано 6 историй! +${result.reward} монет`);
    }
  } catch (_) {
    story.completion_reported = false;
  }
}

window.changeStorySlide = direction => {
  if (!state.selectedStory) return;
  const max = state.selectedStory.parts.length - 1;
  state.storyIndex = Math.max(0, Math.min(max, state.storyIndex + direction));
  if (state.storyIndex === max) reportStoryCompleted(state.selectedStory);
  render();
};

function friendStoryView() {
  const story=state.selectedStory;
  if(!story) return section("📖 История", `<div class="panel">История не загружена.</div><button class="btn secondary" onclick="go('friends')">← К игрокам</button>`);
  const part=story.parts[state.storyIndex];
  const total=story.parts.length;
  const image=part.image_available
    ? `<img class="image-loading" data-protected-image="/friends/${story.character.id}/story/${part.key}/image" alt="${escapeHtml(part.label)}">`
    : `<img class="image-loading" data-protected-image="/friends/${story.character.id}/portrait" alt="${escapeHtml(story.character.name)}">`;
  return section(`📖 История · ${escapeHtml(story.character.name)}`, `
    <article class="visual-novel-scene">
      <div class="novel-image">${image}<div class="novel-progress">${state.storyIndex+1}/${total}</div></div>
      <div class="novel-dialogue">
        <div class="novel-speaker"><span>${escapeHtml(story.character.name)}</span><small>${escapeHtml(part.label)}</small></div>
        <p>${escapeHtml(part.text).replace(/\n/g,"<br>")}</p>
      </div>
    </article>
    <div class="novel-controls">
      <button class="btn secondary" onclick="changeStorySlide(-1)" ${state.storyIndex===0?'disabled':''}>← Назад</button>
      <button class="btn gold" onclick="changeStorySlide(1)" ${state.storyIndex===total-1?'disabled':''}>Далее →</button>
    </div>
    <button class="btn secondary" onclick="openFriend(${story.character.id})">Вернуться в дом игрока</button>
  `);
}

window.repairFriendHouse=async id=>{
  try{
    const r=await api(`/friends/${id}/repair`,{method:'POST'});
    toast(r.message);
    state.friends=await api('/friends');
    state.selectedFriend=state.friends.players.find(player=>player.id===id);
    await refresh();
    state.view='friend-detail';
    render();
  }catch(error){toast(error.message)}
};

async function loadStatistics() {
  try {
    state.statistics = await api("/statistics");
    if (state.view === "statistics") render();
  } catch (error) { toast(error.message); }
}

function statisticsView() {
  if (!state.statistics) {
    setTimeout(loadStatistics, 0);
    return section("📊 Статистика", `<div class="panel">Подсчитываем результаты…</div>`);
  }
  const s = state.statistics;
  const items = [["⚔","Победы в дуэлях",s.duel_wins],["💀","Поражения",s.duel_losses],["🏆","Рейтинг дуэлей",s.duel_rating],["🔥","Серия побед",s.win_streak],["🛡","Успешные защиты",s.house_defenses_won],["👹","Нападения на дом",s.house_attacks],["🔮","Расклады Таро",s.tarot_readings],["🚪","Комнаты",s.rooms],["👥","Живые NPC",s.npcs],["⭐","Репутация",s.reputation]];
  return section("📊 Статистика", `<div class="statistics-grid">${items.map(([icon,label,value])=>`<div class="statistic-card"><span>${icon}</span><b>${value}</b><small>${label}</small></div>`).join("")}</div>`);
}

async function loadAdminPlayers() {
  if (!state.data?.is_admin) return;
  try {
    state.adminPlayers = await api("/admin/players");
    if (state.view === "customization") render();
  } catch (error) { toast(error.message); }
}

function adminPlayerManager() {
  if (!state.data?.is_admin) return "";
  if (!state.adminPlayers) {
    setTimeout(loadAdminPlayers, 0);
    return `<div class="panel">Загружаем игроков…</div>`;
  }
  const titleOptions = title => state.adminPlayers.allowed_titles.map(item =>
    `<option value="${item}" ${item === title ? "selected" : ""}>${item}</option>`
  ).join("");
  const spouseOptions = player => `<option value="">Не в браке</option>` + state.adminPlayers.players
    .filter(item=>item.id!==player.id)
    .map(item=>`<option value="${item.id}" ${item.id===player.spouse_character_id?'selected':''}>${item.name}</option>`).join('');
  return `<div class="panel admin-player-manager">
    <div class="eyebrow">УПРАВЛЕНИЕ ИГРОКАМИ</div>
    <div class="row"><h3>Титулы, браки и активность</h3><button class="text-button" onclick="refreshAdminActivity()">Обновить</button></div>
    <p class="muted">Фракция назначается через панель создателя в боте. Брак объединяет бюджет, комнаты и NPC.</p>
    <div class="admin-player-list">
      ${state.adminPlayers.players.map(player => `<article>
        <div class="row"><b>${player.name} · ур. ${player.level}</b><span class="presence-badge ${player.activity.online ? 'online' : ''}">${player.activity.online ? 'В игре' : 'Не в сети'}</span></div>
        <small>Сейчас: ${player.activity.view_label}</small>
        <small>Фракция: ${player.faction}</small>
        <label>Титул<select id="title-${player.id}">${titleOptions(player.title)}</select></label>
        <button class="btn gold" onclick="savePlayerTitle(${player.id})">Назначить титул</button>
        <label>Статус брака<select id="spouse-${player.id}">${spouseOptions(player)}</select></label>
        <button class="btn secondary" onclick="savePlayerMarriage(${player.id})">Сохранить брак</button>
      </article>`).join("")}
    </div>
  </div>`;
}

window.refreshAdminActivity = async () => {
  state.adminPlayers = null;
  render();
  await loadAdminPlayers();
};

window.savePlayerTitle = async id => {
  try {
    await api("/admin/players/title", {
      method: "POST",
      body: JSON.stringify({character_id: id, title: $(`title-${id}`).value})
    });
    toast("Титул назначен");
    await loadAdminPlayers();
  } catch (error) { toast(error.message); }
};

window.savePlayerMarriage = async id => {
  try {
    const value=$(`spouse-${id}`).value;
    await api('/admin/players/marriage',{
      method:'POST',body:JSON.stringify({character_id:id,spouse_character_id:value?Number(value):null})
    });
    toast(value?'Игроки объединены в совместный дом':'Статус брака снят');
    state.adminPlayers=null;
    await loadAdminPlayers();
    await refresh();
    state.view='customization';render();
  }catch(error){toast(error.message)}
};

async function reportPresence(view) {
  try {
    await api("/presence", {method: "POST", body: JSON.stringify({view})});
  } catch (_) {}
}

function moreView() {
  return section("✨ Разделы", `
    <div class="quick-grid">
      ${quick("🏋", "Развитие", "Распределить очки", "development", "icon_development")}
      ${quick("🛒", "Магазин", "Товары дня", "shop")}
      ${quick("🎒", "Инвентарь", "Экипировка", "inventory")}
      ${quick("🗺", "Карта", "Земли Королевства", "map")}
      ${quick("🚩", "Фракции", "Политические силы", "factions")}
      ${quick("🎲", "Игры", "Арена и экспедиции", "games")}
      ${quick("🔮", "Таро", "Предсказание и карты друзей", "tarot", "icon_tarot")}
    </div>`);
}

function render() {
  const views = {
    home: homeView,
    hero: heroView,
    house: houseView,
    development: developmentView,
    treasury: treasuryView,
    shop: shopView,
    inventory: inventoryView,
    map: mapView,
    factions: factionsView,
    games: gamesView,
    customization: customizationView,
    tarot: tarotView,
    npcs: npcsView,
    friends: friendsView,
    'friend-detail': friendDetailView,
    'friend-story': friendStoryView,
    statistics: statisticsView,
    more: moreView
  };

  applyActiveScreenBackground();
  content.innerHTML = (views[state.view] || homeView)();
  hydrateProtectedImages();
  hydrateStudioPreviews();
  const oldAdmin=document.getElementById('adminStudioButton'); if(oldAdmin) oldAdmin.remove();
  if(state.data?.is_admin && state.view!=='customization'){
    const button=document.createElement('button');button.id='adminStudioButton';button.className='admin-studio-fab';button.innerHTML=mediaUrl('icon_customization')?`<img src="${mediaUrl('icon_customization')}" alt="">`:'⚙';button.onclick=()=>go('customization');document.body.appendChild(button);
  }
  clearInterval(state.duelPoll);
  if(state.view==='games' && state.duels?.active){state.duelPoll=setInterval(()=>loadDuelCenter(true),3500);}
  if(state.view==='treasury') startWorkCountdown();
  else { clearInterval(state.workTimer); state.workTimer = null; }

  document.querySelectorAll(".bottom-nav button").forEach(button => {
    button.classList.toggle("active", button.dataset.view === state.view);
  });
}

window.openUpload = openUpload;
window.showStreakInfo = showStreakInfo;

window.go = view => {
  state.view = view;
  if(view==='games') loadDuelCenter(true);
  if(view==='house') loadEstate(true);
  if(view==='npcs') loadNpcs(true);
  if(view==='friends') loadFriends();
  if(view==='statistics') loadStatistics();
  if(view==='customization' && state.data?.is_admin) loadAdminPlayers();
  if(view==='customization' && state.data?.is_owner) loadProjectAdmins(true);
  render();
  reportPresence(view);
  tg?.HapticFeedback?.selectionChanged?.();
};

async function refresh() {
  state.data = await api("/bootstrap");
  applyThemeMedia();
  $("heroName").textContent = state.data.hero.name;
  $("gold").textContent = state.data.hero.gold;
  render();
}

window.develop = async (stat, amount) => {
  try {
    const result = await api("/development", {
      method: "POST",
      body: JSON.stringify({ stat, amount })
    });
    toast(result.faction_bonus ? `Фракционный бонус: получено +${result.gained}` : `Получено +${result.gained}`);
    await refresh();
    go("development");
  } catch (error) {
    toast(error.message);
  }
};

window.chooseProfession = async key => {
  try {
    await api("/profession", {
      method: "POST",
      body: JSON.stringify({ key })
    });
    toast("Профессия выбрана");
    await refresh();
    go("treasury");
  } catch (error) {
    toast(error.message);
  }
};

window.startWork = async () => {
  try {
    const result = await api("/work/start", { method: "POST" });
    toast(result.message);
    await refresh();
    go("treasury");
  } catch (error) {
    toast(error.message);
  }
};

window.claimWork = async () => {
  try {
    const result = await api("/work/claim", { method: "POST" });
    toast(`Получено ${result.gold} золота и ${result.xp} XP${result.title_reward ? ` · 🎁 ${result.title_reward}` : ""}`);
    await refresh();
    go("treasury");
  } catch (error) {
    toast(error.message);
  }
};

window.buy = async itemId => {
  try {
    const result = await api("/shop/buy", {
      method: "POST",
      body: JSON.stringify({ item_id: itemId })
    });
    toast(`Куплено: ${result.item}`);
    await refresh();
    go("shop");
  } catch (error) {
    toast(error.message);
  }
};

window.equip = async inventoryId => {
  try {
    const result = await api("/inventory/equip", {
      method: "POST",
      body: JSON.stringify({ inventory_id: inventoryId })
    });
    toast(`${result.name}: ${result.equipped ? "надето" : "снято"}`);
    await refresh();
    go("inventory");
  } catch (error) {
    toast(error.message);
  }
};

window.useInventoryItem = async inventory_id => {
  try {
    const result = await api("/inventory/use", {method:"POST", body:JSON.stringify({inventory_id})});
    toast(result.message);
    await refresh();
    go("inventory");
  } catch (error) { toast(error.message); }
};

window.claimDaily = async () => {
  try {
    const result = await api("/daily-reward", { method: "POST" });
    const extra = result.development
      ? ` и ${result.development} очков развития`
      : "";
    toast(`Получено ${result.gold} золота, ${result.xp} XP${extra}`);
    await refresh();
    go("home");
  } catch (error) {
    toast(error.message);
  }
};

document.querySelectorAll(".bottom-nav button").forEach(button => {
  button.addEventListener("click", () => go(button.dataset.view));
});

$("imageViewer")?.addEventListener("click", event => {
  if (event.target.id === "imageViewer") closeImageViewer();
});

(async () => {
  createParticles();

  try {
    if (!initData) throw new Error("Откройте Mini App внутри Telegram");

    await refresh();
    reportPresence(state.view);
    setInterval(() => reportPresence(state.view), 60000);

    const startParam = tg?.initDataUnsafe?.start_param || "";
    if (startParam.startsWith("attack_")) {
      state.view = "house";
      await loadEstate(true);
      render();
    }

    setTimeout(() => {
      $("loading").classList.add("hidden");
      $("app").classList.remove("hidden");
    }, 420);
  } catch (error) {
    $("loading").innerHTML = `
      <div class="portal">
        <div class="portal-core">⚠️</div>
      </div>
      <h1>Не удалось открыть Королевство</h1>
      <p>${error.message}</p>`;
  }
})();
