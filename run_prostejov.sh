
#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
URL='https://www.volby.cz/pls/ps2017nss/ps32?xjazyk=CZ&xkraj=12&xnumnuts=7103'
OUT="$DIR/vysledky_prostejov.csv"
python3 "$DIR/main.py" "$URL" "$OUT"
