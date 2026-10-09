"""(Tuy chon - phan "sang tao") Viet lai nhan dinh bang Claude API.

An toan du lieu: chi gui JSON cac so DA TINH, prompt cam them so moi; sau khi
nhan ket qua, moi con so xuat hien trong van ban phai co trong du lieu dau vao
(so sanh sau khi chuan hoa) - neu khong, BO ket qua LLM va giu ban quy tac.

Bat: dat ANTHROPIC_API_KEY va LLM_ENABLED=1 trong .env, `pip install anthropic`.
"""
from __future__ import annotations

import json
import os
import re

from ..config import get_settings
from ..logging_conf import get_logger

log = get_logger(__name__)

_SYSTEM = (
    "Bạn là chuyên viên phân tích của một công ty chứng khoán Việt Nam. Viết lại các ý "
    "nhận định thành 1 đoạn văn mạch lạc, chuyên nghiệp, tiếng Việt. TUYỆT ĐỐI không thêm "
    "con số, sự kiện hay dự báo nào không có trong dữ liệu được cung cấp. Giữ nguyên mọi con số."
)


def enabled() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY")) and os.getenv("LLM_ENABLED", "0") == "1"


def _numbers(text: str) -> set[str]:
    return {n.replace(".", "").replace(",", "") for n in re.findall(r"\d[\d.,]*", text)}


def polish(section: str, paragraphs: list[str]) -> list[str]:
    if not enabled() or not paragraphs:
        return paragraphs
    try:
        import anthropic  # type: ignore

        s = get_settings()
        client = anthropic.Anthropic()
        source = "\n".join(paragraphs)
        msg = client.messages.create(
            model=os.getenv("LLM_MODEL", s.get("llm.model", "claude-sonnet-5-5")),
            max_tokens=s.get("llm.max_tokens", 1200),
            system=_SYSTEM,
            messages=[{"role": "user", "content": json.dumps(
                {"muc": section, "y_nhan_dinh": paragraphs}, ensure_ascii=False)}],
        )
        text = "".join(getattr(b, "text", "") for b in msg.content).strip()
        if not text or not _numbers(text) <= _numbers(source):
            log.warning("LLM them so khong co trong du lieu (%s) - giu ban quy tac", section)
            return paragraphs
        return [text]
    except Exception as exc:  # noqa: BLE001
        log.warning("LLM loi (%s): %s", section, exc)
        return paragraphs
