#!/usr/bin/env bash
# Kagit (paper) bot SIFIRLAMA — 26.11 sahip karari: 14 enstruman, 1h/4h/1d, 55 kurulum, ML1 sifirdan.
# GERI ALINAMAZ. Arsiv YOK (sahip karari). Canli/testnet (var-live, var-testnet, shared/live, shared/testnet) ve
# Telegram offset'i (eski komutlar tekrar islenmesin) KORUNUR.
# Kullanim (root):  sudo bash /home/trader/SG-Github-AB-proje/trader/deploy/sifirla_14.sh
# Onay icin "SIFIRLA" yazilmasi istenir. --evet ile sorusuz calisir.
set -euo pipefail

T="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
U="trader"
TG_GROUP="trader-tg"
KALAN=(AAPL MSFT NVDA GOOGL AMZN META TSLA BTC ETH SOL XRP TRX XAU BZ)

[ "$(id -u)" -eq 0 ] || { echo "root ile calistirin (sudo)"; exit 1; }
[ -f "$T/config/engine.paper.json" ] || { echo "TRADER_DIR bulunamadi: $T"; exit 1; }
python3 - "$T/config/engine.paper.json" <<'PY' || { echo "Yeni ayar kurulu degil (14 cift / 162 kol bekleniyor). Once kurulumu bekleyin."; exit 1; }
import json, sys
c = json.load(open(sys.argv[1]))
assert len(c["pairs"]) == 14 and len(c["arms"]) == 162 and not any(a.endswith("@15m") for a in c["arms"])
PY

echo "Silinecekler ($T):"
echo "  var/learner/*            (paper defteri, pozisyonlar, risk merdiveni, ML1 ogrenme ve paket, sayaclar)"
echo "  var/durum/*, var/rapor/* (pano/rapor dosyalari)"
echo "  var/telegram/* (offset.json HARIC), outbox icerigi"
echo "  var/universe, var/veri, var/market.sqlite*, var/feed-status.json, var/gap_report.json"
echo "  var/history: 14 enstruman disindakiler; var/vision_raw tamamen"
echo "  /var/lib/trader-health/state.json, /var/backups/trader/*"
if [ "${1:-}" != "--evet" ]; then
  read -r -p 'Onay icin SIFIRLA yazin: ' ok
  [ "$ok" = "SIFIRLA" ] || { echo "Iptal."; exit 1; }
fi

echo "== Calisan trader birimleri durduruluyor (canli/testnet haric)"
mapfile -t AKTIF < <(systemctl list-units --type=service,timer --state=active --no-legend --plain 'trader*' \
  | awk '{print $1}' | grep -v -E 'trader-engine-live|trader-engine-testnet|env-retry' || true)
printf '%s\n' "${AKTIF[@]}" > /root/sifirla_14_birimler.txt
# once zamanlayicilar (oto-guncelle, kurulum-gozcu dahil), sonra servisler
for u in "${AKTIF[@]}"; do [[ "$u" == *.timer ]] && systemctl stop "$u" || true; done
for u in "${AKTIF[@]}"; do [[ "$u" == *.service ]] && systemctl stop "$u" || true; done

echo "== Siliniyor"
find "$T/var/learner" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
rm -rf "$T/var/durum"/* "$T/var/rapor"/* 2>/dev/null || true
find "$T/var/telegram" -mindepth 1 -maxdepth 1 ! -name offset.json ! -name outbox -exec rm -rf {} +
find "$T/var/telegram/outbox" -mindepth 1 -exec rm -rf {} + 2>/dev/null || true
rm -rf "$T/var/universe" "$T/var/veri" "$T/var/vision_raw"
rm -f "$T/var/market.sqlite" "$T/var/market.sqlite-wal" "$T/var/market.sqlite-shm" "$T/var/feed-status.json" \
      "$T/var/feed.lock" "$T/var/gap_report.json"
if [ -d "$T/var/history" ]; then
  for f in "$T/var/history"/*; do
    [ -e "$f" ] || continue
    b="$(basename "$f")"; b="${b%%_USDT*}"; keep=0
    for k in "${KALAN[@]}"; do [ "$b" = "$k" ] && keep=1; done
    [ "$keep" -eq 1 ] || rm -rf "$f"
  done
fi
rm -f /var/lib/trader-health/state.json
rm -rf /var/backups/trader/* 2>/dev/null || true

echo "== Dizinler yeniden"
install -d -m 0750 -o "$U" -g "$U" "$T/var/learner" "$T/var/learner/models" "$T/var/durum" "$T/var/rapor"
install -d -m 2770 -o "$U" -g "$TG_GROUP" "$T/var/telegram/outbox" "$T/var/telegram/outbox/sent"

[ -e "$T/shared/KILL" ] && echo "UYARI: $T/shared/KILL var (silinmedi; bilerek mi?)"
[ -e "$T/shared/PAUSE.learner" ] && echo "UYARI: $T/shared/PAUSE.learner var (silinmedi)"

echo "== Birimler yeniden baslatiliyor (once feed)"
systemctl start trader-feed.service || true
for u in "${AKTIF[@]}"; do [[ "$u" == *.service ]] && systemctl start "$u" || true; done
for u in "${AKTIF[@]}"; do [[ "$u" == *.timer ]] && systemctl start "$u" || true; done
echo "Tamam. Motor, feed 14 enstrumanin mumlarini indirince girislere baslar (birkac dakika)."
echo "Kontrol: systemctl status trader-engine@learner --no-pager | head -5"
