# invest-system — Hệ thống phân tích cơ hội đầu tư cổ phiếu

Nhập **một mã cổ phiếu bất kỳ** (HOSE/HNX/UPCOM), hệ thống tự thu thập dữ liệu, phân tích theo khung
**top-down của công ty chứng khoán** và xuất **báo cáo PDF** theo lựa chọn của người dùng:

```
Vĩ mô  →  Ngành  →  Doanh nghiệp  →  Định giá theo loại DN  →  Khuyến nghị (MUA … BÁN)  →  PDF
```

Báo cáo mẫu (dữ liệu giả lập, chạy offline): [`outputs/samples/`](outputs/samples/).

## Web app (Vercel) — bản production

**Demo:** https://invest-system-silk.vercel.app  ·  API: `/api/py/docs`  ·  Kiểm tra nguồn live: `/nguon`

| Trang | Nội dung |
|---|---|
| `/` | Tìm mã (tên/thương hiệu), VN-Index live, thống kê toàn thị trường, vĩ mô mới nhất kèm link nguồn, ngành cấp 1 |
| `/nganh` | Mọi nút ICB cấp 1–4 tính từ **toàn bộ 1.522 mã**: số mã, vốn hoá & tỷ trọng, GTGD, hiệu suất 1T/3T/YTD/1N so VN-Index, P/E–P/B–ROE trung vị (P25/P75), P/E gộp, điểm & hạng ngành, tỷ lệ phủ |
| `/nganh/[slug]` | Chỉ số ngành cap-weighted (=100) vs VN-Index, phân phối P/E–P/B, scatter P/B–ROE, **bảng tất cả mã** (lọc, sắp xếp, CSV) |
| `/stock/[mã]` | 10 tab: Tổng quan (khuyến nghị, giá mục tiêu, 7 nhóm điểm, luận điểm/rủi ro) · Vĩ mô · Ngành (phân vị trong toàn ngành) · BCTC (CĐKT/KQKD/LCTT, tên gốc, % quy mô, YoY, CSV) · Chỉ số (hover xem công thức) · Định giá (3 kịch bản + giả định) · Kỹ thuật (nến) · Tin tức · Tài liệu BCTN · Dữ liệu & nguồn |
| `/report/[mã]?sections=&years=&template=` | Báo cáo in A4 kiểu SSI/VCSC; nút "Xuất PDF" (in trình duyệt) và "Tải PDF từ máy chủ" (`/api/pdf`, Chromium headless) |

### Kiến trúc

```
Next.js 16 App Router (app/, components/, lib/)  ──rewrite /api/py/:path*──►  api/index.py (FastAPI, Python 3.12, sin1)
        │                                                                       │ import src/invest_system (giữ nguyên CLI/Streamlit/WeasyPrint)
        └─ app/api/pdf/route.ts (puppeteer-core 25.11 + @sparticuz/chromium 153)│ web/service.py → analysis/* (macro, sector, ratios, valuation,
                                                                                │                  technical, sentiment, composite), validation/checks
   Vercel Blob  universe/latest.parquet ─────► web/universe.py (cache 10') ◄────┘ fallback: webdata/snapshot/* đóng gói trong repo
   Live: Vietcap gap-chart (giá, VN-Index), CafeF/RSS (tin), World Bank (chuỗi vĩ mô)
```

Bảng toàn thị trường **tính sẵn trên máy ở VN** (Vercel không gọi 1.500 mã trong một request):

```bash
pip install -r requirements-local.txt        # có vnstock (chỉ dùng local)
python scripts/backfill_data.py              # giá toàn sàn, ~2 phút
python scripts/build_market_universe.py      # 1.522 mã: ngành ICB 1–4, giá, số CP, P/E–P/B–ROE tự tính (~1,5 phút)
python scripts/build_ttm.py --top 120        # LNST 4 quý gần nhất (vnstock) cho mã thanh khoản cao (~4 phút)
vercel env pull .env.local                   # lấy BLOB_READ_WRITE_TOKEN
python scripts/build_market_universe.py --upload-only   # đẩy lên Vercel Blob – web đọc bản mới, không cần deploy lại
bash scripts/deploy_vercel.sh                # (khi đổi code) deploy bản sạch từ HEAD
```

Kiểm tra tự động khi dựng: số mã universe = số mã getAll; mỗi mã đúng 1 nút ICB4; tổng mã các ngành cấp 1 = tổng universe.

Chạy web local: `pip install -r requirements.txt && npm install`, rồi `npm run fastapi-dev` và `npm run dev` (http://localhost:3000).

**Nguồn, giấy phép, đối chiếu với CafeF/Vietstock, lỗi nguồn đã phát hiện:** [`docs/data-sources.md`](docs/data-sources.md).

### Giới hạn của bản web
- BCTC năm (arminer) chỉ phủ HSX/HNX đến FY2025; mã UPCOM có giá + ngành, phần BCTC/định giá ghi rõ "chưa có nguồn BCTC".
- P/E/định giá dùng FY2025 để nhất quán với bội số ngành; P/E TTM (vnstock quý) chỉ có cho mã thanh khoản cao.
- Số CP = `listedShare` (niêm yết) → có thể thấp hơn số lưu hành khi DN vừa phát hành CP chưa niêm yết (vd FPT).
- Vĩ mô nhập tay có URL nguồn (tra cứu 09/10/2026); cần cập nhật `config/macro_vn.csv` khi GSO/NHNN công bố số mới.

## Đáp ứng yêu cầu đề bài

| Yêu cầu | Cách hệ thống đáp ứng |
|---|---|
| Giá & dữ liệu giao dịch | Kho giá toàn sàn + DNSE + Vietcap (tái sử dụng từ `bot-phan-tich`), dự phòng API công khai Vietcap — `data/prices.py` |
| BCTC & chỉ số tài chính | vnstock (Vietcap/VCI) → `vnfinancialdata` (UEL, HuggingFace) → file nhập tay; chuẩn hoá về một bộ chỉ tiêu — `data/fundamentals.py` |
| Thông tin, tin tức | Công bố thông tin chính thức (VCI) + RSS CafeF/VnExpress, chấm cảm xúc bằng từ điển tài chính tiếng Việt — `analysis/sentiment.py` |
| Format báo cáo CTCK | Trang 1 kiểu SSI/VCSC: ô khuyến nghị, giá mục tiêu, upside, bảng chỉ số bên lề, luận điểm & rủi ro, chart giá vs VN-Index — `report/templates/report.html` |
| Đánh giá vĩ mô | GSO/NHNN (nhập tay có nguồn) + World Bank API; chấm điểm và quy đổi tác động lên ngành bằng ma trận độ nhạy — `analysis/macro.py` |
| Phân tích ngành | Nhóm cùng ngành ICB, trung vị P/E, P/B, ROE; chỉ số ngành tự tính so với VN-Index; vị thế DN theo phân vị — `analysis/sector.py` |
| Cơ hội đầu tư | Định giá **theo loại DN** (ngân hàng: P/B Gordon; DN thường: P/E, EV/EBITDA, DCF FCFF…), 3 kịch bản, điểm tổng hợp 7 nhóm → khuyến nghị — `analysis/valuation.py`, `analysis/composite.py` |
| PDF theo nhu cầu | Chọn mã, mục, số năm, mẫu Đầy đủ / Tóm tắt (CLI hoặc giao diện web) |
| **Chính xác dữ liệu** | Nhật ký nguồn cho **mọi** số liệu (Phụ lục C), ánh xạ chỉ tiêu ↔ dòng gốc (Phụ lục A), 15+ kiểm tra tự động: TS = Nợ + VCSH, đơn vị, độ mới của giá, biên độ, đối chiếu ROE/P/E với nguồn thứ hai (Phụ lục B). Thiếu số → `N/A`, không bịa. |
| **Đánh giá thích hợp** | Ngân hàng không dùng DCF/EV-EBITDA; phương pháp lệch > 2,5× trung vị bị loại khỏi bình quân; không có dữ liệu ngành → so với lịch sử 5 năm của chính DN |
| **Sáng tạo** | Radar 7 nhóm điểm, football-field định giá, text mining BCTC PDF (ý kiến kiểm toán, từ khoá rủi ro), cảm xúc tin tức, nhận định bằng OpenAI/Gemini có kiểm tra số liệu |

## Chạy nhanh (Windows)

```bat
git clone https://github.com/thienanpham160806-code/invest-system.git
cd invest-system
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env

:: 1) Chạy thử offline bằng dữ liệu giả lập (luôn chạy được)
python cli.py --ticker DEMO,DEMOB

:: 2) Kiểm tra nguồn dữ liệu nào chạy trên máy này
python scripts/check_sources.py FPT

:: 3) Báo cáo thật
python cli.py --ticker FPT
python cli.py --ticker VCB,HPG,VHM --template summary
python cli.py --ticker MWG --sections macro,sector,company,valuation --years 5

:: 4) Giao diện web
streamlit run app.py
```

PDF nằm ở `outputs/reports/`.

### PDF engine

`report/render.py` thử lần lượt **WeasyPrint → Playwright → HTML**.

- macOS/Linux: WeasyPrint cài qua pip là chạy.
- Windows: WeasyPrint cần GTK runtime. Cách nhanh hơn là dùng Chromium:
  `pip install playwright && playwright install chromium`, rồi chạy `python cli.py -t FPT --engine playwright`.
- Không có engine nào thì hệ thống xuất `.html` (mở bằng trình duyệt → In → Lưu PDF).

### Dữ liệu cần chuẩn bị trước khi demo

1. **vnstock** (BCTC, ngành, tin công bố): gói đang bị PyPI cách ly. Máy nào đã cài từ dự án bot thì dùng
   luôn venv đó, hoặc `pip install "vnstock>=4.0"` khi gói được mở lại. Thiếu vnstock: giá vẫn chạy, BCTC lấy
   từ `vnfinancialdata` (chạy `hf auth login` một lần) hoặc file tay.
2. **Vĩ mô**: mở `config/macro_vn.csv` và điền các dòng `CẦN CẬP NHẬT` (GDP, CPI 2025, lãi suất,
   tỷ giá, TPCP 10 năm) theo số GSO/NHNN, kèm nguồn. Các dòng 2024 đã điền sẵn, **nhóm kiểm tra lại**.
3. (Tuỳ chọn) Kho giá toàn sàn để tìm peers nhanh: `python scripts/backfill_data.py` (2–3 phút).
4. (Tuỳ chọn) Text mining BCTC: đặt file PDF BCTC vào `data/reports/<MÃ>/`.
5. (Tuỳ chọn) Mã không có BCTC ở nguồn nào: `python scripts/make_manual_template.py ABC`, rồi điền
   `data/manual/ABC_financials.csv` (VND).

## Kiến trúc

```
src/invest_system/
├── data/                    # TẦNG DỮ LIỆU
│   ├── router.py dnse.py vietcap.py cache.py cleaner.py market_store.py   ← tái sử dụng bot-phan-tich
│   ├── macro_news.py        ← RSS (tái sử dụng)
│   ├── prices.py            # OHLCV, VN-Index, beta, biến động
│   ├── fundamentals.py      # BCTC chuẩn hoá + ánh xạ tên cột (vnstock / tiếng Việt / file tay)
│   ├── company.py           # hồ sơ, ngành ICB, loại DN, peers, tin tức
│   ├── macro.py             # GSO/NHNN (CSV) + World Bank API
│   └── demo.py              # dữ liệu GIẢ LẬP (mã DEMO*, không trùng mã thật)
├── validation/checks.py     # kiểm tra chất lượng dữ liệu
├── analysis/
│   ├── macro.py             # điểm vĩ mô + tác động lên ngành
│   ├── sector.py            # peers, trung vị, chỉ số ngành, vị thế
│   ├── ratios.py            # chỉ số DN thường & ngân hàng (NIM, CIR, chi phí tín dụng, LDR)
│   ├── valuation.py         # định giá theo loại DN, 3 kịch bản
│   ├── technical.py         ← MACD + RSI thích ứng + Ichimoku (tái sử dụng scoring.py của bot)
│   ├── fintext.py           ← text mining BCTC PDF (tái sử dụng)
│   ├── sentiment.py         # cảm xúc tin tức
│   └── composite.py         # điểm tổng hợp, khuyến nghị, luận điểm & rủi ro
├── narrative/               # nhận định: quy tắc (mặc định) + OpenAI/Gemini (tuỳ chọn)
├── charts/                  # biểu đồ PDF (+ chart kỹ thuật của bot)
├── report/                  # Jinja2 template kiểu CTCK → PDF
├── provenance.py            # nhật ký nguồn của từng số liệu
└── pipeline.py              # analyze() / run()
app.py   cli.py   config/   scripts/   tests/
```

### Phương pháp định giá theo loại doanh nghiệp

| Loại DN (nhận diện từ ngành ICB) | Phương pháp (tỷ trọng mặc định) |
|---|---|
| Phi tài chính | P/E tương đối 35%, DCF FCFF 5 năm 35%, P/B 15%, EV/EBITDA 15% |
| Ngân hàng | P/B hợp lý `(ROE − g)/(Ke − g)` 50%, P/B tương đối 30%, P/E 20% |
| Chứng khoán / Bảo hiểm / BĐS | P/B tương đối 60%, P/E tương đối 40% (RNAV cho BĐS: hướng mở rộng) |

- `Ke = rf + β × ERP`, với β tính từ lợi suất tuần 2 năm so với VN-Index (giới hạn 0,6–1,8).
- Ba kịch bản lấy phân vị 25/50/75 của bội số ngành, WACC ±1%, tăng trưởng ±2%, ROE ±2 điểm %.
- Khuyến nghị theo upside: MUA ≥ 20%, KHẢ QUAN 10–20%, NẮM GIỮ −5…10%, KÉM KHẢ QUAN −15…−5%, BÁN < −15%.
  Điểm tổng hợp ≥ 70 nâng 1 bậc, < 40 hạ 1 bậc.
- Mọi tham số nằm trong `config/settings.yaml` và được in trong Phụ lục C của PDF.

## Nhận định bằng OpenAI hoặc Gemini (tuỳ chọn)

Báo cáo vẫn tính điểm, định giá và khuyến nghị bằng các quy tắc có thể kiểm tra. Có thể chọn **một** provider bằng `LLM_PROVIDER=openai` hoặc `LLM_PROVIDER=gemini`; ứng dụng không gọi cả hai trong cùng một lần phân tích. Mặc định `LLM_ENABLED=0` nên chỉ lưu API key chưa gọi mô hình. Khi bật, mô hình tổng hợp đánh giá vĩ mô từ chỉ tiêu, nguồn và điểm đã tính; phần ngành và doanh nghiệp được biên tập thành nhận định liền mạch hơn. Mô hình không tra cứu hoặc tự thêm dữ kiện; nhận định bị loại nếu chứa số ngoài đầu vào. Khi API lỗi, báo cáo dùng nhận định theo quy tắc.

Trong file `.env`, đặt key tương ứng với provider đã chọn (`OPENAI_API_KEY` hoặc `GEMINI_API_KEY`), rồi chủ động bật `LLM_ENABLED=1`. Model mặc định OpenAI là `gpt-6-luna`; Gemini là `gemini-3.5-flash-lite`; giới hạn đầu ra mặc định 500 token mỗi lần gọi. Khi deploy Vercel, khai báo các biến trong **Project → Settings → Environment Variables**; không dùng tiền tố `NEXT_PUBLIC_` và không đưa key vào mã nguồn hoặc commit lên Git. Có thể đặt giới hạn chi tiêu cứng trong OpenAI API project; hệ thống áp dụng hạn mức có thể trễ một chút.

## Kiểm thử

```bash
pytest -q        # 75 test: định giá, kiểm tra dữ liệu, chuẩn hoá BCTC, cảm xúc, pipeline demo + test chỉ báo của bot
```

## Giới hạn đã biết (nhóm nên nói rõ khi bảo vệ)

- EPS/BVPS dựa trên BCTC **năm** gần nhất (FY), chưa dùng 4 quý gần nhất (TTM).
- Tên cột vnstock cho một số chỉ tiêu (capex, vay nợ…) là ứng viên + tìm theo từ khoá.
  Cột nào được dùng đều in ở Phụ lục A, nên kiểm tra lại với một mã quen thuộc trước khi demo.
- NIM là xấp xỉ (thu nhập lãi thuần / tổng tài sản bình quân), không phải / tài sản sinh lãi.
- Tín hiệu kỹ thuật kế thừa từ bot đã được backtest walk-forward là **không có edge**,
  nên chỉ chiếm 10% điểm tổng hợp.

## Nguồn tham khảo

- Ngo, P. T. (2025). *Vietnam Listed Companies Annual Reports PDF Dataset, 2000–2025*. Zenodo. doi:10.5281/zenodo.20949551
- Ngo, P. T. *vnfinancialdata* — https://github.com/thanhnp-uel/vnfinancialdata
- Tumiqa, *vn-annual-report-miner* — https://github.com/Tumiqa/vn-annual-report-miner
- World Bank Open Data API; Tổng cục Thống kê; Ngân hàng Nhà nước Việt Nam.
- Loughran, T. & McDonald, B. (2011). When is a liability not a liability? *Journal of Finance*.

Font Be Vietnam Pro (SIL Open Font License, `assets/fonts/OFL.txt`).
