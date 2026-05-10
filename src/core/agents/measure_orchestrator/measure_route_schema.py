"""Структурированный выбор исполнителя для measure_orchestrator (без transfer tool)."""

from typing import Literal

from pydantic import BaseModel, Field


class MeasureRouteDecision(BaseModel):
    route: Literal["network_optimizer_agent", "relocation_agent"] = Field(
        description="Имя ноды графа: сеть закрытия или перемещение ВСП",
    )
