"""Gestao de autonomia da moto (Harley Heritage Softail Classic).

Calcula a autonomia a partir do tanque/consumo definidos no config e analisa
se ha postos suficientes a frente, alertando ao entrar em 'zona remota'.

Importante: o bot NAO sabe quanto combustivel resta no tanque (nao ha integracao
com o odometro da moto). Por isso ele raciocina pela DISTANCIA ate o proximo posto
mapeado, sempre usando a autonomia SEGURA (com reserva), e deixa a decisao final
com voces. Trate como apoio, nao como medidor de combustivel.
"""
from config import TANQUE_LITROS, CONSUMO_KM_L, RESERVA_LITROS
from services.overpass import get_postos
from services.route import haversine

# Autonomia teorica com tanque cheio (km)
AUTONOMIA_TOTAL_KM = TANQUE_LITROS * CONSUMO_KM_L
# Autonomia que o bot considera "segura": desconta a reserva
AUTONOMIA_SEGURA_KM = (TANQUE_LITROS - RESERVA_LITROS) * CONSUMO_KM_L


async def analise_combustivel(lat, lon, raio_busca_m=90000):
    """Procura postos num raio amplo e devolve um diagnostico de combustivel."""
    postos = await get_postos(lat, lon, raio_busca_m, limite=30)

    com_dist = sorted(
        (
            {"nome": p["nome"], "lat": p["lat"], "lon": p["lon"],
             "dist_km": haversine(lat, lon, p["lat"], p["lon"]) / 1000}
            for p in postos
        ),
        key=lambda x: x["dist_km"],
    )

    if not com_dist:
        nivel = "remota"
        msg = (f"⚠️ ZONA REMOTA: nenhum posto mapeado em {raio_busca_m // 1000} km ao redor. "
               f"Abasteçam ANTES de seguir. Autonomia segura: ~{AUTONOMIA_SEGURA_KM:.0f} km.")
        return {"nivel": nivel, "mensagem": msg, "postos": [], "autonomia_segura_km": AUTONOMIA_SEGURA_KM}

    mais_proximo = com_dist[0]
    d = mais_proximo["dist_km"]

    if d > AUTONOMIA_TOTAL_KM:
        nivel = "critico"
        msg = (f"🚨 CRITICO: o posto mais próximo está a {d:.0f} km — além da autonomia máxima "
               f"(~{AUTONOMIA_TOTAL_KM:.0f} km). Não sigam sem abastecer e levar reserva.")
    elif d > AUTONOMIA_SEGURA_KM:
        nivel = "alerta"
        msg = (f"⛽ ATENÇÃO: o posto mais próximo ({mais_proximo['nome']}) está a {d:.0f} km, "
               f"acima da autonomia segura (~{AUTONOMIA_SEGURA_KM:.0f} km). Só sigam com o tanque cheio.")
    elif d > AUTONOMIA_SEGURA_KM * 0.6:
        nivel = "aviso"
        msg = (f"⛽ Próximo posto: {mais_proximo['nome']} a {d:.0f} km. Dentro da autonomia, "
               f"mas considerem abastecer nele para não esticar demais.")
    else:
        nivel = "ok"
        msg = (f"⛽ Combustível tranquilo: {mais_proximo['nome']} a {d:.0f} km "
               f"(autonomia segura ~{AUTONOMIA_SEGURA_KM:.0f} km).")

    return {
        "nivel": nivel,
        "mensagem": msg,
        "postos": com_dist[:5],
        "autonomia_total_km": AUTONOMIA_TOTAL_KM,
        "autonomia_segura_km": AUTONOMIA_SEGURA_KM,
    }
