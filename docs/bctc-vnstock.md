# Mở rộng dữ liệu BCTC

`scripts/fetch_bctc_vnstock.py` bổ sung báo cáo năm qua Vietcap/VCI trong vnstock và lưu cùng schema dài với arminer. Mỗi mã được kiểm tra tối thiểu 5 kỳ năm, đơn vị VND, phương trình `tài sản = nợ phải trả + vốn chủ` sai lệch tối đa 1%, và trường doanh thu phù hợp với ngành. TTM chỉ được tạo khi có bốn quý liên tiếp và dùng lợi nhuận cổ đông công ty mẹ.

Chạy thử một nhóm nhỏ trước:

```powershell
python scripts/fetch_bctc_vnstock.py --exchange UPCOM --top 10 --resume
```

Chạy toàn bộ UPCOM rồi bổ sung sáu mã HOSE/HNX còn thiếu trong dữ liệu đóng gói:

```powershell
python scripts/fetch_bctc_vnstock.py --exchange UPCOM --resume --upload
python scripts/fetch_bctc_vnstock.py --exchange HOSE --resume --upload
python scripts/fetch_bctc_vnstock.py --exchange HNX --resume --upload
python scripts/check_bctc_coverage.py
```

Mặc định đợi 3.2 giây giữa các truy vấn để tôn trọng giới hạn nguồn. Bật `--upload` cần `BLOB_READ_WRITE_TOKEN`; runner cần `BLOB_BASE_URL` để tải bản đã công bố trước khi gộp bản mới. GitHub Actions cần các secrets `VNSTOCK_API_KEY`, `BLOB_READ_WRITE_TOKEN`, `BLOB_BASE_URL`. Hai workflow trong `.github/workflows/` chạy hàng tuần, có thể chạy thủ công và không gọi LLM.

Mỗi mã được lưu checkpoint riêng. Chạy lại với `--resume` sẽ bỏ qua mã đã thành công và thử lại mã lỗi. Bao phủ được tính theo mã đang giao dịch đúng sàn; một bản ghi lịch sử HOSE/HNX trùng ticker không được tính thay cho UPCOM.

## Giới hạn hiện tại

Repo hiện không có kết nối mạng outbound đáng tin cậy từ máy chạy này, nên chưa thể xác minh tài khoản vnstock, tải đủ 817 mã hay so khớp ACV/BSR/VEA/MCH/QNS trực tiếp với CafeF. Workflow được cấu hình để thực hiện phần thu thập khi chạy trong GitHub Actions; không ghi nhận dữ liệu chưa tải là đã hoàn tất.
