"""
main.py: třetí projekt do Engeto Online Python Akademie

author: Roman Janotík
email: janotik.roman@yahoo.com
"""

import sys
import csv
import re
from io import StringIO
from typing import Dict, List, Tuple
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
import pandas as pd

BASE = "https://www.volby.cz/pls/ps2017nss/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ElectionsScraper/1.0)"}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def validate_args(argv: List[str]) -> Tuple[str, str]:
    if len(argv) != 3:
        die(
            "Program vyžaduje 2 argumenty:\n"
            " 1) URL okresu (stránka s obcami – obsahuje 'ps32')\n"
            " 2) názov výstupného .csv súboru\n"
            "Príklad:\n"
            " python main.py "
            "\"https://www.volby.cz/pls/ps2017nss/ps32?xjazyk=CZ&xkraj=12&xnumnuts=7103\" "
            "vysledky_prostejov.csv"
        )
    url, out_csv = argv[1], argv[2]

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or "volby.cz" not in parsed.netloc:
        die("Zadaný odkaz nevyzerá ako stránka volby.cz.")

    if "ps32" not in parsed.path:
        die("URL musí smerovať na stránku okresu s obcami (obsahuje 'ps32').")

    q = parse_qs(parsed.query)
    if "xjazyk" not in q or "xnumnuts" not in q:
        print("Upozornenie: URL vyzerá netypicky (očakávam parametre xjazyk a xnumnuts).", file=sys.stderr)

    if not out_csv.lower().endswith(".csv"):
        die("Druhý argument musí byť názov výstupného súboru s príponou .csv.")

    return url, out_csv


def get_html(url: str) -> str:
    r = SESSION.get(url, timeout=30)
    r.raise_for_status()
    if r.apparent_encoding:
        r.encoding = r.apparent_encoding
    return r.text


def _norm(s: str) -> str:
    import unicodedata
    s = str(s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", "", s)
    return s.lower()


def _to_int(x) -> int:
    s = str(x)
    m = re.findall(r"\d+", s.replace("\xa0", " ").replace(" ", ""))
    return int("".join(m)) if m else 0


def parse_municipalities(index_url: str) -> List[Tuple[str, str, str]]:
    html = get_html(index_url)
    soup = BeautifulSoup(html, "lxml")
    rows: List[Tuple[str, str, str]] = []

    for tr in soup.select("tr"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        code, name, href = None, None, None
        code_a = tds[0].find("a")
        name_a = tds[1].find("a")
        if code_a and code_a.has_attr("href") and "ps311" in code_a["href"]:
            href = urljoin(BASE, code_a["href"]); code = code_a.get_text(strip=True)
        if name_a and name_a.has_attr("href") and "ps311" in name_a["href"]:
            href = urljoin(BASE, name_a["href"]); name = name_a.get_text(strip=True)
        if code is None:
            code_txt = tds[0].get_text(strip=True)
            if code_txt.isdigit(): code = code_txt
        if name is None:
            name = tds[1].get_text(strip=True)
        if href and code and name:
            rows.append((code, name, href))

    if not rows:
        seen = set()
        for a in soup.select("td a[href*='ps311']"):
            href = urljoin(BASE, a["href"])
            tr = a.find_parent("tr"); 
            if not tr: continue
            tds = tr.find_all("td")
            if len(tds) >= 2:
                code = tds[0].get_text(strip=True)
                name = tds[1].get_text(strip=True)
                key = (code, name, href)
                if code and name and key not in seen:
                    rows.append((code, name, href)); seen.add(key)

    if not rows:
        die("Na stránke okresu sa nepodarilo nájsť zoznam obcí (odkazy na 'ps311').")
    return rows


def extract_summary_and_parties(detail_url: str) -> Tuple[int, int, int, Dict[str, int]]:
    html = get_html(detail_url)
    tables = pd.read_html(StringIO(html), flavor="lxml")

    registered = envelopes = valid = None
    party_votes: Dict[str, int] = {}

    targets = {"volicivseznamu", "vydaneobalky", "platnehlasy"}

    for df in tables:
        df = df.copy()
        df.columns = [" ".join(map(str, c)) if isinstance(c, tuple) else str(c) for c in df.columns]
        cols_norm = {_norm(c) for c in df.columns}
        if targets.issubset(cols_norm) and len(df) >= 1:
            row0 = df.iloc[0]
            def pick(colkey: str) -> str:
                for c in df.columns:
                    if _norm(c) == colkey: return c
                raise KeyError(colkey)
            registered = _to_int(row0[pick("volicivseznamu")])
            envelopes = _to_int(row0[pick("vydaneobalky")])
            valid = _to_int(row0[pick("platnehlasy")])
            break

    if registered is None or envelopes is None or valid is None:
        die("Nepodarilo sa vyčítať sumarizačné hodnoty (Voliči/Obálky/Platné).")

    for df in tables:
        df = df.copy()
        df.columns = [" ".join(map(str, c)) if isinstance(c, tuple) else str(c) for c in df.columns]
        name_col = None; votes_col = None
        for c in df.columns:
            n = _norm(c)
            if "nazevstrany" in n or n == "strana": name_col = c
            if _norm(c) == "hlasy": votes_col = c
        if not name_col or not votes_col: continue
        for _, row in df.iterrows():
            party = str(row[name_col]).strip()
            if not party or party.lower() == "nan": continue
            votes = _to_int(row[votes_col])
            party_votes[party] = party_votes.get(party, 0) + votes

    if not party_votes:
        die("Nepodarilo sa nájsť tabuľky s hlasmi pre strany.")
    return int(registered), int(envelopes), int(valid), {k: int(v) for k, v in party_votes.items()}


def scrape(index_url: str) -> List[Dict[str, int]]:
    municipalities = parse_municipalities(index_url)
    results: List[Dict[str, int]] = []; party_order: List[str] = []
    print(f"Nájdených obcí: {len(municipalities)}")
    for code, name, detail in municipalities:
        try:
            registered, envelopes, valid, votes = extract_summary_and_parties(detail)
        except Exception as e:
            print(f"VAROVANIE: Preskakujem obec {name} ({code}) – {e}", file=sys.stderr)
            continue
        for p in votes.keys():
            if p not in party_order: party_order.append(p)
        row: Dict[str, int] = {
            "code": code, "location": name, "registered": registered,
            "envelopes": envelopes, "valid": valid,
        }
        row.update(votes); results.append(row)

    def sort_key(r: Dict[str, int]) -> int:
        num = re.sub(r"\D", "", str(r.get("code", ""))); return int(num) if num else 0
    results.sort(key=sort_key)
    if results: results[0]["__party_order__"] = party_order
    return results


def write_csv(rows: List[Dict[str, int]], out_csv: str) -> None:
    if not rows: die("Nie je čo zapisovať – žiadne dáta.")
    party_order = rows[0].get("__party_order__", [])
    if "__party_order__" in rows[0]: del rows[0]["__party_order__"]
    header = ["code","location","registered","envelopes","valid"] + list(party_order)
    for r in rows:
        for p in party_order: r.setdefault(p, 0)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header); writer.writeheader()
        for r in rows:
            writer.writerow({k: (r.get(k, 0) if k not in {"code","location"} else r.get(k, "")) for k in header})
    print(f"Hotovo. Výstup uložený do: {out_csv}")


def main() -> None:
    index_url, out_csv = validate_args(sys.argv)
    print(f"STAHUJI DATA Z VYBRANEHO URL: {index_url}")
    rows = scrape(index_url)
    print(f"UKLADAM DO SOUBORU: {out_csv}")
    write_csv(rows, out_csv)
    print("UKONCUJI election-scraper")


if __name__ == "__main__":
    main()
