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


def ensure_telemetry_indexes():
    collection = get_telemetry_collection()

    index_names = [
        collection.create_index(
            [("device_id", 1), ("timestamp", -1)],
            name="device_timestamp_desc",
        ),
        collection.create_index(
            [("timestamp", -1)],
            name="timestamp_desc",
        ),
        collection.create_index(
            [("status", 1), ("timestamp", -1)],
            name="status_timestamp_desc",
        ),
    ]

    return {
        "database": get_mongodb_db(),
        "collection": get_mongodb_telemetry_collection(),
        "indexes": index_names,
    }


def get_telemetry_indexes():
    collection = get_telemetry_collection()
    return {
        "database": get_mongodb_db(),
        "collection": get_mongodb_telemetry_collection(),
        "indexes": list(collection.list_indexes()),
    }


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


def flatten_telemetry_document(document):
    metrics = document.get("metrics") or {}
    alarm = document.get("alarm") or {}

    return {
        "device_id": document.get("device_id"),
        "timestamp": document.get("timestamp"),
        "cpu_usage": metrics.get("cpu_usage"),
        "memory_usage": metrics.get("memory_usage"),
        "heartbeat_delay": metrics.get("heartbeat_delay"),
        "status": document.get("status"),
        "log_message": document.get("log_message"),
        "alarm_name": alarm.get("name"),
        "alarm_severity": alarm.get("severity"),
    }


def get_all_latest_devices_from_mongo():
    collection = get_telemetry_collection()
    rows = collection.aggregate([
        {"$sort": {"timestamp": -1}},
        {
            "$group": {
                "_id": "$device_id",
                "document": {"$first": "$$ROOT"},
            }
        },
        {"$replaceRoot": {"newRoot": "$document"}},
        {"$sort": {"device_id": 1}},
        {"$project": {"_id": 0}},
    ])

    return [
        flatten_telemetry_document(row)
        for row in rows
    ]


def get_latest_status_from_mongo(device_id):
    collection = get_telemetry_collection()
    document = collection.find_one(
        {"device_id": device_id},
        {"_id": 0},
        sort=[("timestamp", -1)],
    )

    if not document:
        return None

    return flatten_telemetry_document(document)


def get_device_telemetry_history_from_mongo(device_id, limit=30):
    collection = get_telemetry_collection()
    rows = list(
        collection.find(
            {"device_id": device_id},
            {"_id": 0},
        )
        .sort("timestamp", -1)
        .limit(limit)
    )

    return [
        flatten_telemetry_document(row)
        for row in reversed(rows)
    ]
