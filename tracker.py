import sqlite3
import time
from datetime import datetime
import httpx
from bs4 import BeautifulSoup

DB_PATH = "tracker.db"
DOMAIN = "https://sibdroid.ru"
AJAX_URL = f"{DOMAIN}/ajax/sib/catalog.php"

# Новый фильтр: В наличии, 256 ГБ, 12 ГБ ОЗУ, цена 30 000 - 80 000 ₽
FILTER_PATH = (
    "/catalog/smartfony_samsung/filter/"
    "sib_avail_14647-is-available/"
    "vstroennaya_pamyat-is-d323a77b-b942-11e6-8a88-f0795970fe80/"
    "obem_operativnoy_pamyati-is-a365c71f-c318-11ed-8a22-a8a1598bc6ff/"
    "sib_min_price_base-from-30000-to-80000/apply/"
    "?view=list&page_count=12&sort=shows&by=desc"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Accept": "*/*",
    "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{DOMAIN}{FILTER_PATH}",
}

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL REFERENCES products(id),
                price INTEGER NOT NULL,
                recorded_at TEXT NOT NULL
            )
        """)
        conn.commit()

def parse_items_from_html(html_text: str):
    soup = BeautifulSoup(html_text, "html.parser")
    items = soup.select("li.catalog-item")
    parsed = []

    for item in items:
        title_tag = item.select_one('.c20-title span[itemprop="name"]')
        price_tag = item.select_one('.c20-price meta[itemprop="price"]')
        sku_tag = item.select_one('.c20-price meta[itemprop="sku"]')
        link_tag = item.select_one("a.c20-title")

        if not (title_tag and price_tag and sku_tag and link_tag):
            continue

        link = link_tag["href"]
        if link.startswith("/"):
            link = f"{DOMAIN}{link}"

        parsed.append({
            "title": title_tag.get_text(strip=True),
            "price": int(price_tag["content"]),
            "sku": sku_tag["content"],
            "url": link,
        })
    return parsed

def fetch_all_items():
    all_items = []
    seen_skus = set()

    with httpx.Client(headers=HEADERS, timeout=15.0) as client:
        # 1. Загрузка первых 36 позиций (GET)
        print("Запрос страницы 1 (GET)...")
        r = client.get(f"{DOMAIN}{FILTER_PATH}")
        r.raise_for_status()

        page_items = parse_items_from_html(r.text)
        for item in page_items:
            if item["sku"] not in seen_skus:
                seen_skus.add(item["sku"])
                all_items.append(item)
        print(f"Страница 1: получено {len(page_items)} шт.")

        # 2. Дозагрузка оставшихся позиций (AJAX POST)
        page = 2
        while True:
            payload = {
                "rz_ajax": "y",
                "site_id": "s1",
                "IBLOCK_ID": "6",
                "REQUEST_URI": FILTER_PATH,
                "SCRIPT_NAME": "/bitrix/urlrewrite.php",
                "view": "list",
                "page_count": "12",
                "sort": "shows",
                "by": "desc",
                "inf_button": "true",
                "PAGEN_1": str(page),
                "MORE_CLICK": "1",
            }

            print(f"Запрос страницы {page} (AJAX POST)...")
            resp = client.post(AJAX_URL, data=payload)
            resp.raise_for_status()

            ajax_items = parse_items_from_html(resp.text)
            if not ajax_items:
                break

            new_found = 0
            for item in ajax_items:
                if item["sku"] not in seen_skus:
                    seen_skus.add(item["sku"])
                    all_items.append(item)
                    new_found += 1

            print(f"Страница {page}: добавлено {new_found} шт.")
            if new_found == 0:
                break

            page += 1
            time.sleep(0.5)

    return all_items

def scrape_and_save():
    init_db()
    items = fetch_all_items()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for item in items:
            cursor.execute("""
                INSERT INTO products (sku, title, url)
                VALUES (?, ?, ?)
                ON CONFLICT(sku) DO UPDATE SET
                    title=excluded.title,
                    url=excluded.url
            """, (item["sku"], item["title"], item["url"]))

            cursor.execute("SELECT id FROM products WHERE sku = ?", (item["sku"],))
            product_id = cursor.fetchone()[0]

            cursor.execute("""
                INSERT INTO price_history (product_id, price, recorded_at)
                VALUES (?, ?, ?)
            """, (product_id, item["price"], now_str))

        conn.commit()

    print(f"\nУспешно зафиксировано {len(items)} товаров на {now_str}.")

if __name__ == "__main__":
    scrape_and_save()