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
  duels: null,
  duelStyle: "guardian",
  duelPoll: null
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

      <div class="compact-reward">
        <div class="reward-mini">
          ${visualIcon("icon_daily", "🎁")}
          <div>
            <b>Ежедневная награда</b>
            <small>Серия: ${h.login_streak} дн.</small>
          </div>
        </div>
        <div class="reward-actions">
          <button class="info-btn" onclick="showStreakInfo()" aria-label="Что такое серия входов">i</button>
          <button class="btn gold reward-claim" onclick="claimDaily()" ${h.daily_reward_available ? "" : "disabled"}>
            ${h.daily_reward_available ? "Получить" : "Получено"}
          </button>
        </div>
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
        ${h.portrait_available ? `
          <img
            class="hero-portrait image-loading"
            data-protected-image="/hero-image"
            alt="Портрет ${h.name}">
        ` : `
          <div class="upload-placeholder">
            <div class="upload-symbol">👤</div>
            <h3>Портрет не загружен</h3>
            <p>Добавьте фотографию персонажа через личный чат с ботом.</p>
            <button class="btn gold" onclick="openUpload('portrait')">Загрузить</button>
          </div>
        `}
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
      ${h.image_available ? `
        <img
          class="house-photo image-loading"
          data-protected-image="/house-image"
          alt="${h.name}">
      ` : `
        <div class="upload-placeholder house-upload">
          <div class="upload-symbol">🏰</div>
          <h3>Фото владения не загружено</h3>
          <p>Добавьте изображение дома через личный чат с ботом.</p>
          <button class="btn gold" onclick="openUpload('house')">Загрузить</button>
        </div>
      `}
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
    <div class="section-visual-large treasury-visual" ${bgStyle("treasury")}>
      <div class="visual-overlay">
        <div class="eyebrow">КОРОЛЕВСКАЯ СЛУЖБА</div>
        <div class="compact-meta">
          <span>${d.hero.profession}</span>
          <span>${work.count}/2 смен</span>
          <span>${work.active ? "Работа идёт" : "Свободен"}</span>
        </div>
        <div class="action-grid">
          <button class="btn gold" onclick="startWork()">Начать смену</button>
          <button class="btn secondary" onclick="claimWork()">Получить награду</button>
        </div>
      </div>
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
        <p>Свиток +30 очков развития доступен ежедневно.</p>
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
    duel_frame:'Рамка бойца', duel_vs:'Знак VS', icon_customization:'Иконка кастомизации'
  };

  const themeCards = Object.entries(labels).map(([key,label]) => {
    const url = state.data.media[key];
    return `<article class="theme-item">
      <button class="theme-preview ${url ? '' : 'empty'}"
        ${url ? `style="background-image:url('${url}')" onclick="openImageViewer('${url}')"` : ''}>
        ${url ? '<span>Нажмите для просмотра</span>' : '<span>Изображение не задано</span>'}
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

    <h3 class="subheading">Оформление приложения</h3>
    <div class="theme-grid">${themeCards}</div>
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
    customization: customizationView,
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

  document.querySelectorAll(".bottom-nav button").forEach(button => {
    button.classList.toggle("active", button.dataset.view === state.view);
  });

  window.scrollTo({ top: 0, behavior: "smooth" });
}

window.openUpload = openUpload;
window.showStreakInfo = showStreakInfo;

window.go = view => {
  state.view = view;
  if(view==='games') loadDuelCenter(true);
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
