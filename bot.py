"""Bot do Telegram: ponto de entrada do agente da Rota 66.

Rode com:  python bot.py
Antes, rode uma vez:  python route_loader.py  (para carregar a planilha)
"""
import asyncio
import time
import logging

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes,
)

from config import TELEGRAM_TOKEN, SEARCH_RADIUS, PROXIMITY_ALERT, SEPARACAO_ALERTA
from database import (
    init_db, get_estado, set_estado, listar_waypoints, marcar_visitado,
    ler_conhecimento, upsert_piloto, listar_pilotos, salvar_cache, ler_cache,
)
from services.weather import get_clima
from services.geo import reverse_geocode
from services.overpass import get_postos, get_atracoes
from services.route import (
    proxima_parada, pontos_proximos, haversine, bearing, bussola, ponto_medio,
)
from services.fuel import analise_combustivel, AUTONOMIA_TOTAL_KM, AUTONOMIA_SEGURA_KM
from brain import gerar_resposta, responder_pergunta

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("rota66")

# Tempo minimo (segundos) entre relatorios completos durante localizacao ao vivo.
INTERVALO_RELATORIO = 600  # 10 minutos


async def montar_relatorio(lat, lon):
    """Busca todos os dados em paralelo e gera o texto final via Gemini.
    Retorna (texto, diagnostico_de_combustivel)."""
    clima, local, postos, atracoes, comb = await asyncio.gather(
        get_clima(lat, lon),
        reverse_geocode(lat, lon),
        get_postos(lat, lon, SEARCH_RADIUS),
        get_atracoes(lat, lon, SEARCH_RADIUS),
        analise_combustivel(lat, lon),
    )
    prox = proxima_parada(lat, lon)
    contexto = {
        "local": local,
        "clima": clima,
        "postos": postos,
        "atracoes": atracoes,
        "proxima_parada": prox,
        "combustivel": comb["mensagem"],
    }
    return await gerar_resposta(contexto), comb


# ----- Comandos -----

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = (
        "🏍️ *Companheiro de Rota 66 ativado!*\n\n"
        "Compartilhe sua *localizacao ao vivo* (clipe 📎 > Localizacao > Compartilhar ao vivo) "
        "que eu vou acompanhando voces e avisando sobre paradas, postos e dicas.\n\n"
        "Comandos:\n"
        "/relatorio — clima, postos e dicas de onde voces estao agora\n"
        "/combustivel — autonomia da moto e postos por perto\n"
        "/rota — proximas paradas planejadas\n"
        "/postos — postos de gasolina por perto\n"
        "/dicas — o que visitar por perto\n"
        "/onde — onde esta o outro piloto (distancia e direcao)\n"
        "/encontro — sugere um ponto de reencontro no meio do caminho\n"
        "/parei — avisa o grupo que voce parou (ex.: /parei abastecer)\n\n"
        "💬 Ou simplesmente me *pergunte* qualquer coisa (\"vale a pena parar em Tucumcari?\", "
        "\"que dia chegamos em Flagstaff?\") que eu respondo com base em onde voces estao e na planilha."
    )
    await update.message.reply_text(texto, parse_mode="Markdown")


async def _exige_localizacao(update, context):
    """Recupera a ultima localizacao conhecida do chat, ou pede para compartilhar."""
    estado = get_estado(update.effective_chat.id)
    if not estado or estado["ultima_lat"] is None:
        await update.message.reply_text(
            "Ainda nao sei onde voces estao. Compartilhe a localizacao primeiro 📍"
        )
        return None
    return estado["ultima_lat"], estado["ultima_lon"]


async def cmd_relatorio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    coords = await _exige_localizacao(update, context)
    if not coords:
        return
    await update.message.chat.send_action("typing")
    texto, _ = await montar_relatorio(*coords)
    await update.message.reply_text(texto)


async def cmd_combustivel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    coords = await _exige_localizacao(update, context)
    if not coords:
        return
    await update.message.chat.send_action("typing")
    comb = await analise_combustivel(*coords)
    linhas = [
        f"🏍️ *Autonomia da Heritage*",
        f"Tanque cheio (teórico): ~{AUTONOMIA_TOTAL_KM:.0f} km",
        f"Autonomia segura (com reserva): ~{AUTONOMIA_SEGURA_KM:.0f} km",
        "",
        comb["mensagem"],
    ]
    if comb["postos"]:
        linhas.append("\nPostos mais próximos:")
        for p in comb["postos"]:
            linhas.append(f"⛽ {p['nome']} — {p['dist_km']:.0f} km")
    await update.message.reply_text("\n".join(linhas), parse_mode="Markdown")


async def cmd_rota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pendentes = [w for w in listar_waypoints() if not w["visitado"]]
    if not pendentes:
        await update.message.reply_text("Nenhuma parada planejada pendente. 🏁")
        return
    linhas = ["🗺️ *Proximas paradas planejadas:*"]
    for w in pendentes[:8]:
        dica = f" — {w['dicas']}" if w["dicas"] else ""
        linhas.append(f"{w['ordem']}. {w['nome']} ({w['tipo'] or 'parada'}){dica}")
    await update.message.reply_text("\n".join(linhas), parse_mode="Markdown")


async def cmd_postos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    coords = await _exige_localizacao(update, context)
    if not coords:
        return
    postos = await get_postos(coords[0], coords[1], SEARCH_RADIUS)
    if not postos:
        await update.message.reply_text("Nenhum posto encontrado por perto no mapa. ⛽❌")
        return
    nomes = "\n".join(f"⛽ {p['nome']}" for p in postos[:6])
    await update.message.reply_text(f"Postos num raio de {SEARCH_RADIUS//1000} km:\n{nomes}")


async def cmd_dicas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    coords = await _exige_localizacao(update, context)
    if not coords:
        return
    atracoes = await get_atracoes(coords[0], coords[1], SEARCH_RADIUS)
    if not atracoes:
        await update.message.reply_text("Nada de turistico mapeado por perto agora. 🤷")
        return
    nomes = "\n".join(f"📸 {a['nome']}" for a in atracoes[:6])
    await update.message.reply_text(f"Pra ver por perto:\n{nomes}")


async def cmd_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = (
        "🏍️ *O que eu sei fazer*\n\n"
        "*📍 Onde voces estao*\n"
        "Compartilhem a localizacao ao vivo e eu acompanho sozinho, mandando clima, "
        "postos, atracoes e a proxima parada a cada ~10 min.\n"
        "• /relatorio — resumo do ponto atual agora\n\n"
        "*⛽ Combustivel*\n"
        "Calculo a autonomia da Heritage e aviso se a proxima area for remota.\n"
        "• /combustivel — autonomia + postos por perto\n\n"
        "*🤝 Entre as duas motos*\n"
        "Rastreio voces separadamente e aviso se se afastarem demais.\n"
        "• /onde — onde esta o outro (distancia e direcao)\n"
        "• /encontro — ponto de reencontro no meio do caminho\n"
        "• /parei — avisa o grupo que voce parou\n\n"
        "*🗺️ Sua viagem (da planilha)*\n"
        "• /rota — proximas paradas planejadas\n"
        "• /postos — postos no raio atual\n"
        "• /dicas — o que visitar por perto\n\n"
        "*💬 Perguntas livres*\n"
        "Pode me perguntar qualquer coisa em texto normal — sobre o lugar atual "
        "(\"onde comer aqui?\") ou sobre a viagem inteira da planilha "
        "(\"que dia chegamos em Flagstaff?\", \"qual o hotel mais caro?\").\n\n"
        "_Comandos funcionam com cache mesmo sem sinal; perguntas livres precisam de internet._"
    )
    await update.message.reply_text(texto, parse_mode="Markdown")


# ----- Coordenacao entre as motos -----

def _ha_quanto(ts, agora):
    seg = int(agora - ts)
    if seg < 90:
        return "agora mesmo"
    if seg < 3600:
        return f"ha {seg // 60} min"
    return f"ha {seg // 3600}h{(seg % 3600) // 60:02d}"


async def cmd_onde(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra onde estao os outros pilotos, distancia e direcao."""
    chat_id = update.effective_chat.id
    agora = time.time()
    eu_id = update.effective_user.id if update.effective_user else 0
    pilotos = [p for p in listar_pilotos(chat_id) if p["lat"] is not None]

    if not pilotos:
        await update.message.reply_text("Ninguem compartilhou localizacao ainda. 📍")
        return

    eu = next((p for p in pilotos if p["user_id"] == eu_id), None)
    outros = [p for p in pilotos if p["user_id"] != eu_id]
    if not outros:
        await update.message.reply_text("So tenho a sua localizacao por enquanto. 🤷")
        return

    await update.message.chat.send_action("typing")
    linhas = []
    for p in outros:
        cidade = await reverse_geocode(p["lat"], p["lon"])
        quando = _ha_quanto(p["atualizado_em"], agora)
        if eu:
            d = haversine(eu["lat"], eu["lon"], p["lat"], p["lon"]) / 1000
            direcao = bussola(bearing(eu["lat"], eu["lon"], p["lat"], p["lon"]))
            linhas.append(f"📍 *{p['nome']}* esta perto de {cidade} — a {d:.1f} km de voce, "
                          f"sentido {direcao} (atualizado {quando}).")
        else:
            linhas.append(f"📍 *{p['nome']}* esta perto de {cidade} (atualizado {quando}). "
                          f"Compartilhe sua localizacao pra eu calcular a distancia.")
    await update.message.reply_text("\n".join(linhas), parse_mode="Markdown")


async def cmd_encontro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sugere um ponto de reencontro no meio do caminho entre as duas motos."""
    chat_id = update.effective_chat.id
    pilotos = [p for p in listar_pilotos(chat_id) if p["lat"] is not None]
    if len(pilotos) < 2:
        await update.message.reply_text(
            "Preciso da localizacao dos dois pilotos pra sugerir um ponto de encontro. 📍📍")
        return

    a, b = pilotos[0], pilotos[1]
    mlat, mlon = ponto_medio(a["lat"], a["lon"], b["lat"], b["lon"])
    await update.message.chat.send_action("typing")

    postos, atracoes, cidade = await asyncio.gather(
        get_postos(mlat, mlon, 12000),
        get_atracoes(mlat, mlon, 12000),
        reverse_geocode(mlat, mlon),
    )
    candidatos = (postos or []) + (atracoes or [])
    linhas = [f"🤝 *Ponto de reencontro* (meio do caminho, perto de {cidade}):"]
    if candidatos:
        for c in candidatos[:3]:
            da = haversine(a["lat"], a["lon"], c["lat"], c["lon"]) / 1000
            db = haversine(b["lat"], b["lon"], c["lat"], c["lon"]) / 1000
            linhas.append(f"• {c['nome']} — {da:.0f} km do {a['nome']}, {db:.0f} km do {b['nome']}")
    else:
        linhas.append("Nao achei um lugar mapeado no meio. Combinem a proxima parada da planilha (/rota).")
    await update.message.reply_text("\n".join(linhas), parse_mode="Markdown")


async def cmd_parei(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Avisa o grupo que este piloto parou, com o local atual."""
    chat_id = update.effective_chat.id
    eu_id = update.effective_user.id if update.effective_user else 0
    nome = update.effective_user.first_name if update.effective_user else "piloto"
    eu = next((p for p in listar_pilotos(chat_id) if p["user_id"] == eu_id and p["lat"] is not None), None)
    if not eu:
        await update.message.reply_text(
            "Compartilhe sua localizacao primeiro pra eu avisar onde voce parou. 📍")
        return
    cidade = await reverse_geocode(eu["lat"], eu["lon"])
    motivo = " ".join(context.args) if context.args else ""
    extra = f" ({motivo})" if motivo else ""
    await context.bot.send_message(
        chat_id, f"✋ *{nome}* parou perto de {cidade}{extra}.", parse_mode="Markdown")


# ----- Linguagem natural (qualquer texto que nao seja comando) -----

async def handle_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    pergunta = (msg.text or "").strip()
    if not pergunta:
        return
    chat_id = update.effective_chat.id
    await msg.chat.send_action("typing")

    # Resumo das proprias capacidades, para perguntas tipo "o que voce faz?".
    capacidades = (
        "Sei: relatorio do ponto atual (/relatorio), autonomia e postos (/combustivel), "
        "coordenacao entre as motos (/onde, /encontro, /parei), rota e dicas da planilha "
        "(/rota, /postos, /dicas), e responder perguntas livres sobre o lugar atual e sobre "
        "toda a planilha da viagem. Comando /ajuda mostra tudo."
    )

    estado = get_estado(chat_id)
    # Rota planejada (compacta) entra sempre no contexto, mesmo sem localizacao.
    rota = [
        {"ordem": w["ordem"], "nome": w["nome"], "cidade": w["cidade"],
         "tipo": w["tipo"], "dicas": w["dicas"]}
        for w in listar_waypoints() if not w["visitado"]
    ][:12]

    if estado and estado["ultima_lat"] is not None:
        lat, lon = estado["ultima_lat"], estado["ultima_lon"]
        clima, local, postos, atracoes, comb = await asyncio.gather(
            get_clima(lat, lon),
            reverse_geocode(lat, lon),
            get_postos(lat, lon, SEARCH_RADIUS),
            get_atracoes(lat, lon, SEARCH_RADIUS),
            analise_combustivel(lat, lon),
        )
        prox = proxima_parada(lat, lon)
        contexto = {
            "local_atual": local,
            "clima": clima,
            "postos_proximos": postos,
            "atracoes_proximas": atracoes,
            "proxima_parada": prox,
            "combustivel": comb["mensagem"],
            "rota_planejada": rota,
            "minhas_capacidades": capacidades,
        }
    else:
        contexto = {
            "aviso": "Os pilotos ainda nao compartilharam a localizacao, "
                     "entao nao ha dados de clima/postos/atracoes do ponto atual.",
            "rota_planejada": rota,
            "minhas_capacidades": capacidades,
        }

    resposta = await responder_pergunta(contexto, pergunta, planilha=ler_conhecimento())
    await msg.reply_text(resposta)


# ----- Localizacao -----

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    loc = msg.location
    if not loc:
        return
    lat, lon = loc.latitude, loc.longitude
    chat_id = update.effective_chat.id
    agora = time.time()

    # Registra a posicao DESTE piloto (coordenacao entre as motos).
    user = update.effective_user
    nome_piloto = user.first_name if user else "piloto"
    user_id = user.id if user else 0
    upsert_piloto(chat_id, user_id, nome_piloto, lat, lon, agora)

    estado = get_estado(chat_id)
    ultimo_aviso = estado["ultimo_aviso"] if estado else 0

    # 1) Alerta de proximidade a um ponto planejado (barato, so consulta o banco local).
    for item in pontos_proximos(lat, lon, PROXIMITY_ALERT):
        w = item["waypoint"]
        if not w["visitado"]:
            marcar_visitado(w["id"])
            dica = f"\nDica de voces: {w['dicas']}" if w["dicas"] else ""
            await context.bot.send_message(
                chat_id,
                f"🎯 Voces estao chegando em *{w['nome']}*! ({item['distancia_m']:.0f} m){dica}",
                parse_mode="Markdown",
            )

    # 2) Alerta de SEPARACAO entre as duas motos (barato; so haversine local).
    await _checar_separacao(context, chat_id, agora)

    # 3) Relatorio completo: imediato se for um pin avulso; com intervalo se for ao vivo.
    eh_ao_vivo = bool(loc.live_period)
    deve_relatar = (not eh_ao_vivo) or (agora - ultimo_aviso > INTERVALO_RELATORIO)

    if deve_relatar:
        texto, comb = await montar_relatorio(lat, lon)
        await context.bot.send_message(chat_id, texto)
        if comb["nivel"] in ("critico", "alerta", "remota"):
            await context.bot.send_message(chat_id, comb["mensagem"])
        set_estado(chat_id, lat, lon, agora)
    else:
        set_estado(chat_id, lat, lon, ultimo_aviso)


async def _checar_separacao(context, chat_id, agora):
    """Avisa (no maximo 1x a cada 5 min) se as duas motos se afastaram demais."""
    pilotos = [p for p in listar_pilotos(chat_id) if p["lat"] is not None]
    if len(pilotos) < 2:
        return
    a, b = pilotos[0], pilotos[1]  # os dois mais recentes
    dist = haversine(a["lat"], a["lon"], b["lat"], b["lon"])
    if dist <= SEPARACAO_ALERTA:
        return
    # Throttle via cache: se ja avisamos nos ultimos 5 min, nao repete.
    if ler_cache(f"separacao:{chat_id}", validade_segundos=300):
        return
    salvar_cache(f"separacao:{chat_id}", {"t": agora})
    await context.bot.send_message(
        chat_id,
        f"↔️ *{a['nome']}* e *{b['nome']}* estao a {dist/1000:.1f} km de distancia. "
        f"Usem /onde para se localizar ou /encontro para achar um ponto de reencontro.",
        parse_mode="Markdown",
    )


async def _registrar_menu(app):
    """Registra a lista de comandos que aparece ao digitar '/' no Telegram."""
    from telegram import BotCommand
    await app.bot.set_my_commands([
        BotCommand("ajuda", "O que o bot sabe fazer"),
        BotCommand("relatorio", "Clima, postos e dicas de onde voces estao"),
        BotCommand("combustivel", "Autonomia da moto e postos por perto"),
        BotCommand("onde", "Onde esta o outro piloto"),
        BotCommand("encontro", "Ponto de reencontro entre as motos"),
        BotCommand("parei", "Avisar o grupo que voce parou"),
        BotCommand("rota", "Proximas paradas planejadas"),
        BotCommand("postos", "Postos de gasolina por perto"),
        BotCommand("dicas", "O que visitar por perto"),
        BotCommand("start", "Mensagem de boas-vindas"),
    ])


def main():
    init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(_registrar_menu).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("ajuda", cmd_ajuda))
    app.add_handler(CommandHandler("help", cmd_ajuda))
    app.add_handler(CommandHandler("relatorio", cmd_relatorio))
    app.add_handler(CommandHandler("combustivel", cmd_combustivel))
    app.add_handler(CommandHandler("rota", cmd_rota))
    app.add_handler(CommandHandler("postos", cmd_postos))
    app.add_handler(CommandHandler("dicas", cmd_dicas))
    app.add_handler(CommandHandler("onde", cmd_onde))
    app.add_handler(CommandHandler("encontro", cmd_encontro))
    app.add_handler(CommandHandler("parei", cmd_parei))
    # Pega tanto o pin avulso quanto as edicoes da localizacao ao vivo.
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    # Qualquer texto que NAO seja comando vira pergunta em linguagem natural.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_texto))

    log.info("Bot rodando. Ctrl+C para parar.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
