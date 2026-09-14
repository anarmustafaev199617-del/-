#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сборка сайта из шаблонов и данных.

    python3 tools/build.py              собрать всё в site/
    python3 tools/build.py --check      только проверить данные, ничего не писать

КАК ЭТО УСТРОЕНО

    data/site.json       общие значения: бренд, реквизиты, регион, гарантия
    data/cities.json     города с падежами, телефонами и районами
    data/services.json   контент по услугам: поломки, прайс, марки, FAQ, отзывы
              │
              ▼
    templates/*.template.html
              │  токены {{...}} подставляются
              │  участки между <!-- BUILD:x --> и <!-- /BUILD:x --> генерируются
              ▼
    site/<услуга>/index.html

ПОЧЕМУ МАРКЕРЫ, А НЕ ПОЛНАЯ ГЕНЕРАЦИЯ
Шаблон остаётся обычным HTML-файлом: его можно открыть в браузере и увидеть
пример со всей вёрсткой. Генератор трогает только содержательные блоки,
а шапка, подвал, формы и разметка остаются ровно там, где вы их видите.

ЧТО ПРОВЕРЯЕТСЯ ПЕРЕД СБОРКОЙ (--check делает то же самое)
  • все города услуги существуют в cities.json
  • минимум в прайсе совпадает с price_from
  • у каждого отзыва город входит в список городов услуги
  • после сборки не осталось незамещённых токенов {{...}}
Любая из этих ошибок останавливает сборку: лучше не собрать, чем выложить
битую связку город-услуга.
"""

import argparse
import html
import io
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import preview  # noqa: E402  — лежит рядом, в tools/

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PREVIEW_CSS = PREVIEW_JS = ''


def load(name):
    with io.open(os.path.join(ROOT, 'data', name), encoding='utf-8') as f:
        return json.load(f)


def e(text):
    """Экранирует текст для вставки в HTML. Кавычки не трогаем — они в тексте."""
    return html.escape(str(text), quote=False)


def strip_comments(page):
    """
    Вырезает HTML-комментарии из готовой страницы.

    В шаблонах лежат подробные инструкции: что здесь ЗАГЛУШКА, чего нельзя
    делать, как устроен кластер. Это документация для вас, а не для
    посетителя. В собранной странице она:
      • увеличивает вес каждой страницы на десятки килобайт
      • уезжает в продакшен и читается любым, кто откроет исходный код
      • ломается при подстановке токенов — {{REGION_SHORT}} в пояснении
        превращается в «ХМАО», и текст перестаёт быть инструкцией

    Условные комментарии IE (<!--[if ...]>) не трогаем — они управляют
    разметкой, а не поясняют её.
    """
    return re.sub(r'<!--(?!\[if)(?!<!)[^\[].*?-->', '', page, flags=re.S)


def stars(n):
    n = int(n)
    return '★' * n + '☆' * (5 - n)


# ---------------------------------------------------------------------------
# Генераторы блоков. Каждый возвращает HTML для одного BUILD-региона.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Фотографии
# ---------------------------------------------------------------------------

CAMERA_SVG = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" '
              'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
              '<path d="M3 8.5h3.2l1.4-2h8.8l1.4 2H21v10H3z"/>'
              '<circle cx="12" cy="13" r="3.4"/></svg>')


def shot(item, w, h, eager=False, cls=''):
    """
    Возвращает <figure> с фотографией, а пока её нет — пунктирную заглушку
    с описанием нужного кадра.

    Заглушка это не забытая вёрстка, а техзадание на съёмку: открыл страницу —
    видно, что снимать и в каком блоке это окажется.

    width и height проставляются всегда: без них браузер не знает высоту
    до загрузки, страница дёргается при подгрузке (метрика CLS), и человек
    промахивается мимо кнопки.
    """
    item = item or {}
    img = item.get('img')
    caption = item.get('caption', '')

    if not img:
        return ('<figure class="shot-ph%s">%s<b>Фото</b><span>%s</span></figure>'
                % ((' ' + cls) if cls else '', CAMERA_SVG,
                   e(item.get('brief', 'ЗАГЛУШКА: опишите нужный кадр'))))

    alt = item.get('alt', '')
    if not alt:
        raise SystemExit('у фото %s не заполнен alt — пустой alt допустим только '
                         'у чисто декоративных изображений' % img)
    loading = 'eager" fetchpriority="high' if eager else 'lazy'
    cap = '<figcaption>%s</figcaption>' % e(caption) if caption else ''
    return ('<figure class="shot%s"><img src="%s" width="%d" height="%d" loading="%s" '
            'decoding="async" alt="%s">%s</figure>'
            % ((' ' + cls) if cls else '', img, w, h, loading, e(alt), cap))


def gen_gallery(svc, cities, ctx):
    out = []
    for it in svc['gallery']:
        if it['kind'] == 'ba':
            body = ('          <div class="ba">\n'
                    '            <div><span class="label">Было</span>%s</div>\n'
                    '            <div><span class="label label--after">Стало</span>%s</div>\n'
                    '          </div>'
                    % (shot({'brief': it['before'], 'img': it.get('before_img'),
                             'alt': it.get('before_alt', '')}, 380, 285),
                       shot({'brief': it['after'], 'img': it.get('after_img'),
                             'alt': it.get('after_alt', '')}, 380, 285)))
        else:
            body = '          ' + shot(it, 900, 506, cls='shot--wide')
        out.append('        <div class="gallery-card">\n'
                   '          <h3>%s</h3>\n%s\n        </div>' % (e(it['h3']), body))
    return '\n' + '\n'.join(out) + '\n      '


def gen_masters(svc, cities, ctx):
    out = []
    for m in svc['masters']:
        out.append('        <div class="master-card">\n'
                   '          %s\n'
                   '          <h3>%s</h3>\n'
                   '          <p class="role">%s</p>\n'
                   '          <p>%s</p>\n'
                   '        </div>' % (shot(m.get('shot'), 320, 320),
                                       e(m['name']), e(m['role']), e(m['text'])))
    return '\n' + '\n'.join(out) + '\n      '


def gen_warranty_shot(svc, cities, ctx):
    return ('\n        <div class="warranty-shot">\n'
            '          %s\n'
            '          <p>Так выглядит документ, который остаётся у вас. В нём перечень работ, '
            'установленные запчасти, цена и срок гарантии. По нему же обращаетесь, '
            'если что-то пошло не так.</p>\n'
            '        </div>\n' % shot(svc.get('warranty_shot'), 380, 285))


def gen_city_switch(svc, cities, ctx):
    out = []
    for slug in svc['cities']:
        out.append('          <a href="/%s/%s/">%s</a>' % (svc['slug'], slug, e(cities[slug]['nom'])))
    return '\n' + '\n'.join(out) + '\n        '


def gen_mobile_cities(svc, cities, ctx):
    out = []
    for slug in svc['cities']:
        out.append('    <a href="/%s/%s/">%s</a>' % (svc['slug'], slug, e(cities[slug]['nom'])))
    return '\n' + '\n'.join(out) + '\n    '


def gen_hero_badges(svc, cities, ctx):
    out = ['          <span class="trust-badge">%d города %s</span>' % (len(svc['cities']), ctx['REGION_SHORT'])]
    for b in svc['hero_badges']:
        out.append('          <span class="trust-badge">%s</span>' % e(b))
    return '\n' + '\n'.join(out) + '\n        '


def gen_city_cards(svc, cities, ctx):
    out = []
    for slug in svc['cities']:
        c = cities[slug]
        out.append(
            '          <a class="city-card" href="/%s/%s/">\n'
            '            <span class="name">%s</span>\n'
            '            <span class="meta">от %s ₽ · выезд в день обращения</span>\n'
            '            <span class="go">Смотреть цены →</span>\n'
            '          </a>' % (svc['slug'], slug, e(c['nom']), e(svc['price_from'])))
    return '\n' + '\n'.join(out) + '\n        '


def gen_diag_rows(svc, cities, ctx):
    out = []
    for r in svc['diag']:
        out.append(
            '              <tr>\n'
            '                <td class="sym"><a href="%s">%s</a></td>\n'
            '                <td>%s</td>\n'
            '                <td>%s</td>\n'
            '                <td class="price">%s</td>\n'
            '              </tr>' % (r.get('url', '#'), e(r['sym']), e(r['cause']), e(r['fix']), e(r['price'])))
    return '\n' + '\n'.join(out) + '\n            '


def gen_faults(svc, cities, ctx):
    out = []
    for f in svc['faults']:
        signs = '\n'.join('              <li>%s</li>' % e(x) for x in f['signs'])
        fix = '\n'.join('              <li>%s</li>' % e(x) for x in f['fix'])
        out.append(
            '      <div class="fault">\n'
            '        <h3>%s</h3>\n'
            '        <p class="fault-desc">%s</p>\n'
            '        <div class="fault-grid">\n'
            '          <div class="fault-cols">\n'
            '            <div>\n'
            '              <h4>Признаки</h4>\n'
            '              <ul>\n%s\n              </ul>\n'
            '            </div>\n'
            '            <div>\n'
            '              <h4>Как устраняем</h4>\n'
            '              <ul>\n%s\n              </ul>\n'
            '            </div>\n'
            '          </div>\n'
            '          %s\n'
            '        </div>\n'
            '        <div class="fault-meta">\n'
            '          <span>Срок: <strong>%s</strong></span>\n'
            '          <span>Работа: <strong>%s</strong></span>\n'
            '          <span>Гарантия: <strong>%s</strong></span>\n'
            '        </div>\n'
            '      </div>' % (e(f['h3']), e(f['desc']), signs, fix,
                               shot(f.get('shot'), 260, 195, eager=False),
                               e(f['time']), e(f['price']), e(f['warranty'])))
    return '\n\n' + '\n\n'.join(out) + '\n'


def gen_decide(svc, cities, ctx):
    out = []
    for d in svc['decide']:
        out.append(
            '        <div class="decide-card %s">\n'
            '          <span class="tag">%s</span>\n'
            '          <h3>%s</h3>\n'
            '          <p>%s</p>\n'
            '        </div>' % (d['cls'], e(d['tag']), e(d['h3']), e(d['p'])))
    return '\n' + '\n'.join(out) + '\n      '


def _brands(items, indent):
    rows, line = [], []
    for b in items:
        line.append('<span>%s</span>' % e(b))
        if len(line) == 4:
            rows.append(indent + ''.join(line)); line = []
    if line:
        rows.append(indent + ''.join(line))
    return '\n' + '\n'.join(rows) + '\n      '


def gen_brands_main(svc, cities, ctx):
    return _brands(svc['brands_main'], '        ')


def gen_brands_extra(svc, cities, ctx):
    return _brands(svc['brands_extra'], '        ')


def _price_rows(rows, indent):
    out = [indent + '<tr><td>%s</td><td>%s</td></tr>' % (e(a), e(b)) for a, b in rows]
    return '\n' + '\n'.join(out) + '\n            '


def gen_price_main(svc, cities, ctx):
    return _price_rows(svc['prices_main'], '              ')


def gen_price_extra(svc, cities, ctx):
    return _price_rows(svc['prices_extra'], '              ')


def gen_price_city_links(svc, cities, ctx):
    return ', '.join('<a href="/%s/%s/">%s</a>' % (svc['slug'], s, e(cities[s]['nom'])) for s in svc['cities'])


def gen_reviews(svc, cities, ctx):
    out = []
    for r in svc['reviews']:
        n = int(r['stars'])
        out.append(
            '        <div class="review-card">\n'
            '          <div class="review-head"><span class="review-name">%s</span>'
            '<span class="review-date">%s</span></div>\n'
            '          <div class="review-stars" role="img" aria-label="%d из 5">%s</div>\n'
            '          <span class="review-tag">%s</span>\n'
            '          <p class="review-text">%s</p>\n'
            '          <span class="review-city"><a href="/%s/%s/">%s</a></span>\n'
            '        </div>' % (e(r['name']), e(r['date']), n, stars(n), e(r['tag']), e(r['text']),
                               svc['slug'], r['city'], e(cities[r['city']]['nom'])))
    return '\n' + '\n'.join(out) + '\n      '


def gen_other_services(svc, cities, ctx):
    out = []
    for other in ctx['ALL_SERVICES']:
        if other['slug'] == svc['slug']:
            continue
        out.append(
            '        <a class="link-card" href="/%s/">\n'
            '          <strong>%s</strong>\n'
            '          <span>%s</span>\n'
            '        </a>' % (other['slug'], e(other['nom']), e(other['short_line'])))
    out.append(
        '        <a class="link-card" href="/">\n'
        '          <strong>Все услуги и города</strong>\n'
        '          <span>Полный список того, с чем мы работаем</span>\n'
        '        </a>')
    return '\n' + '\n'.join(out) + '\n      '


def gen_articles(svc, cities, ctx):
    out = []
    for a in svc['articles']:
        out.append(
            '        <a href="%s" class="article-card">\n'
            '          <span class="article-date">%s</span>\n'
            '          <h3>%s</h3>\n'
            '          <p>%s</p>\n'
            '          <span class="article-more">Читать</span>\n'
            '        </a>' % (a.get('url', '#'), e(a.get('date', 'ЗАГЛУШКА: дата')), e(a['title']), e(a['desc'])))
    return '\n' + '\n'.join(out) + '\n      '


def gen_faq(svc, cities, ctx):
    out = []
    for q in svc['faq']:
        out.append(
            '        <details class="faq-item">\n'
            '          <summary>%s</summary>\n'
            '          <p>%s</p>\n'
            '        </details>' % (e(q['q']), e(q['a'])))
    return '\n' + '\n'.join(out) + '\n      '


def gen_trust(svc, cities, ctx):
    points = [
        ('Мастер, а не диспетчер', 'Вы говорите сразу с тем, кто приедет. Без call-центра и передачи заявки подрядчику.'),
        ('Запчасти с собой', svc['parts_line']),
        ('Работаем на месте', svc['onsite_line']),
        ('Квитанция и гарантийный талон', 'После ремонта остаётся документ с перечнем работ, ценой и сроком гарантии.'),
        ('%s лет практики' % ctx['YEARS'], 'С %s года. Постоянная команда профильных мастеров по каждому направлению.' % ctx['FOUNDED_YEAR']),
        ('Скажем, если чинить не стоит', 'Если ремонт дороже новой техники — назовём это прямо, а не «накрутим» смету.'),
    ]
    out = []
    for h3, p in points:
        out.append('        <div class="trust-point">\n          <h3>%s</h3>\n          <p>%s</p>\n        </div>' % (e(h3), e(p)))
    return '\n' + '\n'.join(out) + '\n      '


def gen_jsonld(svc, cities, ctx):
    url = ctx['SITE_URL']
    graph = [
        {"@type": "Organization", "@id": url + "/#organization", "name": ctx['BRAND'],
         "legalName": ctx['LEGAL_NAME'], "url": url + "/", "logo": url + "/img/logo.png",
         "telephone": ctx['PHONE_E164'], "email": ctx['EMAIL'],
         "foundingDate": ctx['FOUNDED_YEAR'], "taxID": ctx['INN']},
        {"@type": "WebPage", "@id": "%s/%s/#webpage" % (url, svc['slug']),
         "url": "%s/%s/" % (url, svc['slug']),
         "name": "%s на дому в %s" % (svc['nom'], ctx['REGION_SHORT']),
         "inLanguage": "ru-RU", "isPartOf": {"@id": url + "/#organization"}},
        {"@type": "BreadcrumbList", "@id": "%s/%s/#breadcrumb" % (url, svc['slug']),
         "itemListElement": [
             {"@type": "ListItem", "position": 1, "name": "Главная", "item": url + "/"},
             {"@type": "ListItem", "position": 2, "name": svc['nom']}]},
        {"@type": "Service", "@id": "%s/%s/#service" % (url, svc['slug']),
         "name": "%s на дому" % svc['nom'], "serviceType": svc['nom'],
         "provider": {"@id": url + "/#organization"},
         "areaServed": [{"@type": "City", "name": cities[s]['nom']} for s in svc['cities']],
         "availableChannel": {
             "@type": "ServiceChannel",
             "servicePhone": {"@type": "ContactPoint", "telephone": ctx['PHONE_E164'],
                              "contactType": "customer service"},
             "serviceUrl": "%s/%s/" % (url, svc['slug'])},
         "hoursAvailable": {
             "@type": "OpeningHoursSpecification",
             "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
             "opens": "09:00", "closes": "21:00"},
         "hasOfferCatalog": {
             "@type": "OfferCatalog", "name": "Ориентировочные цены на %s" % svc['acc'],
             "itemListElement": [
                 {"@type": "Offer", "itemOffered": {"@type": "Service", "name": o['name']},
                  "priceSpecification": {"@type": "PriceSpecification", "minPrice": o['min'],
                                         "priceCurrency": "RUB"}}
                 for o in svc['offer_catalog']]}},
        {"@type": "ItemList", "@id": "%s/%s/#cities" % (url, svc['slug']),
         "name": "%s по городам" % svc['nom'],
         "itemListElement": [
             {"@type": "ListItem", "position": i + 1,
              "name": "%s в %s" % (svc['nom'], cities[s]['loc']),
              "url": "%s/%s/%s/" % (url, svc['slug'], s)}
             for i, s in enumerate(svc['cities'])]},
        {"@type": "FAQPage", "@id": "%s/%s/#faq" % (url, svc['slug']),
         "mainEntity": [
             {"@type": "Question", "name": q['q'],
              "acceptedAnswer": {"@type": "Answer", "text": q['a']}}
             for q in svc['faq']]},
    ]
    body = json.dumps({"@context": "https://schema.org", "@graph": graph},
                      ensure_ascii=False, indent=2)
    return '\n' + body + '\n'


BLOCKS = {
    'jsonld': gen_jsonld,
    'city-switch': gen_city_switch,
    'mobile-cities': gen_mobile_cities,
    'hero-badges': gen_hero_badges,
    'city-cards': gen_city_cards,
    'diag-rows': gen_diag_rows,
    'faults': gen_faults,
    'decide': gen_decide,
    'brands-main': gen_brands_main,
    'brands-extra': gen_brands_extra,
    'price-main': gen_price_main,
    'price-extra': gen_price_extra,
    'price-city-links': gen_price_city_links,
    'reviews': gen_reviews,
    'other-services': gen_other_services,
    'articles': gen_articles,
    'faq': gen_faq,
    'trust': gen_trust,
    'gallery': gen_gallery,
    'masters': gen_masters,
    'warranty-shot': gen_warranty_shot,
}


# ---------------------------------------------------------------------------
# Проверки данных
# ---------------------------------------------------------------------------

def check(site, cities, services):
    errors = []
    for svc in services:
        slug = svc['slug']

        for c in svc['cities']:
            if c not in cities:
                errors.append('%s: город %r не описан в cities.json' % (slug, c))

        nums = []
        for label, price in svc['prices_main'] + svc['prices_extra']:
            m = re.search(r'(\d[\d\s]*)\s*₽', price.replace('{{PRICE_FROM}}', svc['price_from'])
                                                    .replace('{{VISIT_PRICE}}', '999999'))
            if m:
                nums.append(int(m.group(1).replace(' ', '')))
        nums = [n for n in nums if n != 999999]
        if nums and min(nums) != int(svc['price_from']):
            errors.append('%s: price_from=%s, а минимум в прайсе %s — заголовок и таблица разойдутся'
                          % (slug, svc['price_from'], min(nums)))

        for r in svc['reviews']:
            if r['city'] not in svc['cities']:
                errors.append('%s: отзыв %s привязан к городу %r, которого нет у этой услуги'
                              % (slug, r['name'], r['city']))

        shots = [f.get('shot') for f in svc['faults']] + \
                [m.get('shot') for m in svc.get('masters', [])] + [svc.get('warranty_shot')]
        for sh in shots:
            if sh and sh.get('img') and not sh.get('alt'):
                errors.append('%s: у фото %s не заполнен alt' % (slug, sh['img']))

        for key in ('faults', 'diag', 'faq', 'articles', 'decide', 'reviews'):
            if not svc.get(key):
                errors.append('%s: пустой блок %r' % (slug, key))

    return errors


# ---------------------------------------------------------------------------
# Сборка
# ---------------------------------------------------------------------------

def build_hub(svc, site, cities, template):
    visit = min(int(cities[s]['visit_price']) for s in svc['cities'])

    ctx = {
        'SITE_URL': site['site_url'], 'SITE_DOMAIN': site['site_domain'],
        'BRAND': site['brand'], 'LEGAL_NAME': site['legal_name'],
        'INN': site['inn'], 'OGRN': site['ogrn'], 'EMAIL': site['email'],
        'WORK_HOURS': site['work_hours'], 'METRIKA_ID': site['metrika_id'],
        'REGION_SHORT': site['region_short'], 'REGION_FULL': site['region_full'],
        'YEAR': site['year'], 'FOUNDED_YEAR': site['founded_year'], 'YEARS': site['years'],
        'RATING': site['rating'], 'REVIEWS_COUNT': site['reviews_count'],
        'ORDERS_COUNT': site['orders_count'],
        'WARRANTY_MIN': site['warranty_min'], 'WARRANTY_MAX': site['warranty_max'],

        # телефон на хабе общий; по городам он подставляется на городских страницах
        'PHONE_DISPLAY': cities[svc['cities'][0]]['phone_display'],
        'PHONE_E164': cities[svc['cities'][0]]['phone_e164'],

        'SERVICE_SLUG': svc['slug'], 'SERVICE_NOM': svc['nom'], 'SERVICE_GEN': svc['gen'],
        'SERVICE_NOM_LC': svc['nom_lc'], 'SERVICE_ACC': svc['acc'], 'SERVICE_INS': svc['ins'],
        'DEVICE_NOM': svc['device_nom'], 'DEVICE_GEN': svc['device_gen'],
        'DEVICE_PL_GEN': svc['device_pl_gen'],
        'CITIES_COUNT': str(len(svc['cities'])),
        'PRICE_FROM': svc['price_from'], 'VISIT_PRICE': str(visit),
        'HERO_LEDE': svc['hero_lede'], 'DIAG_LEDE': svc['diag_lede'],
        'DECIDE_LEDE': svc['decide_lede'], 'PRICES_LEDE': svc['prices_lede'],
        'BRANDS_TITLE': svc['brands_title'], 'BRANDS_LEDE': svc['brands_lede'],
        'GALLERY_TITLE': svc['gallery_title'], 'GALLERY_LEDE': svc['gallery_lede'],
        'GALLERY_NOTE': svc['gallery_note'],
    }
    ctx['ALL_SERVICES'] = build_hub.all_services

    out = template
    for name, fn in BLOCKS.items():
        pattern = re.compile(r'<!-- BUILD:%s -->.*?<!-- /BUILD:%s -->' % (name, name), re.S)
        if not pattern.search(out):
            raise SystemExit('в шаблоне нет региона BUILD:%s' % name)
        out = pattern.sub(lambda m, f=fn: fn(svc, cities, ctx).replace('\\', '\\\\'), out, count=1)

    # токены подставляем дважды: значения сами могут содержать {{...}}
    for _ in range(2):
        out = re.sub(r'\{\{(\w+)\}\}', lambda m: str(ctx.get(m.group(1), m.group(0))), out)

    out = strip_comments(out)
    return out, ctx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='только проверить данные')
    ap.add_argument('--out', default='site', help='каталог сборки (по умолчанию site/)')
    args = ap.parse_args()

    site = load('site.json')
    cities = load('cities.json')
    services = load('services.json')['services']

    errors = check(site, cities, services)
    if errors:
        print('ОШИБКИ В ДАННЫХ — сборка остановлена:', file=sys.stderr)
        for x in errors:
            print('  • ' + x, file=sys.stderr)
        sys.exit(1)
    print('проверка данных: ок (%d услуг, %d городов)' % (len(services), len(cities) - 1))

    if args.check:
        return

    build_hub.all_services = services

    global PREVIEW_CSS, PREVIEW_JS
    PREVIEW_CSS = preview.read_asset('style.css')
    PREVIEW_JS = preview.read_asset('app.js')

    tpl_path = os.path.join(ROOT, 'templates', 'service-hub.template.html')
    template = io.open(tpl_path, encoding='utf-8').read()

    outdir = os.path.join(ROOT, args.out)
    for svc in services:
        page, ctx = build_hub(svc, site, cities, template)

        left = sorted(set(re.findall(r'\{\{(\w+)\}\}', page)))
        if left:
            print('ОШИБКА: %s — не подставлены токены: %s' % (svc['slug'], ', '.join(left)), file=sys.stderr)
            sys.exit(1)

        d = os.path.join(outdir, svc['slug'])
        os.makedirs(d, exist_ok=True)
        io.open(os.path.join(d, 'index.html'), 'w', encoding='utf-8').write(page)

        # Копия для просмотра и отправки: стили и скрипт вшиты внутрь.
        # Боевая страница ссылается на /assets/ абсолютным путём — иначе
        # ссылки сломаются на вложенных адресах и на 404. Но такой файл нельзя
        # открыть двойным кликом или отправить кому-то: соседней папки assets
        # рядом не окажется, и браузер покажет голый HTML без стилей.
        # На хостинг эти копии не выкладываются, см. tools/preview.py.
        prev = os.path.join(outdir, '_preview')
        os.makedirs(prev, exist_ok=True)
        io.open(os.path.join(prev, svc['slug'] + '.html'), 'w', encoding='utf-8').write(
            preview.inline(page, PREVIEW_CSS, PREVIEW_JS))

        print('  /%s/  %6.1f КБ' % (svc['slug'], len(page.encode('utf-8')) / 1024))

    # ассеты рядом, чтобы site/ открывался как настоящий сайт
    assets_src = os.path.join(ROOT, 'assets')
    assets_dst = os.path.join(outdir, 'assets')
    if os.path.isdir(assets_src):
        shutil.rmtree(assets_dst, ignore_errors=True)
        shutil.copytree(assets_src, assets_dst)
        print('  assets/ скопированы')

    print('готово: %s/' % args.out)


if __name__ == '__main__':
    main()
