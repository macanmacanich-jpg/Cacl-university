import json
import time
import argparse
import logging
from pathlib import Path
from dataclasses import dataclass, asdict

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

DATA_FILE = Path(__file__).parent / "universities.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


@dataclass
class RawUniversity:
    name: str
    country: str
    city: str
    fields: list
    ielts_min: float
    toefl_min: int
    gpa_min: float
    tuition_usd: int
    scholarship: bool
    url: str
    description: str = ""


#selenium драйвер ──────────────────────────────────────────────────────────

def get_driver():
    options = Options()
    options.add_argument("--headless")   # браузер без окна
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),  # сам скачает нужный драйвер
        options=options
    )
    return driver


#парсер MastersPortal (динамический) 

def parse_mastersportal(field: str, country: str) -> list[RawUniversity]:
    """
    mastersportal.eu — динамический сайт, данные грузятся через JS.
    Поэтому используем Selenium — он открывает браузер и ждёт загрузки.

    Что извлекаем:
      .university-block__name  → название вуза
      .location                → город
      .tuition-fee             → стоимость обучения
      a.study-card__link       → ссылка на программу
    """
    field_ids = {
        "Computer Science": 23,
        "Medicine": 8,
        "Economics": 14,
        "Engineering": 5,
        "Law": 18,
        "Business": 3,
    }
    country_codes = {
        "Germany": 276,
        "Czech Republic": 203,
        "Hungary": 348,
        "Austria": 40,
        "Finland": 246,
        "Netherlands": 528,
    }

    fid = field_ids.get(field, 23)
    cid = country_codes.get(country)
    country_param = f"|c{cid}" if cid else ""
    url = f"https://www.mastersportal.eu/search/#q=f{fid}|p1{country_param}"

    logger.info(f"Открываем браузер: {url}")
    driver = get_driver()
    driver.get(url)
    time.sleep(3)  # ждём пока JS загрузит карточки

    soup = BeautifulSoup(driver.page_source, "lxml")
    driver.quit()

    results = []
    for card in soup.select(".study-card")[:20]:
        try:
            name = card.select_one(".university-block__name").text.strip()
            city = card.select_one(".location").text.strip()
            fee_text = card.select_one(".tuition-fee").text.strip()
            link = card.select_one("a.study-card__link")["href"]
            tuition = _parse_fee(fee_text)

            results.append(RawUniversity(
                name=name,
                country=country,
                city=city,
                fields=[field],
                ielts_min=6.0,
                toefl_min=80,
                gpa_min=3.0,
                tuition_usd=tuition,
                scholarship=False,
                url=f"https://www.mastersportal.eu{link}",
            ))
        except Exception as e:
            logger.debug(f"Пропуск карточки: {e}")
            continue

    logger.info(f"Найдено {len(results)} программ")
    return results


#парсер QS Rankings (статический JSON API) ─────────────────────────────────

def parse_qs_rankings(subject: str = "computer-science-information-systems") -> list[dict]:
    """
    topuniversities.com отдаёт данные через JSON API.
    Статический запрос, Selenium не нужен — хватает requests.

    Что извлекаем:
      institution.name  → название вуза
      location.name     → страна
      rank              → место в рейтинге
    """
    url = f"https://www.topuniversities.com/sites/default/files/qs-rankings-data/en/subjects/{subject}.json"
    logger.info(f"Запрос к QS API: {url}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.json().get("data", [])
    except Exception as e:
        logger.warning(f"QS API недоступен: {e}")
        return []


#утилиты 

def _parse_fee(text: str) -> int:
    if not text or "free" in text.lower():
        return 0
    digits = "".join(c for c in text if c.isdigit())
    return int(digits) * 1 if digits else 0


def merge_with_existing(new_items: list[RawUniversity]) -> None:
    if DATA_FILE.exists():
        with open(DATA_FILE, encoding="utf-8") as f:
            existing = json.load(f)
    else:
        existing = []

    existing_names = {u["name"] for u in existing}
    added = 0

    for uni in new_items:
        if uni.name not in existing_names:
            existing.append(asdict(uni))
            existing_names.add(uni.name)
            added += 1

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    logger.info(f"Добавлено {added} новых вузов. Всего в базе: {len(existing)}")


#точка входа

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--field", default="Computer Science")
    parser.add_argument("--country", default="Germany")
    args = parser.parse_args()

    unis = parse_mastersportal(args.field, args.country)
    merge_with_existing(unis)

if __name__ == "__main__":
    main()
