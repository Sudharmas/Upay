import os
from typing import Optional
from utils_logger import setup_logger

try:
    import google.generativeai as genai
except Exception as _e:
    genai = None

logger = setup_logger("upay.online")

ALLOWED = {"fraud": "Fraud", "not fraud": "Not Fraud", "mediate": "Mediate"}


def normalize_label(label: str) -> Optional[str]:
    if not label:
        return None
    l = label.strip().lower()
    l = l.replace(".", "").replace("'", "")
    if l in ALLOWED:
        return ALLOWED[l]
    if "not" in l and "fraud" in l:
        return "Not Fraud"
    if "mediate" in l:
        return "Mediate"
    if "fraud" in l or "scam" in l or "spam" in l:
        return "Fraud"
    return None


class OnlineLLM:
    def __init__(self) -> None:
        self.api_key = os.getenv(
            "GOOGLE_API_KEY",
            "AIzaSyAFBGzOxCXwLYRBXhQY3g0VqTPn4cNF-DE",
        )
        self.prompt_tmpl = None
        try:
            from langchain_core.prompts import PromptTemplate  # type: ignore
            self.prompt_tmpl = PromptTemplate.from_template(
                "You are an expert fraud classifier. Classify the given text as exactly one of: "
                "Fraud, Not Fraud, Mediate. Reply with ONLY one of these EXACT labels.\n\n"
                "Text: {text}\n\nAnswer:"
            )
        except Exception:
            self.prompt_tmpl = None

        if genai is None:
            self.enabled = False
            logger.warning("google-generativeai SDK not available; Online LLM disabled.")
            return
        self.enabled = bool(self.api_key)
        if not self.enabled:
            logger.warning("GOOGLE_API_KEY not set and no default provided. Online LLM will be disabled.")
            return
        try:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel("gemini-2.0-flash")
        except Exception as e:
            logger.error("Failed to initialize Gemini model: %s", e)
            self.enabled = False

    def _classify(self, text: str) -> str:
        if self.prompt_tmpl is not None:
            try:
                prompt = self.prompt_tmpl.format(text=text)
            except Exception:
                prompt = (
                    "You are an expert fraud classifier. Classify the given text as exactly one of: "
                    "Fraud, Not Fraud, Mediate. Reply with ONLY one of these EXACT labels.\n\n"
                    f"Text: {text}\n\nAnswer:"
                )
        else:
            prompt = (
                "You are an expert fraud classifier. Classify the given text as exactly one of: "
                "Fraud, Not Fraud, Mediate. Reply with ONLY one of these EXACT labels.\n\n"
                f"Text: {text}\n\nAnswer:"
            )
        resp = self.model.generate_content(prompt)
        raw = None
        try:
            raw = getattr(resp, "text", None)
        except Exception:
            raw = None
        if not raw:
            try:
                if hasattr(resp, "candidates") and resp.candidates:
                    parts = resp.candidates[0].content.parts
                    raw = "".join(getattr(p, "text", "") for p in parts)
            except Exception:
                raw = None
        return raw or ""

    def predict(self, text: str) -> Optional[str]:
        if not self.enabled:
            return None
        try:
            raw = self._classify(text)
            label = normalize_label(raw)
            if label is None:
                raw2 = self._classify(text + "\nReturn only 'Fraud' or 'Not Fraud' or 'Mediate'.")
                label = normalize_label(raw2)
            logger.info("Online LLM raw: %r => %s", raw, label)
            return label
        except Exception as e:
            logger.error("Online LLM predict error: %s", e)
            return None


online_llm = OnlineLLM()
