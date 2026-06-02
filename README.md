# AI-ассистент единой целевой сети

Ассистент для аналитиков сети офисов банка (ВСП). Пользователь задаёт вопрос в чате на естественном языке — система отвечает по данным отчётов: справка по офису, клиентопоток, сценарии закрытия и переноса, перетоки КП.

**Стек:** LangGraph + LangChain, LLM (OpenRouter или GigaChat), SQLite, UI на Streamlit.
<img width="1819" height="942" alt="image" src="https://github.com/user-attachments/assets/7bfcb031-6cca-40d8-a10a-0440969bb22d" />


## Как устроено

<img width="978" height="660" alt="image" src="https://github.com/user-attachments/assets/4453aab3-8beb-4eb6-b2a0-611192760cd5" />

Запрос обрабатывается не одной моделью, а **графом агентов** с общим состоянием:

| Узел | Роль |
|------|------|
| **Control Layer** | Вход: понимает запрос, решает — ответить сразу или запустить полный сценарий; отдаёт финальный ответ |
| **Planner** | Строит план шагов и зависимостей между ними |
| **Orchestrator** | Запускает шаги по плану (в т.ч. параллельно) |
| **Воркеры** | `sql_agent`, `client_flow_agent`, `network_optimizer_agent`, `relocation_agent` |
| **Aggregator** | Собирает результаты шагов в один ответ |
| **Critic** | Проверяет качество; при ошибке — возврат в planner или orchestrator |

```
control_layer → planner → orchestrator ⇄ воркеры → aggregator → critic → control_layer
```

При старте Excel из `data/` загружается в локальную SQLite; дальше воркеры работают с этой базой и инструментами.

## Демо-данные для проверки

В репозитории в `data/` включён **только** файл `Отчет по площади.xlsx` — **синтетические данные** для демонстрации на время сдачи диплома. Этого достаточно для базовой проверки (справка по ВСП).

Файлы `Новые решения.xlsx` и `client_flow.xlsx` в репозиторий **не входят**; при необходимости их можно положить в `data/` локально.

## Быстрый старт

**Требования:** Python 3.11–3.13, [Poetry](https://python-poetry.org/docs/#installation) или pip.

### 1. Клонирование

```bash
git clone https://github.com/Neutrinno/ECSAgent.git
cd ECSAgent

poetry install
```

Репозиторий: [github.com/Neutrinno/ECSAgent](https://github.com/Neutrinno/ECSAgent)

### 2. Переменные окружения

```bash
cp env_example .env      # Linux / macOS
copy env_example .env    # Windows (cmd)
```

Скопируйте шаблон [`env_example`](env_example) в `.env` в корне проекта (файл `.env` в Git не попадает).

Обязательно для запуска:

| Переменная | Описание |
|------------|----------|
| `LLM_PROVIDER` | `openrouter` (как в шаблоне) или `gigachat` |
| `OPENROUTER_API_KEY` | Ключ [OpenRouter](https://openrouter.ai/keys) |

Остальные поля OpenRouter в `env_example` можно не менять. Файл `.env` не коммитить.

Для **GigaChat:** `LLM_PROVIDER=gigachat`, `GIGACHAT_URL`, сертификаты в `cert/cert_pem.txt` и `cert/private_key.txt`.

### 3. Запуск

```bash
poetry run streamlit run src/app.py
```

Откройте в браузере адрес из консоли (обычно http://localhost:8501).

### 4. Пример запроса

В чате UI:

```
Напиши номер всп, адрес, площадь и количество рабочих мест для ВСП 1775_175
```

Ожидается ответ с полями по этому офису из демо-отчёта.

## Установка без Poetry

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS

pip install -r requirements.txt
pip install langchain-openai

streamlit run src/app.py
```

---

## LangSmith (опционально)

Трассировка шагов графа в [LangSmith](https://smith.langchain.com/) — **не обязательна** для проверки работы системы.

| Переменная | Описание |
|------------|----------|
| `LANGSMITH_TRACING` | `true` — включить, `false` — выключить |
| `LANGSMITH_API_KEY` | Ключ из настроек LangSmith (нужен при `TRACING=true`) |
| `LANGSMITH_PROJECT` | Имя проекта в UI (в шаблоне: `AgentEcs`) |
| `LANGSMITH_ENDPOINT` | По умолчанию `https://api.smith.langchain.com` |

Для сдачи достаточно `LANGSMITH_TRACING=false` — остальные `LANGSMITH_*` можно не заполнять.
