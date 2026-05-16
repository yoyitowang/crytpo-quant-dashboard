"""Aden / AsterDEX authenticated API helper (EIP-712 signing).
Requires credentials from https://www.aden.io/en/api-wallet (Pro API).
Set in .env: ADEN_API_USER, ADEN_API_SIGNER, ADEN_API_PRIVATE_KEY
"""
import time
import urllib.parse
import structlog
from datetime import datetime, timezone
from typing import Optional

logger = structlog.get_logger()

# Lazy imports (only when auth is configured)
_eth_account = None
_has_auth = False
_api_user = ""
_api_signer = ""
_api_private_key = ""

TYPED_DATA = {
    "types": {
        "EIP712Domain": [
            {"name": "name", "type": "string"},
            {"name": "version", "type": "string"},
            {"name": "chainId", "type": "uint256"},
            {"name": "verifyingContract", "type": "address"},
        ],
        "Message": [{"name": "msg", "type": "string"}],
    },
    "primaryType": "Message",
    "domain": {
        "name": "AsterSignTransaction",
        "version": "1",
        "chainId": 1666,
        "verifyingContract": "0x0000000000000000000000000000000000000000",
    },
    "message": {"msg": ""},
}


def init(user: str, signer: str, private_key: str):
    global _has_auth, _api_user, _api_signer, _api_private_key, _eth_account
    try:
        from eth_account import Account
        from eth_account.messages import encode_structured_data
        _eth_account = (Account, encode_structured_data)
        _api_user = user
        _api_signer = signer
        _api_private_key = private_key
        _has_auth = True
        logger.info("Aden API auth initialized")
    except ImportError:
        logger.warning("eth_account not installed, Aden auth unavailable")


def _get_nonce() -> str:
    """Nonce: current unix timestamp in microseconds."""
    return str(int(time.time() * 1_000_000))


def _sign(params: dict) -> str:
    """Sign request params with EIP-712."""
    Account, encode_structured_data = _eth_account
    msg_str = urllib.parse.urlencode(params)
    td = dict(TYPED_DATA)
    td["message"]["msg"] = msg_str
    message = encode_structured_data(td)
    signed = Account.sign_message(message, private_key=_api_private_key)
    return signed.signature.hex()


def build_auth_url(base_url: str, extra_params: Optional[dict] = None) -> str:
    """Build an authenticated URL with EIP-712 signature.
    
    Args:
        base_url: The endpoint URL (without query string)
        extra_params: Additional query parameters (e.g. symbol, limit)
    
    Returns:
        Full URL with auth parameters and signature
    """
    if not _has_auth:
        raise RuntimeError("Aden API auth not configured")

    params = dict(extra_params or {})
    params["user"] = _api_user
    params["signer"] = _api_signer
    params["nonce"] = _get_nonce()
    signature = _sign(params)
    qs = urllib.parse.urlencode(params)
    return f"{base_url}?{qs}&signature={signature}"


async def fetch_funding_rate_history(symbol: str, limit: int = 500) -> list:
    """Fetch Aden funding rate history using authenticated API.
    Returns list of {timestamp, rate} dicts, or empty list on failure.
    """
    if not _has_auth:
        logger.warning("Aden auth not configured")
        return []

    import aiohttp
    base = "https://api.aden.io/api/v1/dex_futures/usdt/funding_rate_history"
    try:
        url = build_auth_url(base, {"symbol": symbol, "limit": str(limit)})
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if isinstance(data, list) and data:
                        return [{
                            "timestamp": datetime.fromtimestamp(d["fundingTime"] / 1000, tz=timezone.utc).isoformat(),
                            "rate": float(d["fundingRate"]),
                        } for d in data if d.get("fundingRate") is not None]
                else:
                    body = await resp.text()
                    logger.error("aden history api error", status=resp.status, body=body[:200])
    except Exception as e:
        logger.error("aden history fetch failed", error=str(e)[:200])
    return []
