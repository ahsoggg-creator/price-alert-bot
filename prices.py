import json
import re
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"}


class PriceNotFound(Exception):
    pass


def to_number(text):
    text = str(text).replace("\xa0", "").replace(" ", "")
    match = re.search(r"\d+(?:[.,]\d+)?", text)
    if not match:
        return None
    return float(match.group().replace(",", "."))


def parse_books_toscrape(soup):
    title = soup.select_one("div.product_main h1").get_text(strip=True)
    price = to_number(soup.select_one("div.product_main p.price_color").get_text())
    return title, price


def parse_generic(soup):
    title = soup.find("meta", property="og:title")
    title = title["content"] if title else (soup.title.get_text(strip=True) if soup.title else "Без названия")

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if not isinstance(item, dict) or item.get("@type") != "Product":
                continue
            offers = item.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price = offers.get("price") or offers.get("lowPrice")
            if price:
                return item.get("name", title), to_number(price)

    for attrs in ({"itemprop": "price"}, {"property": "product:price:amount"}):
        tag = soup.find(attrs=attrs)
        if tag:
            price = to_number(tag.get("content") or tag.get_text())
            if price:
                return title, price

    raise PriceNotFound


SHOPS = {
    "books.toscrape.com": parse_books_toscrape,
}


async def get_product(url):
    connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as response:
            response.raise_for_status()
            html = await response.text()

    soup = BeautifulSoup(html, "html.parser")
    domain = urlparse(url).netloc.removeprefix("www.")
    parser = SHOPS.get(domain, parse_generic)
    try:
        title, price = parser(soup)
    except (AttributeError, TypeError):
        raise PriceNotFound
    if price is None:
        raise PriceNotFound
    return title, price
