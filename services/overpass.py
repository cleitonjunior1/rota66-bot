"""Busca postos de gasolina e pontos de interesse via Overpass API (OpenStreetMap).

Gratuito e sem chave. A Overpass tem limites de uso justo, entao guardamos os
resultados em cache para reduzir requisicoes e funcionar offline depois.
"""
import httpx
from database import salvar_cache, ler_cache

ENDPOINT = "https://overpass-api.de/api/interpreter"


async def _consultar(query):
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(ENDPOINT, data={"data": query})
        r.raise_for_status()
        return r.json()


def _extrair(elementos, limite=8):
    """Converte elementos do OSM numa lista limpa de nome + coordenada."""
    saida = []
    for el in elementos:
        tags = el.get("tags", {})
        nome = tags.get("name") or tags.get("brand")
        if not nome:
            continue
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue
        saida.append({"nome": nome, "lat": lat, "lon": lon})
        if len(saida) >= limite:
            break
    return saida


async def get_postos(lat, lon, raio):
    chave = f"postos:{round(lat,2)},{round(lon,2)}:{raio}"
    query = f"""
        [out:json][timeout:25];
        node[amenity=fuel](around:{raio},{lat},{lon});
        out center;
    """
    try:
        data = await _consultar(query)
        resultado = _extrair(data.get("elements", []))
        salvar_cache(chave, resultado)
        return resultado
    except Exception:
        return ler_cache(chave) or []


async def get_atracoes(lat, lon, raio):
    chave = f"atracoes:{round(lat,2)},{round(lon,2)}:{raio}"
    # tourism = atracoes turisticas; historic = pontos historicos (otimo p/ Rota 66)
    query = f"""
        [out:json][timeout:25];
        (
          nwr[tourism~"attraction|museum|viewpoint|artwork"](around:{raio},{lat},{lon});
          nwr[historic](around:{raio},{lat},{lon});
        );
        out center;
    """
    try:
        data = await _consultar(query)
        resultado = _extrair(data.get("elements", []))
        salvar_cache(chave, resultado)
        return resultado
    except Exception:
        return ler_cache(chave) or []
