import json
import time
import sys
import uuid
import httpx

class QwenChatAPI:
    def __init__(self, cookies_file="cookies.txt", base_url="https://chat.qwen.ai"):
        self.base_url = base_url
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0",
            "Accept": "application/json",
            "Accept-Language": "ru-RU,ru;q=0.9",
            "Content-Type": "application/json",
            "Version": "0.2.63",
            "source": "web",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
        
        # Парсим куки при инициализации класса
        cookie_string, auth_token = self._parse_netscape_cookies(cookies_file)
        
        if auth_token:
            self.headers["Authorization"] = f"Bearer {auth_token}"
        if cookie_string:
            self.headers["Cookie"] = cookie_string
            
        # Создаем сессию httpx
        self.client = httpx.Client(headers=self.headers, verify=False, timeout=60.0)

    def _parse_netscape_cookies(self, file_path):
        """Внутренний метод для парсинга cookies.txt"""
        cookies_dict = {}
        auth_token = None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("#") or not line.strip():
                        continue
                    parts = line.strip().split("\t")
                    if len(parts) >= 7:
                        name = parts[5]
                        value = parts[6]
                        cookies_dict[name] = value
                        if name == "token" and value and value != '""' and value.startswith("eyJ"):
                            auth_token = value
        except FileNotFoundError:
            print(f"[Ошибка] Файл куки '{file_path}' не найден!")
            sys.exit(1)
            
        cookie_string = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()])
        return cookie_string, auth_token

    def create_chat(self):
        """Создает новый чат и возвращает его ID"""
        url = f"{self.base_url}/api/v2/chats/new"
        payload = {
            "title": "Новый чат",
            "models": ["qwen3.7-plus"],
            "chat_mode": "normal",
            "chat_type": "t2t",
            "timestamp": int(time.time() * 1000),
            "project_id": ""
        }
        try:
            response = self.client.post(url, json=payload)
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    return data["data"]["id"]
            return None
        except Exception:
            return None

    def ask(self, chat_id, text_message, stream=True):
        """
        Отправляет сообщение в чат.
        Если stream=True, то возвращает генератор (yield) для построчного вывода.
        Если stream=False, то возвращает сразу весь текст одной строкой.
        """
        url = f"{self.base_url}/api/v2/chat/completions"
        params = {"chat_id": chat_id}
        
        msg_fid = str(uuid.uuid4())
        current_ts = int(time.time())
        
        payload = {
            "stream": True,
            "version": "2.1",
            "incremental_output": True,
            "chat_id": chat_id,
            "chat_mode": "normal",
            "model": "qwen3.7-plus",
            "parent_id": None,
            "messages": [
                {
                    "fid": msg_fid,
                    "parentId": None,
                    "childrenIds": [],
                    "role": "user",
                    "content": text_message,
                    "user_action": "chat",
                    "files": [],
                    "timestamp": current_ts,
                    "models": ["qwen3.7-plus"],
                    "chat_type": "t2t",
                    "feature_config": {
                        "thinking_enabled": False,
                        "output_schema": "phase",
                        "research_mode": "normal",
                        "auto_thinking": False,
                        "thinking_mode": "Never",
                        "thinking_format": "summary",
                        "auto_search": True
                    },
                    "extra": {"meta": {"subChatType": "t2t"}},
                    "sub_chat_type": "t2t"
                }
            ],
            "timestamp": current_ts
        }
        
        self.client.headers["X-Request-Id"] = str(uuid.uuid4())
        
        if stream:
            # Возвращаем генератор для стриминга по словам
            def generator():
                try:
                    with self.client.stream("POST", url, params=params, json=payload) as response:
                        if response.status_code == 200:
                            for line in response.iter_lines():
                                if line.startswith("data:"):
                                    json_str = line[5:].strip()
                                    if json_str == "[DONE]":
                                        break
                                    try:
                                        data_json = json.loads(json_str)
                                        choices = data_json.get("choices", [])
                                        if choices:
                                            content = choices[0].get("delta", {}).get("content", "")
                                            if content:
                                                yield content
                                    except json.JSONDecodeError:
                                        continue
                except Exception as e:
                    yield f"\n[Ошибка стриминга: {e}]"
            return generator()
        else:
            # Обычный запрос, собираем всё в одну строку и возвращаем результат
            full_text = ""
            try:
                with self.client.stream("POST", url, params=params, json=payload) as response:
                    if response.status_code == 200:
                        for line in response.iter_lines():
                            if line.startswith("data:"):
                                json_str = line[5:].strip()
                                if json_str == "[DONE]":
                                    break
                                try:
                                    data_json = json.loads(json_str)
                                    choices = data_json.get("choices", [])
                                    if choices:
                                        content = choices[0].get("delta", {}).get("content", "")
                                        if content:
                                            full_text += content
                                except json.JSONDecodeError:
                                    continue
                return full_text
            except Exception as e:
                return f"[Ошибка запроса: {e}]"

    def close(self):
        """Закрывает HTTP-сессию"""
        self.client.close()