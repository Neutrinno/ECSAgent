from typing import Tuple, Optional
from geopy.geocoders import Nominatim
from langchain_core.tools import tool
from src.utils.logger import get_logger

logger = get_logger(__name__)


@tool
def get_coordinates(address: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Инструмент для получения координат (широты и долготы) по адресу используя геокодинг.

    Args:
        address: Адрес для поиска координат (например, "Санкт-Петербург, Ветеранов, 14")
        Формат адреса: "Город, Улица, Номер дома" без лишних символов

        !ВАЖНО: НЕ используй обозначения, например, "ул.", "д.", "г.", "пос." и т.д. и НЕ используй добавления в номерах домов типа /1
            Примеры корректных адресов:
            "Санкт-Петербург, Ветеранов, 14" - корректно
            "ул. Санкт-Петербург, ул. Ветеранов, д. 14/3" - НЕ корректно

    Returns:
        Кортеж с двумя элементами:
        - latitude: float или None - широта
        - longitude: float или None - долгота
        Если адрес не найден, возвращает (None, None)
    """
    logger.info(f"Поиск координат для адреса: {address}")

    geolocator = Nominatim(user_agent="dyatel")

    try:
        location = geolocator.geocode(address)
        if location:
            logger.info(f"Координаты найдены: {location.address} "
                        f"({location.latitude}, {location.longitude})")
            return location.latitude, location.longitude
        else:
            logger.warning(f"Адрес '{address}' не найден")
            return None, None

    except Exception as e:
        error_msg = f"Ошибка при геокодинге: {str(e)}"
        logger.error(error_msg)
        return None, None


if __name__ == "__main__":
    test_address = "Санкт-Петербург, Ветеранов, 14"
    latitude, longitude = get_coordinates.invoke({"address": test_address})

    if latitude is not None and longitude is not None:
        print(f"Широта: {latitude}")
        print(f"Долгота: {longitude}")
    else:
        print("Координаты не найдены")