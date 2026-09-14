/* ==========================================================================
   Общий скрипт сайта
   Подключается на всех страницах: <script src="/assets/app.js" defer></script>
   ==========================================================================

   ОДИН ФАЙЛ НА ВЕСЬ САЙТ. Каждый блок сам проверяет, есть ли на странице
   элементы, с которыми он работает, и молча выходит, если их нет. Поэтому
   фильтр статей не мешает городской странице, а связанные селекты главной —
   политике конфиденциальности.

   --------------------------------------------------------------------------
   КОНФИГУРАЦИЯ ЧИТАЕТСЯ ИЗ <body>, А НЕ ЗАШИТА В КОД

   Внешний JS один на все 16 страниц, поэтому подставлять в него токены
   вида {{PHONE_E164}} нельзя — телефон может отличаться по городам.
   Значения приходят через data-атрибуты:

     <body class="page-city"
           data-phone="+70000000000"
           data-metrika="00000000"
           data-modal-fallback="#lead-form">

     data-phone           телефон в формате E.164, для запасного сценария
                          модалки в старых браузерах
     data-metrika         номер счётчика Яндекс.Метрики. Пока не указан,
                          цели просто не отправляются — ошибок не будет
     data-modal-fallback  селектор блока, к которому прокручиваем, если
                          браузер не поддерживает <dialog>. По умолчанию
                          #lead-form

   --------------------------------------------------------------------------
   ЦЕЛИ ЯНДЕКС.МЕТРИКИ

   Раньше код целей лежал закомментированным в каждом шаблоне — это значило
   восемь мест, где легко забыть раскомментировать. Теперь цели отправляются
   всегда, но функция goal() молча выходит, если счётчика на странице нет
   или data-metrika не заполнен. Заводить цели в интерфейсе Метрики нужно
   с теми же идентификаторами:

     call           клик по любому телефону        (тип: JavaScript-событие)
     form_send      отправка любой формы           (тип: JavaScript-событие)
     service_click  клик по услуге на главной      (тип: JavaScript-событие)
     city_click     клик по городу в списке        (тип: JavaScript-событие)
     blog_to_city   переход из статьи в город      (тип: JavaScript-событие)
     page_404       открытие страницы 404          (тип: JavaScript-событие)

   ⚠️ Главная конверсия сайта настраивается НЕ здесь, а в интерфейсе Метрики:
   тип «Посещение страниц», условие «url: содержит /spasibo/». Цель на submit
   срабатывает и тогда, когда отправка провалилась, — доверять надо странице
   благодарности.

   --------------------------------------------------------------------------
   ⚠️ SERVICE_CITIES НИЖЕ — ЭТО КАРТА САЙТА В КОДЕ.
   Держите её синхронно со структурой: добавили город к услуге — допишите
   и здесь, иначе он не появится в формах и заявок оттуда не будет.
   ========================================================================== */

(function () {
  'use strict';

  var body = document.body;
  var CFG = {
    phone: body.getAttribute('data-phone') || '',
    metrika: body.getAttribute('data-metrika') || '',
    modalFallback: body.getAttribute('data-modal-fallback') || '#lead-form'
  };

  /* Какие города есть у какой услуги. Матрица не прямоугольная:
     в Нягани только стиральные машины, в Ханты-Мансийске их нет. */
  var SERVICE_CITIES = {
    'Ремонт стиральных машин': ['Сургут', 'Нижневартовск', 'Нефтеюганск', 'Нягань'],
    'Ремонт холодильников':    ['Сургут', 'Нижневартовск', 'Нефтеюганск', 'Ханты-Мансийск'],
    'Компьютерная помощь':     ['Сургут', 'Нижневартовск', 'Нефтеюганск', 'Ханты-Мансийск']
  };

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  /* ---------- Цели Метрики ----------
     Молча выходит, если счётчик не установлен или номер не указан. */
  function goal(name, params) {
    if (!CFG.metrika || typeof window.ym !== 'function') { return; }
    try {
      window.ym(Number(CFG.metrika), 'reachGoal', name, params || undefined);
    } catch (err) { /* аналитика не должна ломать страницу */ }
  }

  /* ======================================================================
     Выпадающие меню: закрытие по клику вне и по Esc
     <details class="js-dd"> в шапке и в переключателе городов
     ====================================================================== */
  var dropdowns = $$('details.js-dd');

  function closeDropdowns(except) {
    dropdowns.forEach(function (d) { if (d !== except) { d.open = false; } });
  }

  dropdowns.forEach(function (d) {
    d.addEventListener('toggle', function () { if (d.open) { closeDropdowns(d); } });
  });

  if (dropdowns.length) {
    document.addEventListener('click', function (e) {
      dropdowns.forEach(function (d) {
        if (d.open && !d.contains(e.target)) { d.open = false; }
      });
    });
  }

  /* ======================================================================
     Мобильное меню
     ====================================================================== */
  var burger = $('#burger');
  var mnav = $('#mobile-nav');

  function setNav(open) {
    if (!burger || !mnav) { return; }
    mnav.classList.toggle('open', open);
    burger.setAttribute('aria-expanded', open ? 'true' : 'false');
    burger.setAttribute('aria-label', open ? 'Закрыть меню' : 'Открыть меню');
    burger.textContent = open ? '✕' : '☰';
  }

  if (burger && mnav) {
    burger.addEventListener('click', function () {
      setNav(!mnav.classList.contains('open'));
    });
    mnav.addEventListener('click', function (e) {
      if (e.target.closest('a')) { setNav(false); }
    });
  }

  /* ---------- Esc закрывает всё ---------- */
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') { return; }
    closeDropdowns(null);
    if (mnav && mnav.classList.contains('open')) { setNav(false); }
  });

  /* ======================================================================
     Кнопки «показать ещё»: марки техники, полный прайс
     ====================================================================== */
  $$('[data-toggle]').forEach(function (btn) {
    var target = document.getElementById(btn.getAttribute('data-toggle'));
    if (!target) { return; }
    var closedLabel = btn.textContent;
    var openLabel = btn.getAttribute('data-label-open') || 'Свернуть';
    btn.addEventListener('click', function () {
      var willOpen = target.hidden;
      target.hidden = !willOpen;
      btn.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
      btn.textContent = willOpen ? openLabel : closedLabel;
    });
  });

  /* ======================================================================
     Модалка обратного звонка
     Запасной сценарий для браузеров без <dialog>: прокрутка к блоку из
     data-modal-fallback, а если и его нет — звонок по телефону.
     ====================================================================== */
  var modal = $('#callback-modal');

  $$('[data-modal-open]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (modal && typeof modal.showModal === 'function') {
        modal.showModal();
        return;
      }
      var target = $(CFG.modalFallback);
      if (target) {
        target.scrollIntoView({ block: 'center' });
      } else if (CFG.phone) {
        window.location.href = 'tel:' + CFG.phone;
      }
    });
  });

  $$('[data-modal-close]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (modal && modal.close) { modal.close(); }
    });
  });

  if (modal) {
    /* Клик по затемнению за пределами окна */
    modal.addEventListener('click', function (e) {
      if (e.target === modal) { modal.close(); }
    });
  }

  /* ======================================================================
     Перенос UTM-меток в скрытое поле формы
     Без этого непонятно, с какой рекламной кампании пришла заявка.
     ====================================================================== */
  try {
    var qs = window.location.search;
    if (qs && qs.length > 1) {
      $$('.js-utm').forEach(function (i) { i.value = qs.slice(0, 500); });
    }
  } catch (err) { /* приватный режим и прочие экзотические ограничения */ }

  /* ======================================================================
     Связанные селекты «услуга → город» (главная)
     Список городов пересобирается под выбранную услугу, чтобы человек
     не выбрал связку, которой у нас нет, — например «Нягань + холодильники».
     ====================================================================== */
  $$('[data-service-select]').forEach(function (serviceSel) {
    var form = serviceSel.form;
    if (!form) { return; }
    var citySel = form.querySelector('[data-city-select]');
    if (!citySel) { return; }

    var placeholder = citySel.options.length ? citySel.options[0].textContent : 'Город';

    serviceSel.addEventListener('change', function () {
      var cities = SERVICE_CITIES[serviceSel.value] || [];
      citySel.innerHTML = '';

      var head = document.createElement('option');
      head.value = '';
      head.textContent = cities.length ? 'Выберите город' : placeholder;
      head.disabled = true;
      head.selected = true;
      citySel.appendChild(head);

      cities.forEach(function (name) {
        var o = document.createElement('option');
        o.textContent = name;
        citySel.appendChild(o);
      });

      var other = document.createElement('option');
      other.value = 'Другой';
      other.textContent = 'Другой населённый пункт';
      citySel.appendChild(other);

      citySel.disabled = cities.length === 0;
    });
  });

  /* ======================================================================
     Фильтр статей по услуге (/blog/)
     Клиентский: все карточки остаются в DOM, фильтр только прячет лишние,
     поэтому поисковик видит весь список сразу.
     ====================================================================== */
  var cards = $$('.post-card');

  if (cards.length) {
    var chips = $$('.chip[data-filter]');
    var status = $('#filter-status');
    var empty = $('#empty');

    var plural = function (n, one, few, many) {
      var n10 = n % 10, n100 = n % 100;
      if (n10 === 1 && n100 !== 11) { return one; }
      if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) { return few; }
      return many;
    };

    /* Счётчики считаются из разметки — руками обновлять не нужно */
    chips.forEach(function (chip) {
      var f = chip.getAttribute('data-filter');
      var n = f === 'all' ? cards.length : cards.filter(function (c) {
        return c.getAttribute('data-service') === f;
      }).length;
      var slot = chip.querySelector('.n');
      if (slot) { slot.textContent = n; }
    });

    var applyFilter = function (filter) {
      var shown = 0;
      cards.forEach(function (card) {
        var match = filter === 'all' || card.getAttribute('data-service') === filter;
        card.hidden = !match;
        if (match) { shown++; }
      });

      $$('.filters .chip[data-filter]').forEach(function (c) {
        c.setAttribute('aria-pressed', c.getAttribute('data-filter') === filter ? 'true' : 'false');
      });

      if (status) {
        status.textContent = filter === 'all'
          ? ''
          : shown + ' ' + plural(shown, 'статья', 'статьи', 'статей') + ' в рубрике';
      }
      if (empty) { empty.classList.toggle('show', shown === 0); }
    };

    $$('[data-filter]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        applyFilter(btn.getAttribute('data-filter'));
      });
    });
  }

  /* ======================================================================
     Цели Метрики
     ====================================================================== */
  $$('[data-goal="call"]').forEach(function (a) {
    a.addEventListener('click', function () { goal('call'); });
  });

  $$('.js-form').forEach(function (f) {
    f.addEventListener('submit', function () { goal('form_send'); });
  });

  /* Клик по услуге: карточки офферов на главной, ссылки на хабы в блоге и 404 */
  $$('.offer-card a, .service-links a').forEach(function (a) {
    a.addEventListener('click', function () { goal('service_click'); });
  });

  /* Клик по городу: матрица на главной и 404, карточки городов на хабе */
  $$('.city-block a, .city-card').forEach(function (a) {
    a.addEventListener('click', function () { goal('city_click'); });
  });

  /* Переход из статьи на городскую страницу — ключевая цель для блога.
     Если она близка к нулю, статьи собирают трафик впустую. */
  $$('.post-city-grid a, .aside-links a').forEach(function (a) {
    a.addEventListener('click', function () { goal('blog_to_city'); });
  });

  /* Открытие 404. Отчёт «Источники → Страница входа» с фильтром по этой цели
     сразу показывает, откуда идут битые ссылки: извне или из своей же
     перелинковки. */
  if (body.classList.contains('page-404')) {
    goal('page_404', {
      from: document.referrer || 'direct',
      url: window.location.pathname
    });
  }
})();
