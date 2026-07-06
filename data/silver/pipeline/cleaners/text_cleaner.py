"""Text cleaner with per-step timing observability.

OBSERVABILITY ADDED (2026-07-03):
    - Each cleaning step is timed and reported
    - Stats: total_chars_removed, total_steps, step_durations_ms
    - Character count before/after for quality monitoring
"""
import re
import time
import unicodedata


class TextCleaner:
    """6-step text cleaning pipeline with observability.

    Steps:
        1. Remove HTML tags + entities
        2. Unicode NFC normalization
        3. Normalize newlines (CRLF → LF, max 2 consecutive)
        4. Remove control characters (except newlines)
        5. Normalize punctuation (avoid "08:30" → "08: 30" split)
        6. Normalize whitespace (multiple spaces → 1 space)

    Why this order:
        - HTML first: tags would interfere with punctuation patterns
        - Unicode before newlines: NFC may change line break chars
        - Newlines before control chars: preserves \n while removing \x00 etc
        - Punctuation before whitespace: space normalization should be last
    """

    def clean(self, text: str) -> str:
        """Clean text and return cleaned version with step timing."""
        if not text:
            return ""

        step_times = {}
        original_len = len(text)

        t0 = time.monotonic()
        text = self._remove_html(text)
        step_times["remove_html"] = (time.monotonic() - t0) * 1000

        t0 = time.monotonic()
        text = self._normalize_unicode(text)
        step_times["normalize_unicode"] = (time.monotonic() - t0) * 1000

        t0 = time.monotonic()
        text = self._normalize_newlines(text)
        step_times["normalize_newlines"] = (time.monotonic() - t0) * 1000

        t0 = time.monotonic()
        text = self._remove_control_chars(text)
        step_times["remove_control_chars"] = (time.monotonic() - t0) * 1000

        t0 = time.monotonic()
        text = self._normalize_punctuation(text)
        step_times["normalize_punctuation"] = (time.monotonic() - t0) * 1000

        t0 = time.monotonic()
        text = self._normalize_whitespace(text)
        step_times["normalize_whitespace"] = (time.monotonic() - t0) * 1000

        result = text.strip()
        chars_removed = original_len - len(result)

        # Attach stats to result object for observability collection
        self._last_stats = {
            "original_length": original_len,
            "cleaned_length": len(result),
            "chars_removed": chars_removed,
            "reduction_pct": round(chars_removed / max(original_len, 1) * 100, 2),
            "step_times_ms": step_times,
        }

        return result

    @property
    def last_stats(self) -> dict:
        """Get stats from the last cleaning operation."""
        return getattr(self, "_last_stats", {})

    def _remove_html(self, text: str) -> str:
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"&quot;", '"', text)
        text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
        text = re.sub(r"&[a-zA-Z]+;", " ", text)
        return text

    def _normalize_unicode(self, text: str) -> str:
        return unicodedata.normalize("NFC", text)

    def _normalize_newlines(self, text: str) -> str:
        text = text.replace("\r\n", "\n")
        text = text.replace("\r", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text

    def _remove_control_chars(self, text: str) -> str:
        return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    def _normalize_punctuation(self, text: str) -> str:
        text = re.sub(r"[{}[\]]", "", text)
        text = re.sub(r"(?<!\d)\s*([.,!?;])\s*(?!\d)", r"\1 ", text)
        text = re.sub(r"(?<!\d)\s*:\s*(?!\d)", ": ", text)
        return text

    def _normalize_whitespace(self, text: str) -> str:
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n ", "\n", text)
        text = re.sub(r" \n", "\n", text)
        return text.strip()
