"""Motor hata sinifleri (02 §3)."""


class EngineError(Exception):
    """Taban."""


class ConfigError(EngineError, ValueError):
    pass


class ClockError(EngineError):
    pass


class DataError(EngineError):
    pass


class StateError(EngineError):
    pass


class BrokerError(EngineError):
    pass


class BrokerUncertain(BrokerError):
    pass


class FailClosed(EngineError):
    pass


class EngineExit(Exception):
    """Surec cikisi (systemd yeniden baslatir). `code` cikis kodu. errors.py'de durur ki brokers/ (engine'i iceri alamaz)
    ayni sinifi firlatabilsin; engine.EngineExit ayni nesnedir."""

    def __init__(self, code: int, message: str = "") -> None:
        super().__init__(message or f"exit {code}")
        self.code = code


# ---------------------------------------------------------------------------------------------------------------------
# Hata siniflandirma: KOD hatasi (programlama) - GECICI hata (ag/veri/borsa). 1L3A motor/canli/paper_veri.py'den uyarlandi.
# Programlama hatalari gecici sayilip gizlenmez; gecici hatalar kod hatasi sayilip kol atlama/durus tetiklemez. Tek yer: tur
# koruyucusu (tur_koruyucu.py) ve sinyal kaynagi (kol kod hatasi yalitimi: yakala, logla, say, o kolu bu tur atla) bu iki yardimciyi kullanir.
import json as _json

CODE_ERRORS: tuple[type[BaseException], ...] = (
    TypeError, AttributeError, KeyError, IndexError, NameError, ImportError, AssertionError, NotImplementedError,
    ZeroDivisionError, ArithmeticError)

# Motorun kendi hiyerarsisi (DataError, BrokerError, ClockError, ConfigError...) ve ag/ayrisitirma hatalari GECICI/veri
# kaynaklidir. ConfigError bir ValueError'dur; EngineError oldugu icin burada gecici sayilir (kod hatasi degil).
TRANSIENT_ERRORS: tuple[type[BaseException], ...] = (EngineError, OSError, _json.JSONDecodeError, UnicodeError)

# Strateji KARAR kodunda ayrica ValueError de kod hatasidir (1L3A karari): o kol bu tur atlanir, tur surer. Veri cekme /
# yeniden deneme yolunda ValueError gecici kalir (`is_code_error` degismez).
STRATEGY_CODE_ERRORS: tuple[type[BaseException], ...] = CODE_ERRORS + (ValueError,)


def _is_transient(e: BaseException) -> bool:
    if isinstance(e, TRANSIENT_ERRORS):
        return True
    # borsa istemcisi hatalari (marketdata.rest_public.ExchangeError ve altlari): errors.py yaprak kalir, ad ile taninir
    return any(c.__name__ == "ExchangeError" for c in type(e).__mro__)


def is_code_error(e: BaseException) -> bool:
    """Programlama hatasi mi (TypeError, KeyError, ZeroDivisionError...)? Ag/veri/borsa hatalari asla (ValueError dahil degil)."""
    return isinstance(e, CODE_ERRORS) and not _is_transient(e)


def is_strategy_error(e: BaseException) -> bool:
    """Strateji karar kodundaki hata atlanmasi gerekir mi: kod hatasi + ValueError; gecici hatalar HARIC."""
    return isinstance(e, STRATEGY_CODE_ERRORS) and not _is_transient(e)
