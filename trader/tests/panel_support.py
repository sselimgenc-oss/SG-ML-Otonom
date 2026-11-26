"""Panel testleri icin ortak fiksturler (ag yok): defter/butce/saglik/status dosyalari + sunucu yardimcilari."""
from __future__ import annotations

import http.client
import json
import socket
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trader_core import budget as B
from trader_core import ledger as L
from trader_panel.data import PanelData, load_config
from trader_panel.server import make_server

UTC = timezone.utc
ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 16, 18, 0, tzinfo=UTC)          # 21:00 TSI
DAY = "2026-11-16"
PARAMS = {"range_width_atr": 4.0, "vol_ratio_max": 1.5, "edge_zone_atr": 0.25, "pullback_ema": 50,
          "stop_buffer_atr": 0.3, "trail_atr": 3.0, "range_target_frac": 0.75, "rr_min": 1.5, "trigger_tf": "1h"}


def z(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def mkledger(path, bot: str, specs, keep_open: bool = False):
    """specs: [(win, closed, bar_close_ts)]; keep_open=True -> yazar baglantisi acik doner (WAL dosyalari durur)."""
    led = L.open_ledger(path, bot, clock=lambda: NOW)
    led.init_params(PARAMS, reason="x")
    for i, (win, closed, bar) in enumerate(specs, start=1):
        did = led.record_decision(L.DecisionEvent(
            bar_close_ts=bar, trigger_tf="1h", pair="ETH/USDT" if i % 2 else "BTC/USDT", side="long", setup="R1",
            regime="range", atr_ratio=1.1, rh=2100.0, rl=1980.0, rh_touches=2, rl_touches=3,
            features={"atr_1h": 20.0, "stop_dist_atr": 2.0, "atr_4h": 40.0, "wick_ratio": 0.5, "rr": 2.5,
                      "edge_dist_atr": 0.1},
            planned_entry=2000.0, planned_stop=1960.0, planned_target=2100.0, param_version_id=1,
            veto_status="allowed", veto_reason=None, risk_allowed=True, risk_reason="ok", size_qty=0.3,
            size_notional=600.0, size_margin=200.0, size_risk_amount=13.188, leverage=3,
            final_action="entered", skip_reason=None))
        led.record_trade_entry(L.TradeEntry(i, did, bar + timedelta(seconds=3), 2001.0, 0.3, 3, 0.30015))
        if closed:
            px = 2079.0 if win else 1960.0
            led.record_trade_exit(L.TradeExit(i, bar + timedelta(hours=1), px, "target" if win else "stop",
                                              2100.0, 0.3, 0.1))
    if keep_open:
        return led
    led.close()
    return None


def day_specs(day_utc: datetime, pattern):
    return [(w, c, day_utc.replace(hour=6 + i)) for i, (w, c) in enumerate(pattern)]


STD_LEARNER = (day_specs(datetime(2026, 11, 14, tzinfo=UTC), [(True, True), (False, True)])
               + day_specs(datetime(2026, 11, 15, tzinfo=UTC), [(True, True)])
               + day_specs(datetime(2026, 11, 16, tzinfo=UTC), [(True, True), (False, True), (True, False)]))


def status_doc(loop_at: datetime, **kw) -> dict:
    d = {"schema": "engine-status/1", "bot": "learner", "mode": "paper", "pid": 1, "started_at": z(NOW - timedelta(hours=5)),
         "loop_at": z(loop_at), "trigger_tf": "1h", "param_version_id": 1, "strategy": {"name": "price_action_v1", "version": "1"},
         "entries_open": True, "gate": {"ok": True, "code": "ok"}, "kill": False, "kill_state": "off",
         "entries_blocked_reason": None, "dry_run": True, "wallet": 1000.0, "equity": 1003.5, "day_start_equity": 1000.0,
         "open_positions": [{"trade_id": 6, "pair": "ETH/USDT", "side": "long", "qty": 0.3, "entry_price": 2001.0, "stop": 1960.0}],
         "open_trade_ids": [6], "counters": {"entries": 3}}
    d.update(kw)
    return d


class Env:
    """Gecici veri dizini + yapilandirma. Panel yolu: root/var/<bot>/{status.json,ledger.sqlite} ..."""

    def __init__(self, root: Path, *, learner=True, twin=False, budget=True, health=True, status_age_s=5,
                 keep_open=False):
        self.root = root                       # `twin` kabul edilir ama yok sayilir (DD-12: ikiz kaldirildi)
        for d in ("var/learner", "var/twin", "config", "user_data", "shared", "state"):
            (root / d).mkdir(parents=True, exist_ok=True)
        self.writers = []
        if learner:
            w = mkledger(root / "var/learner/ledger.sqlite", "learner", STD_LEARNER, keep_open)
            if w:
                self.writers.append(w)
            self.write_status("learner", status_age_s)
        (root / "config/engine.base.json").write_text(json.dumps({"wallet_start": 1000.0}))
        if budget:
            bj = json.loads((ROOT / "config/budget.json").read_text())
            bj["db_path"] = str(root / "user_data/budget.sqlite")
            (root / "config/budget.json").write_text(json.dumps(bj))
            B.BudgetGuard(B.load_config(root / "config/budget.json")).authorize("haftalik_ozet", 0.01)
        if health:
            (root / "state/state.json").write_text(json.dumps({
                "schema": 1, "restart_counts": {"engine": 1},
                "fingerprints": {"ledger_write_age|stale": {"first_seen": z(NOW - timedelta(hours=1)), "consecutive": 3,
                                                           "alerted": True}},
                "last_overall": "WARN", "last_run_at": z(NOW - timedelta(minutes=3))}))
        self.cfg_path = root / "config/panel.json"
        self.cfg_path.write_text(json.dumps({
            "schema": "panel/1", "host": "127.0.0.1", "port": free_port(),
            "status_path": "var/learner/status.json",
            "ledger_path": "var/learner/ledger.sqlite",
            "budget_config": "config/budget.json",
            "health_state": str(root / "state/state.json"), "kill_file": "shared/KILL",
            "engine_config": "config/engine.base.json"}))

    def write_status(self, bot, age_s, **kw):
        doc = status_doc(NOW - timedelta(seconds=age_s), bot=bot, **kw)
        (self.root / f"var/{bot}/status.json").write_text(json.dumps(doc))

    def close(self):
        for w in self.writers:
            w.close()


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Running:
    """Bellek ici panel sunucusu (saat sabit)."""

    def __init__(self, env: Env, clock=lambda: NOW, **cfg_over):
        self.cfg = load_config(env.cfg_path)
        self.cfg.port = free_port()
        for k, v in cfg_over.items():
            setattr(self.cfg, k, v)
        self.data = PanelData(self.cfg, clock)
        self.srv = make_server(self.cfg, self.data)
        self.port = self.srv.server_address[1]
        self.t = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.t.start()

    def req(self, path, method="GET", host="default", raw=False):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.putrequest(method, path, skip_host=True)
        c.putheader("Host", f"127.0.0.1:{self.port}" if host == "default" else host)
        c.endheaders()
        r = c.getresponse()
        body = r.read()
        hdr = dict(r.getheaders())
        c.close()
        if raw:
            return r.status, hdr, body
        try:
            return r.status, hdr, (json.loads(body) if body else None)
        except ValueError:
            return r.status, hdr, body

    def get(self, path):
        st, _, j = self.req(path)
        assert st == 200, (path, st, j)
        return j

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()
