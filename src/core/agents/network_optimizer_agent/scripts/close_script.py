import pandas as pd
import pickle
import numpy as np
import math
import warnings

from src.utils.logger import get_logger

warnings.filterwarnings('ignore')

logger = get_logger(__name__)


class VSPAnalyzer:
    def __init__(self, is_close=[], is_cs=[], is_bt=[]):

        self.df_kp_table_asinh = None
        self.df_kp_table_sinh = None
        self.f_df_asinh = None
        self.f_df_sinh = None

        #             """Загрузка и подготовка исходных данных"""
        self.cs_vsp_main, self.city_ids = self.load_cs_vsp_data(is_close, is_cs, is_bt)
        self.peretoki = self.load_peretoki_data()

        self.is_cs = is_cs
        self.is_bt = is_bt

        if len(is_close) > 0:
            self.is_close = is_close
        else:
            self.is_close = self.cs_vsp_main[self.cs_vsp_main['is_close'] == 1]['urf_code'].unique()

    def load_cs_vsp_data(self, is_close, is_cs, is_bt):
        """Загрузка и подготовка данных ЦС_ВСП"""
        cs_vsp_main = self.to_naming(pd.read_excel('data/ЦС_ВСП_v8.xlsx'))
        lst_vsp = is_close + is_bt

        if len(lst_vsp) > 0:
            city_ids = cs_vsp_main.query('urf_code in @lst_vsp')['city_id'].unique()
        else:
            city_ids = cs_vsp_main.city_id.unique()

        cs_vsp_main['kp_smrk'] = cs_vsp_main['all_kp']

        # Валидация и применение is_close
        for i in is_close:
            if i and i.strip():  # Проверка на пустую строку
                mask = cs_vsp_main['urf_code'] == i
                if mask.any():  # Проверка, что ВСП существует
                    cs_vsp_main.loc[mask, 'is_close'] = 1
                    cs_vsp_main.loc[mask, 'is_noflow'] = 1
                    logger.info(f"ВСП {i} помечен для закрытия")
                else:
                    logger.warning(f"ВСП {i} не найден в базе данных (is_close)")

        # Валидация и применение is_cs
        for i in is_cs:
            if i and i.strip():  # Проверка на пустую строку
                mask = cs_vsp_main['urf_code'] == i
                if mask.any():  # Проверка, что ВСП существует
                    cs_vsp_main.loc[mask, 'is_close'] = 0
                    cs_vsp_main.loc[mask, 'is_noflow'] = 0
                    logger.info(f"ВСП {i} помечен для возврата в сеть")
                else:
                    logger.warning(f"ВСП {i} не найден в базе данных (is_cs)")

        return cs_vsp_main.query('city_id in @city_ids'), city_ids

    def load_peretoki_data(self):
        """Загрузка и подготовка данных перетоков"""
        peretoki = pd.read_pickle('data/all_peretok.pickle') \
            .query('((pcnt_peretok!=0)|(urf_code==urf_code_close))&(city in @self.city_ids)')

        return peretoki

    def base_calc(self):
        """Основные расчеты"""

        # Заполняем ПШЯ
        self.cs_vsp_main['pshe_smrk_to_skm1'] = self.cs_vsp_main['pshe_smrk'].apply(lambda x: math.ceil(x / 2))
        self.cs_vsp_main['pshe_smrk_to_skm2'] = round(
            self.cs_vsp_main['sale_up'] / self.cs_vsp_main['norm_up'] / 21 * self.cs_vsp_main['kbo'], 0)

        self.cs_vsp_main.loc[(self.cs_vsp_main['is_smrk'] == 1) & (self.cs_vsp_main['pshe_smo'] == 0), 'pshe_skm'] = \
        self.cs_vsp_main[['pshe_smrk_to_skm1', 'pshe_smrk_to_skm2']].min(axis=1)
        self.cs_vsp_main.loc[(self.cs_vsp_main['is_smrk'] == 1) & (self.cs_vsp_main['pshe_smo'] == 0), 'pshe_smo'] = \
        self.cs_vsp_main['pshe_smrk'] - self.cs_vsp_main['pshe_skm']
        self.cs_vsp_main['pshe_smrk'] = self.cs_vsp_main['pshe_skm'] + self.cs_vsp_main['pshe_smo']

        self.cs_vsp_main['calc_skm'] = self.cs_vsp_main['sale_up'] / self.cs_vsp_main['norm_up'] / 21 * \
                                       self.cs_vsp_main['kbo']
        self.cs_vsp_main['calc_smo'] = self.cs_vsp_main['kp_smo'] / 1400 * self.cs_vsp_main['kbo']
        self.cs_vsp_main['calc_skm1'] = self.cs_vsp_main['pshe_smrk_calc'] * self.cs_vsp_main['calc_skm'] / (
                    self.cs_vsp_main['calc_skm'] + self.cs_vsp_main['calc_smo'])
        self.cs_vsp_main['calc_skm2'] = self.cs_vsp_main['pshe_smrk_calc'] * self.cs_vsp_main['pshe_skm'] / \
                                        self.cs_vsp_main['pshe_smrk']

        self.cs_vsp_main.loc[self.cs_vsp_main['is_smrk'] == 1, 'pshe_skm_calc'] = self.cs_vsp_main[
            ['calc_skm1', 'calc_skm2']].min(axis=1)
        self.cs_vsp_main.loc[self.cs_vsp_main['is_smrk'] == 1, 'pshe_smo_calc'] = self.cs_vsp_main['pshe_smrk_calc'] - \
                                                                                  self.cs_vsp_main['pshe_skm_calc']
        self.cs_vsp_main['pshe_smrk_calc'] = self.cs_vsp_main['pshe_skm_calc'] + self.cs_vsp_main['pshe_smo_calc']

        self.cs_vsp_main['rm_skm'] = np.ceil(self.cs_vsp_main['pshe_skm'] * self.cs_vsp_main['norm_worktime'] / (
                    self.cs_vsp_main['norm_worktime'] + self.cs_vsp_main['norm_pcnt_time_skm'] * (
                        self.cs_vsp_main[['norm_worktime', 'target_worktime']].max(axis=1) - self.cs_vsp_main[
                    'norm_worktime'])))
        self.cs_vsp_main['rm_smo'] = np.ceil(self.cs_vsp_main['pshe_smo'] * self.cs_vsp_main['norm_worktime'] / (
                    self.cs_vsp_main['norm_worktime'] + self.cs_vsp_main['norm_pcnt_time_smo'] * (
                        self.cs_vsp_main[['norm_worktime', 'target_worktime']].max(axis=1) - self.cs_vsp_main[
                    'norm_worktime'])))
        self.cs_vsp_main['rm_smrk'] = np.ceil(self.cs_vsp_main['pshe_smrk'] * self.cs_vsp_main['norm_worktime'] / (
                    self.cs_vsp_main['norm_worktime'] + self.cs_vsp_main['norm_pcnt_time_smrk'] * (
                        self.cs_vsp_main[['norm_worktime', 'target_worktime']].max(axis=1) - self.cs_vsp_main[
                    'norm_worktime'])))
        self.cs_vsp_main = self.cs_vsp_main.drop(
            columns=['pshe_smrk_to_skm1', 'pshe_smrk_to_skm2', 'calc_skm', 'calc_smo', 'calc_skm1', 'calc_skm2'])

        if self.is_all_smrk == 1 and len(self.is_bt) > 0:
            self.cs_vsp_main.loc[self.cs_vsp_main['urf_code'].isin(self.is_bt), 'is_smrk'] = 1
        elif self.is_all_smrk == 0 and len(self.is_bt) > 0:
            self.cs_vsp_main.loc[self.cs_vsp_main['urf_code'].isin(self.is_bt), 'is_smrk'] = 0

        df_base_close = self.cs_vsp_main[self.cs_vsp_main['is_close'] == 1][
            ['urf_code', 'gosb_vsp', 'pcnt_overflow', 'is_close', 'is_smrk',
             'sale_up', 'kp_skm', 'kp_smo', 'kp_smrk', 'all_kp',
             'pshe_skm', 'pshe_smo', 'pshe_smrk', 'norm_up', 'kbo']]

        col = ['urf_code', 'pcnt_overflow',
               'sale_up', 'kp_skm', 'kp_smo', 'kp_smrk',
               'pshe_skm', 'pshe_smo', 'pshe_smrk',
               'pcnt_peretok', 'urf_code_near', 'is_close_near', 'is_smrk_near', 'city_type', 'address',
               'sale_up_near', 'kp_skm_near', 'kp_smo_near', 'kp_smrk_near', 'all_kp_near',
               'norm_up', 'kbo', 'conversion', 'norm_pcnt_time_skm', 'norm_pcnt_time_smo', 'norm_pcnt_time_smrk',
               'norm_worktime', 'target_worktime',
               'pshe_skm_near', 'pshe_skm_calc', 'rm_skm', 'pshe_smo_near', 'pshe_smo_calc', 'rm_smo',
               'pshe_smrk_near', 'pshe_smrk_calc', 'rm_smrk',
               'norm_square', 'diff_square', 'fact_square']

        df_kp_table = df_base_close.merge(
            self.peretoki,
            how='left',
            left_on='gosb_vsp',
            right_on='urf_code_close',
            suffixes=('', '_sub')
        ).merge(
            self.cs_vsp_main,
            left_on='urf_code_sub',
            right_on='gosb_vsp',
            suffixes=('', '_near')
        ).query('(is_noflow==0)|(urf_code==urf_code_near)')[col].sort_values('urf_code')

        df_kp_table.loc[df_kp_table['urf_code'] != df_kp_table['urf_code_near'], 'is_close_near'] = 0

        df_kp_table["pcnt_peretok_summary"] = df_kp_table.groupby('urf_code')["pcnt_peretok"].transform('sum')
        df_kp_table['new_pcnt_peretok'] = round(
            df_kp_table['pcnt_peretok'] / df_kp_table['pcnt_peretok_summary'] * df_kp_table['pcnt_overflow'], 2)
        df_kp_table.loc[df_kp_table['is_close_near'] == 1, 'new_pcnt_peretok'] = -1

        df_kp_table['sale_up_overflow'] = round(df_kp_table['sale_up'] * df_kp_table['new_pcnt_peretok'], 0)
        df_kp_table['kp_skm_overflow'] = round(df_kp_table['kp_skm'] * df_kp_table['new_pcnt_peretok'], 0)
        df_kp_table['kp_smo_overflow'] = round(df_kp_table['kp_smo'] * df_kp_table['new_pcnt_peretok'], 0)
        df_kp_table['smrk_kp_overflow'] = round(df_kp_table['kp_smrk'] * df_kp_table['new_pcnt_peretok'], 0)

        df_kp_table['pshe_skm_overflow'] = round(df_kp_table['pshe_skm'] * df_kp_table['new_pcnt_peretok'], 2)
        df_kp_table['pshe_smo_overflow'] = round(df_kp_table['pshe_smo'] * df_kp_table['new_pcnt_peretok'], 2)
        df_kp_table['pshe_smrk_overflow'] = round(df_kp_table['pshe_smrk'] * df_kp_table['new_pcnt_peretok'], 2)

        df_kp_table.loc[df_kp_table['is_smrk_near'] == 1, 'kp_skm_near'] = 0
        df_kp_table.loc[df_kp_table['is_smrk_near'] == 1, 'kp_smo_near'] = 0
        df_kp_table.loc[df_kp_table['is_smrk_near'] == 1, 'kp_skm_overflow'] = 0
        df_kp_table.loc[df_kp_table['is_smrk_near'] == 1, 'kp_smo_overflow'] = 0
        df_kp_table.loc[df_kp_table['is_smrk_near'] == 0, 'smrk_kp_overflow'] = 0
        df_kp_table.loc[df_kp_table['is_smrk_near'] == 1, 'pshe_skm_overflow'] = 0
        df_kp_table.loc[df_kp_table['is_smrk_near'] == 1, 'pshe_smo_overflow'] = 0
        df_kp_table.loc[df_kp_table['is_smrk_near'] == 0, 'pshe_smrk_overflow'] = 0
        df_kp_table.loc[df_kp_table['is_smrk_near'] == 1, 'pshe_skm_near'] = 0
        df_kp_table.loc[df_kp_table['is_smrk_near'] == 1, 'pshe_smo_near'] = 0
        df_kp_table.loc[df_kp_table['is_smrk_near'] == 0, 'pshe_smrk_near'] = 0
        df_kp_table.loc[df_kp_table['is_smrk_near'] == 1, 'pshe_skm_calc'] = 0
        df_kp_table.loc[df_kp_table['is_smrk_near'] == 1, 'pshe_smo_calc'] = 0
        df_kp_table.loc[df_kp_table['is_smrk_near'] == 0, 'pshe_smrk_calc'] = 0
        df_kp_table.loc[df_kp_table['is_smrk_near'] == 1, 'rm_skm'] = 0
        df_kp_table.loc[df_kp_table['is_smrk_near'] == 1, 'rm_smo'] = 0
        df_kp_table.loc[df_kp_table['is_smrk_near'] == 0, 'rm_smrk'] = 0

        return df_kp_table

    def to_form(self, df_kp_table):
        """Преобразование данных"""
        if df_kp_table.empty:
            # Нет данных для расчета — запрашиваемые ВСП отсутствуют в базе или перетоки пустые
            logger.error("to_form: пустая таблица для расчета (нет совпадений по ВСП)")
            raise ValueError("Нет данных для расчета: ВСП отсутствуют в базе или нет данных о перетоках")
        df_kp_table['new_sale_up'] = df_kp_table['sale_up_overflow'] + df_kp_table['sale_up_near']
        df_kp_table['new_kp_skm'] = df_kp_table['kp_skm_overflow'] + df_kp_table['kp_skm_near']
        df_kp_table['new_kp_smo'] = df_kp_table['kp_smo_overflow'] + df_kp_table['kp_smo_near']
        df_kp_table['new_smrk_kp'] = df_kp_table['smrk_kp_overflow'] + df_kp_table['kp_smrk_near'] + df_kp_table[
            'kp_smo_overflow'] + df_kp_table['kp_skm_overflow']

        df_kp_table.loc[df_kp_table['is_close_near'] == 1, 'new_pshe_skm_calc'] = df_kp_table['pshe_skm_overflow'] + \
                                                                                  df_kp_table['pshe_skm_near']
        df_kp_table.loc[df_kp_table['is_close_near'] == 0, 'new_pshe_skm_calc'] = df_kp_table['pshe_skm_overflow'] + \
                                                                                  df_kp_table['pshe_skm_calc']

        df_kp_table.loc[df_kp_table['is_close_near'] == 1, 'new_pshe_smo_calc'] = df_kp_table['pshe_smo_overflow'] + \
                                                                                  df_kp_table['pshe_smo_near']
        df_kp_table.loc[df_kp_table['is_close_near'] == 0, 'new_pshe_smo_calc'] = df_kp_table['pshe_smo_overflow'] + \
                                                                                  df_kp_table['pshe_smo_calc']

        df_kp_table.loc[df_kp_table['is_close_near'] == 1, 'new_pshe_smrk_calc'] = df_kp_table['pshe_smrk_overflow'] + \
                                                                                   df_kp_table['pshe_smrk_near']
        df_kp_table.loc[df_kp_table['is_close_near'] == 0, 'new_pshe_smrk_calc'] = df_kp_table['pshe_smrk_overflow'] + \
                                                                                   df_kp_table['pshe_smrk_calc']

        df_kp_table.loc[df_kp_table['is_close_near'] == 1, 'new_pshe_skm'] = 0
        df_kp_table.loc[df_kp_table['is_close_near'] == 0, 'new_pshe_skm'] = round(
            df_kp_table[['new_pshe_skm_calc', 'pshe_skm_near']].max(axis=1), 0)

        df_kp_table.loc[df_kp_table['is_close_near'] == 1, 'new_pshe_smo'] = 0
        df_kp_table.loc[df_kp_table['is_close_near'] == 0, 'new_pshe_smo'] = round(
            df_kp_table[['new_pshe_smo_calc', 'pshe_smo_near']].max(axis=1) + 0.4, 0)

        df_kp_table.loc[df_kp_table['is_close_near'] == 1, 'new_pshe_smrk'] = 0
        df_kp_table.loc[df_kp_table['is_close_near'] == 0, 'new_pshe_smrk'] = round(
            df_kp_table[['new_pshe_smrk_calc', 'pshe_smrk_near']].max(axis=1) + 0.2, 0)

        df_kp_table['delta_pshe_skm'] = df_kp_table['new_pshe_skm'] - df_kp_table['pshe_skm_near']
        df_kp_table['delta_pshe_smo'] = df_kp_table['new_pshe_smo'] - df_kp_table['pshe_smo_near']
        df_kp_table['delta_pshe_smrk'] = df_kp_table['new_pshe_smrk'] - df_kp_table['pshe_smrk_near']

        df_kp_table['new_rm_skm'] = np.ceil(df_kp_table['new_pshe_skm'] * df_kp_table['norm_worktime'] / (
                    df_kp_table['norm_worktime'] + df_kp_table['norm_pcnt_time_skm'] * (
                        df_kp_table[['norm_worktime', 'target_worktime']].max(axis=1) - df_kp_table['norm_worktime'])))
        df_kp_table['new_rm_smo'] = np.ceil(df_kp_table['new_pshe_smo'] * df_kp_table['norm_worktime'] / (
                    df_kp_table['norm_worktime'] + df_kp_table['norm_pcnt_time_smo'] * (
                        df_kp_table[['norm_worktime', 'target_worktime']].max(axis=1) - df_kp_table['norm_worktime'])))
        df_kp_table['new_rm_smrk'] = np.ceil(df_kp_table['new_pshe_smrk'] * df_kp_table['norm_worktime'] / (
                    df_kp_table['norm_worktime'] + df_kp_table['norm_pcnt_time_smrk'] * (
                        df_kp_table[['norm_worktime', 'target_worktime']].max(axis=1) - df_kp_table['norm_worktime'])))

        df_kp_table['delta_rm_skm'] = df_kp_table['new_rm_skm'] - df_kp_table['rm_skm']
        df_kp_table.loc[df_kp_table['delta_rm_skm'] < 0, 'delta_rm_skm'] = 0

        df_kp_table['delta_rm_smo'] = df_kp_table['new_rm_smo'] - df_kp_table['rm_smo']
        df_kp_table.loc[df_kp_table['delta_rm_smo'] < 0, 'delta_rm_smo'] = 0

        df_kp_table['delta_rm_smrk'] = df_kp_table['new_rm_smrk'] - df_kp_table['rm_smrk']
        df_kp_table.loc[df_kp_table['delta_rm_smrk'] < 0, 'delta_rm_smrk'] = 0

        df_kp_table['dop_square_rm_skm'] = df_kp_table['delta_rm_skm'] * 12
        df_kp_table['dop_square_rm_smo'] = df_kp_table['delta_rm_smo'] * 12
        df_kp_table['dop_square_rm_smrk'] = df_kp_table['delta_rm_smrk'] * 12

        df_kp_table['new_norm_square'] = df_kp_table['norm_square'] + df_kp_table['dop_square_rm_skm'] + df_kp_table[
            'dop_square_rm_smo'] + df_kp_table['dop_square_rm_smrk']
        df_kp_table['new_diff_square'] = df_kp_table['fact_square'] - df_kp_table['new_norm_square']

        df_kp_table.loc[df_kp_table['is_close_near'] == 1, 'new_norm_square'] = 0
        df_kp_table.loc[df_kp_table['is_close_near'] == 1, 'new_diff_square'] = 0

        return df_kp_table

    def to_sinchro(self, df_kp_table1):
        """Синхронизация данных"""
        uniq_cols = ['urf_code', 'city_type', 'address', 'new_pcnt_peretok']
        sum_cols = ['sale_up_overflow', 'kp_skm_overflow', 'kp_smo_overflow',
                    'smrk_kp_overflow', 'pshe_skm_overflow', 'pshe_smo_overflow', 'pshe_smrk_overflow']
        mean_cols = ['sale_up', 'kp_skm', 'kp_smo', 'kp_smrk', 'pshe_skm', 'pshe_smo', 'pshe_smrk', 'is_close_near',
                     'is_smrk_near', 'sale_up_near', 'kp_skm_near', 'kp_smo_near', 'kp_smrk_near', 'all_kp_near',
                     'norm_up', 'kbo',
                     'conversion', 'norm_pcnt_time_skm', 'norm_pcnt_time_smo', 'norm_pcnt_time_smrk', 'norm_worktime',
                     'target_worktime',
                     'pshe_skm_near', 'pshe_skm_calc', 'rm_skm', 'pshe_smo_near', 'pshe_smo_calc', 'rm_smo',
                     'pshe_smrk_near', 'pshe_smrk_calc', 'rm_smrk', 'norm_square', 'diff_square', 'fact_square']

        df_kp_table2 = df_kp_table1.groupby('urf_code_near').agg(
            {**{col: 'sum' for col in sum_cols},
             **{col: 'unique' for col in uniq_cols},
             **{col: 'mean' for col in mean_cols}}
        ).reset_index()

        return df_kp_table2

    def to_finally(self, df_kp_table):
        """Финальная подготовка данных"""

        cols_overflow = ['urf_code', 'urf_code_near', 'address', 'city_type',
                         'norm_pcnt_time_skm', 'norm_pcnt_time_smo', 'norm_pcnt_time_smrk', 'norm_worktime',
                         'target_worktime',
                         'kbo', 'norm_up', 'conversion', 'is_smrk_near', 'new_pcnt_peretok',
                         'sale_up_near', 'kp_skm_near', 'kp_smo_near', 'all_kp_near',
                         'is_close_near', 'Дата расчета', 'Планируемое мероприятие', 'Новый адрес', 'Новая широта',
                         'Новая долгота',
                         'sale_up_overflow', 'kp_skm_overflow', 'kp_smo_overflow', 'smrk_kp_overflow',
                         'new_sale_up', 'new_kp_skm', 'new_kp_smo', 'new_smrk_kp',
                         'dop_square_rm_skm', 'dop_square_rm_smo', 'dop_square_rm_smrk',
                         'pshe_skm_overflow', 'new_pshe_skm_calc', 'delta_pshe_skm', 'delta_rm_skm',
                         'pshe_smo_overflow', 'new_pshe_smo_calc', 'delta_pshe_smo', 'delta_rm_smo',
                         'pshe_smrk_overflow', 'new_pshe_smrk_calc', 'delta_pshe_smrk', 'delta_rm_smrk',
                         'new_pshe_skm', 'new_rm_skm', 'new_pshe_smo', 'new_rm_smo', 'new_pshe_smrk', 'new_rm_smrk',
                         'pshe_skm_near', 'pshe_skm_calc', 'rm_skm',
                         'pshe_smo_near', 'pshe_smo_calc', 'rm_smo',
                         'pshe_smrk_near', 'pshe_smrk_calc', 'rm_smrk',
                         'norm_square', 'diff_square', 'fact_square', 'new_norm_square', 'new_diff_square']

        df_kp_table['Дата расчета'] = '-'
        df_kp_table['Планируемое мероприятие'] = 'Закрытие'
        df_kp_table['Новый адрес'] = '-'
        df_kp_table['Новая широта'] = '-'
        df_kp_table['Новая долгота'] = '-'

        f_df = df_kp_table[cols_overflow]
        return f_df

    @staticmethod
    def to_naming(df):
        name_to_en = {'Код ВСП': 'urf_code',
                      'ГОСБ_ВСП': 'gosb_vsp',
                      'ТБ': 'tb',
                      'Флаг закрытия': 'is_close',
                      'Флаг неперетока в это ВСП': 'is_noflow',
                      'Флаг СМРК': 'is_smrk',
                      'Продажи СКМ': 'sale_up',
                      'КП СКМ': 'kp_skm',
                      'КП СМО': 'kp_smo',
                      'КП СМРК': 'kp_smrk',
                      'Общий КП': 'all_kp',
                      'Нормативный УП': 'norm_up',
                      'КБО': 'kbo',
                      'Конвертация КП СКМ в УП': 'conversion',
                      'Норматив использования времени СКМ': 'norm_pcnt_time_skm',
                      'Норматив использования времени СМО': 'norm_pcnt_time_smo',
                      'Норматив использования времени СМРК': 'norm_pcnt_time_smrk',
                      'Нормативное время работы': 'norm_worktime',
                      'Целевое время работы в неделю': 'target_worktime',
                      'ГОСБ': 'gosb',
                      'Бизнес-формат': 'bus_format',
                      'id города': 'city_id',
                      'Город': 'city',
                      'Краткий тип НП': 'city_type',
                      'Юр.адрес': 'address',
                      'Общая нормативная площадь': 'norm_square',
                      'избыток, м2': 'diff_square',
                      'Общая фактическая площадь': 'fact_square',
                      'ПШЕ СКМ': 'pshe_skm',
                      'ПШЕ СКМ расч.': 'pshe_skm_calc',
                      'РМ СКМ': 'rm_skm',
                      'ПШЕ СМО': 'pshe_smo',
                      'ПШЕ СМО расч.': 'pshe_smo_calc',
                      'РМ СМО': 'rm_smo',
                      'ПШЕ СМРК': 'pshe_smrk',
                      'ПШЕ СМРК расч.': 'pshe_smrk_calc',
                      'РМ СМРК': 'rm_smrk',
                      'Кол-во ВСП в городе': 'cnt_vsp_incity',
                      'Общая доля перетоков': 'pcnt_overflow',
                      'Широта': 'latitude',
                      'Долгота': 'longitude'}

        name_to_ru = {'urf_code': 'Код ВСП (изменяемое)',
                      'urf_code_near': 'Код ВСП (изменяемое и на которые влияем)',
                      'address': 'Юр.адрес',
                      'city_type': 'Краткий тип НП',
                      'norm_pcnt_time_skm': 'Норматив использования времени СКМ',
                      'norm_pcnt_time_smo': 'Норматив использования времени СМО',
                      'norm_pcnt_time_smrk': 'Норматив использования времени СМРК',
                      'norm_worktime': 'Нормативное время работы',
                      'target_worktime': 'Целевое время работы в неделю',
                      'kbo': 'Коэф. КБО',
                      'norm_up': 'Нормативный УП в сутки на 1 ПШЕ',
                      'conversion': 'Средняя конвертация КП МП в УП МП по городу',
                      'is_smrk_near': 'Флаг СМРК',
                      'new_pcnt_peretok': 'Доля перетока',
                      'sale_up_near': 'Продажи УП СКМ',
                      'kp_skm_near': 'КП СКМ',
                      'kp_smo_near': 'КП СМО',
                      'all_kp_near': 'Общий/СМРК КП',
                      'is_close_near': 'Ключ 1 (изменяемое ВСП) / 0 (ВСП ЛР)',
                      'sale_up_overflow': 'Изменение УП',
                      'kp_skm_overflow': 'Изменение КП СКМ',
                      'kp_smo_overflow': 'Изменение КП СМО',
                      'smrk_kp_overflow': 'Изменение КП СМРК',
                      'new_sale_up': 'Новый УП',
                      'new_kp_skm': 'Новый КП СКМ',
                      'new_kp_smo': 'Новый КП СМО',
                      'new_smrk_kp': 'Новый общий/СМРК КП',
                      'dop_square_rm_skm': 'Требуемая доп.площадь под СКМ',
                      'dop_square_rm_smo': 'Требуемая доп.площадь под СМО',
                      'dop_square_rm_smrk': 'Требуемая доп.площадь под СМРК',
                      'pshe_skm_overflow': 'Изменение ПШЕ СКМ',
                      'new_pshe_skm_calc': 'Новый ПШЕ СКМ',
                      'delta_pshe_skm': 'Изменение ПШЕ СКМ с учетом нагрузки',
                      'delta_rm_skm': 'Требуемое кол-во дополнительных РМ СКМ с учетом изменения УП',
                      'pshe_smo_overflow': 'Изменение ПШЕ СМО',
                      'new_pshe_smo_calc': 'Новый ПШЕ СМО',
                      'delta_pshe_smo': 'Изменение ПШЕ СМО с учетом нагрузки',
                      'delta_rm_smo': 'Требуемое кол-во дополнительных РМ СМО с учетом изменения КП',
                      'pshe_smrk_overflow': 'Изменение ПШЕ СМРК',
                      'new_pshe_smrk_calc': 'Новый ПШЕ СМРК',
                      'delta_pshe_smrk': 'Изменение ПШЕ СМРК с учетом нагрузки',
                      'delta_rm_smrk': 'Требуемое кол-во дополнительных РМ СМРК с учетом изменения КП',
                      'new_pshe_skm': 'Итого необходимо ПШЕ СКМ',
                      'new_rm_skm': 'Итого необходимо РМ СКМ',
                      'new_pshe_smo': 'Итого необходимо ПШЕ СМО',
                      'new_rm_smo': 'Итого необходимо РМ СМО',
                      'new_pshe_smrk': 'Итого необходимо ПШЕ СМРК',
                      'new_rm_smrk': 'Итого необходимо РМ СМРК',
                      'pshe_skm_near': 'ПШЕ СКМ',
                      'pshe_skm_calc': 'ПШЕ СКМ расч.',
                      'rm_skm': 'РМ СКМ',
                      'pshe_smo_near': 'ПШЕ СМО',
                      'pshe_smo_calc': 'ПШЕ СМО расч.',
                      'rm_smo': 'РМ СМО',
                      'pshe_smrk_near': 'ПШЕ СМРК',
                      'pshe_smrk_calc': 'ПШЕ СМРК расч.',
                      'rm_smrk': 'РМ СМРК',
                      'norm_square': 'Площадь норм, м2',
                      'diff_square': 'Дефицит (-)/Избыток (+)',
                      'fact_square': 'Площадь факт, м2',
                      'new_norm_square': 'Нормативная площадь после закрытия ВСП, м2',
                      'new_diff_square': 'Дефицит (-) / Излишек (+) площади после закрытия ВСП, м2'}

        naming = {**name_to_en, **name_to_ru}
        return df.rename(columns=naming)

    @staticmethod
    def unlist(df):
        df['urf_code'] = df['urf_code'].apply(lambda x: ', '.join(x))
        df['address'] = df['address'].apply(lambda x: ', '.join(x))
        df['new_pcnt_peretok'] = df['new_pcnt_peretok'].apply(lambda x: ', '.join(map(lambda num: f"{num:.2f}", x)))
        df['city_type'] = df['city_type'].apply(lambda x: ', '.join(x))
        return df

    def run_analysis(self, is_all_smrk=None):
        """Запуск полного анализа"""

        self.is_all_smrk = is_all_smrk
        self.df_kp_table_asinh = self.base_calc()
        self.df_kp_table_asinh = self.to_form(self.df_kp_table_asinh)
        self.f_df_asinh = self.to_finally(self.df_kp_table_asinh)

        self.df_kp_table_sinh = self.to_sinchro(self.df_kp_table_asinh.query('urf_code in @self.is_close'))

        self.df_kp_table_sinh = self.to_form(self.df_kp_table_sinh)

        self.f_df_sinh = self.unlist(self.to_finally(self.df_kp_table_sinh))

        if len(self.is_bt) > 0:
            self.df_kp_table_bt = self.to_sinchro(self.df_kp_table_asinh.query('urf_code_near in @self.is_bt'))
            self.df_kp_table_bt = self.to_form(self.df_kp_table_bt)
            self.f_df_bt = self.unlist(self.to_finally(self.df_kp_table_bt))

            return self.to_naming(self.f_df_asinh.query('urf_code in @self.is_close')), self.to_naming(
                self.f_df_sinh), self.to_naming(self.f_df_bt)
        return self.to_naming(self.f_df_asinh.query('urf_code in @self.is_close')), self.to_naming(
            self.f_df_sinh), self.to_naming(self.f_df_sinh)
