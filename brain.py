"""O 'cerebro' do agente: junta todos os dados estruturados e pede ao Gemini Flash
um resumo natural, simpatico e em portugues, como um companheiro de viagem."""
import httpx
from config import GEMINI_API_KEY

MODELO = "gemini-2.5-flash"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODELO}:generateContent"

PERSONA = (
    "Voce e um companheiro de viagem bem-humorado e prestativo de dois motociclistas "
    "brasileiros fazendo a Rota 66 nos EUA. Fale em portugues do Brasil, de forma curta "
    "e direta (eles estao na estrada, lendo no celular). Use os dados fornecidos; nao invente "
    "lugares nem distancias. Se algum dado vier marcado como offline/desatualizado, avise."
)


async def gerar_resposta(contexto: dict) -> str:
    """Recebe um dicionario com clima, local, postos, atracoes e proxima parada,
    e devolve um texto pronto para enviar no Telegram."""
    if not GEMINI_API_KEY:
        return _resposta_simples(contexto)  # fallback sem LLM

    prompt = f"{PERSONA}\n\nDADOS ATUAIS (JSON):\n{contexto}\n\nGere a mensagem para eles agora."
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    params = {"key": GEMINI_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(URL, params=params, json=body)
            r.raise_for_status()
            data = r.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        # Se o Gemini falhar (cota, rede), cai para um resumo montado na mao.
        return _resposta_simples(contexto)


def _resposta_simples(ctx: dict) -> str:
    """Resumo de reserva, sem LLM: garante que o bot sempre responde algo util."""
    linhas = []
    if ctx.get("local"):
        linhas.append(f"📍 Voces estao em {ctx['local']}.")
    clima = ctx.get("clima")
    if clima:
        offline = " (dado offline)" if clima.get("_offline") else ""
        linhas.append(
            f"🌤️ {clima['descricao'].capitalize()}, {clima['temperatura']}°C "
            f"(min {clima['min']}° / max {clima['max']}°, chuva {clima['chance_chuva']}%).{offline}"
        )
    prox = ctx.get("proxima_parada")
    if prox:
        km = prox["distancia_m"] / 1000
        linhas.append(f"🏁 Proxima parada: {prox['waypoint']['nome']} (~{km:.0f} km).")
    postos = ctx.get("postos") or []
    if postos:
        nomes = ", ".join(p["nome"] for p in postos[:3])
        linhas.append(f"⛽ Postos por perto: {nomes}.")
    atracoes = ctx.get("atracoes") or []
    if atracoes:
        nomes = ", ".join(a["nome"] for a in atracoes[:3])
        linhas.append(f"📸 Pra ver: {nomes}.")
    return "\n".join(linhas) if linhas else "Nao consegui dados para esta area agora."
