# Báo cáo kiểm tra số liệu trong báo cáo

Tạo lúc: 2026-10-09T23:33:56+07:00

Kiểm tra 15 mã × 15 trường: giá, số cổ phiếu, vốn hóa, doanh thu FY, LNST cổ đông mẹ, tổng tài sản, nợ phải trả, vốn chủ, sai lệch phương trình kế toán, P/E TTM, P/B, ROE, giá trị cơ sở, upside và độ tin cậy.

| Mã | Năm BCTC | Đồng nhất CDKT | P/B vs VCSH mẹ | Giá | Số CP | Độ tin cậy | PDF |
|---|---:|---|---|---|---|---|---|
| FPT | 2025 | PASS | PASS | PASS | PASS | PASS | PASS |
| VCB | 2025 | PASS | PASS | PASS | PASS | PASS | PASS |
| VIC | 2025 | PASS | PASS | PASS | PASS | PASS | PASS |
| VHM | 2025 | PASS | PASS | PASS | PASS | PASS | PASS |
| HPG | 2025 | PASS | PASS | PASS | PASS | PASS | PASS |
| MWG | 2025 | PASS | PASS | PASS | PASS | PASS | PASS |
| SSI | 2024 | PASS | PASS | PASS | PASS | PASS | PASS |
| MSN | 2025 | PASS | PASS | PASS | PASS | PASS | PASS |
| GAS | 2025 | PASS | PASS | PASS | PASS | PASS | PASS |
| VNM | 2025 | PASS | PASS | PASS | PASS | PASS | PASS |
| TCB | 2025 | PASS | PASS | PASS | PASS | PASS | PASS |
| ACB | 2025 | PASS | PASS | PASS | PASS | PASS | PASS |
| VRE | 2025 | PASS | PASS | PASS | PASS | PASS | PASS |
| BSR | 2025 | PASS | PASS | PASS | PASS | PASS | PASS |
| ACV | None | WARN | WARN | PASS | PASS | PASS | PASS |

Kiểm tra công thức độc lập: PASS 96, WARN 0, SKIP 9, FAIL 0.
SKIP nghĩa là snapshot thiếu đầu vào để tính (ví dụ ACV chưa có BCTC hoặc VIC/MSN chưa có mục tiêu định giá); WARN cần rà số liệu/phương pháp.

## Giới hạn đối chiếu PDF

Nếu `--pdf-dir` được truyền, script tìm PDF theo mã và đối chiếu từng số bên cạnh nhãn. Khi kèm `--analysis-json-dir`, headline giá/số cổ phiếu/vốn hóa/giá mục tiêu/upside/độ tin cậy lấy từ API analysis của đúng Preview/deployment ghi trong `pdf-audit-data.json`; số BCTC lấy từ snapshot trong bản audit. Bốn giá trị BCTC thô là SKIP vì mẫu PDF không in các số này; appendix có ánh xạ trường và dòng validation cân đối. Đây là đối chiếu text tự động, không xác minh bố cục thị giác. `MISSING` không được tính là PASS. PDF server-side đã được kiểm tra bằng 15 lượt tải HTTP 200 từ cùng Preview.

## Kiểm tra định giá trọng điểm

VHM được định giá theo nhóm peer đã loại chính mã mục tiêu; regression P/B–ROE chỉ bật khi mẫu thanh khoản đủ lớn, hệ số dốc dương và R² đạt ngưỡng; P/B dự báo bị chặn trong P25–P90. Các mã đa ngành VIC/MSN chỉ dùng P/B lịch sử nếu có ít nhất ba FY giao dịch hợp lệ; khi snapshot giá không có đủ điểm lịch sử, hệ thống hạ độ tin cậy và không xuất mục tiêu giá.

Dữ liệu từng mã, 15 trường, nguồn và thời điểm nằm trong `pdf-audit-data.json`.
