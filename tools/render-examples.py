#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Пересобирает examples/ — демонстрационные страницы по одной на каждый шаблон.

    python3 tools/render-examples.py

Зачем отдельно от build.py: build.py собирает боевой сайт из data/ и умеет
пока только хабы. Примеры показывают ВСЕ типы страниц, включая те, что
заполняются вручную (главная, блог, статья, /spasibo/, /politika/, 404).

Раньше примеры собирались разовым скриптом «на коленке», который нигде
не лежал. Из-за этого их нельзя было воспроизвести, а повторный прогон
инлайнера по уже готовым файлам продублировал в них стили трижды.
"""

import io
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import preview  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Значения для демонстрации. Боевые лежат в data/, эти — только для примеров.
V = {
    'SITE_URL': 'https://example.ru', 'SITE_DOMAIN': 'example.ru', 'BRAND': 'РемонтДом',
    'LEGAL_NAME': 'ИП Иванов Иван Иванович', 'INN': '860000000000', 'OGRN': '300000000000000',
    'LEGAL_ADDRESS': '628400, ХМАО — Югра, г. Сургут, ул. Примерная, д. 1',
    'EMAIL': 'info@example.ru', 'WORK_HOURS': 'с 9:00 до 21:00', 'WORK_HOURS_END': '21:00',
    'METRIKA_ID': '', 'PHONE_DISPLAY': '+7 (000) 000-00-00', 'PHONE_E164': '+70000000000',
    'REGION_SHORT': 'ХМАО', 'REGION_FULL': 'Ханты-Мансийский автономный округ — Югра',
    'YEAR': '2026', 'FOUNDED_YEAR': '2017', 'YEARS': '9',
    'RATING': '4.9', 'REVIEWS_COUNT': '134', 'ORDERS_COUNT': '600',
    'WARRANTY_MIN': '6', 'WARRANTY_MAX': '24',
    'VISIT_PRICE': '500', 'PRICE_FROM': '600',
    'SERVICES_COUNT': '3', 'CITIES_COUNT': '5',
    'POLICY_DATE': '14 сентября 2026', 'POLICY_DATE_ISO': '2026-09-14',

    'SERVICE_SLUG': 'remont-holodilnikov', 'SERVICE_NOM': 'Ремонт холодильников',
    'SERVICE_GEN': 'ремонта холодильников', 'SERVICE_NOM_LC': 'ремонт холодильников',
    'SERVICE_ACC': 'ремонт холодильников', 'SERVICE_INS': 'ремонтом холодильников',
    'DEVICE_NOM': 'холодильник', 'DEVICE_GEN': 'холодильника', 'DEVICE_PL_GEN': 'холодильников',

    'CITY_SLUG': 'surgut', 'CITY_NOM': 'Сургут', 'CITY_GEN': 'Сургута',
    'CITY_DAT': 'Сургуту', 'CITY_ACC': 'Сургут', 'CITY_LOC': 'Сургуте',
    'REGION_NOM': 'Сургутский район', 'REGION_LOC': 'Сургутском районе',

    'POST_SLUG': 'holodilnik-ne-morozit',
    'POST_TITLE': 'Холодильник не морозит: 6 причин и что проверить самому',
    'POST_H1': 'Холодильник не морозит: 6 причин',
    'POST_DESC': 'Почему холодильник работает, но не холодит: разбираем шесть причин '
                 'и показываем, что можно проверить самому.',
    'POST_DATE_ISO': '2026-05-15', 'POST_DATE': '15 мая 2026',
    'POST_MOD_ISO': '2026-09-01', 'POST_MOD': '1 сентября 2026', 'READ_TIME': '7',
    'AUTHOR_NAME': 'Имя Фамилия', 'AUTHOR_SLUG': 'imya-familiya',
    'AUTHOR_ROLE': 'мастер по холодильному оборудованию, стаж 12 лет',

    # у хаба свой счётчик городов: там города одной услуги, а не все
    'HERO_LEDE': 'Работаем в 4 городах ХМАО. Мастер приезжает к вам, чинит на месте '
                 'и оставляет квитанцию с гарантией.',
    'DIAG_LEDE': 'Таблица не заменяет диагностику, но даёт понять, о каких суммах '
                 'идёт речь, ещё до звонка мастеру.',
    'DECIDE_LEDE': 'Универсальный ориентир: если ремонт с запчастями дороже 40–50% '
                   'стоимости аналогичной новой модели — выгоднее покупать новую.',
    'PRICES_LEDE': 'Ориентировочные цены на работу мастера. Запчасти оплачиваются отдельно.',
    'BRANDS_TITLE': 'С какими марками работаем',
    'BRANDS_LEDE': 'Список открытый: если вашей марки нет в перечне — позвоните.',
}

PAGES = [
    ('home.template.html',         'home.html',                        {}),
    ('service-hub.template.html',  'remont-holodilnikov-hub.html',     {'CITIES_COUNT': '4'}),
    ('service-city.template.html', 'remont-holodilnikov-surgut.html',  {}),
    ('blog-index.template.html',   'blog.html',                        {}),
    ('blog-post.template.html',    'blog-holodilnik-ne-morozit.html',  {}),
    ('spasibo.template.html',      'spasibo.html',                     {}),
    ('politika.template.html',     'politika.html',                    {}),
    ('404.template.html',          '404.html',                         {}),
]


def main():
    css, js = preview.read_asset('style.css'), preview.read_asset('app.js')
    outdir = os.path.join(ROOT, 'examples')
    os.makedirs(outdir, exist_ok=True)

    for tpl, name, extra in PAGES:
        src = io.open(os.path.join(ROOT, 'templates', tpl), encoding='utf-8').read()
        vals = dict(V, **extra)
        page = re.sub(r'\{\{(\w+)\}\}', lambda m: vals.get(m.group(1), m.group(0)), src)

        left = sorted(set(re.findall(r'\{\{(\w+)\}\}', page)))
        if left:
            sys.exit('%s: не подставлены токены %s' % (name, ', '.join(left)))

        # маркеры генератора в примерах не нужны — оставляем пример из шаблона
        page = re.sub(r'<!-- /?BUILD:[\w-]+ -->', '', page)

        page = preview.inline(page, css, js)
        io.open(os.path.join(outdir, name), 'w', encoding='utf-8').write(page)
        print('  %-44s %6.1f КБ' % ('examples/' + name, len(page.encode('utf-8')) / 1024))


if __name__ == '__main__':
    main()
