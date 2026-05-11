"""Инструменты network_optimizer_agent.

Оставлен сценарий закрытия ВСП (`calculate_close_vsp`) и справочный
`get_vsp_info`. Логика перемещения вынесена в `movement_old/` в корне репозитория.
"""

import json
import math
from typing import List, Optional

import pandas as pd
from langchain_core.tools import tool

from src.core.agents.network_optimizer_agent.scripts.close_script import VSPAnalyzer
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _num(value, *, integer: bool = False):
    """Безопасно привести значение из pandas/numpy к Python-числу для json.dumps."""
    if value is None:
        return 0
    try:
        if isinstance(value, float) and math.isnan(value):
            return 0
        return int(value) if integer else float(value)
    except (TypeError, ValueError):
        return 0


def _str(value, default: str = "") -> str:
    """Безопасное приведение к str (адрес, тип НП, доля перетока)."""
    if value is None:
        return default
    try:
        if isinstance(value, float) and math.isnan(value):
            return default
    except TypeError:
        pass
    return str(value)


def _closing_vsp_record(df_asinh: pd.DataFrame, close_vsp: str) -> Optional[dict]:
    """Сформировать запись о закрываемом ВСП из df_asinh."""
    rows = df_asinh[df_asinh['Код ВСП (изменяемое)'] == close_vsp]
    if rows.empty:
        return None

    self_flag_col = 'Ключ 1 (изменяемое ВСП) / 0 (ВСП ЛР)'
    if self_flag_col in rows.columns:
        self_rows = rows[rows[self_flag_col] == 1]
        row = self_rows.iloc[0] if not self_rows.empty else rows.iloc[0]
    else:
        row = rows.iloc[0]

    return {
        "vsp_code": _str(row.get('Код ВСП (изменяемое)'), close_vsp),
        "legal_address": _str(row.get('Юр.адрес')),
        "settlement_type_code": _str(row.get('Краткий тип НП')),
        "current_metrics": {
            "sales_up": _num(row.get('Продажи УП СКМ')),
            "kp_skm": _num(row.get('КП СКМ')),
            "kp_smo": _num(row.get('КП СМО')),
            "total_kp": _num(row.get('Общий/СМРК КП')),
        },
    }


def _successor_record(row: pd.Series) -> dict:
    """Сформировать запись о ВСП-преемнике из одной строки df_sinh."""
    dop_skm = _num(row.get('Требуемая доп.площадь под СКМ'))
    dop_smo = _num(row.get('Требуемая доп.площадь под СМО'))
    dop_smrk = _num(row.get('Требуемая доп.площадь под СМРК'))

    return {
        "vsp_code": _str(row.get('Код ВСП (изменяемое и на которые влияем)')),
        "legal_address": _str(row.get('Юр.адрес')),
        "settlement_type_code": _str(row.get('Краткий тип НП')),
        "parameters": {
            "kbo_coefficient": _num(row.get('Коэф. КБО')),
            "normative_up_per_day_per_fte": _num(row.get('Нормативный УП в сутки на 1 ПШЕ')),
            "avg_conversion_kp_mp_to_up_mp_city": _num(
                row.get('Средняя конвертация КП МП в УП МП по городу')
            ),
            "normative_worktime": _num(row.get('Нормативное время работы')),
            "target_worktime_week": _num(row.get('Целевое время работы в неделю')),
            "smrk_flag": _num(row.get('Флаг СМРК'), integer=True) == 1,
            "flow_share": _str(row.get('Доля перетока')),
        },
        "before_close": {
            "sales_up_skm": _num(row.get('Продажи УП СКМ')),
            "kp_skm": _num(row.get('КП СКМ')),
            "kp_smo": _num(row.get('КП СМО')),
            "total_kp_smrk": _num(row.get('Общий/СМРК КП')),
            "pshe": {
                "skm": _num(row.get('ПШЕ СКМ')),
                "smo": _num(row.get('ПШЕ СМО')),
                "smrk": _num(row.get('ПШЕ СМРК')),
                "skm_calc": _num(row.get('ПШЕ СКМ расч.')),
                "smo_calc": _num(row.get('ПШЕ СМО расч.')),
                "smrk_calc": _num(row.get('ПШЕ СМРК расч.')),
            },
            "rm": {
                "skm": _num(row.get('РМ СКМ')),
                "smo": _num(row.get('РМ СМО')),
                "smrk": _num(row.get('РМ СМРК')),
            },
            "area": {
                "norm_m2": _num(row.get('Площадь норм, м2')),
                "fact_m2": _num(row.get('Площадь факт, м2')),
                "balance_m2": _num(row.get('Дефицит (-)/Избыток (+)')),
            },
        },
        "after_close": {
            "changes": {
                "delta_up": _num(row.get('Изменение УП')),
                "delta_kp_skm": _num(row.get('Изменение КП СКМ')),
                "delta_kp_smo": _num(row.get('Изменение КП СМО')),
                "delta_kp_smrk": _num(row.get('Изменение КП СМРК')),
                "delta_pshe_skm": _num(row.get('Изменение ПШЕ СКМ с учетом нагрузки')),
                "delta_pshe_smo": _num(row.get('Изменение ПШЕ СМО с учетом нагрузки')),
                "delta_pshe_smrk": _num(row.get('Изменение ПШЕ СМРК с учетом нагрузки')),
                "delta_rm_skm": _num(
                    row.get('Требуемое кол-во дополнительных РМ СКМ с учетом изменения УП')
                ),
                "delta_rm_smo": _num(
                    row.get('Требуемое кол-во дополнительных РМ СМО с учетом изменения КП')
                ),
                "delta_rm_smrk": _num(
                    row.get('Требуемое кол-во дополнительных РМ СМРК с учетом изменения КП')
                ),
            },
            "new_values": {
                "new_up": _num(row.get('Новый УП')),
                "new_kp_skm": _num(row.get('Новый КП СКМ')),
                "new_kp_smo": _num(row.get('Новый КП СМО')),
                "new_total_kp_smrk": _num(row.get('Новый общий/СМРК КП')),
                "new_pshe_skm": _num(row.get('Итого необходимо ПШЕ СКМ')),
                "new_pshe_smo": _num(row.get('Итого необходимо ПШЕ СМО')),
                "new_pshe_smrk": _num(row.get('Итого необходимо ПШЕ СМРК')),
                "new_pshe_skm_calc": _num(row.get('Новый ПШЕ СКМ')),
                "new_pshe_smo_calc": _num(row.get('Новый ПШЕ СМО')),
                "new_pshe_smrk_calc": _num(row.get('Новый ПШЕ СМРК')),
                "new_rm_skm": _num(row.get('Итого необходимо РМ СКМ')),
                "new_rm_smo": _num(row.get('Итого необходимо РМ СМО')),
                "new_rm_smrk": _num(row.get('Итого необходимо РМ СМРК')),
            },
            "additional_area": {
                "skm_area_m2": dop_skm,
                "smo_area_m2": dop_smo,
                "smrk_area_m2": dop_smrk,
                "total_m2": dop_skm + dop_smo + dop_smrk,
            },
            "area_after": {
                "norm_m2": _num(row.get('Нормативная площадь после закрытия ВСП, м2')),
                "balance_m2": _num(
                    row.get('Дефицит (-) / Излишек (+) площади после закрытия ВСП, м2')
                ),
            },
        },
    }


def _serialize_closure_result(
        df_asinh: Optional[pd.DataFrame],
        df_sinh: Optional[pd.DataFrame],
        scenario: dict,
        warnings: List[dict],
) -> str:
    """Собрать итоговый JSON-ответ инструмента закрытия."""
    closing_vsps: List[dict] = []
    successors: List[dict] = []

    if df_asinh is not None and not df_asinh.empty:
        for code in scenario.get("closing_urf_list", []):
            record = _closing_vsp_record(df_asinh, code)
            if record is not None:
                closing_vsps.append(record)

    if df_sinh is not None and not df_sinh.empty:
        for _, row in df_sinh.iterrows():
            successors.append(_successor_record(row))

    payload = {
        "scenario": scenario,
        "closing_vsps": closing_vsps,
        "successors": successors,
        "warnings": warnings,
    }
    return json.dumps(payload, ensure_ascii=False)


@tool
def calculate_close_vsp(
        closing_urf_list: List[str],
        cs_urf_list: Optional[List[str]] = None,
) -> str:
    """
    Рассчитать последствия закрытия ВСП для банковской сети.

    Возвращает JSON-строку со структурой:
    ``{scenario, closing_vsps, successors, warnings}``.

    Args:
        closing_urf_list: коды ВСП для закрытия (например, ['8627_01710', '8627_01381']).
        cs_urf_list: коды ВСП для возврата в целевую сеть (опционально).
    """
    closing_filtered = [x for x in (closing_urf_list or []) if x and x.strip()]
    cs_filtered = [x for x in (cs_urf_list or []) if x and x.strip()]
    warnings: List[dict] = []
    scenario = {
        "closing_urf_list": closing_filtered,
        "cs_urf_list": cs_filtered,
    }

    if not closing_filtered:
        warnings.append({
            "code": "empty_closing_list",
            "message": "Не указаны ВСП для закрытия (closing_urf_list).",
        })
        return _serialize_closure_result(None, None, scenario, warnings)

    try:
        cs_vsp = VSPAnalyzer.to_naming(pd.read_excel('data/ЦС_ВСП_v8.xlsx'))
        known_vsp = set(cs_vsp['urf_code'])
        missing = [code for code in closing_filtered + cs_filtered if code not in known_vsp]
        if missing:
            warnings.append({
                "code": "unknown_vsp",
                "message": "ВСП не найдены в базе.",
                "items": missing,
            })
            return _serialize_closure_result(None, None, scenario, warnings)
    except FileNotFoundError:
        # Файл валидации отсутствует — пропускаем; основной расчёт упадёт ниже, если данных нет.
        pass

    logger.info(
        f"Запуск расчёта закрытия ВСП: closing={closing_filtered}, cs={cs_filtered}"
    )

    try:
        analyzer = VSPAnalyzer(
            is_close=closing_filtered,
            is_cs=cs_filtered,
            is_bt=[],
        )
        df_asinh, df_sinh, _ = analyzer.run_analysis(is_all_smrk=None)
    except FileNotFoundError:
        warnings.append({
            "code": "data_files_missing",
            "message": "Не найдены файлы данных (ЦС_ВСП_v8.xlsx или all_peretok.pickle).",
        })
        logger.error("calculate_close_vsp: файлы данных не найдены", exc_info=True)
        return _serialize_closure_result(None, None, scenario, warnings)
    except ValueError as e:
        warnings.append({
            "code": "no_overflow_data",
            "message": str(e),
        })
        logger.error(f"calculate_close_vsp: ValueError: {e}", exc_info=True)
        return _serialize_closure_result(None, None, scenario, warnings)
    except KeyError as e:
        warnings.append({
            "code": "unknown_vsp_in_data",
            "message": f"Не найдены ВСП в данных: {e}.",
        })
        logger.error(f"calculate_close_vsp: KeyError: {e}", exc_info=True)
        return _serialize_closure_result(None, None, scenario, warnings)
    except Exception as e:
        warnings.append({
            "code": "internal_error",
            "message": str(e),
        })
        logger.error(f"calculate_close_vsp: непредвиденная ошибка: {e}", exc_info=True)
        return _serialize_closure_result(None, None, scenario, warnings)

    result = _serialize_closure_result(df_asinh, df_sinh, scenario, warnings)
    logger.info(f"Расчёт закрытия завершён, длина JSON: {len(result)} символов")
    return result


@tool
def get_vsp_info(vsp_code: str) -> str:
    """
    Получает информацию о конкретном ВСП из базы данных.

    Args:
        vsp_code: Номер ВСП (например, '8627_01377')

    Returns:
        Текстовая информация о ВСП: адрес, показатели, площадь
    """
    try:

        cs_vsp = VSPAnalyzer.to_naming(pd.read_excel('data/ЦС_ВСП_v8.xlsx'))
        vsp_data = cs_vsp[cs_vsp['urf_code'] == vsp_code]

        if vsp_data.empty:
            return f"ВСП {vsp_code} не найден в базе данных"

        row = vsp_data.iloc[0]

        info_parts = [
            f"📍 ВСП {vsp_code}",
            f"Адрес: {row.get('address', 'н/д')}",
            f"Город: {row.get('city', 'н/д')} ({row.get('city_type', 'н/д')})",
            f" \n Показатели: ",
            f"  • Продажи УП: {row.get('sale_up', 0): .0f}",
            f"  • КП СКМ: {row.get('kp_skm', 0): .0f}",
            f"  • КП СМО: {row.get('kp_smo', 0): .0f}",
            f"  • Общий КП: {row.get('all_kp', 0): .0f}",
            f" \n Ресурсы: ",
            f"  • РМ СКМ: {row.get('rm_skm', 0): .0f}",
            f"  • РМ СМО: {row.get('rm_smo', 0): .0f}",
            f"  • Площадь факт: {row.get('fact_square', 0):.0f} м²",
            f"  • Площадь норм: {row.get('norm_square', 0):.0f} м²"
        ]

        return "\n".join(info_parts)

    except Exception as e:
        return f"❌ Ошибка при получении информации о ВСП: {str(e)}"
