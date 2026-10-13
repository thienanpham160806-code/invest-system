# Backtest point-in-time bảng cơ hội

Sinh tự động bởi `scripts/run_backtest_opportunity.py` lúc 2026-10-13T07:20:43+07:00 (commit `ca2873f`). Thiết kế và các quyết định chốt trước: [`docs/phase2/backtest-design.md`](phase2/backtest-design.md).

## Kết luận

**Không có bằng chứng lợi thế có ý nghĩa thống kê (không đạt: DSR ≥ 0,95; Sharpe OOS vượt cả ba benchmark; Phí × 2 vẫn vượt VN-Index (CAGR)).**

- ❌ DSR ≥ 0,95
- ✅ IC tổng hợp 3 tháng > 0 và t Newey–West ≥ 2
- ❌ Sharpe OOS vượt cả ba benchmark
- ❌ Phí × 2 vẫn vượt VN-Index (CAGR)

> **Kết quả thăm dò, chưa đạt chuẩn point-in-time nghiêm ngặt: BCTC năm và quý là bản mới nhất của nguồn (có thể đã điều chỉnh hồi tố). Bộ lọc ngày công bố chỉ chặn việc dùng kỳ chưa công bố, không khôi phục được con số nhà đầu tư thấy tại thời điểm đó. Không dùng làm kết quả đầu tư đã kiểm chứng.**

Out-of-sample 2020-09-29 → 2026-09-28; 98 ngày tín hiệu cuối tháng; 392 mã từng đủ điều kiện; vốn 1 tỷ đồng; phí hai chiều 0.25%, thuế bán 0.1%, T+2, lệnh ≤ 10% GTGD TB20. DSR với 4 lần thử.

## Chiến lược so với benchmark (OOS)

| | CAGR | Sharpe | Sụt giảm tối đa | Tỷ lệ tháng dương | Tỷ lệ tháng thắng VN-Index | Vòng quay (lần/năm) | PSR(0) | DSR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Chiến lược (walk-forward OOS) | 11.8% | 0.57 | -57.8% | 54.8% | 52.1% | 3.34 | 0.91 | 0.75 |
| VN-Index (chỉ số giá) | 12.1% | 0.68 | -40.3% | 65.8% | — | — | 0.95 | — |
| Cân bằng toàn universe đủ điều kiện | 8.2% | 0.47 | -57.0% | 52.1% | 43.8% | 1.53 | 0.87 | — |
| Top 20 vốn hoá | 12.1% | 0.70 | -36.2% | 56.2% | 56.2% | 0.88 | 0.95 | — |

VN-Index là chỉ số **giá** (không gồm cổ tức); các danh mục dùng giá đã điều chỉnh nên đã gồm cổ tức.

## Năng lực xếp hạng (IC Spearman theo tháng)

| Nhóm | Kỳ hạn | IC TB | ICIR | t thường | t Newey–West | Tháng IC>0 | Số tháng |
|---|---:|---:|---:|---:|---:|---:|---:|
| tổng hợp | 1T | 0.02 | 0.19 | 1.90 | 1.91 | 62.5% | 96 |
| tổng hợp | 3T | 0.04 | 0.33 | 3.23 | 2.33 | 64.9% | 94 |
| tổng hợp | 6T | 0.07 | 0.53 | 5.04 | 2.61 | 67.0% | 91 |
| valuation | 1T | 0.02 | 0.15 | 1.45 | 1.46 | 55.2% | 96 |
| valuation | 3T | 0.03 | 0.24 | 2.35 | 1.74 | 53.2% | 94 |
| valuation | 6T | 0.06 | 0.41 | 3.94 | 2.43 | 63.7% | 91 |
| quality | 1T | 0.01 | 0.10 | 0.99 | 0.99 | 50.0% | 96 |
| quality | 3T | 0.03 | 0.18 | 1.78 | 1.22 | 53.2% | 94 |
| quality | 6T | 0.04 | 0.23 | 2.18 | 1.09 | 56.0% | 91 |
| sector | 1T | -0.01 | -0.05 | -0.47 | -0.48 | 49.0% | 96 |
| sector | 3T | -0.01 | -0.08 | -0.75 | -0.54 | 45.7% | 94 |
| sector | 6T | 0.00 | 0.02 | 0.23 | 0.12 | 53.8% | 91 |
| growth | 1T | 0.00 | 0.04 | 0.36 | 0.36 | 54.2% | 96 |
| growth | 3T | 0.02 | 0.18 | 1.72 | 1.24 | 63.8% | 94 |
| growth | 6T | 0.04 | 0.33 | 3.12 | 1.70 | 63.7% | 91 |
| technical | 1T | 0.01 | 0.10 | 0.95 | 0.96 | 53.1% | 96 |
| technical | 3T | 0.01 | 0.09 | 0.86 | 0.85 | 58.5% | 94 |
| technical | 6T | 0.01 | 0.10 | 0.94 | 0.91 | 54.9% | 91 |

## Độ nhạy (cùng lựa chọn walk-forward, không chọn lại)

| | CAGR | Sharpe | Sụt giảm tối đa | PSR(0) |
|---|---:|---:|---:|---:|
| Gốc | 11.8% | 0.57 | -57.8% | 0.91 |
| Phí × 2 | 10.9% | 0.53 | -58.3% | 0.90 |
| Trễ thêm 1 phiên | 13.7% | 0.64 | -55.6% | 0.94 |
| Bỏ 40 mã lợi suất cao nhất (10%) | 8.0% | 0.43 | -59.8% | 0.85 |

## Bốn cấu hình trên cả giai đoạn OOS (minh bạch, không dùng để chọn)

| | CAGR | Sharpe | Sụt giảm tối đa | Vòng quay (lần/năm) |
|---|---:|---:|---:|---:|
| Top 10, tháng | 1.5% | 0.19 | -61.0% | 6.56 |
| Top 10, quý | 8.2% | 0.44 | -59.8% | 2.80 |
| Top 20, tháng | 8.2% | 0.45 | -59.8% | 5.08 |
| Top 20, quý | 14.2% | 0.66 | -59.1% | 2.18 |

## Các lát walk-forward

| Train từ | Test | Cấu hình chọn | Sharpe train | Lợi suất test |
|---|---|---|---:|---:|
| 09/2018 | 09/2020–03/2021 | Top 20, quý | 0.31 | 53.4% |
| 03/2019 | 03/2021–09/2021 | Top 20, quý | 1.94 | 32.3% |
| 09/2019 | 09/2021–03/2022 | Top 20, quý | 2.32 | 20.4% |
| 03/2020 | 03/2022–09/2022 | Top 20, quý | 2.68 | -27.9% |
| 09/2020 | 09/2022–03/2023 | Top 20, quý | 1.21 | -16.2% |
| 03/2021 | 03/2023–09/2023 | Top 20, quý | 0.08 | 19.4% |
| 09/2021 | 09/2023–03/2024 | Top 20, quý | -0.09 | 21.1% |
| 03/2022 | 03/2024–09/2024 | Top 20, quý | -0.02 | -2.6% |
| 09/2022 | 09/2024–03/2025 | Top 20, quý | 0.53 | -2.3% |
| 03/2023 | 03/2025–09/2025 | Top 10, quý | 1.05 | 23.6% |
| 09/2023 | 09/2025–03/2026 | Top 10, quý | 0.98 | -5.4% |
| 03/2024 | 03/2026–09/2026 | Top 10, quý | 0.49 | -18.3% |

## Giới hạn

- Universe là mã **đang niêm yết hôm nay** (survivorship) → kết quả là cận trên.
- Điểm backtest dùng 5/7 nhóm: vĩ mô và tin tức không có lịch sử theo ngày công bố.
- Số CP, ngành ICB, sàn và lãi suất phi rủi ro lấy giá trị hiện tại; BCTC năm dùng quy tắc 01/04 năm sau, BCTC quý dùng ngày công bố thật của VCI; số liệu có thể đã điều chỉnh hồi tố.
- UPCOM gần như không có BCTC năm trong nguồn arminer nên ít khi đủ điều kiện.
- Kho giá Vietcap có nến giá = 0 (chủ yếu UPCOM, 2015–2018) đã bị bỏ, coi như phiên không giao dịch; các biến động bất thường khác của giá điều chỉnh được giữ nguyên.
