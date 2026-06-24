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

from config import TELEGRAM_TOKEN, SEARCH_RADIUS, PROXIMITY_ALERT
from database import init_db, get_estado, set_estado, listar_waypoints, marcar_visitado
from services.weather import get_clima
from services.geo import reverse_geocode
from services.overpass import get_postos, get_atracoes
from services.route import proxima_parada, pontos_proximos
from brain import gerar_resposta

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("rota66")

# Tempo minimo (segundos) entre relatorios completos durante localizacao ao vivo.
INTERVALO_RELATORIO = 600  # 10 minutos


async def montar_relatorio(lat, lon):
    """Busca todos os dados em paralelo e gera o texto final via Gemini."""
    clima, local, postos, atracoes = await asyncio.gather(
        get_clima(lat, lon),
        reverse_geocode(lat, lon),
        get_postos(lat, lon, SEARCH_RADIUS),
        get_atracoes(lat, lon, SEARCH_RADIUS),
    )
    prox = proxima_parada(lat, lon)
    contexto = {
        "local": local,
        "clima": clima,
        "postos": postos,
        "atracoes": atracoes,
        "proxima_parada": prox,
    }
    return await gerar_resposta(contexto)


# ----- Comandos -----

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = (
        "🏍️ *Companheiro de Rota 66 ativado!*\n\n"
        "Compartilhe sua *localizacao ao vivo* (clipe 📎 > Localizacao > Compartilhar ao vivo) "
        "que eu vou acompanhando voces e avisando sobre paradas, postos e dicas.\n\n"
        "Comandos:\n"
        "/relatorio — clima, postos e dicas de onde voces estao agora\n"
        "/rota — proximas paradas planejadas\n"
        "/postos — postos de gasolina por perto\n"
        "/dicas — o que visitar por perto"
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
    texto = await montar_relatorio(*coords)
    await update.message.reply_text(texto)


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


# ----- Localizacao -----

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    loc = msg.location
    if not loc:
        return
    lat, lon = loc.latitude, loc.longitude
    chat_id = update.effective_chat.id
    agora = time.time()

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

    # 2) Relatorio completo: imediato se for um pin avulso; com intervalo se for ao vivo.
    eh_ao_vivo = bool(loc.live_period)
    deve_relatar = (not eh_ao_vivo) or (agora - ultimo_aviso > INTERVALO_RELATORIO)

    if deve_relatar:
        texto = await montar_relatorio(lat, lon)
        await context.bot.send_message(chat_id, texto)
        set_estado(chat_id, lat, lon, agora)
    else:
        # So atualiza a posicao, sem novo relatorio.
        set_estado(chat_id, lat, lon, ultimo_aviso)


def main():
    init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("relatorio", cmd_relatorio))
    app.add_handler(CommandHandler("rota", cmd_rota))
    app.add_handler(CommandHandler("postos", cmd_postos))
    app.add_handler(CommandHandler("dicas", cmd_dicas))
    # Pega tanto o pin avulso quanto as edicoes da localizacao ao vivo.
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))

    log.info("Bot rodando. Ctrl+C para parar.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
