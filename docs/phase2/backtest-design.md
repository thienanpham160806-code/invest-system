# Thiết kế backtest point-in-time cho bảng cơ hội (`/co-hoi`)

Trạng thái: **thiết kế, chốt trước khi chạy**. Tham số dưới đây được cố định tại commit tạo file này; mọi thay đổi
sau khi đã xem kết quả out-of-sample phải ghi ở mục 10 kèm lý do, và kết quả cũ vẫn được báo cáo.

Câu hỏi cần trả lời: *nếu mua theo bảng cơ hội đúng như cách hệ thống xếp hạng hôm nay, chỉ với thông tin có tại
thời điểm đó, thì có hơn VN-Index và các danh mục đơn giản sau phí, thuế, T+2 và giới hạn thanh khoản không — và
khác biệt đó có ý nghĩa thống kê không?*

## 1. Tái sử dụng

Engine của bot (`Kumo_VN_bot/src/bot_phan_tich/backtest/`) được port vào `src/invest_system/backtest/`:

| File bot | Dùng lại | Thay đổi |
|---|---|---|
| `metrics.py` | nguyên vẹn: CAGR, Sharpe, Sortino, max DD, turnover, `sharpe_moments`, PSR, `expected_max_sharpe`, DSR | thêm `monthly_win_rate` |
| `ic.py` | nguyên vẹn: `daily_rank_ic` (Spearman theo mặt cắt), `newey_west_tstat`, `summarise_ic` | lợi suất kỳ hạn theo **tháng** (21/63/126 phiên) |
| `engine.py` | `PreparedPrices`/`prepare_prices` (lịch chung + mảng giá), quy tắc T+2 theo phiên, kẹt sàn, khớp giá mở cửa | thêm `run_rebalance()`: danh mục tỷ trọng mục tiêu thay cho lệnh stop/target đơn lẻ |
| `walk_forward.py` | khung cuộn train/test, `universe_fn(as_of)`, `WalkForwardResult.sharpe_report()` (PSR/DSR với `n_trials`) | lưới tham số mới (mục 7), train 24 / test 6 tháng |
| `risk/constraints.py` | `is_settled`, `floor_locked`, `settlement_days` | đọc biên độ từ `price_band` trong `config/settings.yaml` |

Mọi chi phí đọc từ `config/settings.yaml: costs` (đã có `fee_rate: 0.0025`, `sell_tax_rate: 0.001`, `settlement_days: 2`).

## 2. Nguồn giá

- **Cổ phiếu**: `webdata/snapshot/ohlcv.parquet` (Vietcap gap-chart), 1.521 mã, từ 02/10/2017. Giá **đã điều chỉnh**
  cổ tức tiền/cổ phiếu và chia tách (xem `docs/data-sources.md` §5), nên lợi suất giữa hai phiên đã gồm cổ tức.
  Backfill trong Đợt 2 ghi vào `DATA_DIR=./data-phase2`, không ghi đè snapshot web.
- **VN-Index**: snapshot hiện chỉ có 1 năm → backfill ≥ 6 năm (Vietcap gap-chart `VNINDEX`). VN-Index là chỉ số giá,
  **không gồm cổ tức** → benchmark này thấp hơn tổng lợi suất thực khoảng 1–2%/năm; ghi rõ trong báo cáo và dùng thêm
  benchmark danh mục cân bằng (mục 6) vốn được tính trên giá điều chỉnh.
- **Hệ quả của giá điều chỉnh**:
  - GTGD = `close_điều_chỉnh × volume` thấp hơn GTGD thật ở quá khứ với mã chia cổ tức nhiều → lọc thanh khoản
    **khắt khe hơn** thực tế (thiên về loại bớt mã, không thổi phồng kết quả).
  - Kẹt sàn: so `close/close_trước − 1` với biên độ sàn; tỷ lệ này giữ nguyên qua điều chỉnh, trừ đúng phiên GDKHQ.
  - Không dùng giá tuyệt đối (vd "giá < 10.000 đ") làm điều kiện lọc.

## 3. Quy tắc công bố BCTC (point-in-time)

Module `src/invest_system/backtest/pit.py`, hàm `available_financials(symbol, as_of)` trả **chỉ các kỳ đã công bố
tại `as_of`**. Ngày có thể dùng một kỳ (`available_from`):

| Kỳ | Có ngày công bố thật | Không có ngày công bố thật |
|---|---|---|
| Năm (FY, kiểm toán) | ngày công bố + 1 ngày | **01/04 năm sau** |
| Quý 1, 2, 3 | ngày công bố + 1 ngày | ngày cuối quý **+ 45 ngày** |
| Quý 4 | ngày công bố + 1 ngày | ngày cuối quý **+ 60 ngày** |

- Cơ sở: Thông tư 96/2020/TT-BTC — BCTC năm kiểm toán trong 90 ngày, BCTC quý trong 20 ngày (30 ngày với công ty mẹ
  lập hợp nhất). Các mức +45/+60 ngày và 01/04 là **đệm bảo thủ** cho DN nộp muộn/xin gia hạn.
- "+1 ngày" với ngày công bố thật: tin đăng sau giờ giao dịch chỉ dùng được từ phiên hôm sau. Tín hiệu tính ở giá
  đóng cửa phiên `t` chỉ dùng kỳ có `available_from <= t`.
- Chuẩn ngày cuối năm tài chính là 31/12. DN có năm tài chính khác (vd kết thúc 30/6) hiện bị coi như 31/12 → dữ liệu
  được dùng **muộn hơn** thực tế (sai về phía an toàn). Ghi trong báo cáo cột `fiscal_year_end_assumed`.
- **Restatement**: arminer/vnstock lưu bản số liệu cuối cùng (có thể đã điều chỉnh hồi tố), không có các "vintage".
  Đây là nguồn nhìn trước còn sót lại; không loại bỏ được nếu không có kho phiên bản. Ghi là giới hạn đã biết.
- Test (`tests/test_pit.py`) chứng minh: tại 31/03/Y+1 không thấy FY Y; tại 01/04/Y+1 thấy; Q3 chỉ thấy sau
  ngày 14/11; Q4 chỉ thấy sau ngày 01/03; ngày công bố thật sớm hơn quy tắc thì dùng ngày thật.

TTM trong backtest dùng `analysis/ttm.py` trên các quý **đã công bố tại t**: đủ 4 quý liên tiếp → TTM; thiếu → FY gần
nhất đã công bố.

## 4. Universe theo thời điểm

Mã `s` thuộc universe tại phiên `t` khi **tất cả** điều kiện sau đúng với dữ liệu `<= t`:

1. Có ≥ 120 phiên giao dịch trước `t` (đủ cho chỉ báo kỹ thuật và GTGD TB20).
2. GTGD TB 20 phiên ≥ **5 tỷ đồng** (cùng ngưỡng `/co-hoi`).
3. Có BCTC đã công bố tại `t` (mục 3).
4. Có giao dịch ở phiên `t` (không tạm ngưng).

Thiên lệch còn lại, ghi rõ trong báo cáo:

- **Survivorship**: kho giá chỉ gồm mã **đang niêm yết hôm nay** → mã đã huỷ niêm yết (thường là mã kém) vắng mặt,
  làm kết quả **lạc quan hơn** thực tế. Đợt 2 thử lấy danh sách mã huỷ niêm yết từ VCI; nếu không lấy được thì kết luận
  coi kết quả là **cận trên**.
- **Sàn niêm yết**: dùng sàn hiện tại cho cả lịch sử (mã chuyển sàn bị gán sai biên độ). Ảnh hưởng nhỏ.
- **Ngành ICB**: dùng phân ngành hiện tại.

## 5. Nhóm điểm: có / không có lịch sử

Điểm tổng hợp hiện tại (`analysis/composite.py`) gồm 7 nhóm. Chỉ nhóm tái tạo được point-in-time mới được dùng;
`combine()` đã chuẩn hoá lại trọng số trên các nhóm có giá trị.

| Nhóm | Trọng số live | Tái tạo tại t? | Cách tính trong backtest |
|---|---:|---|---|
| Định giá (upside) | 25% | **Có** (gần đúng) | P/E, P/B tương đối với bội số ngành tính chéo tại `t` từ BCTC đã công bố + giá `t`; DCF dùng tham số `settings.yaml` cố định |
| Chất lượng | 20% | **Có** | `quality_score` trên tỷ số từ BCTC đã công bố |
| Ngành | 15% | **Có** | hiệu suất ngành 3T so VN-Index và trung vị ngành tại `t` |
| Tăng trưởng | 10% | **Có** | CAGR doanh thu/LNST trên các năm đã công bố |
| Kỹ thuật | 10% | **Có** | `technical_score` trên giá `<= t` |
| Vĩ mô – ngành | 10% | **Không** | `config/macro_vn.csv` chỉ có số mới nhất, không có lịch sử theo ngày công bố |
| Tin tức | 10% | **Không** | không có kho tin lịch sử |

→ Điểm backtest dùng 5/7 nhóm (80% trọng số live, chuẩn hoá lại). **Kết quả backtest không kiểm định phần vĩ mô và
tin tức**; báo cáo ghi rõ. Phần vĩ mô quốc tế (FRED, có lịch sử) có thể thêm như phân tích phụ, không đưa vào chiến
lược chính để không tăng số lần thử.

Điều kiện vào danh mục như `/co-hoi` (`docs/opportunity-audit.md`): khuyến nghị MUA, có BCTC, không có kiểm tra FAIL,
độ tin cậy định giá trung bình/cao, GTGD TB20 ≥ 5 tỷ, `0 < upside <= 150%`. Xếp theo điểm tổng hợp giảm dần.

## 6. Chiến lược, khớp lệnh, chi phí

**Chiến lược chính** (cố định):

- Top **N ∈ {10, 20}** theo điểm, tỷ trọng bằng nhau, **tối đa 35% mỗi ngành ICB cấp 1** (vượt thì bỏ mã điểm thấp
  nhất của ngành đó, lấy mã kế tiếp).
- Rebalance **tháng** (phiên cuối tháng) và **quý** (phiên cuối tháng 3/6/9/12).
- Ít hơn N mã đủ điều kiện → giữ tiền mặt phần còn lại (lãi 0%, bảo thủ).

**Khớp lệnh**:

- Tín hiệu tại **giá đóng cửa phiên t**, khớp tại **giá mở cửa phiên t+1**.
- **T+2 theo phiên**: cổ phiếu mua phiên `t+1` chỉ bán được từ phiên `t+3`; tiền bán chỉ dùng mua được sau khi về
  (`is_settled`). Với rebalance tháng/quý, ràng buộc này hiếm khi chặn lệnh nhưng vẫn được áp.
- **Không bán khi kẹt sàn** (đóng cửa = giá sàn và `low` = giá sàn): lệnh bán dời sang phiên đầu tiên hết kẹt, khớp
  giá mở cửa.
- **Thanh khoản**: giá trị mỗi lệnh ≤ **10% GTGD TB 20 phiên** (tính đến `t`); phần không khớp giữ tiền mặt.
  Vốn ban đầu **1 tỷ đồng**. Khối lượng làm tròn lô 100 cổ phiếu.
- Mã ngừng giao dịch: định giá ở giá đóng cửa gần nhất, bán khi giao dịch lại.

**Chi phí**: phí **0,25% hai chiều** = `costs.fee_rate: 0.0025` sẵn có ("phí hai chiều"), engine trừ `fee/2`
= 0,125% mỗi lần mua và mỗi lần bán. Cách hiểu chặt hơn (0,25% *mỗi* chiều) chính là kịch bản độ nhạy **phí × 2**
ở mục 8, nên cả hai cách hiểu đều được báo cáo. Thuế **0,1%** giá trị bán.

**Benchmark** (cùng giai đoạn, cùng lịch rebalance, cùng chi phí trừ VN-Index):

1. VN-Index mua và nắm giữ (chỉ số giá).
2. Cân bằng toàn bộ universe đủ điều kiện mục 4 (không lọc điểm) — cho biết điểm số có thêm gì so với "mua mọi thứ đủ
   thanh khoản".
3. Top N theo vốn hoá (vốn hoá = giá điều chỉnh × số CP hiện tại; xấp xỉ, ghi rõ).

## 7. Walk-forward

- Cửa sổ **train 24 tháng / test 6 tháng**, bước 6 tháng (khung `walk_forward.py` của bot).
- Lưới chọn trên train: **N ∈ {10, 20} × rebalance ∈ {tháng, quý}** = **4 lần thử**. Chọn theo Sharpe train, áp
  nguyên lên test. Đường vốn out-of-sample ghép từ các lát test là **con số duy nhất** báo cáo là kết quả chiến lược.
- Các tham số khác (trọng số điểm, ngưỡng MUA, 35%/ngành, phí, ngưỡng thanh khoản) **không tối ưu** — lấy nguyên giá
  trị live.
- Universe mỗi cửa sổ: `universe_fn(as_of = ngày trước khi cửa sổ bắt đầu)`.
- Giai đoạn: giá từ 10/2017; cần ~12 tháng lịch sử cho điểm kỹ thuật/tăng trưởng → train đầu tiên từ 10/2018,
  test đầu tiên từ 10/2020, tới hết dữ liệu (≈ 6 năm out-of-sample).
- Ngoài walk-forward, chạy cả 4 cấu hình trên toàn giai đoạn để minh bạch (không dùng để chọn).

## 8. Chỉ số đánh giá

**Danh mục** (`metrics.py`, đã trừ phí/thuế): CAGR, Sharpe (rf = 0, theo ngày × √252), max drawdown, tỷ lệ tháng
thắng (lợi suất tháng > 0 và > VN-Index), turnover một chiều/năm, **PSR(0)** trên đường vốn OOS, **DSR** với
`n_trials = 4` và phương sai Sharpe giữa các lần thử trên train.

**Năng lực xếp hạng** (`ic.py`):

- IC Spearman tại mỗi ngày rebalance tháng giữa điểm tại `t` và lợi suất mở cửa `t+1` → mở cửa `t+1+h`,
  **h = 1, 3, 6 tháng** (21, 63, 126 phiên), trên universe đủ điều kiện.
- Tính cho điểm tổng hợp **và từng nhóm** (định giá, chất lượng, ngành, tăng trưởng, kỹ thuật).
- Báo IC trung bình, ICIR, t-stat thường và **t-stat Newey–West** (độ trễ = số tháng chồng lấn: 0, 2, 5), tỷ lệ tháng
  IC > 0. Mặt cắt < 20 mã bị bỏ.

**Độ nhạy** (chạy trên cấu hình được walk-forward chọn, không dùng để chọn lại):

1. Phí × 2.
2. Trễ thêm 1 phiên (khớp mở cửa `t+2`).
3. Bỏ 10% mã có tổng lợi suất cao nhất cả giai đoạn khỏi universe (kiểm tra kết quả có dựa vào vài mã "trúng" không).

## 9. Tiêu chí kết luận (chốt trước)

Chỉ kết luận **"có lợi thế"** khi đồng thời:

- DSR ≥ 0,95 trên đường vốn OOS, **và**
- IC trung bình của điểm tổng hợp (h = 3 tháng) > 0 với t-stat Newey–West ≥ 2, **và**
- vượt cả ba benchmark về Sharpe OOS, và vẫn vượt VN-Index khi phí × 2.

Thiếu bất kỳ điều kiện nào → báo cáo **"không có bằng chứng lợi thế có ý nghĩa thống kê"**, kèm số liệu đầy đủ.
Không chỉnh tham số sau khi xem kết quả OOS; nếu buộc phải sửa lỗi code thì chạy lại, giữ cả kết quả trước/sau ở mục 10.

## 10. Nhật ký thay đổi sau khi chạy

(trống — chưa chạy)

## 11. Đầu ra

- `outputs/backtest_opportunity/`: `equity_oos.csv`, `slices.csv`, `trials.csv`, `benchmarks.csv`, `ic.csv`,
  `sensitivity.csv`, `summary.json` (kèm commit sha, ngày dữ liệu, tham số).
- `docs/backtest-opportunity.md`: kết quả + kết luận theo mục 9.
- Trang `/backtest`: đọc `summary.json` + CSV, hiển thị đường vốn so benchmark, bảng chỉ số, IC theo nhóm.
