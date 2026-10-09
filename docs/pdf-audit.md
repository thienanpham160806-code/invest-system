# Báo cáo kiểm tra số liệu trong báo cáo

Tạo lúc: 2026-10-09T18:40:01+07:00

Kiểm tra 15 mã × 15 trường: giá, số cổ phiếu, vốn hóa, doanh thu FY, LNST cổ đông mẹ, tổng tài sản, nợ phải trả, vốn chủ, sai lệch phương trình kế toán, P/E TTM, P/B, ROE, giá trị cơ sở, upside và độ tin cậy.

| Mã | Năm BCTC | Đồng nhất CDKT | P/B vs VCSH mẹ | Giá | Số CP | Độ tin cậy | PDF |
|---|---:|---|---|---|---|---|---|
| FPT | 2025 | PASS | PASS | PASS | PASS | PASS | NOT CHECKED |
| VCB | 2025 | PASS | PASS | PASS | PASS | PASS | NOT CHECKED |
| VIC | 2025 | PASS | PASS | PASS | PASS | PASS | NOT CHECKED |
| VHM | 2025 | PASS | PASS | PASS | PASS | PASS | NOT CHECKED |
| HPG | 2025 | PASS | PASS | PASS | PASS | PASS | NOT CHECKED |
| MWG | 2025 | PASS | PASS | PASS | PASS | PASS | NOT CHECKED |
| SSI | 2024 | PASS | PASS | PASS | PASS | PASS | NOT CHECKED |
| MSN | 2025 | PASS | PASS | PASS | PASS | PASS | NOT CHECKED |
| GAS | 2025 | PASS | PASS | PASS | PASS | PASS | NOT CHECKED |
| VNM | 2025 | PASS | PASS | PASS | PASS | PASS | NOT CHECKED |
| TCB | 2025 | PASS | PASS | PASS | PASS | PASS | NOT CHECKED |
| ACB | 2025 | PASS | PASS | PASS | PASS | PASS | NOT CHECKED |
| VRE | 2025 | PASS | PASS | PASS | PASS | PASS | NOT CHECKED |
| BSR | 2025 | PASS | PASS | PASS | PASS | PASS | NOT CHECKED |
| ACV | None | WARN | WARN | PASS | PASS | PASS | NOT CHECKED |

Kiểm tra công thức độc lập: PASS 96, WARN 0, SKIP 9, FAIL 0.
SKIP nghĩa là snapshot thiếu đầu vào để tính (ví dụ ACV chưa có BCTC hoặc VIC/MSN chưa có mục tiêu định giá); WARN cần rà số liệu/phương pháp.

## Giới hạn đối chiếu PDF

Nếu `--pdf-dir` được truyền, script tìm PDF theo mã, trích text và tìm các token số đã làm tròn. Đây là đối chiếu tự động mức sơ bộ; không xác minh token nằm đúng nhãn/đúng phần. `MISSING` nghĩa là chưa có PDF được cung cấp, không được tính là PASS.

## Kiểm tra định giá trọng điểm

VHM được định giá theo nhóm peer đã loại chính mã mục tiêu; regression P/B–ROE chỉ bật khi mẫu thanh khoản đủ lớn, hệ số dốc dương và R² đạt ngưỡng; P/B dự báo bị chặn trong P25–P90. Các mã đa ngành VIC/MSN chỉ dùng P/B lịch sử nếu có ít nhất ba FY giao dịch hợp lệ; khi snapshot giá không có đủ điểm lịch sử, hệ thống hạ độ tin cậy và không xuất mục tiêu giá.

Dữ liệu từng mã, 15 trường, nguồn và thời điểm nằm trong `pdf-audit-data.json`.
