# MCP Server — Deployment Guide

`mcp_server/` là **1 service hoàn toàn độc lập** với app Flask (`iot-ops-agent`)
nằm trong phần còn lại của repo này — khác process, khác env, khác deploy
target, và (kể từ khi tách) **không import bất kỳ thứ gì ngoài thư mục
`mcp_server/`**. Repo này chỉ là nơi chứa source code chung; khi build/deploy,
hãy coi `mcp_server/` như 1 dự án riêng biệt.

Nếu bạn muốn hiểu API surface (tool nào, tham số gì) để tích hợp agent ngoài,
xem [MCP_SERVER_INTEGRATION.md](MCP_SERVER_INTEGRATION.md). Nếu bạn muốn chạy
thử local để dev/test, xem [MCP_SERVER_USAGE.md](MCP_SERVER_USAGE.md).

## Vì sao tách độc lập

`mcp_server/` là ranh giới trust duy nhất giữ credential thật
(`COMPANY_MONGODB_URI`, `GRAFANA_URL`/`GRAFANA_USERNAME`/`GRAFANA_PASSWORD`).
Agent/hệ thống ngoài chỉ cần biết `MCP_SERVER_URL` + 1 bearer key — không bao
giờ chạm credential thật, không cần biết gì về app Flask chính. Vì vậy:

- `mcp_server/services/company_mongo_proxy.py` là **bản copy riêng**
  (vendored) của `services/company_mongo_proxy.py` ở repo root — cố ý trùng
  lặp code thay vì import chéo, để build/deploy `mcp_server/` không phụ thuộc
  cấu trúc thư mục của phần còn lại trong repo. Nếu sau này sửa guardrail
  (allowlist, blocked operators...) ở bản gốc, **phải tự đồng bộ thủ công**
  sang bản trong `mcp_server/`.
- `mcp_server/requirements.txt` độc lập với `requirements.txt` của app Flask.
- Build Docker dùng **`mcp_server/` làm build context**, không phải repo root.

## 1. Build & chạy bằng Docker (khuyến nghị cho production)

```bash
# Build context la mcp_server/, KHONG phai repo root
docker build -t iot-ops-mcp-server mcp_server/

docker run -p 8000:8000 \
  -e COMPANY_MONGODB_URI="mongodb://readonly_user:PASSWORD@company-mongo-host:27017/?authSource=admin&directConnection=true" \
  -e MCP_API_KEYS_JSON='{"caller-id":"sha256_hash_cua_key"}' \
  -e MCP_ENABLE_GRAFANA_TOOLS="true" \
  -e GRAFANA_URL="https://your-grafana-host" \
  -e GRAFANA_USERNAME="readonly_user" \
  -e GRAFANA_PASSWORD="..." \
  iot-ops-mcp-server
```

Hoặc dùng `--env-file` thay vì liệt kê từng `-e`:

```bash
docker run -p 8000:8000 --env-file mcp_server/.env iot-ops-mcp-server
```

`docker build -f mcp_server/Dockerfile -t iot-ops-mcp-server .` (build context
là repo root) **sẽ lỗi** — Dockerfile hiện tại giả định context là chính
`mcp_server/`, xem comment đầu [mcp_server/Dockerfile](../mcp_server/Dockerfile).

## 2. Deploy lên platform (Render, Railway, Fly.io, VPS riêng...)

Vì độc lập, `mcp_server/` nên là **1 service riêng** trên platform deploy của
bạn, không cùng service với app Flask:

1. Root/build directory: `mcp_server/`.
2. Build command: `pip install -r requirements.txt` (chạy trong `mcp_server/`,
   không cần `-r mcp_server/requirements.txt` nữa vì đã ở trong thư mục đó).
3. Start command: `python server.py`.
4. Set toàn bộ env var cần thiết **chỉ trên service này** — xem bảng đầy đủ ở
   [MCP_SERVER_INTEGRATION.md mục 7](MCP_SERVER_INTEGRATION.md#7-env-vars-server-cần-để-team-deploy-biết-cấu-hình-không-đưa-cho-agent-ngoài).
5. Platform tự cấp HTTPS — agent ngoài chỉ cần `https://<service-url>/mcp` +
   bearer key của họ.

## 3. Mạng nội bộ — yêu cầu kết nối được tới MongoDB/Grafana công ty

Vì server cần `COMPANY_MONGODB_URI` reachable thật (không phải mock), nơi
chạy `mcp_server/` (Docker host, VM, hay platform service) phải có đường
mạng tới:

- MongoDB công ty — nếu connection string trỏ tới 1 replica-set có member
  advertise IP nội bộ (vd `192.168.x.x`) không reachable từ ngoài, hoặc thêm
  `directConnection=true` (nếu seed host là 1 member duy nhất expose qua
  IP public/NAT), hoặc deploy `mcp_server/` ngay trong mạng nội bộ đó/qua VPN.
- Grafana instance (nếu bật `MCP_ENABLE_GRAFANA_TOOLS=true`).

Không có cách nào để MCP server "giả lập" kết nối này — nếu host chạy server
không tới được Mongo/Grafana thật, mọi tool gọi vào sẽ trả lỗi timeout (tool
error, không phải crash server).

## 4. Rotate bearer key / thêm caller mới

1. Tạo key mới (xem [MCP_SERVER_USAGE.md mục 2](MCP_SERVER_USAGE.md#2-tạo-bearer-key-cho-client)).
2. Thêm `"caller_id": "hash_moi"` vào `MCP_API_KEYS_JSON`, deploy lại service.
3. Gửi `RAW_KEY` mới cho caller qua kênh riêng (không qua MCP/log).
4. Xoá caller cũ khỏi `MCP_API_KEYS_JSON` khi không còn dùng — key bị xoá lập
   tức bị từ chối ở [`mcp_server/auth.py`](../mcp_server/auth.py), không cần
   restart gì thêm ngoài việc deploy lại với JSON mới.

## 5. Checklist trước khi cho agent ngoài dùng thật

- [ ] `COMPANY_MONGODB_URI` trỏ đúng tài khoản **read-only** (không
      `readWrite`/`dbAdmin`).
- [ ] Đã test `mongo_find` với 1 namespace trong allowlist trả về data thật.
- [ ] Đã test gọi không có `Authorization` header → nhận `401`.
- [ ] Đã test vượt `MCP_RATE_LIMIT_REQUESTS` → nhận `429` kèm `retry_after`.
- [ ] (Nếu bật Grafana) đã test `grafana_list_datasources` trả đúng danh sách
      thật, `structuredContent` khác `null`.
- [ ] Đã gửi `MCP_SERVER_URL` + bearer key riêng cho agent ngoài qua kênh an
      toàn (không qua email/chat không mã hoá).
