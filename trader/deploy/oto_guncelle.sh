#!/usr/bin/env bash
# Trader sunucu otomatik guncelleme (root; trader-oto-guncelle.timer gunde iki SABIT pencerede calistirir:
# 10:30 ve 22:30 Turkiye saati = 07:30 ve 19:30 UTC; Turkiye'de yaz saati yok, UTC+3 sabit).
# Pencere disinda (elle ya da gecikmeli tetiklemede) kurulum YAPILMAZ. Acil kurulum: `trader-oto-simdi` (= bu betik --simdi)
# ya da OTO_ZORLA=1: pencere kontrolunu atlar; DURDUR dosyasi, canli koruma, yesil commit ve atalik kontrolu AYNEN gecerli.
# Kurulum sonrasi korumalar: install.sh kurulum.json yazar; saglik 15 dk yalniz olumcul uyari verir; trader-kurulum-gozcu 20 dk
# sonra oz-kontrol (yalniz sorunda mesaj) ve 60 dk boyunca izleme + esik asilirsa otomatik geri alma yapar (bkz. kurulum_gozcu.py).
# Belirtim: docs/motor/oto-guncelleme-spec.md. Yalniz GitHub'da tests.yml'i YESIL gecmis commit kurulur; mevcut surumun
# atasi olan (geri giden) commit kurulmaz; canli (trader-engine-live*) birim varsa hic dokunulmaz.
# Ortam degiskenleri YALNIZ testler icindir (uretimde varsayilanlar kullanilir):
#   OTO_STATE_DIR OTO_RELEASE_FILE OTO_ROOT_DIR OTO_GIT_DIR OTO_INSTALL OTO_API_URL OTO_TELEGRAM_ENV OTO_BRANCH OTO_INSTALL_TIMEOUT
#   OTO_SIMDI_DAKIKA OTO_SIMDI_SANIYE (UTC 'simdi' dakika/saniye) OTO_UYKU (sleep komutu): mum kapanisi beklemesi testi
#   OTO_SIMDI_SAAT (UTC saat; pencere testi) OTO_ZORLA (=1: pencere kontrolu atlanir; uretimde `--simdi` ile ayni)
#   OTO_GITHUB_TOKEN_FILE (varsayilan /etc/trader-github-token; repo gizliyse salt-okunur fine-grained token; yoksa/bossa anonim)
# Telegram ve GitHub token'i asla komut satirinda degildir: curl --config - ile stdin'den okunur.
set -uo pipefail

ZORLA="${OTO_ZORLA:-}"
for arg in "$@"; do
  case "$arg" in
    --simdi) ZORLA=1 ;;
    *) echo "bilinmeyen secenek: $arg (yalniz --simdi)" >&2; exit 2 ;;
  esac
done

STATE_DIR="${OTO_STATE_DIR:-/var/lib/trader-oto-guncelle}"
RELEASE_FILE="${OTO_RELEASE_FILE:-/etc/trader-release}"
ROOT_DIR="${OTO_ROOT_DIR:-/usr/local/lib/trader-root}"
GIT_DIR_ROOT="${OTO_GIT_DIR:-${ROOT_DIR}/repo.git}"
INSTALL_SH="${OTO_INSTALL:-${ROOT_DIR}/current/deploy/install.sh}"
TG_ENV="${OTO_TELEGRAM_ENV:-/etc/trader-telegram.env}"
GH_TOKEN_FILE="${OTO_GITHUB_TOKEN_FILE:-/etc/trader-github-token}"   # 23.11 repo gizli: token destegi
API_URL="${OTO_API_URL:-https://api.github.com/repos/sselimgenc-oss/SG-ML-Otonom/actions/workflows/tests.yml/runs}"
BRANCH="${OTO_BRANCH:-claude/charming-hawking-ab5w5q}"   # install.sh BRANCH ile ayni olmali
INSTALL_TIMEOUT="${OTO_INSTALL_TIMEOUT:-1800}"            # 30 dk
UYKU="${OTO_UYKU:-sleep}"
HIST="$STATE_DIR/gecmis.tsv"
ILOG="$STATE_DIR/son-kurulum.log"

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*"; }

mask() { # anahtar/parola kaliplari: gunluge ve Telegram'a giden her metinden gecer
  sed -E -e 's/bot[0-9]+:[A-Za-z0-9_-]+/bot<maskeli>/g' \
         -e 's/[0-9]{8,10}:[A-Za-z0-9_-]{30,}/<maskeli>/g' \
         -e 's/sk-ant-[A-Za-z0-9_-]+/sk-ant-<maskeli>/g'
}

env_deger() { # dosya ANAHTAR: ilk eslesen degeri verir (bosluk ve tirnak kirpilir); yoksa bos
  sed -n "s/^$2=//p" "$1" 2>/dev/null | head -n 1 | tr -d ' \t\r\n"\047'
}

release_commit() { sed -n 's/^COMMIT=//p' "$RELEASE_FILE" 2>/dev/null | head -n 1 | tr -d ' \t\r\n'; }

tg_send() { # metni Telegram'a yollar; hata olursa yalniz gunluge yazar (betigi dusurmez)
  local tok chat text
  [ -f "$TG_ENV" ] || { log "Telegram: $TG_ENV yok; yalniz gunluk"; return 0; }
  tok="$(env_deger "$TG_ENV" TELEGRAM_BOT_TOKEN)"
  chat="$(env_deger "$TG_ENV" TELEGRAM_CHAT_ID)"
  if [ -z "$tok" ] || [ -z "$chat" ]; then log "Telegram: anahtar bos; yalniz gunluk"; return 0; fi
  text="$(printf '%s' "$1" | mask)"
  printf 'url = "https://api.telegram.org/bot%s/sendMessage"\n' "$tok" \
    | curl -fsS --max-time 20 --config - --data-urlencode "chat_id=${chat}" --data-urlencode "text=${text}" -o /dev/null \
    || log "Telegram gonderilemedi"
  return 0
}

root_git() { # root'un kendi ciplak klonu (install.sh ile ayni anahtar/known_hosts); trader deposuna dokunmaz
  local key="$ROOT_DIR/ssh/deploy_key" kh="$ROOT_DIR/ssh/known_hosts"
  if [ -f "$key" ]; then
    GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND="ssh -i ${key} -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=${kh}" \
      git -C "$GIT_DIR_ROOT" "$@"
  else
    GIT_TERMINAL_PROMPT=0 env -u GIT_SSH_COMMAND git -C "$GIT_DIR_ROOT" "$@"
  fi
}

canli_birim() { # trader-engine-live ile baslayan ve etkin ya da calisan bir birim varsa adini yazar (0); yoksa 1
  local u
  while IFS= read -r u; do
    [ -n "$u" ] || continue
    if systemctl is-enabled --quiet "$u" 2>/dev/null || systemctl is-active --quiet "$u" 2>/dev/null; then
      printf '%s\n' "$u"
      return 0
    fi
  done < <({
    systemctl list-unit-files 'trader-engine-live*' --no-legend --plain 2>/dev/null
    systemctl list-units 'trader-engine-live*' --all --no-legend --plain 2>/dev/null
  } | awk '{print $1}' | grep -E '^trader-engine-live[^ ]*$' | sort -u)
  return 1
}

degisiklikler() { # eski..yeni arasi birlesme haric konu satirlari (en fazla 15), fazlasi icin sayi
  local eski="$1" yeni="$2" toplam
  toplam="$(root_git rev-list --no-merges --count "${eski}..${yeni}" 2>/dev/null || echo 0)"
  root_git log --format=%s --no-merges "${eski}..${yeni}" 2>/dev/null | head -n 15 | sed 's/^/- /'
  if [ "${toplam:-0}" -gt 15 ]; then echo "… ve $((toplam - 15)) değişiklik daha"; fi
}

kisalt_90() { # stdin -> en cok 90 karakter (baytla degil, karakterle: UTF-8 guvenli, yerel ayardan bagimsiz); sozcuk sinirinda kesilir, sonuna "…"
  python3 -c 'import sys
s = sys.stdin.buffer.read().decode("utf-8", "replace").strip()
if len(s) > 90:
    kes = s[:89]
    if not s[89].isspace() and " " in kes:
        kes = kes.rsplit(" ", 1)[0]
    s = kes.rstrip(" ,;:.-") + "…"
sys.stdout.buffer.write((s + "\n").encode("utf-8"))'
}

guncelleme_metni() { # eski yeni: en cok 3 satir, sade Turkce; dosya adi yok; hangi degisiklik + geri alma tek komut
  local eski="$1" yeni="$2" toplam ilk
  toplam="$(root_git rev-list --no-merges --count "${eski}..${yeni}" 2>/dev/null || echo 0)"
  # konu secimi: en yeni "Test:" / "Merge" olmayan konu (yoksa en yeni konu); tek sozcuklu teknik onek ("Mutabakat:") atilir
  ilk="$(root_git log --format=%s --no-merges "${eski}..${yeni}" 2>/dev/null \
    | awk 'NR==1{ilk=$0} !/^(Test|Merge)/{print; bulundu=1; exit} END{if(!bulundu) print ilk}' | head -n 1 \
    | sed -E 's/^[[:alnum:]_-]+: *//; s/[A-Za-z0-9_\/.-]+\.(py|sh|json|md|js|html|service|timer|sqlite)//g; s/_/ /g; s/  +/ /g; s/^ +| +$//g' | kisalt_90)"
  [ -n "$ilk" ] || ilk="iyileştirmeler"
  printf '[ML] Bot güncellendi: %s\n' "$ilk"
  if [ "${toplam:-0}" -gt 1 ]; then printf '(ve %s değişiklik daha)\n' "$((toplam - 1))"; fi
  printf "Senden: sorun görürsen orkestratöre 'ML geri al' yaz.\n"
}

gecmis_ekle() { # eski yeni sonuc
  printf '%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$1" "$2" "$3" >> "$HIST"
}

# Sabit kurulum pencereleri (UTC): 07:30 ve 19:30 + 60 dk tolerans (systemd gecikmesi / yavas baslangic). 10:30 ve 22:30 TSI.
PENCERE_BASLANGIC_DK="${OTO_PENCERE_DK:-450 1170}"   # 07:30 ve 19:30 UTC (dakika olarak)
PENCERE_TOLERANS_DK=60

pencere_icinde() { # 0: simdi (UTC) kurulum penceresinde; 1: disinda
  local sa dk simdi b
  sa="${OTO_SIMDI_SAAT:-$(date -u +%H)}"
  dk="${OTO_SIMDI_DAKIKA:-$(date -u +%M)}"
  simdi=$((10#$sa * 60 + 10#$dk))
  for b in $PENCERE_BASLANGIC_DK; do
    if [ "$simdi" -ge "$b" ] && [ "$simdi" -lt $((b + PENCERE_TOLERANS_DK)) ]; then return 0; fi
  done
  return 1
}

kapanis_bekle() { # kurulumdan once: 15 dk mum kapanisinin 1 dk oncesi - 3 dk sonrasi (dakika%15 in 14,0,1,2) ise dakika%15==3 olana dek bekler (en cok ~4 dk)
  local dk sn r bekle
  dk="${OTO_SIMDI_DAKIKA:-$(date -u +%M)}"
  sn="${OTO_SIMDI_SANIYE:-$(date -u +%S)}"
  dk=$((10#$dk))
  sn=$((10#$sn))
  r=$((dk % 15))
  case "$r" in
    14 | 0 | 1 | 2)
      bekle=$((((3 - r + 15) % 15) * 60 - sn))
      [ "$bekle" -gt 0 ] || bekle=1
      log "mum kapanisina yakin (dakika ${dk}); kurulum ${bekle} sn ertelendi"
      "$UYKU" "$bekle"
      ;;
  esac
  return 0
}

oto_guncelle() {
  mkdir -p "$STATE_DIR"
  chmod 0700 "$STATE_DIR" 2>/dev/null || true
  exec 9>"$STATE_DIR/kilit"
  flock -n 9 || { log "Baska bir guncelleme calisiyor; cikildi."; return 0; }

  if [ -e "$STATE_DIR/DURDUR" ]; then log "DURDUR dosyasi var; otomatik guncelleme durduruldu."; return 0; fi

  # sabit pencere: yalniz 10:30 / 22:30 TSI (acil durumda --simdi). Pencere disinda sessizce cikar (mesaj yok)
  if [ -z "$ZORLA" ] && ! pencere_icinde; then
    log "kurulum penceresi disinda (10:30 ve 22:30 TSI = 07:30/19:30 UTC); islem yok"
    return 0
  fi

  # canli koruma: canli motor (gercek para) etkin ya da calisiyorsa hic dokunulmaz; bildirim gunde bir kez
  local canli bugun
  if canli="$(canli_birim)"; then
    log "canli birim etkin ya da calisiyor ($canli); islem yok"
    bugun="$(date -u +%Y%m%d)"
    if [ "$(cat "$STATE_DIR/canli-uyari.gun" 2>/dev/null || true)" != "$bugun" ]; then
      printf '%s\n' "$bugun" > "$STATE_DIR/canli-uyari.gun"
      log "otomatik guncelleme canli birim nedeniyle durdu (mesaj yok: tekrar eder)"
    fi
    return 0
  fi

  # yesil commit: GitHub Actions sorgusu (yalniz tests.yml basarili kosusu); token dosyasi varsa Bearer ile (stdin'den)
  local json yeni ghtok=""
  [ -f "$GH_TOKEN_FILE" ] && ghtok="$(tr -d ' \t\r\n' < "$GH_TOKEN_FILE" 2>/dev/null || true)"
  local -a ghcmd=(curl -fsSL --max-time 20 -H 'User-Agent: trader-oto-guncelle')
  [ -z "$ghtok" ] || ghcmd+=(--config -)
  if ! json="$( { [ -z "$ghtok" ] || printf 'header = "Authorization: Bearer %s"\n' "$ghtok"; } \
        | "${ghcmd[@]}" "${API_URL}?branch=${BRANCH}&status=success&per_page=1" 2>/dev/null)"; then
    log "GitHub'a ulasilamadi; islem yok (repo gizliyse /etc/trader-github-token gerekli)"
    return 0
  fi
  yeni="$(printf '%s' "$json" | python3 -I -c 'import json, sys
try:
    print(json.load(sys.stdin)["workflow_runs"][0]["head_sha"])
except Exception:
    pass' 2>/dev/null || true)"
  if ! [[ "$yeni" =~ ^[0-9a-f]{40}$ ]]; then log "yesil test kosusu yok; islem yok"; return 0; fi

  local mevcut
  mevcut="$(release_commit)"
  if ! [[ "$mevcut" =~ ^[0-9a-f]{40}$ ]]; then log "mevcut surum bilinmiyor ($RELEASE_FILE); islem yok"; return 0; fi
  if [ "$yeni" = "$mevcut" ]; then log "zaten guncel: ${mevcut:0:7}"; return 0; fi

  if [ -f "$HIST" ] && awk -F'\t' -v y="$yeni" '$3 == y && $4 == "basarisiz" {f = 1} END {exit !f}' "$HIST"; then
    log "${yeni:0:7} daha once basarisiz denendi; tekrar denenmez"
    return 0
  fi

  # geri gitmeyi onle: yesil commit mevcut surumun atasiysa kurulmaz (kok klon uzerinden)
  if ! root_git fetch --quiet origin "+refs/heads/${BRANCH}:refs/remotes/origin/${BRANCH}" 2>/dev/null; then
    log "kok klon guncellenemedi (ag/anahtar?); islem yok"
    return 1
  fi
  if ! root_git cat-file -e "${yeni}^{commit}" 2>/dev/null; then
    log "${yeni:0:7} yayin dalinda bulunamadi; islem yok"
    return 0
  fi
  if ! root_git cat-file -e "${mevcut}^{commit}" 2>/dev/null; then
    log "mevcut surum kok klonda yok; atalik kontrolu yapilamadi, islem yok"
    return 0
  fi
  local rc
  root_git merge-base --is-ancestor "$yeni" "$mevcut" 2>/dev/null
  rc=$?
  if [ "$rc" -eq 0 ]; then log "${yeni:0:7} mevcut surumun atasi (eski); kurulmadi"; return 0; fi
  if [ "$rc" -ne 1 ]; then log "atalik kontrolu hata verdi; islem yok"; return 0; fi


  kapanis_bekle
  log "kurulum basliyor: ${mevcut:0:7} -> ${yeni:0:7}"
  OTO_KURULUM_TUR=oto COMMIT="$yeni" timeout "$INSTALL_TIMEOUT" bash "$INSTALL_SH" >"$ILOG" 2>&1 9>&-
  rc=$?
  mask < "$ILOG"

  local simdi
  simdi="$(release_commit)"
  if [ "$rc" -eq 0 ] && [ "$simdi" = "$yeni" ]; then
    gecmis_ekle "$mevcut" "$yeni" basarili
    # basarili kurulumda Telegram'a HICBIR sey gitmez (yalniz gunluk): kullanici "Telegram cok karisik"
    log "$(guncelleme_metni "$mevcut" "$yeni" | tr '\n' ' ')"
    log "guncellendi: ${mevcut:0:7} -> ${yeni:0:7}"
    return 0
  fi

  gecmis_ekle "$mevcut" "$yeni" basarisiz
  tg_send "[ML] ⚠️ Güncelleme kurulamadı; bot eski sürümle çalışıyor."
  log "BASARISIZ (kurulum cikis=$rc, surum=${simdi:0:7})"
  return 1
}

oto_guncelle
exit $?
