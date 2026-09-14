#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор sitemap.xml.

Зачем: руками поддерживать 26 адресов с датами неудобно, и первым делом
протухает lastmod. Здесь список страниц лежит в одном месте, а даты для
статей берутся из самих HTML-файлов (мета article:modified_time), если
каталог со сборкой указан.

Запуск:
    python3 tools/build-sitemap.py --site https://example.ru > sitemap.xml

    # подтянуть lastmod статей из собранных страниц
    python3 tools/build-sitemap.py --site https://example.ru --build-dir ./dist > sitemap.xml

Что НЕ попадает в карту: /spasibo/ (у неё noindex) и 404.
"""

import argparse
import datetime
import io
import os
import re
import sys

# Какие города есть у какой услуги. Матрица не прямоугольная —
# держите синхронно со структурой сайта.
SERVICES = {
    "remont-stiralnyh-mashin": ["surgut", "nizhnevartovsk", "nefteyugansk", "nyagan"],
    "remont-holodilnikov": ["surgut", "nizhnevartovsk", "nefteyugansk", "hanty-mansiysk"],
    "kompyuternaya-pomosch": ["surgut", "nizhnevartovsk", "nefteyugansk", "hanty-mansiysk"],
}

# Статьи блога: слаг → дата последнего изменения (ГГГГ-ММ-ДД).
# Если указан --build-dir, дата перечитывается из article:modified_time
# в самом файле, и правки здесь не нужны.
POSTS = {
    "holodilnik-ne-morozit": "2026-09-01",
    "holodilnik-shumit": "2026-04-28",
    "naled-v-morozilke": "2026-04-10",
    "sm-ne-slivaet-vodu": "2026-04-12",
    "sm-ne-otzhimaet": "2026-03-30",
    "sm-prygaet": "2026-03-18",
    "kompyuter-ne-vklyuchaetsya": "2026-03-18",
    "noutbuk-ne-zaryazhaetsya": "2026-03-05",
    "kompyuter-tormozit": "2026-02-20",
}

POLICY_DATE = "2026-09-14"

MOD_RE = re.compile(
    r'<meta\s+property="article:modified_time"\s+content="(\d{4}-\d{2}-\d{2})',
    re.I,
)


def post_lastmod(slug, build_dir, fallback):
    """Читает дату изменения из собранной страницы, иначе берёт из POSTS."""
    if not build_dir:
        return fallback
    path = os.path.join(build_dir, "blog", slug, "index.html")
    if not os.path.isfile(path):
        print("  предупреждение: не найден %s" % path, file=sys.stderr)
        return fallback
    html = io.open(path, encoding="utf-8").read()
    m = MOD_RE.search(html)
    if not m:
        print("  предупреждение: нет article:modified_time в %s" % path, file=sys.stderr)
        return fallback
    return m.group(1)


def url(loc, lastmod, changefreq, priority):
    return (
        "  <url>\n"
        "    <loc>%s</loc>\n"
        "    <lastmod>%s</lastmod>\n"
        "    <changefreq>%s</changefreq>\n"
        "    <priority>%s</priority>\n"
        "  </url>" % (loc, lastmod, changefreq, priority)
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True, help="https://example.ru (без слеша на конце)")
    ap.add_argument("--build-dir", default=None, help="каталог со сборкой, чтобы взять даты статей")
    ap.add_argument("--date", default=None, help="lastmod для статических страниц (по умолчанию сегодня)")
    args = ap.parse_args()

    site = args.site.rstrip("/")
    today = args.date or datetime.date.today().isoformat()

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
           "", "  <!-- Главная -->",
           url(site + "/", today, "weekly", "1.0"),
           "", "  <!-- Хабы услуг -->"]

    for slug in SERVICES:
        out.append(url("%s/%s/" % (site, slug), today, "weekly", "0.9"))

    out += ["", "  <!-- Городские страницы -->"]
    for slug, cities in SERVICES.items():
        for city in cities:
            out.append(url("%s/%s/%s/" % (site, slug, city), today, "weekly", "0.8"))

    out += ["", "  <!-- Блог -->",
            url(site + "/blog/", today, "weekly", "0.6"),
            "", "  <!-- Статьи -->"]
    for slug, fallback in POSTS.items():
        out.append(url("%s/blog/%s/" % (site, slug),
                       post_lastmod(slug, args.build_dir, fallback),
                       "monthly", "0.5"))

    out += ["", "  <!-- Правовое -->",
            url(site + "/politika/", POLICY_DATE, "yearly", "0.2"),
            "", "</urlset>"]

    xml = "\n".join(out)
    print(xml)
    print("  адресов в карте: %d" % xml.count("<loc>"), file=sys.stderr)


if __name__ == "__main__":
    main()
