import argparse
import json
import threading
import time
from datetime import datetime
from typing import Optional, Dict, Any

from flask import Flask, request, jsonify
from flask_cors import CORS

from utils_logger import setup_logger
from agent import agent_graph
from db import insert_message, find_unprocessed, update_result, mark_error, get_message_by_id

logger = setup_logger("upay.app")

app = Flask(__name__)
application = app
CORS(app, resources={r"/api/*": {"origins": "*"}})



def is_after_hours(now: Optional[datetime] = None) -> bool:
    now = now or datetime.now()
    return now.hour >= 21



def run_agent(text: str, after_hours: bool) -> Dict[str, Any]:
    state = {"input_text": text, "after_hours": after_hours}
    out = agent_graph.invoke(state)
    result = out.get("final_label", "Mediate")
    meta = out.get("meta", {})
    return {"result": result, "meta": meta}



def send_to_app(payload: Dict[str, Any]) -> None:
    try:
        logger.info("Sending to app: %s", payload)
    except Exception as e:
        logger.error("send_to_app error: %s", e)


def send_to_website(payload: Dict[str, Any]) -> None:
    try:
        logger.info("Sending to website: %s", payload)
    except Exception as e:
        logger.error("send_to_website error: %s", e)



def process_message(source: str, message: str) -> Dict[str, Any]:
    after_hours_flag = is_after_hours()
    msg_id = insert_message(source=source, message=message, after_hours=after_hours_flag)

    try:
        agent_out = run_agent(message, after_hours_flag)
        result = agent_out["result"]
        payload = {
            "id": msg_id,
            "source": source,
            "message": message,
            "result": result,
            "after_hours": after_hours_flag,
            "meta": agent_out.get("meta", {}),
        }
    except Exception as e:
        logger.error("Agent processing error: %s", e)
        payload = {
            "id": msg_id,
            "source": source,
            "message": message,
            "result": "Mediate",
            "after_hours": after_hours_flag,
            "meta": {"error": str(e)},
        }

    try:
        if msg_id is not None:
            from bson import ObjectId  # type: ignore

            update_result(ObjectId(msg_id), payload["result"], payload.get("meta"))
    except Exception as e:
        logger.error("DB update error: %s", e)
        try:
            if msg_id is not None:
                from bson import ObjectId  # type: ignore

                mark_error(ObjectId(msg_id), str(e))
        except Exception:
            pass

    try:
        if source == "app":
            send_to_app(payload)
        elif source == "website":
            send_to_website(payload)
        elif source == "database":
            pass
    except Exception as e:
        logger.error("Delivery error: %s", e)

    return payload



def _extract_text_from_request() -> str:
    """Extract text from JSON, form, args, or raw body."""
    try:
        if request.is_json:
            data = request.get_json(silent=True) or {}
            text = data.get("text") or data.get("message") or ""
            if text:
                return str(text)
    except Exception:
        pass
    try:
        text = request.form.get("text") or request.form.get("message")
        if text:
            return str(text)
    except Exception:
        pass
    text = request.args.get("text") or request.args.get("message")
    if text:
        return str(text)
    try:
        if request.data:
            return request.data.decode("utf-8", errors="ignore").strip()
    except Exception:
        pass
    return ""


@app.post("/api/message")
def receive_message():
    try:
        data = request.get_json(force=True)
        message = data.get("message", "")
        source = data.get("source", "website")  # default website
        if not message:
            return jsonify({"error": "message is required"}), 400
        payload = process_message(source, message)
        return jsonify(payload), 200
    except Exception as e:
        logger.error("/api/message error: %s", e)
        return jsonify({"error": str(e)}), 500


@app.post("/api/app/message")
def app_message():
    try:
        text = _extract_text_from_request()
        if not text:
            return jsonify({"error": "text or message is required"}), 400
        payload = process_message("app", text)
        return jsonify(payload), 200
    except Exception as e:
        logger.error("/api/app/message error: %s", e)
        return jsonify({"error": str(e)}), 500


@app.get("/api/app/process")
def app_process_get():
    try:
        text = _extract_text_from_request()
        if not text:
            return jsonify({"error": "text query param is required"}), 400
        payload = process_message("app", text)
        return jsonify(payload), 200
    except Exception as e:
        logger.error("/api/app/process error: %s", e)
        return jsonify({"error": str(e)}), 500


@app.get("/api/app/result/<id>")
def app_get_result(id: str):
    # Delegate to the same logic as /api/result/<id>
    return get_result(id)


@app.get("/health")
def health():
    return jsonify({"status": "ok", "time": int(time.time())})


@app.get("/")
def index():
    """Serve the simple frontend UI."""
    try:
        return app.send_static_file("index.html")
    except Exception as e:
        logger.error("/ index route error: %s", e)
        return ("Frontend not found", 404)


@app.get("/api/result/<id>")
def get_result(id: str):
    try:
        doc = get_message_by_id(id)
        if not doc:
            return jsonify({"error": "not found"}), 404
        try:
            doc["_id"] = str(doc.get("_id"))
        except Exception:
            pass
        return jsonify(doc), 200
    except Exception as e:
        logger.error("/api/result error: %s", e)
        return jsonify({"error": str(e)}), 500



class DBPoller(threading.Thread):
    def __init__(self, interval_sec: int = 60):
        super().__init__(daemon=True)
        self.interval = interval_sec
        self._stop = threading.Event()

    def run(self):
        logger.info("DB Poller started (interval=%ss)", self.interval)
        while not self._stop.is_set():
            try:
                docs = find_unprocessed(limit=100)
                for doc in docs:
                    try:
                        message = doc.get("message", "")
                        if not message:
                            continue
                        process_message("database", message)
                    except Exception as e:
                        logger.error("Error processing DB doc %s: %s", doc.get("_id"), e)
                time.sleep(self.interval)
            except Exception as e:
                logger.error("DB Poller loop error: %s", e)
                time.sleep(self.interval)

    def stop(self):
        self._stop.set()



def interactive_loop():
    logger.info("Interactive test mode. Type 'exit' to quit.")
    while True:
        try:
            text = input("Enter message> ").strip()
            if not text or text.lower() in {"exit", "quit"}:
                break
            payload = process_message("terminal", text)
            print(json.dumps(payload, indent=2))
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error("Interactive error: %s", e)



def main():
    parser = argparse.ArgumentParser(description="UPay Fraud Detection Backend")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-poller", action="store_true", help="Disable DB poller")
    parser.add_argument("--interactive", action="store_true", help="Interactive CLI test mode (for testing only)")
    args = parser.parse_args()

    poller = None
    if not args.no_poller:
        poller = DBPoller()
        poller.start()

    if args.interactive:
        interactive_loop()
    else:
        import os
        port = int(os.getenv("PORT", args.port))
        app.run(host=args.host, port=port)


if __name__ == "__main__":
    main()
