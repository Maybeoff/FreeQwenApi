import json
import time
import uuid
import httpx

class QwenImageAPI:
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
        
        cookie_string, auth_token = self._parse_netscape_cookies(cookies_file)
        if auth_token:
            self.headers["Authorization"] = f"Bearer {auth_token}"
        if cookie_string:
            self.headers["Cookie"] = cookie_string
            
        self.client = httpx.Client(headers=self.headers, verify=False, timeout=60.0)

    def _parse_netscape_cookies(self, file_path):
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
            raise FileNotFoundError(f"Файл куки '{file_path}' не найден!")
            
        cookie_string = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()])
        return cookie_string, auth_token

    def generate_image(self, chat_id, prompt, model="qwen3.7-plus", aspect_ratio="16:9"):
        """
        Отправляет запрос на генерацию картинки.
        Ждет завершения потока и возвращает прямой URL на изображение.
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
            "model": model,
            "parent_id": None,
            "messages": [
                {
                    "fid": msg_fid,
                    "parentId": None,
                    "childrenIds": [str(uuid.uuid4())],
                    "role": "user",
                    "content": prompt,
                    "user_action": "chat",
                    "files": [],
                    "timestamp": current_ts,
                    "models": [model],
                    "chat_type": "t2i", # Text to Image
                    "feature_config": {
                        "thinking_enabled": False,
                        "output_schema": "phase",
                        "research_mode": "normal",
                        "auto_thinking": False,
                        "thinking_mode": "Fast",
                        "auto_search": True
                    },
                    "extra": {
                        "meta": {
                            "subChatType": "t2i",
                            "size": aspect_ratio
                        }
                    },
                    "sub_chat_type": "t2i"
                }
            ],
            "timestamp": current_ts + 1,
            "size": aspect_ratio
        }
        
        self.client.headers["X-Request-Id"] = str(uuid.uuid4())
        image_url = None
        
        try:
            with self.client.stream("POST", url, params=params, json=payload) as response:
                if response.status_code != 200:
                    print(f"[Ошибка HTTP {response.status_code}]")
                    return None
                    
                for line in response.iter_lines():
                    if line.startswith("data:"):
                        json_str = line[5:].strip()
                        try:
                            data_json = json.loads(json_str)
                            choices = data_json.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                content = delta.get("content", "")
                                # Проверяем, что в контенте прилетела ссылка на картинку
                                if content.startswith("http://") or content.startswith("https://"):
                                    image_url = content
                        except json.JSONDecodeError:
                            pass
            return image_url
        except Exception as e:
            print(f"[Ошибка при генерации]: {e}")
            return None

    def close(self):
        self.client.close()
