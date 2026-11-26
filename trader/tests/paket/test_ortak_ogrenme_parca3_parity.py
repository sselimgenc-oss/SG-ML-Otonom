"""Ortak ogrenme paketi parca 3 (spec: docs/standart/ortak-ogrenme-paketi-parca3-spec.md).

Parite: mask / neutralize / fit_text / TelegramClient hata siniflari / Outbox / TelegramNotifier tekrar onleme
ve yeniden deneme -> trader_core.telegram ile ayni girdi, ayni cikti (sahte HTTP + sahte saat).
Davranis: etiketle, bildirici etiketleme, OnayKapisi (120 sn, tek kullanim, yanlis kod, sure, komut, denetim, sha256).
Ag yok: urllib.request.urlopen testte patch'li ve cagrilirsa hata verir.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader_core import telegram as ML

from ortak_ogrenme import telegram_cekirdek as T

UTC = timezone.utc
TOKEN = "123456:SECRET_TOKEN_abc"
CHAT = 555000111
T0 = datetime(2026, 11, 19, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _ag_yok(monkeypatch):
    def _yasak(*a, **k):
        raise AssertionError("testte ag cagrisi yapilamaz")
    monkeypatch.setattr(urllib.request, "urlopen", _yasak)


class Clk:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, sec: float):
        self.t = self.t + timedelta(seconds=sec)


class FakeHTTP:
    """Senaryo: her cagrida siradaki yanit (None = basarili). Istisna nesnesi verilirse fırlatılır."""

    def __init__(self, script=()):
        self.script = list(script)
        self.calls: list[tuple[str, dict | None]] = []
        self._mid = 0

    def __call__(self, url, json=None, timeout=None):
        method = url.rsplit("/", 1)[1]
        self.calls.append((method, json))
        if self.script:
            r = self.script.pop(0)
            if isinstance(r, BaseException):
                raise r
            if r is not None:
                return r
        self._mid += 1
        return 200, {"ok": True, "result": {"message_id": self._mid}}

    def sent_texts(self):
        return [j["text"] for m, j in self.calls if m == "sendMessage"]


def _snapshot(base: Path) -> dict[str, str]:
    out = {}
    for p in sorted(Path(base).rglob("*")):
        if p.is_file():
            out[str(p.relative_to(base))] = p.read_text(encoding="utf-8")
    return out


def _item(clk: Clk, text: str, sev: str, key: str, *, expires_at=None, created=None) -> dict:
    return {"text": text, "severity": sev, "dedup_key": key, "expires_at": expires_at,
            "reply_markup": None, "created_at": (created if created is not None else clk().timestamp())}


# ---------------------------------------------------------------------------
# Metin: mask / neutralize / fit_text
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("metin, token", [
    ("duz metin", None),
    (f"istek bot{TOKEN} ile yapildi", TOKEN),
    ("url bot999:ABC_def-1 satirda", None),
    ("anahtar sk-ant-api03-XYZ_abc burada", None),
    (42, None),
    (None, None),
])
def test_mask_parity(metin, token):
    ours = T.mask(metin, token)
    assert ours == ML.mask(metin, token)
    assert TOKEN not in ours and "sk-ant-" not in ours


@pytest.mark.parametrize("metin", [
    "/durum\nmerhaba\n  /x\n",
    "ilk satir\n/durum ve /rapor\n\x01kontrol\x7f karakteri\x0b",
    "sk-ant-abc123 anahtari\n/yardim",
    "satir\r\nbaska satir",
    "",
])
def test_neutralize_parity(metin):
    assert T.neutralize(metin) == ML.neutralize(metin)


def test_neutralize_slash_lines_get_space_and_controls_removed():
    out = T.neutralize("/durum\nx\x01y")
    assert out.split("\n")[0] == " /durum"
    assert "\x01" not in out


_UZUN = "\n".join(f"satir {i} " + "x" * 50 for i in range(200))


@pytest.mark.parametrize("govde, pinned, limit", [
    ("kisa\nmetin", "", 3500),
    (_UZUN, "/onayla 1\n/reddet 1", 3500),
    ("\n".join(f"s{i} {'y' * 20}" for i in range(30)), "/durdur", 120),
    ("tek " + "z" * 5000, "/onayla r1", 3500),
    ("/durum\n" + "q" * 300 + "\n/rapor", "pin", 200),
])
def test_fit_text_parity(govde, pinned, limit):
    ours = T.fit_text(govde, pinned, limit)
    assert ours == ML.fit_text(govde, pinned, limit)
    assert len(ours) <= limit or ours.endswith(pinned)


def test_fit_text_keeps_pinned_and_default_limit():
    out = T.fit_text(_UZUN, "/onayla 1", T.MAX_TEXT)
    assert out.endswith("\n/onayla 1")
    assert "(kısaltıldı," in out
    assert T.MAX_TEXT == ML.MAX_TEXT == 3500


# ---------------------------------------------------------------------------
# Istemci: hata siniflari
# ---------------------------------------------------------------------------
_YANITLAR = [
    (200, {"ok": True, "result": {"message_id": 1}}),
    (200, {"ok": False, "description": "x"}),
    (429, {"ok": False, "parameters": {"retry_after": 7}, "description": "Too Many"}),
    (429, {"ok": False, "description": "Too Many"}),
    (429, {"ok": False, "parameters": {"retry_after": 999}}),
    (409, {"ok": False, "description": "conflict"}),
    (400, {"ok": False, "description": f"bad bot{TOKEN}"}),
    (401, {"ok": False}),
    (403, {"ok": False}),
    (404, {"ok": False, "description": "not found"}),
    (500, {}),
    (0, {}),
]


def _cagri(mod, yanit):
    http = FakeHTTP([yanit])
    c = mod.TelegramClient(TOKEN, http_post=http, sleep=lambda s: None)
    try:
        return ("ok", c.call("sendMessage", {"chat_id": CHAT, "text": "x"}))
    except mod.TelegramError as e:
        return ("err", e.kind, e.status, e.retry_after, str(e))


@pytest.mark.parametrize("yanit", _YANITLAR)
def test_client_error_class_parity(yanit):
    ours = _cagri(T, yanit)
    ref = _cagri(ML, yanit)
    assert ours == ref
    assert TOKEN not in str(ours)


def test_client_network_exception_parity():
    def boom(url, json=None, timeout=None):
        raise RuntimeError("baglanti")
    with pytest.raises(T.TelegramError) as e1:
        T.TelegramClient(TOKEN, http_post=boom).call("getUpdates", {})
    with pytest.raises(ML.TelegramError) as e2:
        ML.TelegramClient(TOKEN, http_post=boom).call("getUpdates", {})
    assert (e1.value.kind, e1.value.status, str(e1.value)) == (e2.value.kind, e2.value.status, str(e2.value))


def test_client_send_message_without_message_id_is_transient():
    http = FakeHTTP([(200, {"ok": True, "result": {"foo": 1}})])
    with pytest.raises(T.TelegramError) as e:
        T.TelegramClient(TOKEN, http_post=http).send_message(CHAT, "x")
    assert e.value.kind == "transient"


def test_default_http_post_masks_token_and_maps_http_error(monkeypatch):
    def hata(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 429, "x", {},
                                     io.BytesIO(b'{"ok": false, "parameters": {"retry_after": 3}}'))
    monkeypatch.setattr(urllib.request, "urlopen", hata)
    assert T.default_http_post("https://x/", json={"a": 1}, timeout=(1, 2)) == (
        429, {"ok": False, "parameters": {"retry_after": 3}})

    def ag(req, timeout=None):
        raise OSError(f"bot{TOKEN} koptu")
    monkeypatch.setattr(urllib.request, "urlopen", ag)
    assert T.default_http_post("https://x/", json={}, timeout=1, token=TOKEN) == (0, {})


# ---------------------------------------------------------------------------
# Outbox: parite (ayni sahte saat + sahte HTTP, dosya durumu karsilastirilir)
# ---------------------------------------------------------------------------
def _run_outbox(mod, base: Path, script, senaryo):
    clk = Clk()
    http = FakeHTTP(script)
    sleeps: list[float] = []
    client = mod.TelegramClient(TOKEN, http_post=http, sleep=sleeps.append)
    box = mod.Outbox(base, clk)
    extra = senaryo(box, clk, client, sleeps)
    return {"sent": http.sent_texts(), "sleeps": sleeps, "snap": _snapshot(base), "extra": extra}


def _s_sira_tekrar(box, clk, client, sleeps):
    box.enqueue(_item(clk, "bir", "WARN", "k1"))
    box.enqueue(_item(clk, "iki", "CRIT", "k2"))
    box.enqueue(_item(clk, "bir-tekrar", "WARN", "k1"))       # ayni dedup_key: ikinci dosya olmaz
    return [box.drain(client, CHAT, sleeps.append), len(box.list()), len(box.pending_for("k1"))]


def _s_hiz_siniri(box, clk, client, sleeps):
    for i in range(20):
        box.enqueue(_item(clk, f"info {i}", "INFO", f"i{i}"))
        clk.advance(0.001)
    return [box.drain(client, CHAT, sleeps.append), len(box.list())]


def _s_info_yaslanma(box, clk, client, sleeps):
    box.enqueue(_item(clk, "eski info", "INFO", "e1"))
    clk.advance(T.INFO_MAX_AGE_S + 1)
    box.enqueue(_item(clk, "yeni uyari", "WARN", "w1"))
    return [box.drain(client, CHAT, sleeps.append)]


def _s_suresi_dolmus(box, clk, client, sleeps):
    box.enqueue(_item(clk, "gecersiz", "WARN", "x1", expires_at=clk().timestamp() + 10))
    box.enqueue(_item(clk, "gecerli", "WARN", "x2"))
    clk.advance(20)
    return [box.drain(client, CHAT, sleeps.append)]


def _s_tekrar_onleme(box, clk, client, sleeps):
    box.mark_sent("tekrar", clk().timestamp() + 300)
    box.enqueue(_item(clk, "engelli", "WARN", "tekrar"))
    before = box.sent_recently("tekrar")
    d1 = box.drain(client, CHAT, sleeps.append)
    clk.advance(301)
    return [before, d1, box.sent_recently("tekrar")]


def _s_429_bekle(box, clk, client, sleeps):
    for i in range(3):
        box.enqueue(_item(clk, f"m{i}", "WARN", f"r{i}"))
    return [box.drain(client, CHAT, sleeps.append), len(box.list())]


def _s_kalici_hata(box, clk, client, sleeps):
    box.enqueue(_item(clk, "a", "WARN", "p1"))
    box.enqueue(_item(clk, "b", "WARN", "p2"))
    return [box.drain(client, CHAT, sleeps.append), len(box.list())]


_OUTBOX_SENARYO = [
    ("sira_ve_tekrar", None, _s_sira_tekrar),
    ("hiz_siniri", None, _s_hiz_siniri),
    ("info_yaslanma", None, _s_info_yaslanma),
    ("suresi_dolmus", None, _s_suresi_dolmus),
    ("tekrar_onleme", None, _s_tekrar_onleme),
    ("429_bekle", [None, (429, {"ok": False, "parameters": {"retry_after": 7}})], _s_429_bekle),
]


@pytest.mark.parametrize("ad, script, senaryo", _OUTBOX_SENARYO, ids=[x[0] for x in _OUTBOX_SENARYO])
def test_outbox_parity(tmp_path, ad, script, senaryo):
    ours = _run_outbox(T, tmp_path / "ours", script or [], senaryo)
    ref = _run_outbox(ML, tmp_path / "ml", script or [], senaryo)
    assert ours == ref


def test_outbox_kalici_hata_bilincli_sapma(tmp_path):
    """9a-03: trader_core.telegram kalici hatali ogeyi rejected/ altina tasir ve siradakine gecer; paket cekirdegi eski davranista
    (dur, oge basta kalir). Sapma bilincli: parite listesinden cikarildi."""
    script = [(400, {"ok": False, "description": "bad"})]
    ml = _run_outbox(ML, tmp_path / "ml", script, _s_kalici_hata)
    ours = _run_outbox(T, tmp_path / "ours", script, _s_kalici_hata)
    assert ours["extra"] == [0, 2] and ours["sleeps"] == []
    assert ml["extra"] == [1, 0] and ml["sleeps"] == [1.0]
    assert any("rejected/" in k for k in ml["snap"])


def test_outbox_scenarios_have_expected_behaviour(tmp_path):
    # parite testlerinin anlamli olmasi icin: hiz siniri senaryosunun beklenen sonucu
    for mod, ad in ((ML, "ml_hiz"), (T, "ours_hiz")):
        r = _run_outbox(mod, tmp_path / ad, [], _s_hiz_siniri)
        assert r["extra"] == [14, 0]        # 14 INFO gonderildi, 6 INFO tek ozete birlestirildi; kuyruk bos
        assert r["sent"][0] == "6 mesaj birlestirildi"
        assert len(r["sent"]) == 15         # 1 ozet + 14 INFO
    r = _run_outbox(T, tmp_path / "ours_429", [None, (429, {"ok": False, "parameters": {"retry_after": 7}})],
                    _s_429_bekle)
    assert r["sleeps"] == [1.0, 7.0] and r["extra"] == [1, 2]
    r = _run_outbox(T, tmp_path / "ours_kalici", [(400, {"ok": False, "description": "bad"})], _s_kalici_hata)
    assert r["extra"] == [0, 2] and r["sleeps"] == []


@pytest.mark.parametrize("mod", [T, ML], ids=["ortak", "trader_core"])
def test_outbox_limit_drops_info_then_warn(tmp_path, monkeypatch, mod):
    monkeypatch.setattr(mod, "SPOOL_MAX_FILES", 3)
    clk = Clk()
    box = mod.Outbox(tmp_path, clk)
    for ad, sev, key in (("a", "INFO", "l1"), ("b", "WARN", "l2"), ("c", "INFO", "l3"), ("d", "CRIT", "l4")):
        box.enqueue(_item(clk, ad, sev, key))
        clk.advance(1)                                        # dosya adi zamana gore: sirayi belirle
    kalan = sorted(json.loads(p.read_text())["text"] for p in box.list())
    assert kalan == ["b", "c", "d"] and box.dropped == 1


# ---------------------------------------------------------------------------
# Bildirici: parite (etiketsiz govde) + etiketleme
# ---------------------------------------------------------------------------
def _run_notifier(mod, base: Path, script, proje):
    clk = Clk()
    http = FakeHTTP(script)
    sleeps: list[float] = []
    client = mod.TelegramClient(TOKEN, http_post=http, sleep=sleeps.append)
    box = mod.Outbox(base, clk)
    if proje is None:
        bildirici = mod.TelegramNotifier(client, CHAT, box, clk, sleep=sleeps.append)
    else:
        bildirici = mod.TelegramNotifier(client, CHAT, box, clk, proje, sleep=sleeps.append)
    r = [
        bildirici.send_text("Giriş: BTC long\nstop 64000", "INFO", "g1"),
        bildirici.send_text("Giriş: BTC long\nstop 64000", "INFO", "g1"),     # tekrar: gonderilmez, True
        bildirici.send_text("Çıkış\n/durum", "WARN", "c1"),                  # 4 deneme basarisiz -> kuyruk
    ]
    kuyruk_adlari = [p.name[21:] for p in box.list()]                      # ns oneki atilir; hash kalir
    r.append(box.drain(client, CHAT, sleeps.append))
    return {"r": r, "sent": http.sent_texts(), "sleeps": sleeps, "names": kuyruk_adlari}


def test_notifier_parity_after_removing_tag(tmp_path):
    script = [None, (500, {}), (500, {}), (500, {}), (500, {})]   # r1 ok; r2 dedup (istek yok); r3 4 deneme
    ours = _run_notifier(T, tmp_path / "ours", list(script), "1L3A")
    ref = _run_notifier(ML, tmp_path / "ml", list(script), None)
    assert ours["r"] == ref["r"] == [True, True, False, 1]
    assert ours["sleeps"] == ref["sleeps"] == [2, 5, 15, 1.0]
    assert ours["names"] == ref["names"]
    assert [s.removeprefix("[1L3A] ") for s in ours["sent"]] == [s.removeprefix("[ML] ") for s in ref["sent"]]   # 19 Kasim: ML de etiketli
    assert all(s.startswith("[1L3A] ") for s in ours["sent"])


@pytest.mark.parametrize("proje", list(T.PROJELER))
def test_notifier_tags_every_message(tmp_path, proje):
    clk = Clk()
    http = FakeHTTP()
    box = T.Outbox(tmp_path, clk)
    bildirici = T.TelegramNotifier(T.TelegramClient(TOKEN, http_post=http), CHAT, box, clk, proje)
    assert bildirici.send_text("merhaba", "INFO", f"k-{proje}")
    assert http.sent_texts() == [f"[{proje}] merhaba"]


def test_notifier_does_not_double_tag(tmp_path):
    clk = Clk()
    http = FakeHTTP()
    box = T.Outbox(tmp_path, clk)
    bildirici = T.TelegramNotifier(T.TelegramClient(TOKEN, http_post=http), CHAT, box, clk, "CT")
    bildirici.send_text("[CT] zaten etiketli", "INFO", "d1")
    assert http.sent_texts() == ["[CT] zaten etiketli"]


def test_notifier_unknown_project_rejected(tmp_path):
    clk = Clk()
    box = T.Outbox(tmp_path, clk)
    client = T.TelegramClient(TOKEN, http_post=FakeHTTP())
    with pytest.raises(ValueError):
        T.TelegramNotifier(client, CHAT, box, clk, "XX")


def test_notifier_spooled_text_is_tagged(tmp_path):
    clk = Clk()
    http = FakeHTTP([(400, {"ok": False, "description": "bad"})])
    box = T.Outbox(tmp_path, clk)
    bildirici = T.TelegramNotifier(T.TelegramClient(TOKEN, http_post=http), CHAT, box, clk, "ML")
    assert bildirici.send_text("kuyruga", "CRIT", "q1") is False
    kayit = json.loads(box.pending_for("q1")[0].read_text())
    assert kayit["text"] == "[ML] kuyruga"


def test_notifier_dedup_key_and_severity_validation(tmp_path):
    clk = Clk()
    box = T.Outbox(tmp_path, clk)
    bildirici = T.TelegramNotifier(T.TelegramClient(TOKEN, http_post=FakeHTTP()), CHAT, box, clk, "ML")
    with pytest.raises(ValueError):
        bildirici.send_text("x", "INFO", "")
    with pytest.raises(ValueError):
        bildirici.send_text("x", "DEBUG", "k")


# ---------------------------------------------------------------------------
# etiketle
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("proje", ["ML", "1L3A", "CT"])
def test_etiketle_prefix(proje):
    assert T.etiketle(proje, "metin") == f"[{proje}] metin"


def test_etiketle_idempotent_and_multiline():
    assert T.etiketle("ML", "[ML] zaten") == "[ML] zaten"
    assert T.etiketle("ML", "satir1\nsatir2") == "[ML] satir1\nsatir2"
    assert T.etiketle("ML", T.etiketle("ML", "x")) == "[ML] x"


@pytest.mark.parametrize("proje", ["", "ml", "XX", "1L3A ", None])
def test_etiketle_unknown_project_value_error(proje):
    with pytest.raises(ValueError):
        T.etiketle(proje, "x")


def test_etiketle_tag_survives_fit_text():
    govde = T.etiketle("1L3A", "\n".join(f"satir {i} " + "x" * 60 for i in range(100)))
    out = T.fit_text(govde, "/durdur", 300)
    assert out.startswith("[1L3A] satir 0")
    assert out.endswith("\n/durdur")


# ---------------------------------------------------------------------------
# OnayKapisi
# ---------------------------------------------------------------------------
class FakeRng:
    def __init__(self, *degerler):
        self.degerler = list(degerler)
        self.sorgular: list[int] = []

    def randbelow(self, n):
        self.sorgular.append(n)
        return self.degerler.pop(0)


def _denetim(dosya: Path) -> list[dict]:
    yol = dosya.with_name(dosya.stem + ".denetim.jsonl")
    return [json.loads(s) for s in yol.read_text(encoding="utf-8").splitlines()]


def test_onay_correct_code_within_120s_ok_once(tmp_path):
    clk = Clk()
    dosya = tmp_path / "onay.json"
    onay = T.OnayKapisi(dosya, clk, rng=FakeRng(42))
    kod = onay.baslat("/durdur", "Yeni girişler durdurulacak")
    assert kod == "0042"
    clk.advance(119)
    assert onay.dogrula("/durdur", "0042") is True
    assert onay.dogrula("/durdur", "0042") is False          # tek kullanimlik
    assert not dosya.exists()


def test_onay_exactly_120s_still_valid_121s_expired(tmp_path):
    clk = Clk()
    onay = T.OnayKapisi(tmp_path / "a.json", clk, rng=FakeRng(1234))
    onay.baslat("/durdur", "x")
    clk.advance(120)
    assert onay.dogrula("/durdur", "1234") is True
    clk = Clk()
    onay = T.OnayKapisi(tmp_path / "b.json", clk, rng=FakeRng(5678))
    onay.baslat("/durdur", "x")
    clk.advance(121)
    assert onay.dogrula("/durdur", "5678") is False


def test_onay_wrong_code_clears_pending(tmp_path):
    clk = Clk()
    dosya = tmp_path / "onay.json"
    onay = T.OnayKapisi(dosya, clk, rng=FakeRng(4217))
    onay.baslat("/hepsini_kapat", "tum pozisyonlar")
    assert onay.dogrula("/hepsini_kapat", "0000") is False
    assert not dosya.exists()
    assert onay.dogrula("/hepsini_kapat", "4217") is False   # yanlis kodla iptal edilmis; dogru kod da artik gecersiz
    assert [r["sonuc"] for r in _denetim(dosya)] == ["kod_uretildi", "yanlis_kod", "bekleyen_yok"]


def test_onay_expiry_clears_pending(tmp_path):
    clk = Clk()
    dosya = tmp_path / "onay.json"
    onay = T.OnayKapisi(dosya, clk, rng=FakeRng(999))
    onay.baslat("/devam", "x")
    clk.advance(500)
    assert onay.dogrula("/devam", "0999") is False
    assert not dosya.exists()
    assert _denetim(dosya)[-1]["sonuc"] == "suresi_doldu"


def test_onay_different_command_rejected_and_pending_kept(tmp_path):
    clk = Clk()
    dosya = tmp_path / "onay.json"
    onay = T.OnayKapisi(dosya, clk, rng=FakeRng(4217))
    onay.baslat("/durdur", "x")
    assert onay.dogrula("/devam", "4217") is False
    assert dosya.exists()
    assert onay.dogrula("/durdur", "4217") is True
    assert [r["sonuc"] for r in _denetim(dosya)] == ["kod_uretildi", "komut_uyusmadi", "onaylandi"]


def test_onay_new_request_replaces_old(tmp_path):
    onay = T.OnayKapisi(tmp_path / "onay.json", Clk(), rng=FakeRng(1111, 2222))
    onay.baslat("/durdur", "x")
    onay.baslat("/durdur", "y")
    assert onay.dogrula("/durdur", "1111") is False          # eski kod artik gecersiz


def test_onay_latest_code_of_replaced_request_works(tmp_path):
    onay = T.OnayKapisi(tmp_path / "onay.json", Clk(), rng=FakeRng(1111, 2222))
    onay.baslat("/durdur", "x")
    onay.baslat("/durdur", "y")
    assert onay.dogrula("/durdur", "2222") is True


def test_onay_non_numeric_or_missing_code_rejected(tmp_path):
    clk = Clk()
    dosya = tmp_path / "onay.json"
    onay = T.OnayKapisi(dosya, clk, rng=FakeRng(7))
    onay.baslat("/durdur", "x")
    assert onay.dogrula("/durdur", None) is False
    assert not dosya.exists()


def test_onay_no_pending(tmp_path):
    onay = T.OnayKapisi(tmp_path / "onay.json", Clk(), rng=FakeRng())
    assert onay.dogrula("/durdur", "0001") is False
    assert _denetim(tmp_path / "onay.json")[0]["sonuc"] == "bekleyen_yok"


def test_onay_only_sha256_stored(tmp_path):
    clk = Clk()
    dosya = tmp_path / "onay.json"
    onay = T.OnayKapisi(dosya, clk, rng=FakeRng(4217))
    onay.baslat("/durdur", "Yeni girişler durdurulacak")
    metin = dosya.read_text(encoding="utf-8")
    kayit = json.loads(metin)
    assert kayit["kod_sha256"] == hashlib.sha256(b"4217").hexdigest()
    assert re.fullmatch(r"[0-9a-f]{64}", kayit["kod_sha256"])
    assert "4217" not in metin
    assert "4217" not in (dosya.with_name("onay.denetim.jsonl")).read_text(encoding="utf-8")


def test_onay_audit_lines_have_fields(tmp_path):
    clk = Clk()
    dosya = tmp_path / "onay.json"
    onay = T.OnayKapisi(dosya, clk, rng=FakeRng(4217, 4218))
    onay.baslat("/durdur", "x")
    onay.dogrula("/devam", "4217")
    onay.dogrula("/durdur", "4217")
    satirlar = _denetim(dosya)
    assert len(satirlar) == 3
    for r in satirlar:
        assert set(r) == {"zaman", "olay", "komut", "sonuc"}
        assert r["zaman"] == "2026-11-19T09:00:00.000Z"
    assert [(r["olay"], r["komut"]) for r in satirlar] == [
        ("baslat", "/durdur"), ("dogrula", "/devam"), ("dogrula", "/durdur")]


def test_onay_default_rng_yields_4_digit_codes(tmp_path):
    onay = T.OnayKapisi(tmp_path / "onay.json", Clk())
    for _ in range(50):
        kod = onay.baslat("/durdur", "x")
        assert re.fullmatch(r"\d{4}", kod)
        onay.dogrula("/durdur", "x" * 4)                       # bekleyeni temizle
