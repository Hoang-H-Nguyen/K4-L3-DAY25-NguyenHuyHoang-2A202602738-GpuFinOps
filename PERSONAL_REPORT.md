# Báo cáo cá nhân — GPU FinOps Optimization

**Họ và tên:** Nguyễn Huy Hoàng  
**MSSV:** 2A202602738  
**Bài thực hành:** Lab 25 — Tối ưu hóa chi phí GPU

## 1. Baseline và Optimized

Ở trạng thái baseline, tổng chi phí GPU ước tính của NimbusAI là **27.133 USD/tháng**. Sau khi áp dụng các biện pháp tối ưu, chi phí còn **13.971 USD/tháng**. Tổng số tiền có thể tiết kiệm là **13.162 USD/tháng**, tương đương khoảng **49%** baseline.

Riêng inference, hệ thống phục vụ 7.533.027 token/ngày. Baseline giả định tất cả request đều chạy trên model lớn, không dùng cache và không dùng batch, tạo ra chi phí **48,87 USD/ngày**, tương đương **6,488 USD/1 triệu token**. Sau khi áp dụng model cascade, prompt caching và batch API, chi phí giảm còn **8,48 USD/ngày**, tương đương **1,126 USD/1 triệu token**. Như vậy, nhóm tối ưu inference tiết kiệm **82,6%** trong khi vẫn phục vụ cùng lượng token.

Kết quả này cho thấy chi phí trên mỗi GPU-giờ chưa đủ để đánh giá hiệu quả hệ thống. Chỉ số phù hợp hơn cho inference là `$/1M-token`, vì nó gắn chi phí với lượng công việc thực tế được phục vụ.

## 2. Phân tích từng đòn bẩy

Bốn nhóm tiết kiệm chính trong báo cáo gồm:

| Đòn bẩy | Tiết kiệm mỗi tháng |
|---|---:|
| Purchasing: spot và reserved | 10.040 USD |
| Inference: cascade, cache và batch | 1.212 USD |
| Right-sizing dựa trên MBU | 1.310 USD |
| Tắt GPU idle | 600 USD |

**Purchasing đóng góp nhiều nhất**, chiếm khoảng 76% tổng số tiền tiết kiệm. Nguyên nhân là các workload training sử dụng nhiều GPU trong nhiều giờ. Việc chuyển job có thể gián đoạn sang spot tạo ra chênh lệch giá lớn trên toàn bộ số GPU-giờ. Các workload inference chạy ổn định từ 18 đến 24 giờ/ngày được chuyển sang reserved vì duty cycle vượt điểm hòa vốn 55%.

Trong nhóm inference, model cascade là biện pháp hiệu quả nhất, tiết kiệm **37,40 USD/ngày**. Prompt caching đóng góp **1,20 USD/ngày**, còn batch đóng góp **1,79 USD/ngày**. Cascade tạo ra mức tiết kiệm lớn vì phần lớn request không cần khả năng của model lớn và có thể được xử lý bằng model nhỏ với đơn giá thấp hơn. Cache chỉ tác động lên phần input token được sử dụng lại, còn batch chỉ phù hợp với request chấp nhận độ trễ.

## 3. GPU-Util Lie

Hai GPU bị phát hiện có GPU-Util cao nhưng MFU thấp là `gpu-h100-4` và `gpu-a10g-1`. Trường hợp rõ nhất là `gpu-h100-4`: GPU-Util đạt **98,2%**, nhưng MFU chỉ đạt **19,4%**. Điều này có nghĩa GPU gần như luôn có kernel hoạt động, nhưng chỉ khai thác được khoảng một phần năm năng lực tính toán lý thuyết.

GPU-Util chỉ đo tỷ lệ thời gian GPU có hoạt động. Nó không cho biết tensor cores thực hiện được bao nhiêu phép tính hữu ích. Memory stall, kernel nhỏ, kernel launch overhead hoặc chờ I/O có thể giữ GPU ở trạng thái bận trong khi throughput thực tế vẫn thấp. Do nhà cung cấp tính phí toàn bộ GPU-giờ, việc chỉ theo dõi GPU-Util có thể che giấu lãng phí tài chính.

Phân tích MBU và yêu cầu tài nguyên cho thấy bốn GPU có thể được xem xét right-size. Chuyển hai H100 phù hợp xuống A100 và hai A10G xuống L4 tạo ra tiềm năng tiết kiệm khoảng **1.310 USD/tháng**. Ngoài ra, các khoảng thời gian GPU có utilization dưới 10% gây lãng phí khoảng **600 USD/tháng**, tương đương **2,2%** tổng baseline. Các đề xuất right-size vẫn cần benchmark latency, throughput và kiểm tra bộ nhớ trước khi áp dụng trong production.

## 4. Các phần mở rộng đã thực hiện

### Extension 1: Right-sizing dựa trên MBU

Phần mở rộng này đánh giá các GPU có MBU dưới 35%. GPU thay thế phải có giá thấp hơn, dung lượng HBM ít nhất bằng GPU hiện tại và peak bandwidth đủ đáp ứng băng thông quan sát được của workload. Cách làm này tránh chọn GPU chỉ dựa trên giá mỗi giờ, vì GPU rẻ nhất có thể không đủ bộ nhớ hoặc tạo ra bottleneck băng thông.

Kết quả xác định bốn ứng viên: `gpu-h100-4` và `gpu-h100-5` có thể xem xét chuyển từ H100 sang A100; `gpu-a10g-0` và `gpu-a10g-1` có thể xem xét chuyển từ A10G sang L4. Tổng tiềm năng tiết kiệm là **1.310 USD/tháng**. Insight quan trọng nhất là right-sizing cần xét cả khả năng chứa model và nhu cầu băng thông, không chỉ `$/GPU-hour`.

### Extension 2: Ngân sách reasoning

Traffic reasoning chỉ chiếm **8,4% số request**, nhưng chiếm **16,5% chi phí inference đã tối ưu** và khoảng **94% điện năng inference ước tính**. Nguyên nhân là mô hình mô phỏng reasoning với mức tiêu thụ điện cao gấp 80 lần truy vấn thông thường do quá trình sinh và xử lý dài hơn.

Policy được đề xuất là chỉ bật reasoning cho task được phân loại là phức tạp hoặc được escalation rõ ràng, đồng thời giới hạn reasoning ở mức 5% traffic. Với dataset hiện tại, policy này chuyển 81 request/ngày sang model nhỏ, tiết kiệm khoảng **1,20 USD/ngày** và **14.314 Wh/ngày**. Insight quan trọng nhất là reasoning có tỷ trọng request nhỏ nhưng có thể chi phối phần lớn điện năng, vì vậy nó cần được quản lý như một ngân sách riêng và phải theo dõi chất lượng sau khi áp dụng giới hạn.

## 5. Khuyến nghị cho NimbusAI

Ba hành động đầu tiên nếu tôi là FinOps Lead tại NimbusAI là:

1. **Tối ưu purchasing trước.** Chuyển các training job có checkpoint và `interruptible=1` sang spot. Dùng reserved cho workload ổn định có duty cycle trên 55%. Đây là hành động có tác động tài chính lớn nhất, khoảng **10.040 USD/tháng**.

2. **Triển khai inference routing có kiểm soát.** Dùng model cascade làm mặc định, sau đó áp dụng prompt cache cho nội dung được tái sử dụng và batch cho workload không nhạy với latency. Reasoning chỉ được bật khi task đủ phức tạp và cần có budget cap cùng theo dõi chất lượng.

3. **Tự động hóa quản trị công suất.** Thiết lập cảnh báo theo MFU, MBU và idle time; tự động tắt GPU sau khi job hoàn thành; benchmark các ứng viên right-size trước khi chuyển production. Việc này giúp thu hồi **600 USD/tháng** từ idle và có thể giảm thêm **1.310 USD/tháng** từ right-sizing.

Về tính bền vững, `europe-north1` có cường độ carbon thấp nhất trong dữ liệu, còn `us-east-wa` có giá điện thấp nhất. NimbusAI nên kết hợp chi phí, carbon, latency và yêu cầu data residency khi chọn vùng triển khai thay vì chỉ tối ưu một chỉ số.

## Kết luận

Lab cho thấy NimbusAI có thể giảm khoảng **49% chi phí GPU hàng tháng** bằng cách kết hợp purchasing, tối ưu inference, right-sizing và tự động tắt tài nguyên idle. Hiệu quả lớn nhất đến từ việc ghép đúng loại hình mua GPU với đặc điểm workload. Đồng thời, MFU, MBU và `$/1M-token` cung cấp góc nhìn chính xác hơn GPU-Util hoặc giá GPU theo giờ khi đánh giá hiệu quả thực tế.
