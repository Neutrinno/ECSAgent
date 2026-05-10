from typing import List, Dict, Optional, Any
from datetime import datetime
import pandas as pd
from sqlalchemy.orm import Session
from pathlib import Path
import ast

from src.database.models import (
    VSPCore, VSPAddress, VSPTimeline, VSPArea,
    VSPWorkplace, VSPOperations, VSPProperty
)
from src.database.service import SQLiteService
from src.utils.logger import get_logger

logger = get_logger(__name__)


class VSPDataProcessor:
    def __init__(self, db_service: SQLiteService):
        self.db_service = db_service
        self.cities_dict = self._load_cities_dict()

        self.field_mapping = {
            'Дата отчёта': 'report_dt',
            'Стандартный urf_code': 'urf_code',
            'ТБ (наименование)': 'tb_name',
            'ГОСБ№': 'gosb_id',
            'Тип ВСП': 'vsp_type',
            'Бизнес-формат': 'business_format',
            'Дата переформата ВСП': 'reformat_dt',
            'Плановая дата переформата ВСП': 'vsp_reformat_end_dt',
            'Плановая дата закрытия ВСП': 'plan_close_dt',
            'Признак ВСП закрытого тип (1=ОО GR, 2 = отдельный ЦПО)': 'close_type_flag',
            'Флаг села (1=село, 0=город)': 'is_village',
            'Фантом (выверенные данные; 1 - фантом, 0 - не фантом)': 'is_fantom',
            'Тип населенного пункта': 'city_type',
            'id населенного пункта': 'city_id',
            'Город': 'city',
            'Кол-во рабочих ВСП в населенном пункте': 'city_vsp_qty',
            'Регион': 'region',
            'Широта юр.адреса ВСП': 'legal_address_latitude',
            'Долгота юр.адреса ВСП': 'legal_address_longitude',
            'Юридический адрес ВСП': 'legal_address',
            'Фактический адрес ВСП': 'fact_address',
            'Широта факт.адреса ВСП': 'vsp_fact_address_latitude',
            'Долгота факт.адреса ВСП': 'vsp_fact_address_longitude',
            'Общая нормативная площадь, м2': 'normative_area',
            'Нормативная площадь БСП, м2': 'normative_rb_area',
            'Нормативная площадь ЦПО, м2': 'norm_cpo_area',
            'Нормативная площадь КИБ, м2': 'normative_cb_area',
            'Нормативная площадь РБ ЦИК, м2': 'normative_cik_area',
            'Нормативная площадь элементов Экосистемы, м2': 'normative_eco_area',
            'Нормативная площадь ВИП-ВСП, м2': 'norm_vip_area',
            'Расчетный дефицит (-) /излишек (+) площади ВСП, м.кв.': 'diff_area',
            'Расчетный дефицит (-) /излишек (+) площади БСП, м2': 'diff_area_bsp',
            'Расчетный дефицит (-) /излишек (+) площади ЦПО, м2': 'diff_area_cpo',
            'Расчетный дефицит (-) /излишек (+) площади ЦИК, м2': 'diff_area_cik',
            'Расчетный дефицит (-) /излишек (+) площади КИБ, м2': 'diff_area_cib',
            'Расчетный дефицит (-) /излишек (+) площади ВИП-ВСП, м2': 'diff_area_vip',
            'Возможность обособления (1 - обосабливать/доработка, 0 - не обосабливать)': 'is_mb_isolated',
            'СБР - Общая фактическая площадь, м2 (АСУН)': 'total_area',
            'СБР - Основная площадь ВСП': 'main_area',
            'СБР - Вспомогательная площадь ВСП': 'aux_area',
            'СБР - Площадь БСП': 'bsp_area',
            'СБР-Площадь ЦПО на орг единицах БСП': 'cpo_bsp_area',
            'СБР-Площадь ЦПО': 'cpo_area',
            'СБР Площадь ЦИК РБ': 'cik_area',
            'СБР - Площадь КИБ': 'kib_area',
            'СБР - Площадь ВИП ВСП': 'vip_area',
            'РМ РВСП': 'wp_rvsp_cnt',
            'РМ ЗРВСП': 'wp_zrvsp_cnt',
            'РМ РЦПО': 'wp_rrcpo_cnt',
            'РМ РВИП ВСП': 'wp_rvsp_vip_cnt',
            'РМ СКМ': 'wp_mp_cnt',
            'РМ СМО': 'wp_smo_cnt',
            'РМ СМРК': 'wp_smrk_cnt',
            'РМ МРК': 'wp_mrk_cnt',
            'РМ КМ премиум-сегмента': 'wp_premier_cnt',
            'РМ ВИП': 'wp_vip_cnt',
            'РМ РЦИК': 'wp_rcik_cnt',
            'РМ МИК': 'wp_mik_cnt',
            'РМ МОИК': 'wp_moik_cnt',
            'Руководитель точки продаж (КБ)': 'wp_manager_point_sale_cnt',
            'РМ КМ МКК (КБ)': 'wp_km_mkk_cnt',
            'РМ КМ малого и микро-бизнеса (КБ)': 'wp_km_mmb_cnt',
            'РМ ГКМ (КБ)': 'wp_akm_cb_cnt',
            'ПШЕ СМО (ИУЧ)': 'pse_smo_cnt',
            'ПШЕ СКМ (ИУЧ)': 'pse_mp_cnt',
            'ПШЕ МИК (целевое)': 'pse_mik_cnt',
            'ПШЕ МОИК (целевое)': 'pse_moik_cnt',
            'ПШЕ СМРК (ИУЧ)': 'pse_smrk_cnt',
            'ПШЕ МРК (ИУЧ)': 'pse_mrk_cnt',
            'Плановое число рабочих мест БСП и ЦПО': 'wp_plan_rb_cnt',
            'Плановое число рабочих мест ЦИК': 'wp_plan_cik_cnt',
            'Плановое число рабочих мест КБ': 'wp_plan_cb_cnt',
            'Плановое число рабочих мест ВИП': 'wp_plan_vip_cnt',
            'Общее плановое число рабочих мест': 'wp_plan_cnt',
            'Количество переговорных комнат ЦИК': 'meetrig_room_cnt',
            'Количество УС (всех видов)': 'us_cnt',
            'Площадь ХЦК, м2': 'area_hck',
            'ХЦК в целевой сети (флаг)': 'has_hck',
            'Количество рабочих дней ВСП в неделю (данные за полгода)': 'work_day_week_6_m_qty',
            'Рабочее время сотрудника ВСП в неделю с исключением обеда (данные за полгода)': 'emp_work_week_6_m_h_cnt',
            'Рабочее время ВСП в неделю (данные за полгода)': 'vsp_work_week_6_m_h_cnt',
            'Дни работы ВСП (общее)': 'vsp_work_dt',
            'Право на помещение ВСП (аренда, собственность)': 'form_rght_name',
            'Доля помещения ВСП в собственности': 'ownership_area_perc',
            'Средняя ставка аренды  (руб. в мес. за м2 с учетом НДС)': 'rent_rate_avg',
            'Средняя ставка вмененной аренды  (руб. в мес. за м2)': 'rpi_rate_avg_area',
            'СБР - Фактическая площадь на 1 РМ': 'rm_norm_area',
            'Продажи УП': 'up_kp',
            'КП СКМ': 'kp_skm',
            'КП СМО': 'kp_smo',
            'КП СМРК': 'kp_smrk',
            'Общий КП': 'all_kp',
            'Транзакртные операции': 'oper_transakt',
            'Продажные операции': 'oper_sale',
            'Всего операций': 'all_oper',
        }

    @staticmethod
    def _load_cities_dict() -> Dict[str, str]:
        """
        Загружает словарь соответствия city_id -> city_short из файла cities_cleaned.txt
        """
        current_file_dir = Path(__file__).parent
        project_root = current_file_dir.parent.parent
        cities_file = project_root / "data" / "cities_cleaned.txt"

        if not cities_file.exists():
            logger.warning(f"Файл со словарем городов не найден: {cities_file}")
            return {}

        try:
            with open(cities_file, 'r', encoding='utf-8') as f:
                content = f.read()
                cities_dict = ast.literal_eval(content)
                logger.info(f"Загружено {len(cities_dict)} соответствий city_id -> city_short")
                return cities_dict
        except Exception as e:
            logger.error(f"Ошибка при загрузке словаря городов: {str(e)}")
            return {}

    def process(self, file_path: Path) -> bool:
        """
        Основной метод обработки файла
        """
        try:
            if not isinstance(file_path, Path):
                file_path = Path(file_path)

            data = self._read_all_data(file_path)
            if not data:
                logger.error("No data extracted from file")
                return False

            with self.db_service.get_session() as session:
                self._save_to_database(session, data)

            return True
        except Exception as e:
            logger.error(f"Processing failed: {str(e)}")
            return False

    @staticmethod
    def _make_gosb_vsp(urf_code: Any) -> Optional[str]:
        """
        Из urf_code вида tb_gosb_vsp формирует строку gosb_vsp = "gosb_vsp" (последние 2 сегмента).
        Примеры:
        - "019_1203_231" -> "1203_231"
        - "121_0213_2100" -> "0213_2100"
        """
        if urf_code is None:
            return None
        s = str(urf_code).strip()
        if not s:
            return None
        parts = [p for p in s.split("_") if p != ""]
        if len(parts) < 2:
            return None
        return "_".join(parts[-2:])

    def _read_all_data(self, file_path: Path) -> List[Dict]:
        """
        Чтение всех данных из файла
        """
        try:
            df_headers = pd.read_excel(
                file_path,
                header=None,
                nrows=2,
                engine='openpyxl'
            )

            if df_headers.shape[1] < 5:
                logger.error("File has too few columns")
                return []

            russian_headers = df_headers.iloc[0].tolist()
            english_headers = df_headers.iloc[1].tolist()

            column_mapping = {}
            for idx, (rus_header, eng_header) in enumerate(zip(russian_headers, english_headers)):
                if pd.isna(rus_header) or pd.isna(eng_header):
                    continue

                rus_str = str(rus_header).strip()
                eng_str = str(eng_header).strip()

                mapped_field = self.field_mapping.get(rus_str, eng_str)
                column_mapping[idx] = mapped_field

            logger.info(f"Mapped {len(column_mapping)} columns")

            df_data = pd.read_excel(
                file_path,
                header=None,
                skiprows=2,
                engine='openpyxl'
            )

            data = []
            for row_idx, row in df_data.iterrows():
                try:
                    row_data = self._extract_row_data(row, column_mapping)
                    if row_data and self._validate_row(row_data):
                        data.append(row_data)
                except Exception as e:
                    logger.warning(f"Error processing row {row_idx}: {str(e)}")
                    continue

            logger.info(f"Extracted {len(data)} valid records")
            return data

        except Exception as e:
            logger.error(f"Error reading file: {str(e)}")
            return []

    def _extract_row_data(self, row: pd.Series, column_mapping: Dict[int, str]) -> Optional[Dict]:
        """
        Извлечение данных из одной строки
        """
        try:
            row_data = {}

            for col_idx, field_name in column_mapping.items():
                if col_idx < len(row):
                    value = row[col_idx]

                    if pd.isna(value):
                        value = None
                    elif field_name in ['report_dt', 'reformat_dt', 'vsp_reformat_end_dt', 'plan_close_dt']:
                        value = self._convert_date(value)
                    elif field_name in ['is_village', 'is_fantom', 'is_mb_isolated', 'has_hck', 'close_type_flag']:
                        value = self._convert_to_int(value)

                    row_data[field_name] = value

            if 'urf_code' not in row_data or not row_data['urf_code']:
                return None

            return row_data

        except Exception as e:
            logger.error(f"Error extracting row data: {str(e)}")
            return None

    @staticmethod
    def _convert_date(value: Any) -> Optional[datetime.date]:
        """
        Конвертация значения в дату
        """
        if pd.isna(value):
            return None
        elif isinstance(value, datetime):
            return value.date()
        elif isinstance(value, pd.Timestamp):
            return value.date()
        elif isinstance(value, str):
            try:
                for fmt in ['%d.%m.%Y', '%Y-%m-%d', '%d/%m/%Y', '%Y.%m.%d']:
                    try:
                        return datetime.strptime(value, fmt).date()
                    except ValueError:
                        continue
            except Exception:
                return None
        return None

    @staticmethod
    def _convert_to_int(value: Any) -> Optional[int]:
        """
        Конвертация значения в целое число
        """
        if pd.isna(value):
            return None
        try:
            if isinstance(value, (int, float)):
                return int(value)
            elif isinstance(value, str):
                cleaned = value.strip()
                if cleaned.lower() in ['да', 'true', 'yes', '+']:
                    return 1
                elif cleaned.lower() in ['нет', 'false', 'no', '-']:
                    return 0
                elif cleaned.replace('.', '', 1).isdigit():
                    return int(float(cleaned))
        except Exception:
            return None
        return None

    @staticmethod
    def _validate_row(row_data: Dict) -> bool:
        """
        Валидация строки данных
        """
        required_fields = ['urf_code', 'report_dt']
        return all(row_data.get(field) for field in required_fields)

    def _save_to_database(self, session: Session, data: List[Dict]):
        """
        Сохранение данных в соответствующие таблицы
        """
        if not data:
            logger.info("No data to save")
            return

        try:
            core_data = []
            address_data = []
            timeline_data = []
            area_data = []
            workplace_data = []
            operations_data = []
            property_data = []

            for record in data:
                # VSPCore
                urf_code = record.get('urf_code')
                gosb_vsp = self._make_gosb_vsp(urf_code)

                city_id = record.get('city_id')
                city_short = None
                if city_id and self.cities_dict:
                    city_id_str = str(city_id).strip()
                    city_short = self.cities_dict.get(city_id_str)

                core_record = {
                    'urf_code': urf_code,
                    'gosb_vsp': gosb_vsp,
                    'report_dt': record.get('report_dt'),
                    'tb_name': record.get('tb_name'),
                    'gosb_id': record.get('gosb_id'),
                    'vsp_type': record.get('vsp_type'),
                    'business_format': record.get('business_format'),
                    'region': record.get('region'),
                    'city_id': city_id,
                    'city': record.get('city'),
                    'city_short': city_short,
                    'city_type': record.get('city_type'),
                    'is_village': record.get('is_village'),
                    'is_fantom': record.get('is_fantom'),
                    'city_vsp_qty': record.get('city_vsp_qty'),
                    'is_mb_isolated': record.get('is_mb_isolated'),
                }
                core_data.append(core_record)

                # VSPAddress
                address_record = {
                    'urf_code': record.get('urf_code'),
                    'report_dt': record.get('report_dt'),
                    'legal_address': record.get('legal_address'),
                    'legal_address_latitude': record.get('legal_address_latitude'),
                    'legal_address_longitude': record.get('legal_address_longitude'),
                    'fact_address': record.get('fact_address'),
                    'vsp_fact_address_latitude': record.get('vsp_fact_address_latitude'),
                    'vsp_fact_address_longitude': record.get('vsp_fact_address_longitude'),
                }
                address_data.append(address_record)

                # VSPTimeline
                timeline_record = {
                    'urf_code': record.get('urf_code'),
                    'report_dt': record.get('report_dt'),
                    'reformat_dt': record.get('reformat_dt'),
                    'vsp_reformat_end_dt': record.get('vsp_reformat_end_dt'),
                    'plan_close_dt': record.get('plan_close_dt'),
                    'close_type_flag': record.get('close_type_flag'),
                    'vsp_work_dt': record.get('vsp_work_dt'),
                    'work_day_week_6_m_qty': record.get('work_day_week_6_m_qty'),
                    'emp_work_week_6_m_h_cnt': record.get('emp_work_week_6_m_h_cnt'),
                    'vsp_work_week_6_m_h_cnt': record.get('vsp_work_week_6_m_h_cnt'),
                }
                timeline_data.append(timeline_record)

                # VSPArea
                area_record = {
                    'urf_code': record.get('urf_code'),
                    'report_dt': record.get('report_dt'),
                    'normative_area': record.get('normative_area'),
                    'normative_rb_area': record.get('normative_rb_area'),
                    'norm_cpo_area': record.get('norm_cpo_area'),
                    'normative_cb_area': record.get('normative_cb_area'),
                    'normative_cik_area': record.get('normative_cik_area'),
                    'normative_eco_area': record.get('normative_eco_area'),
                    'norm_vip_area': record.get('norm_vip_area'),
                    'total_area': record.get('total_area'),
                    'main_area': record.get('main_area'),
                    'aux_area': record.get('aux_area'),
                    'bsp_area': record.get('bsp_area'),
                    'cpo_bsp_area': record.get('cpo_bsp_area'),
                    'cpo_area': record.get('cpo_area'),
                    'cik_area': record.get('cik_area'),
                    'kib_area': record.get('kib_area'),
                    'vip_area': record.get('vip_area'),
                    'diff_area': record.get('diff_area'),
                    'diff_area_bsp': record.get('diff_area_bsp'),
                    'diff_area_cpo': record.get('diff_area_cpo'),
                    'diff_area_cik': record.get('diff_area_cik'),
                    'diff_area_cib': record.get('diff_area_cib'),
                    'diff_area_vip': record.get('diff_area_vip'),
                    'area_hck': record.get('area_hck'),
                    'has_hck': record.get('has_hck'),
                    'rm_norm_area': record.get('rm_norm_area'),
                }
                area_data.append(area_record)

                # VSPWorkplace
                workplace_record = {
                    'urf_code': record.get('urf_code'),
                    'report_dt': record.get('report_dt'),
                    'wp_rvsp_cnt': record.get('wp_rvsp_cnt'),
                    'wp_zrvsp_cnt': record.get('wp_zrvsp_cnt'),
                    'wp_rrcpo_cnt': record.get('wp_rrcpo_cnt'),
                    'wp_rvsp_vip_cnt': record.get('wp_rvsp_vip_cnt'),
                    'wp_mp_cnt': record.get('wp_mp_cnt'),
                    'wp_smo_cnt': record.get('wp_smo_cnt'),
                    'wp_smrk_cnt': record.get('wp_smrk_cnt'),
                    'wp_mrk_cnt': record.get('wp_mrk_cnt'),
                    'wp_premier_cnt': record.get('wp_premier_cnt'),
                    'wp_vip_cnt': record.get('wp_vip_cnt'),
                    'wp_rcik_cnt': record.get('wp_rcik_cnt'),
                    'wp_mik_cnt': record.get('wp_mik_cnt'),
                    'wp_moik_cnt': record.get('wp_moik_cnt'),
                    'wp_manager_point_sale_cnt': record.get('wp_manager_point_sale_cnt'),
                    'wp_km_mkk_cnt': record.get('wp_km_mkk_cnt'),
                    'wp_km_mmb_cnt': record.get('wp_km_mmb_cnt'),
                    'wp_akm_cb_cnt': record.get('wp_akm_cb_cnt'),
                    'wp_plan_rb_cnt': record.get('wp_plan_rb_cnt'),
                    'wp_plan_cik_cnt': record.get('wp_plan_cik_cnt'),
                    'wp_plan_cb_cnt': record.get('wp_plan_cb_cnt'),
                    'wp_plan_vip_cnt': record.get('wp_plan_vip_cnt'),
                    'wp_plan_cnt': record.get('wp_plan_cnt'),
                    'pse_smo_cnt': record.get('pse_smo_cnt'),
                    'pse_mp_cnt': record.get('pse_mp_cnt'),
                    'pse_mik_cnt': record.get('pse_mik_cnt'),
                    'pse_moik_cnt': record.get('pse_moik_cnt'),
                    'pse_smrk_cnt': record.get('pse_smrk_cnt'),
                    'pse_mrk_cnt': record.get('pse_mrk_cnt'),
                    'meetrig_room_cnt': record.get('meetrig_room_cnt'),
                    'us_cnt': record.get('us_cnt'),
                }
                workplace_data.append(workplace_record)

                # VSPOperations
                operations_record = {
                    'urf_code': record.get('urf_code'),
                    'report_dt': record.get('report_dt'),
                    'up_kp': record.get('up_kp'),
                    'kp_skm': record.get('kp_skm'),
                    'kp_smo': record.get('kp_smo'),
                    'kp_smrk': record.get('kp_smrk'),
                    'all_kp': record.get('all_kp'),
                    'oper_transakt': record.get('oper_transakt'),
                    'oper_sale': record.get('oper_sale'),
                    'all_oper': record.get('all_oper'),
                }
                operations_data.append(operations_record)

                # VSPProperty
                property_record = {
                    'urf_code': record.get('urf_code'),
                    'report_dt': record.get('report_dt'),
                    'form_rght_name': record.get('form_rght_name'),
                    'ownership_area_perc': record.get('ownership_area_perc'),
                    'rent_rate_avg': record.get('rent_rate_avg'),
                    'rpi_rate_avg_area': record.get('rpi_rate_avg_area'),
                }
                property_data.append(property_record)

            self._bulk_save(session, VSPCore, core_data)
            self._bulk_save(session, VSPAddress, address_data)
            self._bulk_save(session, VSPTimeline, timeline_data)
            self._bulk_save(session, VSPArea, area_data)
            self._bulk_save(session, VSPWorkplace, workplace_data)
            self._bulk_save(session, VSPOperations, operations_data)
            self._bulk_save(session, VSPProperty, property_data)

            session.commit()
            logger.info(f"Successfully saved {len(data)} records to database")

        except Exception as e:
            session.rollback()
            logger.error(f"Error saving to database: {str(e)}")
            raise

    @staticmethod
    def _bulk_save(session: Session, model_class, data: List[Dict]):
        """
        Массовое сохранение данных
        """
        if not data:
            return

        try:
            unique_data = {}
            for record in data:
                key = (record['urf_code'], record['report_dt'])
                unique_data[key] = record

            session.bulk_insert_mappings(model_class, list(unique_data.values()))
            logger.info(f"Saved {len(unique_data)} records to {model_class.__tablename__}")

        except Exception as e:
            logger.error(f"Error in bulk save to {model_class.__tablename__}: {str(e)}")
            raise


def main():
    """
    Основная функция для запуска обработки
    """
    logger = get_logger(__name__)
    logger.info("Запуск обработки файла с данными ВСП")

    project_root = Path(__file__).resolve().parents[2]
    file_path = project_root / "data" / "Отчет по площади.xlsx"

    if not file_path.exists():
        logger.error(f"Файл не найден: {file_path}")
        return False

    logger.info(f"Обрабатываем файл: {file_path.name}")

    try:
        db_service = SQLiteService()
        processor = VSPDataProcessor(db_service)

        logger.info("Начинаем обработку файла...")
        success = processor.process(file_path)

        if success:
            logger.info("✅ Обработка завершена УСПЕШНО!")
        else:
            logger.error("❌ Обработка завершена с ОШИБКАМИ!")

        return success

    except Exception as e:
        logger.error(f"КРИТИЧЕСКАЯ ОШИБКА при обработке: {str(e)}")
        logger.exception("Трассировка стека:")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
