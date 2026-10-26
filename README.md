# AI Agent – Context Compaction & Code Mode

Bài thực hành **Challenge B** từ chủ đề *Memory, Context Engineering & Prompt Caching*, triển khai bằng **Python**.

- **B1 – Compaction:** Nén lịch sử làm việc dài thành *structured checkpoint*, sau đó tiếp tục nhiệm vụ mà vẫn giữ các thông tin quan trọng.
- **B2 – Code Mode:** Đọc, xử lý nhiều file log trong Python và chỉ gửi kết quả tổng hợp tới LLM.
- **B2 Dynamic:** LLM sinh chương trình Python giới hạn; hệ thống kiểm tra AST, thực thi qua restricted interpreter và đối chiếu kết quả.

## 1. Yêu cầu

- Windows, **VS Code**, Python (khuyến nghị **3.11–3.12**; các lần thử nghiệm cũng đã chạy trên Python 3.14).
- `pip`, `venv` và kết nối tới **API LLM tương thích OpenAI**.
- Các file chính: `main.py`, `b2_code_mode.py`, `b2_dynamic_code_mode.py`, `requirements.txt` và thư mục `tests/`.

## 2. Cài đặt

Mở thư mục project trong VS Code, sau đó chạy trong **PowerShell**:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Chọn interpreter `.venv` trong VS Code nếu cần. Nếu PowerShell chặn lệnh kích hoạt, chuyển terminal sang **Command Prompt** và chạy `.venv\Scripts\activate.bat`.

Tạo cấu hình môi trường:

```powershell
Copy-Item .env.example .env
```

**Chỉnh lại toàn bộ các giá trị kết nối trong `.env`** theo API bạn được cấp. Ví dụ với OpenAI API chính thức:

```dotenv
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini
OPENAI_API_KEY=YOUR_API_KEY
LLM_API_MODE=chat
COMPACT_THRESHOLD_TOKENS=2500
```

> Cấu hình trên chỉ là **ví dụ cài đặt**, không phải cấu hình đã dùng để tạo số liệu trong báo cáo. Có thể sử dụng endpoint và model tương thích OpenAI khác. **Không commit file `.env` hoặc API key lên GitHub.**

Kiểm tra kết nối model:

```powershell
python main.py ping
```

## 3. Chạy Challenge B1 – Compaction

```powershell
python main.py preview   # Kiểm tra ngưỡng kích hoạt (không gọi LLM)
python main.py run       # Tạo checkpoint từ lịch sử dài
python main.py resume    # Tiếp tục từ context đã nén
python main.py verify    # Kiểm tra kết quả
```

**Đạt yêu cầu khi:** hiện `B1 RESULT: PASS`; Agent vẫn nhớ lỗi đang xử lý, cách đã thử thất bại và bước tiếp theo (`inspect_locking`). Kết quả được lưu trong `data/`.

## 4. Chạy Challenge B2 – Code Mode

```powershell
python b2_code_mode.py generate  # Sinh log mẫu
python b2_code_mode.py analyze   # Tổng hợp log tại máy, không gọi LLM
python b2_code_mode.py ask       # Cho LLM trả lời dựa trên findings
python b2_code_mode.py verify
```

**Đạt yêu cầu khi:** hiện `B2 RESULT: PASS`; chương trình xử lý đủ 100 file / 12.000 dòng và không đưa log thô vào input LLM. Kết quả được lưu trong `b2_data/`.

## 5. Chạy B2 Dynamic – LLM tự sinh chương trình

**Chạy bước `generate` của B2 ở mục 4 trước**, để tạo dữ liệu log.

```powershell
python b2_dynamic_code_mode.py plan     # LLM sinh chương trình, kiểm tra AST
python b2_dynamic_code_mode.py execute  # Runtime diễn giải chương trình hợp lệ
python b2_dynamic_code_mode.py ask      # LLM trả lời từ findings
python b2_dynamic_code_mode.py verify   # Đối chiếu kết quả
```

**Đạt yêu cầu khi:** hiện `B2 DYNAMIC RESULT: PASS`. File chương trình và kết quả nằm trong `b2_dynamic_data/`.

> **Không chạy trực tiếp** `b2_dynamic_data/program.txt` bằng Python. Chỉ thực thi qua lệnh `execute` để dùng cơ chế kiểm tra và giới hạn quyền của project.

## 6. Chạy Unit Test

```powershell
python -m unittest discover -s tests -v
```

Kết quả ghi nhận trên Windows: **18 test được phát hiện, 17 PASS, 1 SKIPPED** (kiểm thử symbolic link bị bỏ qua do giới hạn môi trường). Các unit test dùng dữ liệu/LLM giả lập; những bước `run`, `resume`, `ask`, `plan` ở trên cần API LLM hoạt động thật.

## 7. Kết quả thực nghiệm tham khảo

| Nội dung | Kết quả ghi nhận |
|---|---:|
| B1: context trước → sau nén | 13.243 → 345 tokens (**−97,4%**) |
| B2: raw log → prompt tổng hợp | 615.422 → 343 tokens (**−99,94%**) |
| B2 Dynamic: raw log → tổng input hai lần gọi LLM | 615.424 → 712 tokens (**−99,88%**) |
| Kết quả kiểm tra | **B1 PASS · B2 PASS · B2 Dynamic PASS** |

Các số token là **ước tính**, không phải thống kê chi phí API thực tế; kết quả có thể khác khi thay model hoặc bộ dữ liệu.

## 8. Tài liệu và bằng chứng

- `docs/BAO_CAO_CHALLENGE_B1_B2_AI_AGENT.md`: báo cáo kỹ thuật chi tiết.
- `evidence/`: checkpoint, metrics, findings, program và audit mẫu phục vụ đối chiếu (nếu đã bổ sung).
- `data/`, `b2_data/`, `b2_dynamic_data/`: file sinh trong khi chạy; không cần đẩy toàn bộ lên GitHub.

**Giới hạn:** Đây là bài thực hành với log giả lập. B1 và B2 vẫn là các module độc lập; restricted interpreter không thay thế sandbox ở cấp hệ điều hành nếu muốn triển khai với mã tùy ý hoặc dữ liệu nhạy cảm.
