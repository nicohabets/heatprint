"""Bridge to the mindergas.nl meter reading API (optional, token in options).

The token is passed in the ``AUTH-TOKEN`` header and is never logged.
"""

from __future__ import annotations

import logging
from datetime import date

from aiohttp import ClientError, ClientSession, ClientTimeout
from homeassistant.exceptions import HomeAssistantError

from .const import MINDERGAS_API_URL, MINDERGAS_AUTH_HEADER

_LOGGER = logging.getLogger(__name__)
_TIMEOUT = ClientTimeout(total=30)


class MindergasError(HomeAssistantError):
    """Raised when mindergas.nl rejects or fails a push."""


async def async_push_reading(
    session: ClientSession, token: str, reading_date: date, reading: float
) -> int:
    """Post one meter reading to mindergas.nl and return the HTTP status."""
    payload = {"date": reading_date.isoformat(), "reading": f"{reading:.3f}"}
    headers = {MINDERGAS_AUTH_HEADER: token, "Content-Type": "application/json"}
    try:
        async with session.post(
            MINDERGAS_API_URL, json=payload, headers=headers, timeout=_TIMEOUT
        ) as response:
            status = response.status
            if status in (200, 201):
                _LOGGER.debug("Pushed reading for %s to mindergas.nl", reading_date)
                return status
            if status == 401:
                raise MindergasError("mindergas.nl rejected the API token")
            if status == 422:
                raise MindergasError(
                    f"mindergas.nl rejected the reading for {reading_date} (already present or invalid)"
                )
            raise MindergasError(f"mindergas.nl returned HTTP {status}")
    except (ClientError, TimeoutError) as err:
        raise MindergasError(f"Could not reach mindergas.nl: {err}") from err
