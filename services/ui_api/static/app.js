const state = {
  page: "runs",
  lang: localStorage.getItem("moscraper.ui.lang") || "ru",
  stores: [],
  runs: [],
  diagnostics: null,
  selectedRunId: null,
  publication: null,
  logOffset: 0,
  logLevel: "ALL",
  logSearch: "",
  pollTimer: null,
  logsTimer: null,
};

const $ = (id) => document.getElementById(id);

const CATEGORY_OPTIONS = [
  { value: "", labelKey: "category.all" },
  { value: "phone", labelKey: "category.phone" },
  { value: "laptop", labelKey: "category.laptop" },
  { value: "tablet", labelKey: "category.tablet" },
  { value: "tv", labelKey: "category.tv" },
  { value: "appliance", labelKey: "category.appliance" },
  { value: "accessory", labelKey: "category.accessory" },
  { value: "monitor", labelKey: "category.monitor" },
  { value: "gaming", labelKey: "category.gaming" },
];

const BRAND_SUGGESTIONS = [
  "Apple",
  "Samsung",
  "Xiaomi",
  "Redmi",
  "Honor",
  "Huawei",
  "Realme",
  "Poco",
  "Tecno",
  "Infinix",
  "Vivo",
  "Oppo",
  "OnePlus",
  "Sony",
  "LG",
];

const I18N = {
  ru: {
    "brand.subtitle": "Панель оператора",
    "nav.runs": "Запуски",
    "nav.diagnostics": "Диагностика",
    "topbar.language": "Язык",
    "button.refresh": "Обновить",
    "button.startRun": "Запустить",
    "button.reset": "Сбросить",
    "button.open": "Открыть",
    "button.stop": "Остановить",
    "button.rerun": "Повторить",
    "button.backToRuns": "Назад к запускам",
    "button.refreshDiagnostics": "Обновить диагностику",
    "button.publishPending": "Опубликовать pending",
    "runs.newRun": "Новый запуск",
    "runs.recent": "Активные / последние запуски",
    "runs.total": "всего",
    "runs.empty": "Запусков пока нет.",
    "field.store": "Магазин",
    "field.category": "Категория",
    "field.brand": "Бренд",
    "field.categoryUrl": "URL категории",
    "field.timeLimit": "Лимит времени, минут",
    "field.itemLimit": "Лимит товаров",
    "field.parseInterval": "Интервал, секунд",
    "field.runUntilStopped": "Работать до ручной остановки",
    "table.status": "Статус",
    "table.store": "Магазин",
    "table.started": "Дата и время",
    "table.duration": "Длительность",
    "table.items": "Товары",
    "kpi.elapsed": "Прошло",
    "kpi.itemsScraped": "Спарсено товаров",
    "kpi.persisted": "Сохранено",
    "kpi.pagesVisited": "Страниц",
    "kpi.errors": "Ошибки",
    "kpi.warnings": "Предупреждения",
    "summary.title": "Отчет",
    "summary.waiting": "Ждем завершения...",
    "summary.stoppedNoSummary": "Запуск остановлен вручную до штатного отчета. Посмотрите лог: часть товаров могла быть уже сохранена.",
    "summary.finishReason": "Причина завершения",
    "summary.target": "Цель",
    "summary.duration": "Длительность",
    "summary.itemsScraped": "Спарсено товаров",
    "summary.persistedItems": "Сохранено товаров",
    "summary.pagesVisited": "Страниц",
    "summary.failedPdp": "Ошибок PDP",
    "summary.specCoverage": "Покрытие характеристик",
    "summary.imageCoverage": "Покрытие изображений",
    "publication.title": "Публикация",
    "publication.subtitle": "CRM увидит товары только после публикации в RabbitMQ.",
    "publication.total": "Всего outbox",
    "publication.pending": "Pending",
    "publication.published": "Published",
    "publication.retryable": "Retryable",
    "publication.failed": "Failed",
    "publication.noRun": "Для этого запуска пока нет scrape_run_id. Дождитесь первого сохраненного товара или финального отчета.",
    "publication.publishedNotice": "Публикация завершена: claimed={claimed}, published={published}, failed={failed}.",
    "publication.errorNotice": "Ошибка публикации: {error}",
    "log.title": "Лог в реальном времени",
    "log.search": "Поиск по логу",
    "log.autoScroll": "Автопрокрутка",
    "diagnostics.title": "Диагностика",
    "diagnostics.availableStores": "Доступные магазины",
    "diagnostics.dbBackend": "DB backend",
    "diagnostics.dbStatus": "DB статус",
    "diagnostics.rabbitmqStatus": "RabbitMQ статус",
    "diagnostics.pythonVersion": "Версия Python",
    "diagnostics.lastRunLogPath": "Последний log path",
    "diagnostics.scrapyAvailable": "Scrapy доступен",
    "diagnostics.uiRegistry": "UI registry",
    "value.yes": "Да",
    "value.no": "Нет",
    "value.available": "доступен",
    "value.unavailable": "недоступен",
    "limit.prefix": "Лимит",
    "limit.untilStopped": "до ручной остановки",
    "limit.time": "время",
    "limit.items": "товары",
    "limit.interval": "интервал",
    "limit.noLimit": "без лимита",
    "target.all": "все стандартные категории",
    "target.category": "категория",
    "target.brand": "бренд",
    "target.url": "URL",
    "category.all": "Все",
    "category.phone": "Телефоны",
    "category.laptop": "Ноутбуки",
    "category.tablet": "Планшеты",
    "category.tv": "Телевизоры",
    "category.appliance": "Бытовая техника",
    "category.accessory": "Аксессуары",
    "category.monitor": "Мониторы",
    "category.gaming": "Игровая техника",
    "notice.limitRequired": "Укажите лимит времени, лимит товаров или включите работу до ручной остановки.",
    "tooltip.refresh": "Обновить данные",
    "tooltip.category": "Ограничивает стартовые категории магазина. Если оставить пустым, парсер использует стандартные категории магазина.",
    "tooltip.brand": "Фильтрует товары по бренду перед сохранением. Например: Apple или iPhone.",
    "tooltip.categoryUrl": "Точный URL категории магазина. Если указан, он заменяет стандартные стартовые категории.",
    "tooltip.timeLimit": "Скрапер остановится по достижении лимита. Оставьте пустым, если лимит не нужен.",
    "tooltip.itemLimit": "Максимальное число спарсенных товаров. Оставьте пустым, если лимит не нужен.",
    "tooltip.parseInterval": "Пауза между запросами Scrapy. Например, 3 означает примерно один запрос раз в 3 секунды. Оставьте пустым, если интервал не нужен.",
    "status.starting": "стартует",
    "status.running": "работает",
    "status.stopping": "останавливается",
    "status.completed": "завершен",
    "status.failed": "ошибка",
    "status.stopped": "остановлен",
    "status.published": "опубликован",
    "status.unknown": "неизвестно",
    "reason.closespider_itemcount": "достигнут лимит товаров",
    "reason.closespider_timeout": "достигнут лимит времени",
    "reason.manual stop": "ручная остановка",
    "reason.manual stop requested": "запрошена ручная остановка",
  },
  uz: {
    "brand.subtitle": "Operator paneli",
    "nav.runs": "Ishga tushirishlar",
    "nav.diagnostics": "Diagnostika",
    "topbar.language": "Til",
    "button.refresh": "Yangilash",
    "button.startRun": "Ishga tushirish",
    "button.reset": "Tozalash",
    "button.open": "Ochish",
    "button.stop": "To'xtatish",
    "button.rerun": "Qayta ishga tushirish",
    "button.backToRuns": "Ro'yxatga qaytish",
    "button.refreshDiagnostics": "Diagnostikani yangilash",
    "button.publishPending": "Pending ni publikatsiya qilish",
    "runs.newRun": "Yangi ishga tushirish",
    "runs.recent": "Faol / so'nggi ishlar",
    "runs.total": "jami",
    "runs.empty": "Hali ishga tushirishlar yo'q.",
    "field.store": "Do'kon",
    "field.category": "Kategoriya",
    "field.brand": "Brend",
    "field.categoryUrl": "Kategoriya URL",
    "field.timeLimit": "Vaqt limiti, daqiqa",
    "field.itemLimit": "Mahsulot limiti",
    "field.parseInterval": "Interval, soniya",
    "field.runUntilStopped": "Qo'lda to'xtatilguncha ishlasin",
    "table.status": "Holat",
    "table.store": "Do'kon",
    "table.started": "Sana va vaqt",
    "table.duration": "Davomiylik",
    "table.items": "Mahsulotlar",
    "kpi.elapsed": "O'tgan vaqt",
    "kpi.itemsScraped": "Yig'ilgan mahsulotlar",
    "kpi.persisted": "Saqlangan",
    "kpi.pagesVisited": "Sahifalar",
    "kpi.errors": "Xatolar",
    "kpi.warnings": "Ogohlantirishlar",
    "summary.title": "Hisobot",
    "summary.waiting": "Tugashini kutyapmiz...",
    "summary.stoppedNoSummary": "Ish qo'lda to'xtatildi, yakuniy hisobot shakllanmadi. Logni tekshiring: ayrim mahsulotlar saqlangan bo'lishi mumkin.",
    "summary.finishReason": "Tugash sababi",
    "summary.target": "Maqsad",
    "summary.duration": "Davomiylik",
    "summary.itemsScraped": "Yig'ilgan mahsulotlar",
    "summary.persistedItems": "Saqlangan mahsulotlar",
    "summary.pagesVisited": "Sahifalar",
    "summary.failedPdp": "PDP xatolari",
    "summary.specCoverage": "Xususiyatlar qamrovi",
    "summary.imageCoverage": "Rasmlar qamrovi",
    "publication.title": "Publikatsiya",
    "publication.subtitle": "CRM mahsulotlarni faqat RabbitMQ ga publikatsiyadan keyin ko'radi.",
    "publication.total": "Jami outbox",
    "publication.pending": "Pending",
    "publication.published": "Published",
    "publication.retryable": "Retryable",
    "publication.failed": "Failed",
    "publication.noRun": "Bu ish uchun hali scrape_run_id yo'q. Birinchi saqlangan mahsulotni yoki yakuniy hisobotni kuting.",
    "publication.publishedNotice": "Publikatsiya yakunlandi: claimed={claimed}, published={published}, failed={failed}.",
    "publication.errorNotice": "Publikatsiya xatosi: {error}",
    "log.title": "Jonli log",
    "log.search": "Log bo'yicha qidirish",
    "log.autoScroll": "Avto-scroll",
    "diagnostics.title": "Diagnostika",
    "diagnostics.availableStores": "Mavjud do'konlar",
    "diagnostics.dbBackend": "DB backend",
    "diagnostics.dbStatus": "DB holati",
    "diagnostics.rabbitmqStatus": "RabbitMQ holati",
    "diagnostics.pythonVersion": "Python versiyasi",
    "diagnostics.lastRunLogPath": "Oxirgi log path",
    "diagnostics.scrapyAvailable": "Scrapy mavjud",
    "diagnostics.uiRegistry": "UI registry",
    "value.yes": "Ha",
    "value.no": "Yo'q",
    "value.available": "mavjud",
    "value.unavailable": "mavjud emas",
    "limit.prefix": "Limit",
    "limit.untilStopped": "qo'lda to'xtatilguncha",
    "limit.time": "vaqt",
    "limit.items": "mahsulot",
    "limit.interval": "interval",
    "limit.noLimit": "limitsiz",
    "target.all": "barcha standart kategoriyalar",
    "target.category": "kategoriya",
    "target.brand": "brend",
    "target.url": "URL",
    "category.all": "Hammasi",
    "category.phone": "Telefonlar",
    "category.laptop": "Noutbuklar",
    "category.tablet": "Planshetlar",
    "category.tv": "Televizorlar",
    "category.appliance": "Maishiy texnika",
    "category.accessory": "Aksessuarlar",
    "category.monitor": "Monitorlar",
    "category.gaming": "O'yin texnikasi",
    "notice.limitRequired": "Vaqt limiti, mahsulot limiti yoki qo'lda to'xtatish rejimini tanlang.",
    "tooltip.refresh": "Ma'lumotlarni yangilash",
    "tooltip.category": "Do'konning boshlang'ich kategoriyalarini cheklaydi. Bo'sh bo'lsa, standart kategoriyalar ishlatiladi.",
    "tooltip.brand": "Saqlashdan oldin mahsulotlarni brend bo'yicha filtrlaydi. Masalan: Apple yoki iPhone.",
    "tooltip.categoryUrl": "Do'kon kategoriyasining aniq URL manzili. To'ldirilsa, standart start kategoriyalar o'rniga ishlatiladi.",
    "tooltip.timeLimit": "Limitga yetganda skraper to'xtaydi. Limit kerak bo'lmasa bo'sh qoldiring.",
    "tooltip.itemLimit": "Yig'iladigan mahsulotlarning maksimal soni. Limit kerak bo'lmasa bo'sh qoldiring.",
    "tooltip.parseInterval": "Scrapy so'rovlari orasidagi pauza. Masalan, 3 taxminan har 3 soniyada bitta so'rov degani. Interval kerak bo'lmasa bo'sh qoldiring.",
    "status.starting": "boshlanmoqda",
    "status.running": "ishlamoqda",
    "status.stopping": "to'xtatilmoqda",
    "status.completed": "yakunlandi",
    "status.failed": "xato",
    "status.stopped": "to'xtatildi",
    "status.published": "publikatsiya qilingan",
    "status.unknown": "noma'lum",
    "reason.closespider_itemcount": "mahsulot limiti to'ldi",
    "reason.closespider_timeout": "vaqt limiti to'ldi",
    "reason.manual stop": "qo'lda to'xtatildi",
    "reason.manual stop requested": "qo'lda to'xtatish so'raldi",
  },
};

if (!I18N[state.lang]) state.lang = "ru";

function t(key) {
  return (I18N[state.lang] && I18N[state.lang][key]) || I18N.ru[key] || key;
}

function applyTranslations() {
  document.documentElement.lang = state.lang === "uz" ? "uz" : "ru";
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    node.setAttribute("placeholder", t(node.dataset.i18nPlaceholder));
  });
  document.querySelectorAll("[data-tip-key]").forEach((node) => {
    node.dataset.tip = t(node.dataset.tipKey);
  });
  const languageSelect = $("languageSelect");
  if (languageSelect) languageSelect.value = state.lang;
}

function setLanguage(lang) {
  state.lang = I18N[lang] ? lang : "ru";
  localStorage.setItem("moscraper.ui.lang", state.lang);
  applyTranslations();
  renderAll();
  if (state.selectedRunId) refreshSelectedRun();
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return payload;
}

function formatDuration(seconds) {
  const total = Number(seconds || 0);
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  const secSuffix = state.lang === "uz" ? "s" : "с";
  const minSuffix = state.lang === "uz" ? "daq" : "м";
  const hourSuffix = state.lang === "uz" ? "soat" : "ч";
  if (minutes <= 0) return `${rest}${secSuffix}`;
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  if (hours <= 0) return `${minutes}${minSuffix} ${String(rest).padStart(2, "0")}${secSuffix}`;
  return `${hours}${hourSuffix} ${String(mins).padStart(2, "0")}${minSuffix}`;
}

function shortTime(value) {
  if (!value) return "-";
  try {
    return new Date(value).toLocaleString(undefined, {
      month: "2-digit",
      day: "2-digit",
      year: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return value;
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function statusBadge(status) {
  const raw = status || "unknown";
  const safe = escapeHtml(raw);
  return `<span class="badge ${safe}">${escapeHtml(t(`status.${raw}`))}</span>`;
}

function runDisplayStatus(run) {
  return run.display_status || run.status || "unknown";
}

function runItemsCount(run) {
  const values = [
    run.items_scraped,
    run.items_persisted,
    run.summary?.items_scraped,
    run.summary?.items_persisted,
    run.publication_status?.total,
    run.publication_status?.published,
  ].map((value) => Number(value || 0));
  return Math.max(...values, 0);
}

function runLimitLabel(run) {
  if (run.run_until_stopped) return t("limit.untilStopped");
  const parts = [];
  if (run.time_limit_minutes) parts.push(`${t("limit.time")} ${run.time_limit_minutes} ${state.lang === "uz" ? "daq" : "мин"}`);
  if (run.item_limit) parts.push(`${t("limit.items")} ${run.item_limit}`);
  if (run.parse_interval_seconds) parts.push(`${t("limit.interval")} ${run.parse_interval_seconds}${state.lang === "uz" ? "s" : "с"}`);
  return parts.length ? parts.join(" + ") : t("limit.noLimit");
}

function categoryLabel(value) {
  if (!value) return "";
  const option = CATEGORY_OPTIONS.find((item) => item.value === value);
  return option ? t(option.labelKey) : value;
}

function runTargetValue(run) {
  const parts = [];
  if (run.category) parts.push(`${t("target.category")}: ${categoryLabel(run.category)}`);
  if (run.brand) parts.push(`${t("target.brand")}: ${run.brand}`);
  if (run.category_url) parts.push(`${t("target.url")}: ${run.category_url}`);
  return parts.length ? parts.join(" / ") : t("target.all");
}

function translateReason(reason) {
  if (!reason) return "-";
  return t(`reason.${reason}`) === `reason.${reason}` ? reason : t(`reason.${reason}`);
}

function showNotice(text, isError = false) {
  const notice = $("formNotice");
  notice.textContent = text;
  notice.classList.toggle("error", isError);
  notice.classList.toggle("hidden", !text);
}

async function loadInitial() {
  await Promise.all([loadDiagnostics(), loadStores(), loadRuns()]);
  applyTranslations();
  renderAll();
  startPolling();
}

async function loadStores() {
  const payload = await api("/api/stores");
  state.stores = payload.stores || [];
}

async function loadDiagnostics() {
  state.diagnostics = await api("/api/health");
}

async function loadRuns() {
  const payload = await api("/api/runs");
  state.runs = payload.runs || [];
}

function renderAll() {
  renderTopbar();
  renderStores();
  renderTargetControls();
  renderRunsTable();
  renderDiagnostics();
}

function renderTopbar() {
  const diag = state.diagnostics || {};
  $("dbStatus").textContent = `${diag.dbBackend || "..."} / ${translateValue(diag.dbStatus)}`;
  $("rabbitStatus").textContent = translateValue(diag.rabbitmqStatus);
  $("pythonStatus").textContent = diag.pythonVersion || "...";
  $("dbDot").className = `dot ${diag.dbStatus === "available" ? "ok" : "bad"}`;
  $("rabbitDot").className = `dot ${diag.rabbitmqStatus === "available" ? "ok" : "bad"}`;
}

function translateValue(value) {
  if (!value) return "...";
  return t(`value.${value}`) === `value.${value}` ? value : t(`value.${value}`);
}

function renderStores() {
  const select = $("storeSelect");
  select.innerHTML = state.stores.map((store) => `<option value="${escapeHtml(store)}">${escapeHtml(store)}</option>`).join("");
}

function renderTargetControls() {
  const categorySelect = $("categorySelect");
  const selectedCategory = categorySelect.value;
  categorySelect.innerHTML = CATEGORY_OPTIONS.map(
    (option) => `<option value="${escapeHtml(option.value)}">${escapeHtml(t(option.labelKey))}</option>`
  ).join("");
  categorySelect.value = CATEGORY_OPTIONS.some((option) => option.value === selectedCategory) ? selectedCategory : "";

  $("brandOptions").innerHTML = BRAND_SUGGESTIONS.map((brand) => `<option value="${escapeHtml(brand)}"></option>`).join("");
}

function renderRunsTable() {
  $("runsCount").textContent = `${state.runs.length} ${t("runs.total")}`;
  const rows = state.runs
    .map((run) => {
      return `<tr class="run-row" data-open-run="${escapeHtml(run.id)}" tabindex="0" role="button">
        <td>${statusBadge(runDisplayStatus(run))}</td>
        <td>${escapeHtml(run.store)}</td>
        <td>${shortTime(run.started_at)}</td>
        <td>${formatDuration(run.duration_seconds)}</td>
        <td>${runItemsCount(run)}</td>
      </tr>`;
    })
    .join("");
  $("runsTable").innerHTML = rows || `<tr><td colspan="5" class="empty">${escapeHtml(t("runs.empty"))}</td></tr>`;
}

function renderDiagnostics() {
  const diag = state.diagnostics || {};
  const rows = [
    [t("diagnostics.availableStores"), (diag.stores || []).join(", ")],
    [t("diagnostics.dbBackend"), diag.dbBackend],
    [t("diagnostics.dbStatus"), translateValue(diag.dbStatus)],
    [t("diagnostics.rabbitmqStatus"), translateValue(diag.rabbitmqStatus)],
    [t("diagnostics.pythonVersion"), diag.pythonVersion],
    [t("diagnostics.lastRunLogPath"), diag.lastRunLogPath || "-"],
    [t("diagnostics.scrapyAvailable"), diag.scrapyAvailable ? t("value.yes") : t("value.no")],
    [t("diagnostics.uiRegistry"), diag.uiRegistryPath || "-"],
  ];
  $("diagnosticsTable").innerHTML = rows
    .map(([label, value]) => `<tr><td class="muted-text">${escapeHtml(label)}</td><td>${escapeHtml(value)}</td></tr>`)
    .join("");
}

async function startRun(event) {
  event.preventDefault();
  showNotice("");
  const runUntilStopped = $("runUntilStopped").checked;
  const payload = {
    store: $("storeSelect").value,
    category: $("categorySelect").value || null,
    brand: $("brandInput").value.trim() || null,
    category_url: $("categoryUrl").value.trim() || null,
    run_until_stopped: runUntilStopped,
    time_limit_minutes: runUntilStopped ? null : $("timeLimit").value || null,
    item_limit: runUntilStopped ? null : $("itemLimit").value || null,
    parse_interval_seconds: $("parseInterval").value || null,
  };
  if (!runUntilStopped && !payload.time_limit_minutes && !payload.item_limit) {
    showNotice(t("notice.limitRequired"), true);
    return;
  }
  try {
    const run = await api("/api/runs", { method: "POST", body: JSON.stringify(payload) });
    await loadRuns();
    renderRunsTable();
    openRun(run.id);
  } catch (error) {
    showNotice(error.message, true);
  }
}

function resetForm() {
  $("categorySelect").value = "";
  $("brandInput").value = "";
  $("categoryUrl").value = "";
  $("timeLimit").value = "";
  $("itemLimit").value = "";
  $("parseInterval").value = "";
  $("runUntilStopped").checked = false;
  updateLimitInputs();
  showNotice("");
}

function updateLimitInputs() {
  const disabled = $("runUntilStopped").checked;
  $("timeLimit").disabled = disabled;
  $("itemLimit").disabled = disabled;
}

async function openRun(runId) {
  state.selectedRunId = runId;
  state.logOffset = 0;
  $("logOutput").textContent = "";
  $("runsListView").classList.add("hidden");
  $("runDetailView").classList.remove("hidden");
  await refreshSelectedRun();
  startLogPolling();
}

function backToRuns() {
  state.selectedRunId = null;
  stopLogPolling();
  $("runDetailView").classList.add("hidden");
  $("runsListView").classList.remove("hidden");
}

async function refreshSelectedRun() {
  if (!state.selectedRunId) return;
  const run = await api(`/api/runs/${encodeURIComponent(state.selectedRunId)}`);
  renderRunDetail(run);
  await loadPublication(state.selectedRunId);
}

async function loadPublication(runId = state.selectedRunId) {
  if (!runId) return;
  const payload = await api(`/api/publication/status?run_id=${encodeURIComponent(runId)}`);
  state.publication = payload;
  renderPublication(payload.status || {});
}

function renderRunDetail(run) {
  const active = ["running", "starting", "stopping"].includes(run.status);
  $("detailTitle").innerHTML = `${escapeHtml(run.store)} / ${statusBadge(runDisplayStatus(run))}`;
  $("stopRunBtn").classList.toggle("hidden", !active);
  $("kpiElapsed").textContent = formatDuration(run.duration_seconds);
  $("kpiItems").textContent = Number(run.items_scraped || run.summary?.items_scraped || 0);
  $("kpiPersisted").textContent = Number(run.items_persisted || run.summary?.items_persisted || 0);
  $("kpiPages").textContent = Number(run.pages_visited || run.summary?.pages_visited || 0);
  $("kpiErrors").textContent = Number(run.errors || 0);
  $("kpiWarnings").textContent = Number(run.warnings || 0);
  $("limitLabel").textContent = `${t("limit.prefix")}: ${runLimitLabel(run)}`;

  const summary = run.summary || {};
  if (active && !Object.keys(summary).length) {
    $("summaryPanel").innerHTML = `<div class="empty">${escapeHtml(t("summary.waiting"))}</div>`;
    return;
  }
  if (!Object.keys(summary).length && run.status === "stopped") {
    $("summaryPanel").innerHTML = `<div class="empty">${escapeHtml(t("summary.stoppedNoSummary"))}</div>`;
    return;
  }
  const rows = [
    [t("summary.finishReason"), translateReason(run.stop_reason || summary.finish_reason)],
    [t("summary.target"), runTargetValue(run)],
    [t("summary.duration"), formatDuration(run.duration_seconds)],
    [t("summary.itemsScraped"), summary.items_scraped ?? run.items_scraped ?? 0],
    [t("summary.persistedItems"), summary.items_persisted ?? run.items_persisted ?? 0],
    [t("summary.pagesVisited"), summary.pages_visited ?? run.pages_visited ?? 0],
    [t("summary.failedPdp"), summary.failed_pdp ?? 0],
    [t("summary.specCoverage"), percent(summary.spec_coverage_percent)],
    [t("summary.imageCoverage"), percent(summary.image_coverage_percent)],
  ];
  $("summaryPanel").innerHTML = rows
    .map(([label, value]) => `<div class="summary-item"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`)
    .join("");
}

function renderPublication(status) {
  const rows = [
    [t("publication.total"), status.total ?? 0],
    [t("publication.pending"), status.pending ?? 0],
    [t("publication.published"), status.published ?? 0],
    [t("publication.retryable"), status.retryable ?? 0],
    [t("publication.failed"), status.failed ?? 0],
  ];
  $("publicationPanel").innerHTML = rows
    .map(([label, value]) => `<div class="summary-item"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`)
    .join("");

  const canPublish = Boolean(status.scrape_run_id) && Number(status.pending || 0) > 0;
  $("publishPendingBtn").disabled = !canPublish;
  if (!status.scrape_run_id) {
    showPublicationNotice(t("publication.noRun"), false);
  } else if (!$("publicationNotice").classList.contains("error")) {
    showPublicationNotice("", false);
  }
}

function showPublicationNotice(text, isError = false) {
  const notice = $("publicationNotice");
  notice.textContent = text;
  notice.classList.toggle("error", isError);
  notice.classList.toggle("hidden", !text);
}

function formatTemplate(template, values) {
  return template.replace(/\{(\w+)\}/g, (_, key) => String(values[key] ?? ""));
}

async function publishPending() {
  if (!state.selectedRunId) return;
  showPublicationNotice("", false);
  $("publishPendingBtn").disabled = true;
  try {
    const payload = await api("/api/publication/publish-once", {
      method: "POST",
      body: JSON.stringify({ run_id: state.selectedRunId }),
    });
    const result = payload.result || {};
    await loadPublication(state.selectedRunId);
    showPublicationNotice(formatTemplate(t("publication.publishedNotice"), result), false);
  } catch (error) {
    showPublicationNotice(formatTemplate(t("publication.errorNotice"), { error: error.message }), true);
  }
}

function percent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return `${value}%`;
}

async function pollLogs() {
  if (!state.selectedRunId) return;
  const params = new URLSearchParams({
    offset: String(state.logOffset),
    level: state.logLevel,
    q: state.logSearch,
  });
  const payload = await api(`/api/runs/${encodeURIComponent(state.selectedRunId)}/logs?${params.toString()}`);
  state.logOffset = payload.next_offset || state.logOffset;
  appendLogs(payload.lines || []);
}

function appendLogs(lines) {
  if (!lines.length) return;
  const output = $("logOutput");
  const fragment = lines
    .map((line) => {
      const prefix = `${line.timestamp || ""} ${line.level.padEnd(5, " ")}`;
      return `<span class="log-line"><span class="level-${line.level}">${escapeHtml(prefix)}</span> ${escapeHtml(line.message)}</span>`;
    })
    .join("");
  output.insertAdjacentHTML("beforeend", fragment);
  if ($("autoScroll").checked) output.scrollTop = output.scrollHeight;
}

function resetLogStream() {
  state.logOffset = 0;
  $("logOutput").textContent = "";
  pollLogs();
}

function startPolling() {
  if (state.pollTimer) window.clearInterval(state.pollTimer);
  state.pollTimer = window.setInterval(async () => {
    await loadRuns();
    renderRunsTable();
    if (state.selectedRunId) refreshSelectedRun();
  }, 2000);
}

function startLogPolling() {
  stopLogPolling();
  pollLogs();
  state.logsTimer = window.setInterval(pollLogs, 1200);
}

function stopLogPolling() {
  if (state.logsTimer) window.clearInterval(state.logsTimer);
  state.logsTimer = null;
}

async function stopRun(runId = state.selectedRunId) {
  if (!runId) return;
  await api(`/api/runs/${encodeURIComponent(runId)}/stop`, { method: "POST" });
  await loadRuns();
  renderRunsTable();
  if (state.selectedRunId === runId) refreshSelectedRun();
}

function rerunSelected() {
  const run = state.runs.find((item) => item.id === state.selectedRunId);
  if (!run) return;
  backToRuns();
  $("storeSelect").value = run.store;
  $("categorySelect").value = run.category || "";
  $("brandInput").value = run.brand || "";
  $("categoryUrl").value = run.category_url || "";
  $("runUntilStopped").checked = Boolean(run.run_until_stopped);
  $("timeLimit").value = run.time_limit_minutes || "";
  $("itemLimit").value = run.item_limit || "";
  $("parseInterval").value = run.parse_interval_seconds || "";
  updateLimitInputs();
}

function switchPage(page) {
  state.page = page;
  document.querySelectorAll(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.page === page));
  $("runsPage").classList.toggle("hidden", page !== "runs");
  $("diagnosticsPage").classList.toggle("hidden", page !== "diagnostics");
}

function attachEvents() {
  $("languageSelect").addEventListener("change", (event) => setLanguage(event.target.value));
  $("runForm").addEventListener("submit", startRun);
  $("resetFormBtn").addEventListener("click", resetForm);
  $("runUntilStopped").addEventListener("change", updateLimitInputs);
  $("refreshBtn").addEventListener("click", async () => {
    await Promise.all([loadDiagnostics(), loadRuns()]);
    renderAll();
  });
  $("refreshDiagnosticsBtn").addEventListener("click", async () => {
    await loadDiagnostics();
    renderTopbar();
    renderDiagnostics();
  });
  $("backToRunsBtn").addEventListener("click", backToRuns);
  $("stopRunBtn").addEventListener("click", () => stopRun());
  $("rerunBtn").addEventListener("click", rerunSelected);
  $("refreshPublicationBtn").addEventListener("click", () => loadPublication());
  $("publishPendingBtn").addEventListener("click", publishPending);
  $("logSearch").addEventListener("input", (event) => {
    state.logSearch = event.target.value;
    resetLogStream();
  });
  $("levelFilter").addEventListener("click", (event) => {
    if (!event.target.matches("button")) return;
    state.logLevel = event.target.dataset.level;
    document.querySelectorAll("#levelFilter button").forEach((button) => button.classList.toggle("active", button === event.target));
    resetLogStream();
  });
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => switchPage(button.dataset.page));
  });
  $("runsTable").addEventListener("click", (event) => {
    const row = event.target.closest("[data-open-run]");
    if (row) openRun(row.dataset.openRun);
  });
  $("runsTable").addEventListener("keydown", (event) => {
    if (!["Enter", " "].includes(event.key)) return;
    const row = event.target.closest("[data-open-run]");
    if (!row) return;
    event.preventDefault();
    openRun(row.dataset.openRun);
  });
}

attachEvents();
loadInitial().catch((error) => {
  showNotice(error.message, true);
  console.error(error);
});
