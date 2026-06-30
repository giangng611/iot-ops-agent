import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = "/Users/giangnguyendohoang/Desktop/PycharmProjects/iot-ops-agent/outputs/security_roadmap_sheet";
const outputPath = path.join(outputDir, "roadmap_ket_noi_bao_mat_backend_db.xlsx");
const repoRoot = "/Users/giangnguyendohoang/Desktop/PycharmProjects/iot-ops-agent";

const workbook = Workbook.create();

function addSheet(name) {
  const sheet = workbook.worksheets.add(name);
  return sheet;
}

function setValues(sheet, range, values) {
  sheet.getRange(range).values = values;
}

function styleTitle(range) {
  range.format.fill.color = "#183A37";
  range.format.font.color = "#FFFFFF";
  range.format.font.bold = true;
  range.format.font.size = 16;
}

function styleHeader(range) {
  range.format.fill.color = "#245C4F";
  range.format.font.color = "#FFFFFF";
  range.format.font.bold = true;
  range.format.wrapText = true;
}

function styleSubHeader(range) {
  range.format.fill.color = "#DCEBE7";
  range.format.font.bold = true;
  range.format.wrapText = true;
}

function styleBody(range) {
  range.format.wrapText = true;
  range.format.verticalAlignment = "Top";
}

function setWidths(sheet, widths) {
  widths.forEach((width, index) => {
    sheet.getRange(`${columnName(index + 1)}:${columnName(index + 1)}`).format.columnWidthPx = width;
  });
}

function columnName(n) {
  let s = "";
  while (n > 0) {
    const m = (n - 1) % 26;
    s = String.fromCharCode(65 + m) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
}

function categoryForTest(file, method) {
  if (file.includes("company_mongo_proxy")) return "Proxy đọc Company MongoDB";
  if (file.includes("company_mongodb_security")) return "Bảo mật Company MongoDB";
  if (file.includes("mongodb_permissions")) return "Phân quyền MongoDB runtime";
  if (file.includes("company_postgres_security")) return "Guardrail Company Postgres";
  if (file.includes("langgraph_policy")) return "Chính sách agent và công cụ DB";
  if (file.includes("ioa_v3_workflow")) return "Luồng IOA v3 và bằng chứng";
  if (method.includes("telegram")) return "Bảo mật và tích hợp Telegram";
  if (method.includes("mongo")) return "API MongoDB trong ứng dụng";
  if (method.includes("postgres") || method.includes("supabase") || method.includes("storage")) return "Guardrail tầng lưu trữ";
  if (method.includes("company")) return "Nguồn dữ liệu công ty";
  if (method.includes("prompt") || method.includes("chat")) return "Quyền sở hữu dữ liệu người dùng";
  if (method.includes("rate_limit") || method.includes("injection") || method.includes("sensitive")) return "Bảo mật ứng dụng";
  return "Regression ứng dụng";
}

function vietnameseTitle(method, category) {
  const exact = {
    test_sliding_window_rate_limiter_rejects_excess_reads: "Chặn truy vấn vượt giới hạn theo cửa sổ thời gian",
    test_rate_limit_environment_is_read_at_request_time: "Đọc cấu hình rate limit tại thời điểm request",
    test_find_applies_timeout_sort_and_hard_limit: "Áp timeout, sort hợp lệ và giới hạn cứng cho lệnh find",
    test_find_rejects_server_side_javascript_operator: "Chặn toán tử JavaScript phía server trong truy vấn MongoDB",
    test_find_rejects_expensive_query_operators: "Chặn các toán tử truy vấn tốn tài nguyên",
    test_find_rejects_invalid_namespace_sort_and_limit: "Chặn namespace, sort và limit không hợp lệ",
    test_rate_limits_are_isolated_by_actor: "Tách rate limit theo từng actor",
    test_proxy_rejects_namespaces_outside_allowlist: "Chặn namespace nằm ngoài allowlist",
    test_discovery_only_returns_allowlisted_namespaces: "Discovery chỉ trả về namespace được phép",
    test_namespace_allowlist_can_be_configured: "Cho phép cấu hình namespace allowlist",
    test_accepts_database_scoped_read_only_privileges: "Chấp nhận quyền đọc chỉ trong phạm vi database được duyệt",
    test_rejects_read_any_database_and_write_actions: "Từ chối quyền readAnyDatabase và quyền ghi/admin",
    test_accepts_authenticated_collection_scoped_runtime_actions: "Chấp nhận runtime credential đã xác thực và chỉ có quyền trên collection cần thiết",
    test_rejects_anonymous_or_overprivileged_connections: "Từ chối kết nối anonymous hoặc overprivileged",
    test_read_only_guardrails_are_applied_with_parameterized_timeout: "Áp transaction read-only và timeout dạng parameterized",
    test_postgres_preview_rejects_identifier_injection_before_connecting: "Chặn identifier injection trước khi mở kết nối DB",
  };
  if (exact[method]) return exact[method];

  if (method.includes("reject")) return `Từ chối trường hợp không an toàn trong ${category}`;
  if (method.includes("denied") || method.includes("blocks")) return `Chặn truy cập không được phép trong ${category}`;
  if (method.includes("fallback")) return `Kiểm tra fallback an toàn trong ${category}`;
  if (method.includes("source")) return `Kiểm soát nguồn dữ liệu trong ${category}`;
  if (method.includes("evidence")) return `Kiểm tra bằng chứng trong ${category}`;
  if (method.includes("telegram")) return `Kiểm tra luồng Telegram trong ${category}`;
  if (method.includes("company")) return `Kiểm tra luồng dữ liệu công ty trong ${category}`;
  if (method.includes("storage")) return `Kiểm tra trạng thái lưu trữ trong ${category}`;
  if (method.includes("prompt")) return `Kiểm tra prompt trong ${category}`;
  if (method.includes("chat")) return `Kiểm tra chat trong ${category}`;
  if (method.includes("timeout")) return `Kiểm tra timeout trong ${category}`;
  if (method.includes("rate_limit")) return `Kiểm tra rate limit trong ${category}`;
  return `Kiểm tra tự động trong ${category}`;
}

function expectedForTest(method, category) {
  if (method.includes("reject") || method.includes("denied") || method.includes("blocks") || method.includes("disallow")) {
    return "Hệ thống từ chối request không an toàn hoặc không được phép trước khi request chạm tới thao tác DB nhạy cảm.";
  }
  if (method.includes("rate_limit")) {
    return "Request lặp lại bị giới hạn theo actor/cửa sổ thời gian và trả về phản hồi rate limit có kiểm soát.";
  }
  if (method.includes("timeout") || method.includes("hard_limit") || method.includes("clamp")) {
    return "Truy cập DB có giới hạn số bản ghi/timeout rõ ràng, không cho phép đọc dữ liệu không giới hạn.";
  }
  if (method.includes("fallback")) {
    return "Khi lỗi xảy ra, hệ thống chỉ fallback sang nguồn đã được duyệt và thể hiện trạng thái an toàn, rõ ràng.";
  }
  if (method.includes("expose")) {
    return "Response và log không lộ credential, hostname nội bộ, connection string hoặc chi tiết exception thô từ DB.";
  }
  if (method.includes("source")) {
    return "Nguồn dữ liệu đã chọn được áp dụng nhất quán và không bị tự ý nâng quyền sang nguồn dữ liệu khác.";
  }
  if (method.includes("owner") || method.includes("cross_user")) {
    return "Người dùng chỉ truy cập được dữ liệu của chính mình; thao tác đọc/sửa/xóa chéo user bị từ chối.";
  }
  if (method.includes("permission") || method.includes("privilege")) {
    return "Quyền MongoDB khớp với allowlist least privilege; kết nối anonymous hoặc quyền quá rộng bị từ chối.";
  }
  if (method.includes("injection")) {
    return "Payload injection bị xem như dữ liệu thường hoặc bị validation chặn; không có lệnh DB phá hoại nào được thực thi.";
  }
  if (category.includes("MongoDB")) {
    return "Truy cập MongoDB tuân thủ guardrail: có xác thực, đúng phạm vi, có giới hạn và read-only khi yêu cầu.";
  }
  return "Hành vi hiện tại khớp với contract bảo mật/backend mà automated test đang kiểm chứng.";
}

async function collectDetailedTestCases(limit = 86) {
  const sources = [
    "tests/test_company_mongo_proxy.py",
    "tests/test_company_mongodb_security.py",
    "tests/test_mongodb_permissions.py",
    "tests/test_company_postgres_security.py",
    "tests/test_langgraph_policy.py",
    "tests/test_ioa_v3_workflow.py",
    "tests/test_security_and_realtime.py",
  ];
  const excludedMethods = new Set([
    "test_telegram_command_payload_contains_supported_commands",
    "test_telegram_commands_map_to_agent_prompts",
    "test_telegram_duplicate_update_is_answered_once",
    "test_telegram_message_calls_langgraph_and_saves_history",
  ]);
  const cases = [];

  for (const file of sources) {
    const text = await fs.readFile(path.join(repoRoot, file), "utf8");
    let className = "";
    for (const line of text.split("\n")) {
      const classMatch = line.match(/^class\s+([A-Za-z0-9_]+)\(/);
      if (classMatch) className = classMatch[1];
      const methodMatch = line.match(/^\s+def\s+(test_[A-Za-z0-9_]+)\(/);
      if (!methodMatch) continue;

      const method = methodMatch[1];
      if (excludedMethods.has(method)) continue;

      const moduleName = file.replace(/\//g, ".").replace(/\.py$/, "");
      const category = categoryForTest(file, method);
      const methodTitle = vietnameseTitle(method, category);
      cases.push([
        `TC-MDB-${String(cases.length + 1).padStart(3, "0")}`,
        category,
        methodTitle,
        `Xác minh ${methodTitle.toLowerCase()} theo guardrail bảo mật backend/MongoDB của hệ thống.`,
        "Môi trường test trong repo, phần lớn dùng mock/fake DB client; chỉ dùng live checker khi command evidence ghi rõ.",
        `1. Chạy command ở cột Evidence Command.\n2. Đối chiếu assertion trong ${file}.\n3. Xác nhận request/query/permission được kiểm tra đúng với guardrail kỳ vọng.`,
        `Tên test tự động: ${method}`,
        expectedForTest(method, category),
        "Đạt trong lần chạy local ngày 2026-06-24. Full suite hiện có 4 lỗi expectation cũ của Telegram prompt, không nằm trong 86 case ở tab này.",
        "ĐẠT",
        `python3 -m unittest ${moduleName}.${className}.${method} -v`,
        `${file}; ${className}.${method}`,
      ]);

      if (cases.length >= limit) return cases;
    }
  }

  return cases;
}

const summary = addSheet("01_Tong_quan");
setValues(summary, "A1:H1", [["Roadmap kiểm thử kết nối bảo mật Backend - Database", "", "", "", "", "", "", ""]]);
summary.getRange("A1:H1").merge();
styleTitle(summary.getRange("A1:H1"));
setValues(summary, "A3:H3", [[
  "Nhóm kiểm thử",
  "Mục tiêu",
  "Trạng thái hiện tại",
  "Kết quả / phát hiện chính",
  "Rủi ro còn lại",
  "Tiêu chí pass",
  "Owner đề xuất",
  "Bằng chứng repo",
]]);
styleHeader(summary.getRange("A3:H3"));
const summaryRows = [
  [
    "Tầng proxy Company MongoDB",
    "Đảm bảo mọi truy vấn từ backend/LLM đi qua proxy đọc-only, có allowlist namespace, giới hạn tốc độ, giới hạn số bản ghi và timeout.",
    "PASS ở application-side unit test",
    "Proxy không expose insert/update/delete; chặn $where, $regex, $expr, $near; ép limit tối đa 1000; audit có credentials_redacted=true; discovery chỉ trả namespace được phép.",
    "Rate limit hiện là process-local; triển khai nhiều instance cần gateway/Redis/shared limiter.",
    "Unit test pass; mọi tool đọc company DB dùng CompanyMongoReadProxy; không có generic SQL/Mongo tool cho LLM.",
    "Backend",
    "tests/test_company_mongo_proxy.py; services/company_mongo_proxy.py",
  ],
  [
    "DB fallback và app data",
    "Kiểm tra backend có thể xác định nguồn lưu trữ đang dùng, đọc/ghi telemetry đúng backend, và Supabase/Postgres không mở CRUD trực tiếp cho browser-facing role.",
    "CONDITIONAL PASS",
    "Có script kiểm tra storage status, telemetry read source, telemetry write backend và Supabase RLS. RLS pass khi secure=true, không thiếu bảng và anon/authenticated không có CRUD trực tiếp.",
    "Cần chạy lại trên environment thật trước demo/release vì kết quả phụ thuộc .env và credential hiện hành.",
    "scripts/check_app_storage_status.py trả đúng backend; scripts/check_telemetry_* không lỗi; scripts/check_supabase_rls.py trả secure=true.",
    "Backend / DevOps",
    "scripts/check_app_storage_status.py; scripts/check_telemetry_read_source.py; scripts/check_telemetry_write_backend.py; scripts/check_supabase_rls.py",
  ],
  [
    "Company DB security posture",
    "Xác minh credential công ty least privilege, không anonymous read, không write/admin action và chỉ truy cập namespace đã duyệt.",
    "BLOCKED cho production/sensitive data theo assessment 2026-06-15",
    "Checker phát hiện anonymous_document_access_denied=false và role readAnyDatabase rộng hơn allowlist ứng dụng.",
    "Application proxy không thể thay thế MongoDB authorization/firewall; direct DB connection vẫn là rủi ro nếu hạ tầng chưa khóa.",
    "anonymous_document_access_denied=true; least_privilege=true; không readAnyDatabase; không write/admin action; privilege chỉ nằm trong namespace allowlist.",
    "DBA / Infra",
    "docs/COMPANY_DB_SECURITY_ASSESSMENT.md; scripts/check_company_mongodb_security.py",
  ],
  [
    "Lệnh nhạy cảm / injection",
    "Đảm bảo payload phá hoại hoặc operator tốn tài nguyên bị chặn trước khi tới DB hoặc bị xử lý như dữ liệu thường.",
    "PASS ở automated tests",
    "SQL injection login trả 401; identifier injection raise ValueError trước khi mở connection; MongoDB $where/$regex/$expr/$near bị reject; endpoint tạo index không cho POST.",
    "Cần tiếp tục bổ sung test cho prompt/tool mới nếu mở thêm data source.",
    "Các test security pass; không có destructive command được thực thi trong live company DB.",
    "Backend",
    "docs/SECURITY_TEST_PROOF.md; tests/test_security_and_realtime.py; tests/test_company_postgres_security.py",
  ],
  [
    "Runtime MongoDB cá nhân",
    "Đảm bảo local/app MongoDB có auth, runtime user chỉ có action cần thiết trên collection telemetry.",
    "PASS khi checker trả secure=true",
    "Runtime action kỳ vọng: find, insert, listIndexes, update trên iot_ops_agent.telemetry; anonymous/overprivileged connection bị reject trong test.",
    "Index/admin operation dùng credential riêng, cần giữ tách biệt trong env.",
    "scripts/check_mongodb_permissions.py trả secure=true; không có remove/drop/admin action.",
    "Backend / DevOps",
    "tests/test_mongodb_permissions.py; scripts/check_mongodb_permissions.py",
  ],
];
setValues(summary, `A4:H${3 + summaryRows.length}`, summaryRows);
styleBody(summary.getRange(`A4:H${3 + summaryRows.length}`));
setWidths(summary, [190, 300, 170, 370, 300, 300, 140, 260]);
summary.getRange("A3:H8").format.autofitRows();
summary.freezePanes.freezeRows(3);

const tests = addSheet("02_Checklist_test");
setValues(tests, "A1:J1", [["Checklist kiểm thử chi tiết", "", "", "", "", "", "", "", "", ""]]);
tests.getRange("A1:J1").merge();
styleTitle(tests.getRange("A1:J1"));
setValues(tests, "A3:J3", [[
  "ID",
  "Nhóm",
  "Mục tiêu kiểm thử",
  "Cách test / lệnh chạy",
  "Payload hoặc điều kiện",
  "Kỳ vọng hệ thống",
  "Kết quả hiện tại",
  "Trạng thái",
  "Bằng chứng",
  "Ghi chú roadmap",
]]);
styleHeader(tests.getRange("A3:J3"));
const checklistRows = [
  ["PRX-01", "Proxy Company MongoDB", "Rate limit theo sliding window, tách quota theo actor/operation.", "python3 -m unittest tests.test_company_mongo_proxy -v", "COMPANY_MONGO_PROXY_RATE_LIMIT_REQUESTS=1 hoặc 2; window 10-60 giây.", "Request vượt quota raise CompanyMongoProxyRateLimitError và trả retry_after.", "Unit test xác nhận vượt quota bị chặn; actor khác không bị dùng chung quota.", "PASS", "test_sliding_window_rate_limiter_rejects_excess_reads; test_rate_limits_are_isolated_by_actor", "Nếu scale nhiều instance, chuyển limiter sang gateway/Redis."],
  ["PRX-02", "Proxy Company MongoDB", "Ép timeout, sort hợp lệ và hard limit để tránh query kéo quá nhiều dữ liệu.", "python3 -m unittest tests.test_company_mongo_proxy.CompanyMongoProxyTests.test_find_applies_timeout_sort_and_hard_limit -v", "limit request 5000, sort=(ct,-1).", "effective_limit bị clamp về 1000; max_time_ms > 0; audit ghi requested/effective limit.", "Test pass bằng fake cursor; proxy chỉ trả dữ liệu sau khi áp maxTimeMS và limit.", "PASS", "tests/test_company_mongo_proxy.py", "Giữ MAX_QUERY_LIMIT=1000 trừ khi lead duyệt thay đổi."],
  ["PRX-03", "Proxy Company MongoDB", "Chặn operator nguy hiểm/tốn tài nguyên trước khi request tới MongoDB.", "python3 -m unittest tests.test_company_mongo_proxy -v", "$where, $regex, $expr, $near.", "Raise ValueError, query không được gửi xuống collection.", "Unit test xác nhận các payload bị reject.", "PASS", "test_find_rejects_server_side_javascript_operator; test_find_rejects_expensive_query_operators", "Mở thêm operator nào phải thêm vào allowlist/blocklist có test."],
  ["PRX-04", "Proxy Company MongoDB", "Chặn namespace ngoài allowlist và lọc discovery.", "python3 -m unittest tests.test_company_mongo_proxy -v", "datamgmt.SECRET, admin.system_users; list db có secret/admin.", "PermissionError với namespace ngoài allowlist; list_database_names chỉ trả datamgmt; list_collections chỉ trả collection được phép.", "Unit test pass; allowlist cấu hình qua COMPANY_MONGO_ALLOWED_NAMESPACES.", "PASS", "test_proxy_rejects_namespaces_outside_allowlist; test_discovery_only_returns_allowlisted_namespaces", "Cho demo chỉ bật namespace đã được duyệt."],
  ["PRX-05", "Proxy Company MongoDB", "Đảm bảo proxy không expose method ghi dữ liệu.", "python3 -m unittest tests.test_company_mongo_proxy.CompanyMongoProxyTests.test_find_applies_timeout_sort_and_hard_limit -v", "Kiểm tra hasattr(insert_one/update_one/delete_one).", "Không tồn tại insert_one, update_one, delete_one trên proxy.", "Unit test xác nhận proxy read-only ở interface.", "PASS", "tests/test_company_mongo_proxy.py", "Không thêm aggregate/arbitrary command nếu chưa có review bảo mật."],
  ["FBK-01", "DB fallback/app storage", "Xác định backend dữ liệu ứng dụng và telemetry source runtime.", "python3 scripts/check_app_storage_status.py", ".env hiện hành: APP_DB_BACKEND, fallback flag, telemetry env.", "In JSON storage status và telemetry.source; không leak secret.", "Script có sẵn để chạy live trên env; kết quả phụ thuộc cấu hình.", "CẦN CHẠY THEO ENV", "scripts/check_app_storage_status.py", "Đưa output JSON vào evidence sau mỗi lần demo/release."],
  ["FBK-02", "Telemetry fallback/read", "Kiểm tra API đọc devices/telemetry theo source đang chọn.", "python3 scripts/check_telemetry_read_source.py", "GET /api/devices; GET /api/telemetry/sensor-001 bằng Flask test client có session.", "HTTP < 400; payload trả được dữ liệu hoặc fallback state rõ ràng.", "Script fail nếu API trả lỗi >=400.", "CẦN CHẠY THEO ENV", "scripts/check_telemetry_read_source.py", "Dùng trước demo để chứng minh không silent pretend company data."],
  ["FBK-03", "Telemetry write backend", "Kiểm tra simulator ghi telemetry vào backend đúng cấu hình.", "python3 scripts/check_telemetry_write_backend.py", "Generate telemetry cho DEVICES; so sánh count SQLite/MongoDB trước và sau.", "delta tăng ở backend cấu hình; telemetry_write_backend phản ánh đúng nguồn ghi.", "Script in before/after/delta JSON.", "CẦN CHẠY THEO ENV", "scripts/check_telemetry_write_backend.py", "Có thể attach output vào ticket roadmap."],
  ["FBK-04", "Supabase/Postgres RLS", "Xác minh bảng app data có RLS và browser-facing roles không có CRUD trực tiếp.", "python3 scripts/check_supabase_rls.py", "users, chats, messages, prompts, telegram_identities, telegram_link_codes.", "secure=true; missing_tables=[]; anon/authenticated không có SELECT/INSERT/UPDATE/DELETE trực tiếp.", "Checker exit 1 nếu thiếu bảng hoặc role còn quyền trực tiếp.", "CẦN CHẠY THEO ENV", "scripts/check_supabase_rls.py", "Dùng làm acceptance gate trước khi bật Supabase-only."],
  ["CDB-01", "Company MongoDB security", "Kiểm tra credential công ty có least privilege theo allowlist.", "python3 scripts/check_company_mongodb_security.py", "connectionStatus(showPrivileges=true), allowed namespaces từ proxy.", "least_privilege=true; không readAnyDatabase; không write/admin actions; privilege không áp mọi DB.", "Assessment 2026-06-15 ghi least_privilege=false do readAnyDatabase.", "BLOCKED", "docs/COMPANY_DB_SECURITY_ASSESSMENT.md; scripts/check_company_mongodb_security.py", "Cần DBA đổi role trước production/sensitive data."],
  ["CDB-02", "Company MongoDB security", "Kiểm tra anonymous document read bị từ chối.", "python3 scripts/check_company_mongodb_security.py", "Anonymous client find_one bounded vào namespace được phép.", "anonymous_document_access_denied=true.", "Assessment 2026-06-15 ghi anonymous_document_access_denied=false.", "BLOCKED", "docs/COMPANY_DB_SECURITY_ASSESSMENT.md", "Bắt buộc bật MongoDB authorization + firewall/ACL."],
  ["CDB-03", "Company DB discovery", "Probe schema/preview an toàn, có fallback simulator khi DB không sẵn sàng.", "python -m scripts.probe_company_db --table-limit 20; python -m scripts.probe_company_db --preview datamgmt.CIN --preview-limit 5", "Limit thấp, không print secret/connection string; inspect field paths khi cần.", "Read-only guardrails, timeout, row limits, long text truncation, Mongo maxTimeMS.", "Docs mô tả guardrail và command; cần chạy live theo env.", "CẦN CHẠY THEO ENV", "docs/COMPANY_DB_DISCOVERY.md; scripts/probe_company_db.py", "Không dùng generic DB tool cho LLM."],
  ["SEN-01", "Lệnh nhạy cảm SQL", "SQL injection không bypass login, không phá bảng.", "python3 -m unittest tests.test_security_and_realtime -v", "' OR 1=1; DROP TABLE users; --", "Login 401; payload lưu như text thường; bảng users còn hoạt động.", "Đã ghi trong Security Test Evidence; 86 tests passed tại lần assessment.", "PASS", "docs/SECURITY_TEST_PROOF.md", "Chạy lại full unittest trước release."],
  ["SEN-02", "Company Postgres preview", "Identifier injection bị reject trước khi connect DB.", "python3 -m unittest tests.test_company_postgres_security -v", "public; drop schema public cascade; -- và devices\"; drop table users; --", "Raise ValueError; get_company_connection không được gọi.", "Unit test pass bằng mock connection.", "PASS", "tests/test_company_postgres_security.py", "Giữ validate identifier cho mọi schema/table preview mới."],
  ["SEN-03", "Company Postgres guardrail", "Áp transaction read-only và statement timeout parameterized.", "python3 -m unittest tests.test_company_postgres_security.CompanyPostgresSecurityTests.test_read_only_guardrails_are_applied_with_parameterized_timeout -v", "COMPANY_DB_STATEMENT_TIMEOUT_MS=2500.", "cursor.execute('set transaction read only'); cursor.execute('set local statement_timeout = %s', ('2500',)).", "Unit test pass.", "PASS", "tests/test_company_postgres_security.py; services/company_data_service.py", "Timeout nên là env bắt buộc trên production."],
  ["SEN-04", "MongoDB runtime cá nhân", "Runtime credential chỉ có quyền cần thiết trên iot_ops_agent.telemetry.", "python3 scripts/check_mongodb_permissions.py", "connectionStatus(showPrivileges=true).", "secure=true; authenticated=true; actions chỉ find/insert/listIndexes/update đúng resource.", "Unit test chặn anonymous hoặc remove/wrong resource; live checker cần chạy theo env.", "CẦN CHẠY THEO ENV", "tests/test_mongodb_permissions.py; scripts/check_mongodb_permissions.py", "Admin URI tách riêng cho ensure indexes."],
  ["SEN-05", "Sensitive API routes", "API nhạy cảm yêu cầu authenticated session.", "python3 -m unittest tests.test_security_and_realtime -v", "Routes diagnosis, data-source selection, telemetry, Mongo APIs, storage, chats, prompts, profile usage.", "Unauthenticated request trả 401.", "Đã ghi trong Security Test Evidence.", "PASS", "docs/SECURITY_TEST_PROOF.md", "Mở route mới phải thêm vào danh sách test."],
  ["SEN-06", "Index/admin command", "Người dùng app không được gọi endpoint tạo index.", "python3 -m unittest tests.test_security_and_realtime -v", "POST /api/mongo/telemetry/indexes.", "POST trả 405; index creation chỉ qua script admin riêng.", "Đã harden theo Security Test Evidence.", "PASS", "docs/SECURITY_TEST_PROOF.md", "Không expose admin operation qua Flask route user-facing."],
];
setValues(tests, `A4:J${3 + checklistRows.length}`, checklistRows);
styleBody(tests.getRange(`A4:J${3 + checklistRows.length}`));
setWidths(tests, [78, 160, 280, 310, 300, 330, 300, 120, 280, 280]);
tests.freezePanes.freezeRows(3);
tests.getRange(`A3:J${3 + checklistRows.length}`).format.autofitRows();

const detailed = addSheet("06_86_Test_cases");
setValues(detailed, "A1:L1", [["86 test case bảo mật MongoDB/backend", "", "", "", "", "", "", "", "", "", "", ""]]);
detailed.getRange("A1:L1").merge();
styleTitle(detailed.getRange("A1:L1"));
setValues(detailed, "A2:L2", [[
  "Ghi chú format",
  "Theo format test case detail: ID, nhóm/module, tiêu đề, mô tả, điều kiện tiên quyết, bước kiểm thử, dữ liệu test/payload, kết quả kỳ vọng, kết quả thực tế, trạng thái, command evidence, file/method evidence.",
  "",
  "",
  "",
  "",
  "",
  "",
  "",
  "",
  "",
  "",
]]);
detailed.getRange("A2:L2").merge();
styleSubHeader(detailed.getRange("A2:L2"));
setValues(detailed, "A4:L4", [[
  "Test Case ID",
  "Nhóm / Module",
  "Tiêu đề",
  "Mô tả",
  "Điều kiện tiên quyết",
  "Bước kiểm thử",
  "Dữ liệu test / Payload",
  "Kết quả kỳ vọng",
  "Kết quả thực tế",
  "Trạng thái",
  "Evidence Command",
  "Evidence File / Method",
]]);
styleHeader(detailed.getRange("A4:L4"));
const detailedRows = await collectDetailedTestCases(86);
setValues(detailed, `A5:L${4 + detailedRows.length}`, detailedRows);
styleBody(detailed.getRange(`A5:L${4 + detailedRows.length}`));
setWidths(detailed, [96, 170, 260, 340, 300, 360, 240, 360, 360, 90, 390, 340]);
detailed.freezePanes.freezeRows(4);
detailed.getRange(`A4:L${4 + detailedRows.length}`).format.autofitRows();

const commands = addSheet("03_Lenh_evidence");
setValues(commands, "A1:F1", [["Danh sách lệnh chạy và output cần lưu", "", "", "", "", ""]]);
commands.getRange("A1:F1").merge();
styleTitle(commands.getRange("A1:F1"));
setValues(commands, "A3:F3", [["Ưu tiên", "Lệnh", "Dùng để chứng minh", "Output pass cần thấy", "Khi nào chạy", "Lưu ý an toàn"]]);
styleHeader(commands.getRange("A3:F3"));
const commandRows = [
  ["P0", "python3 scripts/check_company_mongodb_security.py", "Company DB đã khóa anonymous read và credential least privilege.", "least_privilege=true; anonymous_document_access_denied=true; violations=[]", "Sau khi DBA sửa role/authorization/firewall.", "Không in document values; checker chỉ đọc privilege metadata và bounded anonymous denial."],
  ["P0", "python3 scripts/check_supabase_rls.py", "Supabase RLS/app data không mở trực tiếp cho anon/authenticated.", "secure=true; missing_tables=[]", "Trước demo/release hoặc sau migration schema.", "Dùng service/backend credential trong .env, không đưa URL/token vào sheet."],
  ["P0", "python3 -m unittest discover -s tests -v", "Regression tổng cho security, proxy, permission, route auth.", "Toàn bộ test pass.", "Trước merge/release.", "Không chạy destructive DB operation."],
  ["P1", "python3 scripts/check_app_storage_status.py", "Backend đang dùng storage/fallback nào.", "JSON có trạng thái relational backend và telemetry.source.", "Khi đổi APP_DB_BACKEND hoặc fallback flag.", "Kiểm tra output không chứa secret."],
  ["P1", "python3 scripts/check_telemetry_read_source.py", "API đọc telemetry/devices hoạt động với source hiện hành.", "GET /api/devices và /api/telemetry/sensor-001 trả status < 400.", "Trước demo UI/chat.", "Script tạo/check user test local."],
  ["P1", "python3 scripts/check_telemetry_write_backend.py", "Simulator ghi telemetry vào backend đúng cấu hình.", "delta tăng ở backend kỳ vọng.", "Sau khi đổi telemetry write backend.", "Dữ liệu test nên chạy ở env dev/staging."],
  ["P1", "python3 scripts/check_mongodb_permissions.py", "MongoDB runtime cá nhân không anonymous/overprivileged.", "secure=true; authenticated=true; granted_actions đúng allowlist.", "Sau khi rotate MongoDB runtime credential.", "Credential admin cho index phải tách khỏi runtime URI."],
  ["P2", "python -m scripts.probe_company_db --table-limit 20", "Company DB discovery an toàn hoặc simulator fallback rõ ràng.", "Schema/probe snapshot có giới hạn, không lỗi.", "Khi mapping thêm bảng/collection công ty.", "Không dùng preview limit cao; không commit connection strings."],
];
setValues(commands, `A4:F${3 + commandRows.length}`, commandRows);
styleBody(commands.getRange(`A4:F${3 + commandRows.length}`));
setWidths(commands, [80, 360, 300, 280, 240, 320]);
commands.freezePanes.freezeRows(3);
commands.getRange(`A3:F${3 + commandRows.length}`).format.autofitRows();

const risks = addSheet("04_Rui_ro_hanh_dong");
setValues(risks, "A1:G1", [["Rủi ro còn lại và hành động đề xuất", "", "", "", "", "", ""]]);
risks.getRange("A1:G1").merge();
styleTitle(risks.getRange("A1:G1"));
setValues(risks, "A3:G3", [["ID", "Rủi ro / khoảng trống", "Tác động", "Hành động đề xuất", "Tiêu chí đóng", "Owner", "Ưu tiên"]]);
styleHeader(risks.getRange("A3:G3"));
const riskRows = [
  ["R-01", "Company MongoDB cho phép anonymous document read theo assessment 2026-06-15.", "Không thể dùng production/sensitive data an toàn; app proxy không bảo vệ direct DB access.", "DBA bật MongoDB authorization, khóa port 27017 bằng firewall/ACL, chỉ allow app host/subnet, rotate credential.", "scripts/check_company_mongodb_security.py trả anonymous_document_access_denied=true.", "DBA / Infra", "P0"],
  ["R-02", "Credential công ty đang có readAnyDatabase, rộng hơn namespace app cần.", "Nếu lộ credential, có thể đọc database ngoài phạm vi IoT Ops Agent.", "Tạo role riêng chỉ read trên authorization.IDENTITY, datamgmt.CIN/CNT/DEVICE_TELEMETRY/RULE, devicemgmt.NODE.", "least_privilege=true; không readAnyDatabase; violations=[].", "DBA", "P0"],
  ["R-03", "Rate limit proxy hiện process-local.", "Nhiều app instance có thể nhân quota tổng.", "Thêm shared rate limit ở API gateway hoặc Redis-backed limiter.", "Có test/integration evidence cho shared limiter.", "Backend / Platform", "P1"],
  ["R-04", "Company rules trong datamgmt.RULE chưa có contract chính thức.", "Alert severity trong PoC có thể bị hiểu nhầm là official.", "Gắn nhãn company-poc-v1 official=false; xác nhận rule semantics với lead/Grafana owner.", "Có tài liệu mapping rule status/severity/filter và source of truth.", "Product / Backend", "P1"],
  ["R-05", "Kết quả DB fallback/RLS phụ thuộc env hiện hành.", "Một lần đổi .env hoặc migration có thể làm lệch trạng thái demo.", "Đưa command evidence vào checklist release, lưu output JSON vào ticket.", "Mỗi release có output check_app_storage_status, check_supabase_rls, telemetry read/write.", "Backend", "P1"],
];
setValues(risks, `A4:G${3 + riskRows.length}`, riskRows);
styleBody(risks.getRange(`A4:G${3 + riskRows.length}`));
setWidths(risks, [80, 330, 310, 360, 280, 160, 90]);
risks.freezePanes.freezeRows(3);
risks.getRange(`A3:G${3 + riskRows.length}`).format.autofitRows();

const sources = addSheet("05_Nguon_tham_chieu");
setValues(sources, "A1:D1", [["Nguồn tham chiếu trong repo", "", "", ""]]);
sources.getRange("A1:D1").merge();
styleTitle(sources.getRange("A1:D1"));
setValues(sources, "A3:D3", [["Loại", "File", "Nội dung dùng trong sheet", "Ghi chú"]]);
styleHeader(sources.getRange("A3:D3"));
const sourceRows = [
  ["Doc", "docs/SECURITY_TEST_PROOF.md", "Tổng hợp security test, payload SQL/Mongo, API auth, rate limit, RLS, permission checker.", "Latest automated result trong doc: 86 tests passed."],
  ["Doc", "docs/COMPANY_DB_SECURITY_ASSESSMENT.md", "Assessment company MongoDB: anonymous read và readAnyDatabase là blocker.", "Không in credential/document values."],
  ["Doc", "docs/COMPANY_DB_DISCOVERY.md", "Luồng Company DB discovery, proxy read-only, fallback simulator, namespace allowlist.", "Dùng cho roadmap guardrail và demo flow."],
  ["Code", "services/company_mongo_proxy.py", "Allowlist, blocked operators, hard limit, timeout, audit event, read-only proxy methods.", "MAX_QUERY_LIMIT=1000; default rate limit 120/60s."],
  ["Test", "tests/test_company_mongo_proxy.py", "Unit test proxy: rate limit, allowlist, blocked operators, no write methods, discovery filter.", "Fake client/cursor, không chạm live DB."],
  ["Test", "tests/test_company_postgres_security.py", "Read-only transaction, parameterized timeout, identifier injection reject trước connect.", "Mock connection."],
  ["Script", "scripts/check_company_mongodb_security.py", "Live checker company MongoDB privilege/anonymous access.", "Acceptance gate cho production."],
  ["Script", "scripts/check_supabase_rls.py", "Live checker Supabase RLS và browser-facing role privileges.", "Acceptance gate cho app data."],
  ["Script", "scripts/check_mongodb_permissions.py", "Live checker MongoDB runtime credential.", "Runtime telemetry collection."],
  ["Script", "scripts/check_app_storage_status.py; scripts/check_telemetry_read_source.py; scripts/check_telemetry_write_backend.py", "Fallback/storage/read/write evidence.", "Chạy lại theo env."],
];
setValues(sources, `A4:D${3 + sourceRows.length}`, sourceRows);
styleBody(sources.getRange(`A4:D${3 + sourceRows.length}`));
setWidths(sources, [100, 360, 430, 300]);
sources.freezePanes.freezeRows(3);
sources.getRange(`A3:D${3 + sourceRows.length}`).format.autofitRows();

for (const sheet of [summary, tests, commands, risks, sources]) {
  sheet.getUsedRange().format.font.name = "Arial";
  sheet.getUsedRange().format.font.size = 10;
}

// Apply status colors.
const statusRanges = [
  [summary, "C4:C8"],
  [tests, `H4:H${3 + checklistRows.length}`],
  [detailed, `J5:J${4 + detailedRows.length}`],
  [risks, `G4:G${3 + riskRows.length}`],
];
for (const [sheet, rangeAddress] of statusRanges) {
  const range = sheet.getRange(rangeAddress);
  range.format.font.bold = true;
}

await fs.mkdir(outputDir, { recursive: true });

const inspectSummary = await workbook.inspect({
  kind: "table",
  range: "01_Tong_quan!A1:H8",
  include: "values",
  tableMaxRows: 10,
  tableMaxCols: 8,
});
console.log(inspectSummary.ndjson);

const inspectDetailed = await workbook.inspect({
  kind: "table",
  range: "06_86_Test_cases!A1:L12",
  include: "values",
  tableMaxRows: 12,
  tableMaxCols: 12,
});
console.log(inspectDetailed.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

for (const sheetName of [
  "01_Tong_quan",
  "02_Checklist_test",
  "06_86_Test_cases",
  "03_Lenh_evidence",
  "04_Rui_ro_hanh_dong",
  "05_Nguon_tham_chieu",
]) {
  const range = sheetName === "06_86_Test_cases" ? "A1:L24" : "A1:J18";
  await workbook.render({ sheetName, range, scale: 1 });
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(outputPath);
