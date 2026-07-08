import threading

from mcp_server.services.company_mongo_proxy import get_company_mongo_read_proxy

_lock = threading.Lock()
_proxy = None


def get_pooled_mongo_proxy(actor="mcp-server"):
    global _proxy

    with _lock:
        if _proxy is None:
            _proxy = get_company_mongo_read_proxy(actor=actor)

        return _proxy


def reset_pooled_mongo_proxy():
    global _proxy

    with _lock:
        if _proxy is not None:
            _proxy.close()
            _proxy = None
