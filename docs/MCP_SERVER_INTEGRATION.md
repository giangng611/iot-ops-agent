# MCP Server — Integration Reference

Tài liệu này dành cho **agent/hệ thống bên ngoài** muốn tích hợp với
`mcp_server/` qua giao thức MCP (Model Context Protocol). Nếu bạn muốn tự
chạy/test server trên máy mình, xem [MCP_SERVER_USAGE.md](MCP_SERVER_USAGE.md).
Nếu bạn deploy server lên hạ tầng, xem [MCP_SERVER_DEPLOYMENT.md](MCP_SERVER_DEPLOYMENT.md).
Để build Docker image, xem [mcp_server/Dockerfile](../mcp_server/Dockerfile).

## 1. Tổng quan kiến trúc

```
Agent/hệ thống ngoài  --Bearer key MCP-->  MCP Server (HTTPS public)
                                              ├─ mongo_tools    -> CompanyMongoReadProxy -> MongoDB công ty
                                              ├─ loki_tools     -> grafana-client          -> Grafana Loki (log)
                                              └─ grafana_tools  -> grafana-client          -> Grafana/Prometheus (metric)
```

- Credential thật (`COMPANY_MONGODB_URI`, `GRAFANA_URL`/`GRAFANA_USERNAME`/`GRAFANA_PASSWORD`
  hoặc `GRAFANA_API_KEY`) **chỉ tồn tại trong env của MCP server**, không bao
  giờ đi qua giao thức MCP. Agent ngoài chỉ cần biết `MCP_SERVER_URL` + 1
  bearer key riêng.
- **Guardrail tự build (allowlist namespace, chặn operator nguy hiểm, rate
  limit riêng) chỉ áp dụng cho nhóm tool Mongo.** Nhóm Loki/Grafana/Prometheus
  gọi trực tiếp qua thư viện [`grafana-client`](https://github.com/grafana-toolbox/grafana-client),
  không có allowlist/cap riêng — quyền truy cập do chính tài khoản/token
  Grafana cấu hình trên server quyết định.
- Transport: **Streamable HTTP** (không phải stdio) — bắt buộc vì server chạy
  như 1 service public, không phải subprocess local.

## 2. Kết nối

```
URL:        https://<your-mcp-server-host>/mcp
Transport:  Streamable HTTP
Header:     Authorization: Bearer <RAW_KEY>
```

Mọi request thiếu hoặc sai `Authorization` header bị chặn ở
[`mcp_server/auth.py`](../mcp_server/auth.py) với HTTP 401, **trước khi chạm**
Mongo/Loki/Grafana — không tool nào được dispatch nếu auth fail.

### Ví dụ client (Python, `mcp` SDK)

```python
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    url = "https://<your-mcp-server-host>/mcp"
    headers = {"Authorization": "Bearer <RAW_KEY>"}

    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print([t.name for t in tools.tools])

            result = await session.call_tool(
                "mongo_find",
                {"database": "authorization", "collection": "IDENTITY", "query": {"_id": "some-device-id"}, "limit": 5},
            )
            # Prefer structuredContent: it's only populated when the
            # server-side tool declares a concrete generic return type
            # (eg. list[dict[str, Any]]) -- see "Đọc kết quả tool" below.
            print(result.structuredContent)

asyncio.run(main())
```

Một client CLI tham khảo, không cần SDK riêng để tự viết từ đầu, có sẵn tại
[`mcp_server/scripts/manual_test_client.py`](../mcp_server/scripts/manual_test_client.py).

## 3. Auth, rate limit, lỗi chuẩn

| Tình huống | HTTP | Body |
|---|---|---|
| Thiếu/sai `Authorization` header | 401 | `{"error": "..."}`|
| Vượt rate limit (theo `caller_id`, cấu hình `MCP_RATE_LIMIT_REQUESTS`/`MCP_RATE_LIMIT_WINDOW_SECONDS`, mặc định 60 req / 60s) | 429 | `{"error": "...", "retry_after": <seconds>}` |
| Tool lỗi (namespace Mongo ngoài allowlist, Mongo/Grafana không reachable, operator bị chặn, v.v.) | 200 (MCP-level) | `CallToolResult.isError = true`, nội dung lỗi nằm trong `result.content` |

`caller_id` được map 1-1 với bearer key qua `MCP_API_KEYS_JSON` (server chỉ
lưu SHA-256 hash, không lưu raw key) — mỗi caller/agent ngoài nên có 1 key
riêng để rate-limit và audit log tách biệt theo từng bên.

## 4. Đọc kết quả tool (quan trọng)

`CallToolResult` có 2 cách lấy dữ liệu:

- `result.content` — danh sách content block (luôn có, dạng text/JSON string).
- `result.structuredContent` — dict đã được validate theo schema, **chỉ được
  điền khi tool có kiểu trả về generic cụ thể** (`list[dict[str, Any]]`,
  `dict[str, Any]`, `list[str]`...). Với kiểu trả về bare (`list`, `dict`
  không tham số), MCP SDK (FastMCP) **không** tạo schema nên
  `structuredContent` sẽ là `None`.

**Khuyến nghị: luôn ưu tiên đọc `result.structuredContent` nếu nó khác
`None`.** Một số SDK còn bọc giá trị non-object (như `list`) dưới key
`"result"` (`{"result": [...]}`) — kiểm tra `structuredContent.keys() ==
{"result"}` và unwrap nếu cần. Toàn bộ tool Mongo trong server này
(`mongo_find`, `mongo_list_collections`, `mongo_collection_stats`,
`mongo_list_databases`) đã khai báo kiểu trả về cụ thể nên luôn có
`structuredContent` đáng tin cậy. Nếu bạn thấy tool nào trả `dict`/`list`
"trần" (không tham số generic) trong code, `structuredContent` cho tool đó
có thể là `None` — khi đó phải tự parse `result.content[0].text` (JSON
string) thay thế. Tham khảo cách xử lý cả 2 trường hợp tại
[`mcp_server/scripts/_debug_common.py`](../mcp_server/scripts/_debug_common.py)
hàm `call_tool()`.

## 5. Tool catalog

### 5.1. Mongo (luôn bật, có guardrail)

| Tool | Tham số | Trả về |
|---|---|---|
| `mongo_find` | `database: str`, `collection: str`, `query: dict?`, `projection: dict?`, `sort_field: str?`, `sort_direction: int?`, `limit: int = 100` | `list[dict[str, Any]]` |
| `mongo_list_collections` | `database: str` | `list[str]` |
| `mongo_collection_stats` | `database: str`, `collection: str` | `dict[str, Any]` |
| `mongo_list_databases` | *(không có)* | `list[str]` |

Guardrail (xem [`services/company_mongo_proxy.py`](../services/company_mongo_proxy.py)):

- **Allowlist namespace** (`database.collection`) — mặc định
  (`DEFAULT_ALLOWED_NAMESPACES`), override bằng env `COMPANY_MONGO_ALLOWED_NAMESPACES`
  (CSV). Truy vấn ngoài allowlist bị chặn trước khi chạm Mongo thật.
- **Chặn operator nguy hiểm** (`BLOCKED_QUERY_OPERATORS`, gồm `$regex`,
  `$where`, ...) trong `query`/`projection` — luôn dùng exact-match, không
  dùng partial/regex match.
- **Cap `limit`** ở `MAX_QUERY_LIMIT` (1000) dù caller truyền lớn hơn.
- **Rate limit riêng** theo `COMPANY_MONGO_PROXY_RATE_LIMIT_REQUESTS`/`_WINDOW_SECONDS`
  (mặc định 120 req / 60s) — độc lập với rate limit theo `caller_id` ở tầng
  MCP auth.
- **Audit log** mỗi lần đọc (database, collection, query, effective limit)
  ra stdout server dưới dạng JSON có cấu trúc.

`mongo_find` trả lỗi (tool error, không phải exception ngầm) khi: namespace
ngoài allowlist, operator bị chặn, hoặc Mongo không reachable. **Một lỗi kết
nối Mongo KHÔNG đồng nghĩa "resource không tồn tại"** — luôn phân biệt rõ 2
trường hợp này ở phía client (xem pattern tri-state `found`/`empty`/`error`
trong `_debug_common.py::mongo_find`).

### 5.2. Loki — log (tuỳ chọn, bật bằng `MCP_ENABLE_GRAFANA_TOOLS=true`)

| Tool | Tham số | Trả về |
|---|---|---|
| `loki_query_range` | `datasource_uid: str`, `start: int`, `end: int`, `service_name: str?`, `namespace: str = "one-iot"`, `contains: str?`, `limit: int = 100` | `dict` (raw Grafana/Loki response) |

- `datasource_uid` lấy qua `grafana_list_datasources` (không còn id cố định).
- `service_name`/`namespace` chỉ là tiện ích tự build LogQL selector
  (`{k8s_namespace_name="...", service_name="..."}`), **không phải
  guardrail** — không có allowlist label.
- `contains` thêm LogQL line filter (`|= "..."`). Bỏ `service_name` + dùng
  `contains` để tìm 1 chuỗi (vd `trace_id`) xuyên suốt **toàn bộ namespace**,
  không giới hạn theo service — hữu ích để follow 1 request qua nhiều service
  mà không cần biết trước nó được route tới đâu (xem
  `_debug_common.py::auto_trace_from_matches`).
- `start`/`end` là Unix timestamp giây.

### 5.3. Grafana/Prometheus — metric (tuỳ chọn, cùng flag `MCP_ENABLE_GRAFANA_TOOLS`)

| Tool | Tham số | Trả về |
|---|---|---|
| `grafana_list_datasources` | *(không có)* | `list` — `[{id, uid, name, type}, ...]` |
| `grafana_query` | `datasource_uid: str`, `promql_query: str` | `dict` — instant query |
| `grafana_query_range` | `datasource_uid: str`, `promql_query: str`, `start: int`, `end: int`, `step: int = 60` | `dict` — range query |

Không có allowlist metric/label riêng — quyền truy cập hoàn toàn do tài
khoản/token Grafana cấu hình trên server (`GRAFANA_USERNAME`/`GRAFANA_PASSWORD`
hoặc `GRAFANA_API_KEY`) quyết định.

Cả 4 tool Loki/Grafana ở trên đều đã khai báo kiểu trả về generic cụ thể
(`list[dict[str, Any]]`/`dict[str, Any]`), giống nhóm Mongo ở mục 5.1, nên
`structuredContent` luôn được điền đáng tin cậy — không cần fallback parse
`result.content` cho các tool này.

## 6. Ví dụ kịch bản tích hợp thực tế

Repo này có sẵn các script tự động hoá theo runbook vận hành công ty (đọc
[`resources/kich_ban_van_hanh_iot_platform_cho_ai_agent.md`](../resources/kich_ban_van_hanh_iot_platform_cho_ai_agent.md)),
toàn bộ chỉ gọi qua MCP tool ở trên — dùng làm ví dụ end-to-end:

- [`mcp_server/scripts/debug_device_command_flow.py`](../mcp_server/scripts/debug_device_command_flow.py) — debug luồng gửi lệnh xuống thiết bị.
- [`mcp_server/scripts/debug_telemetry_flow.py`](../mcp_server/scripts/debug_telemetry_flow.py) — debug luồng telemetry từ thiết bị gửi lên.
- [`mcp_server/scripts/check_device_status.py`](../mcp_server/scripts/check_device_status.py) — kiểm tra tổng quát 1 thiết bị đã lên hệ thống chưa.

## 7. Env vars server cần (để team deploy biết cấu hình, KHÔNG đưa cho agent ngoài)

| Var | Bắt buộc | Mô tả |
|---|---|---|
| `COMPANY_MONGODB_URI` | có | Connection string Mongo công ty (read-only account). Nếu seed host là 1 replica-set member duy nhất expose qua IP public/NAT còn các member khác chỉ advertise IP nội bộ, thêm `&directConnection=true`. |
| `COMPANY_MONGO_ALLOWED_NAMESPACES` | không | CSV `db.collection`, override allowlist mặc định. |
| `MCP_API_KEYS_JSON` | có | JSON `{"caller_id": "sha256_hash_of_key"}`. |
| `MCP_RATE_LIMIT_REQUESTS` / `MCP_RATE_LIMIT_WINDOW_SECONDS` | không | Rate limit theo caller ở tầng MCP auth (mặc định 60/60s). |
| `MCP_ENABLE_GRAFANA_TOOLS` | không | `"true"` để bật nhóm tool Loki/Grafana. |
| `GRAFANA_URL` | nếu bật Grafana | Base URL Grafana instance. |
| `GRAFANA_USERNAME` + `GRAFANA_PASSWORD` hoặc `GRAFANA_API_KEY` | nếu bật Grafana | Credential Grafana. |
| `PORT` | không | Cổng HTTP server lắng nghe (mặc định 8000). |

Chi tiết đầy đủ + cách tạo bearer key: [MCP_SERVER_USAGE.md](MCP_SERVER_USAGE.md).
Hướng dẫn deploy production: [MCP_SERVER_DEPLOYMENT.md](MCP_SERVER_DEPLOYMENT.md).
