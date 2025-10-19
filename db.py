import os
import time
from typing import Optional, List, Dict, Any
from pymongo import MongoClient, ReturnDocument
from pymongo.errors import PyMongoError
from bson import ObjectId  # type: ignore
from utils_logger import setup_logger

logger = setup_logger("upay.db")

try:
    import certifi
    _CA_FILE = certifi.where()
except Exception:
    _CA_FILE = None

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb+srv://admin:admin@springcluster.m1yn68x.mongodb.net/?retryWrites=true&w=majority&appName=SpringCluster")
DB_NAME = os.getenv("MONGODB_DB", "upay")
COLLECTION_NAME = os.getenv("MONGODB_COLLECTION", "messages")

_client: Optional[MongoClient] = None


def get_client() -> Optional[MongoClient]:
    global _client
    if _client is not None:
        return _client
    try:
        client_opts: Dict[str, Any] = {
            "serverSelectionTimeoutMS": 5000,  # a bit more generous
        }
        if _CA_FILE:
            client_opts["tlsCAFile"] = _CA_FILE
        elif os.getenv("MONGODB_TLS_ALLOW_INVALID", "").lower() in ("1", "true", "yes"):
            client_opts["tlsAllowInvalidCertificates"] = True

        _client = MongoClient(MONGODB_URI, **client_opts)
        _client.admin.command("ping")
        logger.info("Connected to MongoDB at %s", MONGODB_URI)
        return _client
    except Exception as e:
        logger.error("MongoDB connection failed: %s", e)
        return None
def get_collection():
    client = get_client()
    if client is None:
        return None
    return client[DB_NAME][COLLECTION_NAME]
def insert_message(source: str, message: str, after_hours: bool) -> Optional[str]:
    col = get_collection()
    if col is None:
        logger.error("No MongoDB collection available; insert_message skipped")
        return None
    doc = {
        "source": source,
        "message": message,
        "after_hours": after_hours,
        "status": "new",
        "result": None,
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
    }
    try:
        res = col.insert_one(doc)
        logger.info("Inserted new message %s from %s", res.inserted_id, source)
        return str(res.inserted_id)
    except PyMongoError as e:
        logger.error("Insert failed: %s", e)
        return None
def find_unprocessed(limit: int = 50) -> List[Dict[str, Any]]:
    col = get_collection()
    if col is None:
        return []
    try:
        cursor = col.find({"$or": [{"status": "new"}, {"result": None}]}, limit=limit).sort("created_at", 1)
        return list(cursor)
    except PyMongoError as e:
        logger.error("Query unprocessed failed: %s", e)
        return []
def update_result(doc_id, result: str, meta: Optional[Dict[str, Any]] = None) -> bool:
    col = get_collection()
    if col is None:
        logger.error("No MongoDB collection available; update_result skipped")
        return False
    try:
        update = {
            "$set": {
                "result": result,
                "status": "processed",
                "updated_at": int(time.time()),
                "meta": meta or {},
            }
        }
        res = col.find_one_and_update({"_id": doc_id} if not isinstance(doc_id, str) else {"_id": __import__("bson").ObjectId(doc_id)}, update, return_document=ReturnDocument.AFTER)
        logger.info("Updated result for %s => %s", doc_id, result)
        return res is not None
    except PyMongoError as e:
        logger.error("Update failed: %s", e)
        return False
    except Exception as e:
        logger.error("Update failed (generic): %s", e)
        return False
def mark_error(doc_id, error: str) -> None:
    col = get_collection()
    if col is None:
        return
    try:
        col.update_one(
            {"_id": doc_id} if not isinstance(doc_id, str) else {"_id": __import__("bson").ObjectId(doc_id)},
            {"$set": {"status": "error", "error": error, "updated_at": int(time.time())}},
        )
    except Exception as e:
        logger.error("Mark error failed: %s", e)
def get_message_by_id(doc_id) -> Optional[Dict[str, Any]]:
    """Fetch a single message document by id (str or ObjectId)."""
    col = get_collection()
    if col is None:
        return None
    try:
        oid = doc_id if not isinstance(doc_id, str) else __import__("bson").ObjectId(doc_id)
        doc = col.find_one({"_id": oid})
        return doc
    except Exception as e:
        logger.error("get_message_by_id failed: %s", e)
        return None