"""Optional OpenAI narrative layer for evidence-based Vietnamese market reports.

The deterministic analysis remains the source of ratings and calculations. The
model only turns supplied, already-computed findings into readable prose; if
the API is unavailable or changes a figure, the original wording is retained.

Choose one provider with LLM_PROVIDER=openai|gemini, set its API key, then opt in
with LLM_ENABLED=1. The feature is off by default and never fails over to the
other provider automatically.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from decimal import Decimal, InvalidOperation

from ..config import get_settings
from ..logging_conf import get_logger

log = get_logger(__name__)

_SYSTEM = """Bạn là chuyên viên phân tích đầu tư tại thị trường chứng khoán Việt Nam.
Hãy biên tập các nhận định được cung cấp thành văn phong tiếng Việt tự nhiên,
điềm tĩnh, chuyên nghiệp, phù hợp với báo cáo phân tích của công ty chứng khoán.

Nguyên tắc bắt buộc:
- Chỉ sử dụng dữ kiện, số liệu, kết luận và quan hệ nhân quả đã có trong đầu vào.
- Không tự tra cứu, thêm số liệu, sự kiện, dự báo, khuyến nghị hay giả định mới.
- Giữ nguyên tất cả con số. Không đổi đơn vị, kỳ báo cáo, dấu, hoặc chiều tăng/giảm.
- Phân biệt dữ kiện quan sát được với hàm ý phân tích; dùng ngôn ngữ thận trọng
  như “có thể”, “hàm ý” khi đầu vào chỉ hỗ trợ một suy luận.
- Với vĩ mô, kết nối tăng trưởng, lạm phát, lãi suất, tín dụng và tỷ giá với
  sức cầu, chi phí vốn và nhóm doanh nghiệp/ngành đã nêu trong đầu vào; không
  suy diễn tác động nếu dữ liệu không hỗ trợ.
- Với phân tích ngành, làm rõ tương quan hiệu suất, định giá và vị thế doanh
  nghiệp trong nhóm so sánh; không gọi một chỉ số tự tính là chỉ số chính thức.
- Nêu giới hạn dữ liệu nếu đầu vào có nói đến; không biến thiếu dữ liệu thành
  kết luận tích cực hoặc tiêu cực.
- Chỉ trả về phần nhận định đã biên tập, không thêm tiêu đề, lời dẫn hay số liệu.
"""


def _selected_provider() -> tuple[str, str] | None:
    """Return only the explicitly selected provider and its key."""
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    key_name = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}.get(provider)
    key = os.getenv(key_name, "").strip() if key_name else ""
    return (provider, key) if key else None


def enabled() -> bool:
    """Require an explicit opt-in and a key for the selected provider."""
    return os.getenv("LLM_ENABLED", "0") == "1" and _selected_provider() is not None


def _generate(payload: str, instructions: str, section: str) -> str | None:
    """Call exactly one configured provider; never silently switch providers."""
    selected = _selected_provider()
    if os.getenv("LLM_ENABLED", "0") != "1" or selected is None:
        return None
    provider, api_key = selected
    try:
        settings = get_settings()
        max_output_tokens = settings.get("llm.max_tokens", 500)
        if provider == "openai":
            from openai import OpenAI

            model = os.getenv("OPENAI_MODEL", settings.get("llm.model", "gpt-6-luna"))
            response = OpenAI(api_key=api_key).responses.create(
                model=model,
                instructions=instructions,
                input=payload,
                max_output_tokens=max_output_tokens,
            )
            return (response.output_text or "").strip() or None

        from google import genai

        response = genai.Client(api_key=api_key).models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
            contents=payload,
            config={"system_instruction": instructions, "max_output_tokens": max_output_tokens},
        )
        return (response.text or "").strip() or None
    except Exception as exc:  # noqa: BLE001 - optional provider must not break reports
        log.warning("LLM %s loi (%s): %s", provider, section, exc)
        return None


def _canonical_number(raw: str) -> str | None:
    """Normalize Western and Vietnamese number formatting without rounding."""
    value = raw.strip()
    sign = ""
    if value[:1] in {"+", "-"}:
        sign, value = value[0], value[1:]

    if "." in value and "," in value:
        decimal_sep = "." if value.rfind(".") > value.rfind(",") else ","
        thousands_sep = "," if decimal_sep == "." else "."
        value = value.replace(thousands_sep, "").replace(decimal_sep, ".")
    elif "," in value:
        value = value.replace(".", "").replace(",", ".")
    elif "." in value:
        # A dot followed by groups of three digits is a thousands separator
        # in report output (for example, 1.234.567).
        pieces = value.split(".")
        if len(pieces) > 1 and all(len(piece) == 3 for piece in pieces[1:]):
            value = "".join(pieces)

    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    normalized = format(number.normalize(), "f")
    if normalized in {"-0", "0"}:
        sign = ""
    return sign + normalized


def _numbers(text: str) -> Counter[str]:
    tokens = re.findall(r"(?<![\w])[-+]?\d[\d.,]*(?![\w])", text)
    return Counter(canonical for token in tokens
                    if (canonical := _canonical_number(token)) is not None)


def polish(section: str, paragraphs: list[str]) -> list[str]:
    """Rewrite a section while retaining exact numeric evidence and fallback."""
    if not enabled() or not paragraphs:
        return paragraphs
    source = "\n".join(paragraphs)
    text = _generate(
        json.dumps({"muc": section, "nhan_dinh_da_tinh": paragraphs}, ensure_ascii=False),
        _SYSTEM,
        section,
    )
    if not text or _numbers(text) != _numbers(source):
        log.warning("LLM thay doi hoac them so lieu (%s) - giu ban quy tac", section)
        return paragraphs
    return [text]


def analyze_macro(ctx: dict) -> list[str]:
    """Synthesize computed macro indicators and the sector transmission view."""
    macro = ctx.get("macro")
    if macro is None:
        return []
    fallback = list(macro.commentary)
    if not enabled():
        return fallback

    facts = {
        "nhan_dinh_theo_quy_tac": macro.commentary,
        "cac_chi_tieu_va_nguon": macro.table,
        "diem_moi_truong_vi_mo_0_100": macro.score,
        "nganh_doanh_nghiep_dang_phan_tich": macro.sector_label,
        "diem_tac_dong_vi_mo_den_nganh_0_100": macro.sector_score,
        "thang_diem": "0-100",
        "ghi_chu_ve_du_lieu": macro.notes,
    }
    request = {"muc": "Đánh giá tổng quan vĩ mô", "du_lieu_da_kiem_chung": facts}
    serialized = json.dumps(request, ensure_ascii=False)
    text = _generate(
        serialized,
        _SYSTEM + """

Riêng mục đánh giá tổng quan vĩ mô: viết một đoạn tổng hợp ngắn, nêu trạng thái
chung, động lực thuận lợi, sức ép/rủi ro và kênh truyền dẫn tới ngành đang phân
tích nếu dữ liệu hỗ trợ. Đây là đánh giá bối cảnh, không đưa khuyến nghị mua/bán.
Chỉ dùng số liệu cùng kỳ và nguồn được cung cấp; nếu thiếu dữ liệu, nói rõ giới hạn.
""",
        "Đánh giá tổng quan vĩ mô",
    )
    if not text or _numbers(text) - _numbers(serialized):
        log.warning("LLM them so lieu ngoai du lieu vi mo - giu ban quy tac")
        return fallback
    return [text]
