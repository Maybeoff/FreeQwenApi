import json
import time
import uuid
import httpx

class QwenVideoAPI:
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

    def _check_task_status(self, task_id):
        """Внутренний метод для проверки готовности видео по его task_id"""
        url = f"{self.base_url}/api/v1/tasks/status/{task_id}"
        try:
            response = self.client.get(url)
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    task_data = data.get("data", {})
                    status = task_data.get("status") # например: "RUNNING", "SUCCESS", "FAILED"
                    
                    if status == "SUCCESS":
                        # Вытаскиваем финальную ссылку на видео
                        video_url = task_data.get("result", {}).get("video_url")
                        return "SUCCESS", video_url
                    elif status == "FAILED":
                        return "FAILED", None
                        
                    return "RUNNING", None
            return "ERROR", None
        except Exception:
            return "ERROR", None

    def generate_video(self, chat_id, prompt, model="qwen3.7-plus", check_interval=5, timeout=300):
        """
        Запускает генерацию видео и ждет его создания, опрашивая сервер.
        """
        url = f"{self.base_url}/api/v2/chat/completions"
        params = {"chat_id": chat_id}
        
        msg_fid = str(uuid.uuid4())
        current_ts = int(time.time())
        
        # Payload, собранный на базе твоих новых логов для t2v
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
                    "chat_type": "t2v",  # Text to Video
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
                            "subChatType": "t2v"
                        }
                    },
                    "sub_chat_type": "t2v"
                }
            ],
            "timestamp": current_ts + 1
        }
        
        self.client.headers["X-Request-Id"] = str(uuid.uuid4())
        task_id = None

        # Шаг 1: Отправляем запрос на создание задачи видео
        try:
            with self.client.stream("POST", url, params=params, json=payload) as response:
                if response.status_code != 200:
                    return None
                    
                for line in response.iter_lines():
                    if line.startswith("data:"):
                        json_str = line[5:].strip()
                        try:
                            data_json = json.loads(json_str)
                            # Ищем task_id в прилетающем SSE потоке
                            choices = data_json.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                extra = delta.get("extra", {})
                                if "task_id" in extra:
                                    task_id = extra["task_id"]
                                    break
                        except json.JSONDecodeError:
                            pass
        except Exception as e:
            print(f"[Ошибка отправки задачи]: {e}")
            return None

        if not task_id:
            print("[Ошибка] Не удалось получить task_id для генерации видео.")
            return None

        print(f"[Задача создана] ID: {task_id}. Начинаем опрос сервера...")

        # Шаг 2: Поллинг статуса задачи до победного конца
        start_time = time.time()
        while time.time() - start_time < timeout:
            status, video_url = self._check_task_status(task_id)
            
            if status == "SUCCESS":
                return video_url
            elif status == "FAILED":
                print("[Ошибка] Сервер вернул статус FAILED при генерации видео.")
                return None
            elif status == "ERROR":
                print("[Предупреждение] Ошибка при проверке статуса, пробуем снова...")
                
            # Если статус RUNNING, то просто ждем интервал и проверяем заново
            time.sleep(check_interval)
            
        print("[Ошибка] Превышено время ожидания генерации видео (таймаут).")
        return None

    def close(self):
        self.client.close()