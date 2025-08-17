
# Elections Scraper – PS 2017 (Engeto Project 3)

Skript stáhne výsledky voleb do Poslanecké sněmovny 2017 pro zvolený **územní celek**
(stránka typu `ps32` s výpisem obcí) a uloží je do CSV ve formátu:

```csv
code,location,registered,envelopes,valid,<politická strana 1>,<politická strana 2>,...
```

Každý řádek = jedna obec. Každý sloupec = počet hlasů pro stranu v dané obci.

---

## Požadavky

- Python 3.10+
- Knihovny: `requests`, `beautifulsoup4`

## Instalace (doporučeno ve virtuálním prostředí)

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> **Pozn.:** Soubor `requirements.txt` obsahuje pouze *relevantní* knihovny. Pokud chcete soubor
> vygenerovat přímo ze svého prostředí: `pip freeze > requirements.txt`.

## Spuštění

Skript vyžaduje **2 argumenty**:

1. `URL` na stránku typu `ps32` (výpis obcí pro daný územní celek, jazyk CZ).
2. `OUTPUT_CSV` – jak se má jmenovat výstupní CSV soubor.

```bash
python main.py "https://www.volby.cz/pls/ps2017nss/ps32?xjazyk=CZ&xkraj=12&xnumnuts=7103" vysledky_prostejov.csv
```

Příklady dalších odkazů najdete na: https://www.volby.cz/pls/ps2017nss/ps3?xjazyk=CZ

## Co skript dělá

- Ověří, že odkaz směřuje na stránku `ps32`.
- Načte seznam obcí a pro každou obec otevře detail výsledků.
- Z každé obce vytáhne:
  - **Voliči v seznamu**, **Vydané obálky**, **Platné hlasy**,
  - počty hlasů pro **všechny kandidující strany** (dvě tabulky na stránce).
- Výstup uloží do CSV s hlavičkou ve tvaru:
  `code,location,registered,envelopes,valid,<strany...>`.

## Ukázka

![sample](Screenshot%202025-08-17%20at%2017.51.04.png)

## Tipy

- Scraping je omezen malou prodlevou (0.2 s) mezi požadavky, aby byl šetrný.
- CSV je ukládáno v kódování `utf-8-sig` – bez problémů se otevře v Excelu.
- Pokud se struktura webu změní, upravte prosím selektory v `extract_*` funkcích.

---

**Autor:** Roman Janotík – janotik.roman@yahoo.com
