import os
import json
import requests
import anthropic
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- AYARLAR ---
TELEGRAM_TOKEN = "8659661541:AAGjGVrcoDSc0DKYDFYRydLiYOkR_ystBLA"
ODDS_API_KEY   = "74f714f00cdf606ae5800e3a2c7f89d7"
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")

SPORTS = {
    "süper lig": "soccer_turkey_super_league",
    "super lig": "soccer_turkey_super_league",
    "sl": "soccer_turkey_super_league",
    "premier league": "soccer_epl",
    "pl": "soccer_epl",
    "la liga": "soccer_spain_la_liga",
    "bundesliga": "soccer_germany_bundesliga",
    "serie a": "soccer_italy_serie_a",
    "ligue 1": "soccer_france_ligue_one",
    "şampiyonlar ligi": "soccer_uefa_champs_league",
    "champions": "soccer_uefa_champs_league",
    "cl": "soccer_uefa_champs_league",
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

def pct(odd):
    if not odd:
        return None
    return round((1 / odd) * 100)

def get_matches(sport_code):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    from_time = now.isoformat()
    to_time = (now + timedelta(days=7)).isoformat()
    
    url = (
        f"https://api.the-odds-api.com/v4/sports/{sport_code}/odds/"
        f"?apiKey={ODDS_API_KEY}&regions=eu"
        f"&markets=h2h,totals,btts,double_chance"
        f"&oddsFormat=decimal&dateFormat=iso"
        f"&commenceTimeFrom={from_time}&commenceTimeTo={to_time}"
    )
    res = requests.get(url, timeout=15)
    if not res.ok:
        return []
    data = res.json()
    if not isinstance(data, list):
        return []
    return data[:10]

def analyze_match(match, client):
    home = match["home_team"]
    away = match["away_team"]
    bk   = match.get("bookmakers", [])

    home_odd  = get_avg_odds(bk, "h2h", home)
    draw_odd  = get_avg_odds(bk, "h2h", "Draw")
    away_odd  = get_avg_odds(bk, "h2h", away)
    over05    = get_avg_odds(bk, "totals", "Over 0.5")
    over15    = get_avg_odds(bk, "totals", "Over 1.5")
    over25    = get_avg_odds(bk, "totals", "Over 2.5")
    over35    = get_avg_odds(bk, "totals", "Over 3.5")
    under25   = get_avg_odds(bk, "totals", "Under 2.5")
    btts_y    = get_avg_odds(bk, "btts", "Yes")
    btts_n    = get_avg_odds(bk, "btts", "No")
    dc_1x     = get_avg_odds(bk, "double_chance", "1X")
    dc_x2     = get_avg_odds(bk, "double_chance", "X2")

    prompt = f"""Sen elit bir futbol analistsin. Gercek bahis oranlarini ve bilgini kullanarak analiz yap.

MAC: {home} vs {away}

GERCEK BAHIS ORANLARI:
1({home})={home_odd} | X={draw_odd} | 2({away})={away_odd}
0.5U={over05} | 1.5U={over15} | 2.5U={over25} | 3.5U={over35}
KGVar={btts_y} | KGYok={btts_n} | 1X={dc_1x} | X2={dc_x2}

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
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.content[0].text
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        print(f"AI hata: {e}")
        return None

def format_message(match, pred, sport_name):
    home = match["home_team"]
    away = match["away_team"]
    date = match.get("commence_time", "")[:16].replace("T", " ")

    def bar(pct_val, max_val=100):
        if pct_val is None:
            return "—"
        filled = round(pct_val / 10)
        return "█" * filled + "░" * (10 - filled) + f" %{pct_val}"

    msg = f"""⚽ *{home} vs {away}*
🏆 {sport_name} | 📅 {date}

━━━━━━━━━━━━━━━━━━
🎯 *MAÇ SONUCU*
1️⃣ {home[:15]}: {bar(pred.get('homeWin'))}
➖ Beraberlik: {bar(pred.get('draw'))}
2️⃣ {away[:15]}: {bar(pred.get('awayWin'))}

━━━━━━━━━━━━━━━━━━
📊 *GOL İSTATİSTİKLERİ*
0.5 Üst: {bar(pred.get('over05'))}
1.5 Üst: {bar(pred.get('over15'))}
2.5 Üst: {bar(pred.get('over25'))}
3.5 Üst: {bar(pred.get('over35'))}
2.5 Alt: {bar(pred.get('under25'))}
🔴 KG Var: {bar(pred.get('bttsYes'))}
⚫ KG Yok: {bar(pred.get('bttsNo'))}

━━━━━━━━━━━━━━━━━━
⏱ *İLK YARI*
İY 1 ({home[:10]}): {bar(pred.get('iy1'))}
İY X (Beraberlik): {bar(pred.get('iyX'))}
İY 2 ({away[:10]}): {bar(pred.get('iy2'))}
İY 1.5 Üst: {bar(pred.get('iy15u'))}

━━━━━━━━━━━━━━━━━━
🎯 *ÇİFTE ŞANS*
1X: {bar(pred.get('dc1X'))}
X2: {bar(pred.get('dcX2'))}

━━━━━━━━━━━━━━━━━━
⚔️ *KAFA KAFAYA (AI ANALİZİ)*
{home[:12]}: {pred.get('h2hHome', '?')} galibiyet
Beraberlik: {pred.get('h2hDraw', '?')}
{away[:12]}: {pred.get('h2hAway', '?')} galibiyet
Maç başı ort. gol: {pred.get('h2hAvgGoals', '?')}

━━━━━━━━━━━━━━━━━━
⚽ *TAHMİNİ SKOR*
{home[:12]} {pred.get('homeGoals', '?')} — {pred.get('awayGoals', '?')} {away[:12]}

━━━━━━━━━━━━━━━━━━
🎯 *AI GÜVEN:* %{pred.get('confidence', '?')}
📈 *TREND:* {pred.get('trend', '?')}
💡 *FAKTÖR:* {pred.get('keyFactor', '?')}

_Eğlence amaçlıdır • Yatırım tavsiyesi değildir_"""
    return msg

# --- TELEGRAM HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚽ *Maç Analiz Botu*\n\n"
        "Komutlar:\n"
        "/maclar - Yaklaşan maçları listele\n"
        "/analiz [numara] - Maçı analiz et\n"
        "/lig [lig adı] - Lig seç\n\n"
        "Örnek:\n"
        "/lig süper lig\n"
        "/maclar\n"
        "/analiz 1",
        parse_mode="Markdown"
    )

async def maclar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sport = context.user_data.get("sport", "soccer_turkey_super_league")
    sport_name = context.user_data.get("sport_name", "Süper Lig")
    
    await update.message.reply_text(f"⏳ {sport_name} maçları yükleniyor...")
    
    matches = get_matches(sport)
    if not matches:
        await update.message.reply_text("❌ Bu ligde yaklaşan maç bulunamadı. /lig komutuyla lig değiştir.")
        return
    
    context.user_data["matches"] = matches
    
    msg = f"📋 *{sport_name} Yaklaşan Maçlar*\n\n"
    for i, m in enumerate(matches, 1):
        date = m.get("commence_time", "")[:16].replace("T", " ")
        msg += f"{i}. {m['home_team']} vs {m['away_team']}\n"
        msg += f"   📅 {date}\n\n"
    
    msg += "Analiz için: /analiz [numara]"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def lig(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = " ".join(context.args).lower().strip()
    
    if args in SPORTS:
        context.user_data["sport"] = SPORTS[args]
        context.user_data["sport_name"] = args.title()
        await update.message.reply_text(f"✅ Lig seçildi: *{args.title()}*\n/maclar ile maçları gör.", parse_mode="Markdown")
    else:
        lig_listesi = "\n".join([f"• {k}" for k in SPORTS.keys()])
        await update.message.reply_text(f"❌ Lig bulunamadı.\n\nMevcut ligler:\n{lig_listesi}")

async def analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    matches = context.user_data.get("matches", [])
    sport_name = context.user_data.get("sport_name", "Süper Lig")
    
    if not matches:
        await update.message.reply_text("❌ Önce /maclar komutuyla maçları listele!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Maç numarası gir. Örnek: /analiz 1")
        return
    
    try:
        idx = int(context.args[0]) - 1
        if idx < 0 or idx >= len(matches):
            await update.message.reply_text(f"❌ Geçersiz numara. 1-{len(matches)} arası gir.")
            return
    except ValueError:
        await update.message.reply_text("❌ Geçersiz numara.")
        return
    
    match = matches[idx]
    await update.message.reply_text(
        f"🤖 *{match['home_team']} vs {match['away_team']}* analiz ediliyor...\n"
        "Bu 10-15 saniye sürebilir.",
        parse_mode="Markdown"
    )
    
    if not ANTHROPIC_KEY:
        await update.message.reply_text("❌ ANTHROPIC_API_KEY ayarlanmamış!")
        return
    
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    pred = analyze_match(match, client)
    
    if not pred:
        await update.message.reply_text("❌ Analiz yapılamadı, tekrar dene.")
        return
    
    msg = format_message(match, pred, sport_name)
    await update.message.reply_text(msg, parse_mode="Markdown")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("maclar", maclar))
    app.add_handler(CommandHandler("lig", lig))
    app.add_handler(CommandHandler("analiz", analiz))
    print("Bot başlatıldı!")
    app.run_polling()

if __name__ == "__main__":
    main()
