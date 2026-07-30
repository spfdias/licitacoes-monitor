import httpx


async def send_text(base_url: str, api_key: str, instance: str, number: str, text: str) -> None:
    url = f"{base_url.rstrip('/')}/message/sendText/{instance}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            url,
            headers={"apikey": api_key, "Content-Type": "application/json"},
            json={"number": number, "text": text},
        )
        resp.raise_for_status()
