"""Clima atual e previsao do dia via Open-Meteo (gratuito, sem chave de API)."""
import httpx
from database import salvar_cache, ler_cache

BASE = "https://api.open-meteo.com/v1/forecast"

# Traducao dos codigos WMO do Open-Meteo para texto em portugues.
WMO = {
    0: "ceu limpo", 1: "predominantemente limpo", 2: "parcialmente nublado", 3: "nublado",
    45: "neblina", 48: "neblina com geada", 51: "garoa leve", 53: "garoa", 55: "garoa forte",
    61: "chuva fraca", 63: "chuva", 65: "chuva forte", 66: "chuva congelante",
    71: "neve fraca", 73: "neve", 75: "neve forte", 80: "pancadas de chuva",
    81: "pancadas de chuva", 82: "pancadas fortes", 95: "tempestade",
    96: "tempestade com granizo", 99: "tempestade forte com granizo",
}


async def get_clima(lat, lon):
    """Retorna um dicionario com o clima atual e maxima/minima do dia.

    Tenta a rede; se falhar (sem sinal), usa o ultimo valor em cache para a regiao.
    """
    chave_cache = f"clima:{round(lat, 1)},{round(lon, 1)}"
    params = {
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "auto", "forecast_days": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(BASE, params=params)
            r.raise_for_status()
            data = r.json()
        cur = data["current"]
        daily = data["daily"]
        resultado = {
            "temperatura": cur["temperature_2m"],
            "descricao": WMO.get(cur["weather_code"], "condicao desconhecida"),
            "vento": cur["wind_speed_10m"],
            "umidade": cur["relative_humidity_2m"],
            "max": daily["temperature_2m_max"][0],
            "min": daily["temperature_2m_min"][0],
            "chance_chuva": daily["precipitation_probability_max"][0],
        }
        salvar_cache(chave_cache, resultado)
        return resultado
    except Exception:
        # Sem sinal: tenta o cache (validade longa, 12h, porque o clima muda devagar)
        cache = ler_cache(chave_cache, validade_segundos=43200)
        if cache:
            cache["_offline"] = True
        return cache
