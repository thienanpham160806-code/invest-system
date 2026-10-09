"""Giao dien du lieu realtime - CHI KHAI BAO, CHUA CAI.

Nhom chua co API key/secret cua DNSE (EntradeX) tai thoi diem viet module
nay. Xem README.md, muc "Cau hinh nguon du lieu (DNSE / Vietcap)" de biet
cach lay API key.

RANG BUOC TUYET DOI: khi `realtime.enabled: false` (mac dinh trong
config/settings.yaml), toan bo bot phai chay binh thuong bang du lieu cuoi
phien qua data/router.py. KHONG duong code nao duoc phep bat buoc phai co
realtime moi chay duoc - moi noi can gia realtime deu phai qua NullRealtimeProvider
hoac kiem tra `enabled` truoc.

Khi co API key, nguoi lam tiep chi can:
  1. Dien _connect()/_subscribe_impl()/... trong DnseRealtimeProvider theo
     tai lieu WebSocket/MQTT thuc te cua DNSE (realtime di qua WebSocket/MQTT,
     khong phai REST - khac voi data/dnse.py hien tai chi dung REST).
  2. KHONG doi RealtimeProvider (giao dien) neu khong can thiet - phan con
     lai cua bot (bot/handlers/, alerts/) chi goi qua giao dien nay.
  3. Neu Vietcap cung khong co API cong khai, VietcapRealtimeProvider co
     the se phai di duong khac (vd polling gia cuoi phien) thay vi socket -
     ghi lai quyet dinh do vao chinh file nay khi cai.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RealtimeQuote:
    """Mot ban tin gia realtime."""

    symbol: str
    price: float
    change: float
    change_pct: float
    volume: int
    timestamp: datetime
    source: str


class RealtimeProvider(ABC):
    """Giao dien nguon du lieu realtime. Xem NullRealtimeProvider cho hanh vi mac dinh."""

    name: str = "base"

    @abstractmethod
    def subscribe(self, symbols: list[str]) -> None:
        """Bat dau nhan ban tin realtime cho danh sach ma nay."""

    @abstractmethod
    def unsubscribe(self, symbols: list[str]) -> None:
        """Ngung nhan ban tin realtime cho danh sach ma nay."""

    @abstractmethod
    def latest(self, symbol: str) -> RealtimeQuote | None:
        """Ban tin gan nhat da nhan cho mot ma, None neu chua co hoac khong ho tro."""

    @abstractmethod
    def close(self) -> None:
        """Dong ket noi va giai phong tai nguyen."""


class DnseRealtimeProvider(RealtimeProvider):
    """Nguon realtime chinh (DNSE) - STUB, CHUA CAI.

    Can API key/secret tu EntradeX (xem README.md, muc "Cau hinh nguon du
    lieu"). DNSE dung WebSocket/MQTT cho du lieu realtime, khac voi REST dung
    cho lich su OHLC (data/dnse.py). Gioi han tai lieu ghi toi da 2.000 ma
    dong thoi.

    TODO (khi co API key): cai dat ket noi WebSocket/MQTT thuc te. KHONG bia
    URL hay ten topic - phai lay tu tai lieu chinh thuc hoac hoi CSKH DNSE
    (hotline 024 7108 9234 / hello@dnse.com.vn).
    """

    name = "dnse"

    def subscribe(self, symbols: list[str]) -> None:
        raise NotImplementedError(
            "Realtime DNSE chua duoc cai. Can DNSE_API_KEY/DNSE_API_SECRET tu "
            "EntradeX (LightSpeed API) va ket noi WebSocket/MQTT - xem README.md."
        )

    def unsubscribe(self, symbols: list[str]) -> None:
        raise NotImplementedError("Realtime DNSE chua duoc cai (xem subscribe()).")

    def latest(self, symbol: str) -> RealtimeQuote | None:
        raise NotImplementedError("Realtime DNSE chua duoc cai (xem subscribe()).")

    def close(self) -> None:
        raise NotImplementedError("Realtime DNSE chua duoc cai (xem subscribe()).")


class VietcapRealtimeProvider(RealtimeProvider):
    """Nguon realtime du phong (Vietcap) - STUB, CHUA CAI.

    Vietcap khong co cong dang ky API cong khai cho ca nhan. Neu can, nguon
    du phong nhieu kha nang phai di duong khac voi DNSE (vi du polling gia
    cuoi phien qua vnstock/VCI thay vi socket thuc su) - quyet dinh cu the
    de lai cho luc co du kien de kiem tra thuc te.

    TODO (khi co huong di ro rang): cai dat theo huong da chon, ghi lai ly do
    ngay trong docstring nay.
    """

    name = "vietcap"

    def subscribe(self, symbols: list[str]) -> None:
        raise NotImplementedError(
            "Realtime Vietcap chua duoc cai. Vietcap khong co API cong khai "
            "cho ca nhan."
        )

    def unsubscribe(self, symbols: list[str]) -> None:
        raise NotImplementedError("Realtime Vietcap chua duoc cai (xem subscribe()).")

    def latest(self, symbol: str) -> RealtimeQuote | None:
        raise NotImplementedError("Realtime Vietcap chua duoc cai (xem subscribe()).")

    def close(self) -> None:
        raise NotImplementedError("Realtime Vietcap chua duoc cai (xem subscribe()).")


class NullRealtimeProvider(RealtimeProvider):
    """Cai dat THAT, dung khi `realtime.enabled: false` (mac dinh).

    Moi phuong thuc deu vo hai (khong raise, khong lam gi) de phan con lai
    cua bot goi vao day ma khong can kiem tra `if enabled` o tung noi.
    """

    name = "null"

    def subscribe(self, symbols: list[str]) -> None:
        return None

    def unsubscribe(self, symbols: list[str]) -> None:
        return None

    def latest(self, symbol: str) -> RealtimeQuote | None:
        return None

    def close(self) -> None:
        return None


_PROVIDERS: dict[str, type[RealtimeProvider]] = {
    "dnse": DnseRealtimeProvider,
    "vietcap": VietcapRealtimeProvider,
    "null": NullRealtimeProvider,
}


def get_realtime_provider() -> RealtimeProvider:
    """Tra ve provider theo config/settings.yaml (`realtime.*`).

    Neu `realtime.enabled` la false (mac dinh) hoac ten provider khong hop
    le, LUON tra ve NullRealtimeProvider - khong bao gio de mot phan cua bot
    bi buoc phai co realtime moi chay duoc.
    """
    from ..config import get_settings  # tranh import vong khi config.py mo rong

    settings = get_settings()
    if not settings.get("realtime.enabled", False):
        return NullRealtimeProvider()

    provider_name = settings.get("realtime.provider", "dnse")
    provider_cls = _PROVIDERS.get(provider_name, NullRealtimeProvider)
    return provider_cls()
