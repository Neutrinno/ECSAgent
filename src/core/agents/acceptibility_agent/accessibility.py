import pandas as pd
import math
import os
from pathlib import Path


def _project_root() -> Path:
    # .../src/core/agents/acceptibility_agent/accessibility.py → корень репозитория
    return Path(__file__).resolve().parents[4]


def load_data():
    """Загрузка данных из файлов в папке data"""

    data_dir = str(_project_root() / "data")

    print(f"Директория с данными: {data_dir}")

    if not os.path.exists(data_dir):
        raise FileNotFoundError(f"Папка 'data' не найдена: {data_dir}")

    hex_path = os.path.join(data_dir, 'hex_epk_region_pd.xlsx')
    vsp_path = os.path.join(data_dir, 'Список_ВСП.xlsx')

    print(f"Путь к файлу гексов: {hex_path}")
    print(f"Путь к файлу ВСП: {vsp_path}")

    if not os.path.exists(hex_path):
        raise FileNotFoundError(f"Файл не найден: {hex_path}")
    if not os.path.exists(vsp_path):
        raise FileNotFoundError(f"Файл не найден: {vsp_path}")

    hex_df = pd.read_excel(
        hex_path,
        decimal=','
    )

    vsp_df = pd.read_excel(
        vsp_path,
        decimal=','
    )

    print(f"\nДоступные city_id в данных ВСП: {vsp_df['city_id'].unique()}")

    vsp_df['city_id'] = pd.to_numeric(vsp_df['city_id'], errors='coerce')
    vsp_df_filtered = vsp_df[vsp_df['city_id'] == 65].copy()

    print(f"Загружено {len(hex_df)} гексов")
    print(f"Загружено {len(vsp_df_filtered)} ВСП для Йошкар-Олы (всего ВСП в файле: {len(vsp_df)})")

    print("\nКолонки в гексах:", hex_df.columns.tolist())
    print("Колонки в ВСП:", vsp_df_filtered.columns.tolist())

    return hex_df, vsp_df_filtered


def haversine(lat1, lon1, lat2, lon2):
    """Расчет расстояния по формуле Haversine"""
    R = 6373.0

    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)
    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def calculate_distance_matrix(hex_coords, vsp_coords):
    """Рассчитывает матрицу расстояний между всеми гексами и ВСП по прямой"""

    distances = []
    for hex_lat, hex_lng in hex_coords:
        row = []
        for vsp_lat, vsp_lng in vsp_coords:
            dist = haversine(hex_lat, hex_lng, vsp_lat, vsp_lng)
            row.append(dist)
        distances.append(row)

    return pd.DataFrame(distances)


def find_nearest_vsp(distance_matrix, hex_ids, vsp_ids):
    """Для каждого гекса находит ближайший ВСП"""
    nearest_indices = distance_matrix.idxmin(axis=1)
    min_distances = distance_matrix.min(axis=1)

    result = pd.DataFrame({
        'hex_id': hex_ids,
        'nearest_vsp_id': [vsp_ids[idx] for idx in nearest_indices],
        'min_distance': min_distances.values,
        'vsp_index': nearest_indices.values
    })

    return result


def calculate_accessibility(hex_df, vsp_df, vsp_filter_list=None):
    """
    Основная функция расчета доступности по прямой

    Args:
        hex_df: DataFrame гексов [hex_id, lat, lng, cnt_epk]
        vsp_df: DataFrame ВСП [urf_code, geo_lat, geo_lng]
        vsp_filter_list: список URF-кодов ВСП для расчета (если None - все ВСП)

    Returns:
        dict с результатами
    """
    if vsp_filter_list is not None:
        vsp_df = vsp_df[vsp_df['urf_code'].isin(vsp_filter_list)].copy()

    if len(vsp_df) == 0:
        raise ValueError("Нет ВСП для расчета после фильтрации")

    hex_coords = list(zip(hex_df['lat'], hex_df['lng']))
    vsp_coords = list(zip(vsp_df['geo_lat'], vsp_df['geo_lng']))

    hex_ids = hex_df['hex_id'].tolist()
    vsp_ids = vsp_df['urf_code'].tolist()

    print(f"Расчет матрицы расстояний: {len(hex_coords)} гексов × {len(vsp_coords)} ВСП")
    distance_matrix = calculate_distance_matrix(hex_coords, vsp_coords)
    print("Матрица расстояний рассчитана:\n", distance_matrix.head())

    hex_assignments = find_nearest_vsp(distance_matrix, hex_ids, vsp_ids)

    assignments_with_pop = pd.merge(
        hex_assignments,
        hex_df[['hex_id', 'cnt_epk']],
        on='hex_id'
    )

    total_population = assignments_with_pop['cnt_epk'].sum()

    if total_population == 0:
        raise ValueError("Общее количество клиентов равно 0")

    weighted_sum = (assignments_with_pop['min_distance'] * assignments_with_pop['cnt_epk']).sum()
    accessibility = weighted_sum / total_population

    summary_stats = {
        'max_distance': assignments_with_pop['min_distance'].max(),
        'median_distance': assignments_with_pop['min_distance'].median(),
        'population_within_1km': assignments_with_pop[assignments_with_pop['min_distance'] <= 1]['cnt_epk'].sum(),
        'population_within_2km': assignments_with_pop[assignments_with_pop['min_distance'] <= 2]['cnt_epk'].sum(),
        'num_hexes': len(hex_df),
        'num_vsp': len(vsp_df)
    }

    return {
        'accessibility': accessibility,
        'total_population': total_population,
        'hex_assignments': assignments_with_pop,
        'summary_stats': summary_stats
    }


def main():
    try:
        hex_df, vsp_df = load_data()

        print(f"\nПервые 3 строки гексов:")
        print(hex_df.head(3))
        print(f"\nПервые 3 строки ВСП:")
        print(vsp_df[['urf_code', 'geo_lat', 'geo_lng']].head(3))

        vsp_list_2025 = [
            '042_8614_013', '042_8614_015', '042_8614_017', '042_8614_018',
            '042_8614_019', '042_8614_028', '042_8614_06', '042_8614_068',
            '042_8614_07', '042_8614_09'
        ]

        vsp_filtered = vsp_df[vsp_df['urf_code'].isin(vsp_list_2025)].copy()

        print(f"\nОтфильтровано {len(vsp_filtered)} ВСП для расчета 2025 года")

        found_vsp = set(vsp_filtered['urf_code'])
        missing = set(vsp_list_2025) - found_vsp
        if missing:
            print(f"Внимание! Не найдены ВСП: {missing}")
        else:
            print("Все ВСП из списка 2025 года найдены")

        result = calculate_accessibility(
            hex_df=hex_df,
            vsp_df=vsp_filtered,
            vsp_filter_list=None
        )

        print(f"\n{'=' * 50}")
        print("📊 РЕЗУЛЬТАТЫ РАСЧЕТА ДОСТУПНОСТИ ДЛЯ ЙОШКАР-ОЛЫ")
        print(f"{'=' * 50}")
        print(f"Среднее расстояние до ближайшего ВСП: {result['accessibility']:.2f} км")
        print(f"Общее число клиентов: {result['total_population']:,}")
        print(f"Максимальное расстояние: {result['summary_stats']['max_distance']:.2f} км")
        print(f"Медианное расстояние: {result['summary_stats']['median_distance']:.2f} км")
        print(
            f"Клиентов в радиусе 1 км: {result['summary_stats']['population_within_1km']:,} ({result['summary_stats']['population_within_1km'] / result['total_population'] * 100:.1f}%)")
        print(
            f"Клиентов в радиусе 2 км: {result['summary_stats']['population_within_2km']:,} ({result['summary_stats']['population_within_2km'] / result['total_population'] * 100:.1f}%)")
        print(f"Количество гексов: {result['summary_stats']['num_hexes']}")
        print(f"Количество ВСП: {result['summary_stats']['num_vsp']}")

        data_dir = str(_project_root() / "data")
        output_path = os.path.join(data_dir, "hex_assignments_2025.csv")

        result['hex_assignments'].to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"\n✅ Привязки сохранены в: {output_path}")

    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
