# 12 — Risk kademe denetimi (RK-1 şartnamesi v1.1, 17 Kasım 2026 — mentor)

> **v1.1 (mentor kararı, RK-1 incelemesi sonrası):** (1) §5 bulgu çıkış kodu **5** (`EXIT_FINDINGS`; 4 = `EXIT_ENGINE` ile çakışıyordu). (2) §7 uyuşmazlık kuralı: borsa tarafı zorunlu küme = tam 7 günlük pencere, günlük tarafı 5 gün; **yapışkan mandal** (süre aşımı tek başına uyuşmazlığı kaldırmaz). (3) §8.2 adım 3 metni düzeltildi (gerçekleme zaten doğruydu). (4) §12'ye günlükte yarım son satır onarım satırı eklendi. (5) Tutuş yazılamazsa / stop satırı yazılamazsa kapı `ladder_invalid` (§8.2 adım 3) ve Telegram `/kademe_devam` blok-durum uyuşmazlığında ret 5 (§9) — gerçekleme güvenlik sıkılaştırmaları.

Kaynak kararlar: `otonom-trading-arastirma/risk-kademe-kurali.md` (v1; özellikle §2, §4, §5, §9); `tasarim-kararlari.md` 17 Kasım "Risk kademe kuralı taslağı" ve "Canlı başlangıç tutarı" (canlı 250–300 USD ile başlar; 3–4 hafta ya da 40–50 işlem sonra 1000 USD'ye tamamlanır; risk %0,5; bu dönemin işlemleri basamak sayaçlarına **girer**; −%20 durma ve %60 taban **yatırılan tutara göre** ölçülür); `11-canli-broker.md` §9 (`EntryPause`, `drawdown_review`, "motor asla kaldırmaz"), §9.4 (bu belgeye bırakılan iş), §13 satır "RK-1 (asgari)". Bağımlılıklar: `05` (`EntryGate`, `Engine`, `StatusWriter`), `11` WP-B2/B3/B6, `docs/risk-kilidi-spec.md` (`LOCKED_CFG`, `tightened`), `docs/telegram-spec.md` (iki adımlı kod), `docs/saglik-spec.md`.

**Okuyana not.** Bu belge kural belgesinin (taslak) koda bağlanan **asgari** kısmıdır: sermaye kaydı, düşüş ölçümü, otomatik iniş, −%20 durma, %60 taban, kullanıcı onaylı devam, durum ve alarmlar. Basamak **artışı** (K0'ın üstü), kural belgesi §3 koşul 4–6 ve §4 tetik 4–8 bu belgede **yoktur** (§15; RK-1b, en geç şubat sonu). RK-1 bitene kadar K0'ın üstüne çıkmanın kod yolu yoktur; bu güvenli taraftır.

- **[V-8]** (doğrulanmamış borsa varsayımı, 11'deki [V-n] dizisinin devamı) `GET /fapi/v1/income?incomeType=TRANSFER` sembolsüz çağrıldığında alt hesabın vadeli cüzdanına giren/çıkan her aktarımı döner: `income` işaretli tutar (giriş +), `asset`, `time` (ms), `tranId`. Doğrulama: duman testi sonrası ilk gerçek yatırma (§12 D-4). Çürürse §7 mentor onayıyla revize edilir; gerçekleyen ajan denetimi sessizce kapatmaz.

## 1. Kararlar (özet)

| Konu | Karar |
|---|---|
| Risk sabitleri | Basamak değerleri ve tüm eşikler **kod sabitidir**: `trader_core/risk_ladder.py`. `config/*.json`'a yazılmaz (kural belgesi §9 madde 1'deki `config/risk_ladder.json` **iptal**; risk sabiti tarayıcısı ve "kilit gevşetilemez" ilkesi). Yapılandırmada yalnız bir **yol** anahtarı vardır (`ladder_follow`) |
| Tek kayıt | Bot başına tek, yalnız eklenen, özet zincirli günlük: `var/<bot>/risk_ladder.jsonl`. Sermaye hareketleri (operatör), durma/iniş/tepe (motor) ve devam kararları (kullanıcı) aynı dosyadadır. Kademe durumu bu dosyanın **saf katlamasıdır** (`fold`); motorun `state.sqlite`'ında kademe durumu **tutulmaz** |
| Ölçü tabanları | `dep_net` = net yatırılan sermaye; `base` = durma tabanı (başta `dep_net`, devam kararında o anki özsermayeye çekilir); `peak` = tepe değer (yalnız otomatik iniş için) |
| −%20 durma | `equity ≤ 0,80 × base` → `drawdown_review` tutuşu (giriş kapalı, pozisyonlar stoplarıyla yaşar). **KILL değildir** |
| %60 taban | `equity ≤ 0,60 × dep_net` → `capital_floor` tutuşu (giriş kapalı, pozisyonlar stoplarıyla yaşar). Telegram'dan **açılamaz** |
| Otomatik iniş | Tepeden −%10 → bir basamak; −%15 → K−1 (K0 üstündeyse K0). Onay beklemez |
| K−1 (%0,35) | Yalnız `dep_net ≥ 1000` iken kullanılır. Küçük sermaye döneminde en alt basamak K0'dır (en küçük emir tutarı; mentor kararı) |
| Etkin risk | `min(cfg.target_trade_risk, STEPS[step])`; yalnız `tightened` ile; risk kilidinin diğer alanlarına dokunulmaz |
| Kipler | `backtest`: RK-1 yok (bit-bit aynı). `paper`: **zorlama (24.11; eski: gözlem)**. `testnet`/`live`: **zorlama** |
| Kim kaldırır | `drawdown_review`: yalnız kullanıcı — Telegram `/kademe_devam` (iki adımlı kod, en erken 24 saat sonra) ya da sunucuda CLI. `capital_floor`: yalnız sunucuda CLI + `tasarim-kararlari.md` karar referansı. Motor, ders servisi, ML, zamanlayıcı **hiçbirini** kaldıramaz |
| Sermaye hareketi | Operatör CLI ile girer; Telegram'dan girilmez. Canlıda borsanın aktarım kayıtlarıyla eşleştirilir; eşleşmeyen aktarım → giriş kapalı |
| Yanlış alarm koruması | Her tetik **art arda iki** değerlendirmede tutmalı (`CONFIRM_N = 2`) |
| Hata durumunda | Günlük yok/bozuk, özsermaye okunamıyor, aktarım doğrulanamıyor → giriş kapalı (fail-closed); çıkışlar ve stoplar etkilenmez |

## 2. DOSYA SAHİPLİĞİ

Yeni dosyalar (bu şartname sahibidir):

- `src/trader_core/risk_ladder.py` (WP-RK1) — sabitler, günlük okuma/yazma, `fold`, `evaluate`, `match_transfers`, `counters`, `step_config`. Saf Python (stdlib); `trader_engine` içe aktarmaz.
- `src/trader_engine/ladder.py` (WP-RK2) — `RiskLadder` (çalışma zamanı sarmalayıcısı).
- Testler: `tests/test_risk_ladder_spec.py`, `tests/engine/test_engine_ladder_spec.py`, `tests/test_telegram_ladder_spec.py`, `tests/test_health_ladder_spec.py` (bağımsız test ajanı); `tests/engine/test_engine_ladder_impl_smoke.py` (gerçekleme ajanı).

Değiştirilen dosyalar (yalnız burada sayılan kadar; ilgili belgeye "12 ile güncellendi" notu):

| Dosya | Değişiklik | WP |
|---|---|---|
| `trader_engine/pause.py` | `REASONS`'a `"capital_floor"`; `code()` önceliği: `capital_floor` → `drawdown_review` → `paused` | RK2 |
| `trader_engine/gates.py` | `EntryGate(..., ladder=None)`; `pre` içinde duraklatmadan sonra kademe kapısı; `check_entry` çağrısında `ladder.risk_config` (§8.3) | RK2 |
| `trader_engine/engine.py` | `ladder.tick` çağrıları (§8.2), `_live_gate_code` sırası, `status_fields()["risk_ladder"]` | RK2 |
| `trader_engine/status.py` | `risk_ladder` bloğu (§10) | RK2 |
| `trader_engine/config.py` | isteğe bağlı `ladder_follow: str \| None` (§8.4) | RK2 |
| `trader_engine/brokers/binance_futures.py` | `LiveBroker.transfers(since, until)` (§7) | RK2 |
| `trader_engine/cli.py` | `capital` ve `ladder` alt komutları (§5) | RK3 |
| `trader_core/telegram.py`, `scripts/telegram_run.py` | `/kademe`, `/kademe_devam`, rapor satırı, `build_ladders` (§9) | RK4 |
| `trader_core/health.py`, `scripts/health_run.py` | `ApiProbe.ladder`, §11 denetimleri | RK4 |
| `tests/engine/test_engine_module_inventory.py` | `ALLOWED_MODULES_B`'ye `ladder.py` | RK2 |
| `tests/engine/test_engine_dependency_direction.py` | `ladder.py` için izinli kenarlar (`trader_core.risk_ladder`, `trader_core.risk`; motor içi: `pause`, `clock`, `config`) | RK2 |
| `tests/engine/test_engine_no_risk_constants.py` | **değişmez**; yeni kod bu tarayıcıdan aynen geçmelidir | — |

## 3. Tanımlar ve sabitler (`trader_core/risk_ladder.py`)

```python
SCHEMA = "risk-ladder/1"
STEPS = {-1: 0.0035, 0: 0.005, 1: 0.0075, 2: 0.010, 3: 0.012, 4: 0.014}   # basamak -> hedef işlem riski
STEP_NAMES = {-1: "K-1", 0: "K0", 1: "K1", 2: "K2", 3: "K3", 4: "K4"}
START_STEP = 0
MAX_STEP_APPROVABLE = 0          # RK-1: step_up yalnız K-1 -> K0. RK-1b bu sabiti yükseltir
KM1_MIN_CAPITAL = 1000.0         # dep_net bunun altındaysa en alt basamak K0
DOWN_1_RATIO = 0.90              # equity <= 0.90 * peak  (tepeden -%10)
DOWN_2_RATIO = 0.85              # equity <= 0.85 * peak  (tepeden -%15)
STOP_RATIO = 0.80                # equity <= 0.80 * base  (-%20 durma)
FLOOR_RATIO = 0.60               # equity <= 0.60 * dep_net (son taban)
CAPITAL_LATCH_RATIO = 0.85       # equity <= 0.85 * dep_net -> capital_latch (yeni giriş mandalı)
NEAR_RATIO = 0.85                # equity <= 0.85 * base -> "eşiğe yaklaşıyor" uyarısı
CONFIRM_N = 2
EVAL_EVERY_S = 60.0
XFER_POLL_S = 120.0; XFER_STALE_S = 900.0; XFER_TOL = 1.0
XFER_WINDOW_S = 7 * 86400; XFER_MUST_S = 5 * 86400; XFER_PAIR_S = 48 * 3600
INIT_TOL_ABS = 2.0; INIT_TOL_REL = 0.02
RESUME_MIN_WAIT_S = 86400        # yalnız Telegram yolu
STATUS_FRESH_S = 120.0
STEP_UP_MIN_TRADES = 60; STEP_UP_MIN_DAYS = 42; STEP_UP_SINCE_DOWN_DAYS = 56
```

**Ana para kilidi (`capital_latch`, kullanıcı kararı).** `equity <= 0.85 × dep_net` (dep_net = başlangıç + yatırılan − çekilen) ardışık `CONFIRM_N` ölçümde sürerse yeni girişler kapanır (duraklatma tutuşu `capital_latch`); açık pozisyonlar ve stopları etkilenmez. TÜM kiplerde etkindir (paper dahil, `enforce`'tan bağımsız; paper'da dep_net = `wallet_start`), yeniden başlatmada kalır, yalnız kullanıcı kaldırır (Telegram `/devam` + 4 haneli kod ya da CLI). Kullanıcı kaldırdıktan sonra eşiğin altındayken yeniden kurulmaz; kasa eşiğin üstüne çıkıp yeniden inerse kurulur (yeniden başlatmada `pause_audit.jsonl`'daki son `capital_latch` satırı `remove` ise ve hâlâ eşikteyse silahsız başlar). Günlüğe yeni satır türü yazılmaz; −%20 kuralı (`STOP_RATIO`) aynen korunur (paper'da gözlem).

Değişmezler (test edilir): `STEPS[4] == LOCKED_CFG.target_trade_risk`; değerler basamakla kesin artan; `STEPS[0] == 0.005`.

- **Özsermaye (`equity`):** `broker.account().equity` (cüzdan + açık pozisyonların anlık kâr/zararı). Tüm kiplerde aynı kaynak.
- **`dep_net`:** yatırılanlar − sermayeden çekilenler (+ düzeltmeler). Kârdan çekilen para `dep_net`'i düşürmez (§4.3).
- **`base`:** durma tabanı. Başta `dep_net`; yatırma/çekme ile aynı tutarda değişir; devam kararında `min(base, equity)` olur.
- **`peak`:** tepe değer. Yeni UTC gününün ilk değerlendirmesindeki özsermaye `peak`'ten büyükse yükselir (süreç yeniden başlarsa ilk değerlendirme gün başı sayılır; bu yalnız sıkılaştırır). Yatırma `peak`'i aynı tutarda yükseltir.
- **Eşik karşılaştırması:** her yerde `equity <= round(RATIO * ref, 8)` (kapsayıcı). "Yüzde düşüş" yalnız gösterim içindir: `dd_base_pct = max(0, (base − equity) / base × 100)`, `dd_peak_pct` aynı biçimde.
- **En alt basamak:** `lowest(dep_net) = -1 if dep_net >= KM1_MIN_CAPITAL else 0`.

**Kural belgesinden bilinçli sapma:** taslak −%20'yi tepe değere göre yazmıştı (§10 madde 1 açık). 17 Kasım kullanıcı kararı "yatırılan tutara göre" dediği için durma **`base`'e**, taban **`dep_net`'e** bağlandı; tepe değer yalnız otomatik inişi sürer. Sonuç: kâr edilmiş hesapta tepeden −%20, girişi durdurmaz (en alt basamağa indirir ve uyarı verir). Bkz. §16 KULLANICI KARARI 1.

## 4. Kayıt günlüğü — veri modeli

### 4.1 Dosya

`var/<bot>/risk_ladder.jsonl` (`cfg.path("risk_ladder.jsonl")`). Satır başına bir JSON nesnesi, UTF-8, `\n`. Yalnız eklenir; hiçbir satır değiştirilmez/silinmez. Yazma: `f"{path}.lock"` üzerinde `flock(LOCK_EX)` → dosyayı baştan oku ve doğrula → yeni satırı ekle → `flush` + `fsync`. Üç yazar vardır (motor, CLI, Telegram süreci); hepsi aynı `LadderLog.append` yolunu kullanır.

Ortak alanlar: `seq` (1'den başlar, +1), `at` (`YYYY-MM-DDTHH:MM:SSZ`, yazarın saati; bir önceki satırdan küçük olamaz), `kind`, `by` (`cli:<ad>` | `telegram:<son3>` | `engine:rk1`), `note` (metin, ≤ 200), `prev` (önceki satırın `hash`'i; ilk satırda 64 adet `0`), `hash`.

`hash = sha256(json.dumps(satır_hash_hariç, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()`.

### 4.2 Satır türleri

| `kind` | Yazar | Ek alanlar | Katlama etkisi |
|---|---|---|---|
| `initial` | CLI | `amount > 0` | Yalnız `seq = 1` ve bir kez. `dep_net = base = peak = amount`; `step = 0`; `step_since = started_at = at`; `status = "ok"` |
| `deposit` | CLI | `amount > 0` | `dep_net += a; base += a; peak += a` |
| `withdraw` | CLI | `amount > 0`, `equity`, `capital_part` (0 ≤ c ≤ amount) | `dep_net −= c; base −= c; peak = max(base, peak − amount)`. Sonuçta `dep_net > 0` ve `base > 0` değilse satır geçersiz |
| `adjust` | CLI | `amount ≠ 0`, `note` **zorunlu** | Kayıt düzeltmesi (para hareketi değil; §7 eşleştirmesine girmez). `dep_net += a; base += a; peak = max(base, peak + a)`; sonuç > 0 olmalı |
| `peak` | motor | `value` | `peak = max(peak, value)`; `fired = ∅` |
| `step_down` | motor | `step` (yeni), `trigger` (`dd_peak_10` \| `dd_peak_15`), `equity`, `peak` | `−1 ≤ step < eski` olmalı. `step_since = last_down_at = at`; `fired ∪= {trigger}` |
| `review_stop` | motor | `equity`, `base` | `status` `ok → review` (başka durumdan geçersiz). `stopped_at = last_down_at = at` |
| `floor_stop` | motor | `equity`, `dep_net` | `status` `ok\|review → floor`. `stopped_at = last_down_at = at` |
| `review_resume` | Telegram / CLI | `equity > 0`, `rebase: bool`, `decision` (metin; Telegram'da `""`) | `status` `review → ok` (başka durumdan geçersiz). `rebase` ise: `base = min(base, equity)`; `peak = max(base, equity)`; `fired = ∅`; `step = min(step, 0)` (değiştiyse `step_since = at`). `rebase=false`: yalnız `status` |
| `floor_restart` | CLI | `equity > 0`, `decision` **zorunlu** (boş olamaz) | `status` `floor → ok`. `dep_net = base = peak = equity`; `step = min(step, 0)`; `step_since = at`; `fired = ∅` |
| `step_up` | CLI | `step`, `decision` **zorunlu** | `status == "ok"`, `step == eski + 1`, `step ≤ MAX_STEP_APPROVABLE` olmalı. `step_since = at` |

Tüm tutarlar sonlu `float`; `bool`, `NaN`, `inf`, metin geçersiz. Bilinmeyen `kind`, eksik/fazla zorunlu alan, kırık `seq`/`prev`/`hash`, geri giden `at`, yukarıdaki geçiş kurallarından birinin ihlali → **tüm günlük geçersiz** (`LadderLogError`); kısmi katlama yoktur.

### 4.3 Çekme: önce kârdan, sonra sermayeden

CLI çekmeyi yazarken `capital_part = max(0, amount − max(0, equity − base))` hesaplar ve satıra `equity` ile birlikte yazar (katlama bu alanı aynen uygular, yeniden hesaplamaz). `equity`: `status.json`'daki değer (`loop_at` en çok `STATUS_FRESH_S` eski) ya da operatörün verdiği `--equity`. Örnek: `base = 1000`, `equity = 1300`, çekilen 300 → `capital_part = 0` (taban değişmez). `equity = 900`, çekilen 100 → `capital_part = 100` (`base = dep_net = 900`).

### 4.4 Arayüz

```python
class LadderLogError(Exception): ...

@dataclass(frozen=True)
class LadderState:
    status: Literal["ok", "review", "floor"]
    step: int
    step_since: datetime
    dep_net: float
    base: float
    peak: float
    started_at: datetime
    last_down_at: datetime | None
    stopped_at: datetime | None
    fired: frozenset[str]
    seq: int
    head_hash: str

@dataclass(frozen=True)
class Action:
    kind: Literal["step_down", "review_stop", "floor_stop"]
    step: int | None = None          # yalnız step_down
    trigger: str | None = None       # yalnız step_down

class LadderLog:
    def __init__(self, path: str | None) -> None      # None = yalnız bellek (kağıt gözlemi)
    def rows(self) -> list[dict]                       # dosya yok -> []; bozuk -> LadderLogError
    def state(self) -> LadderState | None              # satır yok -> None
    def append(self, kind: str, by: str, now: datetime, *, note: str = "", **fields) -> dict
        # kilit altında oku+doğrula+ekle; eklenince katlama geçersizse LadderLogError ve HİÇBİR ŞEY yazılmaz

def fold(rows: Sequence[Mapping]) -> LadderState | None                   # saf
def evaluate(st: LadderState, equity: float) -> tuple[Action, ...]        # saf; 0 ya da 1 eylem
def step_config(base_cfg: RiskConfig, step: int) -> RiskConfig            # saf
def lowest(dep_net: float) -> int
```

`step_config`: `v = min(base_cfg.target_trade_risk, STEPS[step])`; `v == base_cfg.target_trade_risk` ise **aynı nesneyi** döner, değilse `trader_core.risk.tightened(base_cfg, target_trade_risk=v)`. Bilinmeyen basamak → `ValueError`.

## 5. Sermaye ve kademe CLI'si (`python -m trader_engine …`; yalnız sunucuda)

Ortak: `--bot <b>` (ve mevcut `--env`), `--by <ad>` **zorunlu** (`by = "cli:<ad>"`), `--note`. `backtest` ve `paper` kipinde yazan komutlar reddedilir (çıkış 2, "kağıtta sermaye kaydı yok"); `list`/`status` her kipte çalışır. Geçersiz istek hiçbir şey yazmaz; çıkış kodları mevcut `cli.py` düzeni (0 başarı, 2 kullanım/doğrulama hatası, **5 bulgu** = `EXIT_FINDINGS`; 4 = `EXIT_ENGINE` bu belgede kullanılmaz).

| Komut | Davranış |
|---|---|
| `capital init --amount A` | Günlük boşsa `initial` yazar; doluysa ret |
| `capital deposit --amount A` | `deposit` |
| `capital withdraw --amount A [--equity E]` | §4.3. `status.json` taze değilse ve `--equity` yoksa ret |
| `capital adjust --amount ±A --note "<neden>"` | `adjust`; not boşsa ret |
| `capital list` | Satırlar + katlanmış durum, tek JSON (`{"bot", "rows", "state"}`); bozuksa hata metni ve çıkış 5 |
| `ladder status` | `status.json`'daki `risk_ladder` bloğu yoksa günlükten katlanmış durum |
| `ladder resume [--no-rebase] [--equity E] [--decision "<ref>"]` | Koşul: `status == "review"`. `review_resume` yazar (`equity` §4.3'teki kaynak), **sonra** `EntryPause.remove("drawdown_review", by)`. Durum zaten `ok` ama tutuş duruyorsa yalnız tutuşu kaldırır. `--no-rebase` yanlış alarm içindir (taban değişmez) |
| `ladder floor-restart --decision "<ref>" [--equity E]` | Koşul: `status == "floor"`; `--decision` boşsa ret. `floor_restart` yazar, sonra `capital_floor` **ve** varsa `drawdown_review` tutuşlarını kaldırır |
| `ladder step-up --decision "<ref>"` | Yalnız K−1 → K0. Koşullar (hepsi): `status == "ok"`; `step + 1 ≤ MAX_STEP_APPROVABLE`; `counters` (§6.3) `step_trades ≥ 60`, `step_days ≥ 42`, `step_mean_r ≥ 0`; `last_down_at`'ten beri ≥ 56 gün. Tutmayan koşullar tek tek yazdırılır, çıkış 5 |

Yazan her komut sonucu ve yeni eşikleri yazdırır (`base`, durma seviyesi, taban seviyesi, basamak). `capital deposit/withdraw` ayrıca şunu yazdırır: "Canlıda bu kayıt borsadaki aktarımla eşleşene kadar yeni giriş kapalıdır." `pause.remove` çağrısı `src/trader_engine` içinde yine **yalnız** `cli.py`'dedir (11 §9.2 AST koruması değişmez).

## 6. Tetikler, eylemler, sayaçlar

### 6.1 `evaluate(st, equity)` — sırayla, ilk tutan tek eylem

| # | Koşul | Eylem |
|---|---|---|
| 1 | `st.status == "floor"` | — (hiçbir şey) |
| 2 | `equity <= round(FLOOR_RATIO * dep_net, 8)` | `floor_stop` (`ok` ya da `review`'dan) |
| 3 | `st.status == "review"` | — |
| 4 | `equity <= round(STOP_RATIO * base, 8)` | `review_stop` |
| 5 | **[KALDIRILDI 24.11: `STEP_RISK_ENABLED=False` iken atlanır, `step_down` üretilmez]** `equity <= round(DOWN_2_RATIO * peak, 8)` ve `"dd_peak_15" ∉ fired` | hedef = `max(lowest(dep_net), 0 if step > 0 else -1)`; hedef < `step` ise `step_down(hedef, "dd_peak_15")` |
| 6 | **[KALDIRILDI 24.11: aynı sabit]** `equity <= round(DOWN_1_RATIO * peak, 8)` ve `"dd_peak_10" ∉ fired` | hedef = `max(lowest(dep_net), step − 1)`; hedef < `step` ise `step_down(hedef, "dd_peak_10")` |

Satır 5 koşulu tutuyor ama hedef `step`'e eşitse (zaten en altta) eylem yoktur ve satır 6'ya **geçilmez**. `equity` sonlu ve > 0 değilse `ValueError` (çağıran §8.2'de yakalar).

### 6.2 Eylemlerin uygulanması (yalnız zorlama kipi)

| Eylem | Günlük | Tutuş / etki | Kim kaldırır |
|---|---|---|---|
| `step_down` | `step_down` satırı | Tutuş yok. Sonraki girişlerden itibaren etkin risk düşer; açık pozisyonlara dokunulmaz | Geri çıkış: yalnız `ladder step-up` (K−1 → K0) |
| `review_stop` | `review_stop` satırı | `pause.add("drawdown_review", by="engine:rk1", note="base=<…> equity=<…>")`. Yeni giriş kapalı; pozisyonlar stop ve normal çıkışlarla yaşar; mutabakat ve stop bekçisi çalışır | Kullanıcı: `/kademe_devam` ya da `ladder resume` |
| `floor_stop` | `floor_stop` satırı | `pause.add("capital_floor", by="engine:rk1", note="dep_net=<…> equity=<…>")`. Davranış `review_stop` ile aynı (KILL **kurulmaz**; bkz. §16 KULLANICI KARARI 2) | Yalnız `ladder floor-restart` (karar referansıyla) |

Kurallar: günlük satırı **önce** denenir, tutuş **her durumda** kurulur (satır yazılamasa da; `CRITICAL` günlük, sonraki değerlendirmede satır yeniden denenir). Motor `KILL` kurmaz, pozisyon kapatmaz, tutuş kaldırmaz, `review_resume`/`floor_restart`/`step_up`/sermaye satırı **yazmaz** (mimari test: `ladder.py` içinde bu `kind` dizgeleri `append` çağrısına verilmez). `/devam` ve `pause --clear --reason drawdown_review` tek başına yetmez: günlük hâlâ `review`/`floor` diyorsa motor tutuşu bir sonraki değerlendirmede yeniden kurar (§8.2 adım 3). Yatırma, bakiye toparlanması, yeniden başlatma ve süre hiçbir durumu kendiliğinden açmaz.

### 6.3 Sayaçlar — neyin "işlem" sayıldığı

```python
def counters(trades: Sequence[TradeRecord], st: LadderState, now: datetime) -> dict
```

Girdi: botun **kendi** defterinden `list_closed_trades(since=st.started_at, limit=LIST_CLOSED_MAX)`. Bir işlem sayılır ⇔ kapanmış, `entry_ts >= st.started_at` ve `exit_reason != "manual"` (yabancı/elle kapanış strateji sonucu değildir; kâr/zararı özsermayede zaten görünür). KILL, tasfiye ve stop kapanışları sayılır. Kağıt işlemleri sayılmaz (canlı günlüğü `initial` ile başlar; kağıt botunda günlük yoktur). **250–300 USD dönemindeki canlı işlemler sayılır** (kullanıcı kararı); sermaye tamamlama (`deposit`) hiçbir sayacı sıfırlamaz.

| Alan | Tanım |
|---|---|
| `total_trades` | Sayılan tüm işlemler |
| `step_trades` | `entry_ts >= st.step_since` olanlar ("basamak yürürlükteyken açılıp kapanmış") |
| `step_days` | `(now − st.step_since)` tam gün (aşağı yuvarlanır) |
| `step_mean_r` | `step_trades` üzerinde `r_multiple` ortalaması; işlem yoksa `None` |
| `consec_losses` | En son işlemden geriye, `r_multiple < 0` olan kesintisiz dizi uzunluğu |
| `last30_sum_r` | Son 30 sayılan işlemin `r_multiple` toplamı (30'dan azsa eldekiler) |

Sıfırlama: `step_since` değişince basamak sayaçları kendiliğinden sıfırlanır (`step_down`, `step_up`, basamağı değiştiren `review_resume`, her `floor_restart`). `total_trades` yalnız `floor_restart` ile değil, hiçbir satırla sıfırlanmaz (`started_at` sabittir). Yeni strateji ana sürümü ve ML etkinleştirme sıfırlamaları RK-1b'dedir (§15).

## 7. Canlıda aktarım eşleştirmesi (yalnız `mode == "live"`)

Amaç: kaydedilmemiş bir yatırma tabanları olduğundan gevşek gösterir; kaydedilip gelmemiş bir yatırma sahte durma üretir. İkisi de giriş kapatır ve tetikleri askıya alır.

```python
@dataclass(frozen=True)
class Transfer: ts: datetime; amount: float; tran_id: str; asset: str     # amount işaretli: vadeli cüzdana giriş +

@dataclass(frozen=True)
class MatchResult: ok: bool; unmatched_exchange: tuple[Transfer, ...]; unmatched_log: tuple[int, ...]   # seq'ler

def match_transfers(rows: Sequence[Mapping], transfers: Sequence[Transfer], now: datetime) -> MatchResult   # saf
```

- `LiveBroker.transfers(since, until) -> list[Transfer]`: `income(None, "TRANSFER", …)` [V-8]; `tranId` ile tekilleştirir. Okuma hatası istisna olarak yükselir.
- Havuzlar: borsa tarafı `ts >= max(started_at, now − XFER_WINDOW_S)`; günlük tarafı `deposit` (+`amount`) ve `withdraw` (−`amount`) satırları, `at >= now − XFER_WINDOW_S − XFER_PAIR_S`. `initial` ve `adjust` eşleştirmeye **girmez**.
- Eşleme: borsa aktarımları zaman sırasıyla; her biri için aynı işaretli, `|tutar farkı| <= XFER_TOL`, `|Δt| <= XFER_PAIR_S` olan **en eski** eşleşmemiş günlük satırı; bire bir.
- Zorunlu küme (v1.1): **borsa tarafı** = tüm 7 günlük pencere (`ts >= max(started_at, now − XFER_WINDOW_S)`); **günlük tarafı** = son `XFER_MUST_S` (5 gün) içindeki `deposit`/`withdraw` satırları. Bunlardan eşleşmeyen varsa `ok = False`. `asset != "USDT"` aktarım her zaman eşleşmemiş sayılır. (v1'de borsa tarafı da 5 gündü; 5–7 gün arası kaydedilmemiş aktarım sahte "tamam" üretip yanlış taban/yanlış yönde stop doğuruyordu.)
- **Yapışkan mandal (v1.1, `RiskLadder`):** `ok = False` bir kez görüldüyse `capital_mismatch` kalkmaz; ancak sonraki eşleştirme tam `ok` **ve** (günlük başı `seq` değişmiş — operatör eylemi — **ya da** mandaldaki her eşleşmemiş kalem gerçekten eşleşmiş: geç gelen aktarım/kayıt) ise kalkar. Pencereden düşme/süre aşımı tek başına mandalı kaldırmaz. Mandal bellektedir; yeniden başlatmada kaybolur (kabul edilen sınır).
- İlk kurulum denetimi: günlükte yalnız `initial` varken, açık pozisyon ve `started_at`'ten beri kapanmış işlem yokken `|wallet − dep_net| > max(INIT_TOL_ABS, INIT_TOL_REL × dep_net)` ise uyuşmazlık (`detail = "init_wallet"`). Düzeltme: `capital adjust`.
- Operatör sırası serbesttir (önce kaydet ya da önce aktar); arada giriş kapalı kalır, sahte tetik üretilmez (§8.2 adım 6).
- Motor 7 günden uzun kapalı kaldıysa o aradaki aktarımlar denetlenmemiş olur; açılış sonrası ilk günlük raporda mentor elle bakar (bilinen sınır).

## 8. `trader_engine/ladder.py` — `RiskLadder`

### 8.1 Kurulum

```python
class RiskLadder:
    def __init__(self, cfg: EngineConfig, clock: Clock, pause: EntryPause | None, *, log: LadderLog, enforce: bool,
                 follow: LadderLog | None = None,
                 transfers_fn: Callable[[datetime, datetime], list[Transfer]] | None = None,
                 trades_fn: Callable[[datetime], Sequence[TradeRecord]] | None = None) -> None
    def tick(self, now: datetime, equity: float, wallet: float, *, flat: bool = False) -> None
    def gate_code(self) -> str | None
    @property
    def risk_config(self) -> RiskConfig
    def status(self) -> dict
```

| Kip | `ladder` | `enforce` | Günlük | `transfers_fn` |
|---|---|---|---|---|
| `backtest` | `None` (hiç kurulmaz) | — | — | — |
| `paper` | var | `True` (24.11) | dosya (`risk_ladder.jsonl`); günlük yoksa/boşsa motor açılışta bir kez `initial = cfg.wallet_start` (`by="engine:paper"`, `start_step=LIVE_START_STEP`) yazar | yok (tek fark: kâğıtta aktarım eşleştirmesi yok) |
| `testnet` | var | `True` | dosya | yok |
| `live` | var | `True` | dosya | `broker.transfers` |

`testnet`/`live` kipinde `pause is None` ise `ConfigError` (kurulum hatası). `mode == "live"` iken motor `ladder` olmadan kurulamaz (test).

### 8.2 `tick` — değerlendirme

Çağrı yerleri: (a) her karar adımının **başında**, kapılardan (`EntryGate.pre`) önce; (b) `live_tick` içinde olay boşaltmadan sonra, mutabakattan önce (`_guard("ladder", …)`). `equity`/`wallet` çağıranın az önce okuduğu `broker.account()` değerleridir; `flat` = açık pozisyon ve çözülmemiş emir yok. `tick` hiçbir istisnayı dışarı sızdırmaz (yakalar, `ladder_errors` sayacı, kapı `ladder_invalid`).

1. **Kısma:** son değerlendirmeden beri `EVAL_EVERY_S` geçmediyse dön (ilk çağrı her zaman çalışır).
2. **Günlük:** `log.state()`. Dosya yok/boş → kapı `capital_missing`, dön. `LadderLogError` ya da okuma hatası → kapı `ladder_invalid`, dön. (Dosya boyutu/mtime değişmediyse önbellek kullanılabilir.)
3. **Tutuş değişmezi (zorlama):** `status == "review"` → `pause.add("drawdown_review", …)`; `"floor"` → `pause.add("capital_floor", …)` (ikisi de idempotent; ekleme sonrası tutuşun varlığı doğrulanır). **Yalnız `floor`** durumunda adım 4–9 atlanır (yalnız `status()` alanları güncellenir). **`review`** durumunda adım 4–6 ve 8 çalışır (aktarım, özsermaye, uyuşmazlık; tetik yalnız `floor_stop` üretebilir), **adım 7 (tepe) atlanır**. Tutuş eklenemez/doğrulanamazsa bellek içi mandal kapıyı `ladder_invalid` yapar (sonraki başarılı ekleme kaldırır; durma durumlarında tutuş doğrulanmadan kapı asla `None` olmaz). Bir `review_stop`/`floor_stop` satırı yazılamayıp yeniden deneme bekliyorsa kapı `ladder_invalid` (Telegram ret 6 ile `/kademe_devam`'ı da engeller), tutuş her adımda yeniden kurulur ve başka eylem/tetik değerlendirilmez; satır `at = max(now, son satır at)` ile yazılır (motor saati geride kalsa da düşmez).
4. **Aktarım (yalnız `transfers_fn`):** son başarılı yoklamadan beri `XFER_POLL_S` geçtiyse yokla + `match_transfers` + ilk kurulum denetimi. Yoklama hatası: önceki sonuç korunur; son **başarılı** yoklama `XFER_STALE_S`'ten eskiyse (ya da hiç yoksa) kapı `capital_unverified`.
5. **Özsermaye:** sonlu ve > 0 değilse kapı `equity_unreadable`, dön.
6. **Uyuşmazlık:** son eşleştirme `ok` değilse kapı `capital_mismatch`; **tepe güncellenmez, tetik değerlendirilmez**, bekleyen onay sayacı sıfırlanır, dön. (`capital_unverified` tek başına tetikleri **durdurmaz**.)
7. **Tepe:** bu, yeni UTC gününün (ya da sürecin) ilk değerlendirmesiyse ve `equity > peak` ise `peak` satırı (`value = equity`).
8. **Tetik + onay:** `a = evaluate(state, equity)`. Eylem türü bir önceki değerlendirmedekiyle aynıysa sayaç +1, değilse 1 (eylem yoksa 0). Sayaç `CONFIRM_N`'e ulaşınca §6.2 uygulanır ve sayaç sıfırlanır.
9. **Sayaçlar:** `trades_fn` varsa en çok 10 dakikada bir `counters` yenilenir.

**[KALDIRILDI 24.11 — kâğıt da zorlanır; etkin risk her kipte `cfg.risk_config` (%1)]** Eski gözlem kipinde (`enforce=False`) adım 3 ve 4 yoktu; adım 8'de günlük satırı belleğe yazılır, **tutuş kurulmaz, kapı kapanmaz, etkin risk değişmez**; `status()["would"]` = uygulanmış olacak son eylem (`"review_stop"` vb.) ve zamanı.

### 8.3 Kapı ve etkin risk

- `gate_code()`: `None` | `"capital_missing"` | `"ladder_invalid"` | `"equity_unreadable"` | `"capital_mismatch"` | `"capital_unverified"` (öncelik bu sırada). Gözlem kipinde her zaman `None`. Bu kodlar **kalıcı değildir**: neden ortadan kalkınca (dosya düzeltilince, aktarım eşleşince) bir sonraki değerlendirmede kendiliğinden açılır. Kalıcı olanlar (`drawdown_review`, `capital_floor`) duraklatma tutuşlarıdır.
- `EntryGate.pre` sırası (11 §9.3'ün devamı): … → `kill` → duraklatma (`pause.code()`: `capital_floor` \| `drawdown_review` \| `paused`) → **kademe kapısı** → `stale_data`. Kademe kapısı kapalıysa `GateVerdict(False, <kod>, "entry_gate_closed")`; karar olayında `veto_reason = "gate:<kod>"`. `Engine._live_gate_code` aynı sırayı izler.
- `risk_config`: zorlama kipinde `step_config(cfg.risk_config, state.step)`; durum yok/bozuksa `cfg.risk_config` (kapı zaten kapalıdır). Gözlem kipinde: `follow` yoksa `cfg.risk_config` (kağıt sonuçları **bit-bit aynı**); `follow` varsa §8.4.
- `gates.py`: `K.check_entry(acct, cand, src.risk_config)`; `src = self.ladder if self.ladder is not None else self.cfg`. Risk sabiti tarayıcısı `.risk_config` ile biten ifadeyi kabul eder; başka biçim kullanılmaz. `ladder.py` içinde sayısal risk sabiti, `RiskConfig(...)`, `replace(...)` **yoktur** (hepsi `trader_core`'dadır).
- Açık pozisyonlar, çıkışlar, stop yönetimi, KILL ve mutabakat bu belgeden **etkilenmez**.

### 8.4 İkiz ve kağıt botlarının basamağı izlemesi **[KALDIRILDI 24.11: risk düşürme yok, kademe izleme anlamsız; `ladder_follow` alanı kodda kalır, kâğıt dosyasında kullanılmaz]**

`EngineConfig.ladder_follow: str | None = None` — başka bir botun günlük dosyasının yolu; yalnız `mode == "paper"` iken verilebilir (aksi `ConfigError`). Verilmişse her değerlendirmede o günlük katlanır: geçerliyse etkin risk `step_config(cfg.risk_config, s)`, `s = followed.step` (`followed.status != "ok"` ise `min(step, 0)`); dosya yok/bozuksa `cfg.risk_config` ve `ladder_follow_unreadable` sayacı. İzleyen bot günlüğe **yazmaz** ve izlenen botun durmasından etkilenmez (ikiz durmaz; kural belgesi §5 madde 4, §7). Bugün hiçbir yapılandırmada ayarlanmaz; canlıya geçiş adımında `engine.twin.json`'a (ve canlıyla birlikte çalışan kağıt botuna) canlı günlüğün yolu yazılır (11 §13 geçiş listesine eklenir).

## 9. Telegram (`trader_core/telegram.py`)

`TelegramDaemon(..., ladders: Mapping[str, LadderFiles] | None)`; `LadderFiles(log: LadderLog, status_path: str, pause: EntryPause)`. `scripts/telegram_run.py` `build_ladders(env, …)`: `LADDER_BOTS` (varsayılan boş; canlıya geçişte canlı bot yazılır) için mutlak yollar (`build_pauses` ile aynı çözüm).

- **`/kademe`** — salt okunur. Bot başına: `status.json` `risk_ladder` bloğundan (taze değilse günlükten katlayıp "motor durumu bayat" notuyla) şu satırlar: basamak ve risk; durum (`ok` / `inceleme` / `taban`); `dep_net`, `base`, `peak`, `equity`; düşüş yüzdeleri; durma ve taban seviyeleri (USD); kapı kodu (varsa); sayaçlar. `ladders` boşsa "kademe denetimi yapılandırılmadı".
- **`/kademe_devam`** — iki adımlı (mevcut `pending.json` düzeni: 4 haneli kod, TTL 120 sn, tek kullanım; `action="ladder_resume"`). **Hem istek hem kod anında** denetlenen ret koşulları (ilk tutan, yanıt metniyle):
  1. `review` durumunda bot yok → "Bekleyen kademe incelemesi yok" (durum `ok` ama `drawdown_review` tutuşu duruyorsa bu ret **değildir**: onayda yalnız tutuş kaldırılır).
  2. Durum `floor` → "Son taban: Telegram'dan açılamaz; yazılı karar + sunucu gerekir".
  3. KILL etkin → "Önce KILL: /devam".
  4. `now − stopped_at < RESUME_MIN_WAIT_S` → "En erken <tarih saat> (kalan <s> saat)".
  5. `status.json` yok, `loop_at` `STATUS_FRESH_S`'ten eski ya da `equity` sonlu > 0 değil, **ya da `risk_ladder` bloğu yok / bloğun `state` alanı günlükten katlanan durumla aynı değil (v1.1)** → "Motor durumu okunamıyor; sunucuda `ladder resume`".
  6. `risk_ladder.gate_code` boş değil → "Önce sermaye kaydı sorunu çözülmeli: <kod>".
  
  İstek yanıtı kodla birlikte sonucu **önceden** gösterir: "Onaylarsan: yeni taban <E> USD, yeni durma seviyesi <0,80×E> USD, basamak <K0|K−1>, son taban <0,60×dep_net> USD." Onayda: `log.append("review_resume", by="telegram:<son3>", equity=<status equity>, rebase=True, decision="")` → **sonra** `pause.remove("drawdown_review", by)`. Satır yazılamazsa tutuş **kaldırılmaz** (CRIT yanıt). Satır yazıldı ama tutuş kaldırılamadıysa CRIT yanıt; komut yinelenince yalnız tutuş kaldırılır. Yanıt, kalan tutuşları da sayar (`_remaining_lines`). Mentor aynı gün kararı `tasarim-kararlari.md`'ye işler (süreç; kod değil).
- **`/devam`**: değişmez; `drawdown_review` ve `capital_floor` için mevcut ret metni geçerlidir (`capital_floor` için ek: "sunucuda, yazılı kararla").
- **`/durum`** ve **21:00 raporu**: bot başına tek satır — `Kademe: K0 %0,50 | özsermaye 262,40 | taban 250,00 (düşüş %0,0) | durma 200,00 | son taban 150,00 | işlem 37` ; durum `ok` değilse satır başına `İNCELEME` / `TABAN`. Rapor bölüm adı "Risk kademesi".
- `HELP` metnine `/kademe  /kademe_devam` eklenir. Sermaye hareketi, `floor_restart`, `step_up` için Telegram komutu **yoktur**.

## 10. `status.json` — `risk_ladder` bloğu

`backtest` dışındaki her kipte yazılır. Durum yok/bozukken sayısal alanlar `None`, `state` ilgili değer.

```json
"risk_ladder": {
  "enforce": true,
  "state": "ok",                    // ok | review | floor | uninitialized | invalid
  "step": 0, "step_name": "K0", "step_risk": 0.005, "effective_risk": 0.005, "lowest_step": 0,
  "step_since": "2026-12-30T09:00:00Z", "started_at": "2026-12-30T09:00:00Z",
  "dep_net": 250.0, "base": 250.0, "peak": 262.4, "equity": 258.1,
  "dd_base_pct": 0.0, "dd_peak_pct": 1.64,
  "stop_at": 200.0, "floor_at": 150.0, "near": false,
  "stopped_at": null, "last_down_at": null,
  "gate_code": null, "gate_since": null,
  "transfer": {"checked_at": "2026-12-30T10:02:00Z", "ok": true, "unmatched": 0},   // yalnız live; diğerlerinde null
  "pending": null,                  // onay bekleyen eylem türü (CONFIRM_N dolmadan)
  "would": null,                    // yalnız gözlem: {"kind": "review_stop", "at": "..."}
  "follow": null,                   // yalnız ladder_follow: {"step": -1, "ok": true}
  "counters": {"total_trades": 37, "step_trades": 37, "step_days": 21, "step_mean_r": 0.04, "consec_losses": 2, "last30_sum_r": 1.3},
  "log_seq": 4, "log_hash": "1c1cc11e"            // head_hash'in ilk 8 karakteri
}
```

`stop_at = round(STOP_RATIO * base, 8)`, `floor_at = round(FLOOR_RATIO * dep_net, 8)`, `near = equity <= round(NEAR_RATIO * base, 8)`. `StatusWriter.build`: blok `f.get("risk_ladder")` varsa aynen eklenir; `gate.code` zaten `_live_gate_code` üzerinden kademe kapısını yansıtır. Blok hiçbir zaman yazımı bozmaz (hata → blok `None`).

## 11. Alarmlar (sağlık denetçisi; `status.json`'dan, 5 dakikada bir)

`ApiProbe.ladder: Mapping | None`. Denetim adı `risk_ladder:<bot>`; en ağır tek sonuç döner.

| Koşul | Seviye | Kod | İleti özü |
|---|---|---|---|
| `mode ∈ {live, testnet}` ve blok yok | CRIT | `ladder_missing` | Kademe denetimi çalışmıyor |
| `state == "floor"` | CRIT | `capital_floor` | Son taban: özsermaye <E>, yatırılan <D>; girişler kapalı; hepsini kapatmak için /hepsini_kapat; yeniden başlama yazılı kararla |
| `state == "review"` | CRIT | `drawdown_review` | −%20 durma: taban <B>, özsermaye <E>, açık pozisyon <n>; /hepsini_kapat seçeneği; mentor değerlendirmesi ≤ 3 gün; devam /kademe_devam |
| `state ∈ {uninitialized, invalid}` ya da `gate_code ∈ {capital_missing, ladder_invalid, equity_unreadable}` (zorlama) | CRIT | aynı kod | Girişler kapalı; sunucuda bakılmalı |
| `gate_code == "capital_mismatch"` | WARN; `gate_since` 30 dk'dan eskiyse CRIT | `capital_mismatch` | Borsadaki aktarım ile sermaye kaydı eşleşmiyor |
| `gate_code == "capital_unverified"` | WARN | `capital_unverified` | Aktarım kayıtları okunamıyor |
| `near` ve `state == "ok"` | WARN | `ladder_near` | Durma eşiğine yaklaşıldı (özsermaye ≤ tabanın %85'i) |
| `last_down_at` son 24 saatte ve `state == "ok"` | WARN | `ladder_step_down` | Basamak indi: <ad> |
| `state == "ok"` ve `drawdown_review` tutuşu duruyor (10 dk'dan uzun) | WARN | `ladder_hold_stale` | Devam yarım kaldı; /kademe_devam yinelenmeli |
| `would` dolu (gözlem) ve son 24 saatte | WARN | `ladder_would` | Kağıtta: canlı olsaydı <eylem> |
| hiçbiri | OK | `ok` | — |

Motor ayrıca her eylemde `CRITICAL` (durma/taban) ya da `WARNING` (iniş) günlük satırı yazar. Mevcut `pause_audit` denetimi `capital_floor` ve `drawdown_review` tutuşlarını zaten kapsar (motor `add` denetim günlüğüne yazar).

## 12. Elle doğrulanabilir örnekler ve tatbikatlar

1. **Özet zinciri.** Satır 1 = `{"seq":1,"at":"2026-12-30T09:00:00Z","kind":"initial","by":"cli:sg","note":"","amount":250.0,"prev":"<64 sıfır>"}` ⇒ `hash = 1cfa987532dbe34b8d145f274fda1dde6dff6b5b32442a448e5ad9f3fe8dafd7`. Satır 2 = `{"seq":2,"at":"2027-01-25T10:00:00Z","kind":"deposit","by":"cli:sg","note":"1000e tamamlama","amount":750.0,"prev":"1cfa…afd7"}` ⇒ `hash = 1c1cc11e660a0d43a64d6a2e731e48035439d67ce106924efc304bf25797636c`.
2. **Küçük sermaye.** `initial 250` ⇒ `base = dep_net = peak = 250`, durma 200,00, taban 150,00, en alt basamak K0. Özsermaye 224 (tepeden −%10,4) ⇒ eylem yok (K0 zaten en alt). 200,00 ⇒ iki değerlendirme sonra `review_stop`. 200,01 ⇒ yok.
3. **Devam.** Durma sonrası özsermaye 198, `/kademe_devam` ⇒ `base = 198`, `peak = 198`, yeni durma 158,40; taban hâlâ 150,00 (`dep_net = 250`).
4. **Tamamlama.** Örnek 3'ten sonra `deposit 750` ⇒ `dep_net = 1000`, `base = 948`, `peak = 948`, durma 758,40, taban 600,00, en alt basamak K−1. Sayaçlar sıfırlanmaz.
5. **İniş (1000 USD).** `initial 1000`, K0. Özsermaye 900,00 ⇒ `step_down(-1, "dd_peak_10")`. Sonra 850,00 ⇒ eylem yok (zaten K−1). 800,00 ⇒ `review_stop`. 600,00 ⇒ `floor_stop` (inceleme sürerken de).
6. **Çekme.** `base = 1000`, `equity = 1300`, `withdraw 300` ⇒ `capital_part = 0`, `base = 1000`, `peak = max(1000, peak − 300)`. `equity = 900`, `withdraw 100` ⇒ `capital_part = 100`, `base = dep_net = 900`.
7. **Etkin risk.** `cfg.target_trade_risk = 0.005`: K0 ⇒ `cfg.risk_config` nesnesinin kendisi; K−1 ⇒ `target_trade_risk = 0.0035`, diğer alanlar `LOCKED_CFG` ile aynı; K2 (ileride) ⇒ yine 0.005 (yapılandırma tavanı).

**Onarım (runbook, tek satır):** günlükte yarım son satır (satır sonu yok; çökme/disk dolu) ⇒ günlük fail-closed `ladder_invalid`; onarım: yarım son satırı sunucuda elle sil (`sed -i '$ d' var/risk_ladder.jsonl`, önce `cp` ile yedek), `python -m trader_engine capital list --bot <b>` ile zincirin geçerli olduğunu doğrula; kapı ≤ 60 sn'de kendiliğinden açılır.

**Testnet tatbikatları (canlıdan önce zorunlu; sonuç `11-testnet-sonuc.md`'ye):** D-1 `capital init` cüzdanın 1,3 katıyla ⇒ iki değerlendirmede `review_stop`, giriş `drawdown_review` ile reddedilir, açık pozisyon ve stopu yerinde. D-2 motor yeniden başlatılır ⇒ tutuş sürer; `pause --clear --reason drawdown_review` ⇒ ≤ 60 sn'de yeniden kurulur. D-3 `/kademe_devam`: 24 saat reddi, sonra (test için `ladder resume`) taban yenilenir, giriş açılır. D-4 (canlı, duman testi sonrası ilk yatırma) [V-8]: aktarım görünür ve `capital deposit` ile eşleşir; kaydedilmeden önce kapı `capital_mismatch`.

## 13. Test listesi (bağımsız test ajanı yalnız bu belgeden yazar)

Saat her yerde enjekte edilir; gerçek saat, ağ ve gerçek `var/` kullanılmaz. Aksi yazılmadıkça `initial 1000`, K0.

**A. Günlük ve katlama (`tests/test_risk_ladder_spec.py`)**

- T-01 Sabit değişmezleri: `STEPS[4] == LOCKED_CFG.target_trade_risk`; kesin artan; `STEPS[0] == 0.005`; her değer `≤ HARD_LIMITS["target_trade_risk"]`.
- T-02 §12 örnek 1'in iki `hash` değeri birebir.
- T-03 Boş/olmayan dosya ⇒ `rows() == []`, `state() is None`.
- T-04 `initial` yalnız `seq 1`: ikinci `initial` reddi; `initial` olmadan `deposit` reddi; hiçbir şey yazılmaz.
- T-05 `deposit`: `dep_net`, `base`, `peak` aynı tutarda artar; `fired` korunur.
- T-06 `withdraw`: §12 örnek 6'nın iki durumu; `dep_net`/`base` ≤ 0 yapan çekme reddi.
- T-07 `adjust`: ± etkisi; notsuz ret; sonucu ≤ 0 yapan ret.
- T-08 `peak`: yalnız yükseltir; `fired` temizlenir.
- T-09 `step_down`: yukarı ya da eşit basamak reddi; −1 altı reddi; `step_since` ve `last_down_at` güncellenir.
- T-10 Durum makinesi: `review_stop` yalnız `ok`'tan; `floor_stop` `ok` ve `review`'dan, `floor`'dan değil; `review_resume` yalnız `review`'dan; `floor_restart` yalnız `floor`'dan; `step_up` yalnız `ok`'ta.
- T-11 `review_resume rebase=True`: `base = min(base, equity)` (equity < base ve equity > base durumları), `peak = max(base, equity)`, `fired = ∅`, `step = min(step, 0)`. `rebase=False`: yalnız `status` değişir.
- T-12 `floor_restart`: `dep_net = base = peak = equity`; `decision` boşsa ret.
- T-13 `step_up`: +1 dışı ret; `MAX_STEP_APPROVABLE` üstü ret (K0 → K1 **reddedilir**); K−1 → K0 kabul.
- T-14 Bozulma: bir satırda tek karakter değişikliği, satır silme, sıra değiştirme, kırık `prev`, geri giden `at`, bilinmeyen `kind`, `NaN`/`bool` tutar ⇒ her biri `LadderLogError`; kısmi durum dönmez.
- T-15 Eşzamanlı ekleme: iki süreç 50'şer satır ⇒ 100 satır, zincir geçerli, `seq` kesintisiz.
- T-16 `append` geçersiz satırda dosyayı **değiştirmez** (bayt eşitliği).

**B. `evaluate`, `step_config`, `counters`, `match_transfers` (aynı dosya)**

- T-17 Durma sınırı: `equity` 800,01 ⇒ yok; 800,00 ⇒ `review_stop`; 799,99 ⇒ `review_stop`.
- T-18 Taban sınırı: 600,01 (durum `review`) ⇒ yok; 600,00 ⇒ `floor_stop`; `ok` durumunda 600,00 ⇒ `floor_stop` (durma değil, taban öncelikli).
- T-19 `floor` durumunda her `equity` için eylem yok; `review` durumunda taban dışında eylem yok.
- T-20 İniş `dd_peak_10`: 900,01 yok; 900,00 ⇒ `step_down(-1)`; aynı tetik `fired` içindeyken yinelenmez; `peak` satırından sonra yeniden tetiklenebilir.
- T-21 İniş `dd_peak_15`: K2'de (elle kurulmuş durum) 850 ⇒ `step_down(0)`; K0'da ⇒ `step_down(-1)`; K−1'de ⇒ eylem yok ve `dd_peak_10`'a geçilmez.
- T-22 Küçük sermaye: `initial 250`, K0, `equity` 224 ve 212 ⇒ eylem yok; `deposit 750` sonrası `lowest == -1`.
- T-23 Durma tabanı `base`'e, taban `dep_net`'e bağlı: §12 örnek 3–4 değerleri (158,40; 150,00; 758,40; 600,00).
- T-24 `evaluate` geçersiz `equity` (`NaN`, `inf`, 0, negatif, `bool`) ⇒ `ValueError`.
- T-25 `step_config`: §12 örnek 7'nin üç durumu; K0'da dönen nesne `is base_cfg`; bilinmeyen basamak `ValueError`; sonuç hiçbir alanda `LOCKED_CFG`'den gevşek değil.
- T-26 `counters`: `manual` kapanış sayılmaz; `started_at` öncesi giriş sayılmaz; `step_since` öncesi giriş `total`'a girer `step`'e girmez; `consec_losses` ve `last30_sum_r` (31 işlemle) değerleri; işlem yokken `step_mean_r is None`; `step_days` aşağı yuvarlanır.
- T-27 `match_transfers`: tam eşleşme; tutar farkı 1,00 kabul / 1,01 ret; `Δt` 48 saat kabul / 48 saat 1 sn ret; ters işaret eşleşmez; bire bir (iki aktarım tek satırla eşleşmez); `initial` ve `adjust` havuzda değil; **(v1.1)** borsa tarafında 7 günlük pencere içindeki (6 günlük dahil) eşleşmemiş aktarım `ok`'u bozar, 7 günden eskisi bozmaz; günlük tarafında 5 günden eski eşleşmemiş kalem bozmaz, 5 gün içindeki bozar; `asset != "USDT"` her zaman eşleşmemiş; `started_at` öncesi aktarım yok sayılır.

**C. Motor (`tests/engine/test_engine_ladder_spec.py`; sahte broker/saat)**

- T-28 `backtest`: `ladder is None`; kilitli dönem öncesi bir referans backtest'in `summary.json` ve `trades.csv` özeti öncesi/sonrası eşit.
- T-29 `paper` gözlem: özsermaye tabanın %80'ine iner ⇒ tutuş **yok**, giriş açık, `status.risk_ladder.would.kind == "review_stop"`; boyutlama `cfg.risk_config` ile (mevcut kağıt testleri değişmeden yeşil).
- T-30 Zorlama, günlük yok ⇒ kapı `capital_missing`, giriş `entry_gate_closed`/`gate:capital_missing`; açık pozisyonun çıkışı çalışır.
- T-31 Bozuk günlük ⇒ `ladder_invalid`; dosya düzeltilince bir sonraki değerlendirmede kendiliğinden açılır.
- T-32 Onay: koşul tek değerlendirmede tutar, sonrakinde tutmaz ⇒ eylem yok; iki ardışıkta ⇒ uygulanır; `EVAL_EVERY_S` dolmadan ikinci çağrı sayılmaz (59/60 sn sınırı).
- T-33 `review_stop` uygulanınca: günlükte satır, `drawdown_review` tutuşu (`by="engine:rk1"`), kapı kodu `drawdown_review`, pozisyonlar açık, KILL **yok**.
- T-34 Kalıcılık: motor yeniden kurulur ⇒ tutuş ve durum sürer; özsermaye toparlanır ⇒ sürer; `deposit` eklenir ⇒ sürer.
- T-35 Tutuş değişmezi: durum `review` iken PAUSE dosyası silinir ⇒ sonraki değerlendirmede tutuş yeniden kurulur. Durum `floor` için `capital_floor` aynı.
- T-36 Günlük yazılamıyor (salt okunur dizin) ⇒ tutuş yine kurulur, `CRITICAL` günlük, istisna sızmaz; yazma düzelince satır eklenir (tek satır, çift değil).
- T-37 `floor_stop`: `review` sürerken taban ⇒ `capital_floor` tutuşu; `pause.code() == "capital_floor"`.
- T-38 `step_down` sonrası bir sonraki girişin `size_risk_amount`'ı K−1 riskine göre (≈ `0.0035 × equity`); o an açık pozisyonun miktarı değişmez.
- T-39 Aktarım (live sahte): kaydedilmemiş +750 ⇒ kapı `capital_mismatch`, **tetik ve tepe yok**; `deposit 750` eklenince açılır (**v1.1:** 7 gün sonra da — pencere/süre aşımıyla — kapı açılmaz, mandal operatör eylemine ya da gerçek eşleşmeye kadar sürer). Tersi: `deposit` var, aktarım yok ⇒ kapı kapalı ve `review_stop`/`floor_stop` **üretilmez** (özsermaye 250, `base` 1000 olsa da).
- T-40 Aktarım yoklaması hata verir: 15 dakikaya kadar kapı açık (önceki sonuç), sonra `capital_unverified`; bu durumda `review_stop` yine çalışır.
- T-41 İlk kurulum denetimi: `initial 250`, cüzdan 300, düz ⇒ `capital_mismatch`; cüzdan 254 ⇒ tamam; açık pozisyon varken denetim atlanır.
- T-42 Özsermaye `NaN` ⇒ kapı `equity_unreadable`, tetik yok, istisna yok.
- T-43 Kapı sırası: KILL + tutuş + kademe kapısı birlikte ⇒ `kill`; tutuş + kademe kapısı ⇒ tutuş kodu; yalnız kademe ⇒ kademe kodu; `stale_data` en sonda.
- T-44 Tepe: aynı UTC gününde yükselen özsermaye `peak` satırı üretmez; gün değişiminin ilk değerlendirmesinde üretir; uyuşmazlık varken üretmez.
- T-45 `ladder_follow`: izlenen günlük K−1 ⇒ izleyenin girişi K−1 riskiyle; izlenen `review` ⇒ izleyen **durmaz**; dosya yok ⇒ `cfg.risk_config` + sayaç; `mode != "paper"` iken anahtar ⇒ `ConfigError`.
- T-46 Mimari: `ladder.py` kaynağında `pause.remove` çağrısı ve `review_resume`/`floor_restart`/`step_up`/`initial`/`deposit`/`withdraw`/`adjust` dizgeleri yok (AST/metin); risk sabiti tarayıcısı ve modül envanteri gerçek ağaçta yeşil; `trader_core/risk_ladder.py` `trader_engine` içe aktarmaz.
- T-47 `mode == "live"` motoru `ladder` olmadan ya da `pause` olmadan kurulamaz.
- T-48 `status.json`: §10'daki tüm anahtarlar var; `stop_at`/`floor_at`/`near` değerleri; durum yokken `state == "uninitialized"` ve sayısal alanlar `None`; `backtest`'te blok yok.

**D. CLI (`tests/engine/test_engine_ladder_spec.py`)**

- T-49 `capital init/deposit/withdraw/adjust/list`: mutlu yol; `--by` yoksa ret; `paper` kipinde yazma reddi; ikinci `init` reddi; bozuk günlükte `capital list` çıkışı **5** (v1.1; eski şartnamedeki 4 literal hatalıydı).
- T-50 `capital withdraw`: taze `status.json`'dan `equity`; bayat (121 sn) ve `--equity` yok ⇒ ret; `--equity` ile kabul.
- T-51 `ladder resume`: `review` değilken ret; kabulde satır + tutuş kalkar; `--no-rebase` tabanı değiştirmez; durum `ok` + artık tutuş ⇒ yalnız tutuş kalkar.
- T-52 `ladder floor-restart`: `--decision` boş ⇒ ret; kabulde iki tutuş da kalkar, `dep_net = equity`.
- T-53 `ladder step-up`: K0'dan ret (her koşul tutsa da); K−1'den dört koşulun her biri tek tek eksikken ret (59/60 işlem, 41/42 gün, ortalama R −0,01/0, 55/56 gün); hepsi tutunca kabul.

**E. Telegram (`tests/test_telegram_ladder_spec.py`)**

- T-54 `/kademe`: değerler; `ladders` boşken yanıt; bayat durumda günlükten katlama notu.
- T-55 `/kademe_devam` retleri: §9'daki altı koşulun her biri (24 saat sınırı: 86399 sn ret, 86400 sn kabul; durum bayatlığı 120/121 sn).
- T-56 İki adım: yanlış kod, süresi dolmuş kod (119/120/121 sn), yetkisiz sohbet ⇒ hiçbir şey yazılmaz; doğru kod ⇒ `review_resume` (`rebase=True`, `by="telegram:…"`) **sonra** tutuş kalkar; koşullar kod anında yeniden denetlenir (istekten sonra KILL kurulursa ret).
- T-57 Satır yazılamazsa tutuş kaldırılmaz, CRIT yanıt; tutuş kaldırılamazsa CRIT yanıt ve yinelemede yalnız tutuş kalkar (ikinci satır yazılmaz).
- T-58 `/devam` `drawdown_review` ve `capital_floor` tutuşlarını kaldırmaz; `floor` durumunda `/kademe_devam` reddi.
- T-59 `/durum` ve günlük rapor satırı biçimi (durum `ok`, `review`, `floor`).

**F. Sağlık (`tests/test_health_ladder_spec.py`)**

- T-60 §11 tablosunun her satırı için bir senaryo (seviye + kod); `capital_mismatch` 29/31 dakika sınırı; `ladder_missing` yalnız `live`/`testnet`'te; birden çok koşulda en ağırı.

## 14. İş paketleri

Her paket: gerçekleme ajanı (Sonnet) + bağımsız test ajanı (paralel, bu belgeden) + mentor incelemesi. Ön koşul: 11 WP-B6 (duraklatma) birleştirilmiş; RK2'nin aktarım kısmı WP-B3'e bağlıdır (B3 yoksa `transfers_fn=None` ile birleştirilir, `LiveBroker.transfers` B3 ile eklenir).

| WP | İçerik | Dosyalar | Testler | Mentor | Gün |
|---|---|---|---|---|---|
| **RK1** | Çekirdek: sabitler, günlük, `fold`, `evaluate`, `step_config`, `counters`, `match_transfers` | `trader_core/risk_ladder.py` | T-01…T-27 | **Evet** (satır satır) | 0,5 |
| **RK2** | `RiskLadder`, kapı, etkin risk, durum, yapılandırma, `transfers` | `ladder.py`, `gates.py`, `engine.py`, `status.py`, `pause.py`, `config.py`, `binance_futures.py`, iki koruma testi | T-28…T-48 | **Evet** | 0,75 |
| **RK3** | CLI | `cli.py` | T-49…T-53 | Evet | 0,25 |
| **RK4** | Telegram, sağlık, rapor, kurulum notu (`LADDER_BOTS`) | `telegram.py`, `telegram_run.py`, `health.py`, `health_run.py`, `deploy/*.env.example` | T-54…T-60 | Evet | 0,5 |

Toplam ≈ 2 gerçekleme günü. Takvim: RK1–RK3 7–13 Aralık (B3/B4 ile paralel), RK4 14–20 Aralık; tatbikatlar D-1…D-3 testnet gölge koşusunda (14–27 Aralık); D-4 29 Aralık sonrası ilk yatırmada. **RK-1 (RK1–RK4 + D-1…D-3) bitmeden canlı başlamaz** (faz planı madde 26 geçiş listesine eklenir). Süre aşılırsa ilk ertelenen: `ladder step-up` (K−1 → K0; `dep_net < 1000` iken zaten gereksiz) ve §8.4 `ladder_follow`.

Canlıya geçişte operatör adımları (11 geçiş listesine eklenir): (1) `capital init --amount <alt hesaptaki tutar>`; (2) `LADDER_BOTS` ve ikizde `ladder_follow`; (3) `/kademe` çıktısının kontrolü (durma ve taban seviyeleri); (4) 1000 USD'ye tamamlamada `capital deposit --amount <tutar>`.

## 15. Ertelenenler (RK-1b; en geç şubat sonu, ayrı şartname revizyonu)

Basamak artışı K0 üstü (`MAX_STEP_APPROVABLE` yükseltilir; Telegram onaylı `/kademe_artir`; kural belgesi §3 koşul 4–7, 9 — güven sınırı, R cinsinden düşüş, kağıt–canlı tutarlılığı, açık olay); yapılandırmadaki `target_trade_risk`'in tavan rolüne geçmesi (bugün 0.005 olduğu için K0 üstü zaten etkisizdir); otomatik iniş tetikleri 4–8 (art arda 12 zarar, son 30 işlem ≤ −12 R, tutarlılık bozulması, %2 aşımı, teknik olay — hepsi K1 ve üstünde ya da artış saatinde anlamlıdır); yeni strateji ana sürümünde ve ML etkinleştirmede sayaç sıfırlama; 4 haftalık değerlendirme raporunun otomatik üretimi; panelde kademe satırı; 7 günden uzun kapalı kalma sonrası aktarım geriye tarama.

## 16. KULLANICI KARARI gerektirenler

Kullanıcı kararları mentora devretti; aşağıdaki ikisi para davranışını değiştirdiği için yine de açıkça sorulur. Yanıt gelmezse **varsayılan uygulanır** ve gerçekleme beklemez.

1. **KULLANICI KARARI 1 — Kâr edilmiş hesapta tepeden −%20.** Varsayılan (bu belge): durma yalnız **yatırılan tutara** göre (`base`) ölçülür; tepeden düşüş yalnız basamağı indirir ve uyarı verir. Örnek: 1000 USD yatırıldı, hesap 1300'e çıktı; giriş 800'de durur (tepeden −%38), 1040'ta (tepeden −%20) durmaz. Alternatif: ikisinden hangisi önce gelirse (daha sıkı; `STOP` koşuluna `equity <= 0,80 × peak` eklenir, yarım saatlik değişiklik).
2. **KULLANICI KARARI 2 — Durma ve son tabanda açık pozisyonlar.** Varsayılan: açık kalır, borsadaki zarar durdurlarıyla yönetilir; istenirse `/hepsini_kapat`. Alternatif: son tabanda (%60) otomatik kapatma.

Mentor kararıyla kapananlar (bilgi; itiraz yoksa geçerli): K−1 yalnız `dep_net ≥ 1000` iken; Telegram'dan devam en erken 24 saat sonra; son taban Telegram'dan açılamaz; kağıt kipinde yalnız gözlem (kağıt ve ikiz durmaz); çekme önce kârdan sayılır; sermaye hareketi yalnız sunucudan girilir; eşikler yapılandırma dosyasında değil kodda.

## 17. Açık noktalar

- **O-1 (mentor, testnet/duman):** [V-8]. Çürürse §7 "cüzdan = yatırılan + gerçekleşen sonuçlar" denetimine çevrilir (11 §15'te ertelenen cüzdan sapma denetimi öne alınır); o güne kadar canlıda kapı `capital_mismatch`/`capital_unverified` ile kapalı kalır, yani hata güvenli taraftadır ama canlı başlangıcını geciktirir.
- **O-2 (mentor):** 11 O-2 (canlı `var_dir`) kararı `ladder_follow` yolunu ve `LADDER_BOTS` değerini belirler.
- **O-3 (mentor, kağıdın 4. haftası):** 250–300 USD'de K0 riskiyle en küçük emir tutarı reddi oranı gerçek kural anlık görüntüsüyle ölçülür; `KM1_MIN_CAPITAL` gerekirse yükseltilir (gevşetme değil).
- **O-4 (belge bakımı):** onaydan sonra `risk-kademe-kurali.md` §1 (tepe değer tanımı), §5 (tetik tanımı) ve §9 madde 1 bu belgeye göre güncellenir; `tasarim-kararlari.md`'ye tek satır; `11-canli-broker.md` §9.4'e `capital_floor` ve `/kademe_devam` ayrıntısı için "12 ile güncellendi" notu.
