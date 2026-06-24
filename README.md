# Agente de IA para a Rota 66 — Guia de Implementação

Bot de Telegram que acompanha a viagem de moto em tempo real e informa **clima, próximas paradas, postos de gasolina e dicas de lugares**, cruzando a localização ao vivo com a rota planejada na sua planilha. Tudo com serviços de tier gratuito.

---

## Como as peças se encaixam

```
Você no celular (Telegram)
   │  compartilha localização ao vivo
   ▼
bot.py  ──►  busca em paralelo:
   ├─ services/weather.py   → Open-Meteo (clima)
   ├─ services/geo.py       → Nominatim (nome do lugar)
   ├─ services/overpass.py  → Overpass/OSM (postos + atrações)
   └─ services/route.py     → SQLite (próxima parada planejada)
                   │
                   ▼
              brain.py → Gemini Flash monta a resposta natural em PT-BR
                   │
                   ▼
            volta pro grupo do Telegram
```

A planilha entra pelo `route_loader.py`, que a converte em registros no SQLite uma vez.

---

## Etapa 1 — Criar as contas e chaves (gratuitas)

### 1.1 Token do bot do Telegram
1. No app do Telegram, procure por **@BotFather**.
2. Envie `/newbot`, escolha um nome e um username (precisa terminar em `bot`).
3. Ele devolve um **token** parecido com `7123456789:AAF...`. Guarde.

### 1.2 Chave do Gemini
1. Acesse **https://aistudio.google.com/apikey** com sua conta Google.
2. Clique em criar chave de API e copie. O tier gratuito do Gemini Flash cobre tranquilo o volume de duas pessoas numa viagem.

> As demais fontes (Open-Meteo, Nominatim, Overpass) **não exigem chave** — são abertas. Só precisamos respeitar os limites de uso justo, o que o código já faz com cache e um User-Agent identificável.

---

## Etapa 2 — Preparar o ambiente na sua máquina

Precisa de **Python 3.10+**. No terminal, dentro da pasta do projeto:

```bash
# cria e ativa um ambiente isolado
python -m venv venv
source venv/bin/activate        # no Windows: venv\Scripts\activate

# instala as dependências
pip install -r requirements.txt
```

São só quatro: `python-telegram-bot` (o bot), `httpx` (chamadas HTTP assíncronas), `openpyxl` (ler o Excel) e `python-dotenv` (ler o `.env`).

---

## Etapa 3 — Entender os arquivos

| Arquivo | O que faz |
|---|---|
| `config.py` | Lê as chaves e parâmetros do `.env` |
| `database.py` | SQLite: rota planejada, cache offline e estado de cada chat |
| `route_loader.py` | Lê a planilha Excel → popula o banco (roda uma vez) |
| `services/weather.py` | Clima atual + previsão (Open-Meteo) |
| `services/geo.py` | Coordenada → nome do lugar, e nome → coordenada (Nominatim) |
| `services/overpass.py` | Postos e atrações ao redor (Overpass/OpenStreetMap) |
| `services/route.py` | Cálculo de distância e qual é a próxima parada |
| `brain.py` | Junta os dados e pede ao Gemini um texto natural |
| `bot.py` | O bot em si: comandos e tratamento da localização |

---

## Etapa 4 — Configurar o `.env`

Copie o exemplo e preencha:

```bash
cp .env.example .env
```

Abra o `.env` e cole o token do Telegram e a chave do Gemini. Os outros dois valores controlam o comportamento e podem ficar no padrão:

- `SEARCH_RADIUS` — raio (metros) para buscar postos e atrações. Padrão 15 km.
- `PROXIMITY_ALERT` — a que distância (metros) o bot avisa "estão chegando em X". Padrão 3 km.

> Edite também o `USER_AGENT` no `config.py` colocando um e-mail seu — é exigência da política do OpenStreetMap.

---

## Etapa 5 — Carregar a planilha da rota

Coloque sua planilha na pasta do projeto com o nome `rota.xlsx` (ou ajuste `EXCEL_PATH` no `.env`). O loader **detecta as colunas pelo cabeçalho**, aceitando vários nomes em português. Idealmente a planilha tem colunas como:

| ordem | nome | tipo | lat | lon | dicas |
|---|---|---|---|---|---|
| 1 | Chicago | cidade | 41.8781 | -87.6298 | Ponto de partida, foto na placa "Begin Route 66" |
| 2 | Pontiac | parada | 40.8809 | -88.6298 | Mural da Rota 66 |
| 3 | St. Louis | pernoite | 38.627 | -90.199 | Gateway Arch |

**Não tem as coordenadas?** Sem problema — deixe `lat`/`lon` em branco e o loader geocodifica pelo nome automaticamente (via Nominatim). Os nomes das colunas podem variar: ele entende `sequencia/etapa/dia` para ordem, `lugar/parada/local` para nome, `observacoes/obs/notas` para dicas, etc.

Rode uma vez:

```bash
python route_loader.py
```

Ele mostra quais colunas detectou e quantos pontos carregou. Rode de novo sempre que mudar a planilha.

---

## Etapa 6 — Rodar e testar localmente

```bash
python bot.py
```

No Telegram, abra uma conversa com seu bot (ou crie um grupo com você, seu amigo e o bot) e:

1. Envie `/start` — ele explica os comandos.
2. Mande um **pin de localização avulso** (clipe 📎 → Localização → Enviar localização atual). O bot responde na hora com o relatório completo daquele ponto. Bom para testar sem estar viajando — mande um pin em Chicago, por exemplo.
3. Teste os comandos: `/relatorio`, `/rota`, `/postos`, `/dicas`.

### Como vai funcionar na estrada
O piloto compartilha a **localização ao vivo** (clipe 📎 → Localização → *Compartilhar localização ao vivo* → 8 horas). A partir daí:
- O bot recebe a posição atualizada sozinho, sem ninguém mexer no celular.
- Manda um **relatório completo a cada ~10 min** (configurável em `INTERVALO_RELATORIO` no `bot.py`), pra não floodar nem gastar API à toa.
- Dispara um **alerta imediato** sempre que vocês chegam a menos de 3 km de um ponto que marcaram na planilha, já trazendo a dica que vocês anotaram.

### Perguntas em linguagem natural

Além dos comandos, você pode mandar qualquer **pergunta em texto normal** ("vale a pena parar em Tucumcari?", "onde comer bem por aqui?", "qual o próximo lugar histórico?"). O bot usa a última localização conhecida + os dados que ele busca (clima, postos, atrações, rota) e responde via Gemini. Isso depende de **sinal de internet**; sem sinal, ele orienta a usar os comandos, que respondem com o cache.

### ⚠️ Uso em grupo (vocês dois): desligar o "privacy mode"

Por padrão, um bot do Telegram em **grupo** só enxerga mensagens que começam com `/` ou que o mencionam com `@`. Ou seja, num grupo ele **não veria** nem a localização ao vivo nem as perguntas em texto livre. Pra liberar:

1. No **@BotFather**, mande `/setprivacy`.
2. Escolha o seu bot.
3. Selecione **Disable**.

Depois disso, remova e adicione o bot ao grupo de novo (pra valer a mudança). Em conversa privada (1 a 1) isso não é necessário — o bot já vê tudo.

---

## Etapa 7 — Deixar rodando 24h de graça (deploy)

Como o bot usa *polling* (ele pergunta ao Telegram por updates, em vez de receber webhooks), **não precisa de IP público nem domínio**. Isso permite hospedar numa VM gratuita.

**Opção recomendada: Oracle Cloud Always Free.** O tier ARM Ampere é generoso e permanente.

1. Crie a conta e suba uma VM Ubuntu (ARM, *Always Free*).
2. Conecte por SSH, instale Python e copie a pasta do projeto (via `git clone` ou `scp`).
3. Instale as dependências como na Etapa 2.
4. Para o bot sobreviver a quedas e reinícios, rode como serviço com `systemd`. Crie `/etc/systemd/system/rota66.service`:

```ini
[Unit]
Description=Bot Rota 66
After=network.target

[Service]
WorkingDirectory=/home/ubuntu/rota66-bot
ExecStart=/home/ubuntu/rota66-bot/venv/bin/python bot.py
Restart=always
User=ubuntu

[Install]
WantedBy=multi-user.target
```

Depois:

```bash
sudo systemctl enable rota66
sudo systemctl start rota66
sudo systemctl status rota66     # conferir se está de pé
```

Pronto: o bot fica ligado mesmo com seu computador desligado.

---

## Aviso importante: sinal de celular na rota

Trechos longos da Rota 66 (deserto do Arizona, Novo México, Mojave) têm sinal fraco ou nenhum. Duas providências:

1. **Chip/eSIM de dados americano** decente para os pilotos.
2. O bot já **guarda em cache** (no SQLite) o clima, os postos e as atrações que consultou. Quando a conexão cai, ele responde com o último dado conhecido, marcado como "offline". Vale, antes de entrar num trecho ermo, mandar um `/relatorio` ou `/postos` enquanto ainda há sinal, pra "pré-carregar" a região.

---

## Ideias de evolução (quando quiserem)

- **Estimativa de autonomia:** somar a distância até o próximo posto e cruzar com o tanque da moto pra avisar "abasteça aqui, o próximo posto fica a 90 km".
- **Resumo do dia:** comando `/diario` que lista tudo que passaram e fotografaram no dia.
- **Custos da viagem:** registrar gastos com gasolina/hospedagem por mensagem.
- **Clima preventivo:** alerta automático se a previsão à frente indicar tempestade.

Qualquer uma dessas é só um arquivo novo em `services/` mais um comando no `bot.py` — a estrutura já está preparada pra crescer assim.
