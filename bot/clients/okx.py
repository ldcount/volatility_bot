import requests


OKX_FUNDING_URL = "https://www.okx.com/api/v5/public/funding-rate"


def bybit_to_okx_inst_id(bybit_symbol: str) -> str:
    for quote in ("USDC", "USDT"):
        if bybit_symbol.endswith(quote):
            base = bybit_symbol[: -len(quote)]
            return f"{base}-{quote}-SWAP"
    return f"{bybit_symbol}-USDT-SWAP"


def fetch_funding_rate(bybit_symbol: str) -> float | None:
    inst_id = bybit_to_okx_inst_id(bybit_symbol)
    try:
        response = requests.get(
            OKX_FUNDING_URL,
            params={"instId": inst_id},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        print(f"[OKX] Error fetching funding rate for {inst_id}: {exc}")
        return None

    if payload.get("code") != "0" or not payload.get("data"):
        return None

    rate = payload["data"][0].get("fundingRate")
    return float(rate) if rate else None
