import pandas as pd
from typing import Optional

from httpx import AsyncClient
from async_lru import alru_cache

BASE_URL = "https://pokeapi.co/api/v2"


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


_PARQUET_PATH = "resources/pokemon.parquet"
_cached_df = None


def load_pokemon_dataset() -> pd.DataFrame:
    global _cached_df
    if _cached_df is None:
        _cached_df = pd.read_parquet(_PARQUET_PATH, dtype_backend="pyarrow")
    return _cached_df
