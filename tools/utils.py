import asyncio
import json
from dataclasses import dataclass
from typing import Any, List, Optional, Set, Union, Dict

from httpx import AsyncClient

from pydantic import BaseModel, ValidationError, Field, ConfigDict

from pydantic_ai import Agent, ModelRetry, RunContext
from async_lru import alru_cache

BASE_URL = "https://pokeapi.co/api/v2"


def pretty_print(data: dict):
    """Pretty print a dictionary with optional title."""
    print(json.dumps(data, indent=2, ensure_ascii=False))


@alru_cache(maxsize=512)
async def _fetch_url(client: AsyncClient, url: str) -> Optional[dict]:
    """Safely fetches a single URL, returning JSON or None on error."""
    try:
        response = await client.get(url, timeout=10)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    except Exception:
        return None
