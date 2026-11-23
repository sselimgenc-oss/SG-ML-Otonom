#!/usr/bin/env bash
# Canli durum yayini (CT'nin canli-durum duzeninden uyarlandi; kullanicinin kendi kodu): sunucu saatlik olarak ozet verisini
# repo icindeki AYRI bir dala (canli-durum, klasor ml/) yazar; orkestrator ve gelistirici Telegram iletimine gerek kalmadan okur.
# Icerik IZIN LISTESIYLE sinirli: rejim etiketi, gunluk ozet, mutabakat (acik/kapanan islemler, kasa), strateji verisi, tutarlilik,
# etiket kurallari, motor durum dosyasi (acik pozisyonlar, kasa), pano anlik goruntusu (ogrenme kartlari), model paketi listesi
# (yalniz ad/boyut/zaman) ve gece egitimi ozetinin son satirlari. Anahtar, ortam dosyasi,
# defter (sqlite) ya da kisisel veri YAYIMLANMAZ.
# Kimlik: yalniz sunucudaki SSH deploy anahtari ($HOME/.ssh/id_ed25519; repoda ve ortam dosyalarinda sir YOK). Anahtar yoksa
# sessizce atlanir (cikis 0): kullanici kurulum adimlarini yapana kadar uyari uretmez. Yalniz canli-durum dalina yazar.
# Istege bagli: TRADER_DIR, TRADER_PY, DURUM_REPO (varsayilan GitHub SSH adresi), DURUM_DALI (yalniz canli-durum),
# DURUM_ANAHTAR (anahtar yolu), DURUM_YEREL=1 (test: anahtarsiz yerel depo).
set -euo pipefail
dal="${DURUM_DALI:-canli-durum}"
case "$dal" in canli-durum) ;; *) echo "HATA: yalniz canli-durum dalina yazilir (verilen: $dal)" >&2; exit 1 ;; esac
betik_dizin="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
trader_dir="${TRADER_DIR:-$(cd "$betik_dizin/.." && pwd)}"
py="${TRADER_PY:-$trader_dir/.venv/bin/python}"
repo="${DURUM_REPO:-git@github.com:sselimgenc-oss/SG-ML-Otonom.git}"
anahtar="${DURUM_ANAHTAR:-${HOME:-/nonexistent}/.ssh/id_ed25519}"
if [ "${DURUM_YEREL:-0}" != "1" ]; then
  if [ ! -s "$anahtar" ]; then
    echo "durum-yayin: deploy anahtari yok ($anahtar); atlandi (kurulum: docs/sunucu-kurulum.md 'Canli durum dali')"
    exit 0
  fi
  anahtar_dizin="$(dirname "$anahtar")"
  GIT_SSH_COMMAND="ssh -i $anahtar -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$anahtar_dizin/known_hosts"
  export GIT_SSH_COMMAND
fi
gecici="$(mktemp -d)"
trap 'rm -rf "$gecici"' EXIT
cikti="$gecici/ml"
mkdir -p "$cikti"
cd "$trader_dir"
uyari() { echo "UYARI: $1 $(date -u +%FT%TZ); yayin devam ediyor" >&2; }
# 1) Uretilen dosyalar (pano yayiniyla ayni komutlar). Biri basarisizsa yalniz uyari; o dosya bu turda olmaz.
PYTHONPATH="$trader_dir/src" "$py" -m trader_core.rejim_yayini --config-dir "$trader_dir/config" --env paper --out "$cikti/rejim.json" >/dev/null || uyari "rejim.json uretilemedi"
PYTHONPATH="$trader_dir/src" "$py" -m trader_core.gunluk_ozet --config-dir "$trader_dir/config" --env paper --out "$cikti/gunluk_ozet_v1.json" >/dev/null || uyari "gunluk_ozet_v1.json uretilemedi"
PYTHONPATH="$trader_dir/src" "$py" -m trader_panel --config "$trader_dir/config/panel.json" snapshot --out "$cikti/pano.html" >/dev/null || uyari "pano.html uretilemedi"
# 2) Hazir dosyalar (izin listesi; baska hicbir sey kopyalanmaz)
for f in mutabakat_v1.json mutabakat.md strateji-veri-ml.md tutarlilik_v1.json c1_goc_raporu.json tur1_olcum_v1.json tur1_olcum.md; do
  if [ -s "$trader_dir/var/durum/$f" ]; then cp "$trader_dir/var/durum/$f" "$cikti/$f"; fi
done
# YZ yorumcu: en son gunluk rapor (yalniz kendi dizininden; yorumcu_son.md). Yalniz metin; anahtar/sir kalibi son kapida taranir
yorumcu_son="$(ls -1 "$trader_dir"/var/durum/yorumcu/????-??-??.md 2>/dev/null | sort | tail -n 1 || true)"
if [ -n "$yorumcu_son" ] && [ -s "$yorumcu_son" ]; then cp "$yorumcu_son" "$cikti/yorumcu_son.md"; fi
if [ -s "$trader_dir/var/learner/status.json" ]; then cp "$trader_dir/var/learner/status.json" "$cikti/durum.json"; fi
# Model paketleri (yalniz ad/boyut/zaman; icerik yok) ve gece egitimi ozet satirlari: M1/filtre paketi var mi, ne zaman uretildi
if [ -d "$trader_dir/var/learner/models" ]; then
  TZ=UTC find "$trader_dir/var/learner/models" -type f -name '*.json' -printf '%TY-%Tm-%Td %TH:%TM UTC  %8s  %P\n' 2>/dev/null | sort > "$cikti/model_paketleri.txt" || true
fi
if [ -s "$trader_dir/var/learner/paper_models.csv" ]; then tail -n 40 "$trader_dir/var/learner/paper_models.csv" > "$cikti/paper_models_son.csv"; fi
# Bos dosyalari at; hicbir sey yoksa yayimlanacak bir sey yok
find "$cikti" -type f -size 0 -delete
[ -n "$(ls -A "$cikti")" ] || { echo "durum-yayin: yayimlanacak dosya yok"; exit 0; }
# Anahtar/sir sizintisina karsi son kapı: bilinen sir kaliplari gorulurse YAYIMLAMA
if grep -rIlE '(TELEGRAM_BOT_TOKEN|CLOUDFLARE_API_TOKEN|ANTHROPIC_API_KEY|BEGIN [A-Z ]*PRIVATE KEY|[0-9]{8,10}:AA[0-9A-Za-z_-]{30,})' "$cikti" >/dev/null 2>&1; then
  echo "HATA: yayim dosyalarinda sir kalibi goruldu; yayimlanmadi" >&2
  exit 1
fi
date -u +%FT%TZ > "$cikti/uretim.txt"
# 3) Git: gecici depo, yalniz canli-durum dalinin ucu (sig klon); ilk kez ise yetim dal
depo="$gecici/depo"
git init -q "$depo"
git -C "$depo" config user.name 'trader-sunucu'
git -C "$depo" config user.email 'trader-sunucu@users.noreply.github.com'
git -C "$depo" remote add origin "$repo"
if git -C "$depo" ls-remote --exit-code --heads origin "$dal" >/dev/null; then
  git -C "$depo" fetch -q --depth 1 origin "$dal"
  git -C "$depo" checkout -q -B "$dal" FETCH_HEAD
else
  durum=$?
  if [ "$durum" -ne 2 ]; then echo "HATA: uzak depoya ulasilamadi (ls-remote $durum)" >&2; exit "$durum"; fi
  git -C "$depo" checkout -q --orphan "$dal"
fi
rm -rf "$depo/ml"
cp -r "$cikti" "$depo/ml"
git -C "$depo" add -A ml
if git -C "$depo" diff --cached --quiet; then echo "durum-yayin: degisiklik yok"; exit 0; fi
git -C "$depo" commit -q -m "ml: durum $(cat "$cikti/uretim.txt")"
for deneme in 1 2 3; do
  if git -C "$depo" push -q origin "HEAD:refs/heads/$dal"; then echo "durum-yayin: yayimlandi $(cat "$cikti/uretim.txt")"; exit 0; fi
  [ "$deneme" -lt 3 ] || break
  sleep $((deneme * 5))
  git -C "$depo" fetch -q --depth 1 origin "$dal" && git -C "$depo" rebase -q FETCH_HEAD || true
done
echo "HATA: canli-durum dalina gonderilemedi $(date -u +%FT%TZ)" >&2
exit 1
