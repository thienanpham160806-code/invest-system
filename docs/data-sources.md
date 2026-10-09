# Nguồn dữ liệu, giấy phép và đối chiếu

Cập nhật: 09/10/2026. Mọi số trên web/PDF kèm `{source, as_of, fetched_at}`; thiếu thì ghi "–" kèm lý do.

## 1. Bảng nguồn

| Dữ liệu | Nguồn | Live hay snapshot trên Vercel | Ghi chú |
|---|---|---|---|
| Danh sách mã + sàn (1.522 mã) | Vietcap public API `GET /price/symbols/getAll` | Snapshot (`webdata/snapshot/market_universe.parquet`) | Dựng bằng `scripts/build_market_universe.py` |
| Giá OHLCV ngày | Vietcap public API `POST /chart/OHLCChart/gap-chart` | **Live** (từ `sin1` gọi được, timeout 6 s), lỗi thì dùng kho chụp `webdata/snapshot/ohlcv.parquet` | `/api/py/sources` kiểm tra trực tiếp |
| VN-Index | như trên (mã `VNINDEX`) | **Live**, dự phòng `vnindex.parquet` | |
| Số CP niêm yết | Vietcap `POST /price/symbols/getList` → `listingInfo.listedShare` | Snapshot | Fallback ≈ vốn góp / 10.000đ, nhãn "xấp xỉ" (hiện 0 mã phải dùng) |
| Ngành ICB cấp 1–4 | vnstock `Reference().equity.list_by_industry()` (pivot đủ `icb1..icb4`, có `com_type_code` NH/CK/BH) | Snapshot | Bù bằng `fiinpro_icb_companies.csv` (vn-annual-report-miner); không có ở cả hai → "Chưa phân loại". Lần dựng 09/10/2026: 1.522/1.522 mã có ngành từ vnstock |
| BCTC năm (CĐKT, KQKD, LCTT) | `src/arminer/data/bctc_data/*/{HSX,HNX}.parquet` của [vn-annual-report-miner](https://github.com/Tumiqa/vn-annual-report-miner) (MIT, bản sao + LICENSE ở `data/reference/arminer/`) | Đóng gói (`webdata/bctc_long.parquet`, gộp lại theo mã để đọc theo row group) | HSX 409 + HNX 307 mã, FY2009–FY2025, không có UPCOM, không có quý |
| LNST 4 quý gần nhất (TTM) | vnstock `Fundamental().equity(sym).income_statement(period="quarter")` | Snapshot (`ttm.parquet`, top mã thanh khoản) | `scripts/build_ttm.py`; P/E TTM chỉ để hiển thị/đối chiếu |
| Vĩ mô | `config/macro_vn.csv` – GSO/NSO, NHNN, HNX, mỗi dòng có URL + ngày công bố | Đóng gói | World Bank API (live) chỉ để vẽ chuỗi lịch sử |
| Tin tức | Trang chủ đề mã CafeF `cafef.vn/{ma}.html` (theo `CafeFScraper` của repo thầy) + RSS CafeF/VnExpress | **Live** | Chấm cảm xúc bằng `analysis/sentiment.py` |
| BCTN gốc (PDF) | `zenodo_master_index.parquet` – Ngô Phú Thạnh (2025), DOI 10.5281/zenodo.20949551 (13.982 file) | Đóng gói (chỉ mục) | Chỉ hiện link Zenodo + link dự phòng CDN CafeF theo mẫu tên file trong `zenodo_downloader.py` |

## 2. Ánh xạ item_code arminer → chỉ tiêu chuẩn

Khai báo trong `src/invest_system/data/arminer_bctc.py` (`FIELD_CODES`): mỗi chỉ tiêu có danh sách ứng viên
(regex fullmatch), mã có hậu tố hash (vd `bs_von_chu_so_huu_4d280b22`) khớp mẫu `[0-9a-f]{8}`. Dòng nào được dùng
cho từng mã đều in ở tab **Dữ liệu & nguồn** và Phụ lục A của PDF.

Đã xác minh bằng số đã biết (test `tests/test_web_api.py`):

| Mã | Chỉ tiêu | Hệ thống | Kỳ vọng |
|---|---|---|---|
| FPT | Tổng tài sản FY2025 | 88.142 tỷ | ≈ 88.142 tỷ ✓ |
| VCB | Tổng tài sản FY2025 | 2.442.279 tỷ | ≈ 2.442.279 tỷ ✓ |
| FPT, VCB, SSI, BVH, HPG, VHM, SHS | TS = Nợ + VCSH | lệch 0,000% | ✓ |

## 3. Lỗi nguồn đã phát hiện và cách xử lý

1. **SSI FY2025 trùng FY2024** trong arminer (TS, doanh thu, LNST khớp từng đồng). Hệ thống tự phát hiện năm cuối
   là bản sao năm trước và loại năm đó (quét toàn bộ 716 mã: chỉ SSI bị).
2. **EPS báo cáo của SSI** ở một số năm ghi nhầm bằng LNST (2,8 nghìn tỷ đ/cp) → bỏ, dùng EPS tự tính.
3. **EPS ngân hàng** trong arminer = 0 ở nhiều năm → dùng LNST CĐ mẹ / số CP.
4. EPS tự tính (LNST CĐ mẹ / **số CP niêm yết hiện tại**) lệch EPS báo cáo khi DN phát hành thêm/chia cổ tức
   bằng CP sau kỳ báo cáo (vd VHM: 5.100 đ vs 10.200 đ do số CP tăng gấp đôi). Kiểm tra "EPS tự tính vs EPS báo cáo"
   hiện cảnh báo khi lệch > 15%.

## 4. Đối chiếu P/E, P/B, vốn hoá với CafeF / Vietstock (09/10/2026)

| Mã | Chỉ số | Hệ thống | CafeF/Vietstock | Lệch | Nguyên nhân |
|---|---|---|---|---|---|
| FPT | Vốn hoá | 100,1 nghìn tỷ @58.400 (1,714 tỷ CP niêm yết) | 117,1 nghìn tỷ @62.100 (02/10) | quy về cùng giá: ~10% | CafeF dùng số CP **lưu hành** sau đợt phát hành cổ tức bằng CP (~1,886 tỷ CP), Vietcap `listedShare` chưa cập nhật phần mới niêm yết |
| FPT | P/E | 10,7x (FY2025) | 12,5x (TTM) | ~9% (cùng giá) | TTM vs FY + khác số CP |
| FPT | P/B | 2,74x | ~3,1x | ~6% (cùng giá) | VCSH giữa năm 2026 vs cuối 2025 |
| VCB | Vốn hoá | 473,8 nghìn tỷ @56.700 | 472,1 nghìn tỷ @56.500 | < 0,1% (cùng giá) | ✓ |
| VCB | P/E | 13,4x (FY2025) | 11,4x (TTM) | **18%** | LN 4 quý gần nhất (Q3/25–Q2/26) cao hơn FY2025; hệ thống hiện thêm P/E TTM từ vnstock quý |
| VCB | P/B | 2,11x | 1,9x | 11% | VCSH tại Q2/2026 lớn hơn cuối 2025 (BCTC năm) |
| HPG | Vốn hoá | 170,5 nghìn tỷ @20.200 | 173,1 nghìn tỷ (06/10) | ~1,5% | khác ngày giá |
| HPG | P/E | 11,0x (FY2025) | 7,45x (TTM) | **48%** | LNST Q1/2026 tăng 170% → TTM cao hơn hẳn FY2025. Đây là giới hạn chính của BCTC năm; P/E TTM (vnstock quý) được hiển thị cạnh P/E FY |
| HPG | P/B | 1,32x | 1,23x | 7% | VCSH giữa năm 2026 |

Nguồn đối chiếu: [CafeF FPT](https://cafef.vn/du-lieu/hose/fpt-cong-ty-co-phan-fpt.chn),
[CafeF VCB](https://cafef.vn/du-lieu/hose/vcb-ngan-hang-thuong-mai-co-phan-ngoai-thuong-viet-nam.chn),
[CafeF HPG](https://cafef.vn/du-lieu/hose/hpg-cong-ty-co-phan-tap-doan-hoa-phat.chn),
[CafeF – FPT giảm 10 phiên](https://cafef.vn/co-phieu-fpt-bat-ngo-giam-10-phien-lien-tiep-von-hoa-boc-hoi-gan-12000-ty-dong-chi-sau-2-tuan-188261006223053904.chn).

**Kết luận**: vốn hoá khớp khi dùng cùng giá và cùng số CP; P/E/P/B lệch có hệ thống vì BCTC năm (FY2025) trễ
hơn TTM/giữa năm 2026. Định giá vẫn dùng FY để **nhất quán** với bội số ngành (cũng tính trên FY cho toàn bộ ~700 mã),
P/E TTM được hiển thị riêng cho các mã có số quý.

## 5. Vĩ mô (đã tra 09/10/2026)

Xem `config/macro_vn.csv` – mỗi dòng có URL nguồn và ngày công bố. Các dòng 2024 (GDP 7,09%, CPI 3,63%, tín dụng 15,08%)
đã kiểm tra lại. Số mới nhất: GDP Q3/2026 +9,95% (9T +9,01%), CPI bình quân 9T +4,52% (tháng 9 +5,08% yoy),
tín dụng +11,59% từ đầu năm (+16,69% yoy), tỷ giá trung tâm 25.638 (07/10), TPCP 10 năm 4,43% (phiên cuối 9/2026),
lãi suất tái cấp vốn 4,50% (NHNN giữ nguyên từ đầu năm).
