# Kiểm định định giá và nhận định

Ngày tạo: 2026-10-09T18:39:59.718189+07:00

| Mã | Giá | Số CP | Vốn hoá | P/E TTM (nếu có, nếu không FY) | P/B | Phương pháp hợp lệ | Mục tiêu | Upside | Khuyến nghị · tin cậy |
|---|---:|---:|---:|---|---:|---|---:|---:|---|
| FPT | 57,900 | 1,714,326,422 | 99.26 T | 10.3x | 2.72x | pe_relative, dcf_fcff | 80,600 | 39.2% | MUA · TRUNG BÌNH |
| VCB | 56,700 | 8,355,675,094 | 473.77 T | 11.6x | 2.11x | pe_relative, pb_relative, justified_pb | 49,300 | -13.1% | KÉM KHẢ QUAN · CAO |
| VIC | 227,000 | 7,762,186,429 | 1,762.02 T | 72.2x | 11.94x | không đủ dữ liệu | — | — | THEO DÕI · THẤP |
| VHM | 65,600 | 8,214,824,008 | 538.89 T | 9.6x | 2.26x | pe_relative, pb_relative | 92,600 | 41.2% | MUA · TRUNG BÌNH |
| HPG | 20,150 | 8,442,964,520 | 170.13 T | 9.7x | 1.32x | pe_relative, pb_relative | 35,900 | 78.2% | THEO DÕI · THẤP |
| MWG | 75,600 | 1,477,035,294 | 111.66 T | 12.8x | 3.43x | pe_relative, pb_relative, dcf_fcff | 118,100 | 56.2% | MUA · CAO |
| SSI | 19,200 | 3,003,293,801 | 57.66 T | 13.2x | 2.16x | pe_relative, pb_relative | 15,100 | -21.4% | BÁN · TRUNG BÌNH |
| MSN | 74,200 | 1,460,374,611 | 108.36 T | 17.5x | 3.07x | không đủ dữ liệu | — | — | THEO DÕI · THẤP |
| GAS | 81,200 | 2,412,949,756 | 195.93 T | 15.7x | 2.96x | pe_relative, pb_relative, dcf_fcff | 95,300 | 17.4% | THEO DÕI · THẤP |
| VNM | 57,800 | 2,089,955,445 | 120.80 T | 12.0x | 3.94x | pb_relative, dcf_fcff | 40,500 | -29.9% | BÁN · TRUNG BÌNH |
| TCB | 32,150 | 7,086,240,414 | 227.82 T | 8.3x | 1.27x | pe_relative, pb_relative, justified_pb | 34,500 | 7.3% | NẮM GIỮ · CAO |
| ACB | 20,300 | 5,804,421,957 | 117.83 T | 7.8x | 1.25x | pe_relative, pb_relative, justified_pb | 32,800 | 61.6% | MUA · CAO |
| VRE | 23,200 | 2,328,818,410 | 54.03 T | 7.9x | 1.12x | pe_relative, pb_relative | 40,700 | 75.4% | MUA · TRUNG BÌNH |
| BSR | 31,250 | 5,007,299,686 | 156.48 T | 13.3x | 2.59x | pe_relative, pb_relative, dcf_fcff | 23,200 | -25.8% | BÁN · CAO |
| ACV | 40,900 | 3,582,324,023 | 146.52 T | —x | —x | không đủ dữ liệu | — | — | THEO DÕI · THẤP |

## Cách đọc và giới hạn

- Giá, số cổ phiếu, BCTC và thời điểm lấy từ snapshot ghi trong từng bản ghi; P/E ưu tiên LNST cổ đông mẹ TTM khi có, P/B dùng vốn chủ cổ đông mẹ.
- Loại chính mã mục tiêu khỏi peer set. Không dùng bội số gộp theo vốn hoá để định giá một doanh nghiệp riêng lẻ.
- P/B–ROE chỉ điều chỉnh trung vị peer khi có ít nhất 8 peer thanh khoản, hệ số dốc dương và R² ≥ 0,10; P/B mục tiêu bị chặn trong P25–P90. Nếu không đạt điều kiện, dùng trung vị peer thông thường.
- VHM sau sửa có giá trị cơ sở 92,600 đồng, upside 41.2% trên snapshot này; kết quả khác mức outlier cũ do không còn dùng bội số gộp vốn hoá. Đây là ước tính theo snapshot, không phải dự báo chắc chắn.
- VIC và MSN là trường hợp đa ngành: không áp P/E hoặc P/B peer rộng. Snapshot có lần lượt 0 và 0 năm P/B lịch sử hợp lệ; thiếu tối thiểu ba năm thì không công bố mục tiêu giá và giữ độ tin cậy thấp.
- Quy tắc cảnh báo kiểm tra các mã nhận MUA/BÁN có upside ngoài [-60%; +150%]. Danh sách lần chạy: không có.
- Dữ liệu từng mã, nguồn, thời điểm, peer selection, P/B regression và historical multiples nằm trong valuation-audit-data.json.

## Đối chiếu CafeF

CafeF công bố trang tải BCTC và hồ sơ tài chính hiện hành cho ACV; trang tải tài liệu có báo cáo hợp nhất năm 2025 đã kiểm toán và các báo cáo quý. CafeF cũng có báo cáo thường niên 2025 của BSR, VEA và MCH. Các tài liệu công khai này chưa được đối chiếu từng chỉ tiêu với snapshot trong repo ở lần chạy này; cần tải đúng báo cáo hợp nhất, cùng kỳ, rồi so khớp đơn vị và phạm vi hợp nhất trước khi đánh dấu PASS. [ACV – tải BCTC](https://cafef.vn/du-lieu/upcom/acv-tai-lieu.chn) · [ACV – hồ sơ](https://cafef.vn/du-lieu/acv/thong-tin-chung.chn) · [BSR – báo cáo thường niên 2025](https://cafef1.mediacdn.vn/download/160426/bsr-bao-cao-thuong-nien-nam-2025-0.pdf) · [VEA – báo cáo thường niên 2025](https://cafef1.mediacdn.vn/download/210426/vea-bao-cao-thuong-nien-2025-0-610380.pdf) · [MCH – báo cáo thường niên 2025](https://cafef1.mediacdn.vn/download/150426/mch-bao-cao-thuong-nien-nam-2025-0.pdf).

## PDF

Đối chiếu trường số liệu với văn bản PDF được tạo bởi scripts/audit_report_numbers.py; kết quả hiện tại nằm trong docs/pdf-audit.md. Nếu chưa cung cấp PDF đầu vào, trạng thái PDF là NOT CHECKED.
