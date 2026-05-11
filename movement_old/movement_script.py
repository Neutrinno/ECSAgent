import math
import pandas as pd
import numpy as np
from src.utils.logger import get_logger

logger = get_logger(__name__)


class RelocationModel():
    """
    Class for vsp relocation ML model implemented for server app
    """

    def __init__(self, is_close, is_cs):
        self.is_close = is_close
        self.is_cs = is_cs

        self.distance_relocate = 2
        self.radius_lr = 1.5
        self.max_distance_to_near = 2
        # Данные — в той же папке, что и у close_script.py
        self._vsp_data = pd.read_excel('data/ЦС_ВСП_v8.xlsx')

        # Перенести в init и добавить is_cs
        self._vsp_data['Доля талонов МП в ВСП'] = self._vsp_data['КП СКМ'] / self._vsp_data['Общий КП'].replace(0,
                                                                                                                np.nan)
        self._vsp_data['Доля талонов МП в ВСП'] = self._vsp_data['Доля талонов МП в ВСП'].fillna(0)
        self._vsp_data['Нормативный КП СМО в мес. на 1 ПШЕ'] = 1400

    def validate(self, is_reloc_vsp, coors):
        latitude, longitude = coors
        latitude_value = self._vsp_data.loc[self._vsp_data['Код ВСП'] == is_reloc_vsp, 'Широта'].iloc[0]
        longitude_value = self._vsp_data.loc[self._vsp_data['Код ВСП'] == is_reloc_vsp, 'Долгота'].iloc[0]
        distance_relocate = self.get_distance(latitude_value, longitude_value, latitude, longitude)
        if distance_relocate > 1.5:
            raise ValueError(
                f'Расчет перемещения возможен только на расстояние до 1.5 км, а данном случае: {distance_relocate}')

        close_df = self._vsp_data.loc[
            ((self._vsp_data['Флаг закрытия'] == 1) & ~(self._vsp_data['Код ВСП'].isin(self.is_cs))) | (
                self._vsp_data['Код ВСП'].isin(self.is_close))]
        close_df['distance_to_new_loc'] = close_df[['Широта', 'Долгота']].apply(lambda row: self.get_distance(
            row['Широта'], row['Долгота'],
            latitude, longitude
        ), axis=1)
        close_df['is_near'] = close_df['distance_to_new_loc'] > distance_relocate
        nearest_vsp = close_df.query('is_near==False').sort_values('distance_to_new_loc')

        if nearest_vsp.shape[0] > 0:
            raise ValueError(
                f'К локации перемещения есть более близкое ВСП-закрытие, перемещать следует его: {nearest_vsp["Код ВСП"].iloc[0]}')

        return self._vsp_data[
            ((self._vsp_data['Флаг закрытия'] == 0) | (self._vsp_data['Код ВСП'].isin(self.is_cs))) & (
                ~self._vsp_data['Код ВСП'].isin(self.is_close))]

    #         print('init')

    @staticmethod
    def get_distance(lat_1, lng_1, lat_2, lng_2):
        lng_1, lat_1, lng_2, lat_2 = map(math.radians, [lng_1, lat_1, lng_2, lat_2])
        d_lat = lat_2 - lat_1
        d_lng = lng_2 - lng_1
        temp = (
                math.sin(d_lat / 2) ** 2
                + math.cos(lat_1)
                * math.cos(lat_2)
                * math.sin(d_lng / 2) ** 2
        )
        return 6373.0 * (2 * math.atan2(math.sqrt(temp), math.sqrt(1 - temp)))

    @staticmethod
    def calculate_intersection_parameters(initial_distance, current_distance, radius, cnt_clients_rel,
                                          cnt_clients_near):
        """
        Расчет параметров пересечения двух окружностей (ЛР)

        Параметры:
        initial_distance - исходное расстояние между центрами
        current_distance - текущее расстояние между центрами
        radius - радиус обеих окружностей
        cnt_clients_rel - количество клиентов в передвигаемом круге
        cnt_clients_near - количество клиентов в неподвижном круге
        """

        def intersection_area(distance, r):
            """Расчет площади пересечения двух окружностей радиуса r на расстоянии d"""
            if distance >= 2 * r:
                return 0
            elif distance <= 0:
                return np.pi * r ** 2
            else:
                area = 2 * r ** 2 * np.arccos(distance / (2 * r)) - (distance / 2) * np.sqrt(4 * r ** 2 - distance ** 2)
                return area

        # Площади пересечения
        current_intersection_area = intersection_area(current_distance, radius)
        initial_intersection_area = intersection_area(initial_distance, radius)

        # Площадь одной окружности
        single_circle_area = np.pi * radius ** 2

        # Доли пересечения
        current_overlap_ratio = current_intersection_area / single_circle_area
        initial_overlap_ratio = initial_intersection_area / single_circle_area

        # Изменения
        distance_change = current_distance - initial_distance
        area_change = current_intersection_area - initial_intersection_area
        ratio_change = current_overlap_ratio - initial_overlap_ratio

        # Определение типа движения
        if current_distance < initial_distance:
            change_symbol = "↗"
            movement_status = "ПРИБЛИЖЕНИЕ"
        elif current_distance > initial_distance:
            change_symbol = "↘"
            movement_status = "УДАЛЕНИЕ"
        else:
            change_symbol = "="
            movement_status = "БЕЗ ИЗМЕНЕНИЙ"

        # расчеты для долей пересечения
        half_initial_ratio = initial_overlap_ratio / 2
        half_current_ratio = current_overlap_ratio / 2

        # Свободные части фигур
        initial_free_part = 1 - initial_overlap_ratio
        current_free_part = 1 - current_overlap_ratio

        # Доли фигур без лишнего пересечения
        initial_without_excess = 1 - half_initial_ratio
        current_without_excess = 1 - half_current_ratio

        # Доля, перешедшая в другое ВСП
        ratio_transferred = half_initial_ratio - half_current_ratio

        # Расчет клиентов в половине пересечения
        if current_distance > initial_distance:
            clients_in_half_intersection = cnt_clients_rel * half_initial_ratio / (1 - half_initial_ratio)
        elif current_distance < initial_distance:
            clients_in_half_intersection = cnt_clients_near * half_initial_ratio / (1 - half_initial_ratio)
        else:
            clients_in_half_intersection = 0

        # Количество клиентов, перешедших в другое ВСП
        if half_initial_ratio > 0:
            clients_transferred = clients_in_half_intersection * ratio_transferred / half_initial_ratio
        else:
            clients_transferred = 0

        new_cnt_clients_rel = cnt_clients_rel - clients_transferred
        new_cnt_clients_near = cnt_clients_near + clients_transferred

        # результат
        result = {
            # Основные параметры
            'Исходное расстояние': initial_distance,
            'Текущее расстояние': current_distance,
            'Изменение расстояния': distance_change,
            'Радиус окружностей': radius,
            'Кол-во клиентов в движимом круге': cnt_clients_rel,
            'Статус движения': movement_status,

            # Доли пересечения
            'Текущая доля пересечения': current_overlap_ratio,
            'Исходная доля пересечения': initial_overlap_ratio,
            'Изменение доли': ratio_change,

            # Новые параметры - доли пересечения
            'Половина исходной доли': half_initial_ratio,
            'Половина текущей доли': half_current_ratio,
            'Свободная часть исходной фигуры': initial_free_part,
            'Свободная часть текущей фигуры': current_free_part,
            'Доля исходной фигуры без лишнего пересечения': initial_without_excess,
            'Доля текущей фигуры без лишнего пересечения': current_without_excess,

            # Клиенты
            'Кол-во клиентов в половине пересечения': clients_in_half_intersection,
            'Доля перешла в другое ВСП': ratio_transferred,
            'Кол-во кл. перешло в другое ВСП': clients_transferred,

            # Для вывода
            'change_symbol': change_symbol,
            'Кол-во клиентов в неподвижном круге': cnt_clients_near,
            'Изменение кол-ва клиентов в движимом круге': -clients_transferred,
            'Изменение кол-ва клиентов в неподвижном круге': +clients_transferred,
            'Новое кол-во клиентов в движимом круге': new_cnt_clients_rel,
            'Новое кол-во клиентов в неподвижном круге': new_cnt_clients_near,
        }

        return result

    def move_scores(self, urf_code, coors):
        latitude, longitude = coors
        pd.options.mode.chained_assignment = None
        df = pd.read_feather('data/vsp_move_scores.feather')
        df = df.query('urf_code_new == @urf_code')
        df['latitude'] = latitude
        df['longitude'] = longitude

        df['dist'] = df.apply(lambda x: self.get_distance(x['lat_new'], x['lon_new'], x['latitude'], x['longitude']),
                              axis=1)
        min_dist = df.dist.min()
        df_min_dist = df.query('dist == @min_dist')
        new_coef = df_min_dist['vsp_score_new_70'] - df_min_dist['vsp_score_old_70']

        return new_coef.iloc[0]

    def __get_nearest_vsp(self, urf_code: str, latitude, longitude):
        max_distance = self.max_distance_to_near
        gosb = self._vsp_data[self._vsp_data['Код ВСП'] == urf_code]['ГОСБ'].values[0]
        gosb_data = self._vsp_data[(self._vsp_data['ГОСБ'] == gosb)]

        distance_df = gosb_data[['Код ВСП', 'ГОСБ', 'Широта', 'Долгота', 'Продажи СКМ', 'КП СКМ', 'КП СМО']][
            gosb_data['Код ВСП'] == urf_code] \
            .merge(gosb_data[['Код ВСП', 'ГОСБ', 'Широта', 'Долгота', 'Продажи СКМ', 'КП СКМ', 'КП СМО']][
                       gosb_data['Код ВСП'] != urf_code], on='ГОСБ', suffixes=['', '_near'])
        distance_df['old_distance'] = distance_df[['Широта', 'Долгота', 'Широта_near', 'Долгота_near']].apply(
            lambda x: self.get_distance(x['Широта'], x['Долгота'], x['Широта_near'], x['Долгота_near']), axis=1)
        distance_df['new_distance'] = distance_df[['Широта_near', 'Долгота_near']].apply(
            lambda x: self.get_distance(latitude, longitude, x['Широта_near'], x['Долгота_near']), axis=1)
        distance_df = distance_df[
            (distance_df['old_distance'] <= max_distance) | (distance_df['new_distance'] <= max_distance)]

        return distance_df

    def __prepare_forecast(self, urf_code: str,
                           coors: tuple):  # , coors: tuple #relocation_id: int, coors: tuple): #, coors: tuple
        latitude_new, longitude_new = coors

        distance_df = self.__get_nearest_vsp(urf_code=urf_code, latitude=latitude_new, longitude=longitude_new)

        distance_df[['Изменение продаж УП', 'Изменение продаж УП_near']] = \
        distance_df[['old_distance', 'new_distance', 'Продажи СКМ', 'Продажи СКМ_near']].apply(
            lambda row: self.calculate_intersection_parameters(row['old_distance'], row['new_distance'], self.radius_lr,
                                                               row['Продажи СКМ'], row['Продажи СКМ_near']),
            axis=1,
            result_type='expand'
        )[['Изменение кол-ва клиентов в движимом круге', 'Изменение кол-ва клиентов в неподвижном круге']]

        distance_df[['Изменение КП СКМ', 'Изменение КП СКМ_near']] = \
        distance_df[['old_distance', 'new_distance', 'КП СКМ', 'КП СКМ_near']].apply(
            lambda row: self.calculate_intersection_parameters(row['old_distance'], row['new_distance'], self.radius_lr,
                                                               row['КП СКМ'], row['КП СКМ_near']),
            axis=1,
            result_type='expand'
        )[['Изменение кол-ва клиентов в движимом круге', 'Изменение кол-ва клиентов в неподвижном круге']]

        distance_df[['Изменение КП СМО', 'Изменение КП СМО_near']] = \
        distance_df[['old_distance', 'new_distance', 'КП СМО', 'КП СМО_near']].apply(
            lambda row: self.calculate_intersection_parameters(row['old_distance'], row['new_distance'], self.radius_lr,
                                                               row['КП СМО'], row['КП СМО_near']),
            axis=1,
            result_type='expand'
        )[['Изменение кол-ва клиентов в движимом круге', 'Изменение кол-ва клиентов в неподвижном круге']]

        distance_df = distance_df[['Код ВСП', 'Изменение продаж УП', 'Изменение КП СКМ', 'Изменение КП СМО',
                                   'Код ВСП_near', 'Изменение продаж УП_near', 'Изменение КП СКМ_near',
                                   'Изменение КП СМО_near']]

        return distance_df

    def __new_kp_forecast(self, urf_code: str, forecast: float):
        forecast = np.where(forecast > 0.05, 0.05, forecast)
        new_kp_df = self._vsp_data[['Код ВСП', 'Продажи СКМ', 'КП СКМ', 'КП СМО']][
            self._vsp_data['Код ВСП'] == urf_code]
        new_kp_df['Изменение продаж УП'] = new_kp_df['Продажи СКМ'] * forecast
        new_kp_df['Изменение КП СКМ'] = new_kp_df['КП СКМ'] * forecast
        new_kp_df['Изменение КП СМО'] = new_kp_df['КП СМО'] * forecast

        new_kp_df = new_kp_df[['Код ВСП', 'Изменение продаж УП', 'Изменение КП СКМ', 'Изменение КП СМО']]

        return new_kp_df

    @staticmethod
    def get_overflows(prepared_data, new_kp_data):
        prepared_data_vsp = prepared_data[['Код ВСП', 'Изменение продаж УП', 'Изменение КП СКМ', 'Изменение КП СМО']]
        prepared_data_near = prepared_data[
            ['Код ВСП_near', 'Изменение продаж УП_near', 'Изменение КП СКМ_near', 'Изменение КП СМО_near']] \
            .rename(columns={'Код ВСП_near': 'Код ВСП', 'Изменение продаж УП_near': 'Изменение продаж УП',
                             'Изменение КП СКМ_near': 'Изменение КП СКМ', 'Изменение КП СМО_near': 'Изменение КП СМО'})
        new_kp_data = new_kp_data[['Код ВСП', 'Изменение продаж УП', 'Изменение КП СКМ', 'Изменение КП СМО']]
        df_overflow = pd.concat([prepared_data_vsp, prepared_data_near, new_kp_data], axis=0)
        df_overflow_agg = df_overflow.groupby('Код ВСП', as_index=False) \
            .agg({'Изменение продаж УП': 'sum', 'Изменение КП СКМ': 'sum', 'Изменение КП СМО': 'sum'}) \
            .rename(columns={'Изменение продаж УП': 'Изменение УП'})
        df_overflow_agg = df_overflow_agg.round(0)

        return df_overflow_agg

    def get_prediction(self, urf_code: str, coors: tuple, save_report: bool = True):
        # Проверка
        self._vsp_data = self.validate(is_reloc_vsp=urf_code, coors=coors)
        # Доля новых клиентов or отток на ЛР
        forecast = self.move_scores(urf_code, coors)
        logger.info(f'Изменение КП на ЛР: {round(forecast, 3) * 100:.2f}%')
        # Формирование перераспределяемого КП
        prepared_data = self.__prepare_forecast(urf_code=urf_code, coors=coors)
        # Формирование нового КП
        new_kp_data = self.__new_kp_forecast(urf_code, forecast)
        # Объединение перетоков
        overflow_data = self.get_overflows(prepared_data, new_kp_data)
        # Формирование финального файла
        prediction = self.save_prediction(urf_code=urf_code, overflow=overflow_data, coors=coors)

        return prediction

    def save_prediction(self, urf_code: str, overflow: pd.DataFrame, coors=tuple):
        (latitude, longitude) = coors

        finally_data = overflow.merge(self._vsp_data, on='Код ВСП', how='left')
        finally_data['Код ВСП (изменяемое)'] = urf_code
        finally_data['Ключ 1 (изменяемое ВСП) / 0 (ВСП ЛР)'] = np.where(finally_data['Код ВСП'] == urf_code, 1, 0)
        finally_data['Планируемое мероприятие'] = np.where(finally_data['Код ВСП'] == urf_code, 'Перемещение', '')
        finally_data['Новый адрес'] = '-'
        # Используем astype(str) для координат, чтобы избежать ошибки смешивания типов
        finally_data['Новая широта'] = np.where(finally_data['Код ВСП'] == urf_code, str(latitude), '')
        finally_data['Новая долгота'] = np.where(finally_data['Код ВСП'] == urf_code, str(longitude), '')
        finally_data['Изменение ПШЕ СКМ'] = round(
            finally_data['Изменение УП'] / finally_data['Нормативный УП'] / 21 * finally_data['КБО'], 2)
        finally_data['Изменение ПШЕ СМО'] = round(finally_data['Изменение КП СМО'] / 1400 * finally_data['КБО'], 2)
        data_to_bt_relocate = finally_data[['Код ВСП (изменяемое)', 'Код ВСП',
                                            'Ключ 1 (изменяемое ВСП) / 0 (ВСП ЛР)', 'Планируемое мероприятие',
                                            'Новый адрес', 'Новая широта', 'Новая долгота',
                                            'Изменение УП', 'Изменение КП СКМ', 'Изменение КП СМО', 'Изменение ПШЕ СКМ',
                                            'Изменение ПШЕ СМО']]

        finally_data.loc[finally_data['Флаг СМРК'] == 1, 'КП СКМ'] = 0
        finally_data.loc[finally_data['Флаг СМРК'] == 1, 'КП СМО'] = 0

        finally_data.loc[finally_data['Флаг СМРК'] == 0, 'Изменение КП СМРК'] = 0
        finally_data.loc[finally_data['Флаг СМРК'] == 1, 'Изменение КП СМРК'] = finally_data['Изменение КП СКМ'] + \
                                                                                finally_data['Изменение КП СМО']
        finally_data.loc[finally_data['Флаг СМРК'] == 0, 'Изменение ПШЕ СМРК'] = 0
        finally_data.loc[finally_data['Флаг СМРК'] == 1, 'Изменение ПШЕ СМРК'] = finally_data['Изменение ПШЕ СКМ'] + \
                                                                                 finally_data['Изменение ПШЕ СМО']

        finally_data.loc[finally_data['Флаг СМРК'] == 1, 'Изменение КП СКМ'] = 0
        finally_data.loc[finally_data['Флаг СМРК'] == 1, 'Изменение КП СМО'] = 0
        finally_data.loc[finally_data['Флаг СМРК'] == 1, 'Изменение ПШЕ СКМ'] = 0
        finally_data.loc[finally_data['Флаг СМРК'] == 1, 'Изменение ПШЕ СМО'] = 0

        finally_data['Новый УП'] = finally_data['Продажи СКМ'] + finally_data['Изменение УП']
        finally_data['Новый КП СКМ'] = finally_data['КП СКМ'] + finally_data['Изменение КП СКМ']
        finally_data['Новый КП СМО'] = finally_data['КП СМО'] + finally_data['Изменение КП СМО']
        finally_data['Новый общий/СМРК КП'] = finally_data['Общий КП'] + finally_data['Изменение КП СКМ'] + \
                                              finally_data['Изменение КП СМО'] + finally_data['Изменение КП СМРК']

        finally_data['Новый ПШЕ СКМ'] = finally_data['Изменение ПШЕ СКМ'] + finally_data['ПШЕ СКМ']
        finally_data['Новый ПШЕ СМО'] = finally_data['Изменение ПШЕ СМО'] + finally_data['ПШЕ СМО']
        finally_data['Новый ПШЕ СМРК'] = finally_data['Изменение ПШЕ СМРК'] + finally_data['ПШЕ СМРК']

        finally_data['Итого необходимо ПШЕ СКМ'] = round(finally_data['Новый ПШЕ СКМ'], 0)
        finally_data['Итого необходимо ПШЕ СМО'] = round(finally_data['Новый ПШЕ СМО'], 0)
        finally_data['Итого необходимо ПШЕ СМРК'] = round(finally_data['Новый ПШЕ СМРК'], 0)

        finally_data['Изменение ПШЕ СКМ с учетом нагрузки'] = finally_data['Итого необходимо ПШЕ СКМ'] - finally_data[
            'ПШЕ СКМ']
        finally_data['Изменение ПШЕ СМО с учетом нагрузки'] = finally_data['Итого необходимо ПШЕ СМО'] - finally_data[
            'ПШЕ СМО']
        finally_data['Изменение ПШЕ СМРК с учетом нагрузки'] = finally_data['Итого необходимо ПШЕ СМРК'] - finally_data[
            'ПШЕ СМРК']

        finally_data['Итого необходимо РМ СКМ'] = np.ceil(
            finally_data['Итого необходимо ПШЕ СКМ'] * finally_data['Нормативное время работы'] / (
                        finally_data['Нормативное время работы'] + finally_data[
                    'Норматив использования времени СКМ'] * (
                                    finally_data[['Нормативное время работы', 'Целевое время работы в неделю']].max(
                                        axis=1) - finally_data['Нормативное время работы'])))
        finally_data['Итого необходимо РМ СМО'] = np.ceil(
            finally_data['Итого необходимо ПШЕ СМО'] * finally_data['Нормативное время работы'] / (
                        finally_data['Нормативное время работы'] + finally_data[
                    'Норматив использования времени СМО'] * (
                                    finally_data[['Нормативное время работы', 'Целевое время работы в неделю']].max(
                                        axis=1) - finally_data['Нормативное время работы'])))
        finally_data['Итого необходимо РМ СМРК'] = np.ceil(
            finally_data['Итого необходимо ПШЕ СМРК'] * finally_data['Нормативное время работы'] / (
                        finally_data['Нормативное время работы'] + finally_data[
                    'Норматив использования времени СМРК'] * (
                                    finally_data[['Нормативное время работы', 'Целевое время работы в неделю']].max(
                                        axis=1) - finally_data['Нормативное время работы'])))

        finally_data['Требуемое кол-во дополнительных РМ СКМ с учетом изменения УП'] = finally_data[
                                                                                           'Итого необходимо РМ СКМ'] - \
                                                                                       finally_data['РМ СКМ']
        finally_data.loc[finally_data[
                             'Требуемое кол-во дополнительных РМ СКМ с учетом изменения УП'] < 0, 'Требуемое кол-во дополнительных РМ СКМ с учетом изменения УП'] = 0

        finally_data['Требуемое кол-во дополнительных РМ СМО с учетом изменения КП'] = finally_data[
                                                                                           'Итого необходимо РМ СМО'] - \
                                                                                       finally_data['РМ СМО']
        finally_data.loc[finally_data[
                             'Требуемое кол-во дополнительных РМ СМО с учетом изменения КП'] < 0, 'Требуемое кол-во дополнительных РМ СМО с учетом изменения КП'] = 0

        finally_data['Требуемое кол-во дополнительных РМ СМРК с учетом изменения КП'] = finally_data[
                                                                                            'Итого необходимо РМ СМРК'] - \
                                                                                        finally_data['РМ СМРК']
        finally_data.loc[finally_data[
                             'Требуемое кол-во дополнительных РМ СМРК с учетом изменения КП'] < 0, 'Требуемое кол-во дополнительных РМ СМРК с учетом изменения КП'] = 0

        finally_data['Требуемая доп.площадь под СКМ'] = finally_data[
                                                            'Требуемое кол-во дополнительных РМ СКМ с учетом изменения УП'] * 12
        finally_data['Требуемая доп.площадь под СМО'] = finally_data[
                                                            'Требуемое кол-во дополнительных РМ СМО с учетом изменения КП'] * 12
        finally_data['Требуемая доп.площадь под СМРК'] = finally_data[
                                                             'Требуемое кол-во дополнительных РМ СМРК с учетом изменения КП'] * 12

        finally_data['Нормативная площадь после закрытия ВСП, м2'] = finally_data['Общая нормативная площадь'] + \
                                                                     finally_data['Требуемая доп.площадь под СКМ'] + \
                                                                     finally_data['Требуемая доп.площадь под СМО'] + \
                                                                     finally_data['Требуемая доп.площадь под СМРК']
        finally_data['Дефицит (-) / Излишек (+) площади после закрытия ВСП, м2'] = finally_data[
                                                                                       'Общая фактическая площадь'] - \
                                                                                   finally_data[
                                                                                       'Нормативная площадь после закрытия ВСП, м2']

        finally_data['Дата расчета'] = '-'
        finally_data['Доля перетока'] = ''

        columns_to_ru = {
            'Код ВСП': 'Код ВСП (изменяемое и на которые влияем)',
            'КБО': 'Коэф. КБО',
            'Нормативный УП': 'Нормативный УП в сутки на 1 ПШЕ',
            'Конвертация КП СКМ в УП': 'Средняя конвертация КП МП в УП МП по городу',
            'Продажи СКМ': 'Продажи УП СКМ',
            'Общий КП': 'Общий/СМРК КП',
            'Общая нормативная площадь': 'Площадь норм, м2',
            'избыток, м2': 'Дефицит (-)/Избыток (+)',
            'Общая фактическая площадь': 'Площадь факт, м2'}

        finally_data.rename(columns=columns_to_ru, inplace=True)

        data_to_bt_relocate.rename(columns=columns_to_ru, inplace=True)

        finally_data = finally_data[
            ['Код ВСП (изменяемое)', 'Код ВСП (изменяемое и на которые влияем)', 'Юр.адрес', 'Краткий тип НП',
             'Норматив использования времени СКМ', 'Норматив использования времени СМО',
             'Норматив использования времени СМРК',
             'Нормативное время работы', 'Целевое время работы в неделю', 'Коэф. КБО',
             'Нормативный УП в сутки на 1 ПШЕ',
             'Средняя конвертация КП МП в УП МП по городу', 'Флаг СМРК', 'Доля перетока', 'Продажи УП СКМ', 'КП СКМ',
             'КП СМО', 'Общий/СМРК КП',
             'Ключ 1 (изменяемое ВСП) / 0 (ВСП ЛР)', 'Дата расчета', 'Планируемое мероприятие', 'Новый адрес',
             'Новая широта', 'Новая долгота', 'Изменение УП',
             'Изменение КП СКМ', 'Изменение КП СМО', 'Изменение КП СМРК', 'Новый УП', 'Новый КП СКМ', 'Новый КП СМО',
             'Новый общий/СМРК КП', 'Требуемая доп.площадь под СКМ',
             'Требуемая доп.площадь под СМО', 'Требуемая доп.площадь под СМРК', 'Изменение ПШЕ СКМ', 'Новый ПШЕ СКМ',
             'Изменение ПШЕ СКМ с учетом нагрузки',
             'Требуемое кол-во дополнительных РМ СКМ с учетом изменения УП', 'Изменение ПШЕ СМО', 'Новый ПШЕ СМО',
             'Изменение ПШЕ СМО с учетом нагрузки',
             'Требуемое кол-во дополнительных РМ СМО с учетом изменения КП', 'Изменение ПШЕ СМРК', 'Новый ПШЕ СМРК',
             'Изменение ПШЕ СМРК с учетом нагрузки',
             'Требуемое кол-во дополнительных РМ СМРК с учетом изменения КП', 'Итого необходимо ПШЕ СКМ',
             'Итого необходимо РМ СКМ', 'Итого необходимо ПШЕ СМО',
             'Итого необходимо РМ СМО', 'Итого необходимо ПШЕ СМРК', 'Итого необходимо РМ СМРК', 'ПШЕ СКМ',
             'ПШЕ СКМ расч.', 'РМ СКМ', 'ПШЕ СМО', 'ПШЕ СМО расч.', 'РМ СМО',
             'ПШЕ СМРК', 'ПШЕ СМРК расч.', 'РМ СМРК', 'Площадь норм, м2', 'Дефицит (-)/Избыток (+)', 'Площадь факт, м2',
             'Нормативная площадь после закрытия ВСП, м2',
             'Дефицит (-) / Излишек (+) площади после закрытия ВСП, м2']].sort_values(
            ['Ключ 1 (изменяемое ВСП) / 0 (ВСП ЛР)', 'Изменение УП'], ascending=False)

        return finally_data, data_to_bt_relocate
