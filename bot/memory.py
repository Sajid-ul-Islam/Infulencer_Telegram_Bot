from collections import defaultdict

chat_histories: dict[int, list[dict]] = defaultdict(list)
MAX_HISTORY = 10

def add_to_history(user_id: int, role: str, content: str):
    chat_histories[user_id].append({"role": role, "content": content})
    if len(chat_histories[user_id]) > MAX_HISTORY:
        chat_histories[user_id] = chat_histories[user_id][-MAX_HISTORY:]

def get_history(user_id: int, max_exchanges: int = 3) -> list[dict]:
    history = chat_histories.get(user_id, [])
    return history[-(max_exchanges * 2):]

def clear_history(user_id: int):
    if user_id in chat_histories:
        del chat_histories[user_id]

def get_history_count(user_id: int) -> int:
    return len(chat_histories.get(user_id, [])) // 2
