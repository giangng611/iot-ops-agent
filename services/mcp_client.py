import asyncio
import concurrent.futures
import json
import os
import queue
import threading
import time


class McpClientError(RuntimeError):
    pass


def get_mcp_server_url():
    return os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp").strip()


def get_mcp_bearer_key():
    return (
        os.getenv("MCP_BEARER_KEY")
        or os.getenv("MCP_TEST_BEARER_KEY")
        or ""
    ).strip()


def _extract_mcp_result(result, tool_name):
    if result.isError:
        message = "; ".join(
            str(getattr(item, "text", item))
            for item in result.content
        )
        raise McpClientError(f"MCP tool returned an error: {tool_name}: {message}")

    structured = result.structuredContent

    if isinstance(structured, dict) and set(structured.keys()) == {"result"}:
        return structured["result"]

    if structured is not None:
        return structured

    for item in result.content:
        text = getattr(item, "text", None)

        if not text:
            continue

        try:
            return json.loads(text)
        except ValueError:
            return text

    return None


async def _call_mcp_tool_async(tool_name, arguments):
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
    except ImportError as exc:
        raise McpClientError(
            "MCP client dependency is not installed. "
            "Install app requirements, including mcp."
        ) from exc

    url = get_mcp_server_url()
    bearer_key = get_mcp_bearer_key()

    if not bearer_key:
        raise McpClientError("MCP_BEARER_KEY is not configured for the app.")

    headers = {"Authorization": f"Bearer {bearer_key}"}

    result = None

    try:
        async with streamablehttp_client(
            url,
            headers=headers,
            terminate_on_close=False,
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments or {})
    except Exception as exc:
        if result is not None:
            return _extract_mcp_result(result, tool_name)

        raise McpClientError(
            f"MCP tool call failed before tool result: {tool_name}: {exc}"
        ) from exc

    return _extract_mcp_result(result, tool_name)


class SyncMcpToolSession:
    def __init__(self):
        self._thread = None
        self._requests = queue.Queue()
        self._ready = threading.Event()
        self._error = None

    def __enter__(self):
        attempts = 3

        for attempt in range(attempts):
            self._error = None
            self._ready.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            self._ready.wait()

            if not self._error:
                return self

            self.close()

            if attempt < attempts - 1:
                time.sleep(0.2 * (attempt + 1))

        raise self._error

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _run_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._main())
        except BaseException as exc:
            self._error = exc
            self._ready.set()
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.run_until_complete(loop.shutdown_default_executor())
            loop.close()

    async def _main(self):
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client
        except ImportError as exc:
            raise McpClientError(
                "MCP client dependency is not installed. "
                "Install app requirements, including mcp."
            ) from exc

        url = get_mcp_server_url()
        bearer_key = get_mcp_bearer_key()

        if not bearer_key:
            raise McpClientError("MCP_BEARER_KEY is not configured for the app.")

        headers = {"Authorization": f"Bearer {bearer_key}"}
        async with streamablehttp_client(
            url,
            headers=headers,
            terminate_on_close=False,
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self._ready.set()

                while True:
                    request = await asyncio.to_thread(self._requests.get)

                    if request is None:
                        break

                    tool_name, arguments, future = request

                    try:
                        result = await session.call_tool(
                            tool_name,
                            arguments or {},
                        )
                        future.set_result(
                            _extract_mcp_result(result, tool_name)
                        )
                    except BaseException as exc:
                        future.set_exception(exc)

    def call_tool(self, tool_name, arguments=None):
        if not self._thread:
            raise McpClientError("MCP session is not open.")

        future = concurrent.futures.Future()
        self._requests.put((tool_name, arguments or {}, future))

        try:
            return future.result()
        except Exception as exc:
            if isinstance(exc, McpClientError):
                raise

            raise McpClientError(
                f"MCP tool call failed before tool result: {tool_name}: {exc}"
            ) from exc

    def close(self):
        if not self._thread:
            return

        self._requests.put(None)
        self._thread.join()
        self._thread = None


def _run_coro_in_thread(coro):
    result = {}

    def runner():
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:
            result["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()

    if "error" in result:
        raise result["error"]

    return result.get("value")


def call_mcp_tool(tool_name, arguments=None):
    coro = _call_mcp_tool_async(tool_name, arguments or {})

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            return asyncio.run(coro)
        except RuntimeError as loop_exc:
            # asyncio cleanup (e.g. httpx teardown) can fire after the event
            # loop closes and re-raise RuntimeError in the except block above,
            # which would escape unhandled. Wrap it so callers see McpClientError.
            raise McpClientError(
                f"MCP tool call failed (event loop error): {loop_exc}"
            ) from loop_exc

    return _run_coro_in_thread(coro)
