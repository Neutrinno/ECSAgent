import json
from datetime import datetime
from typing import List, Dict, Any
from langchain_core.messages import BaseMessage
import os


def log_agent_messages(messages: List[BaseMessage], thread_id: str, agent_type: str = "decision_agent"):
    """
    Логирует все сообщения агента в отдельный файл с улучшенным форматированием
    """
    log_dir = "logs/agent_debug"
    os.makedirs(log_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{log_dir}/{agent_type}_{thread_id}_{timestamp}.json"

    log_data = {
        "timestamp": datetime.now().isoformat(),
        "thread_id": thread_id,
        "agent_type": agent_type,
        "messages": []
    }

    for i, msg in enumerate(messages):
        message_data = {
            "index": i,
            "type": type(msg).__name__,
            "content": _format_content(msg.content) if hasattr(msg, 'content') and msg.content else None,
            "tool_calls": _format_tool_calls(msg.tool_calls) if hasattr(msg, 'tool_calls') and msg.tool_calls else None,
            "tool_call_id": getattr(msg, 'tool_call_id', None),
            "name": getattr(msg, 'name', None),
            "additional_kwargs": getattr(msg, 'additional_kwargs', None)
        }
        log_data["messages"].append(message_data)

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)

    return filename


def _format_content(content: Any) -> str:
    """Форматирует содержание сообщения для лучшей читаемости"""
    if isinstance(content, str):
        if len(content) > 120:
            formatted = content.replace('. ', '.\n')
            formatted = formatted.replace(', ', ',\n')
            return formatted
        return content
    elif isinstance(content, list):
        return json.dumps(content, ensure_ascii=False, indent=2)
    elif isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False, indent=2)
    return str(content)


def _format_tool_calls(tool_calls: List[Dict]) -> List[Dict]:
    """Форматирует вызовы инструментов для лучшей читаемости"""
    formatted_calls = []
    for call in tool_calls:
        formatted_call = {
            "name": call.get("name"),
            "args": call.get("args", {}),
            "id": call.get("id")
        }
        formatted_calls.append(formatted_call)
    return formatted_calls


def print_agent_messages(messages: List[BaseMessage]):
    """
    Выводит сообщения агента в консоль в читаемом формате
    """
    print("\n" + "=" * 80)
    print("🔍 ДЕБАГ - ПОЛНАЯ ЦЕПОЧКА СООБЩЕНИЙ:")
    print("=" * 80)

    for i, msg in enumerate(messages):
        print(f"\n{'=' * 40}")
        print(f"📝 [{i}] {type(msg).__name__}:")
        print(f"{'=' * 40}")

        if hasattr(msg, 'content') and msg.content:
            print("💬 Content:")
            print(_format_content_for_console(msg.content))
            print()

        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            print("🛠️  Tool calls:")
            for j, call in enumerate(msg.tool_calls):
                print(f"   {j + 1}. {call.get('name', 'Unknown')}")
                if call.get('args'):
                    print("      Args:")
                    for key, value in call.get('args', {}).items():
                        print(f"        {key}: {value}")
                if call.get('id'):
                    print(f"      ID: {call.get('id')}")
            print()

        if hasattr(msg, 'tool_call_id') and msg.tool_call_id:
            print(f"🔧 Tool call ID: {msg.tool_call_id}")

        if hasattr(msg, 'name') and msg.name:
            print(f"🏷️  Name: {msg.name}")

        if hasattr(msg, 'additional_kwargs') and msg.additional_kwargs:
            print("⚙️  Additional kwargs:")
            for key, value in msg.additional_kwargs.items():
                print(f"   {key}: {value}")

    print("=" * 80 + "\n")


def _format_content_for_console(content: Any) -> str:
    """Форматирует содержание для консольного вывода"""
    if isinstance(content, str):
        # Разбиваем на строки для лучшей читаемости
        lines = []
        current_line = ""

        for word in content.split():
            if len(current_line) + len(word) + 1 > 80:
                lines.append(current_line)
                current_line = word
            else:
                if current_line:
                    current_line += " " + word
                else:
                    current_line = word

        if current_line:
            lines.append(current_line)

        return "\n".join(lines)

    elif isinstance(content, (dict, list)):
        return json.dumps(content, ensure_ascii=False, indent=2)

    return str(content)


def log_tool_calls(messages: List[BaseMessage], thread_id: str):
    """
    Логирует только вызовы инструментов и их результаты
    """
    tool_calls_log = []

    for i, msg in enumerate(messages):
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            for call in msg.tool_calls:
                tool_calls_log.append({
                    "message_index": i,
                    "type": "TOOL_CALL",
                    "tool_name": call.get("name"),
                    "arguments": call.get("args", {}),
                    "call_id": call.get("id")
                })

        if hasattr(msg, 'tool_call_id') and msg.tool_call_id:
            tool_calls_log.append({
                "message_index": i,
                "type": "TOOL_RESULT",
                "tool_call_id": msg.tool_call_id,
                "content": _format_content(msg.content) if hasattr(msg, 'content') else None
            })

    if tool_calls_log:
        log_dir = "logs/tool_calls"
        os.makedirs(log_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{log_dir}/tool_calls_{thread_id}_{timestamp}.json"

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(tool_calls_log, f, ensure_ascii=False, indent=2)

        return filename
    return None
