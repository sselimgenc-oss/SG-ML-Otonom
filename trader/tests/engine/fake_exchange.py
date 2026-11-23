"""Sahte Binance vadeli borsasi (11 §2; 07 §4.5 kuru.py uyarlamasi). HTTP duzeyinde: `FakeExchange.session`, SignedRestClient'a
`session=` olarak verilir; imza/zaman damgasi gercekten dogrulanir. Belirlenimli: saat `now_ms` ile enjekte, rastgelelik yok.

Kapsam: positionRisk, account, openOrders, algo/classic kosullu emirler (MARK_PRICE tetik), userTrades, income, apiRestrictions,
exchangeInfo, commissionRate, premiumIndex, hesap kipi uclari. Arıza enjeksiyonu: `inject(path, response_or_exception)`.
Test yardimcilari: set_mark, liquidate, external_close, add_funding, fill_market.

Anahtarlar (varsayilan = temkinli/gercekci olan; yeni anahtarlar T-02/T-07 testnet sonuclariyla sabitlenir):
  * child_cid_mode        "auto" (varsayilan, TEMKINLI): tetiklenen algo emrinin cocuk emri otomatik kimlik alir ("same": stop kimligi;
                          classic kipte stop emrinin kendisi doldugundan her zaman ayni kimlik)
  * reduce_only_mode      "reject" (varsayilan: -2022) | "clip" (reduceOnly piyasa emri pozisyona kirpilir)
  * stop_after_close      "keep" (varsayilan: kapanistan sonra bekleyen reduceOnly stop NEW kalir) | "expire" (EXPIRED olur)
  * immediate_trigger     "reject" (varsayilan: -2021) | "accept_then_trigger" (NEW kabul edilir, hemen tetiklenir)
  * market_parts          piyasa emri dolumunun kac islem satirina bolunecegi (ayni orderId)
  * hide_rules            exchangeInfo'dan cikarilacak semboller (kural eksik testleri)
  * liquidation_queryable False: likidasyon emri GET /fapi/v1/order?orderId ile -2013 verir (yalniz forceOrders bulur)
Acik pozisyonla marginType -> -4048, acik emirle -4047, kaldirac dusurme -> -4161; GET /fapi/v1/forceOrders.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from decimal import ROUND_FLOOR, Decimal
from urllib.parse import parse_qsl, urlparse

D = Decimal
SECRET = "FAKE-SECRET-0123456789abcdef0123456789"
KEY = "FAKE-KEY-0123456789abcdef0123456789abc"


class FakeResp:
    def __init__(self, status: int, body, headers: dict | None = None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.text = json.dumps(body)

    def json(self):
        return self._body


def _err(code: int, msg: str = "", status: int = 400) -> FakeResp:
    return FakeResp(status, {"code": code, "msg": msg or f"error {code}"})


class FakeExchange:
    def __init__(self, now_ms: Callable[[], int], symbols: dict[str, dict] | None = None, taker_rate: str = "0.0004",
                 wallet: str = "100", secret: str = SECRET, api_key: str = KEY, classic: bool = False):
        self.now_ms, self.secret, self.api_key, self.classic = now_ms, secret, api_key, classic
        self.taker = D(taker_rate)
        self.wallet = D(wallet)
        self.symbols = symbols or {"XRPUSDT": {"tick": "0.0001", "step": "0.1", "notional": "5"},
                                   "DOGEUSDT": {"tick": "0.00001", "step": "1", "notional": "5"}}
        self.marks: dict[str, Decimal] = {s: D("2.0") for s in self.symbols}
        self.pos: dict[str, dict] = {}
        self.lev: dict[str, int] = {s: 20 for s in self.symbols}
        self.margin_type: dict[str, str] = {s: "cross" for s in self.symbols}
        self.dual, self.multi = False, False
        self.orders: dict[str, dict] = {}              # clientOrderId -> normal emir
        self.algos: dict[str, dict] = {}               # clientAlgoId -> kosullu emir
        self.trades: list[dict] = []
        self.incomes: list[dict] = []
        self.restrictions = {"enableReading": True, "enableFutures": True, "enableWithdrawals": False,
                             "enableInternalTransfer": False, "permitsUniversalTransfer": False, "ipRestrict": True}
        self.restrictions_status = 200
        self.requests: list[tuple[str, str, dict]] = []
        self._inject: list[tuple[str, object]] = []
        self._oid = 1000
        self._tid = 0
        self.can_trade = True
        self.child_cid_mode = "auto"
        self.reduce_only_mode = "reject"
        self.stop_after_close = "keep"
        self.immediate_trigger = "reject"
        self.market_parts = 1
        self.hold_market = False                         # True: reduceOnly piyasa emri NEW kalir (dolmaz) -> release_market(cid) doldurur
        self.hide_trades_oids: set[int] = set()          # userTrades gecikmesi: bu orderId'lerin islemleri gizlenir
        self.hide_rules: set[str] = set()
        self.liquidation_queryable = True
        self.force_rows: list[dict] = []
        self.session = self                              # SignedRestClient(session=fake.session)

    # ------------------------------------------------------------------ test yardimcilari
    def inject(self, path_part: str, resp_or_exc) -> None:
        """Yol parcasini iceren siradaki istege FakeResp/istisna dondur (bir kez)."""
        self._inject.append((path_part, resp_or_exc))

    def count(self, path_part: str, method: str | None = None) -> int:
        return sum(1 for m, p, _ in self.requests if path_part in p and (method is None or m == method))

    def set_mark(self, symbol: str, price) -> None:
        self.marks[symbol] = D(str(price))
        for cid, a in sorted(self.algos.items(), key=lambda kv: kv[1]["algoId"]):
            if a["algoStatus"] == "NEW" and a["symbol"] == symbol and self._hit(a, self.marks[symbol]):
                self._trigger(a)

    def add_funding(self, symbol: str, income: str, time_ms: int | None = None) -> None:
        self.incomes.append({"symbol": symbol, "incomeType": "FUNDING_FEE", "income": str(income), "asset": "USDT",
                             "time": time_ms or self.now_ms(), "tranId": 7000 + len(self.incomes)})

    def liquidate(self, symbol: str, price) -> None:
        p = self.pos.get(symbol)
        if p:
            oid = self._fill(symbol, "SELL" if p["amt"] > 0 else "BUY", abs(p["amt"]), D(str(price)), "autoclose-1234", True)
            self.force_rows.append({"orderId": oid, "symbol": symbol, "clientOrderId": "autoclose-1234",
                                    "autoCloseType": "LIQUIDATION", "time": self.now_ms()})

    def fill_market(self, symbol: str, side: str, qty, cid: str = "web_manual", parts: int = 1, price=None) -> int:
        """Disaridan (web/baska istemci) piyasa dolumu: reduceOnly degil; `parts` islem satirina bolunur."""
        return self._fill(symbol, side, D(str(qty)), D(str(price)) if price is not None else self.marks[symbol], cid, False,
                          parts=parts)

    def external_close(self, symbol: str, cid: str = "web_manual") -> None:
        p = self.pos.get(symbol)
        if p:
            self._fill(symbol, "SELL" if p["amt"] > 0 else "BUY", abs(p["amt"]), self.marks[symbol], cid, True)

    # ------------------------------------------------------------------ cekirdek
    def _hit(self, a: dict, mark: Decimal) -> bool:
        trig, sell = a["triggerPrice"], a["side"] == "SELL"
        if a["type"] == "STOP_MARKET":
            return mark <= trig if sell else mark >= trig
        return mark >= trig if sell else mark <= trig

    def _trigger(self, a: dict) -> None:
        p = self.pos.get(a["symbol"])
        a["algoStatus"] = "TRIGGERED"
        if a.get("reduce", True):
            qty = min(a["qty"], abs(p["amt"])) if p else D(0)
        else:
            qty = a["qty"]                                   # reduceOnly olmayan stop ters pozisyon acabilir
        if qty > 0:
            cid = a["cid"] if (self.child_cid_mode == "same" or self.classic) else f"algo_auto_{a['algoId']}"
            a["actualOrderId"] = self._fill(a["symbol"], a["side"], qty, self.marks[a["symbol"]], cid, a.get("reduce", True),
                                            via_algo=a)

    def _parts(self, symbol: str, qty: Decimal, parts: int) -> list[Decimal]:
        if parts <= 1:
            return [qty]
        step = D(self.symbols[symbol]["step"])
        each = floor_dec(qty / parts, step)
        if each <= 0:
            return [qty]
        out = [each] * (parts - 1)
        out.append(qty - each * (parts - 1))
        return out

    def _fill(self, symbol: str, side: str, qty: Decimal, price: Decimal, cid: str, reduce: bool, via_algo=None,
              parts: int = 1) -> int:
        self._oid += 1
        oid = self._oid
        now = self.now_ms()
        sign = D(1) if side == "BUY" else D(-1)
        p = self.pos.setdefault(symbol, {"amt": D(0), "entry": D(0), "upd": now})
        for part in self._parts(symbol, qty, parts):
            old = p["amt"]
            new = old + sign * part
            if old == 0 or (old > 0) == (sign > 0):
                tot = abs(old) + part
                p["entry"] = (p["entry"] * abs(old) + price * part) / tot if tot else D(0)
            elif old * new < 0:
                p["entry"] = price                              # ters pozisyona gecis
            pnl = D(0)
            if old != 0 and (old > 0) != (sign > 0):
                pnl = (price - p["entry"]) * min(part, abs(old)) * (1 if old > 0 else -1)
            p["amt"], p["upd"] = new, now
            if new == 0:
                p["entry"] = D(0)
            fee = part * price * self.taker
            self.wallet += pnl - fee
            self._tid += 1
            self.trades.append({"id": self._tid, "orderId": oid, "symbol": symbol, "side": side, "price": str(price),
                                "qty": str(part), "quoteQty": str(price * part), "commission": str(fee),
                                "commissionAsset": "USDT", "realizedPnl": str(pnl), "time": now})
        if p["amt"] == 0 and self.stop_after_close == "expire":
            for a in self.algos.values():
                if a["symbol"] == symbol and a["algoStatus"] == "NEW":
                    a["algoStatus"] = "EXPIRED"
        row = self.orders.setdefault(cid, {"clientOrderId": cid, "symbol": symbol, "side": side, "type": "MARKET",
                                           "reduceOnly": reduce, "origQty": str(qty), "time": now})
        row.update(orderId=oid, status="FILLED", executedQty=str(qty), avgPrice=str(price), cumQuote=str(price * qty),
                   updateTime=now)
        return oid

    def release_market(self, cid: str) -> None:
        """hold_market ile NEW tutulan piyasa emrini simdiki mark'tan doldurur."""
        o = self.orders[cid]
        assert o["status"] == "NEW"
        self._fill(o["symbol"], o["side"], D(o["origQty"]), self.marks[o["symbol"]], cid, True)

    # ------------------------------------------------------------------ HTTP
    def request(self, method: str, url: str, headers=None, timeout=None):
        u = urlparse(url)
        q = dict(parse_qsl(u.query, keep_blank_values=True))
        path = u.path
        self.requests.append((method, path, q))
        for i, (part, r) in enumerate(self._inject):
            if part in path:
                del self._inject[i]
                if isinstance(r, Exception):
                    raise r
                return r
        signed = path not in ("/fapi/v1/time", "/fapi/v1/exchangeInfo", "/fapi/v1/premiumIndex")
        if signed:
            bad = self._auth(q, u.query, headers or {})
            if bad:
                return bad
        h = self._route(method, path, q)
        if isinstance(h, FakeResp):
            h.headers.setdefault("X-MBX-USED-WEIGHT-1M", "10")
            return h
        return FakeResp(200, h, {"X-MBX-USED-WEIGHT-1M": "10"})

    def _auth(self, q: dict, raw: str, headers: dict) -> FakeResp | None:
        if headers.get("X-MBX-APIKEY") != self.api_key:
            return _err(-2015, "Invalid API-key", 401)
        sig = q.get("signature", "")
        body = raw.rsplit("&signature=", 1)[0]
        if not hmac.compare_digest(sig, hmac.new(self.secret.encode(), body.encode(), hashlib.sha256).hexdigest()):
            return _err(-1022, "Signature for this request is not valid.")
        ts, rw = int(q.get("timestamp", 0)), int(q.get("recvWindow", 5000))
        if not (self.now_ms() - rw < ts <= self.now_ms() + 1000):
            return _err(-1021, "Timestamp for this request is outside of the recvWindow.")
        return None

    def _row(self, o: dict) -> dict:
        return dict(o)

    def _pr(self, s: str) -> dict:
        p = self.pos.get(s, {"amt": D(0), "entry": D(0), "upd": 0})
        m = self.marks[s]
        return {"symbol": s, "positionAmt": str(p["amt"]), "entryPrice": str(p["entry"]), "markPrice": str(m),
                "unRealizedProfit": str((m - p["entry"]) * p["amt"]) if p["amt"] else "0", "liquidationPrice": "0",
                "leverage": str(self.lev[s]), "marginType": self.margin_type[s], "isolatedMargin": "0",
                "positionSide": "BOTH", "updateTime": p["upd"]}

    def _unreal(self) -> Decimal:
        return sum(((self.marks[s] - p["entry"]) * p["amt"] for s, p in self.pos.items() if p["amt"]), D(0))

    def _route(self, method: str, path: str, q: dict):
        sym = q.get("symbol")
        if path == "/fapi/v1/time":
            return {"serverTime": self.now_ms()}
        if path == "/fapi/v1/exchangeInfo":
            return {"symbols": [{"symbol": s, "status": "TRADING", "contractType": "PERPETUAL", "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": v["tick"]},
                {"filterType": "LOT_SIZE", "stepSize": v["step"], "minQty": v["step"], "maxQty": "1000000"},
                {"filterType": "MARKET_LOT_SIZE", "stepSize": v["step"], "minQty": v["step"], "maxQty": "1000000"},
                {"filterType": "MIN_NOTIONAL", "notional": v["notional"]}]} for s, v in self.symbols.items()
                if s not in self.hide_rules]}
        if path == "/fapi/v1/premiumIndex":
            return {"symbol": sym, "markPrice": str(self.marks[sym])}
        if path == "/sapi/v1/account/apiRestrictions":
            return FakeResp(self.restrictions_status, dict(self.restrictions))
        if path == "/fapi/v2/account":
            un = self._unreal()
            return {"canTrade": self.can_trade, "totalWalletBalance": str(self.wallet), "totalUnrealizedProfit": str(un),
                    "totalMarginBalance": str(self.wallet + un), "totalInitialMargin": "0",
                    "availableBalance": str(self.wallet)}
        if path == "/fapi/v2/positionRisk":
            return [self._pr(s) for s in self.symbols if sym in (None, s)]
        if path == "/fapi/v1/positionSide/dual":
            if method == "POST":
                self.dual = q["dualSidePosition"] == "true"
                return {"code": 200, "msg": "success"}
            return {"dualSidePosition": self.dual}
        if path == "/fapi/v1/multiAssetsMargin":
            if method == "POST":
                self.multi = q["multiAssetsMargin"] == "true"
                return {"code": 200, "msg": "success"}
            return {"multiAssetsMargin": self.multi}
        if path == "/fapi/v1/marginType":
            want = q["marginType"].lower()
            if self.margin_type[sym] == want:
                return _err(-4046, "No need to change margin type.")
            if self.pos.get(sym, {"amt": D(0)})["amt"] != 0:
                return _err(-4048, "Margin type cannot be changed if there exists position.")
            if any(o.get("status") == "NEW" and o["symbol"] == sym for o in self.orders.values()) or \
                    any(a["algoStatus"] == "NEW" and a["symbol"] == sym for a in self.algos.values()):
                return _err(-4047, "Margin type cannot be changed if there exists open orders.")
            self.margin_type[sym] = want
            return {"code": 200, "msg": "success"}
        if path == "/fapi/v1/leverage":
            new_lev = int(q["leverage"])
            if self.pos.get(sym, {"amt": D(0)})["amt"] != 0 and new_lev < self.lev[sym]:
                return _err(-4161, "Leverage reduction is not supported in Isolated Margin Mode with open positions.")
            self.lev[sym] = new_lev
            return {"symbol": sym, "leverage": self.lev[sym]}
        if path == "/fapi/v1/commissionRate":
            return {"symbol": sym, "takerCommissionRate": str(self.taker), "makerCommissionRate": "0.0002"}
        if path == "/fapi/v1/openOrders":
            rows = [o for o in self.orders.values() if o.get("status") == "NEW" and sym in (None, o["symbol"])]
            if self.classic:
                rows += [self._classic(a) for a in self.algos.values() if a["algoStatus"] == "NEW" and sym in (None, a["symbol"])]
            return rows
        if path == "/fapi/v1/openAlgoOrders":
            return [self._algo_row(a) for a in self.algos.values() if a["algoStatus"] == "NEW" and sym in (None, a["symbol"])]
        if path == "/fapi/v1/userTrades":
            lo, hi = int(q.get("startTime", 0)), int(q.get("endTime", 1 << 62))
            return [t for t in self.trades if t["symbol"] == sym and lo <= t["time"] <= hi
                    and t["orderId"] not in self.hide_trades_oids][:int(q.get("limit", 500))]
        if path == "/fapi/v1/income":
            lo, hi = int(q.get("startTime", 0)), int(q.get("endTime", 1 << 62))
            return [i for i in self.incomes if i["symbol"] == sym and i["incomeType"] == q.get("incomeType")
                    and lo <= i["time"] <= hi]
        if path == "/fapi/v1/forceOrders":
            lo = int(q.get("startTime", 0))
            return [r for r in self.force_rows if r["symbol"] == sym and r["time"] >= lo
                    and r["autoCloseType"] == q.get("autoCloseType", "LIQUIDATION")]
        if path == "/fapi/v1/order":
            return self._order(method, q)
        if path == "/fapi/v1/algoOrder":
            return self._algo(method, q)
        return _err(-5000, "unknown path " + path, 404)

    # ------------------------------------------------------------------ emirler
    def _algo_row(self, a: dict) -> dict:
        r = {"algoId": a["algoId"], "clientAlgoId": a["cid"], "symbol": a["symbol"], "side": a["side"], "type": a["type"],
             "algoType": "CONDITIONAL", "quantity": str(a["qty"]), "triggerPrice": str(a["triggerPrice"]),
             "workingType": a["workingType"], "reduceOnly": a.get("reduce", True), "algoStatus": a["algoStatus"],
             "createTime": a["time"], "updateTime": a["time"]}
        if "actualOrderId" in a:
            r["actualOrderId"] = a["actualOrderId"]
        return r

    def _classic(self, a: dict) -> dict:
        return {"orderId": a.get("actualOrderId", a["algoId"]), "clientOrderId": a["cid"], "symbol": a["symbol"], "side": a["side"],
                "type": a["type"], "origType": a["type"], "origQty": str(a["qty"]), "stopPrice": str(a["triggerPrice"]),
                "workingType": a["workingType"], "reduceOnly": a.get("reduce", True), "status": "FILLED" if a["algoStatus"] == "TRIGGERED" else a["algoStatus"],
                "time": a["time"], "updateTime": a["time"]}

    def _check_qty(self, sym: str, qty: Decimal):
        step = D(self.symbols[sym]["step"])
        if qty <= 0 or (qty / step) != (qty / step).to_integral_value():
            return _err(-1111, "Precision is over the maximum defined for this asset.")
        return None

    def _order(self, method: str, q: dict):
        cid = q.get("newClientOrderId") or q.get("origClientOrderId")
        if method == "POST":
            sym, side = q["symbol"], q["side"]
            qty = D(q["quantity"])
            if cid in self.orders and self.orders[cid].get("status") == "NEW":
                return _err(-4116, "ClientOrderId is duplicated.")
            bad = self._check_qty(sym, qty)
            if bad:
                return bad
            reduce = q.get("reduceOnly") == "true"
            p = self.pos.get(sym, {"amt": D(0)})
            if q["type"] != "MARKET":
                return self._post_classic(q, cid)
            if reduce:
                if p["amt"] == 0 or (p["amt"] > 0) == (side == "BUY"):
                    return _err(-2022, "ReduceOnly Order is rejected.")
                if qty > abs(p["amt"]):
                    if self.reduce_only_mode != "clip":
                        return _err(-2022, "ReduceOnly Order is rejected.")
                    qty = abs(p["amt"])
            elif qty * self.marks[sym] < D(self.symbols[sym]["notional"]):
                return _err(-4164, "Order's notional must be no smaller than 5.")
            if self.hold_market and reduce:
                self._oid += 1
                self.orders[cid] = {"clientOrderId": cid, "symbol": sym, "side": side, "type": "MARKET", "reduceOnly": True,
                                    "origQty": str(qty), "time": self.now_ms(), "orderId": self._oid, "status": "NEW",
                                    "executedQty": "0", "avgPrice": "0", "cumQuote": "0", "updateTime": self.now_ms()}
                return self._row(self.orders[cid])
            self._fill(sym, side, qty, self.marks[sym], cid, reduce, parts=self.market_parts)
            return self._row(self.orders[cid])
        o = self.orders.get(cid) if cid else next((x for x in self.orders.values() if x.get("orderId") == int(q.get("orderId", -1))), None)
        if method == "GET" and o is not None and not self.liquidation_queryable and str(o["clientOrderId"]).startswith("autoclose-"):
            return _err(-2013, "Order does not exist.")
        if method == "GET":
            if o is None:
                a = self.algos.get(cid) if (cid and self.classic) else None
                return self._classic(a) if a else _err(-2013, "Order does not exist.")
            return self._row(o)
        if method == "DELETE":
            if o is None and self.classic and cid in self.algos:
                self.algos[cid]["algoStatus"] = "CANCELED"
                return {"clientOrderId": cid, "status": "CANCELED"}
            if o is None or o.get("status") != "NEW":
                return _err(-2011, "Unknown order sent.")
            o["status"] = "CANCELED"
            return self._row(o)
        return _err(-5000, "method", 405)

    def _post_classic(self, q: dict, cid: str):
        a = self._new_cond(q["symbol"], q["side"], q["type"], D(q["quantity"]), D(q["stopPrice"]), q["workingType"], cid,
                           q.get("reduceOnly") == "true")
        if isinstance(a, FakeResp):
            return a
        row = self._classic(a)
        if a.pop("post_new", False):
            row["status"] = "NEW"
        return row

    def _new_cond(self, sym, side, typ, qty: Decimal, trig: Decimal, wt: str, cid: str, reduce: bool = True):
        if cid in self.algos and self.algos[cid]["algoStatus"] == "NEW":
            return _err(-4116, "ClientOrderId is duplicated.")
        bad = self._check_qty(sym, qty)
        if bad:
            return bad
        tick = D(self.symbols[sym]["tick"])
        if (trig / tick) != (trig / tick).to_integral_value():
            return _err(-1111, "Precision is over the maximum defined for this asset.")
        p = self.pos.get(sym, {"amt": D(0)})
        if reduce and (p["amt"] == 0 or (p["amt"] > 0) == (side == "BUY") or qty > abs(p["amt"])):
            return _err(-2022, "ReduceOnly Order is rejected.")
        self._oid += 1
        a = {"algoId": self._oid, "cid": cid, "symbol": sym, "side": side, "type": typ, "qty": qty, "triggerPrice": trig,
             "workingType": wt, "algoStatus": "NEW", "time": self.now_ms(), "reduce": reduce}
        if self._hit(a, self.marks[sym]):
            if self.immediate_trigger != "accept_then_trigger":
                return _err(-2021, "Order would immediately trigger.")
            self.algos[cid] = a
            a["post_new"] = True                                # POST yaniti NEW; hemen ardindan tetiklenir
            self._trigger(a)
            return a
        self.algos[cid] = a
        return a

    def _algo(self, method: str, q: dict):
        cid = q.get("clientAlgoId")
        if method == "POST":
            a = self._new_cond(q["symbol"], q["side"], q["type"], D(q["quantity"]), D(q["triggerPrice"]), q["workingType"], cid,
                               q.get("reduceOnly") == "true")
            if isinstance(a, FakeResp):
                return a
            row = self._algo_row(a)
            if a.pop("post_new", False):
                row["algoStatus"] = "NEW"
            return row
        a = self.algos.get(cid)
        if a is None:
            return _err(-2013, "Order does not exist.")
        if method == "GET":
            return self._algo_row(a)
        if method == "DELETE":
            if a["algoStatus"] != "NEW":
                return _err(-2011, "Unknown order sent.")
            a["algoStatus"] = "CANCELED"
            return self._algo_row(a)
        return _err(-5000, "method", 405)


def floor_dec(x: Decimal, step: Decimal) -> Decimal:
    return (x / step).to_integral_value(rounding=ROUND_FLOOR) * step
