"""Geocodificacao usando o Nominatim (OpenStreetMap), gratuito e sem chave.

IMPORTANTE: a politica de uso do Nominatim exige um User-Agent identificavel
e no maximo 1 requisicao por segundo. Respeite isso para nao ser bloqueado.
"""
import asyncio
import httpx
from config import USER_AGENT

BASE = "https://nominatim.openstreetmap.org"
_HEADERS = {"User-Agent": USER_AGENT}


async def reverse_geocode(lat, lon):
    """Coordenada -> nome legivel do lugar (cidade, estado)."""
    params = {"lat": lat, "lon": lon, "format": "json", "zoom": 12, "accept-language": "pt-BR"}
    async with httpx.AsyncClient(timeout=15, headers=_HEADERS) as client:
        r = await client.get(f"{BASE}/reverse", params=params)
        r.raise_for_status()
        data = r.json()
    addr = data.get("address", {})
    cidade = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("county")
    estado = addr.get("state")
    pais = addr.get("country")
    partes = [p for p in (cidade, estado, pais) if p]
    return ", ".join(partes) if partes else data.get("display_name", "local desconhecido")


async def forward_geocode(nome):
    """Nome do lugar -> (lat, lon). Usado para preencher coordenadas que faltam na planilha."""
    params = {"q": nome, "format": "json", "limit": 1}
    async with httpx.AsyncClient(timeout=15, headers=_HEADERS) as client:
        r = await client.get(f"{BASE}/search", params=params)
        r.raise_for_status()
        data = r.json()
    await asyncio.sleep(1)  # respeita o limite de 1 req/seg
    if not data:
        return None, None
    return float(data[0]["lat"]), float(data[0]["lon"])
