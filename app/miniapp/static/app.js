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
  protectedImages: new Map()
};
const $ = id => document.getElementById(id);
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

function quick(icon, title, subtitle, view, mediaKey=null) {
  return `
    <button class="quick-card" onclick="go('${view}')">
      <span class="quick-icon">${mediaKey ? visualIcon(mediaKey, icon) : icon}</span>
      <b>${title}</b>
      <small>${subtitle}</small>
    </button>`;
}

function homeView() {
  const d = state.data;
  const h = d.hero;
  const house = d.house;

  return `
    <div class="page-enter">
      <section class="hero-banner" ${bgStyle("home_bg")}>
        <div class="eyebrow">ГРАЖДАНИН КОРОЛЕВСТВА</div>
        <h2>${h.name}</h2>
        <p>${h.title} · Уровень ${h.level}</p>
        <div class="magic-divider">✦</div>
        <div class="row">
          <span>🚩 ${h.faction}</span>
          <span>✨ ${h.experience}/${h.experience_next} XP</span>
        </div>
      </section>

      <div class="panel reward-panel">
        <div>
          <div class="reward-title">${visualIcon("icon_daily", "🎁")}<div><div class="eyebrow">ЕЖЕДНЕВНЫЙ ПОДАРОК</div>
          <h3>Серия входов: ${h.login_streak} дн.</h3></div></div>
          <p class="muted">На 7-й день дополнительно выдаются очки развития.</p>
        </div>
        <button class="btn gold" onclick="claimDaily()" ${h.daily_reward_available ? "" : "disabled"}>
          ${h.daily_reward_available ? "Забрать" : "Уже получено"}
        </button>
      </div>

      <div class="quick-grid">
        ${quick("👤", "Герой", `${h.development_points} очков развития`, "hero", "icon_hero")}
        ${quick("🏰", "Владение", `Прочность ${house.integrity ?? 0}%`, "house", "icon_house")}
        ${quick("💰", "Казна", `${h.gold} золота`, "treasury", "icon_treasury")}
        ${quick("🛒", "Магазин", "5 товаров дня", "shop", "icon_shop")}
        ${quick("🗺", "Карта", "Королевство", "map", "icon_map")}
        ${quick("🎲", "Игры", "Дуэли и походы", "games", "icon_games")}
        ${quick("🚩", "Фракции", h.faction, "factions", "icon_factions")}
        ${quick("🎒", "Снаряжение", `${d.inventory.length} предметов`, "inventory", "icon_inventory")}
      </div>
    </div>`;
}

function heroView() {
  const h = state.data.hero;

  const stats = Object.entries(h.stats).map(([key, value]) => `
    <div class="stat">
      <div class="stat-head">
        <span>${statLabels[key]}</span>
        <b>${value}</b>
      </div>
      <div class="bar"><i style="width:${Math.min(100, value)}%"></i></div>
    </div>`).join("");

  return section("👤 Герой", `
    <div class="hero-profile-layout">
      <div class="portrait-stage" ${bgStyle("hero_bg")}>
        <img
          class="hero-portrait image-loading"
          data-protected-image="/hero-image"
          alt="Портрет ${h.name}">
        ${mediaUrl("frame_hero") ? `<img class="decorative-frame" src="${mediaUrl("frame_hero")}" alt="">` : ""}
        <div class="portrait-shine"></div>
      </div>

      <div class="panel hero-info-panel">
        <div class="eyebrow">ЛИЧНАЯ КАРТОЧКА</div>
        <h2>${h.name}</h2>
        <p>
          <span class="badge">${h.title}</span>
          <span class="badge">${h.faction}</span>
          <span class="badge">${h.rank}</span>
        </p>
        <div class="row">
          <span>💹 Бонус дохода уровня</span>
          <b>+${Math.round((h.income_multiplier - 1) * 100)}%</b>
        </div>
        <div class="stat">
          <div class="stat-head">
            <span>Уровень ${h.level}</span>
            <b>${h.experience}/${h.experience_next} XP</b>
          </div>
          <div class="bar">
            <i style="width:${Math.min(100, h.experience / h.experience_next * 100)}%"></i>
          </div>
        </div>
      </div>
    </div>

    <div class="panel">
      <h3>Характеристики</h3>
      ${stats}
    </div>

    <div class="panel">
      <div class="row">
        <span>Свободные очки развития</span>
        <b>${h.development_points}</b>
      </div>
      <div class="action-grid">
        <button class="btn gold" onclick="go('development')">Распределить</button>
        <button class="btn secondary" onclick="go('inventory')">Снаряжение</button>
      </div>
    </div>`);
}

function houseView() {
  const h = state.data.house;

  if (!h.name) {
    return section("🏰 Владение", `<div class="panel muted">Дом не найден</div>`);
  }

  return section("🏰 Владение", `
    <div class="house-photo-stage" ${bgStyle("house_bg")}>
      <img
        class="house-photo image-loading"
        data-protected-image="/house-image"
        alt="${h.name}">
      ${mediaUrl("frame_house") ? `<img class="decorative-frame house-frame" src="${mediaUrl("frame_house")}" alt="">` : ""}
      <div class="house-photo-caption">
        <div class="eyebrow">ЛИЧНОЕ ВЛАДЕНИЕ</div>
        <h2>${h.name}</h2>
        <p>${h.location}</p>
      </div>
    </div>

    <div class="panel">
      <p>${h.description || ""}</p>

      <div class="row"><span>⭐ Уровень</span><b>${h.level}</b></div>
      <div class="row"><span>🛡 Защита</span><b>${h.defense}</b></div>
      <div class="row"><span>✨ Энергия ремонта</span><b>${h.repair_energy}</b></div>

      <div class="stat">
        <div class="stat-head">
          <span>🏗 Прочность</span>
          <b>${h.integrity}/100</b>
        </div>
        <div class="bar"><i style="width:${h.integrity}%"></i></div>
      </div>

      
    </div>`);
}

function developmentView() {
  const h = state.data.hero;

  const cards = Object.entries(h.stats).map(([key, value]) => `
    <div class="card">
      <div class="row">
        <b>${statLabels[key]}</b>
        <span class="badge">${value}</span>
      </div>
      <div class="action-grid">
        <button class="btn secondary" onclick="develop('${key}',1)"
          ${h.development_points < 1 ? "disabled" : ""}>+1</button>
        <button class="btn gold" onclick="develop('${key}',5)"
          ${h.development_points < 5 ? "disabled" : ""}>+5</button>
      </div>
    </div>`).join("");

  return section(`🏋 Развитие · осталось ${h.development_points}`, `
    <div class="panel muted media-panel" ${bgStyle("development")}>
      Каждое очко навсегда усиливает героя и влияет на дуэли,
      экспедиции и защиту дома.
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
      <button class="btn secondary" onclick="chooseProfession('${p.key}')">
        Выбрать профессию
      </button>
    </div>`).join("");

  return section("💰 Казна", `
    <div class="panel media-panel" ${bgStyle("treasury")}>
      <div class="eyebrow">КОРОЛЕВСКАЯ СЛУЖБА</div>
      <div class="row"><span>Профессия</span><b>${d.hero.profession}</b></div>
      <div class="row"><span>Смены сегодня</span><b>${work.count}/2</b></div>
      <div class="row"><span>Статус</span><b>${work.active ? "Работа идёт" : "Свободен"}</b></div>

      <div class="action-grid">
        <button class="btn gold" onclick="startWork()">Начать смену</button>
        <button class="btn secondary" onclick="claimWork()">Получить награду</button>
      </div>
    </div>

    <div class="cards">${professions}</div>`);
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
    `<div class="panel media-panel" ${bgStyle("shop")}><p>Магический ассортимент обновляется ежедневно. Свиток +30 очков развития доступен каждый день.</p></div><div class="cards">${items}</div>`);
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
      </div>`).join("")
    : `<div class="panel muted">Инвентарь пуст</div>`;

  return section("🎒 Снаряжение", `<div class="panel media-panel inventory-cover" ${bgStyle("inventory_bg")}><p>Арсенал и магические предметы персонажа.</p></div><div class="cards">${items}</div>`);
}

function mapView() {
  return section("🗺 Карта Королевства", `
    <div class="hero-banner" ${bgStyle("map")}>
      <div class="eyebrow">ЗЕМЛИ ФЛОПТРОПИКИ</div>
      <h2>Карта Королевства</h2>
      <p>Города, владения, фракции и магические области.</p>
    </div>
    <div class="panel">
      <p>Полное изображение карты открывается командой /map в боте.</p>
    </div>`);
}

function factionsView() {
  return section("🚩 Фракции", `
    <div class="cards">
      <div class="card">
        <h3>🌅 Западная сторона</h3>
        <p>Порядок, сила и контроль территорий.</p>
      </div>
      <div class="card">
        <h3>🕊 Нейтральный Диалог</h3>
        <p>Дипломатия, баланс и переговоры.</p>
      </div>
      <div class="panel">
        <div class="row">
          <span>Ваша фракция</span>
          <b>${state.data.hero.faction}</b>
        </div>
      </div>
    </div>`);
}

function gamesView() {
  return section("🎲 Игровая арена", `
    <div class="panel media-panel" ${bgStyle("games_bg")}><p>Арена Королевства объединяет дуэли и совместные походы.</p></div><div class="cards">
      <div class="card">
        <div class="eyebrow">PVP</div>
        <h3>⚔ Королевская дуэль</h3>
        <p>Вызовите соперника командой /duel, ответив на его сообщение.</p>
      </div>
      <div class="card">
        <div class="eyebrow">CO-OP</div>
        <h3>🧭 Проклятый лабиринт</h3>
        <p>Создайте экспедицию командой /expedition. До шести игроков.</p>
      </div>
    </div>`);
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
    more: moreView
  };

  content.innerHTML = (views[state.view] || homeView)();

  

window.claimDaily = async () => {
  try {
    const result = await api("/daily-reward", { method: "POST" });
    const extra = result.development ? ` и ${result.development} очков развития` : "";
    toast(`Получено ${result.gold} золота, ${result.xp} XP${extra}`);
    await refresh();
    go("home");
  } catch (error) {
    toast(error.message);
  }
};

document.querySelectorAll(".bottom-nav button").forEach(button => {
    button.classList.toggle("active", button.dataset.view === state.view);
  });

  window.scrollTo({ top: 0, behavior: "smooth" });
}

window.go = view => {
  state.view = view;
  render();
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
    await api("/development", {
      method: "POST",
      body: JSON.stringify({ stat, amount })
    });
    toast("Характеристика улучшена");
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
    toast(`Получено ${result.gold} золота и ${result.xp} XP`);
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



window.claimDaily = async () => {
  try {
    const result = await api("/daily-reward", { method: "POST" });
    const extra = result.development ? ` и ${result.development} очков развития` : "";
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

(async () => {
  createParticles();

  try {
    if (!initData) throw new Error("Откройте Mini App внутри Telegram");

    await refresh();

    setTimeout(() => {
      $("loading").classList.add("hidden");
      $("app").classList.remove("hidden");
    }, 550);
  } catch (error) {
    $("loading").innerHTML = `
      <div class="portal">
        <div class="portal-core">⚠️</div>
      </div>
      <h1>Не удалось открыть Королевство</h1>
      <p>${error.message}</p>`;
  }
})();
