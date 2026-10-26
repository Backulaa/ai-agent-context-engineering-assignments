# BÁO CÁO THỰC HÀNH CHALLENGE B — CONTEXT MANAGEMENT & CODE MODE

**Chủ đề:** Xây dựng AI Agent Harness bằng Python với Context Compaction và Code Mode  
**Căn cứ:** Bộ slide *Memory, Context Engineering & Prompt Caching*, MSc. Ngô Ngọc Đăng Khoa — trọng tâm trang 17–34, đặc biệt Challenge B tại trang 32–33.  
**Ngày tổng hợp báo cáo:** 27/10/2026  
**Môi trường thực hành:** Windows, Visual Studio Code, PowerShell, Python virtual environment (`.venv`) và kết nối LLM qua API tương thích OpenAI.  
**Phạm vi:** Chỉ Python + AI/Agent; không có frontend, backend, database hoặc Docker.  
**Trạng thái:** B1 **PASS**; B2 cơ bản **PASS**; B2 Dynamic Code Mode **PASS** trên kịch bản mô phỏng và các tiêu chí kiểm thử hiện có.

> **Quy ước bằng chứng:** Các số liệu thực nghiệm và kết quả tương tác với LLM được ghi nhận từ output terminal của người thực hành. Bên biên soạn không truy cập trực tiếp môi trường API của người thực hành. Bộ mã tích hợp đã được kiểm tra lại với **21 unit test offline: OK** trong môi trường riêng. Không đồng nhất unit test dùng fake LLM với kiểm thử tích hợp dùng LLM thật. Thông số nhà cung cấp và endpoint cụ thể được lược bỏ khỏi báo cáo; không hàm ý đã kiểm chứng riêng một nhà cung cấp API chính thức.

---

## 1. Tóm tắt điều hành

Challenge B gồm hai phần:

- **B1 — Compaction:** Tạo lịch sử làm việc dài, kích hoạt nén khi context vượt ngưỡng, lưu một *structured checkpoint*, sau đó tiếp tục session chỉ từ checkpoint mà vẫn nhớ nhiệm vụ, ràng buộc, cách đã thử thất bại và bước xử lý tiếp theo.
- **B2 — Code Mode:** Cho chương trình xử lý nhiều tool call và hàng nghìn dòng log trong Python Runtime, chỉ chuyển kết quả đã tổng hợp vào LLM. Bản nâng cao cho **LLM tự sinh chương trình Python-subset**, kiểm tra AST theo danh sách cho phép rồi diễn giải qua runtime hạn chế.

### Kết quả đo được trong quá trình thực hành

| Hạng mục | Bằng chứng từ terminal | Kết quả |
|---|---|---|
| B1: context ban đầu | `Approx. active tokens BEFORE: 13243` | 13.243 token ước tính |
| B1: sau compaction | `Approx. active tokens AFTER: 345` | 345 token ước tính |
| B1: tỷ lệ giảm | `Reduced by 97.4%` | **97,4%** |
| B1: trạng thái sau resume | `Next action: inspect_locking` | Đúng hành động kỳ vọng |
| B1: đánh giá cuối | `B1 RESULT: PASS` | **PASS** |
| B2 cơ bản: dữ liệu | 100 file / 12.000 dòng | Đã đọc và thống kê tại máy |
| B2 cơ bản: raw / findings | 615.422 / 343 token ước tính | **99,94%** giảm input ước tính |
| B2 cơ bản: đánh giá cuối | `B2 RESULT: PASS` | **PASS** |
| B2 Dynamic: mã do LLM sinh | `AST allowlist: ACCEPTED` | Chấp nhận chương trình hợp lệ |
| B2 Dynamic: thực thi | 100 file / 12.000 dòng | Đã diễn giải chương trình trong runtime |
| B2 Dynamic: raw / hai request LLM | 615.424 / 712 token ước tính | **99,88%** giảm input ước tính |
| B2 Dynamic: đánh giá cuối | `B2 DYNAMIC RESULT: PASS` | **PASS** |
| Unit test trên máy người học | `Ran 18 tests ... OK (skipped=1)` | **17 PASS, 1 SKIPPED** |
| Unit test tích hợp trong môi trường kiểm tra riêng | `Ran 21 tests ... OK` | **21 PASS**, không dùng LLM thật |

**Kết luận ngắn:** Các mục tiêu của Challenge B đã được chứng minh bằng ví dụ mô phỏng. Kết quả chưa phải bằng chứng về độ an toàn, chất lượng và hiệu quả chi phí trên hệ thống production hoặc trên mọi dạng log và mọi yêu cầu người dùng.

---

## 2. Yêu cầu đầu vào và phạm vi kiến trúc

### 2.1. Điều kiện trước khi cài

1. Máy Windows có **VS Code** và extension **Python** của Microsoft.
2. Python có `venv` và `pip`; khuyến nghị **Python 3.11 hoặc 3.12** để giảm rủi ro tương thích. Người thực hành đã chạy project trên Python 3.14, vì vậy **không cần đổi phiên bản nếu môi trường hiện tại vẫn PASS**.
3. Có quyền sử dụng một **LLM API tương thích OpenAI**, với endpoint, model ID và API key hợp lệ (nếu dịch vụ yêu cầu).
4. Endpoint/model phải hỗ trợ cơ chế request đang dùng trong project (mặc định là Chat Completions).
5. Sử dụng **OpenAI Python SDK** làm client; đây là thư viện giao tiếp API, **không có nghĩa tất cả lần gọi đều được gửi tới dịch vụ OpenAI chính thức**.
6. Có mã nguồn cho ba module: B1 Compaction, B2 Fixed Code Mode và B2 Dynamic Code Mode, cùng các bài test liên quan.

### 2.2. Cấu trúc thư mục sau khi ghép các gói

```text
challenge-b1-compaction/
├── .env.example
├── .env                         # Người dùng tự tạo; KHÔNG đưa lên Git
├── .gitignore
├── .venv/                       # Môi trường Python tại máy
├── requirements.txt
├── README.md
├── main.py                      # B1: Compaction
├── b2_code_mode.py              # B2: Code Mode cơ bản
├── b2_dynamic_code_mode.py      # B2: Dynamic Code Mode
├── tests/
│   ├── test_compaction.py
│   ├── test_b2_code_mode.py
│   └── test_b2_dynamic_code_mode.py
├── data/                        # B1: checkpoint, history, kết quả resume
├── b2_data/
│   └── logs/                   # 100 file log giả lập
└── b2_dynamic_data/             # Chương trình LLM sinh và kết quả Dynamic B2
```

**Lưu ý:** `data/`, `b2_data/`, `b2_dynamic_data/` chứa dữ liệu/kết quả được tạo trong lúc chạy. Không cần tự tạo tất cả các file JSON trong các thư mục này.

### 2.3. Luồng kiến trúc

```text
                         Người dùng / CLI (VS Code)
                                   |
                         Python Agent Harness
                                   |
                    +--------------+---------------+
                    |                              |
             B1: Compaction                 B2: Code Mode
                    |                              |
        Long simulated session           User asks about logs
                    |                              |
           LLM API                          LLM API
             tạo checkpoint                 sinh chương trình
                    |                              |
          Validate checkpoint            AST allowlist validator
                    |                              |
           Save archive +               Restricted AST Runtime
           active_context                đọc nhiều local logs
                    |                              |
          LLM resume từ                   Structured findings
          checkpoint duy nhất                      |
                    |                          LLM API
           Hành động tiếp theo               Câu trả lời cuối
```

**Giới hạn quan trọng:** Hai module B1 và B2 hiện **chạy độc lập**. Chưa có một Agent Loop hợp nhất tự chọn tool, tự compact và duy trì trạng thái liên tục trong cùng phiên nhiều lượt.

---

## 3. Hướng dẫn cài đặt từ đầu trong VS Code

### 3.1. Chuẩn bị mã nguồn

**Cách A — nếu đã có project hoạt động:** Giữ thư mục `challenge-b1-compaction`, `.env` và `.venv` hiện tại; không cần tạo mới. Chỉ bảo đảm có ba file `main.py`, `b2_code_mode.py`, `b2_dynamic_code_mode.py` và các test tương ứng.

**Cách B — cài từ đầu:**

1. Chuẩn bị thư mục mã nguồn B1 (`main.py`, `requirements.txt`, `.env.example`, `tests/test_compaction.py`) trong `challenge-b1-compaction/`.
2. Giải nén **`challenge-b2-code-mode-addon.zip`** và chép `b2_code_mode.py` vào thư mục gốc; chép `tests/test_b2_code_mode.py` vào `tests/`.
3. Giải nén **`challenge-b2-dynamic-code-mode-addon.zip`** và chép `b2_dynamic_code_mode.py` vào thư mục gốc; chép `tests/test_b2_dynamic_code_mode.py` vào `tests/`.
4. Có thể chép thêm `B2_README.md`, `B2_DYNAMIC_README.md` để giữ hướng dẫn kỹ thuật gốc.
5. Giữ phiên bản `main.py` có hỗ trợ cấu hình `OPENAI_BASE_URL` và `LLM_API_MODE` qua biến môi trường; tránh ghi đè bằng bản cũ chưa có các tùy chọn này.
6. Mở thư mục gốc bằng **VS Code → File → Open Folder**.

> Nếu giảng viên tải project từ GitHub đã ghép sẵn các module, chỉ cần clone repository và tiếp tục từ bước tạo môi trường Python; không cần tìm các gói bổ sung riêng lẻ.

### 3.2. Tạo môi trường Python

Mở **Terminal → New Terminal** trong VS Code. Tại thư mục gốc project:

```powershell
python --version
py -0p
```

Nếu muốn dùng Python 3.12 và phiên bản đó đã được cài:

```powershell
py -3.12 -m venv .venv
```

Hoặc sử dụng phiên bản Python mặc định:

```powershell
py -3 -m venv .venv
```

Kích hoạt virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Nếu PowerShell chặn script, **không cần giảm chính sách bảo mật của toàn máy**: có thể chuyển terminal VS Code sang Command Prompt rồi dùng:

```cmd
.venv\Scripts\activate.bat
```

Trong VS Code, chọn **Ctrl + Shift + P → Python: Select Interpreter** và chọn interpreter nằm trong `.venv`.

### 3.3. Cài dependencies

Nội dung yêu cầu của `requirements.txt`:

```text
openai>=2.0,<4.0
python-dotenv>=1.0,<2.0
pydantic>=2.0,<3.0
tiktoken>=0.7,<1.0
```

Cài đặt:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Kiểm tra toàn bộ thư viện:

```powershell
python -c "import openai, dotenv, pydantic, tiktoken; print('All dependencies OK')"
```

**Kết quả mong đợi:** `All dependencies OK`.

**Lỗi đã gặp trong quá trình thực hành:**

- `ModuleNotFoundError: No module named 'dotenv'`: bổ sung **`python-dotenv`**, không phải package tên `dotenv`.
- `ModuleNotFoundError: No module named 'pydantic'`: chưa cài đủ `requirements.txt` hoặc đang dùng sai môi trường Python.

Ưu tiên `python -m pip install -r requirements.txt` thay vì cài từng thư viện theo từng lỗi.

### 3.4. Cấu hình kết nối LLM trong `.env`

Tạo file cấu hình từ mẫu:

```powershell
Copy-Item .env.example .env
```

Ví dụ cấu hình tham khảo khi dùng OpenAI API chính thức (không phải cấu hình đã dùng để ghi nhận kết quả):

```ini
# Thay bằng thông số API bạn được cấp.
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini
OPENAI_API_KEY=YOUR_API_KEY
LLM_API_MODE=chat
COMPACT_THRESHOLD_TOKENS=2500
```

> **Lưu ý:** Đoạn cấu hình trên chỉ nhằm minh họa cách sử dụng một API phổ biến, **không phải cấu hình được dùng để thu thập các số liệu trong phần kết quả**. Với endpoint tương thích OpenAI khác, thay `OPENAI_BASE_URL`, `OPENAI_MODEL` và `OPENAI_API_KEY` theo tài liệu của dịch vụ. Các thống kê PASS và số token dưới đây là bằng chứng của lần chạy đã ghi nhận, không bảo đảm lặp lại chính xác với model khác. Không commit API key vào Git.

Giải thích:

| Biến | Chức năng |
|---|---|
| `OPENAI_BASE_URL` | Địa chỉ API base URL tương thích OpenAI (theo cấu hình dịch vụ sử dụng) |
| `OPENAI_MODEL` | Model ID được endpoint hỗ trợ, phải khớp cấu hình được cấp |
| `OPENAI_API_KEY` | Khóa truy cập hợp lệ của dịch vụ API; quản lý bằng biến môi trường |
| `LLM_API_MODE` | `chat` gọi Chat Completions; chỉ thử `responses` khi endpoint/model và code hỗ trợ |
| `COMPACT_THRESHOLD_TOKENS` | Ngưỡng **thực hành** để B1 quyết định compact, không phải context-window tối đa của model |

**Về API key:** Khi dùng dịch vụ có xác thực, phải điền key hợp lệ vào `.env`. Một số endpoint thử nghiệm nội bộ có thể cho phép key giả hoặc bỏ xác thực, nhưng không được giả định điều đó áp dụng cho mọi nhà cung cấp. Nếu nhận HTTP 401, kiểm tra thông tin xác thực; **không gửi hoặc commit key**.

### 3.5. Cập nhật `.gitignore` để tránh đưa dữ liệu chạy lên Git

Kiểm tra `.gitignore` tại thư mục gốc và bảo đảm có tối thiểu:

```gitignore
.env
.venv/
__pycache__/
*.pyc
data/*.json
b2_data/
b2_dynamic_data/
```

Các file log demo, checkpoint, payload và câu trả lời sinh trong quá trình chạy là **đầu ra thực nghiệm**, không nhất thiết cần đưa vào source control. Nếu cần nộp bằng chứng, tạo bản sao đã rà soát và che dữ liệu không nên công khai.

### 3.6. Xác nhận kết nối LLM hoạt động

```powershell
python main.py ping
```

Kỳ vọng:

```text
# Ví dụ: lời gọi thử tới endpoint/model cấu hình đã thành công
Model reply: OK
```

Dòng hiển thị ban đầu của lệnh `ping` có thể khác tùy phiên bản mã nguồn và cấu hình API. Kết quả có ý nghĩa là **lời gọi inference trả về nội dung hợp lệ**; việc chỉ kết nối TCP thành công (nếu kiểm tra riêng) không đủ chứng minh LLM có thể trả lời.

---

## 4. Hướng dẫn sử dụng Challenge B1 — Compaction

### 4.1. Mục tiêu và dữ liệu đầu vào

Mô phỏng lỗi `refresh-token race condition`:

- Mục tiêu: sửa lỗi xảy ra khi nhiều yêu cầu refresh token chạy đồng thời.
- Ràng buộc: giữ API backward compatible.
- Test đang lỗi: `test_concurrent_refresh`, `test_parallel_rotation`.
- Đã thử tăng TTL của refresh token; cách đó **không hiệu quả**.
- Bước tiếp theo cần giữ: **kiểm tra locking/synchronization**, chưa kết luận nguyên nhân gốc.
- History chứa nhiều dòng tool log giả lập để gây phình context.

Đây **không phải** phần mềm authentication thật và không sửa bất kỳ backend nào.

### 4.2. Các lệnh thực hiện

**(1) Kiểm tra điều kiện kích hoạt, không tốn request LLM**

```powershell
python main.py preview
```

Kết quả đã ghi nhận:

```text
Approx. input tokens: 13243
Threshold: 2500
Compaction would trigger: True
```

**(2) Sinh structured checkpoint với LLM qua API đã cấu hình**

```powershell
python main.py run
```

Kết quả ghi nhận:

```text
[1/4] Approx. active tokens BEFORE: 13243
[2/4] Threshold reached (2500): compacting with LLM...
[3/4] Approx. active tokens AFTER:  345
[4/4] Reduced by 97.4%
```

**(3) Resume từ context đã nén**

```powershell
python main.py resume
```

Trong phiên đã chạy, Agent xuất ra:

```text
Loading ONLY active_context.json (not archive_history.json)...
Next action: inspect_locking
```

Agent còn nhớ việc **tăng TTL không giải quyết lỗi**, và chọn kiểm tra locking trước khi thay đổi code.

**(4) Xác minh điều kiện thành công**

```powershell
python main.py verify
```

Kết quả ghi nhận:

```text
PASS - goal/constraints/failed attempts/next action preserved
PASS - active context reduced >= 50%
PASS - agent chose inspect_locking
PASS - agent remembers failed TTL attempt
B1 RESULT: PASS
```

### 4.3. Các file đầu ra B1

| File | Nội dung cần kiểm tra |
|---|---|
| `data/archive_history.json` | History dài đã lưu lại để đối chiếu; **không được dùng làm input khi resume** |
| `data/checkpoint.json` | `goal`, `current_state`, `constraints`, `findings`, `failed_attempts`, `files`, `next_action` |
| `data/active_context.json` | Context nhỏ gọn, chứa checkpoint và hướng dẫn cần cho session tiếp |
| `data/metrics.json` | Token ước tính trước/sau, tỷ lệ giảm, ngưỡng compact |
| `data/resume_result.json` | Hành động và lý do do LLM chọn khi resume |

**Kiểm tra thủ công:** Mở `checkpoint.json` và xác nhận có mục tiêu, tính tương thích API, TTL thất bại, và bước kiểm tra locking. Mở `active_context.json` để kiểm tra log thô không còn chiếm toàn bộ context. **Không được chỉ dựa vào tỷ lệ giảm token** nếu checkpoint làm mất thông tin quan trọng.

### 4.4. Logic B1 đã triển khai

1. Tạo long history gồm yêu cầu, các bước thử, log mô phỏng và trạng thái đang điều tra.
2. Ước tính số token; so với `COMPACT_THRESHOLD_TOKENS`.
3. Gọi LLM qua `OpenAIPlanner` để tạo JSON checkpoint; Pydantic kiểm tra schema.
4. `validate_checkpoint()` kiểm tra một số thông tin **bắt buộc của kịch bản cố định**.
5. Chỉ khi checkpoint hợp lệ, tạo active context mới và lưu archive tách biệt.
6. Gọi `resume` bằng `active_context.json`, kiểm tra bước tiếp theo và thông tin đã nhớ.

**Điểm phải hiểu đúng:** Compaction ở đây là cơ chế do chính Agent Harness quản lý, **không phải** tính năng memory mặc định hoặc server-side compaction của LLM/provider.

---

## 5. Hướng dẫn Challenge B2 cơ bản — Fixed Code Mode

### 5.1. Mục tiêu

Python xử lý log tại máy thay cho việc gửi toàn bộ file vào input của LLM. Phiên bản B2 cơ bản sử dụng **chương trình phân tích cố định do người phát triển viết trước**, nên trình diễn lợi ích về context nhưng chưa thể coi là LLM tự lập trình.

### 5.2. Các lệnh chạy

```powershell
python b2_code_mode.py generate
python b2_code_mode.py analyze
python b2_code_mode.py ask
python b2_code_mode.py verify
```

| Lệnh | Tác dụng | Gọi LLM? |
|---|---|---|
| `generate` | Tạo 100 file log giả lập × 120 dòng = 12.000 dòng | Không |
| `analyze` | `list_files` → `read_file` → trích mã lỗi → tổng hợp findings | Không |
| `ask` | Gửi structured findings tới LLM và nhận câu trả lời | **Có** |
| `verify` | Kiểm tra đầu ra, marker, tỷ lệ giảm token và mã lỗi chính | Không |

### 5.3. Kết quả thực tế

```text
Generated 100 synthetic log files / 12000 lines
Runtime read 100 log files / 12000 lines LOCALLY
Naive all-raw prompt estimate: 615422 tokens
Code Mode compact prompt estimate: 343 tokens
Estimated reduction: 99.94%
B2 RESULT: PASS
```

LLM nhận đúng bảng tổng hợp:

| Mã lỗi | Số lần | Tỷ lệ trên 2.094 lỗi |
|---|---:|---:|
| `REFRESH_RACE` | 1.091 | 52,10% |
| `UPSTREAM_TIMEOUT` | 620 | 29,61% |
| `DB_POOL_EXHAUSTED` | 383 | 18,29% |
| **Tổng** | **2.094** | **100%** |

Top 5 file được trả về: `service-014.log` đến `service-018.log`, mỗi file 22 lỗi. Không đủ dữ liệu trong riêng top 5 để kết luận có hay không những file khác đồng hạng.

### 5.4. File đầu ra B2 cơ bản

- `b2_data/logs/*.log`: dữ liệu thô **giả lập**, chỉ đọc tại máy.
- `b2_data/findings.json`: tổng hợp số lỗi theo code và theo file.
- `b2_data/metrics.json`: ước tính token raw vs structured prompt.
- `b2_data/payload_to_llm.json`: nội dung system/user được chuẩn bị chuyển cho LLM.
- `b2_data/answer.json`: câu trả lời từ LLM sau `ask`.

**Bằng chứng:** `analyze` tự ghi rõ `No LLM called in 'analyze'`. File `payload_to_llm.json` cần không chứa các đoạn log thô/marker đặc trưng của dữ liệu mô phỏng.

---

## 6. Hướng dẫn Challenge B2 nâng cao — Dynamic Code Mode

### 6.1. Khác biệt so với B2 cơ bản

B2 Dynamic cho LLM sinh chương trình theo yêu cầu, thay vì luôn chạy một vòng lặp cố định. Chương trình sinh ra chỉ được phép dùng **tập con rất nhỏ của Python** và các API đã duyệt:

```python
paths = tools.list_files("*.log")
counts = new_counter()
per_file = new_counter()
for path in paths:
    raw = tools.read_file(path)
    for line in raw.splitlines():
        code = extract_error_code(line)
        if code:
            counter_add(counts, code)
            counter_add(per_file, path.name)
result = make_findings(counts, per_file, tools, 5)
```

Đây là chương trình đã được LLM thật sinh và được báo `AST allowlist: ACCEPTED`. Nó **trùng với ví dụ hợp lệ có trong system prompt**; vì vậy mới xác minh khả năng tạo/chấp nhận đúng chương trình theo mẫu, **chưa đủ chứng minh Agent tự tìm ra chiến lược hoàn toàn mới**.

### 6.2. Trình tự thực hiện (trên bộ log đã tạo)

```powershell
python b2_dynamic_code_mode.py plan
python b2_dynamic_code_mode.py execute
python b2_dynamic_code_mode.py ask
python b2_dynamic_code_mode.py verify
```

Hoặc, sau khi đã có log:

```powershell
python b2_dynamic_code_mode.py all
```

**Diễn giải từng bước:**

1. **`plan` — GỌI LLM THẬT:** Gửi yêu cầu và đặc tả API tool đến endpoint LLM đã cấu hình. LLM trả về mã Python-subset. Kiểm tra AST, lưu `program.txt`, `program_meta.json` cùng SHA-256. Không gửi log thô trong yêu cầu sinh mã.
2. **`execute` — KHÔNG GỌI LLM:** Kiểm tra lại SHA-256, parse/validate AST, diễn giải chương trình bằng restricted runtime. Các lệnh `tools.list_files`, `tools.read_file`, tách dòng, đếm lỗi được thực hiện tại máy. Không được dùng `exec()`/`eval()` để thực thi mã sinh ra.
3. **`ask` — GỌI LLM THẬT:** Gửi findings đã tổng hợp tới model qua API đã cấu hình và nhận câu trả lời.
4. **`verify` — KHÔNG GỌI LLM:** So sánh số lượng lỗi với thuật toán tham chiếu cố định, kiểm tra số file, dữ liệu truyền vào, tỷ lệ token và nội dung câu trả lời.

> **TUYỆT ĐỐI KHÔNG** chạy `python b2_dynamic_data/program.txt` hoặc copy mã chưa kiểm duyệt sang `.py` để chạy trực tiếp. Chỉ dùng lệnh `execute` để mã được kiểm tra và chạy trong restricted interpreter.

### 6.3. Kết quả chạy tích hợp với LLM thật

Bước lập kế hoạch:

```text
LLM generated Python-subset program; AST allowlist: ACCEPTED
Saved: b2_dynamic_data/program.txt
Program SHA-256: 66c1415c7808c8442811c6f9673a8360eb094b4da0cdcb6dd703c1bafe5f393a
```

Bước thực thi:

```text
Runtime interpreted LLM program; read 100 files / 12000 lines LOCALLY
Raw-log input estimate: 615424 tokens
Two LLM request input estimate: 712 tokens
Estimated input reduction: 99.88%
Structured findings saved; raw log lines were not sent to the model
```

Bước kiểm thử cuối:

```text
PASS - LLM-generated program validated by restricted AST
PASS - runtime processed at least 50 files
PASS - runtime counts match trusted offline reference
PASS - raw marker absent from both model inputs
PASS - raw diagnostic absent from both model inputs
PASS - runtime did not exec/eval code
PASS - two-request estimated input reduction >= 80%
PASS - answer obtained and includes top error
B2 DYNAMIC RESULT: PASS
```

LLM tổng hợp chính xác 2.094 lỗi, xếp `REFRESH_RACE` đứng đầu (1.091 lần), và không khẳng định nguyên nhân gốc chỉ từ thống kê.

### 6.4. Các file đầu ra và cách đọc

| File | Ý nghĩa |
|---|---|
| `b2_dynamic_data/codegen_payload.json` | Prompt *sinh chương trình* gửi cho LLM; không chứa raw logs |
| `b2_dynamic_data/program.txt` | Chương trình do LLM sinh, **không thực thi trực tiếp** |
| `b2_dynamic_data/program_meta.json` | Model, câu hỏi, SHA-256 của source |
| `b2_dynamic_data/findings.json` | Kết quả thống kê có cấu trúc |
| `b2_dynamic_data/payload_to_llm.json` | Prompt gửi LLM lần thứ hai, chỉ gồm câu hỏi và findings |
| `b2_dynamic_data/audit.json` | Phương thức runtime, danh sách tool, SHA-256, số file đọc |
| `b2_dynamic_data/metrics.json` | Baseline raw và tổng input token ước tính của **hai request** |
| `b2_dynamic_data/answer.json` | Câu trả lời LLM sau `ask` |
| `b2_dynamic_data/rejected_program.txt` | Chỉ có nếu mã sinh ra bị validator từ chối |

### 6.5. Các hàng rào kỹ thuật hiện có

Module `b2_dynamic_code_mode.py` triển khai:

- **AST allowlist:** cấm import, function/class definitions, shell, `exec/eval`, `while`, attribute/call không nằm trong tập được phép.
- **API allowlist:** chỉ đọc `*.log`, `read_file`, `splitlines`, đếm lỗi và tạo findings theo schema dự kiến.
- **Giới hạn nguồn:** tối đa **9.000 bytes source** và **120 AST nodes**.
- **Giới hạn đọc:** tối đa **150 file**, **120.000 bytes/file**, **8.000.000 bytes tổng**, **25.000 dòng**.
- **Giới hạn runtime:** tối đa **150.000 bước** và **15 giây** theo đồng hồ đơn điệu được kiểm tra trong interpreter.
- **Kiểm tra đường dẫn:** hạn chế đọc ra ngoài thư mục log; có logic từ chối symbolic link.
- **Integrity check:** đối chiếu SHA-256 khi chuyển từ `plan` sang `execute`; **đây là phát hiện thay đổi ngoài ý muốn, không phải chữ ký chống người tấn công có thể sửa cả mã và metadata**.
- **Đối chiếu số đếm:** findings từ mã động phải khớp thuật toán tham chiếu của B2 cơ bản.

Đây là **hàng rào cấp ứng dụng**, không phải sandbox ở cấp hệ điều hành, không nên dùng để chạy Python tùy ý do LLM sinh khi xử lý dữ liệu thật.

---

## 7. Hướng dẫn kiểm thử và tiêu chí nghiệm thu

### 7.1. Chạy toàn bộ Unit Test

```powershell
python -m unittest discover -s tests -v
```

**Kết quả trên máy người học (Windows):**

```text
Ran 18 tests in 7.781s
OK (skipped=1)
```

Diễn giải đúng: **18 test được phát hiện; 17 test chạy thành công, 1 test được bỏ qua** (`test_reject_log_symlinks_if_supported`) do môi trường không hỗ trợ thao tác tạo symlink. Không được ghi "18/18 PASS" hay tuyên bố kiểm thử symlink đã thành công trên Windows này.

**Kiểm tra độc lập bằng bộ mã ghép đầy đủ:**

```text
Ran 21 tests in 0.262s
OK
```

Bản ghép gồm thêm 3 bài test của `test_router_adapter.py` (tên file thuộc mã nguồn của project). Đây là **unit test offline**; FakePlanner/fake adapter không chứng minh một kết nối API thật đã thành công. Chênh lệch số token giữa các máy có thể do bộ đếm `tiktoken` so với fallback số ký tự/4.

### 7.2. Nhóm test đã thực hiện

| Nhóm | Kiểm tra chính | Kết quả |
|---|---|---|
| B1 | Checkpoint đủ state; history dài; từ chối checkpoint thiếu thông tin | PASS |
| API adapter (offline) | Chat Completions, Responses, từ chối JSON sai | PASS trong bộ test tích hợp |
| B2 cơ bản | Không đưa raw log vào prompt; chặn path ngoài thư mục; thống kê đúng; thiếu `answer.json` thì verify thất bại | PASS |
| B2 Dynamic | Chặn import/shell/dynamic exec, `while`, attribute nguy hiểm, bỏ sót file, chương trình bị sửa, kết quả giả mạo | PASS |
| B2 Dynamic | Tạo code → execute → ask → verify bằng fake LLM | PASS offline |
| B2 Dynamic | Symlink | SKIPPED trên Windows người học; PASS tại môi trường test riêng |
| Tích hợp B1 với LLM | `ping`, `run`, `resume`, `verify` | PASS theo terminal người học |
| Tích hợp B2 với LLM | `generate`, `analyze`, `ask`, `verify` | PASS theo terminal người học |
| Tích hợp Dynamic B2 với LLM | `plan`, `execute`, `ask`, `verify` | PASS theo terminal người học |

**Lưu ý về dòng FAIL trong unit test:** Một bài test âm tính cố ý tạo tình huống thiếu `answer.json` và mong lệnh verify báo `B2 RESULT: FAIL - missing files: answer.json`. Khi dòng cuối của toàn bộ test là `OK`, đó là **test PASS vì đã phát hiện lỗi đúng như thiết kế**, không phải thất bại của bộ test.

### 7.3. Checklist nghiệm thu có thể chạy lại

- [ ] `python main.py ping` trả phản hồi hợp lệ từ endpoint LLM được cấu hình.
- [ ] `python main.py preview` xác nhận vượt ngưỡng compact.
- [ ] B1 `run → resume → verify` kết thúc với `B1 RESULT: PASS`.
- [ ] B1 `archive_history.json` không được nạp lại vào lần `resume`.
- [ ] `python b2_code_mode.py generate` tạo đủ 100 file và 12.000 dòng.
- [ ] B2 `analyze → ask → verify` kết thúc với `B2 RESULT: PASS`.
- [ ] B2 `payload_to_llm.json` không chứa log thô hay marker kiểm thử.
- [ ] B2 Dynamic `plan` sinh `program.txt` và validator chấp nhận.
- [ ] B2 Dynamic `execute` xử lý hết log bằng runtime giới hạn, không dùng `exec/eval`.
- [ ] B2 Dynamic `ask → verify` kết thúc với `B2 DYNAMIC RESULT: PASS`.
- [ ] Các thống kê khớp dữ liệu mặc định: tổng 2.094 lỗi; `REFRESH_RACE` 1.091.
- [ ] Test toàn bộ: `python -m unittest discover -s tests -v` kết thúc bằng `OK` (có thể có `skipped=1` trên Windows).

---

## 8. Troubleshooting — lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| `No module named 'dotenv'` | Thiếu `python-dotenv` | Thêm package vào requirements rồi `python -m pip install -r requirements.txt` |
| `No module named 'pydantic'` | Dependencies chưa đủ hoặc sai interpreter | Kiểm tra `.venv`, cài lại requirements |
| `python main.py ping` thất bại | Chưa kết nối được API, sai model ID hoặc chế độ request | Kiểm tra `OPENAI_BASE_URL`, `OPENAI_MODEL`, key, kết nối Internet và chế độ `LLM_API_MODE` |
| HTTP 401 | Thiếu hoặc sai thông tin xác thực API | Cung cấp `OPENAI_API_KEY` hợp lệ cho dịch vụ sử dụng |
| HTTP 400/404 | Endpoint không hợp lệ, model không tồn tại hoặc không hỗ trợ chế độ request | Kiểm tra tài liệu API, model ID và hỗ trợ `chat`/`responses` |
| `run` báo dưới ngưỡng | History chưa đủ lớn so với threshold | Dùng đúng ngưỡng demo hoặc tăng số log mô phỏng với `--log-lines` |
| `resume` thiếu active context | Chưa chạy B1 `run` thành công | Chạy `python main.py run` |
| `B2 RESULT: FAIL - missing ... answer.json` khi chạy riêng | Chưa chạy `ask` sau `analyze` | Chạy `python b2_code_mode.py ask` rồi `verify` |
| `No B2 logs` | Chưa sinh log giả lập | Chạy `python b2_code_mode.py generate` |
| `ProgramRejected` tại `plan` | LLM sinh cú pháp ngoài allowlist | Mở `rejected_program.txt`, sửa prompt/kiểm tra model rồi `plan` lại; **không tắt validator** |
| `Program was modified` | Chương trình thay đổi sau khi duyệt | Chạy lại `plan`; không bỏ qua SHA-256 |
| `Execution budget exceeded` | Quá số bước/thời gian/bytes/file | Kiểm tra source và quy mô đầu vào trước khi nâng quota |
| `test_reject_log_symlinks_if_supported` SKIPPED | Thiếu quyền/hỗ trợ tạo symbolic link | Ghi nhận coverage chưa đủ; kiểm thử trên môi trường có symlink |

### 8.1. Lưu ý trình tự chạy

- **B1:** `preview → ping → run → resume → verify`.
- **B2 cơ bản:** `generate → analyze → ask → verify`.
- **B2 Dynamic:** dùng lại log từ B2 cơ bản; `plan → execute → ask → verify`.
- Unit test có thể tạo các file output trong thư mục test riêng hoặc fixture; **luôn đọc dòng tổng kết `Ran ... / OK`**, không dựa duy nhất vào chữ PASS/FAIL trong thông báo demo bên trong từng test.
- Chạy lại `plan` hoặc `analyze` có thể xóa kết quả trung gian trước đó để tránh dùng `answer.json` cũ. Nếu muốn lưu bằng chứng nhiều lần chạy, sao chép hoặc đổi tên thư mục kết quả trước khi bắt đầu vòng mới.

---

## 9. Những điểm đã hoàn thành

1. **Kết nối LLM qua API tương thích OpenAI:** Python client đọc endpoint/model từ `.env`; các lệnh `ping`, tạo checkpoint, sinh chương trình và trả lời findings đã chạy thành công trên môi trường thực hành.
2. **B1 — Structured Compaction:** Tạo long history, chọn ngưỡng compact, xác thực checkpoint, lưu archive, tạo active context nhỏ hơn và resume đúng bước điều tra.
3. **B2 — Fixed Code Mode:** Tự động tạo và xử lý 100 file log, đếm lỗi bằng Python Runtime, chỉ gửi structured findings vào model.
4. **B2 — Dynamic Code Mode:** LLM sinh source code, AST Validator chấp nhận/từ chối, restricted runtime diễn giải code, tạo findings và lấy câu trả lời từ model.
5. **Kiểm thử chức năng:** Các bài test của B1/B2/Dynamic B2 chạy thành công; kiểm tra output thực tế cho thấy ba lệnh verify cuối đều PASS.
6. **Kiểm soát an toàn ở mức demo:** Chặn nhiều cú pháp không an toàn, giới hạn đường dẫn đọc, dung lượng, số file, số bước và thời gian; kiểm tra source hash; không chủ động gửi raw log ở hai request Dynamic B2.
7. **Khả năng quan sát:** Lưu `checkpoint`, `findings`, `metrics`, `audit`, model payload và answer ra các file riêng, thuận tiện đối chiếu và trình bày bằng chứng.

---

## 10. Hạn chế đã phát hiện và hướng cải thiện

| Ưu tiên | Hạn chế / rủi ro | Hướng cải thiện có thể kiểm chứng |
|---|---|---|
| **P0** | Chưa có cô lập hệ điều hành cho mã/tác vụ do LLM điều phối; AST interpreter chỉ hỗ trợ ngôn ngữ rất nhỏ | Nếu mở rộng chạy code tổng quát: đưa vào sandbox/container/VM có giới hạn file system, network, CPU/RAM/time, quyền tối thiểu; kiểm thử tấn công với mã độc mẫu |
| **P0** | Kiểm tra rò rỉ raw log dựa vào marker và payload; không chứng minh được mọi dữ liệu nhạy cảm đều không lộ | Dùng chính sách data classification, redaction, schema output allowlist, integration test với log chứa dữ liệu giả nhạy cảm; xác nhận request body phát thực tế |
| **P1** | B1 `validate_checkpoint` chủ yếu kiểm tra từ khóa của một kịch bản refresh-token cố định | Thiết kế schema/checkpoint tổng quát theo task; đánh giá faithfulness, kiểm tra constraint có cấu trúc, test nhiều case và mâu thuẫn |
| **P1** | B1/B2 chưa được tích hợp thành agent loop nhiều lượt | Tạo orchestration quản lý session, tool results, context budget, memory/checkpoint và action history; demo một phiên hỏi đáp nhiều bước rồi compact/resume |
| **P1** | LLM sinh code gần như sao chép ví dụ trong system prompt; chưa chứng minh tính linh hoạt khi yêu cầu thay đổi | Thử nhiều câu hỏi, top-k khác nhau, thống kê theo file/loại lỗi; cho model sinh kế hoạch trên một DSL an toàn và kiểm thử bằng dataset độc lập |
| **P1** | Thống kê bằng mã động và mã tham chiếu cùng chia sẻ parser/quy tắc định dạng log; có thể có lỗi tương quan | Thêm bộ test ground-truth độc lập với dữ liệu được gán nhãn, trường hợp log hỏng, duplicate, unicode, file trống, nhiều định dạng |
| **P1** | Unit test symlink bị bỏ qua trên Windows người học | Chạy CI trên môi trường hỗ trợ symlink; kiểm thử junction/reparse point và race-condition của filesystem |
| **P1** | Không có phép đo usage API thực tế và chi phí hoàn chỉnh | Lưu `usage`/latency nếu API trả về; cộng input/output của 2 request, retries, chi phí dịch vụ và compaction; so sánh A/B |
| **P2** | Dữ liệu chỉ giả lập, chưa kiểm thử log lớn/khác định dạng | Tạo nhiều dataset với kích thước và phân bố lỗi khác nhau, benchmark thời gian, peak memory, độ chính xác |
| **P2** | Hash SHA-256 kiểm tra thay đổi file nhưng chưa có provenance chống người sửa cả `program.txt` lẫn metadata | Bảo vệ metadata/approval ở vùng không thể sửa bởi chương trình, ký HMAC/chữ ký hoặc dùng manifest chỉ-đọc |
| **P2** | File JSON ghi ra đĩa chưa có chính sách lưu trữ, bảo mật hoặc rotation rõ ràng | Cấu hình thời gian lưu, xóa log mô phỏng/kết quả cũ, quyền đọc file, mã hóa khi phù hợp; không commit dữ liệu nhạy cảm |
| **P2** | Chưa có CI, packaging và hướng dẫn cross-platform tự động | Bổ sung `pyproject.toml`, GitHub Actions, test matrix 3.11–3.14 (nếu tương thích), CLI nhất quán và version pin/lockfile |

**Ưu tiên cải thiện gần nhất:** (1) kiểm tra model sinh chương trình trên **nhiều yêu cầu/dataset**, (2) bổ sung **đo usage/latency thật**, (3) **tích hợp B1+B2 thành một agent loop**, rồi mới cân nhắc triển khai trên dữ liệu thật. Khi chưa có sandbox và chính sách dữ liệu phù hợp, không mở quyền chạy Python tổng quát.

### 10.1. Diễn giải đúng về con số tối ưu token

- **97,4% của B1**: giảm kích thước **active context ước tính** sau checkpoint; chưa tính phí gọi LLM để compact và các request tiếp theo.
- **99,94% của B2 cơ bản**: so sánh *giả định gửi tất cả raw log* với **một prompt findings**; không bao gồm toàn bộ chi phí một workflow production.
- **99,88% của B2 Dynamic**: so sánh raw baseline với tổng **input ước tính của hai lần gọi LLM** (*plan* + *ask*), chưa gồm output tokens, request wrappers, retry hoặc đơn giá API thực tế.
- Các giá trị baseline raw hơn 600 nghìn token là **phương án đối chứng giả định**, không có bằng chứng rằng một model hiện tại có thể/đã xử lý thành công prompt khổng lồ như vậy trong một request.
- **Giảm input estimate ≠ giảm đúng từng đó tiền API ≠ tăng cùng tỷ lệ chất lượng**. Cần đo API usage và quality trên các nhiệm vụ tương đương để kết luận tổng hiệu quả.

---

## 11. Tiêu chí hoàn thành bài tập và kết luận

### Đối chiếu với yêu cầu tại slide Challenge B

| Yêu cầu slide | Cách thực hiện | Đánh giá |
|---|---|---|
| B1: Session dài được compact | Sinh log dài + structured checkpoint | **Đạt** |
| B1: nhớ lỗi đang điều tra | `refresh-token race condition` còn trong checkpoint và resume | **Đạt** |
| B1: nhớ cách đã thử | TTL đã tăng nhưng không hiệu quả | **Đạt** |
| B1: nhớ bước tiếp theo | `inspect_locking` | **Đạt** |
| B2: Agent trả lời câu hỏi trên nhiều file log | Xử lý 100 file / 12.000 dòng, hỏi LLM từ findings | **Đạt** |
| B2: raw log không đi vào context của LLM | Code Runtime tổng hợp cục bộ + kiểm tra payload/marker | **Đạt trong phạm vi demo và kiểm thử hiện có** |
| B2 mở rộng: LLM sinh chương trình, runtime gọi tools | Dynamic Code Mode với AST interpreter | **Đạt với Python-subset giới hạn** |

### Kết luận cuối

**Challenge B1 và B2 đã được hoàn thành và kiểm tra thành công theo các tiêu chí của bài thực hành.** Người thực hành đã chứng minh qua terminal rằng: kết nối LLM có thể thực hiện inference, Agent có thể compact và resume mà giữ trạng thái quan trọng, Python có thể xử lý hàng loạt log mà không đưa nguyên văn log vào input LLM, và một chương trình Python-subset do LLM sinh có thể được validator chấp nhận, diễn giải và đối chiếu kết quả.

Dù vậy, đây là **hệ thống thử nghiệm phục vụ học tập**. Các bằng chứng hiện tại không đủ để khẳng định hệ thống đã sẵn sàng xử lý log thực tế nhạy cảm, mã Python bất kỳ, hoặc quy trình vận hành production. Hướng phát triển có giá trị cao nhất là mở rộng kiểm thử độ chính xác, bổ sung cô lập bảo mật phù hợp, đo chi phí thực tế và hợp nhất B1+B2 thành một Agent Harness chạy nhiều lượt.

---

## Phụ lục A — Bộ lệnh chạy nhanh

```powershell
# 0. Ở thư mục gốc; đã cài requirements và có .env hợp lệ
python -m unittest discover -s tests -v

# 1. Kiểm tra API LLM
python main.py ping

# 2. Challenge B1
python main.py preview
python main.py run
python main.py resume
python main.py verify

# 3. Challenge B2 cơ bản
python b2_code_mode.py generate
python b2_code_mode.py analyze
python b2_code_mode.py ask
python b2_code_mode.py verify

# 4. Challenge B2 Dynamic (dùng log của bước 3)
python b2_dynamic_code_mode.py plan
python b2_dynamic_code_mode.py execute
python b2_dynamic_code_mode.py ask
python b2_dynamic_code_mode.py verify
```

## Phụ lục B — Bằng chứng cần lưu để nộp / trình bày

| Bằng chứng | Nơi lấy |
|---|---|
| Ảnh chụp unit test `OK` | Terminal VS Code |
| Ảnh chụp kết quả `python main.py ping` | Terminal VS Code (che key/endpoint nội bộ nếu có) |
| So sánh token trước/sau B1 | `data/metrics.json` và terminal B1 |
| Structured checkpoint | `data/checkpoint.json` |
| Hành động Agent sau resume | `data/resume_result.json` |
| Thống kê 100 file log B2 | `b2_data/findings.json` |
| LLM chỉ nhận findings B2 | `b2_data/payload_to_llm.json` |
| Mã do LLM sinh + tính toàn vẹn | `b2_dynamic_data/program.txt`, `program_meta.json` |
| Kết quả xử lý và audit Dynamic B2 | `b2_dynamic_data/findings.json`, `audit.json`, `metrics.json` |
| LLM trả lời và verify cuối | `b2_dynamic_data/answer.json` và terminal `B2 DYNAMIC RESULT: PASS` |

**Bảo mật khi chia sẻ:** Xóa/che API key, thông tin tài khoản và đường dẫn cá nhân không cần thiết. Không đính kèm `.env` hoặc các log thực tế nhạy cảm.

---

*Hết báo cáo.*
