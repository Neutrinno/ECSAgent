# AI-ассистент единой целевой сети

Ассистент для аналитиков, которые работают с сетью офисов банка (ВСП). Вместо ручного поиска в Excel и разрозненных расчётов можно задать вопрос обычным языком: получить справку по офису, сравнить клиентопоток, оценить последствия закрытия или переноса точки, посмотреть перетоки КП между преемниками.

Данные лежат в SQLite: при старте приложение подгружает отчёты из каталога `data/` (площади, клиентский поток, новые решения). Ответы строятся на этой базе и на предметной логике сети (ЦС, преемники, доли перетока и т.д.).

## Как устроена система

Пользователь пишет в чат (**Streamlit**). Запрос попадает в граф агентов на **LangGraph** — это не один большой промпт, а цепочка ролей с общим состоянием (`GraphState`).

**Control Layer** — входная точка. Решает, можно ли ответить сразу (уточнение, простой вопрос) или нужен полный сценарий. После выполнения плана сюда же возвращается управление: финальный ответ пользователю формируется здесь.

**Planner** — разбивает задачу на шаги: кого вызвать, в каком порядке, что зависит от чего. Несколько независимых шагов могут идти параллельно (группы в плане).

**Orchestrator** — по плану запускает нужного исполнителя и следит, какие шаги уже сделаны. Когда все шаги закрыты — передаёт ход агрегатору.

Исполнители (воркеры), у каждого своя зона:

| Агент | Задачи |
|-------|--------|
| `sql_agent` | Выборки и агрегации по таблицам отчётов |
| `client_flow_agent` | Клиентопоток, динамика, сравнения |
| `network_optimizer_agent` | Сценарии изменения сети, закрытие/оптимизация |
| `relocation_agent` | Переносы, перетоки КП, преемники |

**Aggregator** собирает результаты шагов в один связный ответ.

**Critic** проверяет результат: план не сработал, шаг упал, нужно уточнение у пользователя — или всё в порядке. При ошибке граф может уйти обратно в planner или orchestrator, а не отдавать «сырой» ответ.

Схема потока:

```
control_layer → planner → orchestrator ⇄ воркеры → aggregator → critic → control_layer
```

Агенты работают через **LangChain** / **LangGraph**: каждый шаг графа — вызов LLM и инструментов. Без настроенного провайдера модели запросы не пойдут.

## Стек

| Компонент | Технология |
|-----------|------------|
| Оркестрация агентов | LangGraph, LangChain |
| LLM | OpenRouter (по умолчанию) или GigaChat |
| Хранение данных | SQLite |
| UI | Streamlit |
| Наблюдаемость | LangSmith (опционально) |

## Требования

- Python 3.11–3.13
- [Poetry](https://python-poetry.org/docs/#installation) или pip

## Быстрый старт

### 1. Клонирование и зависимости

```bash
git clone https://github.com/Neutrinno/ECSAgent-.git
cd ECSAgent-

poetry install
```

### 2. Конфигурация окружения

Создайте файл `.env` на основе шаблона:

```bash
# Windows
copy env_example .env

# Linux / macOS
cp env_example .env
```

Заполните обязательные значения (см. раздел [Переменные окружения](#переменные-окружения)). Файл `.env` не должен попадать в систему контроля версий.

**Минимум, чтобы завелись LangChain и граф агентов:**

1. `LLM_PROVIDER=openrouter` и непустой `OPENROUTER_API_KEY` (ключ на [openrouter.ai](https://openrouter.ai/keys)).
2. При установке через pip — пакет `langchain-openai` (для OpenRouter; в `poetry install` уже входит).

**LangSmith** (логи и трассировка вызовов в [smith.langchain.com](https://smith.langchain.com/)):

- при `LANGSMITH_TRACING=true` обязателен `LANGSMITH_API_KEY` (создаётся в личном кабинете LangSmith → Settings → API Keys);
- `LANGSMITH_PROJECT` — имя проекта, куда складываются трейсы (в шаблоне `AgentEcs`).
- если трассировка не нужна, поставьте `LANGSMITH_TRACING=false` — остальные `LANGSMITH_*` можно не заполнять.

Переменные из `.env` подхватываются при старте (`python-dotenv`); LangChain/LangSmith читают их из окружения автоматически.

### 3. Исходные данные (опционально)

Для полноценной работы с отчётами разместите Excel-файлы в каталоге `data/`:

| Файл | Назначение |
|------|------------|
| `Отчет по площади.xlsx` | Основной отчёт по площадям ВСП |
| `Новые решения.xlsx` | Данные по новым решениям |
| `client_flow.xlsx` | Клиентский поток |

Каталог `data/` создаётся автоматически при первом запуске.

### 4. Запуск

```bash
poetry run streamlit run src/app.py
```

Приложение будет доступно по адресу, указанному в консоли (по умолчанию: http://localhost:8501).

## Переменные окружения

Полный шаблон — в файле [`env_example`](env_example).

| Назначение | Что обязательно |
|------------|-----------------|
| Запуск LLM и графа | `LLM_PROVIDER`, `OPENROUTER_API_KEY` (или GigaChat + сертификаты) |
| Трассировка LangSmith | `LANGSMITH_TRACING=true` → нужен `LANGSMITH_API_KEY` |

### LLM (OpenRouter)

| Переменная | Обязательность | Описание |
|------------|----------------|----------|
| `LLM_PROVIDER` | Да | Провайдер модели: `openrouter` или `gigachat` |
| `OPENROUTER_API_KEY` | Да* | API-ключ [OpenRouter](https://openrouter.ai/) |
| `OPENROUTER_BASE_URL` | Нет | Базовый URL API (по умолчанию: `https://openrouter.ai/api/v1`) |
| `OPENROUTER_MODEL` | Нет | Идентификатор модели (по умолчанию: `qwen/qwen3.6-flash`) |

\* Обязательно при `LLM_PROVIDER=openrouter`.

### LangSmith (трассировка LangChain)

| Переменная | Обязательность | Описание |
|------------|----------------|----------|
| `LANGSMITH_TRACING` | Нет | `true` — отправлять трейсы в LangSmith; `false` — выключить |
| `LANGSMITH_API_KEY` | Да* | API-ключ из [LangSmith](https://smith.langchain.com/settings) |
| `LANGSMITH_ENDPOINT` | Нет | Обычно не меняют: `https://api.smith.langchain.com` |
| `LANGSMITH_PROJECT` | Нет | Имя проекта в UI LangSmith (в шаблоне: `AgentEcs`) |

\* Обязательно, если `LANGSMITH_TRACING=true`. Без ключа при включённой трассировке возможны ошибки или пустые трейсы.

### Пример `.env`

```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=<your_api_key>
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=qwen/qwen3.6-flash

LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=<your_api_key>
LANGSMITH_PROJECT=AgentEcs
```

### Альтернатива: GigaChat

При `LLM_PROVIDER=gigachat` укажите `GIGACHAT_URL` и разместите TLS-сертификаты:

- `cert/cert_pem.txt`
- `cert/private_key.txt`

## Установка без Poetry

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
# source .venv/bin/activate

pip install -r requirements.txt
pip install langchain-openai

streamlit run src/app.py
```

Пакет `langchain-openai` требуется для работы через OpenRouter.
