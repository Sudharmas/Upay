from typing import Optional
import re
import os
import pickle
from utils_logger import setup_logger

logger = setup_logger("upay.offline")

MODEL_PATH = os.path.join(os.path.dirname(__file__), "model.pkl")
local_model = None
try:
    if os.path.exists(MODEL_PATH):
        try:
            import joblib  # type: ignore
            local_model = joblib.load(MODEL_PATH)
            logger.info("Loaded local model via joblib from %s", MODEL_PATH)
        except Exception:
            with open(MODEL_PATH, "rb") as f:
                local_model = pickle.load(f)
            logger.info("Loaded local model via pickle from %s", MODEL_PATH)
    else:
        logger.warning("Local model file not found at %s; falling back to heuristics", MODEL_PATH)
except Exception as e:
    logger.error("Failed to load local model: %s; falling back to heuristics", e)
    local_model = None

SAFE_PATTERNS = [
    r"UPI payment received",
    r"credited to your account",
    r"debit of INR .* via UPI",
    r"transaction id|txn id|utr",
    r"payment successful",
    r"thank you for using",
]

FRAUD_KEYWORDS = [
    "otp", "kyc", "urgent", "immediately", "verify", "verification",
    "blocked", "suspend", "suspended", "lottery", "gift", "refund",
    "click", "link", "qr", "scan", "pin", "password", "cvv",
    "update account", "reset", "collect request", "upi collect",
    "call", "whatsapp", "telegram", "send money", "transfer",
    "prize", "winner", "free", "limited time", "offer", "bonus",
    "bank manager", "customer care", "support",
]

MEDIATE_SIGNALS = [
    "unknown", "unexpected", "strange", "suspicious",
]


class OfflineHeuristicModel:
    """Lightweight, offline-only heuristic model for fraud detection.
    Returns one of: 'Fraud', 'Not Fraud', 'Mediate'.
    """

    def __init__(self) -> None:
        pass

    @staticmethod
    def normalize(txt: str) -> str:
        return re.sub(r"\s+", " ", txt.strip().lower())

    def score(self, text: str) -> int:
        t = self.normalize(text)
        score = 0
        for kw in FRAUD_KEYWORDS:
            if kw in t:
                score += 2
        if re.search(r"https?://|\bbit\.ly\b|tinyurl|\.link\b|\d{10}\b", t):
            score += 3
        if re.search(r"inr\s*\d+|rs\.?\s*\d+|\b\d{3,}\b", t) and ("urgent" in t or "immediately" in t):
            score += 2
        if re.search(r"[a-z0-9_.-]+@[a-z]+", t):
            score += 1
        return score

    def is_safe_like(self, text: str) -> bool:
        t = self.normalize(text)
        return any(re.search(pat, t) for pat in SAFE_PATTERNS)

    def predict(self, text: str) -> Optional[str]:
        try:
            if not text or not text.strip():
                return None

            if local_model is not None:
                try:
                    pred = local_model.predict([text])
                    if isinstance(pred, (list, tuple)) and pred:
                        label = pred[0]
                    else:
                        try:
                            label = pred[0]
                        except Exception:
                            label = pred
                    if hasattr(label, "item"):
                        label = label.item()
                    if isinstance(label, (bytes, bytearray)):
                        label = label.decode("utf-8", errors="ignore")
                    label_str = str(label).strip()
                    if label_str:
                        logger.info("Local model prediction: %s", label_str)
                        return label_str
                except Exception as e:
                    logger.warning("Local model prediction failed, falling back to heuristics: %s", e)

            t = self.normalize(text)
            score = self.score(t)
            logger.debug("Offline score: %s", score)

            if self.is_safe_like(t) and score <= 1:
                return "Not Fraud"
            if score >= 5:
                return "Fraud"
            if any(sig in t for sig in MEDIATE_SIGNALS):
                return "Mediate"
            if 2 <= score <= 4:
                return "Mediate"
            return "Not Fraud"
        except Exception as e:
            logger.error("Offline model error: %s", e)
            return None


offline_model = OfflineHeuristicModel()
