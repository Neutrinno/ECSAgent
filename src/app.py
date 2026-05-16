import sys
from pathlib import Path

from dotenv import load_dotenv

# Должно выполняться до любых `from src...`, иначе Streamlit не видит пакет `src`.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from typing import List
from uuid import uuid4

import streamlit as st
from sqlalchemy import inspect, text

from src.core.agents.service_manager import service_manager
from src.core.llm_utils.agent_init import start_agent
from src.database.models import Base
from src.file_upload.processor import VSPDataProcessor, logger
from src.file_upload.new_solution_processor import NewSolutionProcessor
from src.file_upload.client_flow_processor import ClientFlowProcessor
from config import REPORTS_DIRECTORY


class AreaAssistantApp:
    def __init__(self):
        self._init_page_config()
        self._init_ui_content()
        self._init_session_state()

        self._init_services()

    @staticmethod
    def _init_page_config():
        """Инициализация конфига страницы"""
        st.set_page_config(
            page_title="AI ассистент по площадям",
            page_icon="📊",
            layout="wide",
            initial_sidebar_state="collapsed"
        )

    @staticmethod
    def _init_ui_content():
        """Инициализация интерфейса"""
        st.markdown("""
            <style>
                .main-header {
                    font-size: 2.5rem;
                    color: #1f77b4;
                    margin-bottom: 0.5rem;
                }
                .subheader {
                    font-size: 1.2rem;
                    color: #7f7f7f;
                    margin-bottom: 2rem;
                }
                .stButton>button {
                    width: 100%;
                    transition: all 0.3s;
                    border-radius: 8px;
                }
                .stButton>button:hover {
                    background-color: #f0f2f6;
                    transform: translateY(-2px);
                }
                div.block-container {
                    padding-top: 1rem;
                    padding-bottom: 1rem;
                }
                .chat-message {
                    padding: 1rem;
                    border-radius: 0.5rem;
                    margin-bottom: 1rem;
                }
                .chat-message.user {
                    background-color: #e6f7ff;
                }
                .chat-message.assistant {
                    background-color: #f9f9f9;
                }

                [data-testid="stToast"] {
                    position: fixed;
                    top: 4rem;
                    right: 1rem;
                    z-index: 9999;
                }
                [data-testid="stToast"] > div {
                    font-size: 0.875rem;
                    padding: 0.5rem 0.75rem;
                    min-width: fit-content;
                    max-width: 350px;
                    line-height: 1.3;
                    border-radius: 6px;
                }
            </style>
        """, unsafe_allow_html=True)

        st.markdown('<h1 class="main-header">📊 AI агент ЕЦС</h1>', unsafe_allow_html=True)
        st.markdown('<div class="subheader">Интеллектуальный помощник ЕЦС для анализа данных ВСП</div>',
                    unsafe_allow_html=True)
        st.markdown("---")

    @staticmethod
    def _init_session_state():
        """Инициализация состояния сессии"""
        defaults = {
            "messages": [],
            "chat_thread_id": uuid4(),
            "services_initialized": False,
            "initialization_error": None,
            "loading_complete": False
        }

        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value

    def _init_services(self):
        """Инициализация сервисов с проверкой состояния"""
        if st.session_state.services_initialized:
            return

        with st.spinner("Инициализация системы... Это может занять несколько секунд."):
            try:
                logger.info("Инициализация ServiceManager...")
                service_manager.initialize()

                self.db_service = service_manager.db_service

                self._initialize_database()
                loaded_files = self._load_reports_from_directory()
                new_solutions_loaded = self._load_new_solutions()
                client_flow_loaded = self._load_client_flow()

                st.session_state.services = {"db_service": self.db_service}

                st.session_state.services_initialized = True
                st.session_state.loading_complete = True

                if loaded_files:
                    st.toast(f"Система готова! Загружено {len(loaded_files)} отчетов.", icon="✅")
                else:
                    st.toast("Система готова к работе.\nОтчеты загружены.", icon="✅")

                if new_solutions_loaded:
                    st.toast("✅ Файл 'Новые решения' загружен.", icon="📄")
                if client_flow_loaded:
                    st.toast("✅ Файл 'Клиентский поток' загружен.", icon="📄")

            except Exception as e:
                error_msg = f"Ошибка инициализации: {str(e)}"
                logger.error(error_msg, exc_info=True)
                st.session_state.initialization_error = error_msg
                st.error(error_msg)

    def _initialize_database(self):
        """Инициализация базы данных с проверкой существующих таблиц"""
        inspector = inspect(self.db_service.engine)
        existing_tables = inspector.get_table_names()

        if 'area_report' not in existing_tables:
            with self.db_service.engine.begin() as connection:
                Base.metadata.create_all(connection)
                logger.info("Таблицы базы данных созданы")
        else:
            logger.info("Таблицы базы данных уже существуют")

    def _load_reports_from_directory(self) -> List[str]:
        """Загружает отчет из директории, если он еще не загружен"""
        report_filename = "Отчет по площади.xlsx"
        processor = VSPDataProcessor(self.db_service)
        loaded_files = []

        if "reports_loaded" in st.session_state and st.session_state.reports_loaded:
            return st.session_state.loaded_report_files

        reports_dir = Path(PROJECT_ROOT) / REPORTS_DIRECTORY
        reports_dir.mkdir(parents=True, exist_ok=True)

        with self.db_service.engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM vsp_core"))
            count = result.scalar()

            if count > 0:
                logger.info(f"В базе уже есть {count} записей, пропускаем загрузку")
                st.session_state.reports_loaded = True
                return []

        file_path = reports_dir / report_filename

        if not file_path.exists():
            st.warning(f"Файл {report_filename} не найден в директории {reports_dir}")
            logger.warning(f"Файл не найден: {file_path}")
            return []

        try:
            if processor.process(file_path):
                loaded_files.append(report_filename)
                logger.info(f"Файл {report_filename} успешно обработан")
            else:
                logger.warning(f"Файл {report_filename} не был обработан")
        except Exception as e:
            error_msg = f"Ошибка при обработке файла {report_filename}: {str(e)}"
            st.error(error_msg)
            logger.error(error_msg, exc_info=True)

        st.session_state.reports_loaded = True
        st.session_state.loaded_report_files = loaded_files

        return loaded_files

    def _load_new_solutions(self) -> bool:
        """Загружает файл с новыми решениями, если он еще не загружен"""
        if st.session_state.get("new_solutions_loaded"):
            return True

        processor = NewSolutionProcessor(self.db_service)
        reports_dir = Path(PROJECT_ROOT) / REPORTS_DIRECTORY
        filename = "Новые решения.xlsx"
        file_path = reports_dir / filename

        with self.db_service.engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM new_solution"))
            count = result.scalar()
            if count > 0:
                logger.info(f"В таблице new_solution уже есть {count} записей, пропускаем загрузку")
                st.session_state.new_solutions_loaded = True
                return True

        if not file_path.exists():
            logger.warning(f"Файл 'Новые решения' не найден: {file_path}")
            return False

        try:
            if processor.process(file_path):
                st.session_state.new_solutions_loaded = True
                logger.info(f"Файл '{filename}' успешно обработан")
                return True
            logger.warning(f"Файл '{filename}' не был обработан")
            return False
        except Exception as e:
            error_msg = f"Ошибка при обработке файла '{filename}': {str(e)}"
            st.error(error_msg)
            logger.error(error_msg, exc_info=True)
            return False

    def _load_client_flow(self) -> bool:
        """Загружает файл с клиентским потоком, если он еще не загружен"""
        if st.session_state.get("client_flow_loaded"):
            return True

        processor = ClientFlowProcessor(self.db_service)
        reports_dir = Path(PROJECT_ROOT) / REPORTS_DIRECTORY
        filename = "client_flow.xlsx"
        file_path = reports_dir / filename

        with self.db_service.engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM client_flow"))
            count = result.scalar()
            if count > 0:
                logger.info(f"В таблице client_flow уже есть {count} записей, пропускаем загрузку")
                st.session_state.client_flow_loaded = True
                return True

        if not file_path.exists():
            logger.warning(f"Файл 'Клиентский поток' не найден: {file_path}")
            return False

        try:
            if processor.process(file_path):
                st.session_state.client_flow_loaded = True
                logger.info(f"Файл '{filename}' успешно обработан")
                return True
            logger.warning(f"Файл '{filename}' не был обработан")
            return False
        except Exception as e:
            error_msg = f"Ошибка при обработке файла '{filename}': {str(e)}"
            st.error(error_msg)
            logger.error(error_msg, exc_info=True)
            return False

    def _render_chat(self):
        """Рендер чат-интерфейса"""
        st.subheader("💬 Чат с ассистентом")

        for msg in st.session_state.messages:
            role_class = "user" if msg["role"] == "user" else "assistant"
            with st.chat_message(role_class):
                st.markdown(msg["content"])

                if msg["role"] == "assistant" and "debug_info" in msg:
                    with st.expander("🔍 Детали выполнения", expanded=False):
                        st.json(msg["debug_info"])

        if prompt := st.chat_input("Введите ваш вопрос о площадях..."):
            self._handle_user_message(prompt)

    @staticmethod
    def _handle_user_message(prompt: str):
        """Обработка сообщения пользователя с отладочной информацией в плашке"""
        message_id = str(uuid4())
        user_message = {"role": "user", "content": prompt, "id": message_id}
        st.session_state.messages.append(user_message)

        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Анализирую запрос..."):
                try:
                    thread_id = st.session_state.chat_thread_id

                    result = start_agent(
                        user_query=prompt,
                        thread_id=thread_id
                    )

                    if "result" in result:
                        final_response = result["result"]
                    elif "error" in result:
                        final_response = f"Ошибка: {result['error']}"
                    else:
                        final_response = "Не удалось получить ответ от системы."

                    st.markdown(final_response)

                    with st.expander("🔍 Детали выполнения запроса", expanded=False):
                        if "final_state" in result and result["final_state"]:
                            debug_info = result["final_state"]
                            has_output = False

                            # Основная информация
                            col1, col2 = st.columns(2)
                            with col1:
                                if "user_query" in debug_info:
                                    st.markdown(f"**Запрос:** `{debug_info['user_query']}`")
                                    has_output = True
                                if "thread_id" in debug_info:
                                    st.markdown(f"**Thread ID:** `{debug_info['thread_id']}`")
                                    has_output = True
                            with col2:
                                if "current_agent" in debug_info:
                                    st.markdown(f"**Текущий агент:** `{debug_info.get('current_agent', 'N/A')}`")
                                    has_output = True

                            st.divider()

                            if "execution_timeline" in debug_info and debug_info["execution_timeline"]:
                                st.markdown("**Цепочка шагов плана**")
                                st.json(debug_info["execution_timeline"])
                                has_output = True

                            if "plan_summary" in debug_info and debug_info["plan_summary"]:
                                st.markdown("**Краткая стратегия (plan_summary)**")
                                st.code(str(debug_info["plan_summary"]), language="text")
                                has_output = True

                            if "step_results" in debug_info and debug_info["step_results"]:
                                st.markdown("**Результаты по шагам (step_results)**")
                                st.json(debug_info["step_results"])
                                has_output = True

                            # Результаты
                            if "result" in debug_info and debug_info["result"]:
                                st.markdown("**📊 SQL Результат:**")
                                st.code(debug_info["result"], language="text")
                                has_output = True

                            if "final_result" in debug_info and debug_info["final_result"]:
                                st.markdown("**💬 Финальный ответ:**")
                                st.code(debug_info["final_result"], language="text")
                                has_output = True

                            # Сообщения
                            if "messages" in debug_info and debug_info["messages"]:
                                st.markdown(
                                    f"**📨 Сообщения:** ({debug_info.get('total_messages', len(debug_info['messages']))} всего, показаны последние {len(debug_info['messages'])})")
                                for i, msg in enumerate(debug_info["messages"]):
                                    msg_type = msg.get('type', 'Unknown')
                                    msg_content = msg.get('content', '')

                                    st.markdown(f"**{i + 1}. {msg_type}**")

                                    # Контент
                                    if msg_content:
                                        st.code(msg_content, language="text")
                                        has_output = True

                                    # Tool calls для AIMessage
                                    if 'tool_calls' in msg and msg['tool_calls']:
                                        st.markdown("*Tool calls:*")
                                        for tc in msg['tool_calls']:
                                            st.markdown(f"- `{tc.get('name')}`: {tc.get('args', '')}")
                                        has_output = True

                                    # Дополнительная информация для ToolMessage
                                    if msg_type == 'ToolMessage':
                                        if 'name' in msg:
                                            st.markdown(f"*Tool:* `{msg['name']}`")
                                            has_output = True

                                    if i < len(debug_info["messages"]) - 1:
                                        st.markdown("---")

                            # Ошибки
                            if "error" in debug_info and debug_info["error"]:
                                st.error(f"**Ошибка:** {debug_info['error']}")
                                has_output = True

                            # Промежуточные результаты
                            if "intermediate_results" in debug_info and debug_info["intermediate_results"]:
                                st.markdown("**🔧 Промежуточные результаты:**")
                                for key, value in debug_info["intermediate_results"].items():
                                    st.markdown(f"- **{key}:** `{value}`")
                                has_output = True

                            # Fallback: если ничего не вывели — показываем сырой JSON
                            if not has_output:
                                st.markdown("Детали недоступны в структурированном виде, показываю сырой JSON:")
                                st.json(debug_info)
                        else:
                            st.write("Отладочная информация недоступна")

                    assistant_message = {
                        "role": "assistant",
                        "content": final_response,
                        "id": message_id,
                        "debug_info": result.get("final_state", {}),
                        "metadata": {
                            "thread_id": thread_id,
                            "result_keys": list(result.keys()) if isinstance(result, dict) else []
                        }
                    }
                    st.session_state.messages.append(assistant_message)

                except Exception as e:
                    error_msg = f"Ошибка обработки запроса: {str(e)}"
                    logger.error(error_msg, exc_info=True)

                    st.error(error_msg)

                    with st.expander("Детали ошибки", expanded=False):
                        st.write("### Информация об ошибке")
                        st.write("**Тип ошибки:**")
                        st.code(f"{type(e).__name__}")
                        st.write("**Сообщение ошибки:**")
                        st.code(f"{str(e)}")
                        st.write("**Полный traceback:**")
                        st.exception(e)

                    error_message = {
                        "role": "assistant",
                        "content": error_msg,
                        "id": message_id,
                        "error": True,
                        "metadata": {
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                            "thread_id": thread_id if 'thread_id' in locals() else "unknown"
                        }
                    }
                    st.session_state.messages.append(error_message)

    def run(self):
        """Основной цикл приложения"""
        try:
            if not st.session_state.services_initialized:
                self._init_services()
                return

            if st.session_state.loading_complete:
                self._render_chat()

        except Exception as e:
            logger.error(f"Критическая ошибка: {str(e)}", exc_info=True)
            st.error("Произошла критическая ошибка. Пожалуйста, перезагрузите страницу.")

            if st.button("Перезагрузить приложение"):
                st.session_state.clear()
                st.rerun()


if __name__ == "__main__":
    app = AreaAssistantApp()
    app.run()
