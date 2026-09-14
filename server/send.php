<?php
declare(strict_types=1);

/**
 * ============================================================================
 *  ОБРАБОТЧИК ФОРМ ЗАЯВОК
 *  Кладётся в корень сайта: /send.php
 * ============================================================================
 *
 *  ЗАЧЕМ ОН НУЖЕН ВМЕСТО FORMSPREE
 *
 *  Formspree держит серверы в США. Для персональных данных граждан РФ это
 *  расходится с ч. 5 ст. 18 152-ФЗ: запись, систематизация, накопление и
 *  хранение должны производиться с использованием баз данных на территории
 *  России. Этот скрипт пишет заявку в файл на вашем хостинге — то есть
 *  первичная запись происходит в РФ, как и требует закон.
 *
 *  ⚠️ ЭТО РАБОТАЕТ, ТОЛЬКО ЕСЛИ ХОСТИНГ ТОЖЕ В РФ.
 *  Скрипт на зарубежном VPS проблему не решает, а маскирует. Проверьте, где
 *  физически стоит сервер, прежде чем менять раздел 8 политики.
 *
 *  Уведомление в Роскомнадзор об обработке ПДн подавать всё равно нужно —
 *  смена обработчика форм от этого не освобождает.
 *
 *  ----------------------------------------------------------------------------
 *  ПОРЯДОК ДЕЙСТВИЙ. ЗАЯВКА НЕ ТЕРЯЕТСЯ НИКОГДА
 *
 *    1. записали в logs/leads.csv          ← если упадёт, дальше не идём
 *    2. отправили письмо
 *    3. отправили в Telegram
 *    4. увели пользователя на /spasibo/
 *
 *  Запись на диск идёт ПЕРВОЙ и единственная считается критичной. Почта может
 *  залипнуть в очереди, Telegram может быть недоступен — заявка всё равно
 *  лежит в CSV, и её видно. Обратный порядок (сначала письмо) — самый частый
 *  способ терять заявки молча.
 *
 *  ----------------------------------------------------------------------------
 *  УСТАНОВКА
 *
 *    1. Скопируйте config.sample.php → config.php и заполните
 *    2. Положите config.php ВЫШЕ корня сайта, если хостинг позволяет,
 *       и поправьте CONFIG_PATH ниже. Если не позволяет — рядом, но тогда
 *       обязательно положите .htaccess из этой же папки
 *    3. Создайте папку logs/ с правами на запись (755 или 775)
 *    4. Проверьте, что /send.php закрыт в robots.txt — он уже там
 *    5. Отправьте тестовую заявку и убедитесь, что пришло всё три раза:
 *       в CSV, на почту и в Telegram
 *
 *  ⚠️ ПРО TELEGRAM НА РОССИЙСКОМ ХОСТИНГЕ
 *  Часть хостеров не пускает исходящие запросы к api.telegram.org. Если
 *  уведомления не приходят, а в logs/error.log видно ошибку соединения —
 *  дело в этом. Варианты: попросить хостера открыть доступ, поднять свой
 *  прокси или отключить Telegram и оставить почту. На запись в CSV и на
 *  письмо это не влияет.
 * ============================================================================
 */

const CONFIG_PATH = __DIR__ . '/config.php';

/* --------------------------------------------------------------------------
 * Загрузка конфигурации
 * -------------------------------------------------------------------------- */
if (!is_readable(CONFIG_PATH)) {
    http_response_code(500);
    exit('Форма не настроена: отсутствует config.php');
}
/** @var array $CFG */
$CFG = require CONFIG_PATH;

$LOG_DIR    = $CFG['log_dir'] ?? __DIR__ . '/logs';
$LEADS_FILE = $LOG_DIR . '/leads.csv';
$ERROR_FILE = $LOG_DIR . '/error.log';

/* --------------------------------------------------------------------------
 * Вспомогательные функции
 * -------------------------------------------------------------------------- */

/** Пишет строку в error.log. Сам никогда не падает. */
function log_error(string $message): void
{
    global $LOG_DIR, $ERROR_FILE;
    if (!is_dir($LOG_DIR)) {
        @mkdir($LOG_DIR, 0775, true);
    }
    @file_put_contents(
        $ERROR_FILE,
        sprintf("[%s] %s\n", date('Y-m-d H:i:s'), $message),
        FILE_APPEND | LOCK_EX
    );
}

/** Запрос пришёл через fetch/XHR и ждёт JSON, а не редирект. */
function wants_json(): bool
{
    $xhr = $_SERVER['HTTP_X_REQUESTED_WITH'] ?? '';
    $accept = $_SERVER['HTTP_ACCEPT'] ?? '';
    return strtolower($xhr) === 'xmlhttprequest'
        || str_contains(strtolower($accept), 'application/json');
}

/**
 * Чистит пользовательский ввод.
 * Убирает управляющие символы — в том числе перевод строки, через который
 * делают инъекцию заголовков письма (CRLF injection).
 */
function clean(?string $value, int $maxLength): string
{
    $value = (string) $value;
    $value = preg_replace('/[\x00-\x1F\x7F]/u', ' ', $value) ?? '';
    $value = trim(preg_replace('/\s+/u', ' ', $value) ?? '');
    if (function_exists('mb_substr')) {
        return mb_substr($value, 0, $maxLength, 'UTF-8');
    }
    return substr($value, 0, $maxLength);
}

/** Оставляет в телефоне только то, из чего он может состоять. */
function clean_phone(?string $value): string
{
    $value = preg_replace('/[^0-9+()\-\s]/u', '', (string) $value) ?? '';
    return clean($value, 25);
}

/** Цифры телефона — для проверки длины и для ссылки tel: */
function phone_digits(string $phone): string
{
    return preg_replace('/\D+/', '', $phone) ?? '';
}

function client_ip(): string
{
    /* ⚠️ X-Forwarded-For подделывается кем угодно. Доверять ему можно
       ТОЛЬКО если перед PHP стоит ваш собственный прокси или CDN,
       который этот заголовок перезаписывает. Включается в конфиге. */
    global $CFG;
    if (!empty($CFG['trust_proxy']) && !empty($_SERVER['HTTP_X_FORWARDED_FOR'])) {
        $parts = explode(',', $_SERVER['HTTP_X_FORWARDED_FOR']);
        $ip = trim($parts[0]);
        if (filter_var($ip, FILTER_VALIDATE_IP)) {
            return $ip;
        }
    }
    return $_SERVER['REMOTE_ADDR'] ?? '0.0.0.0';
}

/**
 * Куда вернуть пользователя после отправки.
 *
 * ⚠️ ОТКРЫТЫЙ РЕДИРЕКТ. Поле _next приходит из формы, то есть от клиента.
 * Если подставлять его как есть, злоумышленник отправит форму с
 * _next=https://фишинг.example и получит редирект с вашего домена —
 * удобный инструмент для фишинга и повод для санкций поисковиков.
 * Поэтому принимаем только относительный путь и только из белого списка.
 */
function safe_redirect_target(string $raw, array $cfg): string
{
    $default = $cfg['success_url'] ?? '/spasibo/';
    $raw = trim($raw);

    if ($raw === '') {
        return $default;
    }
    /* Абсолютный URL на свой же домен — приводим к пути */
    $host = $_SERVER['HTTP_HOST'] ?? '';
    if ($host !== '' && str_starts_with($raw, 'http')) {
        $parts = parse_url($raw);
        if (($parts['host'] ?? '') !== $host) {
            return $default;
        }
        $raw = $parts['path'] ?? $default;
    }
    /* Только относительный путь. "//злой.сайт" и "\\злой.сайт" браузер
       трактует как протокол-относительный URL — отсекаем. */
    if (!str_starts_with($raw, '/') || str_starts_with($raw, '//') || str_contains($raw, '\\')) {
        return $default;
    }
    $allowed = $cfg['allowed_redirects'] ?? ['/spasibo/'];
    return in_array($raw, $allowed, true) ? $raw : $default;
}

/** Завершает запрос: редирект для обычной формы, JSON для fetch. */
function finish(bool $ok, string $target, string $message = ''): never
{
    if (wants_json()) {
        http_response_code($ok ? 200 : 400);
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode(
            ['ok' => $ok, 'message' => $message, 'redirect' => $target],
            JSON_UNESCAPED_UNICODE
        );
        exit;
    }
    if ($ok) {
        header('Location: ' . $target, true, 303);
        exit;
    }
    http_response_code(400);
    header('Content-Type: text/html; charset=utf-8');
    echo '<!doctype html><meta charset="utf-8"><title>Не отправлено</title>'
       . '<p style="font:16px/1.6 system-ui;padding:40px">'
       . htmlspecialchars($message, ENT_QUOTES, 'UTF-8')
       . '<br><br><a href="/">Вернуться на сайт</a></p>';
    exit;
}

/**
 * Простое ограничение частоты по IP.
 * Не защита от целенаправленной атаки, но отсекает скрипты, которые
 * долбят форму в цикле.
 */
function rate_limit_ok(string $ip, array $cfg): bool
{
    global $LOG_DIR;
    $limit  = (int) ($cfg['rate_limit_count'] ?? 5);
    $window = (int) ($cfg['rate_limit_window'] ?? 600);
    if ($limit <= 0) {
        return true;
    }
    if (!is_dir($LOG_DIR) && !@mkdir($LOG_DIR, 0775, true) && !is_dir($LOG_DIR)) {
        return true; /* не можем считать — не блокируем живого человека */
    }

    $file = $LOG_DIR . '/rate_' . md5($ip) . '.txt';
    $now  = time();
    $hits = [];
    if (is_readable($file)) {
        $raw = (string) @file_get_contents($file);
        foreach (explode("\n", $raw) as $line) {
            $t = (int) trim($line);
            if ($t > 0 && $now - $t < $window) {
                $hits[] = $t;
            }
        }
    }
    if (count($hits) >= $limit) {
        return false;
    }
    $hits[] = $now;
    @file_put_contents($file, implode("\n", $hits), LOCK_EX);
    return true;
}

/* --------------------------------------------------------------------------
 * 0. Метод запроса
 * -------------------------------------------------------------------------- */
if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    /* Прямой заход на /send.php браузером — уводим на главную,
       а не показываем пустую страницу */
    header('Location: /', true, 303);
    exit;
}

$redirectTo = safe_redirect_target((string) ($_POST['_next'] ?? ''), $CFG);

/* --------------------------------------------------------------------------
 * 1. Отсев ботов
 * -------------------------------------------------------------------------- */

/* Honeypot: поле _gotcha скрыто от человека, но видно автозаполнялке бота.
   Отвечаем как при успехе — боту незачем знать, что его раскусили. */
if (trim((string) ($_POST['_gotcha'] ?? '')) !== '') {
    finish(true, $redirectTo);
}

if (!rate_limit_ok(client_ip(), $CFG)) {
    finish(false, $redirectTo, 'Слишком много заявок с вашего адреса. Попробуйте через несколько минут или позвоните нам.');
}

/* --------------------------------------------------------------------------
 * 2. Разбор и проверка полей
 * -------------------------------------------------------------------------- */
$lead = [
    'time'       => date('Y-m-d H:i:s'),
    'name'       => clean($_POST['name']    ?? '', 80),
    'phone'      => clean_phone($_POST['phone'] ?? ''),
    'city'       => clean($_POST['city']    ?? '', 60),
    'service'    => clean($_POST['service'] ?? '', 80),
    'problem'    => clean($_POST['problem'] ?? '', 500),
    'form_place' => clean($_POST['form_place'] ?? '', 40),
    'page'       => clean($_POST['page']    ?? '', 200),
    'utm'        => clean($_POST['utm']     ?? '', 500),
    'referer'    => clean($_SERVER['HTTP_REFERER'] ?? '', 200),
    'ip'         => client_ip(),
];

$digits = phone_digits($lead['phone']);
if (strlen($digits) < 10 || strlen($digits) > 15) {
    finish(false, $redirectTo, 'Проверьте номер телефона — кажется, в нём опечатка.');
}

/* Согласие на обработку ПДн. Чекбокс в формах обязательный, но проверяем
   и на сервере: без него обработка данных неправомерна. */
if (empty($_POST['consent'])) {
    finish(false, $redirectTo, 'Без согласия на обработку персональных данных мы не можем принять заявку.');
}

/* --------------------------------------------------------------------------
 * 3. ЗАПИСЬ НА ДИСК — единственный критичный шаг
 * -------------------------------------------------------------------------- */
if (!is_dir($LOG_DIR) && !@mkdir($LOG_DIR, 0775, true) && !is_dir($LOG_DIR)) {
    log_error('Не удалось создать каталог логов: ' . $LOG_DIR);
    finish(false, $redirectTo, 'Не удалось сохранить заявку. Пожалуйста, позвоните нам.');
}

$isNewFile = !file_exists($LEADS_FILE);
$fh = @fopen($LEADS_FILE, 'a');
if ($fh === false) {
    log_error('Не удалось открыть файл заявок: ' . $LEADS_FILE);
    finish(false, $redirectTo, 'Не удалось сохранить заявку. Пожалуйста, позвоните нам.');
}
if (flock($fh, LOCK_EX)) {
    if ($isNewFile) {
        /* BOM, чтобы Excel открыл CSV в UTF-8 без плясок с кодировкой */
        fwrite($fh, "\xEF\xBB\xBF");
        fputcsv($fh, array_keys($lead), ';', '"', '\\');
    }
    fputcsv($fh, array_values($lead), ';', '"', '\\');
    fflush($fh);
    flock($fh, LOCK_UN);
}
fclose($fh);

/* --------------------------------------------------------------------------
 * 4. Письмо
 * -------------------------------------------------------------------------- */

/**
 * ⚠️ mail() отправляет через локальный sendmail хостинга. На дешёвом
 * шаред-хостинге такие письма часто уезжают в спам, потому что домен
 * отправителя не проходит SPF/DKIM.
 *
 * Что сделать, чтобы письма доходили:
 *   1. from_email обязательно на вашем домене (не gmail, не yandex)
 *   2. в DNS домена прописать SPF и DKIM хостинга
 *   3. если всё равно в спам — поставить PHPMailer и слать через SMTP
 *      вашего почтового ящика. Место для подмены помечено ниже.
 */
function send_mail_notification(array $lead, array $cfg): bool
{
    $to = $cfg['mail_to'] ?? '';
    if ($to === '') {
        return false;
    }

    $subjectPlain = sprintf(
        'Заявка с сайта: %s%s',
        $lead['service'] !== '' ? $lead['service'] : 'услуга не указана',
        $lead['city'] !== '' ? ' / ' . $lead['city'] : ''
    );
    /* Тема письма кодируется base64: кириллица в заголовке иначе поедет.
       Значения уже очищены от переводов строки в clean(). */
    $subject = '=?UTF-8?B?' . base64_encode($subjectPlain) . '?=';

    $rows = [
        'Имя'        => $lead['name'],
        'Телефон'    => $lead['phone'],
        'Город'      => $lead['city'],
        'Услуга'     => $lead['service'],
        'Что с техникой' => $lead['problem'],
        'Блок формы' => $lead['form_place'],
        'Страница'   => $lead['page'],
        'UTM'        => $lead['utm'],
        'Время'      => $lead['time'],
        'IP'         => $lead['ip'],
    ];

    $html = '<html><head><meta charset="utf-8"></head><body style="font:15px/1.6 Arial,sans-serif;color:#1C2321">'
          . '<h2 style="font-size:18px;margin:0 0 14px">' . htmlspecialchars($subjectPlain, ENT_QUOTES, 'UTF-8') . '</h2>'
          . '<table cellpadding="6" cellspacing="0" border="0" style="border-collapse:collapse">';
    foreach ($rows as $label => $value) {
        if ($value === '') {
            continue;
        }
        $html .= '<tr>'
              .  '<td style="border-bottom:1px solid #E1DED4;color:#4B534F">' . htmlspecialchars($label, ENT_QUOTES, 'UTF-8') . '</td>'
              .  '<td style="border-bottom:1px solid #E1DED4;font-weight:bold">' . htmlspecialchars($value, ENT_QUOTES, 'UTF-8') . '</td>'
              .  '</tr>';
    }
    $digits = phone_digits($lead['phone']);
    $html .= '</table><p style="margin-top:18px"><a href="tel:+' . htmlspecialchars($digits, ENT_QUOTES, 'UTF-8') . '"'
          .  ' style="background:#B75B12;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none">Позвонить</a></p>'
          .  '</body></html>';

    $fromEmail = $cfg['from_email'] ?? ('noreply@' . ($_SERVER['HTTP_HOST'] ?? 'localhost'));
    $fromName  = '=?UTF-8?B?' . base64_encode((string) ($cfg['from_name'] ?? 'Сайт')) . '?=';

    $headers = [
        'MIME-Version: 1.0',
        'Content-Type: text/html; charset=UTF-8',
        'From: ' . $fromName . ' <' . $fromEmail . '>',
        'X-Mailer: site-form',
    ];

    /* ---- Точка подмены на SMTP ----------------------------------------
       Здесь ставится PHPMailer, если mail() не справляется:

           $m = new PHPMailer\PHPMailer\PHPMailer(true);
           $m->isSMTP(); $m->Host = $cfg['smtp_host'];
           $m->SMTPAuth = true;
           $m->Username = $cfg['smtp_user']; $m->Password = $cfg['smtp_pass'];
           $m->Port = 465; $m->SMTPSecure = 'ssl'; $m->CharSet = 'UTF-8';
           $m->setFrom($fromEmail, $cfg['from_name']);
           $m->addAddress($to);
           $m->isHTML(true); $m->Subject = $subjectPlain; $m->Body = $html;
           return $m->send();
       ------------------------------------------------------------------ */

    $sent = @mail($to, $subject, $html, implode("\r\n", $headers));
    if (!$sent) {
        log_error('mail() вернул false. Получатель: ' . $to);
    }
    return $sent;
}

/* --------------------------------------------------------------------------
 * 5. Telegram
 * -------------------------------------------------------------------------- */
function send_telegram_notification(array $lead, array $cfg): bool
{
    $token  = $cfg['telegram_token'] ?? '';
    $chatId = $cfg['telegram_chat_id'] ?? '';
    if ($token === '' || $chatId === '') {
        return false;
    }
    if (!function_exists('curl_init')) {
        log_error('Расширение cURL недоступно — Telegram отключён');
        return false;
    }

    /* parse_mode=HTML, поэтому каждое подставляемое значение экранируем.
       Иначе символ < в описании поломки сломает разбор сообщения. */
    $e = static fn(string $v): string => htmlspecialchars($v, ENT_NOQUOTES, 'UTF-8');

    $lines = ['<b>Новая заявка с сайта</b>', ''];
    if ($lead['service'] !== '') { $lines[] = '🔧 ' . $e($lead['service']); }
    if ($lead['city'] !== '')    { $lines[] = '📍 ' . $e($lead['city']); }
    $lines[] = '';
    if ($lead['name'] !== '')    { $lines[] = 'Имя: <b>' . $e($lead['name']) . '</b>'; }
    $lines[] = 'Телефон: <b>' . $e($lead['phone']) . '</b>';
    if ($lead['problem'] !== '') { $lines[] = 'Проблема: ' . $e($lead['problem']); }
    $lines[] = '';
    if ($lead['page'] !== '')    { $lines[] = 'Страница: ' . $e($lead['page']); }
    if ($lead['form_place'] !== '') { $lines[] = 'Блок: ' . $e($lead['form_place']); }
    if ($lead['utm'] !== '')     { $lines[] = 'Метки: ' . $e($lead['utm']); }
    $lines[] = 'Время: ' . $e($lead['time']);

    $ch = curl_init('https://api.telegram.org/bot' . $token . '/sendMessage');
    curl_setopt_array($ch, [
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => http_build_query([
            'chat_id'                  => $chatId,
            'text'                     => implode("\n", $lines),
            'parse_mode'               => 'HTML',
            'disable_web_page_preview' => 'true',
        ]),
        CURLOPT_RETURNTRANSFER => true,
        /* Таймауты обязательны: без них зависший Telegram держит
           пользователя на белом экране до таймаута PHP. */
        CURLOPT_CONNECTTIMEOUT => 5,
        CURLOPT_TIMEOUT        => 8,
    ]);
    $response = curl_exec($ch);
    $status   = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $curlErr  = curl_error($ch);
    curl_close($ch);

    if ($response === false || $status !== 200) {
        log_error(sprintf(
            'Telegram не ответил. HTTP %d. cURL: %s. Ответ: %s',
            $status,
            $curlErr !== '' ? $curlErr : '—',
            is_string($response) ? substr($response, 0, 300) : 'нет'
        ));
        return false;
    }
    return true;
}

/* --------------------------------------------------------------------------
 * 6. Отправка уведомлений и ответ
 *    Ни одна ошибка здесь не должна ронять запрос: заявка уже на диске.
 * -------------------------------------------------------------------------- */
try {
    send_mail_notification($lead, $CFG);
} catch (Throwable $e) {
    log_error('Ошибка отправки письма: ' . $e->getMessage());
}

try {
    send_telegram_notification($lead, $CFG);
} catch (Throwable $e) {
    log_error('Ошибка отправки в Telegram: ' . $e->getMessage());
}

finish(true, $redirectTo, 'Заявка принята');
