"""Build the link-preview "bridge" pages for the Business & Talent Management Newsletter.

Each bridge page is a tiny static page that carries the Open Graph / Twitter tags for one
article (so LinkedIn, Facebook and WhatsApp can build a preview) and sends human visitors
straight on to the real page on milleniumrx.biz.

Run:  python build.py            (then publish.bat, or commit and push the docs/ folder)

It only READS from the newsletter server (the article files, over FTP). Nothing on
milleniumrx.biz is changed. Re-run it whenever a new article is published or scheduled.
"""
import csv
import html
import io
import json
import os
import re
import shutil
import ssl
import sys
from ftplib import FTP_TLS
from urllib.parse import quote

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG = json.load(open(os.path.join(ROOT, 'config.json'), encoding='utf-8'))
OUT = os.path.join(ROOT, 'docs')
SLUGS_FILE = os.path.join(ROOT, 'slugs.json')   # article id -> slug; keeps links stable across runs
BASE = CONFIG['base_url'].rstrip('/')
SITE = CONFIG['newsletter_site'].rstrip('/')
SITE_NAME = 'Business and Talent Management Newsletter'
IMG_W, IMG_H = 1280, 720


# ---------- data ----------

def load_env():
    """FTP login from the environment or from a local .env file (never committed)."""
    env = dict(os.environ)
    path = os.path.join(ROOT, '.env')
    if os.path.isfile(path):
        for line in open(path, encoding='utf-8'):
            if '=' in line and not line.lstrip().startswith('#'):
                k, v = line.strip().split('=', 1)
                env.setdefault(k, v)
    return env


def fetch_articles():
    """Read every article file from the newsletter server (read-only)."""
    env = load_env()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE          # the host's FTP certificate does not match its name
    ftp = FTP_TLS(context=ctx, timeout=60)
    ftp.connect(env['NEWSLETTER_FTP_HOST'])
    ftp.login(env['NEWSLETTER_FTP_USER'], env['NEWSLETTER_FTP_PASS'])
    ftp.prot_p()
    ftp.cwd('articles')
    articles = []
    for name in sorted(ftp.nlst()):
        if not re.match(r'^\d{8}-.+\.json$', name):
            continue                          # index.json, share_log.json, config files...
        buf = io.BytesIO()
        ftp.retrbinary('RETR ' + name, buf.write)
        a = json.loads(buf.getvalue().decode('utf-8'))
        if isinstance(a, dict) and a.get('status') in ('published', 'scheduled') and a.get('title'):
            articles.append(a)
    ftp.quit()
    articles.sort(key=lambda a: a.get('publish_date', ''))
    return articles


# ---------- text helpers ----------

def shorten(text, limit=200):
    text = ' '.join((text or '').split())
    if len(text) <= limit:
        return text
    cut = text[:limit - 3]
    if ' ' in cut:
        cut = cut[:cut.rindex(' ')]
    return cut.rstrip(' ,;:–-') + '...'


def make_slug(title, taken):
    words = re.sub(r'[^a-z0-9]+', ' ', title.lower().replace('&', ' and ').replace("'", '').replace('’', '')).split()
    picked = []
    for w in words:
        if picked and (len('-'.join(picked + [w])) > 45 or len(picked) >= 6):
            break
        picked.append(w)
    while len(picked) > 1 and picked[-1] in ('a', 'an', 'and', 'for', 'from', 'how', 'in', 'of', 'on', 'the', 'to', 'vs', 'with'):
        picked.pop()
    slug = '-'.join(picked) or 'article'
    base, n = slug, 2
    while slug in taken:
        slug = f'{base}-{n}'
        n += 1
    return slug


def norm(s):
    return re.sub(r'[^a-z0-9]+', '', s.lower())


# ---------- images ----------

def font(names, size):
    for n in names:
        try:
            return ImageFont.truetype(os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', n), size)
        except OSError:
            pass
    return ImageFont.load_default()


def wrap(draw, text, fnt, width):
    lines, line = [], ''
    for word in text.split():
        trial = (line + ' ' + word).strip()
        if draw.textlength(trial, font=fnt) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + [line]


def title_card(title, subtitle=''):
    """A 1280x720 card in the same style as the ready-made frames (used when no frame exists)."""
    img = Image.new('RGB', (IMG_W, IMG_H))
    px = img.load()
    for y in range(IMG_H):
        for x in range(0, IMG_W, 4):
            t = (x / IMG_W + y / IMG_H) / 2
            c = (int(11 + 4 * t), int(18 + 30 * t), int(48 + 30 * t))
            for dx in range(4):
                px[x + dx, y] = c
    d = ImageDraw.Draw(img)
    d.text((80, 66), 'B U S I N E S S   &   T A L E N T   M A N A G E M E N T   N E W S L E T T E R',
           font=font(['segoeuib.ttf', 'arialbd.ttf'], 17), fill=(125, 211, 252))
    size = 72
    while True:
        fnt = font(['seguibl.ttf', 'segoeuib.ttf', 'arialbd.ttf'], size)
        lines = wrap(d, title, fnt, IMG_W - 160)
        if len(lines) <= 4 or size <= 40:
            break
        size -= 6
    y = 112
    for line in lines:
        d.text((80, y), line, font=fnt, fill=(240, 244, 255))
        y += int(size * 1.18)
    if subtitle:
        sf = font(['segoeui.ttf', 'arial.ttf'], 30)
        y += 14
        for line in wrap(d, subtitle, sf, IMG_W - 160)[:3]:
            d.text((80, y), line, font=sf, fill=(203, 213, 225))
            y += 42
    d.rounded_rectangle((80, y + 22, 200, y + 28), radius=3, fill=(251, 191, 36))
    return img


def load_frames():
    """Ready-made title cards, indexed by article title."""
    folder = CONFIG.get('frames_folder', '')
    index = os.path.join(folder, '_List by article title.csv')
    frames = {}
    if os.path.isfile(index):
        rows = list(csv.reader(open(index, encoding='utf-8-sig')))
        for r in rows[1:]:
            if len(r) >= 2 and os.path.isfile(os.path.join(folder, r[1])):
                frames[norm(r[0])] = os.path.join(folder, r[1])
    return frames


def write_image(src_img, slug):
    img = src_img.convert('RGB')
    if img.size != (IMG_W, IMG_H):
        img = img.resize((IMG_W, IMG_H), Image.LANCZOS)
    os.makedirs(os.path.join(OUT, 'img'), exist_ok=True)
    img.save(os.path.join(OUT, 'img', slug + '.jpg'), 'JPEG', quality=88, optimize=True)
    return f'{BASE}/img/{slug}.jpg'


# ---------- pages ----------

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="{site_name}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:image" content="{image}">
<meta property="og:image:width" content="{w}">
<meta property="og:image:height" content="{h}">
<meta property="og:url" content="{bridge_url}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{desc}">
<meta name="twitter:image" content="{image}">
<script>
// Send readers straight to the real page. Only utm_* tags are carried over (no personal data);
// utm_source=linkedin is added when the link has none.
(function () {{
  var dest = new URL({dest_js});
  new URLSearchParams(location.search).forEach(function (v, k) {{
    if (/^utm_[a-z]+$/.test(k)) dest.searchParams.set(k, v);
  }});
  if (!dest.searchParams.has('utm_source')) dest.searchParams.set('utm_source', {utm_js});
  location.replace(dest.toString());
}})();
</script>
<meta http-equiv="refresh" content="2; url={dest_utm}">
<style>
body{{margin:0;background:#0b1220;color:#e2e8f0;font-family:Segoe UI,Arial,sans-serif;display:flex;min-height:100vh;align-items:center;justify-content:center;text-align:center}}
main{{max-width:36rem;padding:2rem}} h1{{font-size:1.4rem;line-height:1.3}} p{{color:#94a3b8}}
a{{display:inline-block;margin-top:1rem;background:#3b82f6;color:#fff;padding:.7rem 1.4rem;border-radius:8px;text-decoration:none;font-weight:600}}
</style>
</head>
<body>
<main>
<h1>{title}</h1>
<p>{desc}</p>
<a href="{dest_utm}">{link_text}</a>
</main>
</body>
</html>
"""


def write_page(slug, title, desc, image, dest, og_type, link_text):
    utm = CONFIG.get('utm_source', 'linkedin')
    dest_utm = dest + ('&' if '?' in dest else '?') + 'utm_source=' + quote(utm)
    e = lambda s: html.escape(s, quote=True)
    page = PAGE.format(
        title=e(title), desc=e(desc), image=e(image), w=IMG_W, h=IMG_H, og_type=og_type,
        site_name=e(SITE_NAME), bridge_url=e(f'{BASE}/{slug}/' if slug else f'{BASE}/'),
        dest_js=json.dumps(dest).replace('<', '\\u003c'), utm_js=json.dumps(utm),
        dest_utm=e(dest_utm), link_text=e(link_text))
    folder = os.path.join(OUT, slug) if slug else OUT
    os.makedirs(folder, exist_ok=True)
    open(os.path.join(folder, 'index.html'), 'w', encoding='utf-8', newline='\n').write(page)


def main():
    if not BASE.startswith('https://'):
        sys.exit('Set "base_url" in config.json to the bridge site address first.')
    articles = fetch_articles()
    slugs = json.load(open(SLUGS_FILE, encoding='utf-8')) if os.path.isfile(SLUGS_FILE) else {}
    frames = load_frames()

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    open(os.path.join(OUT, '.nojekyll'), 'w').close()

    # Newsletter sign-up page: at /newsletter/ and at the site root.
    n_title = SITE_NAME + ' — Millenium Malaysia Resources'
    n_desc = 'Practical insights on leadership, talent management and organizational growth. Subscribe free to get each new article.'
    n_img = write_image(title_card('Business & Talent Management Newsletter',
                                   'Practical insights on leadership, talent management and organizational growth'), 'newsletter')
    for slug in ('newsletter', ''):
        write_page(slug, n_title, n_desc, n_img, SITE + '/newsletter.html', 'website', 'Continue to the newsletter')

    rows = [('Newsletter sign-up page', 'live', f'{BASE}/newsletter/', SITE + '/newsletter.html')]
    made_cards = []
    taken = set(slugs.values()) | {'newsletter', 'img'}
    for a in articles:
        aid, title = a['id'], a['title'].strip()
        if aid not in slugs:
            slugs[aid] = make_slug(title, taken)
            taken.add(slugs[aid])
        slug = slugs[aid]
        desc = shorten(a.get('teaser') or a.get('excerpt') or '')
        frame = frames.get(norm(title))
        if frame:
            image = write_image(Image.open(frame), slug)
        else:
            image = write_image(title_card(title), slug)
            made_cards.append(title)
        dest = f'{SITE}/article.html?id={quote(aid)}'
        write_page(slug, title, desc, image, dest, 'article', 'Continue to the article')
        rows.append((title, a['status'], f'{BASE}/{slug}/', dest))

    json.dump(slugs, open(SLUGS_FILE, 'w', encoding='utf-8'), indent=2, ensure_ascii=False)

    csv_path = CONFIG.get('links_csv', '')
    if csv_path:
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.writer(f)
            w.writerow(['Article title', 'Status', 'Bridge link (share this)', 'Goes to'])
            w.writerows(rows)

    print(f'{len(articles)} article pages + newsletter page written to {OUT}')
    if made_cards:
        print('No ready-made frame, so a title card was generated for:')
        for t in made_cards:
            print('  -', t)
    if csv_path:
        print('Links list:', csv_path)


if __name__ == '__main__':
    main()
