import os
from datetime import datetime

try:
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
except ImportError:
    MongoClient = None
    PyMongoError = Exception


_client = None
_client_uri = None
_warned_unavailable = False
_disabled_after_failure = False


def mongodb_enabled():
    if _disabled_after_failure:
        return False

    return os.getenv("ENABLE_MONGODB", "false").lower() == "true"


def get_mongodb_uri():
    return os.getenv("MONGODB_URI", "mongodb://localhost:27017")


def get_mongodb_db():
    return os.getenv("MONGODB_DB", "iot_ops_agent")


def get_mongodb_telemetry_collection():
    return os.getenv("MONGODB_TELEMETRY_COLLECTION", "telemetry")


def get_mongo_client():
    global _client, _client_uri

    if MongoClient is None:
        raise RuntimeError(
            "pymongo is not installed. Run `pip install -r requirements.txt` "
            "before enabling MongoDB telemetry."
        )

    uri = get_mongodb_uri()
    if _client is None or _client_uri != uri:
        _client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        _client_uri = uri
        _client.admin.command("ping")

    return _client


def get_telemetry_collection():
    client = get_mongo_client()
    return client[get_mongodb_db()][get_mongodb_telemetry_collection()]


def build_telemetry_document(
    device_id,
    cpu_usage,
    memory_usage,
    heartbeat_delay,
    status,
    log_message=None,
    alarm_name=None,
    alarm_severity=None,
):
    return {
        "device_id": device_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "metrics": {
            "cpu_usage": cpu_usage,
            "memory_usage": memory_usage,
            "heartbeat_delay": heartbeat_delay,
        },
        "status": status,
        "log_message": log_message,
        "alarm": {
            "name": alarm_name,
            "severity": alarm_severity,
            "active": alarm_name is not None,
        },
        "source": "simulator",
    }


def insert_telemetry_document(document):
    if not mongodb_enabled():
        return False

    collection = get_telemetry_collection()
    collection.insert_one(document)
    return True


def insert_telemetry_if_enabled(**telemetry):
    global _warned_unavailable, _disabled_after_failure

    if not mongodb_enabled():
        return False

    try:
        document = build_telemetry_document(**telemetry)
        return insert_telemetry_document(document)
    except (PyMongoError, RuntimeError) as exc:
        _disabled_after_failure = True
        if not _warned_unavailable:
            print(f"MongoDB telemetry write disabled for this run: {exc}")
            _warned_unavailable = True
        return False


def get_telemetry_health(limit=5):
    collection = get_telemetry_collection()
    latest = list(
        collection.find({}, {"_id": 0})
        .sort("timestamp", -1)
        .limit(limit)
    )

    return {
        "database": get_mongodb_db(),
        "collection": get_mongodb_telemetry_collection(),
        "count": collection.count_documents({}),
        "latest": latest,
    }
