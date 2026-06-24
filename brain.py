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


async def responder_pergunta(contexto: dict, pergunta: str, planilha: str = "") -> str:
    """Responde uma pergunta em linguagem natural, ancorada no contexto da viagem.

    Diferente de gerar_resposta (que resume um relatorio), aqui o usuario escreveu
    uma pergunta livre e o bot responde usando os dados que tem em maos, incluindo
    o conteudo completo da planilha (datas, hoteis, custos, distancias, etc.).
    """
    if not GEMINI_API_KEY:
        return ("Pra responder perguntas livres eu preciso do Gemini configurado. "
                "Por enquanto, use os comandos: /relatorio, /combustivel, /postos, /dicas, /rota.")

    secao_planilha = f"\n\nDADOS DA PLANILHA DA VIAGEM (todas as abas):\n{planilha}" if planilha else ""
    prompt = (
        f"{PERSONA}\n\n"
        f"Um dos pilotos perguntou: \"{pergunta}\"\n\n"
        "Responda de forma curta e util. Use o CONTEXTO ATUAL (localizacao, clima, postos, "
        "atracoes, proxima parada) e tambem os DADOS DA PLANILHA (a viagem inteira: datas, "
        "hoteis, custos, distancias, pontos). Se a resposta nao estiver em nenhum dos dois, diga "
        "com franqueza que nao tem o dado. Nao invente lugares, enderecos, datas nem distancias.\n\n"
        f"CONTEXTO ATUAL (JSON):\n{contexto}"
        f"{secao_planilha}"
    )
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    params = {"key": GEMINI_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(URL, params=params, json=body)
            r.raise_for_status()
            data = r.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return ("Nao consegui pensar agora (provavelmente sem sinal). "
                "Tente os comandos, que funcionam com o ultimo dado em cache: "
                "/relatorio, /combustivel, /postos, /dicas.")


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
    comb = ctx.get("combustivel")
    if comb:
        linhas.append(comb)
    postos = ctx.get("postos") or []
    if postos:
        nomes = ", ".join(p["nome"] for p in postos[:3])
        linhas.append(f"⛽ Postos por perto: {nomes}.")
    atracoes = ctx.get("atracoes") or []
    if atracoes:
        nomes = ", ".join(a["nome"] for a in atracoes[:3])
        linhas.append(f"📸 Pra ver: {nomes}.")
    return "\n".join(linhas) if linhas else "Nao consegui dados para esta area agora."
