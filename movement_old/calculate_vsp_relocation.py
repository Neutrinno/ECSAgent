"""Архив устаревшего инструмента перемещения ВСП.

Перенесено из `src/core/agents/network_optimizer_agent/network_optimizer_tools.py`.
В активном коде не используется (актуальный аналог живёт в `relocation_agent`).
Содержимое функции сохранено без изменений.
"""

from typing import List, Optional

import pandas as pd
from langchain_core.tools import tool

from src.core.agents.network_optimizer_agent.scripts.close_script import VSPAnalyzer
from movement_old.movement_script import RelocationModel
from src.utils.logger import get_logger

logger = get_logger(__name__)


@tool
def calculate_vsp_relocation(
        vsp_code: str,
        latitude: float,
        longitude: float,
        is_close: Optional[List[str]] = None,
        is_cs: Optional[List[str]] = None
) -> str:
    """
    Рассчитывает последствия перемещения ВСП на новое место.

    Args:
        vsp_code: Номер ВСП для перемещения (например, '8627_01377')
        latitude: Широта новой локации
        longitude: Долгота новой локации
        is_close: Список номеров ВСП для закрытия (опционально)
        is_cs: Список номеров ВСП для возврата в целевую сеть (опционально)

    Returns:
        Полный текстовый отчет с результатами расчета перемещения: информация о перемещаемом ВСП,
        перераспределение клиентов, все изменения показателей (УП, КП, ПШЕ, РМ), площади
    """
    try:
        is_close_filtered = [x for x in (is_close or []) if x and x.strip()]
        is_cs_filtered = [x for x in (is_cs or []) if x and x.strip()]

        if not vsp_code or not vsp_code.strip():
            return "❌ Ошибка: не указан ВСП для перемещения (vsp_code)."

        try:
            cs_vsp = VSPAnalyzer.to_naming(pd.read_excel('data/ЦС_ВСП_v8.xlsx'))
            known_vsp = set(cs_vsp['urf_code'])
            all_vsp_codes = [vsp_code] + is_close_filtered + is_cs_filtered
            missing_vsp = [code for code in all_vsp_codes if code not in known_vsp]
            if missing_vsp:
                return f"❌ Ошибка: ВСП не найдены в базе: {', '.join(missing_vsp)}. Проверьте коды (формат: XXXX_XXXXX)."
        except FileNotFoundError:
            pass

        logger.info(
            f"Запуск расчета перемещения ВСП: vsp_code={vsp_code}, координаты=({latitude}, {longitude}), "
            f"is_close={is_close_filtered}, is_cs={is_cs_filtered}")

        model = RelocationModel(is_close=is_close_filtered, is_cs=is_cs_filtered)
        try:
            df_result, df_bt = model.get_prediction(urf_code=vsp_code, coors=(latitude, longitude))
        except ValueError as e:

            msg = str(e)
            logger.warning(f"Валидация перемещения ВСП не пройдена: {msg}")
            if "Расчет перемещения возможен только на расстояние до 1.5 км" in msg:
                return (
                    "Ошибка валидации перемещения: точка перемещения слишком далеко.\n"
                    f"{msg}\n"
                    "Попробуйте указать координаты ближе к текущему ВСП (≤ 1.5 км)."
                )
            return f"Ошибка валидации перемещения: {msg}"

        if df_result.empty:
            return "Jшибка: не удалось рассчитать перемещение. Проверьте корректность параметров."

        report_parts = []

        report_parts.append("=" * 80)
        report_parts.append("ОТЧЕТ О РАСЧЕТЕ ПЕРЕМЕЩЕНИЯ ВСП")
        report_parts.append("=" * 80)

        report_parts.append("\nПАРАМЕТРЫ РАСЧЕТА:")
        report_parts.append(f"  • Перемещаемый ВСП: {vsp_code}")
        report_parts.append(f"  • Новые координаты: ({latitude:.6f}, {longitude:.6f})")
        if is_close_filtered:
            report_parts.append(f"  • ВСП для закрытия: {', '.join(is_close_filtered)}")
        if is_cs_filtered:
            report_parts.append(f"  • ВСП для возврата в сеть: {', '.join(is_cs_filtered)}")

        if not df_result.empty:
            report_parts.append("\n" + "=" * 80)
            report_parts.append("РЕЗУЛЬТАТЫ ПЕРЕРАСПРЕДЕЛЕНИЯ:")
            report_parts.append("=" * 80)

            for idx, row in df_result.iterrows():
                vsp_code_result = row.get('Код ВСП (изменяемое и на которые влияем)', 'н/д')
                address = row.get('Юр.адрес', 'н/д')
                city_type = row.get('Краткий тип НП', 'н/д')
                is_relocated = row.get('Ключ 1 (изменяемое ВСП) / 0 (ВСП ЛР)', 0)

                report_parts.append(f"\nВСП {vsp_code_result}:")
                report_parts.append(f"  Адрес: {address}")
                report_parts.append(f"  Тип НП: {city_type}")
                if is_relocated == 1:
                    new_lat = row.get('Новая широта', '')
                    new_lon = row.get('Новая долгота', '')
                    if new_lat and new_lon:
                        report_parts.append(f"  Новые координаты: ({new_lat}, {new_lon})")

                sale_up_near = row.get('Продажи УП СКМ', 0)
                kp_skm_near = row.get('КП СКМ', 0)
                kp_smo_near = row.get('КП СМО', 0)
                all_kp_near = row.get('Общий/СМРК КП', 0)
                is_smrk = row.get('Флаг СМРК', 0)

                report_parts.append(f"\n  ИСХОДНЫЕ ПОКАЗАТЕЛИ:")
                if sale_up_near > 0:
                    report_parts.append(f"    - Продажи УП: {sale_up_near:.0f}")
                if kp_skm_near > 0:
                    report_parts.append(f"    - КП СКМ: {kp_skm_near:.0f}")
                if kp_smo_near > 0:
                    report_parts.append(f"    - КП СМО: {kp_smo_near:.0f}")
                if all_kp_near > 0:
                    report_parts.append(f"    - Общий/СМРК КП: {all_kp_near:.0f}")
                report_parts.append(f"    - Режим СМРК: {'Да' if is_smrk == 1 else 'Нет'}")

                sale_overflow = row.get('Изменение УП', 0)
                kp_skm_overflow = row.get('Изменение КП СКМ', 0)
                kp_smo_overflow = row.get('Изменение КП СМО', 0)
                smrk_kp_overflow = row.get('Изменение КП СМРК', 0)

                if sale_overflow != 0 or kp_skm_overflow != 0 or kp_smo_overflow != 0:
                    report_parts.append(f"\n  ИЗМЕНЕНИЯ (ПЕРЕТОКИ):")
                    if sale_overflow != 0:
                        sign = '+' if sale_overflow > 0 else ''
                        report_parts.append(f"    - Изменение УП: {sign}{sale_overflow:.0f}")
                    if kp_skm_overflow != 0:
                        sign = '+' if kp_skm_overflow > 0 else ''
                        report_parts.append(f"    - Изменение КП СКМ: {sign}{kp_skm_overflow:.0f}")
                    if kp_smo_overflow != 0:
                        sign = '+' if kp_smo_overflow > 0 else ''
                        report_parts.append(f"    - Изменение КП СМО: {sign}{kp_smo_overflow:.0f}")
                    if smrk_kp_overflow != 0:
                        sign = '+' if smrk_kp_overflow > 0 else ''
                        report_parts.append(f"    - Изменение КП СМРК: {sign}{smrk_kp_overflow:.0f}")

                new_sale_up = row.get('Новый УП', 0)
                new_kp_skm = row.get('Новый КП СКМ', 0)
                new_kp_smo = row.get('Новый КП СМО', 0)
                new_smrk_kp = row.get('Новый общий/СМРК КП', 0)

                if new_sale_up > 0 or new_kp_skm > 0 or new_kp_smo > 0:
                    report_parts.append(f"\n  НОВЫЕ ПОКАЗАТЕЛИ (ПОСЛЕ ПЕРЕРАСПРЕДЕЛЕНИЯ):")
                    if new_sale_up > 0:
                        report_parts.append(f"    - Новый УП: {new_sale_up:.0f}")
                    if new_kp_skm > 0:
                        report_parts.append(f"    - Новый КП СКМ: {new_kp_skm:.0f}")
                    if new_kp_smo > 0:
                        report_parts.append(f"    - Новый КП СМО: {new_kp_smo:.0f}")
                    if new_smrk_kp > 0:
                        report_parts.append(f"    - Новый общий/СМРК КП: {new_smrk_kp:.0f}")

                # ПШЕ показатели
                pshe_skm_near = row.get('ПШЕ СКМ', 0)
                pshe_smo_near = row.get('ПШЕ СМО', 0)
                pshe_smrk_near = row.get('ПШЕ СМРК', 0)
                pshe_skm_calc = row.get('ПШЕ СКМ расч.', 0)
                pshe_smo_calc = row.get('ПШЕ СМО расч.', 0)
                pshe_smrk_calc = row.get('ПШЕ СМРК расч.', 0)

                new_pshe_skm = row.get('Итого необходимо ПШЕ СКМ', 0)
                new_pshe_smo = row.get('Итого необходимо ПШЕ СМО', 0)
                new_pshe_smrk = row.get('Итого необходимо ПШЕ СМРК', 0)
                new_pshe_skm_calc = row.get('Новый ПШЕ СКМ', 0)
                new_pshe_smo_calc = row.get('Новый ПШЕ СМО', 0)
                new_pshe_smrk_calc = row.get('Новый ПШЕ СМРК', 0)

                delta_pshe_skm = row.get('Изменение ПШЕ СКМ с учетом нагрузки', 0)
                delta_pshe_smo = row.get('Изменение ПШЕ СМО с учетом нагрузки', 0)
                delta_pshe_smrk = row.get('Изменение ПШЕ СМРК с учетом нагрузки', 0)

                if pshe_skm_near > 0 or pshe_smo_near > 0 or pshe_smrk_near > 0:
                    report_parts.append(f"\n  ПШЕ (ПОЛНЫЕ ШТАТНЫЕ ЕДИНИЦЫ):")
                    report_parts.append(f"    Текущие:")
                    if pshe_skm_near > 0:
                        report_parts.append(f"      - ПШЕ СКМ: {pshe_skm_near:.0f} (расч.: {pshe_skm_calc:.2f})")
                    if pshe_smo_near > 0:
                        report_parts.append(f"      - ПШЕ СМО: {pshe_smo_near:.0f} (расч.: {pshe_smo_calc:.2f})")
                    if pshe_smrk_near > 0:
                        report_parts.append(f"      - ПШЕ СМРК: {pshe_smrk_near:.0f} (расч.: {pshe_smrk_calc:.2f})")

                    if new_pshe_skm > 0 or new_pshe_smo > 0 or new_pshe_smrk > 0:
                        report_parts.append(f"    Новые (после перераспределения):")
                        if new_pshe_skm > 0:
                            report_parts.append(f"      - ПШЕ СКМ: {new_pshe_skm:.0f} (расч.: {new_pshe_skm_calc:.2f})")
                        if new_pshe_smo > 0:
                            report_parts.append(f"      - ПШЕ СМО: {new_pshe_smo:.0f} (расч.: {new_pshe_smo_calc:.2f})")
                        if new_pshe_smrk > 0:
                            report_parts.append(f"      - ПШЕ СМРК: {new_pshe_smrk:.0f} (расч.: {new_pshe_smrk_calc:.2f})")

                    if delta_pshe_skm != 0 or delta_pshe_smo != 0 or delta_pshe_smrk != 0:
                        report_parts.append(f"    Изменения:")
                        if delta_pshe_skm != 0:
                            sign = '+' if delta_pshe_skm > 0 else ''
                            report_parts.append(f"      - Изменение ПШЕ СКМ: {sign}{delta_pshe_skm:.2f}")
                        if delta_pshe_smo != 0:
                            sign = '+' if delta_pshe_smo > 0 else ''
                            report_parts.append(f"      - Изменение ПШЕ СМО: {sign}{delta_pshe_smo:.2f}")
                        if delta_pshe_smrk != 0:
                            sign = '+' if delta_pshe_smrk > 0 else ''
                            report_parts.append(f"      - Изменение ПШЕ СМРК: {sign}{delta_pshe_smrk:.2f}")

                # РМ показатели
                rm_skm = row.get('РМ СКМ', 0)
                rm_smo = row.get('РМ СМО', 0)
                rm_smrk = row.get('РМ СМРК', 0)
                new_rm_skm = row.get('Итого необходимо РМ СКМ', 0)
                new_rm_smo = row.get('Итого необходимо РМ СМО', 0)
                new_rm_smrk = row.get('Итого необходимо РМ СМРК', 0)
                delta_rm_skm = row.get('Требуемое кол-во дополнительных РМ СКМ с учетом изменения УП', 0)
                delta_rm_smo = row.get('Требуемое кол-во дополнительных РМ СМО с учетом изменения КП', 0)
                delta_rm_smrk = row.get('Требуемое кол-во дополнительных РМ СМРК с учетом изменения КП', 0)

                if rm_skm > 0 or rm_smo > 0 or rm_smrk > 0:
                    report_parts.append(f"\n  РМ (РАБОЧИЕ МЕСТА):")
                    report_parts.append(f"    Текущие:")
                    if rm_skm > 0:
                        report_parts.append(f"      - РМ СКМ: {rm_skm:.0f}")
                    if rm_smo > 0:
                        report_parts.append(f"      - РМ СМО: {rm_smo:.0f}")
                    if rm_smrk > 0:
                        report_parts.append(f"      - РМ СМРК: {rm_smrk:.0f}")

                    if new_rm_skm > 0 or new_rm_smo > 0 or new_rm_smrk > 0:
                        report_parts.append(f"    Новые (после перераспределения):")
                        if new_rm_skm > 0:
                            report_parts.append(f"      - РМ СКМ: {new_rm_skm:.0f}")
                        if new_rm_smo > 0:
                            report_parts.append(f"      - РМ СМО: {new_rm_smo:.0f}")
                        if new_rm_smrk > 0:
                            report_parts.append(f"      - РМ СМРК: {new_rm_smrk:.0f}")

                    if delta_rm_skm > 0 or delta_rm_smo > 0 or delta_rm_smrk > 0:
                        report_parts.append(f"    Требуется дополнительно:")
                        if delta_rm_skm > 0:
                            report_parts.append(f"      - РМ СКМ: +{delta_rm_skm:.0f}")
                        if delta_rm_smo > 0:
                            report_parts.append(f"      - РМ СМО: +{delta_rm_smo:.0f}")
                        if delta_rm_smrk > 0:
                            report_parts.append(f"      - РМ СМРК: +{delta_rm_smrk:.0f}")

                # Площади
                norm_square = row.get('Площадь норм, м2', 0)
                fact_square = row.get('Площадь факт, м2', 0)
                diff_square = row.get('Дефицит (-)/Избыток (+)', 0)
                new_norm_square = row.get('Нормативная площадь после закрытия ВСП, м2', 0)
                new_diff_square = row.get('Дефицит (-) / Излишек (+) площади после закрытия ВСП, м2', 0)
                dop_square_skm = row.get('Требуемая доп.площадь под СКМ', 0)
                dop_square_smo = row.get('Требуемая доп.площадь под СМО', 0)
                dop_square_smrk = row.get('Требуемая доп.площадь под СМРК', 0)

                if norm_square > 0 or fact_square > 0:
                    report_parts.append(f"\n  📐 ПЛОЩАДИ:")
                    report_parts.append(f"    Текущие:")
                    if norm_square > 0:
                        report_parts.append(f"      - Нормативная площадь: {norm_square:.0f} м²")
                    if fact_square > 0:
                        report_parts.append(f"      - Фактическая площадь: {fact_square:.0f} м²")
                    if diff_square != 0:
                        if diff_square < 0:
                            report_parts.append(f"      - Дефицит: {abs(diff_square):.0f} м²")
                        else:
                            report_parts.append(f"      - Избыток: {diff_square:.0f} м²")

                    if new_norm_square > 0:
                        report_parts.append(f"    После перемещения ВСП:")
                        report_parts.append(f"      - Нормативная площадь: {new_norm_square:.0f} м²")
                        if new_diff_square != 0:
                            if new_diff_square < 0:
                                report_parts.append(f"      - Дефицит: {abs(new_diff_square):.0f} м²")
                            else:
                                report_parts.append(f"      - Избыток: {new_diff_square:.0f} м²")

                    total_dop_square = dop_square_skm + dop_square_smo + dop_square_smrk
                    if total_dop_square > 0:
                        report_parts.append(f"    Требуется дополнительно:")
                        if dop_square_skm > 0:
                            report_parts.append(f"      - Под СКМ: {dop_square_skm:.0f} м²")
                        if dop_square_smo > 0:
                            report_parts.append(f"      - Под СМО: {dop_square_smo:.0f} м²")
                        if dop_square_smrk > 0:
                            report_parts.append(f"      - Под СМРК: {dop_square_smrk:.0f} м²")
                        report_parts.append(f"      - ИТОГО: {total_dop_square:.0f} м²")

        report_parts.append("\n" + "=" * 80)
        report_parts.append("Конец отчета")
        report_parts.append("=" * 80)

        result = "\n".join(report_parts)
        logger.info(f"Расчет перемещения завершен успешно, длина отчета: {len(result)} символов")
        return result

    except FileNotFoundError as e:
        error_msg = f"Ошибка: не найдены файлы данных (ЦС_ВСП_v8.xlsx или vsp_move_scores.feather). Проверьте наличие файлов."
        logger.error(error_msg)
        return error_msg
    except ValueError as e:

        error_msg = f"❌ Ошибка валидации перемещения: {str(e)}"
        logger.warning(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Ошибка при расчете перемещения: {str(e)}. Проверьте корректность кодов ВСП и координат."
        logger.error(f"Ошибка расчета перемещения ВСП: {e}", exc_info=True)
        return error_msg
