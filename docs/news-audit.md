# Kiểm định gán tin theo mã

Ngày lấy mẫu (giờ Việt Nam): 2026-10-09T16:02:24.062720

Nguồn tin: production protected API. Cột nguồn ghi số bài trả về theo khoảng **30 ngày / 180 ngày**; số đếm bị giới hạn bởi tối đa 30 bài mỗi nguồn ở API. Mỗi mã có tối đa 10 tiêu đề và lý do gán trong `news-audit-data.json`. Khi nguồn bị chặn mạng, số liệu ghi “không xác định”, không diễn giải thành mã không có tin.

| Mã | Bài theo nguồn (30d/180d) | Tổng bài trả về | Tiêu đề lấy mẫu | Không có tin |
|---|---|---:|---:|---|
| FPT (HOSE) | CafeF (trang chủ đề mã): 12/12; CafeF TTCK: 1/1 | 13 | 10 | không |
| VCB (HOSE) | CafeF (trang chủ đề mã): 2/13; CafeF Tài chính: 3/3; VnExpress: 1/1 | 17 | 10 | không |
| VIC (HOSE) | CafeF (trang chủ đề mã): 1/4; VnExpress: 1/1 | 5 | 5 | không |
| VHM (HOSE) | CafeF (trang chủ đề mã): 3/13; CafeF TTCK: 1/1 | 14 | 10 | không |
| HPG (HOSE) | CafeF (trang chủ đề mã): 7/13; CafeF TTCK: 1/1 | 14 | 10 | không |
| MWG (HOSE) | CafeF (trang chủ đề mã): 4/7; CafeF TTCK: 1/1 | 8 | 8 | không |
| SSI (HOSE) | CafeF (trang chủ đề mã): 9/12; CafeF TTCK: 2/2 | 14 | 10 | không |
| MSN (HOSE) | CafeF (trang chủ đề mã): 1/10; CafeF TTCK: 2/2; VnExpress: 1/1 | 13 | 10 | không |
| GAS (HOSE) | CafeF (trang chủ đề mã): 2/5 | 5 | 5 | không |
| VNM (HOSE) | CafeF (trang chủ đề mã): 0/8 | 16 | 10 | không |
| TCB (HOSE) | CafeF (trang chủ đề mã): 1/10; CafeF Tài chính: 5/5 | 15 | 10 | không |
| ACB (HOSE) | CafeF (trang chủ đề mã): 9/9; CafeF Tài chính: 1/1 | 10 | 10 | không |
| CEO (HNX) | — | 0 | 0 | có |
| ART (UPCOM) | CafeF (trang chủ đề mã): 1/1 | 3 | 3 | không |
| BVS (HNX) | CafeF (trang chủ đề mã): 2/2 | 4 | 4 | không |
| IDC (HNX) | CafeF (trang chủ đề mã): 0/1 | 6 | 6 | không |
| PVS (HNX) | CafeF (trang chủ đề mã): 0/2 | 2 | 2 | không |
| VGI (UPCOM) | CafeF (trang chủ đề mã): 0/1 | 1 | 1 | không |
| MCH (HOSE) | CafeF (trang chủ đề mã): 1/3; CafeF TTCK: 1/1; VnExpress: 1/1 | 5 | 5 | không |
| QNS (UPCOM) | CafeF (trang chủ đề mã): 0/1 | 6 | 6 | không |

## Precision thủ công

Precision thủ công = tiêu đề được xác nhận liên quan đến đúng mã / tổng tiêu đề đã đánh giá. Trong mẫu này đã đọc 135 tiêu đề (tối đa 10/mã), precision 97.8%. Các false positive theo title được đánh dấu `manual_relevant: false` trong JSON và quy tắc tương ứng nằm trong script. Mẫu đạt mục tiêu 90% khi các nguồn truy cập được. Không coi lý do rule matcher là nhãn ground truth.

## Quy tắc gán

- Mã được so khớp theo token nguyên vẹn; mã mơ hồ VND, GAS, CEO, POW, BID, PET, HOT, ART cần ngữ cảnh chứng khoán hoặc nhắc tên/thương hiệu.
- Tên/thương hiệu được so không dấu. RSS vĩ mô không có liên hệ doanh nghiệp bị loại khỏi feed cổ phiếu.
- Đã gộp tiêu đề trùng không dấu và chuyển thời gian hiển thị sang giờ Việt Nam.
