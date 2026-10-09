"""Text mining bao cao tai chinh hop nhat da kiem toan.

Giai quyet van de: doc BCTC (PDF nguoi dung gui, hoac du lieu co cau truc tu
data/router.py) qua nhieu nam va sinh nhan xet bang TIENG VIET ve tinh hinh
tai chinh doanh nghiep. Dung QUY TAC + TU DIEN, khong dung mo hinh ngon ngu -
de moi cau trong nhan xet co the truy lai duoc dung mot dong code hoac mot
dong trong tu dien (de giai thich khi bao ve do an), va khong can GPU/API
ngoai de chay.

Luong xu ly: extract_text (PDF -> text) -> segment_sections (tach theo tieu
de) -> audit_opinion + risk_keywords (doc tren toan van ban hoac tung phan)
-> trend_analysis (tren du lieu co cau truc nhieu nam) -> generate_commentary
(gop tat ca thanh mot nhan xet co bo cuc co dinh).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from ..config import CONFIG_DIR
from ..logging_conf import get_logger

log = get_logger(__name__)

# ------------------------------------------------------------- trich xuat PDF
MAX_PDF_PAGES = 200  # BCTC hop nhat thuong 60-150 trang


def extract_text(pdf_path: str | Path, max_pages: int = MAX_PDF_PAGES) -> str:
    """Trich van ban tu PDF BCTC bang pypdfium2 (thu vien C cua PDFium), giu
    cau truc doan theo trang.

    Truoc day dung pdfplumber: do tren PDF 150 trang, pdfplumber ton ~1,9 GB
    RAM (giu cache moi trang) va 24s; pypdfium2 ton ~4 MB va 0,5s, van ban
    tieng Viet giong het - quan trong tren Render goi Free (512 MB, 0,1 CPU).
    PDF la ban SCAN (anh) thi tra ve gan nhu rong - xem is_scanned_text().

    pypdfium2 duoc cai KEM pdfplumber (requirements.txt), khong khai bao
    rieng: tu 25/09/2026 goi vnstock bi PyPI "quarantine" (khong tai duoc),
    Render chi build duoc nho cache buoc pip install - sua requirements.txt la
    mat cache va build that bai."""
    import pypdfium2 as pdfium

    pages_text: list[str] = []
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        for index in range(min(len(pdf), max_pages)):
            page = pdf[index]
            textpage = page.get_textpage()
            try:
                pages_text.append(textpage.get_text_bounded() or "")
            finally:
                textpage.close()
                page.close()
    finally:
        pdf.close()
    text = "\n\n".join(pages_text).replace("\r\n", "\n")
    return unicodedata.normalize("NFC", text)


def is_scanned_text(text: str) -> bool:
    """PDF gan nhu khong co lop chu (ban scan/chup) - khong khai thac duoc."""
    return len(text.strip()) < 500


# --------------------------------------------------------------- tach cac phan
# TODO: cac mau tieu de la DU DOAN hop ly dua tren cach trinh bay BCTC pho
# bien tai Viet Nam - bo sung them mau khi gap BCTC thuc te khong khop.
_SECTION_PATTERNS: dict[str, list[str]] = {
    "y_kien_kiem_toan": [r"ý kiến (của )?kiểm toán", r"báo cáo (của )?kiểm toán( độc lập)?"],
    "bang_can_doi": [r"bảng cân đối kế toán"],
    "ket_qua_kinh_doanh": [r"báo cáo kết quả hoạt động kinh doanh", r"kết quả kinh doanh"],
    "luu_chuyen_tien_te": [r"báo cáo lưu chuyển tiền tệ", r"lưu chuyển tiền tệ"],
    "thuyet_minh": [r"thuyết minh báo cáo tài chính", r"thuyết minh"],
}


def segment_sections(text: str) -> dict[str, str]:
    """Tach van ban BCTC theo tieu de thuong gap (regex, khong dau cau tinh).

    Tra ve dict {ten_phan: noi_dung}. Phan nao khong tim thay tieu de trong
    van ban thi KHONG co trong dict - khong bia noi dung.
    """
    lowered = text.lower()
    matches: list[tuple[int, str]] = []
    for key, patterns in _SECTION_PATTERNS.items():
        for pattern in patterns:
            matches.extend((m.start(), key) for m in re.finditer(pattern, lowered))
    if not matches:
        return {}

    matches.sort()
    sections: dict[str, str] = {}
    for i, (start, key) in enumerate(matches):
        if key in sections:
            continue  # giu doan tu LAN XUAT HIEN DAU TIEN cua tieu de nay
        end = matches[i + 1][0] if i + 1 < len(matches) else len(text)
        sections[key] = text[start:end].strip()
    return sections


# ------------------------------------------------------------- y kien kiem toan
_AUDIT_OPINIONS: dict[str, list[str]] = {
    "trái ngược": ["ý kiến trái ngược", "không trình bày trung thực và hợp lý"],
    "từ chối": ["từ chối đưa ra ý kiến", "không thể đưa ra ý kiến"],
    "ngoại trừ": ["ý kiến ngoại trừ", "ngoại trừ ảnh hưởng", "ngoại trừ vấn đề"],
    "chấp nhận toàn phần": [
        "chấp nhận toàn phần",
        "ý kiến chấp nhận toàn phần",
        "trình bày trung thực và hợp lý",
    ],
}
# Thu tu uu tien: loai NGHIEM TRONG hon duoc kiem truoc, vi mot doan van co
# the vua nhac "trinh bay trung thuc" (trong cau dan) vua co "ngoai tru".
_OPINION_PRIORITY = ["trái ngược", "từ chối", "ngoại trừ", "chấp nhận toàn phần"]


def _normalize(text: str) -> str:
    """Ha thuong + gop khoang trang + BO DAU TIENG VIET - chi dung de SO KHOP.

    Van ban trich tu PDF BCTC doi khi MAT DAU (font nhung/encoding loi khi
    pdfplumber trich xuat - da gap thuc te), trong khi tu dien trong file nay
    (_AUDIT_OPINIONS, config/risk_keywords.yaml) LUON co dau day du. Neu chi
    ha thuong ma khong bo dau, van ban mat dau se khong khop duoc voi tu dien
    -> audit_opinion()/risk_keywords() lang le tra ve khong tim thay gi, du
    van ban THUC SU co noi dung lien quan. Bo dau ca hai chieu (van ban lan
    tu dien) giai quyet tron ca 2 truong hop: van ban co dau lan mat dau.

    LUU Y: KHONG dung ket qua ham nay de HIEN THI - "audit_opinion" tra ve
    `evidence` tu tu dien goc (co dau), "risk_keywords" tra ve `Hit.sentence`
    tu van ban goc (giu nguyen, co dau hay khong tuy PDF) - ca hai deu KHONG
    bi ghi de boi ban da bo dau nay.
    """
    text = text.replace("đ", "d").replace("Đ", "D")  # "đ" khong tach duoc qua NFD
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", stripped.lower()).strip()


def audit_opinion(text: str) -> dict:
    """Phan loai y kien kiem toan bang tu dien cum tu.

    Y kien NGOAI TRU la tin hieu canh bao rat manh - duoc kiem truoc ca
    "tu choi"/"trai nguoc" o day chi vi thu tu liet ke, nhung generate_commentary()
    la noi thuc su dua no len dau nhan xet.

    Tra ve dict: opinion (mot trong 4 loai, None neu khong nhan dien duoc),
    evidence (cum tu khop dau tien lam minh chung).
    """
    lowered = _normalize(text)
    for opinion in _OPINION_PRIORITY:
        for phrase in _AUDIT_OPINIONS[opinion]:
            if _normalize(phrase) in lowered:
                return {"opinion": opinion, "evidence": phrase}
    return {"opinion": None, "evidence": None}


# --------------------------------------------------------------- tu khoa rui ro
@dataclass
class Hit:
    """Mot lan tu khoa rui ro xuat hien trong van ban."""

    keyword: str
    group: str
    weight: float
    sentence: str


def _load_risk_dictionary() -> dict:
    path = CONFIG_DIR / "risk_keywords.yaml"
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _split_sentences(text: str) -> list[str]:
    """Tach cau don gian theo dau cham/hoi/than hoac xuong dong - du dung de
    lay ra cau chua tu khoa, khong can chinh xac tuyet doi ve ngu phap."""
    parts = re.split(r"(?<=[.!?;])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def risk_keywords(text: str, dictionary: dict | None = None) -> list[Hit]:
    """Quet tu dien rui ro (config/risk_keywords.yaml) tren `text`.

    Tra ve danh sach Hit, moi Hit la MOT lan tu khoa xuat hien kem cau chua
    no (de nguoi dung tu doc lai ngu canh, khong chi thay tu khoa tro tru).
    """
    dictionary = dictionary if dictionary is not None else _load_risk_dictionary()
    sentences = _split_sentences(text)
    normalized_sentences = [(_normalize(s), s) for s in sentences]

    hits: list[Hit] = []
    for group_key, group in dictionary.get("groups", {}).items():
        weight = float(group.get("weight", 1.0))
        for keyword in group.get("keywords", []):
            needle = _normalize(keyword)
            for normalized, original in normalized_sentences:
                if needle in normalized:
                    hit = Hit(keyword=keyword, group=group_key, weight=weight, sentence=original)
                    hits.append(hit)
    return hits


# ------------------------------------------------------------------- xu huong
# Ten cot (item_id) DA XAC NHAN tren vnstock 4.0.8 thuc te (Fundamental().
# equity(symbol=...).income_statement()/.balance_sheet()/.cash_flow()) - xem
# data/vietcap.py. "equity" khong co item_id chung duy nhat giua cac cong ty
# (du lieu ke toan Viet Nam khong dong nhat) nen giu nhieu candidate.
_TREND_COLUMNS: dict[str, list[str]] = {
    "revenue": ["revenue", "net_sales", "netRevenue", "saleRevenue"],
    "net_income": ["net_profit", "netIncome", "profitAfterTax"],
    "gross_profit": ["gross_profit", "grossProfit"],
    "total_assets": ["total_assets", "totalAssets"],
    # "equity": ten item_id thuc te THAY DOI theo nganh (vd cong ty thuong
    # thuong la "owners_equity_2"/"owners_equity_3", cong ty chung khoan la
    # "equity" don gian) - giu nhieu candidate.
    "equity": [
        "equity", "owners_equity_2", "owners_equity_3", "owners_equity", "totalEquity",
        "capital_and_reserves",  # ngan hang: "Von va cac quy" (= VCSH)
    ],
}
# Ngan hang khong co "doanh thu"/"loi nhuan gop" - bao cao dung chi tieu rieng
# (item_id da xac nhan tren BCTC nam cua CTG qua vnstock 4.0.8).
_BANK_COLUMNS: dict[str, tuple[str, list[str]]] = {
    "net_interest_income": ("income", ["net_interest_income"]),
    "credit_provision": ("income", ["provision_for_credit_losses"]),
    "customer_loans": ("balance", ["loans_advances_and_finance_leases_to_customers"]),
    "customer_deposits": ("balance", ["deposits_from_customers"]),
}
# CFO cho cong ty chung khoan/ngan hang dung ten item_id rieng theo nganh
# (vd VIX: "net_cash_flows_from_securities_trading_activities"), khong co
# trong candidate chung o day - phu hop voi quy uoc da co trong du an (xem
# Altman Z-score trong docs/cong-thuc.md cu: khong ap dung cho nhom nay).
_CFO_COLUMNS = ["operating_cash_flow", "netCashFlowFromOperating", "cfo"]
_YEAR_COLUMNS = ["period", "year", "yearReport"]
_EARNINGS_QUALITY_THRESHOLD = 0.8

# Item_id trong bao cao "ratios" (DA XAC NHAN tren vnstock 4.0.8 that, vi du
# FPT nam 2025: roe=28.30, roa=11.71, debt_to_equity=48.17, short_term_ratio=1.40
# - CA BA deu la SO PHAN TRAM san (vd 28.30 nghia la 28.30%), rieng
# short_term_ratio la SO LAN (vd 1.40 nghia la 1.40 lan), khong phai phan tram.
_RATIO_TREND_COLUMNS: dict[str, list[str]] = {
    "roe": ["roe"],
    "roa": ["roa"],
    "debt_to_equity": ["debt_to_equity"],
    "current_ratio": ["short_term_ratio"],
}


def _find_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    return next((c for c in candidates if c in frame.columns), None)


def _cagr(first: float, last: float, years: int) -> float | None:
    """Toc do tang truong kep nhieu nam: (last/first)^(1/years) - 1."""
    if first is None or last is None or first <= 0 or years <= 0:
        return None
    return float((last / first) ** (1 / years) - 1)


def trend_analysis(financials: dict[str, pd.DataFrame]) -> dict:
    """Tinh CAGR + gia tri tung nam cua doanh thu/LNST/tong tai san/VCSH, bien
    loi nhuan, ROE/ROA/no-VCSH/thanh khoan (tu bao cao "ratios"), va chat
    luong loi nhuan (CFO/LNST) tu bao cao tai chinh nhieu nam.

    `financials` co dang tra ve cua data/router.py:financials() - dict voi
    cac khoa income/balance/cashflow/ratios, moi gia tri la mot DataFrame
    theo nam (period="year"), SAP XEP TANG DAN theo thoi gian.

    Tra ve dict, chi dien cac khoa TINH DUOC (thieu cot nao thi bo qua khoa
    do va ghi vao "notes" - khong bia so). Cac khoa "*_by_year" la dict
    {nam: gia_tri} de generate_commentary() trich dan duoc TUNG NAM, khong
    chi mot con so CAGR gop chung.
    """
    income = financials.get("income", pd.DataFrame())
    balance = financials.get("balance", pd.DataFrame())
    cashflow = financials.get("cashflow", pd.DataFrame())
    ratios = financials.get("ratios", pd.DataFrame())

    result: dict = {"years": [], "notes": []}

    year_col = _find_column(income, _YEAR_COLUMNS)
    if income.empty or year_col is None:
        result["notes"].append("Khong co du lieu ket qua kinh doanh theo nam")
        return result
    years = income[year_col].tolist()
    result["years"] = years

    rev_col = _find_column(income, _TREND_COLUMNS["revenue"])
    ni_col = _find_column(income, _TREND_COLUMNS["net_income"])
    gp_col = _find_column(income, _TREND_COLUMNS["gross_profit"])

    if rev_col:
        revenue = income[rev_col].astype(float)
        result["revenue_by_year"] = dict(zip(years, revenue, strict=False))
        result["revenue_cagr"] = _cagr(revenue.iloc[0], revenue.iloc[-1], len(revenue) - 1)
        if ni_col:
            net_income = income[ni_col].astype(float)
            margins = net_income / revenue.replace(0, pd.NA)
            result["net_margin_by_year"] = dict(zip(years, margins, strict=False))
        if gp_col:
            gross = income[gp_col].astype(float)
            result["gross_margin_by_year"] = dict(
                zip(years, gross / revenue.replace(0, pd.NA), strict=False)
            )
    else:
        result["notes"].append("Khong tim duoc cot doanh thu")

    if ni_col:
        net_income = income[ni_col].astype(float)
        years_span = len(net_income) - 1
        result["net_income_by_year"] = dict(zip(years, net_income, strict=False))
        result["net_income_cagr"] = _cagr(net_income.iloc[0], net_income.iloc[-1], years_span)
    else:
        result["notes"].append("Khong tim duoc cot loi nhuan sau thue")

    asset_col = _find_column(balance, _TREND_COLUMNS["total_assets"])
    if asset_col and not balance.empty:
        assets = balance[asset_col].astype(float)
        result["total_assets_by_year"] = dict(zip(years, assets, strict=False))
        result["total_assets_cagr"] = _cagr(assets.iloc[0], assets.iloc[-1], len(assets) - 1)

    equity_col = _find_column(balance, _TREND_COLUMNS["equity"])
    if equity_col and not balance.empty:
        equity = balance[equity_col].astype(float)
        result["equity_by_year"] = dict(zip(years, equity, strict=False))
        result["equity_cagr"] = _cagr(equity.iloc[0], equity.iloc[-1], len(equity) - 1)

    statements = {"income": income, "balance": balance}
    for key, (part, candidates) in _BANK_COLUMNS.items():
        frame = statements[part]
        col = _find_column(frame, candidates)
        if col and len(frame) == len(years):
            result[f"{key}_by_year"] = dict(zip(years, frame[col].astype(float), strict=False))
    nii = list((result.get("net_interest_income_by_year") or {}).values())
    if len(nii) >= 2:
        result["net_interest_income_cagr"] = _cagr(nii[0], nii[-1], len(nii) - 1)

    cfo_col = _find_column(cashflow, _CFO_COLUMNS)
    if cfo_col and ni_col and not cashflow.empty:
        n = min(len(cashflow), len(income))
        cfo = cashflow[cfo_col].astype(float).tail(n).reset_index(drop=True)
        net_income_tail = income[ni_col].astype(float).tail(n).reset_index(drop=True)
        cfo_ratio = cfo / net_income_tail.replace(0, pd.NA)
        result["cfo_to_ni_by_year"] = dict(zip(years[-n:], cfo_ratio, strict=False))
        valid = cfo_ratio.dropna()
        result["cfo_to_ni_avg"] = float(valid.mean()) if not valid.empty else None

    ratio_year_col = _find_column(ratios, _YEAR_COLUMNS)
    if ratio_year_col and not ratios.empty:
        ratio_years = ratios[ratio_year_col].tolist()
        for key, candidates in _RATIO_TREND_COLUMNS.items():
            col = _find_column(ratios, candidates)
            if col:
                series = pd.to_numeric(ratios[col], errors="coerce")
                result[f"{key}_by_year"] = dict(zip(ratio_years, series, strict=False))

    return result


# --------------------------------------------------------------- nhan xet cuoi
def generate_commentary(symbol: str, audit: dict, risk_hits: list[Hit], trend: dict) -> str:
    """Sinh nhan xet tieng Viet theo QUY TAC + MAU CAU co dinh, khong dung mo
    hinh ngon ngu. Bo cuc: y kien kiem toan -> tang truong -> sinh loi ->
    co cau tai chinh -> chat luong loi nhuan -> rui ro thuyet minh -> ket luan.

    Moi dong deu co gang dan so cu the kem nam; khi thieu du lieu thi noi ro
    "khong co du lieu" thay vi noi chung chung.
    """
    lines: list[str] = [f"<b>Bình luận tình hình tài chính — {symbol.upper()}</b>", ""]

    lines.append("<b>1. Ý kiến kiểm toán</b>")
    lines.append(_audit_paragraph(audit))
    lines.append("")

    lines.append("<b>2. Tăng trưởng qua các năm</b>")
    lines.append(_growth_paragraph(trend))
    lines.append("")

    lines.append("<b>3. Khả năng sinh lời</b>")
    lines.append(_profitability_paragraph(trend))
    lines.append("")

    lines.append("<b>4. Cơ cấu tài chính và đòn bẩy</b>")
    lines.append(_structure_paragraph(trend))
    lines.append("")

    lines.append("<b>5. Chất lượng lợi nhuận và dòng tiền</b>")
    lines.append(_earnings_quality_paragraph(trend))
    lines.append("")

    lines.append("<b>6. Rủi ro phát hiện trong thuyết minh</b>")
    lines.append(_risk_paragraph(risk_hits))
    lines.append("")

    lines.append("<b>Kết luận</b>")
    lines.append(_conclusion_paragraph(audit, trend, risk_hits))

    return "\n".join(lines)


def _fmt_billion(value) -> str:
    """Hien so tien lon dang 'X,XXX ty dong' - de doc hon so nguyen VND day du."""
    if value is None or pd.isna(value):
        return "n/a"
    return f"{value / 1e9:,.0f} tỷ đồng"


def _fmt_frac_pct(value) -> str:
    """Cho cac ty le TU TINH (vd net_income/revenue) - dang phan so 0-1."""
    if value is None or pd.isna(value):
        return "n/a"
    return f"{value:.1%}"


def _fmt_ratio_pct(value) -> str:
    """Cho cac chi so LAY TU BAO CAO "ratios" (roe/roa/debt_to_equity) - DA o
    dang phan tram san (vd 28.30 nghia la 28.30%), khac voi _fmt_frac_pct."""
    if value is None or pd.isna(value):
        return "n/a"
    return f"{value:.1f}%"


def _fmt_times(value) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{value:.2f} lần"


def _series_line(label: str, by_year: dict, fmt) -> str | None:
    """'Nhan: 2022: X | 2023: Y | ...' - bo qua nam thieu du lieu. None neu rong."""
    if not by_year:
        return None
    parts = [f"{year}: {fmt(value)}" for year, value in by_year.items()]
    return f"{label}: " + " | ".join(parts) + "."


def _yoy_change(by_year: dict) -> tuple[str, str, float] | None:
    """So sanh nam gan nhat voi nam lien truoc. Tra (nam_gan_nhat, nam_truoc, ty_le)."""
    years = list(by_year)
    if len(years) < 2:
        return None
    last, prev = by_year[years[-1]], by_year[years[-2]]
    if prev is None or pd.isna(prev) or prev == 0 or last is None or pd.isna(last):
        return None
    return years[-1], years[-2], float(last / prev - 1)


def _audit_paragraph(audit: dict) -> str:
    opinion, evidence = audit.get("opinion"), audit.get("evidence")
    if opinion == "ngoại trừ":
        return f"⚠️ Ý kiến kiểm toán là NGOẠI TRỪ — cảnh báo mạnh: “{evidence}”."
    if opinion in ("từ chối", "trái ngược"):
        return f"⚠️ Ý kiến kiểm toán là {opinion.upper()} — cảnh báo rất mạnh: “{evidence}”."
    if opinion == "chấp nhận toàn phần":
        return "Kiểm toán viên đưa ra ý kiến chấp nhận toàn phần."
    return "Không xác định được loại ý kiến kiểm toán từ văn bản đã cung cấp."


def _growth_paragraph(trend: dict) -> str:
    years = trend.get("years") or []
    span = f"{years[0]}-{years[-1]}" if len(years) >= 2 else "giai đoạn có dữ liệu"
    lines: list[str] = []

    rev_by_year = trend.get("revenue_by_year") or {}
    line = _series_line("Doanh thu", rev_by_year, _fmt_billion)
    if line:
        lines.append(line)
    if trend.get("revenue_cagr") is not None:
        rev_cagr = trend["revenue_cagr"]
        lines.append(f"Tốc độ tăng trưởng kép doanh thu bình quân {rev_cagr:+.1%}/năm ({span}).")
    rev_yoy = _yoy_change(rev_by_year)
    if rev_yoy:
        last_y, prev_y, pct = rev_yoy
        huong = "tăng" if pct >= 0 else "giảm"
        lines.append(f"Riêng năm {last_y}, doanh thu {huong} {abs(pct):.1%} so với năm {prev_y}.")

    ni_by_year = trend.get("net_income_by_year") or {}
    line = _series_line("Lợi nhuận sau thuế", ni_by_year, _fmt_billion)
    if line:
        lines.append(line)
    if trend.get("net_income_cagr") is not None:
        ni_cagr = trend["net_income_cagr"]
        lines.append(f"Tốc độ tăng trưởng kép lợi nhuận sau thuế bình quân {ni_cagr:+.1%}/năm.")
    ni_yoy = _yoy_change(ni_by_year)
    if ni_yoy:
        last_y, prev_y, pct = ni_yoy
        huong = "tăng" if pct >= 0 else "giảm"
        lines.append(
            f"Riêng năm {last_y}, lợi nhuận sau thuế {huong} {abs(pct):.1%} so với năm {prev_y}."
        )

    nii_by_year = trend.get("net_interest_income_by_year") or {}
    line = _series_line("Thu nhập lãi thuần (ngân hàng)", nii_by_year, _fmt_billion)
    if line:
        lines.append(line)
    if trend.get("net_interest_income_cagr") is not None:
        lines.append(
            f"Thu nhập lãi thuần tăng trưởng kép bình quân "
            f"{trend['net_interest_income_cagr']:+.1%}/năm ({span})."
        )
    line = _series_line(
        "Chi phí dự phòng rủi ro tín dụng", trend.get("credit_provision_by_year") or {},
        _fmt_billion,
    )
    if line:
        lines.append(line)

    if not lines:
        return "Không có đủ dữ liệu doanh thu/lợi nhuận theo năm để phân tích tăng trưởng."
    return "\n".join(lines)


def _profitability_paragraph(trend: dict) -> str:
    lines: list[str] = []
    for label, key, fmt in (
        ("Biên lợi nhuận gộp", "gross_margin_by_year", _fmt_frac_pct),
        ("Biên lợi nhuận ròng", "net_margin_by_year", _fmt_frac_pct),
        ("ROE (lợi nhuận / vốn chủ sở hữu)", "roe_by_year", _fmt_ratio_pct),
        ("ROA (lợi nhuận / tổng tài sản)", "roa_by_year", _fmt_ratio_pct),
    ):
        line = _series_line(label, trend.get(key) or {}, fmt)
        if line:
            lines.append(line)

    if not lines:
        return "Không có dữ liệu biên lợi nhuận/ROE/ROA theo năm."
    return "\n".join(lines)


def _structure_paragraph(trend: dict) -> str:
    lines: list[str] = []
    line = _series_line("Tổng tài sản", trend.get("total_assets_by_year") or {}, _fmt_billion)
    if line:
        lines.append(line)
    if trend.get("total_assets_cagr") is not None:
        assets_cagr = trend["total_assets_cagr"]
        lines.append(f"Tổng tài sản tăng trưởng kép bình quân {assets_cagr:+.1%}/năm.")

    line = _series_line("Vốn chủ sở hữu", trend.get("equity_by_year") or {}, _fmt_billion)
    if line:
        lines.append(line)
    if trend.get("equity_cagr") is not None:
        equity_cagr = trend["equity_cagr"]
        lines.append(f"Vốn chủ sở hữu tăng trưởng kép bình quân {equity_cagr:+.1%}/năm.")

    debt_col = trend.get("debt_to_equity_by_year") or {}
    line = _series_line("Tỷ lệ Nợ/Vốn chủ sở hữu", debt_col, _fmt_ratio_pct)
    if line:
        lines.append(line)
    loans = trend.get("customer_loans_by_year") or {}
    deposits = trend.get("customer_deposits_by_year") or {}
    for label, series in (("Cho vay khách hàng", loans), ("Tiền gửi của khách hàng", deposits)):
        line = _series_line(label, series, _fmt_billion)
        if line:
            lines.append(line)
    ldr = {
        y: loans[y] / deposits[y] for y in loans
        if y in deposits and deposits[y] and not pd.isna(deposits[y])
    }
    line = _series_line("Cho vay / tiền gửi khách hàng", ldr, _fmt_frac_pct)
    if line:
        lines.append(line)
    current_col = trend.get("current_ratio_by_year") or {}
    line = _series_line("Khả năng thanh toán hiện hành", current_col, _fmt_times)
    if line:
        lines.append(line)

    if not lines:
        return "Không có dữ liệu tổng tài sản/vốn chủ sở hữu để đánh giá cơ cấu tài chính."
    return "\n".join(lines)


def _earnings_quality_paragraph(trend: dict) -> str:
    by_year = trend.get("cfo_to_ni_by_year") or {}
    avg = trend.get("cfo_to_ni_avg")
    if avg is None:
        return "Không có dữ liệu dòng tiền hoạt động để đánh giá chất lượng lợi nhuận."

    lines: list[str] = []
    label = "Tỷ lệ dòng tiền hoạt động/lợi nhuận sau thuế"
    line = _series_line(label, by_year, lambda v: f"{v:.2f}")
    if line:
        lines.append(line)
    lines.append(f"Bình quân giai đoạn: {avg:.2f}.")

    low_years = [
        y for y, v in by_year.items()
        if v is not None and not pd.isna(v) and v < _EARNINGS_QUALITY_THRESHOLD
    ]
    if low_years:
        lines.append(
            f"Các năm {', '.join(str(y) for y in low_years)} có tỷ lệ dưới mức "
            f"{_EARNINGS_QUALITY_THRESHOLD} — dấu hiệu lợi nhuận chưa đi kèm tiền thật."
        )
    return "\n".join(lines)


def _risk_paragraph(risk_hits: list[Hit]) -> str:
    if not risk_hits:
        return "Không phát hiện từ khoá rủi ro nào trong văn bản đã cung cấp."
    groups: dict[str, list[Hit]] = {}
    for hit in risk_hits:
        groups.setdefault(hit.group, []).append(hit)
    ranked = sorted(groups.items(), key=lambda kv: -kv[1][0].weight)

    lines = []
    for group_key, hits in ranked:
        lines.append(f"<b>{group_key}</b> ({len(hits)} lần nhắc tới):")
        # Toi da 3 vi du moi nhom, tranh nhan xet qua dai khi van ban co rat nhieu trung lap.
        seen_sentences: set[str] = set()
        shown = 0
        for hit in hits:
            if hit.sentence in seen_sentences:
                continue
            seen_sentences.add(hit.sentence)
            lines.append(f"  - “{hit.sentence[:200]}”")
            shown += 1
            if shown >= 3:
                break
    return "\n".join(lines)


def _conclusion_paragraph(audit: dict, trend: dict, risk_hits: list[Hit]) -> str:
    concerns = []
    if audit.get("opinion") in ("ngoại trừ", "từ chối", "trái ngược"):
        concerns.append("ý kiến kiểm toán không phải chấp nhận toàn phần")
    cfo_avg = trend.get("cfo_to_ni_avg")
    if cfo_avg is not None and cfo_avg < _EARNINGS_QUALITY_THRESHOLD:
        concerns.append("chất lượng lợi nhuận thấp (dòng tiền chưa theo kịp lợi nhuận)")
    if any(hit.group == "hoat_dong_lien_tuc" for hit in risk_hits):
        concerns.append("có dấu hiệu rủi ro về khả năng hoạt động liên tục")

    if concerns:
        return "Tổng thể có một số điểm cần lưu ý: " + "; ".join(concerns) + "."
    if trend.get("revenue_cagr") is not None or trend.get("net_income_cagr") is not None:
        return (
            "Trong phạm vi dữ liệu đã phân tích, không phát hiện dấu hiệu bất "
            "thường lớn về tình hình tài chính."
        )
    return "Không đủ dữ liệu để đưa ra kết luận tổng thể đáng tin cậy."
