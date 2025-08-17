
"""
main.py: třetí projekt do Engeto Online Python Akademie

author: Roman Janotík
email: janotik.roman@yahoo.com
"""

import argparse
import csv
import re
import sys
import time
from typing import Dict, List, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://www.volby.cz/pls/ps2017nss/"


# ----------------------------
# Helpers
# ----------------------------
def die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def parse_int(text: str) -> int:
    """Convert strings like '1 234' or '1\xa0234' to int safely."""
    if text is None:
        return 0
    cleaned = re.sub(r"[^0-9-]", "", text.replace("\xa0", ""))  # strip spaces & NBSP & non-digits
    return int(cleaned) if cleaned else 0


def is_valid_list_url(url: str) -> bool:
    """Basic validation: must be a ps32 list page under volby.cz for PS2017."""
    try:
        u = urlparse(url)
    except Exception:
        return False
    if u.netloc not in {"www.volby.cz", "volby.cz"}:
        return False
    # Accept paths like /pls/ps2017nss/ps32?... (Czech list of municipalities)
    return "/pls/ps2017nss/ps32" in u.path and "xjazyk=CZ" in (u.query or "")


# ----------------------------
# Scraping functions
# ----------------------------
def get_soup(session: requests.Session, url: str) -> BeautifulSoup:
    r = session.get(url, timeout=30)
    r.raise_for_status()
    # The site is CP1250/Windows-1250; requests usually decodes correctly. Force fallback if needed.
    if r.encoding is None:
        r.encoding = "cp1250"
    return BeautifulSoup(r.text, "html.parser")


def extract_municipality_links(soup: BeautifulSoup, base_url: str) -> List[Tuple[str, str, str]]:
    """Return list of tuples (code, name, detail_url) for all municipalities on the list page."""
    rows = []
    # Heuristic: rows where first <td> looks like 6-digit code
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        code_txt = tds[0].get_text(strip=True)
        if not re.fullmatch(r"\d{6}", code_txt):
            continue
        name_txt = tds[1].get_text(strip=True)
        # Find a link to the municipality detail (ps311) somewhere in the row
        detail_href = None
        for a in tr.find_all("a"):
            href = a.get("href", "")
            if "ps311" in href:  # municipality detail page
                detail_href = href
                break
        if not detail_href:
            # Fallback: sometimes the code cell contains the link
            a = tds[0].find("a")
            if a and a.get("href"):
                detail_href = a["href"]
        if not detail_href:
            # As a last resort, try the last cell (column with 'X')
            a = tds[-1].find("a")
            if a and a.get("href"):
                detail_href = a["href"]
        if not detail_href:
            # Skip if no link found (should not happen on the official list page)
            continue
        detail_url = urljoin(base_url, detail_href)
        rows.append((code_txt, name_txt, detail_url))
    if not rows:
        die("Nepodařilo se najít žádné obce na dané stránce. Zkontroluj odkaz – musí to být ps32 stránka s výpisem obcí.")
    return rows


def extract_value_by_label(soup: BeautifulSoup, label: str) -> int:
    """Find numbers like 'Voliči v seznamu', 'Vydané obálky', 'Platné hlasy'."""
    # exact match ignoring surrounding whitespace
    lab = soup.find("td", string=re.compile(rf"^\s*{re.escape(label)}\s*$"))
    if not lab:
        return 0
    tr = lab.find_parent("tr")
    if not tr:
        return 0
    # number is typically the last <td class='cislo'> in the same row
    candidates = [td for td in tr.find_all("td") if "cislo" in (td.get("class") or [])]
    if not candidates:
        # fallback: any numeric-looking td in the row
        candidates = [td for td in tr.find_all("td") if re.search(r"\d", td.get_text())]
    return parse_int(candidates[-1].get_text()) if candidates else 0


def extract_party_votes(soup: BeautifulSoup) -> Dict[str, int]:
    """Collect all (party -> votes) from one municipality page.

    The PS2017 site shows parties in 2 tables. We find every row that has a party name
    in <td class='overflow_name'> and then take the first numeric cell in that row as votes.
    """
    votes: Dict[str, int] = {}
    for tr in soup.find_all("tr"):
        name_cell = tr.find("td", {"class": "overflow_name"})
        if not name_cell:
            continue
        party = name_cell.get_text(strip=True)
        # Find the first numeric cell in the same row
        num = 0
        for td in tr.find_all("td"):
            if td is name_cell:
                continue
            txt = td.get_text(strip=True)
            if re.search(r"\d", txt):
                num = parse_int(txt)
                # Some rows have both votes and percent. We assume the first numeric is votes.
                break
        if party:
            votes[party] = num
    return votes


def scrape_municipality(session: requests.Session, code: str, name: str, url: str) -> Tuple[Dict[str, int], Dict[str, int]]:
    soup = get_soup(session, url)
    registered = extract_value_by_label(soup, "Voliči v seznamu")
    envelopes = extract_value_by_label(soup, "Vydané obálky")
    valid = extract_value_by_label(soup, "Platné hlasy")
    parties = extract_party_votes(soup)
    meta = {
        "code": code,
        "location": name,
        "registered": registered,
        "envelopes": envelopes,
        "valid": valid,
    }
    return meta, parties


def write_csv(path: str, rows_meta: List[Dict[str, int]], rows_parties: List[Dict[str, int]]) -> None:
    # Compute the union of all party names
    party_names: List[str] = sorted({p for row in rows_parties for p in row.keys()})
    header = ["code", "location", "registered", "envelopes", "valid"] + party_names
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for meta, parties in zip(rows_meta, rows_parties):
            line = [
                meta["code"],
                meta["location"],
                meta["registered"],
                meta["envelopes"],
                meta["valid"],
            ] + [parties.get(p, 0) for p in party_names]
            writer.writerow(line)


# ----------------------------
# Main
# ----------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stáhne výsledky voleb 2017 pro zadaný územní celek (ps32 stránka) a uloží je do CSV."
    )
    parser.add_argument("url", help="Odkaz na územní celek – stránka typu ps32... (např. https://www.volby.cz/pls/ps2017nss/ps32?xjazyk=CZ&xkraj=12&xnumnuts=7103)")
    parser.add_argument("output_csv", help="Cesta/jméno výstupního CSV souboru (např. vysledky_prostejov.csv)")
    args = parser.parse_args()

    if not is_valid_list_url(args.url):
        die("Zadej platný odkaz na stránku ps32 s výpisem obcí (jazyk CZ).")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Engeto Elections Scraper (https://www.volby.cz/)"
    })

    print("Načítám seznam obcí...", file=sys.stderr)
    list_soup = get_soup(session, args.url)
    municipalities = extract_municipality_links(list_soup, BASE)
    print(f"Nalezeno obcí: {len(municipalities)}", file=sys.stderr)

    metas: List[Dict[str, int]] = []
    parties_list: List[Dict[str, int]] = []

    for i, (code, name, detail_url) in enumerate(municipalities, start=1):
        print(f"[{i}/{len(municipalities)}] {code} – {name}", file=sys.stderr)
        try:
            meta, parties = scrape_municipality(session, code, name, detail_url)
        except Exception as e:
            print(f"  -> Chyba při zpracování {name}: {e}", file=sys.stderr)
            # Přesto pokračuj dál; doplň 0 a pokračuj
            meta = {"code": code, "location": name, "registered": 0, "envelopes": 0, "valid": 0}
            parties = {}
        metas.append(meta)
        parties_list.append(parties)
        time.sleep(0.2)  # šetrný scraping

    write_csv(args.output_csv, metas, parties_list)
    print(f"Hotovo! Výsledky uloženy do: {args.output_csv}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as e:
        die(f"Síťová chyba: {e}")
    except KeyboardInterrupt:
        die("Přerušeno uživatelem.", code=130)
