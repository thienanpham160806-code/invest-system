# Kiểm định định giá và nhận định

Ngày tạo: 2026-10-09T15:55:26.484114+07:00

| Mã | Giá | Số CP | Vốn hoá | P/E TTM (nếu có, nếu không FY) | P/B | Phương pháp hợp lệ | Mục tiêu | Upside | Khuyến nghị · tin cậy |
|---|---:|---:|---:|---:|---:|---|---:|---:|---|
| FPT | 57,900 | 1,714,326,422 | 99.26 T | 10.3x | 2.72x | pe_relative, dcf_fcff | 81,700 | 41.1% | MUA · TRUNG BÌNH |
| VCB | 56,700 | 8,355,675,094 | 473.77 T | 11.6x | 2.11x | pe_relative, pb_relative, justified_pb | 49,200 | -13.2% | KÉM KHẢ QUAN · CAO |
| VIC | 227,000 | 7,762,186,429 | 1,762.02 T | 72.2x | 11.94x | không đủ dữ liệu | — | — | THEO DÕI · THẤP |
| VHM | 65,600 | 8,214,824,008 | 538.89 T | 9.6x | 2.26x | pb_relative | 256,200 | 290.5% | THEO DÕI · THẤP |
| HPG | 20,150 | 8,442,964,520 | 170.13 T | 9.7x | 1.32x | pe_relative, pb_relative | 28,500 | 41.4% | THEO DÕI · THẤP |
| MWG | 75,600 | 1,477,035,294 | 111.66 T | 12.8x | 3.43x | pe_relative, pb_relative, dcf_fcff | 111,900 | 48.0% | MUA · CAO |
| SSI | 19,200 | 3,003,293,801 | 57.66 T | 13.2x | 2.16x | pe_relative, pb_relative | 17,500 | -8.9% | KÉM KHẢ QUAN · TRUNG BÌNH |
| MSN | 74,200 | 1,460,374,611 | 108.36 T | 17.5x | 3.07x | không đủ dữ liệu | — | — | THEO DÕI · THẤP |
| GAS | 81,200 | 2,412,949,756 | 195.93 T | 15.7x | 2.96x | pe_relative, pb_relative, dcf_fcff | 66,300 | -18.3% | BÁN · CAO |
| VNM | 57,800 | 2,089,955,445 | 120.80 T | 12.0x | 3.94x | pe_relative, pb_relative, dcf_fcff | 73,200 | 26.6% | THEO DÕI · THẤP |
| TCB | 32,150 | 7,086,240,414 | 227.82 T | 8.3x | 1.27x | pe_relative, pb_relative, justified_pb | 35,500 | 10.4% | KHẢ QUAN · CAO |
| ACB | 20,300 | 5,804,421,957 | 117.83 T | 7.8x | 1.25x | pe_relative, pb_relative, justified_pb | 32,800 | 61.6% | MUA · CAO |

## Cách đọc và dữ liệu

- Giá lấy từ nguồn giá đang khả dụng; số cổ phiếu lấy từ `listedShare` trong Vietcap `getList`, ngày theo metadata universe. P/E dùng LNST cổ đông công ty mẹ TTM khi có, nếu không dùng FY; P/B dùng vốn chủ sở hữu cổ đông công ty mẹ.
- Khi nguồn mạng bị chặn, ứng dụng ghi rõ đang dùng snapshot. Bản audit được sinh bởi `scripts/valuation_audit.py`; chi tiết kỳ, nguồn, độ tin cậy, nhận định và rủi ro từng mã nằm trong `valuation-audit-data.json`.
- VIC trước sửa: theo tái hiện trên dữ liệu snapshot, giá 225.500đ, mục tiêu 18.500đ, upside −91,8%, khuyến nghị BÁN; công thức dùng trung vị P/E/P/B của nhóm ICB quá rộng và P/E FY 155,2x. Sau sửa: P/E không còn dùng khi >60x, tập đoàn đa ngành chỉ dùng P/B lịch sử 5 năm; thiếu đủ 3 điểm lịch sử thì không công bố giá mục tiêu, độ tin cậy THẤP, khuyến nghị THEO DÕI. Số lượng cổ phiếu hiện tại là 7.762.186.429 theo Vietcap; ngày snapshot ghi trong từng bản ghi.
- Quy tắc kiểm thử: không để mã nào có upside ngoài [−50%; +100%] vẫn nhận MUA/BÁN. Kết quả lần chạy: `không có`.

## Đối chiếu công khai

CafeF có trang thông tin VIC hiện hành, nhưng kết quả web không trả cùng bộ số định lượng/đúng timestamp với snapshot này. Vietstock có báo cáo Vietcap VIC ngày 30/03/2026 nêu vốn hoá 977,3 nghìn tỷ, P/E trượt 85,2x và P/B 6,6x; đây là ngày khác và loại trừ cổ phiếu VIC do công ty con sở hữu, nên không thể coi là đối chiếu cùng kỳ với số liệu snapshot 09/10/2026. Không dùng benchmark lệch ngày để kết luận sai số định lượng. [CafeF VIC](https://cafef.vn/du-lieu/vic/bao-cao-tai-chinh.chn) · [Vietstock/Vietcap, 30/03/2026](https://static1.vietstock.vn/edocs/19653/Vinstocks_20260330_VN.pdf).

## Nhận định trang đầu

Mỗi bản ghi `thesis`/`risks` trong tệp JSON là nội dung narrative đầu trang gửi cùng API. Đã bỏ câu định giá khỏi luận điểm khi độ tin cậy THẤP, hiển thị lý do theo dõi và ký hiệu tăng trưởng có dấu; không phát sinh khuyến nghị mua/bán từ giá mục tiêu không đáng tin cậy.
