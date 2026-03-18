import os
import json
import requests
import anthropic
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# --- AYARLAR ---
TELEGRAM_TOKEN = "8659661541:AAGjGVrcoDSc0DKYDFYRydLiYOkR_ystBLA"
ODDS_API_KEY   = "74f714f00cdf606ae5800e3a2c7f89d7"
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")

SPORTS = {
    "🇹🇷 Süper Lig":      "soccer_turkey_super_league",
    "🏴 Premier League":  "soccer_epl",
    "🇪🇸 La Liga":        "soccer_spain_la_liga",
    "🇩🇪 Bundesliga":     "soccer_germany_bundesliga",
    "🇮🇹 Serie A":        "soccer_italy_serie_a",
    "🇫🇷 Ligue 1":        "soccer_france_ligue_one",
    "⭐ Şamp. Ligi":      "soccer_uefa_champs_league",
}

def get_avg_odds(bookmakers, market, outcome_name):
    prices = []
    for bk in bookmakers or []:
        for mkt in bk.get("markets", []):
            if mkt["key"] == market:
                for o in mkt.get("outcomes", []):
                    if o.get("name") == outcome_name or o.get("description") == outcome_name:
                        if o.get("price"):
                            prices.append(o["price"])
    if not prices:
        return None
    return round(sum(prices) / len(prices), 2)

def get_matches(sport_code):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    url = (
        f"https://api.the-odds-api.com/v4/sports/{sport_code}/odds/"
        f"?apiKey={ODDS_API_KEY}&regions=eu"
        f"&markets=h2h,totals,btts,double_chance"
        f"&oddsFormat=decimal&dateFormat=iso"
        f"&commenceTimeFrom={now.isoformat()}"
        f"&commenceTimeTo={(now + timedelta(days=7)).isoformat()}"
    )
    try:
        res = requests.get(url, timeout=15)
        if not res.ok:
            return []
        data = res.json()
        return data[:10] if isinstance(data, list) else []
    except:
        return []

def analyze_match(match):
    home = match["home_team"]
    away = match["away_team"]
    bk   = match.get("bookmakers", [])

    home_odd = get_avg_odds(bk, "h2h", home)
    draw_odd = get_avg_odds(bk, "h2h", "Draw")
    away_odd = get_avg_odds(bk, "h2h", away)
    over05   = get_avg_odds(bk, "totals", "Over 0.5")
    over15   = get_avg_odds(bk, "totals", "Over 1.5")
    over25   = get_avg_odds(bk, "totals", "Over 2.5")
    over35   = get_avg_odds(bk, "totals", "Over 3.5")
    under25  = get_avg_odds(bk, "totals", "Under 2.5")
    btts_y   = get_avg_odds(bk, "btts", "Yes")
    btts_n   = get_avg_odds(bk, "btts", "No")
    dc_1x    = get_avg_odds(bk, "double_chance", "1X")
    dc_x2    = get_avg_odds(bk, "double_chance", "X2")

    prompt = f"""Sen elit bir futbol analistsin. Gercek bahis oranlarini kullanarak analiz yap.

MAC: {home} vs {away}

GERCEK BAHIS ORANLARI:
1({home})={home_odd} X={draw_odd} 2({away})={away_odd}
0.5U={over05} 1.5U={over15} 2.5U={over25} 3.5U={over35}
KGVar={btts_y} KGYok={btts_n} 1X={dc_1x} X2={dc_x2}

Sadece JSON don dur:
{{"homeWin":SAYI,"draw":SAYI,"awayWin":SAYI,
"over05":SAYI,"over15":SAYI,"over25":SAYI,"over35":SAYI,"under25":SAYI,
"bttsYes":SAYI,"bttsNo":SAYI,"dc1X":SAYI,"dcX2":SAYI,
"iy1":SAYI,"iyX":SAYI,"iy2":SAYI,"iy15u":SAYI,
"homeGoals":SAYI,"awayGoals":SAYI,
"h2hHome":SAYI,"h2hDraw":SAYI,"h2hAway":SAYI,"h2hAvgGoals":"X.X",
"confidence":SAYI,"keyFactor":"max 10 kelime","trend":"max 8 kelime"}}
Kural: homeWin+draw+awayWin=100, tam sayi."""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.content[0].text.replace("```json","").replace("```","").strip()
        return json.loads(raw)
    except Exception as e:
        print(f"AI hata: {e}")
        return None

def bar(val):
    if val is None:
        return "— "
    filled = round(val / 10)
    return "█" * filled + "░" * (10 - filled) + f" %{val}"

def format_analysis(match, pred, sport_name):
    home = match["home_team"]
    away = match["away_team"]
    date = match.get("commence_time","")[:16].replace("T"," ")
    return f"""⚽ *{home} vs {away}*
🏆 {sport_name} | 📅 {date}

━━━━━━━━━━━━━━━━━━
🎯 *MAÇ SONUCU*
1️⃣ {home[:14]}: {bar(pred.get('homeWin'))}
➖ Beraberlik: {bar(pred.get('draw'))}
2️⃣ {away[:14]}: {bar(pred.get('awayWin'))}

━━━━━━━━━━━━━━━━━━
📊 *GOL İSTATİSTİKLERİ*
0\.5 Üst: {bar(pred.get('over05'))}
1\.5 Üst: {bar(pred.get('over15'))}
2\.5 Üst: {bar(pred.get('over25'))}
3\.5 Üst: {bar(pred.get('over35'))}
2\.5 Alt: {bar(pred.get('under25'))}
🔴 KG Var: {bar(pred.get('bttsYes'))}
⚫ KG Yok: {bar(pred.get('bttsNo'))}

━━━━━━━━━━━━━━━━━━
⏱ *İLK YARI*
İY 1: {bar(pred.get('iy1'))}
İY X: {bar(pred.get('iyX'))}
İY 2: {bar(pred.get('iy2'))}
İY 1\.5 Üst: {bar(pred.get('iy15u'))}

━━━━━━━━━━━━━━━━━━
🎯 *ÇİFTE ŞANS*
1X: {bar(pred.get('dc1X'))}
X2: {bar(pred.get('dcX2'))}

━━━━━━━━━━━━━━━━━━
⚔️ *KAFA KAFAYA*
{home[:12]}: {pred.get('h2hHome','?')} galibiyet
Beraberlik: {pred.get('h2hDraw','?')}
{away[:12]}: {pred.get('h2hAway','?')} galibiyet
Ort\. gol: {pred.get('h2hAvgGoals','?')}

⚽ *TAHMİNİ SKOR:* {pred.get('homeGoals','?')} \- {pred.get('awayGoals','?')}
🎯 *AI GÜVEN:* %{pred.get('confidence','?')}
📈 *TREND:* {pred.get('trend','?')}
💡 {pred.get('keyFactor','?')}

_Eğlence amaçlıdır_"""

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    row = []
    for i, (name, code) in enumerate(SPORTS.items()):
        row.append(InlineKeyboardButton(name, callback_data=f"lig:{code}:{name}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    await update.message.reply_text(
        "⚽ *Maç Analiz Botu*\n\nHangi ligi analiz edelim?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("lig:"):
        _, code, name = data.split(":", 2)
        context.user_data["sport"] = code
        context.user_data["sport_name"] = name
        await query.edit_message_text(f"⏳ {name} maçları yükleniyor...")
        
        matches = get_matches(code)
        context.user_data["matches"] = matches

        if not matches:
            keyboard = [[InlineKeyboardButton("🔙 Lig Seç", callback_data="back")]]
            await query.edit_message_text(
                "❌ Bu ligde yaklaşan maç bulunamadı.\n\nBaşka bir lig deneyin.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        keyboard = []
        for i, m in enumerate(matches):
            date = m.get("commence_time","")[:10]
            label = f"{m['home_team'][:12]} vs {m['away_team'][:12]} | {date}"
            keyboard.append([InlineKeyboardButton(f"⚽ {label}", callback_data=f"mac:{i}")])
        keyboard.append([InlineKeyboardButton("🔙 Lig Seç", callback_data="back")])

        await query.edit_message_text(
            f"📋 *{name} — Yaklaşan Maçlar*\n\nAnaliz etmek istediğin maça dokun 👇",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif data.startswith("mac:"):
        idx = int(data.split(":")[1])
        matches = context.user_data.get("matches", [])
        sport_name = context.user_data.get("sport_name", "")
        
        if idx >= len(matches):
            await query.edit_message_text("❌ Maç bulunamadı.")
            return

        match = matches[idx]
        await query.edit_message_text(
            f"🤖 *{match['home_team']} vs {match['away_team']}*\n\nAI analiz yapıyor... ⏳",
            parse_mode="Markdown"
        )

        pred = analyze_match(match)
        if not pred:
            await query.edit_message_text("❌ Analiz yapılamadı, tekrar dene.")
            return

        msg = format_analysis(match, pred, sport_name)
        keyboard = [
            [InlineKeyboardButton("🔙 Maçlara Dön", callback_data=f"lig:{context.user_data.get('sport')}:{sport_name}")],
            [InlineKeyboardButton("🏠 Ana Menü", callback_data="back")]
        ]
        await query.edit_message_text(
            msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif data == "back":
        keyboard = []
        row = []
        for i, (name, code) in enumerate(SPORTS.items()):
            row.append(InlineKeyboardButton(name, callback_data=f"lig:{code}:{name}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        await query.edit_message_text(
            "⚽ *Maç Analiz Botu*\n\nHangi ligi analiz edelim?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("Bot başlatıldı!")
    app.run_polling()

if __name__ == "__main__":
    main()
