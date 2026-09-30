#!/usr/bin/env python3
"""Catalog extractor for artistchap.ir.

Probes three transports in order and stops at the first that yields products:
  1. WooCommerce Store API  /wp-json/wc/store/v1/products
  2. WordPress REST         /wp-json/wp/v2/product
  3. Sitemap + HTML         /wp-sitemap.xml -> product URLs -> JSON-LD

Writes data/raw_catalog.jsonl (one SKU per line) and data/extract_report.json.
Stdlib only. Resumable: URLs already in the JSONL are skipped.
"""
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser

BASE = "https://artistchap.ir"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CATALOG = os.path.join(DATA, "raw_catalog.jsonl")
REPORT = os.path.join(DATA, "extract_report.json")
CA_BUNDLE = "/root/.ccr/ca-bundle.crt"
UA = "Mozilla/5.0 (compatible; catalog-indexer/1.0)"
DELAY = 1.0          # seconds between requests
RETRIES = 3          # attempts per URL
TAG_RE = re.compile(r"<[^>]+>")


def ssl_ctx():
    if os.path.exists(CA_BUNDLE):
        return ssl.create_default_context(cafile=CA_BUNDLE)
    return ssl.create_default_context()


CTX = ssl_ctx()


def get(url, timeout=45):
    """Fetch a URL as text. Returns (status, body). Retries with backoff."""
    last = None
    for attempt in range(RETRIES):
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                   "Accept-Language": "fa,en"})
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (404, 401, 403):       # definitive, do not retry
                return e.code, ""
            last = "HTTP %s" % e.code
        except Exception as e:                   # noqa: BLE001 - network is messy
            last = type(e).__name__ + ": " + str(e)
        time.sleep(2 ** attempt)
    print("  ! %s -> %s" % (url, last), file=sys.stderr)
    return 0, ""


def clean(s):
    """Strip tags and collapse whitespace."""
    if not s:
        return ""
    return " ".join(TAG_RE.sub(" ", str(s)).split())


def done_urls():
    seen = set()
    if os.path.exists(CATALOG):
        with open(CATALOG, encoding="utf-8") as fh:
            for line in fh:
                try:
                    seen.add(json.loads(line)["url"])
                except Exception:                # noqa: BLE001 - tolerate a torn line
                    pass
    return seen


def emit(records, seen, fh):
    """Append records whose url is new. Returns how many were written."""
    n = 0
    for rec in records:
        if not rec.get("url") or rec["url"] in seen:
            continue
        seen.add(rec["url"])
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        n += 1
    return n


# ---------------------------------------------------------------- transport 1

def from_store_api(page):
    url = "%s/wp-json/wc/store/v1/products?per_page=100&page=%d" % (BASE, page)
    status, body = get(url)
    if status != 200 or not body:
        return None
    try:
        items = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(items, list):
        return None
    out = []
    for p in items:
        attrs = {}
        for a in p.get("attributes") or []:
            terms = [clean(t.get("name")) for t in (a.get("terms") or [])]
            if a.get("name") and terms:
                attrs[clean(a["name"])] = terms
        prices = p.get("prices") or {}
        out.append({
            "url": p.get("permalink", ""),
            "sku": p.get("sku") or "",
            "title_fa": clean(p.get("name")),
            "categories": [clean(c.get("name")) for c in (p.get("categories") or [])],
            "attributes": attrs,
            "short_desc": clean(p.get("short_description"))[:600],
            "stock_status": (p.get("stock_availability") or {}).get("text")
                            or ("in_stock" if p.get("is_in_stock") else "out_of_stock"),
            "price_raw": prices.get("price", ""),
            "currency": prices.get("currency_code", ""),
            "image_urls": [i.get("src", "") for i in (p.get("images") or []) if i.get("src")],
            "source": "store_api",
        })
    return out


# ---------------------------------------------------------------- transport 2

def from_wp_rest(page):
    url = "%s/wp-json/wp/v2/product?per_page=100&page=%d" % (BASE, page)
    status, body = get(url)
    if status != 200 or not body:
        return None
    try:
        items = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(items, list):
        return None
    return [{
        "url": p.get("link", ""),
        "sku": "",
        "title_fa": clean((p.get("title") or {}).get("rendered")),
        "categories": [],
        "attributes": {},
        "short_desc": clean((p.get("excerpt") or {}).get("rendered"))[:600],
        "stock_status": "",
        "price_raw": "",
        "currency": "",
        "image_urls": [],
        "source": "wp_rest",
    } for p in items]


# ---------------------------------------------------------------- transport 3

class AttrTableParser(HTMLParser):
    """Collect WooCommerce product-attribute rows: <th>label</th><td>value</td>."""

    def __init__(self):
        super().__init__()
        self.rows = {}
        self.cell = None
        self.buf = []
        self.label = None

    def handle_starttag(self, tag, attrs):
        if tag in ("th", "td"):
            self.cell = tag
            self.buf = []

    def handle_data(self, data):
        if self.cell:
            self.buf.append(data)

    def handle_endtag(self, tag):
        if tag != self.cell:
            return
        text = " ".join("".join(self.buf).split())
        if tag == "th":
            self.label = text
        elif self.label:
            self.rows[self.label] = [text]
            self.label = None
        self.cell = None


def sitemap_product_urls():
    """Walk the sitemap index and return every product URL found."""
    status, body = get("%s/wp-sitemap.xml" % BASE)
    if status != 200:
        status, body = get("%s/sitemap_index.xml" % BASE)
    if status != 200:
        return []
    children = [u for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body)
                if "product" in u.lower()]
    urls = []
    for child in children or re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body):
        time.sleep(DELAY)
        st, sub = get(child)
        if st != 200:
            continue
        for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sub):
            if "/product/" in loc or "/محصول/" in loc:
                urls.append(loc)
    return sorted(set(urls))


def scrape_product_page(url):
    status, body = get(url)
    if status != 200 or not body:
        return None
    rec = {"url": url, "sku": "", "title_fa": "", "categories": [], "attributes": {},
           "short_desc": "", "stock_status": "", "price_raw": "", "currency": "",
           "image_urls": [], "source": "html"}

    # JSON-LD Product block, when the theme emits one
    for blob in re.findall(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            body, re.S | re.I):
        try:
            node = json.loads(blob)
        except json.JSONDecodeError:
            continue
        for item in (node.get("@graph", []) if isinstance(node, dict)
                     else node if isinstance(node, list) else [node]):
            if not isinstance(item, dict) or item.get("@type") != "Product":
                continue
            rec["title_fa"] = clean(item.get("name")) or rec["title_fa"]
            rec["sku"] = item.get("sku") or rec["sku"]
            rec["short_desc"] = clean(item.get("description"))[:600]
            img = item.get("image")
            if isinstance(img, str):
                rec["image_urls"] = [img]
            elif isinstance(img, list):
                rec["image_urls"] = [i if isinstance(i, str) else i.get("url", "")
                                     for i in img]
            offer = item.get("offers")
            offer = offer[0] if isinstance(offer, list) and offer else offer
            if isinstance(offer, dict):
                rec["price_raw"] = str(offer.get("price", ""))
                rec["currency"] = offer.get("priceCurrency", "")
                rec["stock_status"] = str(offer.get("availability", "")).rsplit("/", 1)[-1]

    if not rec["title_fa"]:
        m = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.S | re.I)
        rec["title_fa"] = clean(m.group(1)) if m else ""

    m = re.search(r'<table[^>]*class="[^"]*woocommerce-product-attributes[^"]*".*?</table>',
                  body, re.S | re.I)
    if m:
        p = AttrTableParser()
        p.feed(m.group(0))
        rec["attributes"] = p.rows

    rec["categories"] = [clean(c) for c in re.findall(
        r'rel="tag"[^>]*>(.*?)</a>', body, re.S | re.I)]
    if not rec["image_urls"]:
        rec["image_urls"] = re.findall(
            r'class="[^"]*wp-post-image[^"]*"[^>]*src="([^"]+)"', body)[:4]
    return rec if rec["title_fa"] else None


# ---------------------------------------------------------------------- driver

def main():
    os.makedirs(DATA, exist_ok=True)
    seen = done_urls()
    report = {"target": BASE, "transport": None, "pages": 0, "written": 0,
              "resumed_from": len(seen), "failures": [], "started": time.strftime("%FT%TZ")}

    with open(CATALOG, "a", encoding="utf-8") as fh:
        for name, fetch in (("store_api", from_store_api), ("wp_rest", from_wp_rest)):
            page, written = 1, 0
            while True:
                batch = fetch(page)
                if batch is None:
                    break
                if not batch:
                    break
                written += emit(batch, seen, fh)
                fh.flush()
                report["pages"] = page
                print("  %s page %d: %d items" % (name, page, len(batch)))
                page += 1
                if len(batch) < 100:
                    break
                time.sleep(DELAY)
            if written:
                report["transport"] = name
                report["written"] = written
                break

        if not report["transport"]:
            urls = sitemap_product_urls()
            report["sitemap_urls"] = len(urls)
            written = 0
            for i, url in enumerate(urls, 1):
                if url in seen:
                    continue
                time.sleep(DELAY)
                rec = scrape_product_page(url)
                if rec is None:
                    report["failures"].append(url)
                    continue
                written += emit([rec], seen, fh)
                fh.flush()
                if i % 25 == 0:
                    print("  html %d/%d" % (i, len(urls)))
            report["transport"] = "html" if written else None
            report["written"] = written

    report["total_skus"] = len(seen)
    report["finished"] = time.strftime("%FT%TZ")
    with open(REPORT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != "failures"},
                     ensure_ascii=False, indent=2))
    return 0 if report["transport"] else 1


if __name__ == "__main__":
    sys.exit(main())
