#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Делает страницу самодостаточной: вшивает CSS и JS прямо в HTML.

    python3 tools/preview.py site/remont-holodilnikov/index.html -o preview.html
    python3 tools/preview.py examples/*.html --in-place

ЗАЧЕМ

Боевые страницы ссылаются на /assets/style.css и /assets/app.js абсолютным
путём — иначе ссылки сломаются на вложенных адресах вида
/remont-holodilnikov/surgut/ и на странице 404, которая отдаётся по любому URL.

Но такой файл нельзя просто открыть двойным кликом или отправить кому-то:
абсолютный путь указывает в корень диска, относительный — в соседнюю папку,
которой рядом с одиноким файлом нет. Браузер показывает голый HTML без стилей.

Поэтому для просмотра и для отправки делается отдельная копия, внутри которой
лежит всё необходимое. Такой файл открывается где угодно и ничего вокруг себя
не требует.

⚠️ НА ХОСТИНГ ЭТИ КОПИИ НЕ ВЫКЛАДЫВАЮТСЯ. Они дублируют 70 КБ стилей в каждой
странице и ломают кэш — ровно то, ради чего ассеты и выносились в отдельные
файлы. Для продакшена берите site/<услуга>/index.html.
"""

import argparse
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Пути, которыми страницы ссылаются на ассеты: абсолютный в боевой сборке,
# относительные — в ранее сделанных превью.
#
# ⚠️ Регулярки привязаны к НАЧАЛУ СТРОКИ (?m)^ и это принципиально.
# Внутри самого style.css в шапке написано «Подключается на всех страницах:
# <link rel="stylesheet" href="/assets/style.css">». Без привязки к началу
# строки повторный прогон по уже вшитому файлу находит это упоминание
# в комментарии и вшивает стили ВТОРОЙ раз. Так и произошло: файлы примеров
# распухли до 280 КБ с тройным CSS внутри.
LINK_RE = re.compile(r'(?m)^[ \t]*<link rel="stylesheet" href="(?:/|\.\./|)assets/style\.css">\n?')
SCRIPT_RE = re.compile(r'(?m)^[ \t]*<script src="(?:/|\.\./|)assets/app\.js" defer></script>\n?')

# Признак того, что стили уже внутри файла
ALREADY_INLINED = re.compile(r'<style>.*?\.wrap\{max-width:1080px', re.S)


def read_asset(name):
    path = os.path.join(ROOT, 'assets', name)
    if not os.path.isfile(path):
        sys.exit('не найден %s — сначала соберите ассеты' % path)
    return io.open(path, encoding='utf-8').read()


def inline(page, css, js):
    """Убирает внешние подключения и вставляет их содержимое."""
    if ALREADY_INLINED.search(page):
        sys.exit('стили уже вшиты в этот файл — повторный прогон продублирует их.\n'
                 'Пересоберите страницу из шаблона и прогоните preview.py один раз.')
    if not LINK_RE.search(page):
        sys.exit('в файле нет подключения assets/style.css — нечего вшивать')

    # ⚠️ Внутри встроенного <script> любой литерал </script> закрывает блок —
    # даже если он стоит в комментарии или в строке. У нас такой литерал есть:
    # в шапке app.js описано, как файл подключается. Без экранирования браузер
    # обрывает скрипт на этой строке, и остальные 13 КБ кода вываливаются
    # на страницу видимым текстом. То же правило для </style> в CSS.
    js = js.replace('</script', '<\\/script')
    css = css.replace('</style', '<\\/style')

    page = LINK_RE.sub('<style>\n%s\n</style>\n' % css, page, count=1)

    # Скрипт переносим в конец body. Атрибут defer у встроенного скрипта
    # игнорируется, поэтому в <head> он выполнился бы до разбора разметки
    # и не нашёл ни одного элемента.
    page = SCRIPT_RE.sub('', page)
    page = page.replace('</body>', '<script>\n%s\n</script>\n</body>' % js, 1)
    return page


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='+')
    ap.add_argument('-o', '--out', help='куда записать (только для одного файла)')
    ap.add_argument('--in-place', action='store_true', help='перезаписать исходные файлы')
    args = ap.parse_args()

    if args.out and len(args.files) > 1:
        sys.exit('-o работает только с одним файлом')
    if not args.out and not args.in_place:
        sys.exit('укажите -o или --in-place')

    css, js = read_asset('style.css'), read_asset('app.js')

    for src in args.files:
        page = io.open(src, encoding='utf-8').read()
        out = inline(page, css, js)
        dst = args.out or src
        io.open(dst, 'w', encoding='utf-8').write(out)
        print('  %-46s %6.1f КБ' % (os.path.relpath(dst, ROOT), len(out.encode('utf-8')) / 1024))


if __name__ == '__main__':
    main()
