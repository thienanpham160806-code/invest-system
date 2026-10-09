"""Truy vet nguon goc moi so lieu (tieu chi "chinh xac ve mat du lieu").

Moi buoc lay du lieu ghi lai mot `SourceRecord`: lay cai gi, tu dau, so lieu
den ngay nao, luc nao lay. Bao cao PDF in toan bo danh sach nay o phu luc,
va trang 1 ghi "Nguon du lieu" ngan gon - nguoi cham co the doi chieu tung so.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class SourceRecord:
    item: str                 # vd "Giá OHLCV FPT", "BCTC năm FPT"
    source: str               # vd "Vietcap public API", "vnstock 4.x (VCI)"
    as_of: str | None = None  # so lieu den ngay/ky nao
    fetched_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))
    note: str = ""
    ok: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


class SourceLog:
    """Nhat ky nguon cho MOT lan chay pipeline."""

    def __init__(self) -> None:
        self.records: list[SourceRecord] = []

    def add(self, item: str, source: str, as_of=None, note: str = "", ok: bool = True) -> None:
        as_of_str = None
        if as_of is not None:
            as_of_str = as_of.strftime("%Y-%m-%d") if hasattr(as_of, "strftime") else str(as_of)
        self.records.append(SourceRecord(item, source, as_of_str, note=note, ok=ok))

    def fail(self, item: str, note: str) -> None:
        self.add(item, "—", note=note, ok=False)

    def to_list(self) -> list[dict]:
        return [r.to_dict() for r in self.records]

    def summary(self) -> str:
        sources = sorted({r.source for r in self.records if r.ok and r.source != "—"})
        return "; ".join(sources) if sources else "Không có nguồn"
