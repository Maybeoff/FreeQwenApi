import httpx

def get_available_models():
    """
    Делает тупой реквест и отдает чистый, сырой JSON с сервера без редактирования.
    """
    url = "https://chat.qwen.ai/api/v2/models/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0"
    }
    try:
        response = httpx.get(url, headers=headers, verify=False, timeout=15.0)
        return response.json()
    except Exception as e:
        return {"error": str(e)}