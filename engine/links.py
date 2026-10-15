"""Links shown to shoppers (Noemi's decisions of 15 Oct 2026, late afternoon: "direct links only").

A card may link to a product's own page, its maker's or a big UK shop's, and show a small image from its maker's own
page. Every such address comes from the researched lists (data/prices.json, data/product_pages.json, data/brand_lines.json),
never from a comment, and is checked here before it is shown, and again on the page (engine/templates/search.html):

- is_linkable: https, with a web address, no spaces, name or password in it, and never Reddit's (writers aren't makers
  or shops, and Reddit's image hosts are Reddit's too);
- is_search_page: a shop's or a search engine's results page (config.SEARCH_PAGE_PATH_STEPS in its path, or one of
  config.SEARCH_PAGE_QUERY_KEYS naming the words searched for). Noemi: no search links, so a product not researched
  yet shows no link. Such an address may still be where a researcher checked that a product isn't sold (an entry that is
  never shown), but it is never linked;
- is_direct_page: both, the test every product link passes.
"""

from urllib.parse import parse_qsl, urlsplit

from engine.config import SEARCH_PAGE_PATH_STEPS, SEARCH_PAGE_QUERY_KEYS

# Reddit's own hosts and its image hosts: never a source of a link or an image.
REDDIT_HOSTS = ("reddit.com", "redd.it", "redditmedia.com", "redditstatic.com")


def is_linkable(url: str | None) -> bool:
    """Whether an address may be shown as a link or loaded as an image: https, with a web address, no spaces, name or
    password in it, and never Reddit's."""
    if not url or not isinstance(url, str) or not url.startswith("https://") or any(c.isspace() for c in url):
        return False
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        unsafe = parts.username is not None or parts.password is not None
    except ValueError:  # a malformed address ("https://[")
        return False
    return bool(host) and not unsafe and not is_reddit_host(host)


def is_reddit_host(host: str) -> bool:
    """Whether a host is Reddit's, or one of its subdomains."""
    host = host.lower().rstrip(".")
    return any(host == name or host.endswith("." + name) for name in REDDIT_HOSTS)


def is_search_page(url: str) -> bool:
    """Whether an address is a results page of a search: a step of its path is a search step ("/search",
    "/sitesearch", eBay's "/sch/", Amazon's "/s"), or its query names the words searched for ("?q=", "?k=",
    "?searchTerm=", eBay's "?_nkw="). A product whose name holds such a word ("/search-and-rescue-torch") isn't one."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    steps = {step.lower() for step in parts.path.split("/") if step}
    if steps & set(SEARCH_PAGE_PATH_STEPS):
        return True
    keys = {key.lower() for key, _ in parse_qsl(parts.query, keep_blank_values=True)}
    return bool(keys & set(SEARCH_PAGE_QUERY_KEYS))


def is_direct_page(url: str | None) -> bool:
    """Whether an address may be a product's link: linkable (is_linkable) and not a search (is_search_page)."""
    return is_linkable(url) and not is_search_page(url)
