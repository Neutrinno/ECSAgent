"""Нормализация текста финального ответа для пользователя (без JSON/state-артефактов)."""

import json
import re
from typing import Any, Optional


_FENCE_RE = re.compile(
    r"```(?:json)?\s*([\s\S]*?)```",
    re.IGNORECASE,
)


def _try_extract_inner_final(obj: Any) -> Optional[str]:
    """Извлекает строку ответа из вложенных dict, если модель вернула «state»."""
    if isinstance(obj, str):
        s = obj.strip()
        if not s:
            return None
        try:
            parsed = json.loads(s)
        except json.JSONDecodeError:
            return None
        return _try_extract_inner_final(parsed)

    if isinstance(obj, dict):
        fr = obj.get("final_result")
        if isinstance(fr, str) and fr.strip():
            return fr.strip()
        st = obj.get("state")
        if isinstance(st, dict):
            fr2 = st.get("final_result")
            if isinstance(fr2, str) and fr2.strip():
                return fr2.strip()
        if isinstance(st, str) and st.strip():
            return _try_extract_inner_final(st)
    return None


def sanitize_final_result(text: str) -> str:
    """
    Убирает markdown-ограждения с JSON; при «проза + fenced JSON» оставляет прозу.
    Если остался только JSON — извлекает вложенный final_result.
    """
    if not text or not isinstance(text, str):
        return text or ""

    s = text.strip()

    extracted_from_fence: Optional[str] = None
    for m in _FENCE_RE.finditer(s):
        inner = m.group(1).strip()
        ex = _try_extract_inner_final(inner)
        if ex:
            extracted_from_fence = ex
            break

    without_fences = _FENCE_RE.sub("", s).strip()
    # Если после снятия кода остался связный текст — это ответ пользователю (в т.ч. «проза + JSON-блок»).
    if without_fences:
        return without_fences

    if extracted_from_fence:
        return extracted_from_fence

    if s.startswith("{"):
        try:
            parsed = json.loads(s)
            ex = _try_extract_inner_final(parsed)
            if ex:
                return ex
        except json.JSONDecodeError:
            pass

    return s
