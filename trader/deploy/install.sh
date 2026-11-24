#!/usr/bin/env bash
# Trader sunucu kurulumu (Ubuntu 22.04+/24.04, root olarak, etkilesimsiz, tekrar calistirilabilir).
# Kullanim: COMMIT=<40 karakterlik surum kodu> bash install.sh [--live | --no-live]
#   COMMIT zorunludur (ortam degiskeni; yoksa /etc/trader-release icindeki COMMIT=). Kisa kod, dal ya da etiket adi KABUL EDILMEZ.
#   Ikiz (twin) DD-12'de KALDIRILDI: ikiz birimleri durdurulur/devre disi birakilir, var/twin silinmez var/arsiv/twin-<tarih>/ altina tasinir.
#   --live: CANLI motor birimini kurar (varsayilan KURULMAZ; kurulsa da KENDILIGINDEN BASLAMAZ). --no-live: canli birimi kaldirir.
# Yalniz "trader" kullanicisina ve trader-* systemd birimlerine dokunur; baska projeye, guvenlik duvarina, acik porta dokunmaz.
# Root'un calistirdigi her sey (bu betik, birim sablonlari, env ornekleri, root birimlerinin betikleri) root sahipli
# /usr/local/lib/trader-root/releases/<COMMIT>/ altindan gelir; trader'in yazabildigi depodan hicbir sey calistirilmaz.
set -euo pipefail
SELF_SUM_AT_START="$(sha256sum "$0" 2>/dev/null | cut -d" " -f1 || true)"   # surum kopyasindaki betikle yeniden baslamak icin

# ---- ayarlar (gerekirse degistirin) ---------------------------------------
REPO_URL="${REPO_URL:-https://github.com/sselimgenc-oss/SG-ML-Otonom.git}"
REPO_SSH_URL="${REPO_SSH_URL:-git@github.com:sselimgenc-oss/SG-ML-Otonom.git}"
BRANCH="${BRANCH:-claude/charming-hawking-ab5w5q}"
TRADER_USER="trader"
TG_GROUP="trader-tg"
HOME_DIR="/home/${TRADER_USER}"
REPO_DIR="${HOME_DIR}/SG-Github-AB-proje"
TRADER_DIR="${REPO_DIR}/trader"
DEPLOY_KEY="${HOME_DIR}/.ssh/deploy_key"
SWAP_FILE="/swapfile"
SWAP_SIZE="4G"
UNIT_DIR="/etc/systemd/system"
ROOT_DIR="/usr/local/lib/trader-root"      # root sahipli kod/venv/klon agaci (/opt/trader-root KULLANILMAZ: render() sed'i onu bozar)
RELEASE_FILE="/etc/trader-release"
LIVE_FLAG=0
NO_LIVE=0

for arg in "$@"; do
  case "$arg" in
    --live) LIVE_FLAG=1 ;;
    --no-live) NO_LIVE=1 ;;
    *) echo "Bilinmeyen secenek: $arg (kullanim: install.sh [--live | --no-live])" >&2; exit 2 ;;
  esac
done
if [ "$LIVE_FLAG" -eq 1 ] && [ "$NO_LIVE" -eq 1 ]; then
  echo "Kullanim hatasi: --live ve --no-live birlikte verilemez." >&2
  exit 2
fi
# Canli kipi: --live verildi YA DA canli birim zaten kurulu (yapiskan); --no-live her ikisini de kapatir.
if [ "$NO_LIVE" -eq 1 ]; then
  LIVE=0
elif [ "$LIVE_FLAG" -eq 1 ] || [ -f "${UNIT_DIR}/trader-engine-live.service" ]; then
  LIVE=1
else
  LIVE=0
fi

say()  { printf '\n==> %s\n' "$*"; }
fail() { printf '\nHATA: %s\n' "$*" >&2; exit 1; }

valid_commit() { # 40 kucuk onaltilik karakter (kisa sha, dal adi, etiket adi, buyuk harf RET)
  local v="${1-}"
  [[ "$v" =~ ^[0123456789abcdef]{40}$ ]]
}

resolve_commit() { # stdout'a COMMIT'i yazar; yoksa/gecersizse 1 doner. Sira: ortam > RELEASE_FILE (ortamdaki gecersiz deger dosyaya dusmez)
  local v f
  if [ -n "${COMMIT:-}" ]; then
    valid_commit "$COMMIT" || return 1
    printf '%s\n' "$COMMIT"
    return 0
  fi
  f="${RELEASE_FILE:-/etc/trader-release}"
  if [ -f "$f" ]; then
    v="$(sed -n 's/^COMMIT=//p' "$f" | head -n 1 | tr -d '[:space:]')"
    if valid_commit "$v"; then
      printf '%s\n' "$v"
      return 0
    fi
  fi
  return 1
}

is_live_tag() { # canli-YYYYAAGG[-N]
  local v="${1-}"
  [[ "$v" =~ ^canli-[0-9]{8}(-[0-9]+)?$ ]]
}

set_kv() { # dosya AD deger: satir varsa degistirir, yoksa ekler; dosya sonu satir sonu korunur (idempotent)
  local f="$1" k="$2" v="$3" esc
  if grep -q "^${k}=" "$f" 2>/dev/null; then
    esc="$(printf '%s' "$v" | sed -e 's/[\\&|]/\\&/g')"
    sed -i "s|^${k}=.*|${k}=${esc}|" "$f"
  else
    if [ -s "$f" ] && [ -n "$(tail -c1 "$f")" ]; then echo >> "$f"; fi
    printf '%s=%s\n' "$k" "$v" >> "$f"
  fi
}

safe_tree_path() { # F2: root owner/mod islemi oncesi, yolun HICBIR bileseni sembolik baglanti olamaz (trader yazabilir)
  local p
  for p in "$@"; do
    if [ "$(realpath -m "$p")" != "$p" ]; then
      fail "Guvenlik: $p yolunda sembolik baglanti var (kurulum durdu; root trader'in koydugu baglantiyi izlemez)"
      return 1
    fi
  done
}

[ "$(id -u)" -eq 0 ] || fail "Bu betik root olarak calistirilmali (DigitalOcean konsolunda zaten rootsunuz)."

# COMMIT zorunlu: hicbir sey degistirilmeden once cozulur (ortam, yoksa /etc/trader-release).
COMMIT="$(resolve_commit)" || fail "COMMIT gerekli: 40 karakterlik kucuk harfli surum kodu (ornek: COMMIT=<kod> bash install.sh). Kisa kod, dal ya da etiket adi kabul edilmez. Hicbir sey degistirilmedi."
export COMMIT
REL_DIR="${ROOT_DIR}/releases/${COMMIT}"
PREV_COMMIT="$(sed -n 's/^COMMIT=//p' "$RELEASE_FILE" 2>/dev/null | head -n 1 | tr -d '[:space:]' || true)"
echo "Surum (COMMIT): ${COMMIT}   canli kip: ${LIVE}"

# ---- 0. Ubuntu / python kontrolu -------------------------------------------
say "Sistem kontrolu"
echo "Bellek (kurulumdan once; diger projenin payini dusunun):"
free -m | awk 'NR==1 || /Mem:|Swap:/ {print "  " $0}'
command -v apt-get >/dev/null || fail "Bu betik Ubuntu/Debian icindir."
command -v systemctl >/dev/null || fail "systemd bulunamadi."
PY_BIN="$(command -v python3 || true)"
if [ -z "$PY_BIN" ]; then
  DEBIAN_FRONTEND=noninteractive apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3
  PY_BIN="$(command -v python3)"
fi
if ! "$PY_BIN" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  fail "Sunucudaki Python surumu cok eski ($("$PY_BIN" --version 2>&1)); en az 3.11 gerekir (Ubuntu 24.04 uygundur). Hicbir sey kurulmadi/degistirilmedi. Lutfen bana bildirin, birlikte cozelim."
fi
echo "Python: $("$PY_BIN" --version 2>&1)"

# ---- 1. swap ------------------------------------------------------------------
say "Takas (swap)"
if [ -n "$(swapon --show --noheadings 2>/dev/null)" ]; then
  echo "Takas zaten var, dokunulmadi."
else
  if [ ! -e "$SWAP_FILE" ]; then
    fallocate -l "$SWAP_SIZE" "$SWAP_FILE" 2>/dev/null || dd if=/dev/zero of="$SWAP_FILE" bs=1M count=4096 status=none
    chmod 600 "$SWAP_FILE"
    mkswap "$SWAP_FILE" >/dev/null
  fi
  swapon "$SWAP_FILE"
  grep -qs "^${SWAP_FILE} " /etc/fstab || echo "${SWAP_FILE} none swap sw 0 0" >> /etc/fstab
  echo "4 GB takas olusturuldu."
fi
echo "vm.swappiness=10" > /etc/sysctl.d/99-trader-swappiness.conf
sysctl -q -p /etc/sysctl.d/99-trader-swappiness.conf >/dev/null || true

# ---- 2. kullanici ve gruplar --------------------------------------------------
say "Kullanici ve gruplar"
getent group "$TG_GROUP" >/dev/null || groupadd --system "$TG_GROUP"
if ! id "$TRADER_USER" >/dev/null 2>&1; then
  useradd --create-home --home-dir "$HOME_DIR" --shell /usr/sbin/nologin "$TRADER_USER"
fi
# DD-9 (O13): trader kullanicisi trader-tg uyesi OLMAZ (env dosyalari root:root 0600). Grup silinmez: outbox dizini (2770 trader:trader-tg)
# ve birimlerdeki SupplementaryGroups=trader-tg root yazan saglik birimi ile trader okuyan daemon arasindaki tek koprudur.
if id -nG "$TRADER_USER" 2>/dev/null | tr ' ' '\n' | grep -qx "$TG_GROUP"; then
  gpasswd -d "$TRADER_USER" "$TG_GROUP" >/dev/null   # gpasswd -d trader trader-tg (uye degilse bu satira girilmez)
  echo "trader kullanicisi trader-tg grubundan cikarildi."
fi
safe_tree_path "$HOME_DIR"
install -d -m 0750 -o "$TRADER_USER" -g "$TRADER_USER" "$HOME_DIR"

# ---- 3. paketler -----------------------------------------------------------------
say "Paketler (python3-venv, git, sqlite3, openssl)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3-venv git sqlite3 ca-certificates openssl

# ---- 4. depo, root kopyasi ve surum ----------------------------------------------
say "Kod deposu ve root kopyasi"
as_trader() { runuser -u "$TRADER_USER" -- "$@"; }
install -d -m 0755 -o root -g root "$ROOT_DIR" "$ROOT_DIR/releases"
ROOT_GIT_SSH=""
if [ -f "$DEPLOY_KEY" ]; then
  [ ! -L "$DEPLOY_KEY" ] || fail "Deploy anahtari sembolik baglanti: $DEPLOY_KEY (kurulum durdu)"
  safe_tree_path "$DEPLOY_KEY"
  chown -h "$TRADER_USER:$TRADER_USER" "$DEPLOY_KEY"; chmod 600 "$DEPLOY_KEY"
  # root'un kendi anahtar kopyasi ve sabit known_hosts'u (root trader'in dizinindeki hicbir dosyaya guvenmez)
  install -d -m 0700 -o root -g root "$ROOT_DIR/ssh"
  install -m 0600 -o root -g root "$DEPLOY_KEY" "$ROOT_DIR/ssh/deploy_key"
  # github.com ana makine anahtarlari sabit (TOFU/accept-new yok). Kaynak: GitHub "SSH key fingerprints" belgesi ve
  # https://api.github.com/meta (ssh_keys); parmak izleri: ed25519 SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU,
  # ecdsa SHA256:p2QAMXNIC1TJYWeIOttrVc98/R1BUFWu3/LiyKgUfQM, rsa SHA256:uNiVztksCsDhcc0u9e8BujQXVUpKZIDTMczCvj3tD2s
  cat > "$ROOT_DIR/ssh/known_hosts" <<'KEYS'
github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl
github.com ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBEmKSENjQEezOmxkZMy7opKgwFB9nkt5YRrYMjNuG5N87uRgg6CLrbo5wAdT/y6v0mKV0U2w0WZ2YB/++Tpockg=
github.com ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCj7ndNxQowgcQnjshcLrqPEiiphnt+VTTvDP6mHBL9j1aNUkY4Ue1gvwnGLVlOhGeYrnZaMgRK6+PKCUXaDbC7qtbW8gIkhL7aGCsOr/C56SJMy/BCZfxd1nWzAOxSDPgVsmerOBYfNqltV9/hWCqBywINIR+5dIg6JTJ72pcEpEjcYgXkE2YEFXV1JHnsKgbLWNlhScqb2UmyRkQyytRLtL+38TGxkxCflmO+5Z8CSSNY7GidjMIZ7Q4zMjA2n1nGrlTDkzwDCsw+wqFPGQA179cnfGWOWRVruj16z6XyvxvjJwbz0wQZ75XK5tKSb7FNyeIEs4TT4jk+S4dhPeAUC5y+bDYirYgM4GC7uEnztnZyaVWQ7B381AK4Qdrwt51ZqExKbQpTUNn+EjqoTwvqNj4kqx5QUCI0ThS/YkOxJCXmPUWZbhjpCg56i+2aB6CmK2JGhn57K5mj0MNdBXA4/WnwH6XoPWJzK5Nyu2zB3nAZp+S5hpQs+p1vN1/wsjk=
KEYS
  chmod 0600 "$ROOT_DIR/ssh/known_hosts"
  GH_KNOWN_HOSTS="${HOME_DIR}/.ssh/github_known_hosts"
  safe_tree_path "$GH_KNOWN_HOSTS" "${HOME_DIR}/.ssh"
  install -m 0644 -o "$TRADER_USER" -g "$TRADER_USER" "$ROOT_DIR/ssh/known_hosts" "$GH_KNOWN_HOSTS"
  # trader'in (kod deposu icin) ve root'un (kendi klonu icin) AYRI ssh komutlari; root yalniz kendi kopyasini kullanir
  export GIT_SSH_COMMAND="ssh -i ${DEPLOY_KEY} -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=${GH_KNOWN_HOSTS}"
  ROOT_GIT_SSH="ssh -i ${ROOT_DIR}/ssh/deploy_key -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=${ROOT_DIR}/ssh/known_hosts"
  CLONE_URL="$REPO_SSH_URL"
  echo "Deploy anahtari bulundu; SSH ile cekiliyor."
else
  CLONE_URL="$REPO_URL"
fi

# -- 4a. root'un KENDI ciplak klonu: yalniz $BRANCH ve canli-* etiketleri (trader deposuna root hicbir git komutu calistirmaz)
ROOT_REPO="$ROOT_DIR/repo.git"
root_git() {
  if [ -n "$ROOT_GIT_SSH" ]; then
    GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND="$ROOT_GIT_SSH" git -C "$ROOT_REPO" "$@"
  else
    GIT_TERMINAL_PROMPT=0 env -u GIT_SSH_COMMAND git -C "$ROOT_REPO" "$@"
  fi
}
[ -d "$ROOT_REPO" ] || git init --bare --quiet "$ROOT_REPO"
if root_git remote get-url origin >/dev/null 2>&1; then root_git remote set-url origin "$CLONE_URL"; else root_git remote add origin "$CLONE_URL"; fi
root_git fetch --quiet origin "+refs/heads/${BRANCH}:refs/remotes/origin/${BRANCH}" "+refs/tags/canli-*:refs/tags/canli-*" \
  || fail "Root klonu guncellenemedi (ag/anahtar?). Hicbir sey degistirilmedi."
root_git cat-file -e "${COMMIT}^{commit}" 2>/dev/null || fail "COMMIT root klonunda yok: ${COMMIT} (dal: ${BRANCH}). Hicbir sey degistirilmedi."
root_git merge-base --is-ancestor "$COMMIT" "refs/remotes/origin/${BRANCH}" \
  || fail "COMMIT yayın dalında değil: ${COMMIT} (dal: ${BRANCH}). Hicbir sey degistirilmedi."

# -- 4b. surum dizini: git archive (trader/ oneki atilir); yarim kalirsa current DEGISMEZ
if [ ! -f "${REL_DIR}/.complete" ]; then
  REL_TMP="$(mktemp -d "${ROOT_DIR}/releases/.tmp-XXXXXX")"
  if ! root_git archive --format=tar "$COMMIT" trader/src trader/scripts trader/deploy trader/config trader/requirements.lock \
        | tar -x -C "$REL_TMP" --strip-components=1 --no-same-owner --no-same-permissions; then
    rm -rf "$REL_TMP"
    fail "Surum arsivi cikarilamadi; current degismedi (eski surum calismaya devam eder)."
  fi
  chown -R root:root "$REL_TMP"
  chmod -R go-w "$REL_TMP"
  chmod 0755 "$REL_TMP"
  if [ ! -f "$REL_TMP/deploy/install.sh" ] || [ ! -f "$REL_TMP/deploy/requirements-root.lock" ]; then
    rm -rf "$REL_TMP"
    fail "Surum eksik (deploy/install.sh ya da requirements-root.lock yok); current degismedi."
  fi
  : > "$REL_TMP/.complete"
  rm -rf "$REL_DIR"
  mv -T "$REL_TMP" "$REL_DIR"
fi
[ -d "$REL_DIR/deploy" ] || fail "$REL_DIR/deploy yok; surum hazirlanamadi."

# -- 4c. root'un sanal ortami: yalniz requests ve 4 bagimliligi, hash sabit (requirements-root.lock)
say "Root python ortami"
[ -x "$ROOT_DIR/venv/bin/python" ] || "$PY_BIN" -m venv "$ROOT_DIR/venv"
"$ROOT_DIR/venv/bin/python" -m pip install --quiet --disable-pip-version-check --require-hashes --no-deps \
  -r "$REL_DIR/deploy/requirements-root.lock"

# -- 4d. current: atomik gecis (yeni baglanti + mv -T); eski surumler: current + onceki en cok iki
ln -sfn "$REL_DIR" "$ROOT_DIR/current.new"
mv -T "$ROOT_DIR/current.new" "$ROOT_DIR/current"
KEEP=0
while IFS= read -r old; do
  [ -n "$old" ] || continue
  [ "$old" = "$COMMIT" ] && continue
  KEEP=$((KEEP + 1))
  if [ "$KEEP" -gt 2 ]; then rm -rf "${ROOT_DIR:?}/releases/${old}"; fi
done < <(find "$ROOT_DIR/releases" -mindepth 1 -maxdepth 1 -type d -regextype posix-extended -regex '.*/[0-9a-f]{40}' -printf '%T@ %f\n' 2>/dev/null | sort -rn | awk '{print $2}')

# Bash calisan betigi bellekte eski haliyle surdurur; surum kopyasindaki betik farkliysa ONUNLA bastan calistir (bir kez).
if [ "${TRADER_INSTALL_REEXEC:-}" != "root" ] && [ "$(sha256sum "$ROOT_DIR/releases/$COMMIT/deploy/install.sh" | cut -d" " -f1)" != "$SELF_SUM_AT_START" ]; then
  say "install.sh surum kopyasindan yeniden baslatiliyor"
  export TRADER_INSTALL_REEXEC=root      # eski betigin "1" bayragi bu gecisi atlatamaz: yalniz kok kopyadan baslayan surec "root" yazar
  exec bash "$ROOT_DIR/releases/$COMMIT/deploy/install.sh" "$@"
fi

# -- 4e. trader deposu: COMMIT'e sabitlenir (dal ucu DEGIL); git islemleri trader olarak
# WP-3 (defter sema 4): sema goci YALNIZ motor sureciyle (yazar, premigrate yedegi) yapilir; okuyucular salt okunur acar.
# Bu yuzden kod degistiyse (onceki /etc/trader-release != COMMIT) calisan motorlar sonda yeniden baslatilir.
CODE_CHANGED=0
if [ "$PREV_COMMIT" != "$COMMIT" ]; then CODE_CHANGED=1; fi
HAVE_REPO=0
as_trader test -d "$REPO_DIR/.git" && HAVE_REPO=1 || true
if [ "$HAVE_REPO" -eq 1 ]; then
  as_trader git -C "$REPO_DIR" fetch --quiet origin "$BRANCH" || fail "Depo guncellenemedi (ag/anahtar?)."
else
  as_trader git clone --quiet --branch "$BRANCH" "$CLONE_URL" "$REPO_DIR" \
    || fail "Depo indirilemedi. Depo ozelse deploy anahtari gerekir: bkz. trader/docs/sunucu-kurulum.md"
fi
as_trader git -C "$REPO_DIR" checkout --quiet --detach "$COMMIT" \
  || fail "COMMIT trader deposuna alinamadi (yerel degisiklik var mi?). $REPO_DIR icinde elle bakilmali."
trader_git() {
  as_trader git -C "$REPO_DIR" "$@"
}
[ "$(trader_git rev-parse HEAD)" = "$COMMIT" ] || fail "Trader deposu COMMIT'te degil."
[ -z "$(trader_git status --porcelain --untracked-files=no)" ] \
  || fail "Trader deposunda izlenen dosyalarda yerel degisiklik var; kurulum durdu ($REPO_DIR icinde elle bakilmali)."
[ -d "$TRADER_DIR/deploy" ] || fail "$TRADER_DIR/deploy yok; dal/depo adi yanlis olabilir."

# ---- 5. python ortami (yalniz calisma bagimliliklari) -----------------------------
say "Python ortami (birkac dakika surebilir)"
[ -x "$TRADER_DIR/.venv/bin/python" ] || as_trader "$PY_BIN" -m venv "$TRADER_DIR/.venv"
as_trader "$TRADER_DIR/.venv/bin/python" -m pip install --quiet --disable-pip-version-check --upgrade pip
# trader/src ve trader/scripts icindeki iceri aktarmalardan: requests pandas numpy pyarrow anthropic (ccxt YOK: dis cati yasak)
# (dis ticaret cercevesi, pytest ve diger gelistirme paketleri KURULMAZ)
# Surum + sha256 sabit: requirements.lock (CPython 3.12, linux x86_64); --require-hashes kaymayi/degisikligi reddeder.
as_trader "$TRADER_DIR/.venv/bin/python" -m pip install --quiet --disable-pip-version-check \
  --require-hashes -r "$TRADER_DIR/requirements.lock"

# ---- 5a. canli on kosullari (LIVE=1): herhangi bir birim/env degismeden once ------------
has_value() { # dosyada ANAHTAR= bos degilse 0
  grep -Eq "^$2=[^[:space:]]+" "$1" 2>/dev/null
}
MISSING=()
if [ "$LIVE" -eq 1 ]; then
  say "Canli on kosullari"
  [ -f "$RELEASE_FILE" ] || fail "önce --live'sız kurulum gerekli ($RELEASE_FILE yok)"
  LIVE_ENV="/etc/trader-live.env"
  { [ -f "$LIVE_ENV" ] && [ ! -L "$LIVE_ENV" ]; } || fail "Canli on kosul: $LIVE_ENV yok. Once COMMIT ile --live'siz kurun, sonra dosyayi nano ile doldurun."
  [ "$(stat -c '%a' "$LIVE_ENV")" = "600" ] || fail "Canli on kosul: $LIVE_ENV kipi 0600 degil."
  if [ "$(id -u)" -eq 0 ] && [ "$(stat -c '%U:%G' "$LIVE_ENV")" != "root:root" ]; then fail "Canli on kosul: $LIVE_ENV sahibi root:root degil."; fi
  for k in BINANCE_API_KEY BINANCE_API_SECRET LIVE_CONFIRM; do
    has_value "$LIVE_ENV" "$k" || fail "Canli on kosul: $LIVE_ENV icinde $k bos. Dosyayi nano ile doldurun (degeri sohbete yazmayin)."
  done
  LIVE_TAG_OK=0
  LIVE_TAGS="$(root_git tag --points-at "$COMMIT" 2>/dev/null || true)"
  for t in $LIVE_TAGS; do
    if is_live_tag "$t"; then LIVE_TAG_OK=1; fi
  done
  [ "$LIVE_TAG_OK" -eq 1 ] || fail "Canli on kosul: COMMIT canli-YYYYAAGG[-N] etiketi tasimiyor; etiketsiz commit canliya kurulamaz."
  # canli katman motorun KENDI dogrulayicisiyla yuklenir (LIVE_CONFIRM gerekmez; hicbir sey yazilmaz)
  PYTHONPATH="$TRADER_DIR/src" as_trader "$TRADER_DIR/.venv/bin/python" -m trader_engine pause --bot learner --env live \
    --config-dir "$TRADER_DIR/config" --list >/dev/null \
    || fail "Canli on kosul: config/engine.live.json motorun dogrulayicisindan gecmedi."
  echo "Canli on kosullar tamam."
fi

# ---- 5b. Node + wrangler (yalniz panel yayini icin; yalniz eksikse kurulur, global degil) ------------------
say "Node/npm ve wrangler (Cloudflare yayini)"
WRANGLER_VERSION="3.114.0"      # sabit surum (kayan 'latest' yok)
WRANGLER_DIR="$TRADER_DIR/var/wrangler"
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  apt-get install -y -qq nodejs npm
fi
safe_tree_path "$TRADER_DIR/var" "$WRANGLER_DIR"
install -d -m 0750 -o "$TRADER_USER" -g "$TRADER_USER" "$TRADER_DIR/var" "$WRANGLER_DIR"
if [ "$(as_trader cat "$WRANGLER_DIR/node_modules/wrangler/package.json" 2>/dev/null | grep -o '"version": *"[^"]*"' | head -1 | grep -o '[0-9][0-9.]*')" != "$WRANGLER_VERSION" ]; then
  ( cd "$WRANGLER_DIR" && as_trader env HOME="$HOME_DIR" npm install --no-audit --no-fund --silent --prefix "$WRANGLER_DIR" "wrangler@${WRANGLER_VERSION}" ) \
    || echo "UYARI: wrangler kurulamadi; install.sh'i yeniden calistirin (panel yayini bu olmadan calismaz)."
else
  echo "wrangler ${WRANGLER_VERSION} zaten kurulu."
fi

# ---- 6. dizinler -------------------------------------------------------------------
say "Dizinler"
safe_tree_path "$TRADER_DIR/var" "$TRADER_DIR/shared" "$TRADER_DIR/shared/veto" "$TRADER_DIR/user_data" "$TRADER_DIR/var/history" \
  "$TRADER_DIR/var/telegram" "$TRADER_DIR/var-testnet" "$TRADER_DIR/shared/testnet" "$TRADER_DIR/var-live" "$TRADER_DIR/shared/live" \
  "$TRADER_DIR/var/telegram/outbox" "$TRADER_DIR/user_data/budget.sqlite"
install -d -m 0750 -o "$TRADER_USER" -g "$TRADER_USER" "$TRADER_DIR/var" "$TRADER_DIR/shared" "$TRADER_DIR/shared/veto" \
  "$TRADER_DIR/user_data" "$TRADER_DIR/var/history" \
  "$TRADER_DIR/var/telegram" "$TRADER_DIR/var-testnet" "$TRADER_DIR/shared/testnet" \
  "$TRADER_DIR/var-live" "$TRADER_DIR/shared/live"
install -d -m 2770 -o "$TRADER_USER" -g "$TG_GROUP" "$TRADER_DIR/var/telegram/outbox"
# gece egitimi calisma zamani ciktilari (git-izli models/ ve research/ yazilmaz): var/learner/models/pa_proposer
safe_tree_path "$TRADER_DIR/var/learner" "$TRADER_DIR/var/learner/models" \
  "$TRADER_DIR/var/learner/models/pa_proposer"
install -d -m 0750 -o "$TRADER_USER" -g "$TRADER_USER" "$TRADER_DIR/var/learner" "$TRADER_DIR/var/learner/models" \
  "$TRADER_DIR/var/learner/models/pa_proposer"
install -d -m 0750 -o root -g root /var/backups/trader
# veto birimi artik trader olarak calisir (DD-9 §4.2): onceden root'un yazdigi dosyalar trader'a gecer
chown -hR "$TRADER_USER:$TRADER_USER" "$TRADER_DIR/shared/veto" "$TRADER_DIR/user_data"
# budget.sqlite'i trader sahipli onceden olustur (yoksa): ilk olusturan veto (root) olursa dosya root:root 0600 kalir ve ders/telegram acamaz (OPEN-8).
# Sifir bayt dosya gecerlidir: budget.py bos dosyayi 'ilk olusturma' sayip semayi kendisi kurar.
if [ ! -e "$TRADER_DIR/user_data/budget.sqlite" ]; then
  safe_tree_path "$TRADER_DIR/user_data/budget.sqlite"
  install -m 0600 -o "$TRADER_USER" -g "$TRADER_USER" /dev/null "$TRADER_DIR/user_data/budget.sqlite"
fi

# ---- 7. env dosyalari (var olani asla ezme) -----------------------------------------
say "Ayar dosyalari (/etc/trader-*.env)"
copy_env() { # kaynak ornek, hedef, sahip:grup, mod
  local dst="$2"
  if [ -e "$dst" ]; then echo "Var, dokunulmadi: $dst"; return; fi
  install -m "$4" -o "${3%%:*}" -g "${3##*:}" "$1" "$dst"
  echo "Olusturuldu: $dst"
}
harden_env_file() { # /etc/trader-*.env: root:root 0600; sembolik baglantiya DOKUNMAZ ve kurulumu durdurur
  local f="$1"
  if [ -L "$f" ]; then
    fail "Ayar dosyasi sembolik baglanti: $f (kurulum durdu; dosyayi elle inceleyin)"
    return 1
  fi
  [ -e "$f" ] || return 0
  if [ "$(id -u)" -eq 0 ]; then chown root:root "$f"; fi
  chmod 0600 "$f"
}
REL_DIR="${REL_DIR:-${ROOT_DIR:-/usr/local/lib/trader-root}/releases/${COMMIT:-unset}}"   # env ornekleri root sahipli surum dizininden
copy_env "$REL_DIR/deploy/trader-health.env.example"    /etc/trader-health.env    "root:root" 0600
copy_env "$REL_DIR/deploy/trader-lesson.env.example"    /etc/trader-lesson.env    "root:root" 0600
copy_env "$REL_DIR/deploy/trader-telegram.env.example"  /etc/trader-telegram.env  "root:root" 0600
copy_env "$REL_DIR/deploy/trader-veto-hmac.env.example" /etc/trader-veto-hmac.env "root:root" 0600
copy_env "$REL_DIR/deploy/trader-panel-cf.env.example"  /etc/trader-panel-cf.env  "root:root" 0600
# testnet golge motoru anahtarlari: AYRI dosya (canli anahtar dosyasi degil); anahtarlar bos kalirsa birim acilmaz (WP-B8)
copy_env "$REL_DIR/deploy/trader-testnet.env.example"   /etc/trader-testnet.env   "root:root" 0600
# CANLI anahtar dosyasi (DD-9): bos ornekten her kurulumda olusturulur (var olan ezilmez); degerleri kullanici nano ile yazar
copy_env "$REL_DIR/deploy/trader-live.env.example"      /etc/trader-live.env      "root:root" 0600
# veto HMAC anahtari (YALNIZ testnet/canli motoru dogrular; kagitta veto yok): bos ise otomatik uret (ekrana YAZILMAZ)
if ! grep -Eq '^TRADER_VETO_HMAC_KEY=[^[:space:]]+' /etc/trader-veto-hmac.env; then
  HMAC_NEW="$(openssl rand -hex 32)"
  sed -i '/^TRADER_VETO_HMAC_KEY=/d' /etc/trader-veto-hmac.env
  printf 'TRADER_VETO_HMAC_KEY=%s\n' "$HMAC_NEW" >> /etc/trader-veto-hmac.env
  unset HMAC_NEW
  chmod 0600 /etc/trader-veto-hmac.env
  echo "Uretildi: /etc/trader-veto-hmac.env (veto HMAC anahtari; gosterilmez)"
fi
# yol alanlarini bu sunucunun gercek yoluna cevir (yalniz /opt/trader on eki ve bos ENGINE_VAR_DIR)
for f in /etc/trader-health.env /etc/trader-lesson.env /etc/trader-telegram.env; do
  sed -i "s#/opt/trader/#${TRADER_DIR}/#g" "$f"
done
sed -i "s#^ENGINE_VAR_DIR=\$#ENGINE_VAR_DIR=${TRADER_DIR}/var#" /etc/trader-health.env
# piyasa verisi alarmlari varsayilan acik (bos ise doldur; kullanici degeri korunur)
sed -i "s#^MARKET_DB=\$#MARKET_DB=${TRADER_DIR}/var/market.sqlite#" /etc/trader-health.env
sed -i "s#^ENGINE_CONFIG_DIR=\$#ENGINE_CONFIG_DIR=${TRADER_DIR}/config#" /etc/trader-health.env
# sapma izleyicisi kancasi (saglik-spec 16.6): izleyici birimleri kuruldugu icin drift_check_enabled acilir; bos/eksik ise 1 yazilir, kullanici degeri korunur
if ! grep -q '^DRIFT_CHECK_ENABLED=' /etc/trader-health.env; then
  # dosya sonunda satir sonu yoksa once ekle (son satirin sonuna yapismasin)
  if [ -s /etc/trader-health.env ] && [ -n "$(tail -c1 /etc/trader-health.env)" ]; then echo >> /etc/trader-health.env; fi
  echo "DRIFT_CHECK_ENABLED=1" >> /etc/trader-health.env
fi
sed -i "s#^DRIFT_CHECK_ENABLED=\$#DRIFT_CHECK_ENABLED=1#" /etc/trader-health.env
# beklenen motorlar (DD-12: ikiz yok, yalniz learner); her calistirmada guncellenir
HEALTH_BOTS_VAL="learner"
if grep -q '^HEALTH_BOTS=' /etc/trader-health.env; then
  sed -i "s#^HEALTH_BOTS=.*#HEALTH_BOTS=${HEALTH_BOTS_VAL}#" /etc/trader-health.env
else
  echo "HEALTH_BOTS=${HEALTH_BOTS_VAL}" >> /etc/trader-health.env
fi
# /durdur her beklenen botun PAUSE dosyasina yazar (11 §9.5): yalniz learner (DD-12: ikiz yok)
if grep -q '^PAUSE_BOTS=' /etc/trader-telegram.env; then
  sed -i "s#^PAUSE_BOTS=.*#PAUSE_BOTS=${HEALTH_BOTS_VAL}#" /etc/trader-telegram.env
else
  echo "PAUSE_BOTS=${HEALTH_BOTS_VAL}" >> /etc/trader-telegram.env
fi

# her calistirmada: /etc/trader-*.env kalibindaki VAR OLAN her dosya root:root 0600 (DD-9 O13; sembolik baglanti = kurulum durur)
for f in /etc/trader-*.env; do
  { [ -e "$f" ] || [ -L "$f" ]; } || continue
  harden_env_file "$f"
done
# canli yol alanlari (sir DEGIL; yalniz --live): Telegram ve saglik canli botu config/engine.live.json ile ayni yollardan izler (DD-9 §6.4)
if [ "${LIVE:-0}" -eq 1 ]; then
  set_kv /etc/trader-telegram.env KILL_FILE "${TRADER_DIR}/shared/live/KILL"
  set_kv /etc/trader-telegram.env ENGINE_STATUS_PATH "${TRADER_DIR}/var-live/learner/status.json"
  set_kv /etc/trader-telegram.env LEDGER_PATH "${TRADER_DIR}/var-live/learner/ledger.sqlite"
  set_kv /etc/trader-telegram.env LIVE_BOTS "learner"
  set_kv /etc/trader-telegram.env LIVE_VAR_DIR "${TRADER_DIR}/var-live"
  set_kv /etc/trader-telegram.env LIVE_PAUSE_FILE "${TRADER_DIR}/shared/live/PAUSE"
  set_kv /etc/trader-telegram.env LADDER_BOTS "learner"
  set_kv /etc/trader-telegram.env ENGINE_CONFIG_DIR "${TRADER_DIR}/config"
  set_kv /etc/trader-health.env LIVE_BOTS "learner"
  set_kv /etc/trader-health.env LIVE_VAR_DIR "${TRADER_DIR}/var-live"
  set_kv /etc/trader-health.env LIVE_PAUSE_FILE "${TRADER_DIR}/shared/live/PAUSE"
  set_kv /etc/trader-lesson.env LEDGER_PATH "${TRADER_DIR}/var-live/learner/ledger.sqlite"
fi

# ---- 8. systemd birimleri ---------------------------------------------------------
say "systemd birimleri"
render() { # ornek birim yollarini bu sunucuya uyarla
  sed -e "s#/home/trader/trader/var#${TRADER_DIR}/var#g" \
      -e "s#/opt/trader#${TRADER_DIR}#g" \
      -e "s#/usr/bin/python3#${TRADER_DIR}/.venv/bin/python#g" "$1" > "$2"
  chmod 0644 "$2"
}
for f in "$REL_DIR"/deploy/trader-*.service "$REL_DIR"/deploy/trader-*.timer; do
  # canli birim YALNIZ LIVE=1 iken kurulur (varsayilan kapali)
  if [ "$(basename "$f")" = "trader-engine-live.service" ] && [ "$LIVE" -ne 1 ]; then continue; fi
  render "$f" "${UNIT_DIR}/$(basename "$f")"
done
# DD-12: eski ML golge drop-in'i (paper-ml katmani) artik yok; sunucuda kalan drop-in dizini kaldirilir
rm -rf "${UNIT_DIR}/trader-engine@learner.service.d"
if [ "$NO_LIVE" -eq 1 ]; then
  say "Canli kip kapatiliyor (--no-live)"
  systemctl disable --now trader-engine-env-retry@live.timer >/dev/null 2>&1 || true
  systemctl disable --now trader-engine-live.service >/dev/null 2>&1 || true
  rm -f "${UNIT_DIR}/trader-engine-live.service"
  echo "UYARI: /etc/trader-telegram.env, /etc/trader-health.env icindeki canli alanlar (LIVE_BOTS, LIVE_VAR_DIR, LIVE_PAUSE_FILE, KILL_FILE, ...) ve /etc/trader-lesson.env LEDGER_PATH elle kagit degerlerine alinmali."
fi
# trader.slice: tum birimlerin ortak bellek tavani (GECICI sayilar; soak'te 48 saatlik olcumle kesinlesir). 'trader-*' glob'una girmez, ayrica kurulur.
render "$REL_DIR/deploy/trader.slice" "${UNIT_DIR}/trader.slice"
systemctl daemon-reload
# journald boyut siniri (drop-in; yalniz icerik degistiyse journald yeniden baslatilir; baska journald ayarina dokunmaz)
JD_DST="/etc/systemd/journald.conf.d/trader.conf"
install -d -m 0755 -o root -g root /etc/systemd/journald.conf.d
if ! cmp -s "$REL_DIR/deploy/trader-journald.conf" "$JD_DST" 2>/dev/null; then
  install -m 0644 -o root -g root "$REL_DIR/deploy/trader-journald.conf" "$JD_DST"
  systemctl restart systemd-journald || echo "UYARI: systemd-journald yeniden baslatilamadi (drop-in bir sonraki acilista gecerli olur)"
fi

# ---- 9. veri ---------------------------------------------------------------------
say "Gecmis veri"
HIST="$TRADER_DIR/var/history"
if [ -z "$(find "$HIST" -maxdepth 1 -name '*.feather' -print -quit 2>/dev/null)" ]; then
  echo "Veri yok; Binance acik arsivinden indiriliyor (yavas olabilir, sunucuyu yormaz)."
  systemd-run --quiet --wait --collect --unit=trader-fetch -p User="$TRADER_USER" -p Nice=15 -p MemoryMax=450M -p Slice=trader.slice \
    -p WorkingDirectory="$TRADER_DIR" "$TRADER_DIR/.venv/bin/python" "$TRADER_DIR/scripts/fetch_binance_vision.py" --workers 2 \
    || echo "UYARI: veri indirme tamamlanamadi; install.sh'i yeniden calistirirsaniz kaldigi yerden devam eder."
else
  echo "Veri zaten var, atlandi."
fi

# ---- 10. servisleri baslat --------------------------------------------------------
say "Servisler"
# DD-12 WP-07: ikiz kaldirma. Ikiz birimleri durdurulur ve devre disi birakilir; var/twin SILINMEZ, var/arsiv/twin-<tarih>/ altina tasinir (tekrar calistirmada no-op).
# DD-12 WP-06a: LLM veto kagit botta kaldirildi. Veto birimleri durdurulur/devre disi birakilir ve birim dosyalari silinir
# (/etc/trader-veto.env'e dokunulmaz; shared/veto/ okunmaz). Tekrar calistirmada no-op.
for u in trader-veto.timer trader-veto.service; do
  systemctl disable --now "$u" >/dev/null 2>&1 || true
done
rm -f "${UNIT_DIR}/trader-veto.service" "${UNIT_DIR}/trader-veto.timer"
for u in trader-engine@twin.service trader-engine-retry@twin.timer trader-counterfactual@twin.timer trader-drift@twin.timer trader-exit-counterfactual@twin.timer; do
  systemctl disable --now "$u" >/dev/null 2>&1 || true
done
if [ -d "$TRADER_DIR/var/twin" ]; then
  safe_tree_path "$TRADER_DIR/var/twin" "$TRADER_DIR/var/arsiv"
  TWIN_ARCH="$TRADER_DIR/var/arsiv/twin-$(date -u +%Y%m%d)"
  install -d -m 0750 -o "$TRADER_USER" -g "$TRADER_USER" "$TRADER_DIR/var/arsiv"
  [ -e "$TWIN_ARCH" ] && TWIN_ARCH="${TWIN_ARCH}-$(date -u +%H%M%S)"
  mv "$TRADER_DIR/var/twin" "$TWIN_ARCH" && echo "Ikiz verisi arsive tasindi (silinmedi): $TWIN_ARCH"
fi
# CT/C1 ayriligi (docs/motor/ct-ayrilik-spec.md): CT kadro okuyucu kaldirildi. Birimler durdurulur, devre disi birakilir, dosyalari silinir
# (tekrar calistirmada no-op). C1 verisi tek seferlik temizlenir (isaret dosyasi var/c1_temizle_v2.done; defter dosyasina DOKUNULMAZ).
for u in trader-ct-kadro.timer trader-ct-kadro.service; do
  systemctl disable --now "$u" >/dev/null 2>&1 || true
done
rm -f "${UNIT_DIR}/trader-ct-kadro.service" "${UNIT_DIR}/trader-ct-kadro.timer"
# C1 defter/state gocu (docs/motor/ct-ayrilik-spec.md bolum 5): motor DURDURULUR, goc yedekli ve dogrulamali calisir (hata halinde yedekten
# geri yuklenir, isaret yazilmaz), basariliysa yedek silinir ve var/durum/c1_goc_raporu.json yazilir. Acik C1 pozisyonu varsa goc
# REDDEDILIR (hicbir sey degismez): motor yeni kodla baslar, acilista C1'i piyasadan kapatir; kapaninca (en cok ~15 dk) goc yeniden denenir.
c1_acik_sayisi() { # state.sqlite'ta kapanmamis C1 pozisyonu (salt okunur); okunamazsa 0
  as_trader /usr/bin/python3 -I -c "import sqlite3,sys; c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True); print(c.execute(\"SELECT COUNT(*) FROM positions WHERE setup='C1' AND status!='closed'\").fetchone()[0])" "$TRADER_DIR/var/learner/state.sqlite" 2>/dev/null || echo 0
}
c1_goc_dene() { # motoru durdurur, gocu calistirir; basariliysa 0
  systemctl stop trader-engine@learner.service trader-engine-retry@learner.timer trader-notes.service trader-lesson.service >/dev/null 2>&1 || true
  systemctl start trader-c1-goc.service >/dev/null 2>&1 || true
  [ -e "$TRADER_DIR/var/c1_goc.done" ]
}
if [ ! -e "$TRADER_DIR/var/c1_goc.done" ] && [ -f "$TRADER_DIR/var/learner/state.sqlite" ] && [ -f "$TRADER_DIR/var/learner/ledger.sqlite" ]; then
  if [ "$LIVE" -eq 1 ] && systemctl is-active --quiet trader-engine@learner.service 2>/dev/null; then
    echo "UYARI: C1 gocu ertelendi: canli kipte kagit learner calisiyor (durdurulmadan goc yapilmaz)"
  else
    say "C1 gocu"
    safe_tree_path "$TRADER_DIR/var" "$TRADER_DIR/var/durum"
    if c1_goc_dene; then
      echo "C1 gocu tamamlandi (rapor: var/durum/c1_goc_raporu.json)"
    elif [ "$(systemctl show -p ExecMainStatus --value trader-c1-goc.service 2>/dev/null)" = "3" ]; then
      echo "C1 gocu ertelendi: acik C1 pozisyonu var; motor baslatilip C1 piyasadan kapatilacak"
      systemctl start trader-feed.service trader-engine@learner.service >/dev/null 2>&1 || true
      for _ in $(seq 1 30); do
        sleep 30
        [ "$(c1_acik_sayisi)" = "0" ] && break
      done
      if [ "$(c1_acik_sayisi)" = "0" ] && c1_goc_dene; then
        echo "C1 gocu tamamlandi (rapor: var/durum/c1_goc_raporu.json)"
      else
        echo "UYARI: C1 gocu tamamlanamadi (acik C1 pozisyonu kapanmadi ya da goc reddedildi); sonraki kurulumda yeniden denenir"
        MISSING+=("C1 gocu bekliyor: acik C1 pozisyonu kapaninca 'systemctl stop trader-engine@learner; systemctl start trader-c1-goc; systemctl start trader-engine@learner' (ya da install.sh'i yeniden calistirin)")
      fi
    else
      echo "CRIT: C1 gocu BASARISIZ; yedekten geri yuklendi, isaret yazilmadi (journalctl -u trader-c1-goc; Telegram'a da bildirildi). Sonraki kurulumda yeniden denenir."
      MISSING+=("C1 gocu basarisiz oldu (veri yedekten geri yuklendi): journalctl -u trader-c1-goc")
    fi
  fi
fi
if [ ! -e "$TRADER_DIR/var/c1_temizle_v2.done" ]; then
  safe_tree_path "$TRADER_DIR/var"
  if as_trader /usr/bin/python3 -I "$REL_DIR/scripts/c1_temizle.py" --var-dir "$TRADER_DIR/var" --saglik-durum /var/lib/trader-health/state.json; then
    echo "C1 temizligi tamamlandi"
  else
    echo "UYARI: C1 temizligi tamamlanamadi (isaret yazilmadi; sonraki kurulumda yeniden denenir)"
  fi
fi
LIVE_WARN=""
# kod degistiyse yeniden baslatilacak, su an CALISAN motor birimleri (enable_now'dan once alinir; yeni acilanlar zaten yeni kodla baslar)
ACTIVE_ENGINES=""
if [ "$CODE_CHANGED" -eq 1 ]; then
  ACTIVE_ENGINES="$(systemctl list-units 'trader-engine@*.service' 'trader-engine-testnet.service' 'trader-engine-live.service' --state=active --no-legend --plain 2>/dev/null | awk '{print $1}' | grep -v '@twin\.' || true)"
fi
enable_now() { systemctl enable --now "$1" >/dev/null 2>&1 && echo "Etkin: $1" || echo "UYARI: $1 baslatilamadi (systemctl status $1)"; }

enable_now trader-feed.service     # veri akisi once: motor kural + taze veri gormeden baslamaz (acilis kapisi)
if [ "$LIVE" -eq 1 ]; then
  # canli kip: kagit learner ETKINLESTIRILMEZ; hala etkinse DURDURULMAZ (canliya gecis listesine gore elle durdurulur)
  if systemctl is-active --quiet trader-engine@learner.service 2>/dev/null; then
    LIVE_WARN="kagit learner calisiyor; canliya gecis listesine gore durdurun (KILL ile duzlayip: systemctl disable --now trader-engine@learner trader-engine-retry@learner.timer)"
  fi
  echo "Canli kip: kagit learner (trader-engine@learner) etkinlestirilmedi."
else
  enable_now trader-engine@learner.service
fi
enable_now trader-health.timer
if [ "$LIVE" -eq 0 ]; then enable_now trader-engine-retry@learner.timer; fi   # acilis kapisi (cikis 7) yeniden deneme: besleme saglikliyse, saatte en fazla 6
enable_now trader-backup.timer
enable_now trader-oi.timer   # ML-G7: OI/long-short orani toplayici (5 dk; salt okunur Binance uclari, anahtar yok); var/market.sqlite positioning_5m
drift_first_run() { # var/<bot> dizinini hazirla ve ilk olcumu hemen al (yoksa saglik 20:20'ye kadar yanlis drift_missing der)
  safe_tree_path "$TRADER_DIR/var/$1"
  install -d -o "$TRADER_USER" -g "$TRADER_USER" "$TRADER_DIR/var/$1"
  systemctl start "trader-drift@$1.service" || true
}
enable_now trader-drift@learner.timer; drift_first_run learner   # gunluk sapma izleyicisi (WP-2; 20:20 TSI, salt okunur; var/<bot>/drift.json tek yazar; Telegram'a mesaj atmaz)
enable_now trader-counterfactual@learner.timer   # alinmayan sinyal gece isi (23:10 UTC); defter/market salt okunur, var/<bot>/counterfactual.sqlite tek yazar
enable_now trader-exit-counterfactual@learner.timer   # cikis karsi-olgusu gece isi (23:40 UTC; plan 25c); defter/market salt okunur, var/<bot>/exit_counterfactual.sqlite tek yazar; yalniz kanit (ders menusune bilgi)
enable_now trader-panel.service   # salt okunur pano: yalniz 127.0.0.1:8787, anahtar gerekmez

# Kurulum isareti (docs/sunucu-kurulum.md 'Kurulum sonrasi koruma'): kod degistiyse motorlar yeniden baslamadan ONCE yazilir.
# Okuyanlar: saglik (ilk 15 dk yalniz olumcul uyari), trader-kurulum-gozcu (20 dk oz-kontrol, 60 dk izleme + otomatik geri alma).
# tur: oto (oto_guncelle.sh) | elle | geri-al (trader-geri-al; izlenmez, dongu olmaz). onceki: geri alinacak surum.
OTO_STATE_DIR="/var/lib/trader-oto-guncelle"
if [ "$CODE_CHANGED" -eq 1 ]; then
  safe_tree_path "$OTO_STATE_DIR"
  install -d -m 0700 -o root -g root "$OTO_STATE_DIR"
  KURULUM_TMP="${OTO_STATE_DIR}/kurulum.json.tmp"
  KURULUM_AT="$(date -u +%FT%TZ)"
  printf '{"at":"%s","commit":"%s","onceki":"%s","tur":"%s"}\n' "$KURULUM_AT" "$COMMIT" "$PREV_COMMIT" "${OTO_KURULUM_TUR:-elle}" > "$KURULUM_TMP"
  chmod 0644 "$KURULUM_TMP"
  mv -f "$KURULUM_TMP" "${OTO_STATE_DIR}/kurulum.json"
  rm -f "${OTO_STATE_DIR}/gozcu.json"   # onceki kurulumun izleme sayaclari yeni kuruluma tasinmaz
fi

# WP-3: motor (yazar) yeni kodla yeniden baslar => defter sema gocu motor icinde, premigrate yedegiyle olur
if [ "$CODE_CHANGED" -eq 1 ]; then
  # besleme (feed) once yeniden baslar: motor yeni 44-parite konfigurasyonunu feed'den alir
  if systemctl is-active --quiet trader-feed.service 2>/dev/null; then
    systemctl restart trader-feed.service >/dev/null 2>&1 && echo "Yeniden baslatildi: trader-feed.service (kod degisti)" || echo "UYARI: trader-feed.service yeniden baslatilamadi (systemctl status trader-feed.service)"
  fi
fi
if [ "$CODE_CHANGED" -eq 1 ] && systemctl is-active --quiet trader-panel.service 2>/dev/null; then   # pano statik dosyalari acilista okur
  systemctl restart trader-panel.service >/dev/null 2>&1 && echo "Yeniden baslatildi: trader-panel.service (kod degisti)" || echo "UYARI: trader-panel.service yeniden baslatilamadi."
fi
if [ "$CODE_CHANGED" -eq 1 ] && [ -n "$ACTIVE_ENGINES" ]; then
  say "Kod degisti: calisan motorlar yeniden baslatiliyor (defter sema gocu motor icinde yapilir)"
  for u in $ACTIVE_ENGINES; do
    systemctl restart "$u" >/dev/null 2>&1 && echo "Yeniden baslatildi: $u" || echo "UYARI: $u yeniden baslatilamadi (systemctl status $u)"
  done
fi

TG_OK=0
if has_value /etc/trader-telegram.env TELEGRAM_BOT_TOKEN && has_value /etc/trader-telegram.env TELEGRAM_CHAT_ID; then
  TG_OK=1
  enable_now trader-telegram.service
  if [ "$CODE_CHANGED" -eq 1 ] && systemctl is-active --quiet trader-telegram.service 2>/dev/null; then   # yeni kod (ornegin /devam duzeltmesi) devreye girsin
    systemctl restart trader-telegram.service >/dev/null 2>&1 && echo "Yeniden baslatildi: trader-telegram.service (kod degisti)" || echo "UYARI: trader-telegram.service yeniden baslatilamadi."
  fi
  enable_now trader-telegram-report.timer
  # saglik uyarilari Telegram'a: anahtarlar tamam oldugunda NOTIFIER=auto zaten telegram'i secer (ornek dosyada auto); log kalmissa auto yap
  sed -i 's#^NOTIFIER=log$#NOTIFIER=auto#' /etc/trader-health.env
else MISSING+=("/etc/trader-telegram.env -> TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID (Telegram)"); fi
# ders: Anthropic anahtari VE Telegram anahtarlari (config/lesson.json notifier=telegram; bildirimcisiz cikis 1)
if has_value /etc/trader-lesson.env ANTHROPIC_API_KEY_LESSON && [ "$TG_OK" -eq 1 ]; then
  enable_now trader-lesson.timer
else MISSING+=("/etc/trader-lesson.env  -> ANTHROPIC_API_KEY_LESSON ve Telegram anahtarlari (ders servisi; ikisi de dolu olmadan acilmaz)"); fi
# DD-12 WP-09: gece islem notu (kodla; anahtar/ag gerekmez) ve haftalik ozet (anahtar yoksa no-op; butce payi haftalik_ozet)
enable_now trader-notes.timer
enable_now trader-ml-retrain.timer
# DD-12 WP-16: unit ReadWritePaths (namespace) icin dizin ilk kurulumda olussun; birim ilk calismadan once vardir
safe_tree_path "$TRADER_DIR/var/universe"
install -d -m 0750 -o "$TRADER_USER" -g "$TRADER_USER" "$TRADER_DIR/var/universe"
enable_now trader-universe.timer   # DD-12 WP-16: aylik kagit evreni (1. gun 00:30 UTC; var/universe/paper_pairs.json, ag yok)
# Etiket/kural mekanizmasi 21 Kasim 2026'da KALDIRILDI ve geri gelmedi. Yeniden eklenen YALNIZ VERI TOPLAMA (23 Kasim 2026 karari; docs/veri-toplama-spec.md):
# karar girdisi degildir; golge/ust lig hatti icin ham veri biriktirir. Eski birimler (var/durum/haber_v1.json yazani) yerini yenisine birakir.
safe_tree_path "$TRADER_DIR/var/veri" "$TRADER_DIR/var/veri/haber" "$TRADER_DIR/var/veri/piyasa"
install -d -m 0750 -o "$TRADER_USER" -g "$TRADER_USER" "$TRADER_DIR/var/veri" "$TRADER_DIR/var/veri/haber" "$TRADER_DIR/var/veri/piyasa"
safe_tree_path "$TRADER_DIR/var/durum"
install -d -m 0750 -o "$TRADER_USER" -g "$TRADER_USER" "$TRADER_DIR/var/durum"
enable_now trader-haber.timer          # veri toplama: ham haber + Fear&Greed (saatlik; var/veri/haber; yalniz https okuma)
enable_now trader-piyasa-veri.timer    # veri toplama: OI/funding/long-short/taker (saatlik; var/veri/piyasa; herkese acik GET, anahtar yok)
# Haber sinyali (ust lig §1; saatlik :08; MemoryMax=150M): ham haberi Haiku 5.5 ile puanlar, YALNIZ var/learner/sinyal/haber_sinyal.json yazar.
# Anahtar ANTHROPIC_API_KEY_HABER (/etc/trader-lesson.env) yoksa dosya yenilenmez (zarari yok); yine de bildir.
safe_tree_path "$TRADER_DIR/var/learner" "$TRADER_DIR/var/learner/sinyal"
install -d -m 0750 -o "$TRADER_USER" -g "$TRADER_USER" "$TRADER_DIR/var/learner" "$TRADER_DIR/var/learner/sinyal"
enable_now trader-haber-sinyal.timer
if ! has_value /etc/trader-lesson.env ANTHROPIC_API_KEY_HABER; then MISSING+=("/etc/trader-lesson.env  -> ANTHROPIC_API_KEY_HABER (haber sinyali; yoksa var/learner/sinyal/haber_sinyal.json yenilenmez)"); fi
enable_now trader-weekly-summary.timer
enable_now trader-weekly-collect.timer   # haftalik ozet + tur 1 yorumu batch sonuclarini toplar (3 saatte bir; bekleyen yoksa no-op; 24.11 Batch karari)
# Faz 2a: kagit-geri test tutarlilik raporu (haftalik; yalniz bilgi). unit ReadWritePaths (namespace) icin dizinler ilk kurulumda olussun
safe_tree_path "$TRADER_DIR/var/rapor" "$TRADER_DIR/var/rapor/tutarlilik" "$TRADER_DIR/var/durum"
install -d -m 0750 -o "$TRADER_USER" -g "$TRADER_USER" "$TRADER_DIR/var/rapor" "$TRADER_DIR/var/rapor/tutarlilik" "$TRADER_DIR/var/durum"
enable_now trader-tutarlilik.timer
# Islem mutabakati (motor = panel = Telegram; gunluk 04:40 UTC + her kurulum sonrasi; yalniz bilgi). Cikti var/durum (yukarida olusur);
# outbox yazimi icin var/telegram da unit ReadWritePaths'inde (yoksa '-' ile atlanir)
enable_now trader-mutabakat.timer
# Tur 1 olcum raporu (gunluk 05:10 UTC, gece islerinden sonra; yalniz bilgi, botu degistirmez). Cikti var/durum; durum-yayin ml/ altina yayimlar
enable_now trader-tur1-olcum.timer
# Tur 1 haftalik YZ yorumu (pazar 06:00 UTC; YETKISI YOK, yalniz Telegram). Butce payi haftalik_ozet; anahtar ANTHROPIC_API_KEY_HAFTALIK_OZET yoksa sessizce atlar
enable_now trader-tur1-haftalik.timer
# YZ yorumcu (ust lig §3; gunluk 05:40 UTC; YETKISI YOK). unit ReadWritePaths (namespace) icin var/durum/yorumcu ilk kurulumda olussun.
# Anahtar ANTHROPIC_API_KEY_YORUMCU (/etc/trader-lesson.env) yoksa servis "bugun rapor yok" dosyasi yazar (zarari yok); yine de bildir
safe_tree_path "$TRADER_DIR/var/durum" "$TRADER_DIR/var/durum/yorumcu"
install -d -m 0750 -o "$TRADER_USER" -g "$TRADER_USER" "$TRADER_DIR/var/durum/yorumcu"
enable_now trader-yorumcu.timer
if ! has_value /etc/trader-lesson.env ANTHROPIC_API_KEY_YORUMCU; then MISSING+=("/etc/trader-lesson.env  -> ANTHROPIC_API_KEY_YORUMCU (YZ yorumcu; yoksa gunluk rapor 'bugun rapor yok' yazar)"); fi
# Canli durum yayini (saatlik; repo dali canli-durum, klasor ml/): yalniz SSH deploy anahtariyla; anahtar yoksa birim sessizce atlar.
# Anahtar/known_hosts yeri: /var/lib/trader-durum-yayin/.ssh (StateDirectory). Kurulum adimlari: docs/sunucu-kurulum.md 'Canli durum dali'
enable_now trader-durum-yayin.timer
# Haftalik disk bakimi (sqlite WAL checkpoint/VACUUM + eski cikti temizligi; izin listesi). unit ReadWritePaths (var) zaten yukarida olusur
enable_now trader-bakim.timer
enable_now trader-strateji-veri.timer   # strateji verisi raporu 6 saatte bir yenilenir (Telegram belgesi yalniz ilk kez)
# Otomatik guncelleme (docs/motor/oto-guncelleme-spec.md): komutlar root sahipli surum dizininden; durum dizini root 0700.
safe_tree_path "$OTO_STATE_DIR"
install -d -m 0700 -o root -g root "$OTO_STATE_DIR"
for c in trader-geri-al trader-oto-ac trader-oto-simdi; do
  safe_tree_path "/usr/local/sbin/$c"
  install -m 0755 -o root -g root "$REL_DIR/deploy/$c" "/usr/local/sbin/$c"
done
enable_now trader-oto-guncelle.timer   # 5 dakikada bir (24.11: sabit saat yok); yalniz GitHub'da yesil testli commit kurulur, canli birim varsa dokunmaz
enable_now trader-kurulum-gozcu.timer  # kurulum sonrasi 20 dk oz-kontrol (yalniz sorunda mesaj) + 60 dk izleme/otomatik geri alma (kurulum.json yoksa bosta calisir)
# Saglik birimi HEARTBEAT_URL (https) olmadan her turda cikis 1 ile coker (zorunlu ortam degiskeni): bos birakilirsa uyar
if ! has_value /etc/trader-health.env HEARTBEAT_URL; then
  MISSING+=("/etc/trader-health.env   -> HEARTBEAT_URL (https:// dis nabiz adresi; ZORUNLU: bos iken trader-health her 5 dk basarisiz olur)"); fi

# Panel yayini: Cloudflare anahtarlari yer tutucuyken zamanlayici ACILMAZ
CF_TODO=()
if has_value /etc/trader-panel-cf.env CLOUDFLARE_API_TOKEN && has_value /etc/trader-panel-cf.env CLOUDFLARE_ACCOUNT_ID; then
  enable_now trader-panel-publish.timer
else
  CF_TODO+=("Cloudflare'da API token olusturun (Workers duzenleme yetkisi: 'Edit Cloudflare Workers' sablonu); token ve hesap kimligini /etc/trader-panel-cf.env dosyasina nano ile yazin (sohbete yazmayin)")
  CF_TODO+=("Worker'i bir kez olusturun (pano kilitsiz, yalniz okuma; 20 Kasim kullanici karari): systemctl start trader-panel-publish.service")
  CF_TODO+=("Yayini acin: systemctl enable --now trader-panel-publish.timer (ya da install.sh'i yeniden calistirin); workers.dev adresini yer imine ekleyin")
fi

# ---- canli birim (LIVE=1): on denetim -> enable (--now YOK: motor BASLATILMAZ) ---------------------------------------------
if [ "$LIVE" -eq 1 ]; then
  say "Canli birim: on denetim"
  if ! "$ROOT_DIR/venv/bin/python" -I "$ROOT_DIR/current/scripts/live_preflight.py" --config-dir "$TRADER_DIR/config"; then
    fail "Canli on denetim basarisiz (yukaridaki FAIL satirlari); canli birim ETKINLESTIRILMEDI."
  fi
  systemctl enable trader-engine-live.service >/dev/null 2>&1 || fail "trader-engine-live.service etkinlestirilemedi (systemctl status trader-engine-live)."
  echo "Canli birim etkinlestirildi (BASLATILMADI): baslatma canliya gecis gunu listesiyle, elle."
  systemctl enable --now trader-engine-env-retry@live.timer >/dev/null 2>&1 || echo "UYARI: canli yeniden deneme zamanlayicisi etkinlestirilemedi."
  if [ "$TG_OK" -eq 1 ]; then   # Telegram env'i degisti: daemon yeni yollarla yeniden baslar
    systemctl restart trader-telegram.service >/dev/null 2>&1 && echo "Yeniden baslatildi: trader-telegram.service" || echo "UYARI: trader-telegram.service yeniden baslatilamadi."
  fi
fi

# Testnet golge motoru (WP-B8): BINANCE_API_KEY ve BINANCE_API_SECRET ikisi de doluysa acilir (gercek para yok; yalniz testnet.binancefuture.com)
if has_value /etc/trader-testnet.env BINANCE_API_KEY && has_value /etc/trader-testnet.env BINANCE_API_SECRET; then
  # saglik denetcisi golge motoru da izler (stopsuz pozisyon / borsa erisimi); kullanici degeri korunur
  grep -q '^HEALTH_SHADOW_VAR_DIR=' /etc/trader-health.env || echo "HEALTH_SHADOW_VAR_DIR=" >> /etc/trader-health.env
  sed -i "s#^HEALTH_SHADOW_VAR_DIR=\$#HEALTH_SHADOW_VAR_DIR=${TRADER_DIR}/var-testnet#" /etc/trader-health.env
  # testnet sermaye kaydi (bos ise, borsadan okunan testnet bakiyesiyle; var olana dokunmaz). Hata kurulumu durdurmaz.
  TN_WAS_ACTIVE=0; systemctl is-active --quiet trader-engine-testnet.service 2>/dev/null && TN_WAS_ACTIVE=1
  # shellcheck disable=SC1091
  if TN_OUT="$( set -a; . /etc/trader-testnet.env; set +a; cd "$TRADER_DIR" && PYTHONPATH="$TRADER_DIR/src" runuser -u "$TRADER_USER" -m -- python3 -m trader_engine capital init-from-exchange --bot learner --env testnet --by kurulum.testnet --config-dir config 2>&1 )"; then
    echo "$TN_OUT" | sed 's/^/  /'
    if [ "$TN_WAS_ACTIVE" -eq 1 ] && printf '%s' "$TN_OUT" | grep -q '^yazildi:'; then
      systemctl restart trader-engine-testnet.service >/dev/null 2>&1 && echo "Yeniden baslatildi: trader-engine-testnet.service (sermaye kaydi alindi)" || echo "UYARI: trader-engine-testnet.service yeniden baslatilamadi."
    fi
  else
    echo "$TN_OUT" | sed 's/^/  /'
    TESTNET_CAPITAL_WARN="testnet sermaye kaydi yazilamadi (borsa bakiyesi okunamadi): elle: python3 -m trader_engine capital init-from-exchange --bot learner --env testnet --by kurulum.testnet"
    echo "UYARI: $TESTNET_CAPITAL_WARN"
  fi
  enable_now trader-engine-testnet.service
  enable_now trader-engine-env-retry@testnet.timer   # acilis kapisi (cikis 7) yeniden deneme: testnet birimi icin (DD-9 §2.3)
else MISSING+=("/etc/trader-testnet.env  -> BINANCE_API_KEY ve BINANCE_API_SECRET (Binance Futures TESTNET anahtari; testnet golge motoru, ikisi de dolu olmadan acilmaz)"); fi

# ---- 11. ozet ---------------------------------------------------------------------
# DD-12 WP-18: kâgit kapanis denetimi (yalniz UYARI; kurulumu durdurmaz). DD-12 zamanlayicilari etkin olmali; veto ve ikiz
# birimleri kalmamali (kaldirma yukarida yapildi; eski bir kopya kaldiysa burada gorunur).
say "DD-12 zamanlayici denetimi"
for t in trader-notes.timer trader-weekly-summary.timer trader-ml-retrain.timer trader-universe.timer \
         trader-counterfactual@learner.timer trader-exit-counterfactual@learner.timer trader-tutarlilik.timer trader-mutabakat.timer trader-tur1-olcum.timer trader-tur1-haftalik.timer trader-weekly-collect.timer trader-yorumcu.timer trader-durum-yayin.timer trader-haber.timer trader-haber-sinyal.timer trader-piyasa-veri.timer trader-bakim.timer trader-strateji-veri.timer; do
  if systemctl is-enabled --quiet "$t" 2>/dev/null; then echo "  etkin: $t"; else echo "UYARI: $t etkin degil (systemctl enable --now $t)"; fi
done
for u in trader-veto.service trader-veto.timer trader-engine@twin.service trader-engine-retry@twin.timer; do
  if [ -e "${UNIT_DIR}/$u" ]; then echo "UYARI: eski birim duruyor: $u (install.sh'i yeniden calistirin veya elle kaldirin)"; fi
done
say "OZET"
echo "Calisan Trader birimleri:"
systemctl list-units 'trader-*' --no-legend --plain 2>/dev/null | awk '{print "  " $1 "  " $3 "/" $4}' || true
echo
echo "Bellek:"
free -m | awk 'NR==1 || /Mem:|Swap:/ {print "  " $0}'
echo
# Kurulum basariyla bitti: surum sabitlemesi yazilir (sir degil; sonraki kurulumlar ve on denetim okur)
printf 'COMMIT=%s\n' "$COMMIT" > "${RELEASE_FILE}.tmp"
chmod 0644 "${RELEASE_FILE}.tmp"
mv -f "${RELEASE_FILE}.tmp" "$RELEASE_FILE"
echo "Surum: ${COMMIT} (${RELEASE_FILE})"
# Islem mutabakati bir kez de kurulum/yeniden baslatmalardan SONRA calissin (kosan birimler yeni kodla; yalniz bilgi, kurulumu durdurmaz). Surum kimligi /etc/trader-release'ten okunur:
# bu yuzden surum dosyasi yazildiktan SONRA baslatilir (yoksa eski commit okunur ve ozet bir tur gecikir)
if [ -e "${UNIT_DIR}/trader-mutabakat.service" ]; then
  if systemctl start --no-block trader-mutabakat.service >/dev/null 2>&1; then echo "Baslatildi: trader-mutabakat.service (kurulum sonrasi)"; else echo "UYARI: trader-mutabakat.service baslatilamadi (kurulum devam ediyor)."; fi
fi
# Strateji verisi (beyin firtinasi): sessiz tek Telegram belgesi; birim kendi isaret dosyasiyla (var/durum/strateji_veri_gonderildi.json) bir kez gonderir. Salt okunur, kurulumu durdurmaz:
if [ -e "${UNIT_DIR}/trader-strateji-veri.service" ]; then
  if systemctl start --no-block trader-strateji-veri.service >/dev/null 2>&1; then echo "Baslatildi: trader-strateji-veri.service (kurulum sonrasi, tek seferlik)"; else echo "UYARI: trader-strateji-veri.service baslatilamadi (kurulum devam ediyor)."; fi
fi
if [ -n "$LIVE_WARN" ]; then echo "UYARI: $LIVE_WARN"; fi
if [ "$NO_LIVE" -eq 1 ]; then echo "UYARI (--no-live): /etc/trader-telegram.env, /etc/trader-health.env (LIVE_BOTS, LIVE_VAR_DIR, LIVE_PAUSE_FILE, KILL_FILE, ENGINE_STATUS_PATH, LEDGER_PATH, LADDER_BOTS) ve /etc/trader-lesson.env (LEDGER_PATH) hala CANLI yollari tasiyor olabilir; elle kagit degerlerine alin."; fi
if [ "$LIVE" -eq 1 ]; then echo "CANLI birim kuruldu ve etkin ama BASLATILMADI (systemctl start trader-engine-live yalniz canliya gecis gunu listesiyle)."; fi
if [ -n "${TESTNET_CAPITAL_WARN:-}" ]; then
  echo "YAPILACAKLAR (testnet sermaye kaydi):"; echo "  - $TESTNET_CAPITAL_WARN"
fi
if [ "${#MISSING[@]}" -gt 0 ]; then
  echo "YAPILACAKLAR (anahtarlar doldurulmadan bu zamanlayicilar KAPALI birakildi):"
  for m in "${MISSING[@]}"; do echo "  - $m"; done
  echo "  Doldurduktan sonra bu komutu tekrar calistirin: COMMIT=<KOD> bash $ROOT_DIR/current/deploy/install.sh"
  echo "  (Anahtarlari sohbete yazmayin; dosyayi nano ile acip degeri yapistirin.)"
fi
if [ "${#CF_TODO[@]}" -gt 0 ]; then
  echo
  echo "PANO YAYINI (Cloudflare) icin siradaki adimlar (zamanlayici bunlar bitene kadar KAPALI):"
  for m in "${CF_TODO[@]}"; do echo "  - $m"; done
  echo "  Sonra: COMMIT=<KOD> bash $ROOT_DIR/current/deploy/install.sh   (zamanlayiciyi kendisi acar)"
fi
echo
echo "Pano (telefon/bilgisayar): ssh -L 8787:127.0.0.1:8787 <kullanici>@<sunucu>  sonra tarayicida http://127.0.0.1:8787"
echo "Durum: systemctl status trader-engine@learner   |   Kayit: journalctl -u trader-engine@learner -n 50"
echo "Kurulum bitti."
