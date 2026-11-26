#!/usr/bin/env bash
# Kagit (paper) bot SIFIRLAMA — 26.11 sahip karari: 14 enstruman, 1h/4h/1d, 55 kurulum, ML1 sifirdan.
# GERI ALINAMAZ. Arsiv YOK (sahip karari). Canli/testnet dizinleri (var-live, var-testnet, shared/live, shared/testnet), canli/testnet
# yedekleri (*live*, *testnet*) ve Telegram offset'i (eski komutlar tekrar islenmesin) KORUNUR.
# var/market.sqlite ORTAKTIR ve silinir; canli/testnet motoru aktifse betik CALISMAZ (once onu durdurun).
# Kullanim (root):  sudo bash /home/trader/SG-Github-AB-proje/trader/deploy/sifirla_14.sh
# Onay icin "SIFIRLA" yazilmasi istenir. --evet ile sorusuz calisir.
set -euo pipefail

T="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
U="trader"
TG_GROUP="trader-tg"
KAYIT="${SIFIRLA_KAYIT:-/root/sifirla_14_birimler.txt}"
SAGLIK="${SIFIRLA_SAGLIK:-/var/lib/trader-health/state.json}"
YEDEK="${SIFIRLA_YEDEK:-/var/backups/trader}"
KALAN=(AAPL MSFT NVDA GOOGL AMZN META TSLA BTC ETH SOL XRP TRX XAU BZ)

[ "$(id -u)" -eq 0 ] || { echo "root ile calistirin (sudo)"; exit 1; }
[ -f "$T/config/engine.paper.json" ] || { echo "TRADER_DIR bulunamadi: $T"; exit 1; }
python3 - "$T/config/engine.paper.json" <<'PY' || { echo "Yeni ayar kurulu degil (14 cift / 162 kol bekleniyor). Once kurulumu bekleyin."; exit 1; }
import json, sys
c = json.load(open(sys.argv[1]))
assert len(c["pairs"]) == 14 and len(c["arms"]) == 162 and not any(a.endswith("@15m") for a in c["arms"])
PY

# P7-01: canli/testnet motoru aktifse reddet (ortak var/market.sqlite silinecek)
CANLI="$(systemctl list-units --all --no-legend --plain 'trader-engine-live*' 'trader-engine-testnet*' \
  | awk '$3 != "inactive" && $3 != "failed" {print $1}' | head -n1 || true)"
if [ -n "$CANLI" ]; then
  echo "Canli/testnet motoru calisiyor ($CANLI): bu betik var/market.sqlite'i siler. Once onu durdurun."
  exit 1
fi

echo "Silinecekler ($T):"
echo "  var/learner/*            (paper defteri, pozisyonlar, risk merdiveni, ML1 ogrenme ve paket, sayaclar)"
echo "  var/durum/*, var/rapor/* (pano/rapor dosyalari)"
echo "  var/telegram/* (offset.json HARIC; audit.jsonl DAHIL), outbox icerigi"
echo "  var/universe, var/veri, var/market.sqlite*, var/feed-status.json, var/gap_report.json"
echo "  var/history: rules.json ve 14 enstruman disindaki her sey; var/vision_raw tamamen"
echo "  saglik durumu ($SAGLIK), kagit yedekleri ($YEDEK; *live*/*testnet* ve MANIFEST.json HARIC)"
if [ "${1:-}" != "--evet" ]; then
  read -r -p 'Onay icin SIFIRLA yazin: ' ok
  [ "$ok" = "SIFIRLA" ] || { echo "Iptal."; exit 1; }
fi

echo "== Calisan trader birimleri durduruluyor (canli/testnet haric)"
mapfile -t AKTIF < <(systemctl list-units --type=service,timer --all --no-legend --plain 'trader*' \
  | awk '$3 ~ /^(active|activating|reloading|deactivating)$/ || $4 == "auto-restart" {print $1}' \
  | grep -v -E 'trader-engine-live|trader-engine-testnet|env-retry' || true)
printf '%s\n' "${AKTIF[@]}" > "$KAYIT"
BITTI=0; SILME=0
cikis() {
  [ "$BITTI" -eq 1 ] && return 0
  if [ "$SILME" -eq 0 ]; then
    for u in "${AKTIF[@]}"; do systemctl start "$u" 2>/dev/null || true; done
    echo "Iptal: hicbir sey silinmedi, birimler geri baslatildi."
  else
    echo "YARIDA KALDI: birimler DURUYOR. Liste: $KAYIT. Betigi yeniden calistirin."
  fi
}
trap cikis EXIT
# once zamanlayicilar (oto-guncelle, kurulum-gozcu dahil), sonra servisler; durdurma hatasi = silmeden cik
for u in "${AKTIF[@]}"; do if [[ "$u" == *.timer ]]; then systemctl stop "$u"; fi; done
for u in "${AKTIF[@]}"; do if [[ "$u" == *.service ]]; then systemctl stop "$u"; fi; done
for u in "${AKTIF[@]}"; do
  st="$(systemctl is-active "$u" 2>/dev/null || true)"
  if [ "$st" != "inactive" ] && [ "$st" != "failed" ]; then
    echo "DURMADI: $u ($st). Hicbir sey silinmedi."
    exit 1
  fi
done

echo "== Siliniyor"
SILME=1
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
rm -f "$SAGLIK"
# yedekler gun dizinleri altinda (YYYY-MM-DD/ledger_<bot>[@live].sqlite, MANIFEST.json): yalniz kagit dosyalari silinir
if [ -d "$YEDEK" ]; then
  find "$YEDEK" -mindepth 1 -type f ! -name '*live*' ! -name '*testnet*' ! -name 'MANIFEST.json' -delete
  find "$YEDEK" -mindepth 1 -type d -empty -delete
fi

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
BITTI=1
