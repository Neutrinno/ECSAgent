from sqlalchemy import Column, Integer, String, Text, UniqueConstraint, Index, ForeignKeyConstraint
from sqlalchemy.orm import declarative_base
from sqlalchemy import Float, Date

Base = declarative_base()


class VSPCore(Base):
    """
    Базовая информация о ВСП
    """
    __tablename__ = 'vsp_core'

    id = Column(Integer, primary_key=True, autoincrement=True)
    urf_code = Column(String(50), nullable=False, index=True,
                      comment="Уникальный код объекта (УРФ код) для связи с другими системами")
    gosb_vsp = Column(String(50), nullable=True, index=True, comment="Номер ВСП")
    report_dt = Column(Date, nullable=False, index=True, comment="Дата отчёта (извлекается из названия файла)")

    tb_name = Column(String(255), nullable=True, comment="Название территориального банка")
    gosb_id = Column(String(50), nullable=True, comment="Идентификатор головного отдела банка (ГОСБ)")
    vsp_type = Column(String(50), nullable=True, comment="Тип отделения ВСП")
    business_format = Column(String(50), nullable=True, comment="Формат бизнеса отделения (стандарт, премиум и т.д.)")

    region = Column(String(100), nullable=True, comment="Регион расположения отделения")
    city_id = Column(String(50), nullable=True, comment="Идентификатор населенного пункта")
    city = Column(String(100), nullable=True, comment="Город расположения отделения")
    city_short = Column(String(100), nullable=True, comment="Короткое название города (без префиксов и районов)")
    city_type = Column(String(50), nullable=True, comment="Тип населенного пункта")

    is_village = Column(Integer, default=0, comment="Признак сельского отделения (1 - сельское, 0 - городское)")
    is_fantom = Column(Integer, default=0, comment="Признак фантомного объекта (1 - фантомный, 0 - нет)")

    city_vsp_qty = Column(Integer, nullable=True, comment="Количество рабочих ВСП в населенном пункте")
    is_mb_isolated = Column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint('urf_code', 'report_dt', name='uq_urf_report_date'),
        Index('idx_urf_date', 'urf_code', 'report_dt'),
        )


class VSPAddress(Base):
    """
    Адресная информация и геолокация ВСП.
    Хранит юридические и фактические адреса с географическими координатами.
    """
    __tablename__ = 'vsp_address'

    id = Column(Integer, primary_key=True, autoincrement=True, comment="Автоинкрементный идентификатор записи")
    report_dt = Column(Date, nullable=False, index=True,  comment="Дата отчета (месяц), часть составного ключа")
    urf_code = Column(String(50), nullable=False, index=True, comment="Уникальный код ВСП, часть составного ключа")

    legal_address = Column(String(500), nullable=True,  comment="Юридический адрес ВСП")
    legal_address_latitude = Column(Float, nullable=True, comment="Широта юр.адреса ВСП")
    legal_address_longitude = Column(Float, nullable=True, comment="Долгота юр.адреса ВСП")

    fact_address = Column(String(500), nullable=True, comment="Фактический адрес ВСП")
    vsp_fact_address_latitude = Column(Float, nullable=True, comment="Широта факт.адреса ВСП")
    vsp_fact_address_longitude = Column(Float, nullable=True, comment="Долгота факт.адреса ВСП")

    __table_args__ = (
        ForeignKeyConstraint(['urf_code', 'report_dt'],
                             ['vsp_core.urf_code', 'vsp_core.report_dt']),
        Index('idx_addr_urf_date', 'urf_code', 'report_dt')
    )


class VSPTimeline(Base):
    """
    Календарные события, планы и графики работы ВСП.
    Хранит даты ключевых событий (переформатирование, закрытие) и рабочее расписание.
    """
    __tablename__ = 'vsp_timeline'

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_dt = Column(Date, nullable=False, index=True)
    urf_code = Column(String(50), nullable=False, index=True)

    reformat_dt = Column(Date, nullable=True, comment="Дата переформатирования ВСП")
    vsp_reformat_end_dt = Column(Date, nullable=True, comment="Плановая дата переформатирования ВСП")
    plan_close_dt = Column(Date, nullable=True, comment="Плановая дата закрытия ВСП")
    close_type_flag = Column(Integer, nullable=True, comment="Признак ВСП закрытого типа (1=ОО GR, 2=отдельный ЦПО)")

    vsp_work_dt = Column(String(255), nullable=True, comment="Дни работы ВСП (общее описание)")
    work_day_week_6_m_qty = Column(Integer, nullable=True, comment="Количество рабочих дней ВСП в неделю (данные за полгода)")
    emp_work_week_6_m_h_cnt = Column(Float, nullable=True, comment="Рабочее время сотрудника ВСП в неделю (данные за полгода)")
    vsp_work_week_6_m_h_cnt = Column(Float, nullable=True, comment="Рабочее время ВСП в неделю (данные за полгода)")

    __table_args__ = (
        ForeignKeyConstraint(['urf_code', 'report_dt'],
                             ['vsp_core.urf_code', 'vsp_core.report_dt']),
        Index('idx_tl_urf_date', 'urf_code', 'report_dt')
    )


class VSPArea(Base):
    """
    Нормативные и фактические площади помещений ВСП по функциональным зонам.
    Содержит площади для различных бизнес-направлений (БСП, ЦПО, КИБ, ЦИК, ВИП)
    и их отклонения от нормативов.
    """
    __tablename__ = 'vsp_area'

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_dt = Column(Date, nullable=False, index=True)
    urf_code = Column(String(50), nullable=False, index=True)

    normative_area = Column(Float, nullable=True, comment="Общая нормативная площадь, м²")
    normative_rb_area = Column(Float, nullable=True, comment="Нормативная площадь БСП, м²")
    norm_cpo_area = Column(Float, nullable=True, comment="Нормативная площадь ЦПО, м²")
    normative_cb_area = Column(Float, nullable=True, comment="Нормативная площадь КИБ, м²")
    normative_cik_area = Column(Float, nullable=True, comment="Нормативная площадь РБ ЦИК, м²")
    normative_eco_area = Column(Float, nullable=True, comment="Нормативная площадь элементов Экосистемы, м²")
    norm_vip_area = Column(Float, nullable=True, comment="Нормативная площадь ВИП-ВСП, м²")

    total_area = Column(Float, nullable=True, comment="СБР - Общая фактическая площадь, м² (АСУН)")
    main_area = Column(Float, nullable=True, comment="СБР - Основная площадь ВСП, м²")
    aux_area = Column(Float, nullable=True, comment="СБР - Вспомогательная площадь ВСП, м²")
    bsp_area = Column(Float, nullable=True, comment="СБР - Площадь БСП, м²")
    cpo_bsp_area = Column(Float, nullable=True, comment="СБР-Площадь ЦПО на орг единицах БСП, м²")
    cpo_area = Column(Float, nullable=True, comment="СБР-Площадь ЦПО, м²")
    cik_area = Column(Float, nullable=True, comment="СБР Площадь ЦИК РБ, м²")
    kib_area = Column(Float, nullable=True, comment="СБР - Площадь КИБ, м²")
    vip_area = Column(Float, nullable=True, comment="СБР - Площадь ВИП ВСП, м²")

    diff_area = Column(Float, nullable=True, comment="Расчетный дефицит (-) / излишек (+) площади ВСП, м²")
    diff_area_bsp = Column(Float, nullable=True, comment="Расчетный дефицит (-) / излишек (+) площади БСП, м²")
    diff_area_cpo = Column(Float, nullable=True,  comment="Расчетный дефицит (-) / излишек (+) площади ЦПО, м²")
    diff_area_cik = Column(Float, nullable=True, comment="Расчетный дефицит (-) / излишек (+) площади ЦИК, м²")
    diff_area_cib = Column(Float, nullable=True, comment="Расчетный дефицит (-) / излишек (+) площади КИБ, м²")
    diff_area_vip = Column(Float, nullable=True, comment="Расчетный дефицит (-) / излишек (+) площади ВИП-ВСП, м²")

    area_hck = Column(Float, nullable=True, comment="Площадь ХЦК, м²")
    has_hck = Column(Integer, nullable=True, comment="ХЦК в целевой сети (флаг: 1 - есть, 0 - нет)")
    rm_norm_area = Column(Float, nullable=True, comment="СБР - Фактическая площадь на 1 РМ (рабочее место), м²")

    __table_args__ = (
        ForeignKeyConstraint(['urf_code', 'report_dt'],
                             ['vsp_core.urf_code', 'vsp_core.report_dt']),
        Index('idx_area_urf_date', 'urf_code', 'report_dt'),
    )


class VSPWorkplace(Base):
    """
    Кадровое обеспечение и инфраструктура рабочих мест ВСП.
    Содержит данные по фактическим и плановым рабочим местам, целевым показателям (ПШЕ)
    и вспомогательной инфраструктуре (переговорные, УС).
    """
    __tablename__ = 'vsp_workplace'

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_dt = Column(Date, nullable=False, index=True)
    urf_code = Column(String(50), nullable=False, index=True)

    wp_rvsp_cnt = Column(Integer, nullable=True, comment="РМ РВСП (руководитель ВСП)")
    wp_zrvsp_cnt = Column(Integer, nullable=True, comment="РМ ЗРВСП (заместитель руководителя ВСП)")
    wp_rrcpo_cnt = Column(Integer, nullable=True, comment="РМ РЦПО (руководитель центра поддержки обслуживания)")
    wp_rvsp_vip_cnt = Column(Integer, nullable=True, comment="РМ РВИП ВСП (руководитель ВИП ВСП)")
    wp_mp_cnt = Column(Integer, nullable=True, comment="РМ СКМ (менеджер по продажам среднего бизнеса)")
    wp_smo_cnt = Column(Integer, nullable=True, comment="РМ СМО (специалист по малым предприятиям)")
    wp_smrk_cnt = Column(Integer, nullable=True,  comment="РМ СМРК (специалист по малому бизнесу и работе с клиентами)")
    wp_mrk_cnt = Column(Integer, nullable=True, comment="РМ МРК (менеджер по работе с клиентами)")
    wp_premier_cnt = Column(Integer, nullable=True, comment="РМ КМ премиум-сегмента (ключевой менеджер)")
    wp_vip_cnt = Column(Integer, nullable=True, comment="РМ ВИП (менеджер по обслуживанию VIP-клиентов)")
    wp_rcik_cnt = Column(Integer, nullable=True, comment="РМ РЦИК (руководитель цифровых каналов)")
    wp_mik_cnt = Column(Integer, nullable=True, comment="РМ МИК (менеджер по микро-бизнесу)")
    wp_moik_cnt = Column(Integer, nullable=True, comment="РМ МОИК (менеджер по малому и среднему бизнесу)")

    wp_manager_point_sale_cnt = Column(Integer, nullable=True, comment="Руководитель точки продаж (КБ)")
    wp_km_mkk_cnt = Column(Integer, nullable=True, comment="РМ КМ МКК (КБ) (ключевой менеджер МКК)")
    wp_km_mmb_cnt = Column(Integer, nullable=True, comment="РМ КМ малого и микро-бизнеса (КБ)")
    wp_akm_cb_cnt = Column(Integer, nullable=True, comment="РМ ГКМ (КБ) (администратор/главный ключевой менеджер)")

    wp_plan_rb_cnt = Column(Integer, nullable=True, comment="Плановое число рабочих мест БСП и ЦПО")
    wp_plan_cik_cnt = Column(Integer, nullable=True, comment="Плановое число рабочих мест ЦИК")
    wp_plan_cb_cnt = Column(Integer, nullable=True, comment="Плановое число рабочих мест КБ")
    wp_plan_vip_cnt = Column(Integer, nullable=True, comment="Плановое число рабочих мест ВИП")
    wp_plan_cnt = Column(Integer, nullable=True, comment="Общее плановое число рабочих мест")

    pse_smo_cnt = Column(Float, nullable=True, comment="ПШЕ СМО (ИУЧ)")
    pse_mp_cnt = Column(Float, nullable=True,  comment="ПШЕ СКМ (ИУЧ)")
    pse_mik_cnt = Column(Float, nullable=True, comment="ПШЕ МИК (целевое)")
    pse_moik_cnt = Column(Float, nullable=True, comment="ПШЕ МОИК (целевое)")
    pse_smrk_cnt = Column(Float, nullable=True, comment="ПШЕ СМРК (ИУЧ)")
    pse_mrk_cnt = Column(Float, nullable=True, comment="ПШЕ МРК (ИУЧ)")


    meetrig_room_cnt = Column(Integer, nullable=True, comment="Количество переговорных комнат ЦИК")
    us_cnt = Column(Integer, nullable=True, comment="Количество УС (устройств самообслуживания всех видов)")

    __table_args__ = (
        ForeignKeyConstraint(['urf_code', 'report_dt'],
                             ['vsp_core.urf_code', 'vsp_core.report_dt']),
        Index('idx_wp_urf_date', 'urf_code', 'report_dt'),
    )


class VSPOperations(Base):
    """
    Операционные показатели эффективности и клиентская активность ВСП.
    Содержит метрики по продажам, клиентопотоку и транзакционной активности.

    """
    __tablename__ = 'vsp_operations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_dt = Column(Date, nullable=False, index=True)
    urf_code = Column(String(50), nullable=False, index=True)

    up_kp = Column(Float, nullable=True, comment="Продажи УП (управление продажами)")

    kp_skm = Column(Float, nullable=True, comment="Клиентопоток СКМ (средний и крупный бизнес)")
    kp_smo = Column(Float, nullable=True, comment="Клиентопоток СМО (малые предприятия)")
    kp_smrk = Column(Float, nullable=True, comment="Клиентопоток СМРК (малый бизнес и работа с клиентами)")
    all_kp = Column(Float, nullable=True, comment="Общий клиентопоток по всем категориям")

    oper_transakt = Column(Float, nullable=True, comment="Транзакционные операции (обслуживающие)")
    oper_sale = Column(Float, nullable=True, comment="Продажные операции (коммерческие)")
    all_oper = Column(Float, nullable=True, comment="Всего операций (сумма транзакционных и продажных)")

    __table_args__ = (
        ForeignKeyConstraint(['urf_code', 'report_dt'],
                             ['vsp_core.urf_code', 'vsp_core.report_dt']),
        Index('idx_ops_urf_date', 'urf_code', 'report_dt'),
    )


class VSPProperty(Base):
    """
    Юридические и экономические условия использования помещений ВСП.
    Содержит информацию о правах собственности, арендных ставках и управленческих решениях по недвижимости.
    """
    __tablename__ = 'vsp_property'

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_dt = Column(Date, nullable=False, index=True)
    urf_code = Column(String(50), nullable=False, index=True)

    form_rght_name = Column(String(255), nullable=True, comment="Право на помещение ВСП (аренда, собственность)")
    ownership_area_perc = Column(Float, nullable=True, comment="Доля помещения ВСП в собственности")

    rent_rate_avg = Column(Float, nullable=True, comment="Средняя ставка аренды (руб. в мес. за м2 с учетом НДС)")
    rpi_rate_avg_area = Column(Float, nullable=True, comment="Средняя ставка вмененной аренды (руб. в мес. за м2)")

    # separ_poss = Column(String(255), nullable=True,
    #                     comment="Возможность разделения помещения")
    # separ_focus_kun_area_decision = Column(String(255), nullable=True,
    #                                        comment="Решение по КУН для фокусировки на площади")
    # separ_selo_kun = Column(String(255), nullable=True,
    #                         comment="Решение по КУН для сельских отделений")

    __table_args__ = (
        ForeignKeyConstraint(['urf_code', 'report_dt'],
                             ['vsp_core.urf_code', 'vsp_core.report_dt']),
        Index('idx_prop_urf_date', 'urf_code', 'report_dt'),
    )


class NewSolution(Base):
    """
    Модель для хранения данных по новым решениям
    """
    __tablename__ = 'new_solution'

    id = Column(Integer, primary_key=True, autoincrement=True)

    urf_code = Column(String(50), nullable=True, index=True, comment="Уникальный код объекта (УРФ код)")
    tb_name = Column(String(255), nullable=True, comment="Название территориального банка")
    address = Column(Text, nullable=True, comment="Адрес")

    actual_decision_cs = Column(Text, nullable=True, comment="Актуальное решение по ЦС")
    actual_event_year = Column(String(4), nullable=True, comment="Актуальный год мероприятия")
    decision_kun_cs_vsp = Column(Text, nullable=True, comment="Решение КУН ЦС ВСП")
    event_year_kun_cs_vsp = Column(String(4), nullable=True, comment="Год мероприятия КУН ЦС ВСП")

    closing_decision = Column(Text, nullable=True, comment="Решение о закрытии")
    closing_date = Column(Date, nullable=True, comment="Дата закрытия факт/план")
    comments = Column(Text, nullable=True, comment="Комментарии")


class ClientFlow(Base):
    """
    Модель для хранения данных по клиентскому потоку
    """
    __tablename__ = 'client_flow'

    id = Column(Integer, primary_key=True, autoincrement=True)

    urf_code = Column(String(50), nullable=True, index=True, comment="УРФ код объекта")

    # Территориальная принадлежность
    tb = Column(String, nullable=True, comment="Территориальный банк")
    gosb = Column(String, nullable=True, comment="ГОСБ")
    city_id = Column(String, nullable=True, comment="ID города")
    city = Column(String, nullable=True, comment="Город")

    # Тип и период
    type_np = Column(String(100), nullable=True, comment="Тип НП")
    year = Column(String(4), nullable=True, index=True, comment="Год")
    month = Column(Date, nullable=True, comment="Месяц")

    # Показатели
    up = Column(Integer, nullable=True, comment="УП")
    kp_skm = Column(Integer, nullable=True, comment="КП СКМ")
    kp_smo = Column(Integer, nullable=True, comment="КП СМО")
    total_kp = Column(Integer, nullable=True, comment="Общий КП")
