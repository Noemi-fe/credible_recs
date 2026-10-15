"""Each shown product's own page on its maker's site, found by a script (Noemi, 15 Oct 2026, evening, of the links and
images research left: "can you do it automatically?").

The researchers looked products up with web search, which only Claude Code's own tool has, a turn at a time; Google's
search through Gemini can't be used (its terms don't allow storing its results for a site), and the free search APIs
are gone. This needs no search: a maker's site lists the pages it publishes for crawlers in its sitemaps (named in its
robots.txt). So, for each product answers show with no page of its own and not known to be discontinued:
1. its maker's sites: the sites our lists already link whose address spells the brand its name starts with
   (data/product_pages.json, data/prices.json, data/brand_lines.json, data/product_facts.json, the researchers' findings),
   UK sites first; else the brand spelled as a site (<brand>.co.uk, then <brand>.com);
2. the pages its sitemaps list whose address holds every word of the product's model (its name without its brand, its
   type's words and filler: "Patagonia Nano Puff" -> nano, puff): those also holding its type's words first, then the
   fewest other words; never a blog, search, category or help page;
3. at most three of them are read: the first whose own product name (its schema.org Product, else og:title, else its
   <title>) holds every model word is the product's page; its image is the page's own (og:image, else the Product's).
Politely: robots.txt is followed, a site gets one request a second, and a site that refuses tools (401, 403, 429, 503)
is left alone for the run, never asked again as if by a browser.

It writes findings in the researchers' format (engine/buyable.py) for the importer to check as it checks theirs:
"sold_new" only when the maker's own page has a price in pounds and doesn't say it is out of stock or discontinued (the
price list then says it is sold there, with that price); otherwise "unsure", which gives the product its page and says
nothing about where it is sold, so what the price list says stays as it was. A product whose name has no model words
(a brand alone) or whose page isn't found gets nothing.

    python -m engine.maker_pages find <shown-products.jsonl> <found-auto.jsonl> [--limit N]
        <shown-products.jsonl>: one {"name", "type", "category", "picks", "worth", "line"} a line, the products answers
        show; most shown first; products already in <found-auto.jsonl> or tried before (its .tried file) are skipped
"""

import gzip
import html
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import unquote, urljoin, urlsplit

from engine.buyable import _maker_of
from engine.links import is_direct_page, is_linkable

AGENT = "credible-recs-maker-pages/1.0 (reads makers' sitemaps and product pages; github.com/Noemi-fe/credible_recs)"
PAUSE_SECONDS = 1.0  # between two requests to one site
TIMEOUT_SECONDS = 15
MAX_SITEMAP_BYTES = 15_000_000
MAX_PAGE_BYTES = 3_000_000
MAX_SITEMAPS = 12  # sitemap files read per site
SITEMAP_NAMES = ("sitemap.xml", "sitemap_index.xml", "wp-sitemap.xml", "sitemap_products_1.xml")  # robots.txt naming none
MAX_CANDIDATES = 3  # pages read per site for one product
MAX_SITES = 3  # sites tried for one product
REFUSING = {401, 403, 429, 503}
FILLER = {"a", "an", "and", "the", "of", "for", "with", "from", "by", "in", "on", "my", "our", "their", "vintage",
          "used", "old", "older", "newer", "model", "models", "version", "colored", "coloured", "high", "waisted",
          "pre", "era", "style"}
# Words of a product's name its page's address often leaves out ("Stridex Maximum Pads" at /product/stridex-maximum/):
# a page's address must hold the model's other words, and its own name all of them but these.
GENERIC = {"pads", "pad", "cream", "creme", "gel", "serum", "lotion", "oil", "wash", "cleanser", "spray", "balm", "mask",
           "toner", "essence", "treatment", "set", "kit", "pack", "bottle", "bottles", "original", "classic", "new"}
# Address words of pages that aren't a product's own: blogs, help, searches, categories ("/c/"), shops' lists.
NOT_PRODUCT_WORDS = {"blog", "blogs", "news", "article", "articles", "recipe", "recipes", "guide", "guides", "review",
                     "reviews", "support", "help", "faq", "faqs", "manual", "manuals", "search", "cart", "account",
                     "collection", "collections", "category", "categories", "c", "tag", "tags", "store", "stores",
                     "press", "careers", "compare", "comparison", "vs", "community", "forum", "forums", "gp"}
NOT_PRODUCT_HOSTS = re.compile(r"^(?:support|help|community|forums?|blog|docs|faq|kb|developer|investors?)\.")
# A country in an address: a site's first label ("at.camelbak.com") or path's first part ("/au_en/", "/fr-fr/").
COUNTRY_LABEL = re.compile(r"^[a-z]{2}$")
LOCALE_PART = re.compile(r"^(?:[a-z]{2}|[a-z]{2}[-_][a-z]{2})$")
OURS = {"uk", "gb", "en-gb", "en_gb", "gb-en", "gb_en", "uk-en", "uk_en", "en-uk", "en_uk"}
NEUTRAL = {"en", "us", "en-us", "en_us", "us-en", "us_en", "eu", "int", "global", "intl", "www"}
LOC = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.DOTALL)
LD_JSON = re.compile(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)
META = re.compile(r"<meta\s[^>]*>", re.IGNORECASE)
ATTRIBUTE = re.compile(r"""([a-zA-Z:_-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.DOTALL | re.IGNORECASE)


# --- Reading sites politely ---

@dataclass
class Response:
    status: int
    url: str  # where it ended, redirects followed
    body: bytes


def fetch(url: str, max_bytes: int) -> Response | None:
    """One GET over the network, as this script (AGENT); None when the site doesn't answer."""
    import ssl

    import certifi
    # Python from python.org on macOS has no certificates of its own; certifi brings the standard set.
    context = ssl.create_default_context(cafile=certifi.where())
    request = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=context) as response:
            body = response.read(max_bytes + 1)
            if response.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            return Response(response.status, response.url, body[:max_bytes])
    except urllib.error.HTTPError as e:
        return Response(e.code, url, b"")
    except Exception:  # no answer, a bad certificate, a cut-off gzip: nothing read
        return None


class Sites:
    """Reads sites as the module says: robots.txt first, a pause between two requests to one site, and a site that
    refuses tools left alone. `get`, `sleep` and `clock` are the network's and time's (tests give fakes)."""

    def __init__(self, get: Callable[[str, int], Response | None] = fetch, sleep=time.sleep, clock=time.monotonic):
        self._get, self._sleep, self._clock = get, sleep, clock
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._last: dict[str, float] = {}
        self.refused: set[str] = set()
        self.requests = 0

    def read(self, url: str, max_bytes: int = MAX_PAGE_BYTES) -> Response | None:
        """The page, when robots.txt allows it and its site hasn't refused; None otherwise."""
        robots = self.robots(_host(url))
        if robots is None or not robots.can_fetch(AGENT, url):
            return None
        return self._request(url, max_bytes)

    def robots(self, host: str) -> urllib.robotparser.RobotFileParser | None:
        """The site's robots.txt rules (a missing one allows everything); None for a site refusing or not answering."""
        if host not in self._robots:
            response = self._request(f"https://{host}/robots.txt", 500_000)
            rules = None
            if response is not None and response.status not in REFUSING and response.status < 500:
                rules = urllib.robotparser.RobotFileParser()
                rules.parse(response.body.decode("utf-8", "replace").splitlines() if response.status == 200 else [])
            self._robots[host] = rules
        return self._robots[host]

    def _request(self, url: str, max_bytes: int) -> Response | None:
        host = _host(url)
        if host in self.refused:
            return None
        wait = self._last.get(host, -PAUSE_SECONDS) + PAUSE_SECONDS - self._clock()
        if wait > 0:
            self._sleep(wait)
        self._last[host] = self._clock()
        self.requests += 1
        response = self._get(url, max_bytes)
        if response is not None and response.status in REFUSING:
            self.refused.add(host)
        return response


def _host(url: str) -> str:
    return urlsplit(url).netloc.lower()


# --- A maker's sitemaps ---

def sitemap_pages(sites: Sites, host: str) -> list[tuple[str, str]]:
    """(page, sitemap) for every page the site's sitemaps list: robots.txt's sitemaps, else /sitemap.xml; an index's
    product sitemaps and UK ones first, at most MAX_SITEMAPS files."""
    robots = sites.robots(host)
    if robots is None:
        return []
    queue = list(robots.site_maps() or []) or [f"https://{host}/{name}" for name in SITEMAP_NAMES]
    pages, read = [], 0
    while queue and read < MAX_SITEMAPS:
        sitemap = queue.pop(0)
        response = sites.read(sitemap, MAX_SITEMAP_BYTES)
        if response is None or response.status != 200:
            continue
        if sitemap.rsplit("/", 1)[-1] in SITEMAP_NAMES and not robots.site_maps():
            queue = [q for q in queue if q.rsplit("/", 1)[-1] not in SITEMAP_NAMES]  # the first one found will do
        read += 1
        body = response.body
        if body[:2] == b"\x1f\x8b":
            try:
                body = gzip.decompress(body)
            except Exception:
                continue
        text = body.decode("utf-8", "replace")
        locs = [html.unescape(loc) for loc in LOC.findall(text)]
        if "<sitemapindex" in text:
            queue = sorted(queue + locs, key=_sitemap_rank)
        else:
            pages += [(loc, sitemap) for loc in locs]
    return pages


def _sitemap_rank(url: str) -> tuple:
    low = url.lower()
    return ("product" not in low, not re.search(r"en[-_]gb|/gb/|/uk/|[-_.]uk\b", low),
            bool(re.search(r"blog|post|article|news|recipe|video|image|page|store|faq|help|categor|collection", low)))


# --- Which page is the product's ---

def words_of(text: str) -> list[str]:
    """Lowercase words and numbers, accents taken off ("Wüsthof Classic 8\"" -> wusthof, classic, 8)."""
    plain = unicodedata.normalize("NFKD", unquote(text).lower().replace("&", " and "))
    return re.findall(r"[a-z0-9]+", "".join(c for c in plain if not unicodedata.combining(c)))


def model_words(name: str, brand: str, product_type: str) -> list[str]:
    """The words of a product's name that tell it from its maker's other products: its name without its brand, its
    type's words and filler ("Patagonia Nano Puff", "Patagonia", "jacket" -> nano, puff). Empty for a brand alone."""
    brand_words = set(words_of(brand))
    type_words = {w for t in words_of(product_type) for w in (t, t + "s", t + "es")}
    return [w for w in dict.fromkeys(words_of(name))
            if w not in brand_words and w not in type_words and w not in FILLER and (len(w) > 1 or w.isdigit())]


def holds(text_words: list[str], wanted: Iterable[str]) -> bool:
    """Whether every wanted word is among the words, or (four letters or more) inside them run together ("nanopuff"),
    a plural's "s" aside ("bumpers" at /rogue-echo-bumper-plates)."""
    stems = [_stem(w) for w in text_words]
    joined = "".join(text_words)
    return all(_stem(w) in stems or (len(w) >= 4 and _stem(w) in joined) for w in wanted)


def _stem(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def candidates(pages: list[tuple[str, str]], words: list[str], product_type: str) -> list[tuple[str, str]]:
    """The pages whose address holds every model word, best first: those also holding the type's words, then the fewest
    other words, then the shortest; never a blog, search, category or help page."""
    type_words = words_of(product_type)
    needed = [w for w in words if w not in GENERIC] or words
    found = []
    for page, sitemap in pages:
        parts = urlsplit(page)
        path_words = words_of(parts.path)
        country = country_of(page)
        if (country == "abroad" or NOT_PRODUCT_HOSTS.match(parts.netloc.lower()) or not is_direct_page(page)
                or NOT_PRODUCT_WORDS & set(path_words) or not holds(path_words, needed)):
            continue
        rank = (country != "uk", not holds(path_words, type_words), not holds(path_words, words),
                len(path_words) - len(words), len(page))
        found.append((rank, page, sitemap))
    return [(page, sitemap) for _, page, sitemap in sorted(found)[:MAX_CANDIDATES]]


def country_of(url: str) -> str:
    """"uk" for a UK address (a .uk site, or a UK part: /en-gb/, uk.), "abroad" for another country's (at.camelbak.com,
    /au_en/; the US, the EU and English alone count as neither), else "any"."""
    parts = urlsplit(url)
    host = parts.netloc.lower()
    first = (parts.path.strip("/").split("/") or [""])[0].lower()
    label = host.split(".")[0]
    if host.endswith(".uk") or first in OURS or label in OURS:
        return "uk"
    if (COUNTRY_LABEL.match(label) and label not in NEUTRAL) or (LOCALE_PART.match(first) and first not in NEUTRAL):
        return "abroad"
    return "any"


@dataclass
class PageFacts:
    is_product: bool  # it has a schema.org Product, or its og:type says product
    names: list[str]  # its schema.org Product's name, og:title, <title>
    image: str | None
    price: float | None
    currency: str | None
    in_stock: bool | None  # None when the page doesn't say
    site_name: str | None


def read_page(text: str, url: str) -> PageFacts:
    """What a product page says of its product: its schema.org Product (JSON-LD) first, then its Open Graph tags."""
    products = [p for block in LD_JSON.findall(text) for p in _products(_json(block))]
    meta = {}
    for tag in META.findall(text):
        attributes = {k.lower(): a or b for k, a, b in ATTRIBUTE.findall(tag)}
        key = attributes.get("property") or attributes.get("name")
        if key and "content" in attributes:
            meta.setdefault(key.lower(), html.unescape(attributes["content"]).strip())
    title = TITLE.search(text)
    names = [str(p["name"]) for p in products if isinstance(p.get("name"), str)]
    names += [n for n in (meta.get("og:title"), html.unescape(title.group(1)).strip() if title else None) if n]
    image = meta.get("og:image") or next((i for p in products if (i := _image(p.get("image")))), None)
    price, currency, in_stock = None, None, None
    for offer in (o for p in products for o in _offers(p.get("offers"))):
        availability = str(offer.get("availability") or "").lower()
        if availability:
            in_stock = not re.search(r"outofstock|soldout|discontinued", availability)
        try:
            amount = float(str(offer.get("price") or offer.get("lowPrice") or "").replace(",", ""))
        except ValueError:
            continue
        if amount > 0:
            price, currency = amount, str(offer.get("priceCurrency") or "").upper() or None
            break
    is_product = bool(products) or "product" in (meta.get("og:type") or "").lower()
    return PageFacts(is_product, names, urljoin(url, image) if image else None, price, currency, in_stock,
                     meta.get("og:site_name"))


def _json(block: str):
    try:
        return json.loads(html.unescape(block.strip()), strict=False)
    except ValueError:
        return None


def _products(data) -> list[dict]:
    if isinstance(data, list):
        return [p for item in data for p in _products(item)]
    if not isinstance(data, dict):
        return []
    kinds = data.get("@type")
    kinds = kinds if isinstance(kinds, list) else [kinds]
    found = [data] if any(k in ("Product", "ProductGroup") for k in kinds) else []
    return found + _products(data.get("@graph")) + _products(data.get("hasVariant"))


def _offers(offers) -> list[dict]:
    if isinstance(offers, list):
        return [o for item in offers for o in _offers(item)]
    if not isinstance(offers, dict):
        return []
    return [offers] + _offers(offers.get("offers"))


def _image(image) -> str | None:
    if isinstance(image, list):
        return next((i for item in image if (i := _image(item))), None)
    if isinstance(image, dict):
        return _image(image.get("url") or image.get("contentUrl"))
    return image if isinstance(image, str) and image else None


# --- One product ---

def maker_sites(name: str, known_hosts: Iterable[str]) -> list[tuple[str, str]]:
    """(site, brand as its name writes it) for the sites that may be the product's maker's: the known sites whose
    address spells the brand its name starts with (after filler words; a brand of under five letters only as a whole
    label: "Baby" isn't babylist.com's), UK ones and the longest brand first, never another country's or a help site;
    else the brand spelled as a site, its first two words then its first one (four letters or more), .co.uk then .com."""
    words = name.split()
    while words and words[0].lower() in FILLER:
        words = words[1:]
    plain = " ".join(words)
    known = []
    for host in sorted(set(known_hosts)):
        brand = _maker_of(plain, host)
        letters = "".join(words_of(brand or ""))
        if (brand is None or (len(letters) < 5 and letters not in host.split("."))
                or NOT_PRODUCT_HOSTS.match(host) or country_of(f"https://{host}/") == "abroad"):
            continue
        known.append((host, brand))
    if known:
        known.sort(key=lambda hb: (country_of(f"https://{hb[0]}/") != "uk", -len(hb[1]), not hb[0].startswith("www.")))
        return known[:MAX_SITES]
    guesses = []
    for k in (2, 1):
        letters = "".join(words_of(" ".join(words[:k])))
        if len(words) >= k and len(letters) >= 4:
            guesses += [(f"www.{letters}.co.uk", " ".join(words[:k])), (f"www.{letters}.com", " ".join(words[:k]))]
    return list(dict.fromkeys(guesses))[:2 * MAX_SITES]


def find_product(product: dict, known_hosts: Iterable[str], sites: Sites, sitemaps: dict, today: date,
                 why: list | None = None) -> dict | None:
    """A finding for one shown product ({"name", "type", "category"}), or None when its page isn't found (and why, in
    `why`). `sitemaps` keeps each site's sitemap pages for the run."""
    name, product_type = product["name"], product["type"]
    why = why if why is not None else []
    makers = maker_sites(name, known_hosts)
    if not makers:
        why.append("no maker's site")
    for host, brand in makers:
        words = model_words(name, brand, product_type)
        if not words:
            why.append(f"{host}: a brand alone")
            continue
        if host not in sitemaps:
            sitemaps[host] = sitemap_pages(sites, host)
        if not sitemaps[host]:
            why.append(f"{host}: {'refuses tools' if host in sites.refused else 'no sitemap pages'}")
            continue
        found = candidates(sitemaps[host], words, product_type)
        if not found:
            why.append(f"{host}: no page holds {' '.join(words)} ({len(sitemaps[host])} pages)")
        needed = [w for w in words if w not in GENERIC] or words
        for page, sitemap in found:
            response = sites.read(page)
            if response is None or response.status != 200 or not is_direct_page(response.url):
                why.append(f"{page}: not read ({response.status if response else 'no answer or robots.txt'})")
                continue
            facts = read_page(response.body.decode("utf-8", "replace"), response.url)
            named = next((n for n in facts.names if holds(words_of(n), needed)), None)
            if not facts.is_product or named is None or country_of(response.url) == "abroad":
                why.append(f"{page}: {'not a product page' if not facts.is_product else 'abroad' if named else 'named ' + (facts.names or ['nothing'])[0][:50]}")
                continue
            return _finding(product, brand, response.url, sitemap, named, facts, today)
    return None


def _finding(product: dict, brand: str, page: str, sitemap: str, named: str, facts: PageFacts, today: date) -> dict:
    shop = brand
    if facts.site_name and words_of(facts.site_name)[:1] == words_of(brand)[:1] and len(facts.site_name) <= 30:
        shop = facts.site_name
    elif brand == brand.lower():
        shop = brand.title()
    sold = facts.currency == "GBP" and facts.price is not None and facts.in_stock is not False
    image = facts.image if is_linkable(facts.image) else None
    note = (f"Found by engine.maker_pages in the sitemap {sitemap}; the page names it \"{named[:120]}\""
            + (f"; {facts.currency} {facts.price:g} on the page" if facts.price else "")
            + ("; it says out of stock or discontinued" if facts.in_stock is False else "") + ".")
    return {"name": product["name"], "type": product["type"], "category": product["category"],
            "status": "sold_new" if sold else "unsure", "product_page": page, "shop": shop,
            "price_gbp": facts.price if sold else None, "price_url": page if sold else None,
            "image_url": image, "image_page": page if image else None,
            "sources": list(dict.fromkeys([page, sitemap])), "checked_on": today.isoformat(), "note": note}


# --- What to look for ---

def known_hosts(root: Path = Path(".")) -> set[str]:
    """Every site our lists and the researchers' findings link (makers' among them)."""
    urls: list[str] = []

    def walk(value):
        if isinstance(value, str) and value.startswith("https://"):
            urls.append(value)
        elif isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    for name in ("prices.json", "product_pages.json", "brand_lines.json", "product_facts.json"):
        path = root / "data" / name
        if path.is_file():
            walk(json.loads(path.read_text(encoding="utf-8")))
    for path in (root / "docs").glob("handoff-*/research/found-*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                walk(json.loads(line))
    return {_host(url) for url in urls if is_linkable(url)}


def to_find(shown: list[dict]) -> list[dict]:
    """The shown products (not brand lines) with no page of their own and not known to be discontinued, most shown
    first: picks count twice an Also worth a look."""
    from engine.prices import counts_as_sold, find_availability, load_prices
    from engine.product_pages import find_page, load_product_pages
    pages, prices = load_product_pages(), load_prices()
    left = [s for s in shown if not s.get("line")
            and find_page([s["name"]], s["category"], s["type"], pages) is None
            and counts_as_sold(find_availability(s["name"], s["category"], prices)) is not False]
    return sorted(left, key=lambda s: -(2 * s.get("picks", 0) + s.get("worth", 0)))


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[0] != "find":
        print(__doc__.split("\n\n")[-1])
        return 2
    shown_path, out_path = Path(argv[1]), Path(argv[2])
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None
    tried_path = out_path.with_suffix(".tried")
    tried = set(tried_path.read_text(encoding="utf-8").splitlines()) if tried_path.is_file() else set()
    if out_path.is_file():
        tried |= {json.loads(line)["name"] for line in out_path.read_text(encoding="utf-8").splitlines() if line}
    shown = [json.loads(line) for line in shown_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    todo = [s for s in to_find(shown) if s["name"] not in tried][:limit]
    hosts, sites, sitemaps, found = known_hosts(), Sites(), {}, 0
    print(f"{len(todo)} products to look for, {len(hosts)} known sites", flush=True)
    for i, product in enumerate(todo, 1):
        why = []
        finding = find_product(product, hosts, sites, sitemaps, date.today(), why)
        if finding is not None:
            found += 1
            with out_path.open("a", encoding="utf-8") as out:
                out.write(json.dumps(finding, ensure_ascii=False) + "\n")
        with tried_path.open("a", encoding="utf-8") as out:
            out.write(product["name"] + "\n")
        print(f"[{i}/{len(todo)}] {product['name']}: "
              + (f"FOUND {finding['status']} {finding['product_page']}" if finding else "; ".join(why[:3])), flush=True)
    print(f"Found {found} of {len(todo)} ({sites.requests} requests; sites refusing tools: {len(sites.refused)})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
