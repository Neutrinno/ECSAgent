import json
import math
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from langchain_core.tools import tool

from src.core.agents.relocation_agent.relocation_models import RelocationModel
from src.utils.logger import get_logger

logger = get_logger(__name__)

KEY_MOVING_COL = "Ключ 1 (изменяемое ВСП) / 0 (ВСП ЛР)"


def _sanitize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (np.floating,)):
        v = float(value)
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value


def dataframe_to_json_safe_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []
    df = df.replace([np.inf, -np.inf], np.nan)
    records = df.to_dict(orient="records")
    out: List[Dict[str, Any]] = []
    for row in records:
        out.append({str(k): _sanitize_value(v) for k, v in row.items()})
    return out


def _build_summary(vsp_code: str, df_main: pd.DataFrame) -> Dict[str, Any]:
    summary: Dict[str, Any] = {"vsp_code": vsp_code}
    if df_main is None or df_main.empty:
        return summary
    if KEY_MOVING_COL not in df_main.columns:
        return summary
    moving = df_main[df_main[KEY_MOVING_COL] == 1]
    if moving.empty:
        return summary
    r = moving.iloc[0]
    for col in (
        "Изменение УП",
        "Изменение КП СКМ",
        "Изменение КП СМО",
        "Изменение КП СМРК",
        "Требуемое кол-во дополнительных РМ СКМ с учетом изменения УП",
        "Требуемое кол-во дополнительных РМ СМО с учетом изменения КП",
        "Требуемое кол-во дополнительных РМ СМРК с учетом изменения КП",
        "Требуемая доп.площадь под СКМ",
        "Требуемая доп.площадь под СМО",
        "Требуемая доп.площадь под СМРК",
        "Дефицит (-) / Излишек (+) площади после закрытия ВСП, м2",
    ):
        if col in r.index:
            summary[col] = _sanitize_value(r[col])
    return summary


def _payload_error(error: str, error_type: str) -> str:
    return json.dumps({"ok": False, "error": error, "error_type": error_type}, ensure_ascii=False)


@tool
def calculate_vsp_relocation(
    vsp_code: str,
    latitude: float,
    longitude: float,
    is_close: Optional[List[str]] = None,
    is_cs: Optional[List[str]] = None,
) -> str:
    """
    Расчёт последствий перемещения ВСП (RelocationModel): перетоки в зонах ЛР, КП/УП, ПШЕ, РМ, площади.

    Вход: vsp_code — полный код ВСП (как в ЦС_ВСП_v8); latitude, longitude — новая точка (WGS84);
    is_close — коды ВСП, исключаемые из справочника; is_cs — коды, оставляемые при закрытии.

    Выход: JSON-строка. При успехе: ok=true, report_rows (полный отчёт), bt_relocate_rows (срез для БТ),
    summary (ключевые дельты по перемещаемому ВСП). Данные: data/ЦС_ВСП_v8.xlsx, data/relocation/vsp_move_scores.feather.
    """
    is_close_f = [x for x in (is_close or []) if x and str(x).strip()]
    is_cs_f = [x for x in (is_cs or []) if x and str(x).strip()]

    if not vsp_code or not str(vsp_code).strip():
        return _payload_error("Не указан vsp_code (код перемещаемого ВСП).", "ValueError")

    code = str(vsp_code).strip()

    try:
        model = RelocationModel(is_close=is_close_f, is_cs=is_cs_f)
        df_main, df_bt = model.get_prediction(urf_code=code, coors=(latitude, longitude))
    except FileNotFoundError as e:
        logger.error("Relocation: файл данных не найден: %s", e)
        return _payload_error(
            "Не найдены файлы данных (data/ЦС_ВСП_v8.xlsx или data/relocation/vsp_move_scores.feather).",
            "FileNotFoundError",
        )
    except Exception as e:
        logger.exception("Relocation: ошибка расчёта")
        return _payload_error(str(e), type(e).__name__)

    payload: Dict[str, Any] = {
        "ok": True,
        "vsp_code": code,
        "latitude": latitude,
        "longitude": longitude,
        "is_close": is_close_f,
        "is_cs": is_cs_f,
        "report_rows": dataframe_to_json_safe_records(df_main),
        "bt_relocate_rows": dataframe_to_json_safe_records(df_bt),
        "summary": _build_summary(code, df_main),
    }
    return json.dumps(payload, ensure_ascii=False)


RELOCATION_AGENT_TOOLS = [calculate_vsp_relocation]
