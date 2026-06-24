"""Logica da rota: distancia entre coordenadas e qual e a proxima parada planejada."""
import math
from database import listar_waypoints


def haversine(lat1, lon1, lat2, lon2):
    """Distancia em metros entre dois pontos na superficie da Terra."""
    R = 6371000  # raio da Terra em metros
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def proxima_parada(lat, lon):
    """Retorna o proximo waypoint ainda nao visitado, em ordem de rota,
    junto com a distancia atual ate ele. None se a rota acabou."""
    wps = [w for w in listar_waypoints() if not w["visitado"] and w["lat"] and w["lon"]]
    if not wps:
        return None
    proximo = wps[0]  # ja vem ordenado por 'ordem'
    dist = haversine(lat, lon, proximo["lat"], proximo["lon"])
    return {"waypoint": proximo, "distancia_m": dist}


def pontos_proximos(lat, lon, raio_m):
    """Waypoints planejados (lugares que voces marcaram) dentro do raio dado.
    Usado para o alerta 'voces estao chegando perto de X'."""
    perto = []
    for w in listar_waypoints():
        if not w["lat"] or not w["lon"]:
            continue
        d = haversine(lat, lon, w["lat"], w["lon"])
        if d <= raio_m:
            perto.append({"waypoint": w, "distancia_m": d})
    return sorted(perto, key=lambda x: x["distancia_m"])
