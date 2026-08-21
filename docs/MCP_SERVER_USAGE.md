# MCP Server — Usage Guide (chạy thử local)

Hướng dẫn này dành cho việc **tự chạy và test `mcp_server/` trên máy của bạn**.
Xem kiến trúc tổng thể tại [ARCHITECTURE.md](ARCHITECTURE.md), hướng dẫn
tích hợp client tại [MCP_SERVER_INTEGRATION.md](MCP_SERVER_INTEGRATION.md), và
hướng dẫn deploy public tại [MCP_SERVER_DEPLOYMENT.md](MCP_SERVER_DEPLOYMENT.md).

## 1. Cài dependency (1 lần)

```bash
cd <repo-root>
pip install -r mcp_server/requirements.txt
```

## 2. Tạo bearer key cho client

MCP server không lưu raw key, chỉ lưu hash SHA-256. Tạo 1 cặp key/hash:

```bash
python -c "
import secrets, hashlib
key = secrets.token_urlsafe(24)
print('RAW_KEY=' + key)
print('HASH=' + hashlib.sha256(key.encode()).hexdigest())
"
RAW_KEY=PqTUmPNKxrVn2g3EJslOdeUorNcntST5
HASH=b210b4660de91484074f62370a43766b8669bab7ab21814fe3c2e8bf1638cc78
```

- `RAW_KEY` → đưa cho client (Flask app, MCP Inspector, script test, agent ngoài...).
- `HASH` → đưa vào `MCP_API_KEYS_JSON` của server, không bao giờ gửi đi.

## 3. Set biến môi trường và chạy server

```bash
$env:MCP_API_KEYS_JSON='{"demo-caller":"b210b4660de91484074f62370a43766b8669bab7ab21814fe3c2e8bf1638cc78"}'
$env:PORT=8000
$env:COMPANY_MONGODB_URI="mongodb://readonly_user:replace_me@company-mongo-host:27017/?authSource=admin&directConnection=true"   # MongoDB thật của bạn -- directConnection=true bắt buộc nếu seed host là 1 member duy nhất expose qua IP public/NAT, còn các member khác chỉ advertise IP nội bộ (192.168.x.x) không reach được từ ngoài
$env:MCP_ENABLE_GRAFANA_TOOLS="true"
$env:GRAFANA_URL="https://your-grafana-host"
$env:GRAFANA_USERNAME="readonly_user"
$env:GRAFANA_PASSWORD="replace_me"
python mcp_server/server.py
```

Server chạy ở foreground (`Ctrl+C` để dừng). Log thành công trông như:

```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

Lưu ý quan trọng: **Loki không có URL riêng** — dùng thư viện [grafana-client](https://github.com/grafana-toolbox/grafana-client)
gọi qua cùng Grafana instance (`datasource.smartquery()`), dùng chung
credential Grafana (`GRAFANA_USERNAME`/`GRAFANA_PASSWORD` hoặc
`GRAFANA_API_KEY`). Vì vậy nhóm tool Loki và Grafana/Prometheus cùng được bật
bởi 1 flag duy nhất: `MCP_ENABLE_GRAFANA_TOOLS=true`. Muốn tìm đúng
`datasource_uid` (không còn dùng id cố định nữa), gọi tool `grafana_list_datasources`.

**Guardrail chỉ áp dụng cho Mongo** (allowlist namespace, chặn operator, rate
limit, audit) — Loki/Grafana/Prometheus **không có** allowlist/cap riêng,
quyền truy cập do chính tài khoản/token Grafana quyết định.

Tuỳ chọn thêm:

- `MCP_RATE_LIMIT_REQUESTS`, `MCP_RATE_LIMIT_WINDOW_SECONDS` để chỉnh rate limit theo caller (đây là rate-limit của riêng MCP server, không phải guardrail theo backend).
- Toàn bộ biến khác xem trong `.env.example` (phần "mcp_server/").

Nếu chưa có MongoDB/Loki thật, vẫn có thể chạy server với giá trị giả (server start được, các tool sẽ lỗi ở bước network — phù hợp để test auth/guardrail, không phải test data thật).

## 4. Kiểm tra nhanh bằng curl

**PowerShell** (gọi `curl.exe` thẳng để tránh bị alias `Invoke-WebRequest` của PowerShell nuốt mất các flag):

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:8000/mcp -X POST -H "Content-Type: application/json" -d '{}'
# kỳ vọng: 401 (không có Authorization header)
```

**Git Bash / Linux:**

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/mcp -X POST -H "Content-Type: application/json" -d '{}'
```

## 5. Test bằng script CLI có sẵn

[mcp_server/scripts/manual_test_client.py](../mcp_server/scripts/manual_test_client.py)
nhận tham số dạng **`key=value`** (không phải JSON inline) — để tránh đúng lỗi
quote JSON mà PowerShell/cmd.exe hay gặp khi double-quote bị nuốt mất:

```powershell
$env:MCP_SERVER_URL="http://127.0.0.1:8000/mcp"
$env:MCP_TEST_BEARER_KEY="PqTUmPNKxrVn2g3EJslOdeUorNcntST5"

# Liệt kê tool
python mcp_server/scripts/manual_test_client.py list

# Gọi 1 tool — dùng key=value, script tự cast số/bool, giữ nguyên string cho LogQL
python mcp_server/scripts/manual_test_client.py call mongo_find database=authorization collection=IDENTITY limit=5
python mcp_server/scripts/manual_test_client.py call grafana_list_datasources
python mcp_server/scripts/manual_test_client.py call grafana_query datasource_uid=prometheus promql_query=rabbitmq_queue_messages
python mcp_server/scripts/manual_test_client.py call loki_query_range datasource_uid=loki service_name=iot-core-authentication-authorization start=1782700000 end=1782703600 limit=20
```

`datasource_uid` (`prometheus`, `loki`...) lấy được từ `grafana_list_datasources`.
`loki_query_range` tự build LogQL selector từ `namespace` (mặc định lấy từ
`DEFAULT_LOKI_NAMESPACE`, public template dùng `iot-platform`)

- `service_name` cho tiện dùng (không phải LogQL thô) — nhưng đây chỉ là tiện
  ích, **không phải guardrail bảo mật**: tool này không còn allowlist label hay
  rate-limit riêng nữa (theo quyết định: guardrail tự build chỉ áp dụng cho Mongo).

Nếu tool cần tham số lồng nhau (object/dict, ví dụ `query`/`projection` của
`mongo_find` dạng filter Mongo thật), ghi JSON ra file rồi truyền bằng `@`:

```powershell
'{"database":"authorization","collection":"IDENTITY","query":{"_id":"some-device-id"},"limit":5}' | Out-File -Encoding utf8 args.json
python mcp_server/scripts/manual_test_client.py call mongo_find @args.json
```

(Cú pháp JSON inline `'{"database": ...}'` truyền trực tiếp trên command line
**không còn được hỗ trợ/khuyến nghị** vì PowerShell và cmd.exe đều có thể làm
mất dấu `"` khi forward argument cho `python.exe` — luôn dùng `key=value` hoặc
`@file.json`.)

## 6. Test bằng MCP Inspector (UI click trực quan)

`npx` chỉ có sẵn trong **Git Bash** (do nvm setup PATH ở đó), thường **không**
có trong PowerShell. Chọn 1 trong 2 cách:

**Cách A (đơn giản nhất) — mở 1 cửa sổ Git Bash riêng**, giữ server PowerShell
ở bước 3 vẫn chạy, rồi trong Git Bash:

```bash
npx -y @modelcontextprotocol/inspector
```

**Cách B — chạy ngay trong PowerShell** bằng cách thêm thư mục nvm vào PATH
cho session hiện tại trước (chỉ cần làm 1 lần mỗi session PowerShell):

```powershell
$env:PATH += ";C:\Users\dangn\AppData\Roaming\nvm\v26.1.0"
npx -y @modelcontextprotocol/inspector
```

Inspector tự mở browser tại `http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=...`
(hoặc copy link từ log dán vào browser).

Trong Inspector:

1. **Transport Type**: `Streamable HTTP`
2. **URL**: `http://127.0.0.1:8000/mcp`
3. **Headers**: thêm `Authorization` = `Bearer <RAW_KEY>`
4. Bấm **Connect** → thấy danh sách tool: `mongo_find`, `mongo_list_collections`,
   `mongo_collection_stats`, `mongo_list_databases` (luôn có), và
   `grafana_list_datasources`, `grafana_query`, `grafana_query_range`,
   `loki_query_range` (nếu đã bật `MCP_ENABLE_GRAFANA_TOOLS=true`).
5. Click vào 1 tool, điền tham số, bấm **Run Tool** để xem kết quả/lỗi trực tiếp.

## 7. Các tình huống nên thử

| Thử                                                       | Cách                                                           | Kỳ vọng                                                                                                          |
| --------------------------------------------------------- | -------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Không có Authorization header                             | curl không header, hoặc bỏ Header trong Inspector              | `401`                                                                                                            |
| Bearer key sai                                            | Đổi 1 ký tự trong `RAW_KEY`                                    | `401`                                                                                                            |
| `mongo_find` với namespace ngoài allowlist                | `call mongo_find database=some_db collection=SECRET`           | Lỗi bị chặn trước khi chạm Mongo (hoặc lỗi kết nối nếu Mongo giả) — **guardrail Mongo vẫn áp dụng**              |
| `grafana_query`/`loki_query_range` với query/metric tuỳ ý | `call grafana_query datasource_uid=prometheus promql_query=up` | Chạy thẳng, **không bị chặn** — không có allowlist cho nhóm này, quyền do Grafana user/token quyết định          |
| Gọi liên tục vượt `MCP_RATE_LIMIT_REQUESTS`               | Set biến này = `2`, gọi 3 lần liên tiếp                        | Lần thứ 3 trả `429` kèm `retry_after` (đây là rate-limit của MCP server, áp dụng cho mọi tool)                   |
| Bật Loki/Grafana                                          | `MCP_ENABLE_GRAFANA_TOOLS=true` + cấu hình `GRAFANA_*`         | Thấy thêm `grafana_list_datasources`, `grafana_query`, `grafana_query_range`, `loki_query_range` trong list tool |

## 8. Dừng server / dọn dẹp

- Foreground: `Ctrl+C` trong terminal đang chạy `python mcp_server/server.py`.
- Background (nếu chạy bằng `nohup ... &`): tìm PID bằng `ps aux | grep server.py` rồi `kill <PID>`; trên Windows nếu PID bash không khớp PID thật, dùng `netstat -ano | grep <port>` để tìm đúng PID rồi `taskkill //PID <pid> //F`.
- MCP Inspector: đóng terminal hoặc `Ctrl+C`; nếu vẫn còn process nghe cổng `6274`, dùng cách tìm PID/`taskkill` như trên.
