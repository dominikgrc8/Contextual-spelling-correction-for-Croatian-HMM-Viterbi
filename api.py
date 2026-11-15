"""Client for the Ispravi.me n-gram frequency API."""
from functools import lru_cache

import requests

API_TIMEOUT = 5  # seconds


@lru_cache(maxsize=100_000)
def _fetch_ngram_data_cached(ngram):
    # Raises on any failure; lru_cache does not store exceptions, so only successful responses are cached.
    url = "https://ispravi.me/api/ngram"
    response = requests.post(url, data={"ngram": ngram}, timeout=API_TIMEOUT)
    response.raise_for_status()
    return response.json()


def fetch_ngram_data(ngram):
    try:
        return _fetch_ngram_data_cached(ngram)
    except requests.exceptions.HTTPError as e:
        return {"error": f"Server vratio status {e.response.status_code}", "details": e.response.text}
    except ValueError:
        return {"error": "Odgovor nije validan JSON"}
    except requests.exceptions.RequestException as e:
        return {"error": "Greška u zahtevu", "details": str(e)} #timeout, connection error...
