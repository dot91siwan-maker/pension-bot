import os
import logging
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# =============================================
# CONFIG - Aapka token yahan hai
# =============================================
TOKEN = "8787856178:AAGZDazVzrL4ySO8uJdh9pkBI_DLZ7XWV7s"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================
# PORTAL SE DATA FETCH KARO
# =============================================
def check_pension_status(search_type: str, search_id: str, year: str = "2026-2027") -> dict:
    """Bihar e-Labharthi portal se pension status check karo"""
    
    url = "https://elabharthi.bih.nic.in/Public/LabharthiSearch.aspx"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://elabharthi.bih.nic.in/",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    try:
        # Pehle page load karo - ViewState lene ke liye
        session = requests.Session()
        resp = session.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # ASP.NET form fields nikalo
        viewstate = ""
        eventval = ""
        viewgen = ""
        
        vs = soup.find("input", {"id": "__VIEWSTATE"})
        ev = soup.find("input", {"id": "__EVENTVALIDATION"})
        vg = soup.find("input", {"id": "__VIEWSTATEGENERATOR"})
        
        if vs: viewstate = vs.get("value", "")
        if ev: eventval = ev.get("value", "")
        if vg: viewgen = vg.get("value", "")
        
        # Search type map
        type_map = {
            "beneficiary": "Beneficiary Id",
            "account": "Account No",
            "aadhaar": "Aadhaar No",
            "ben": "Beneficiary Id",
            "acc": "Account No",
            "aad": "Aadhaar No",
        }
        
        portal_type = type_map.get(search_type.lower(), "Beneficiary Id")
        
        # Form data
        data = {
            "__VIEWSTATE": viewstate,
            "__EVENTVALIDATION": eventval,
            "__VIEWSTATEGENERATOR": viewgen,
            "ctl00$ContentPlaceHolder1$ddlFinancialYear": year,
            "ctl00$ContentPlaceHolder1$ddlSearchType": portal_type,
            "ctl00$ContentPlaceHolder1$txtSearchValue": search_id.strip(),
            "ctl00$ContentPlaceHolder1$btnSearch": "Search"
        }
        
        # POST request
        resp2 = session.post(url, data=data, headers=headers, timeout=15)
        soup2 = BeautifulSoup(resp2.text, "html.parser")
        
        # Result parse karo
        result_table = soup2.find("table", {"id": "ctl00_ContentPlaceHolder1_GridView1"})
        
        if result_table:
            rows = result_table.find_all("tr")
            if len(rows) > 1:
                # Data mili!
                headers_row = [th.get_text(strip=True) for th in rows[0].find_all("th")]
                data_row = [td.get_text(strip=True) for td in rows[1].find_all("td")]
                
                result = dict(zip(headers_row, data_row))
                return {
                    "found": True,
                    "data": result,
                    "raw_row": data_row,
                    "headers": headers_row
                }
        
        # No record found check
        no_record = soup2.find(string=lambda t: t and ("no record" in t.lower() or "not found" in t.lower()))
        if no_record:
            return {"found": False, "reason": "no_record"}
        
        return {"found": False, "reason": "unknown"}
        
    except requests.Timeout:
        return {"found": False, "reason": "timeout"}
    except Exception as e:
        logger.error(f"Fetch error: {e}")
        return {"found": False, "reason": "error", "error": str(e)}


def format_result(result: dict, search_id: str, search_type: str, year: str) -> str:
    """Result ko Telegram message format mein convert karo"""
    
    if result["found"]:
        data = result.get("data", {})
        headers = result.get("headers", [])
        raw = result.get("raw_row", [])
        
        msg = f"✅ *Record Mila!*\n"
        msg += f"━━━━━━━━━━━━━━━━\n"
        msg += f"🔍 *ID:* `{search_id}`\n"
        msg += f"📅 *Year:* {year}\n"
        msg += f"━━━━━━━━━━━━━━━━\n"
        
        if data:
            for key, val in data.items():
                if val and val.strip():
                    emoji = "👤" if "name" in key.lower() else "💰" if "amount" in key.lower() or "payment" in key.lower() else "🏦" if "bank" in key.lower() or "account" in key.lower() else "📋"
                    msg += f"{emoji} *{key}:* {val}\n"
        else:
            for i, val in enumerate(raw):
                if val:
                    msg += f"• {val}\n"
        
        msg += f"━━━━━━━━━━━━━━━━\n"
        msg += f"✅ _Data fetched from e-Labharthi portal_"
        return msg
        
    else:
        reason = result.get("reason", "unknown")
        if reason == "no_record":
            return f"❌ *Record Nahi Mila*\n\n🔍 ID: `{search_id}`\n📅 Year: {year}\n\nPortal mein yeh ID nahi mili. ID dobara check karein."
        elif reason == "timeout":
            return f"⏳ *Portal Slow Hai*\n\nBihar portal se response nahi aaya.\nThodi der baad dobara try karein:\n`/check {search_type} {search_id}`"
        else:
            err = result.get("error", "")
            return f"⚠️ *Error Aaya*\n\nID: `{search_id}`\nKaran: {err or reason}\n\nThodi der baad dobara try karein."


# =============================================
# BOT COMMANDS
# =============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    msg = """🏛️ *Bihar e-Labharthi Pension Checker*
━━━━━━━━━━━━━━━━━━━━

Namaste! Main aapko pension payment status check karne mein madad karta hoon.

*Commands:*

🔍 `/check BEN 123456789`
   → Beneficiary ID se check

🔍 `/check ACC 9876543210`  
   → Account Number se check

🔍 `/check AAD 123412341234`
   → Aadhaar Number se check

📋 `/bulk`
   → Multiple IDs ek saath

📅 `/year 2025-2026`
   → Financial year change karo

ℹ️ `/help` - Help dekhein

━━━━━━━━━━━━━━━━━━━━
_Bihar e-Labharthi Portal se data fetch hota hai_"""
    await update.message.reply_text(msg, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command"""
    msg = """📖 *Help - Kaise Use Karein*

*Single Check:*
`/check BEN 123456789` - Beneficiary ID
`/check ACC 9876543210` - Account No
`/check AAD 123412341234` - Aadhaar No

*Bulk Check (ek saath kai):*
`/bulk` type karein, phir IDs bhejein:
```
123456789
987654321
456789123
```

*Year Change:*
`/year 2025-2026`
`/year 2024-2025`

*Short Forms:*
BEN = Beneficiary ID
ACC = Account Number  
AAD = Aadhaar Number

*Note:* Default year 2026-2027 hai"""
    await update.message.reply_text(msg, parse_mode="Markdown")


async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Single check command: /check BEN 123456789"""
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ *Sahi format:*\n`/check BEN 123456789`\n`/check ACC 9876543210`\n`/check AAD 123412341234`",
            parse_mode="Markdown"
        )
        return
    
    search_type = context.args[0].upper()
    search_id = context.args[1].strip()
    
    # Year check karo user data mein
    year = context.user_data.get("year", "2026-2027")
    
    if search_type not in ["BEN", "ACC", "AAD"]:
        await update.message.reply_text(
            "⚠️ Type BEN, ACC, ya AAD hona chahiye.\n\nExample: `/check BEN 123456789`",
            parse_mode="Markdown"
        )
        return
    
    # Loading message
    loading = await update.message.reply_text(f"⏳ *Checking...* `{search_id}`", parse_mode="Markdown")
    
    # Fetch karo
    result = check_pension_status(search_type, search_id, year)
    formatted = format_result(result, search_id, search_type, year)
    
    await loading.edit_text(formatted, parse_mode="Markdown")


async def bulk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bulk check start karo"""
    context.user_data["bulk_mode"] = True
    context.user_data["bulk_type"] = "BEN"  # default
    
    msg = """📋 *Bulk Check Mode*
━━━━━━━━━━━━━━━━

Abhi IDs bhejein - ek line mein ek:

```
123456789
987654321
456789123
```

*Type change karne ke liye:*
`/bulktype ACC` - Account numbers
`/bulktype AAD` - Aadhaar numbers
`/bulktype BEN` - Beneficiary IDs (default)

`/cancel` - bulk mode band karo"""
    await update.message.reply_text(msg, parse_mode="Markdown")


async def bulktype_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bulk type set karo"""
    if not context.args:
        await update.message.reply_text("Usage: `/bulktype BEN` ya `/bulktype ACC` ya `/bulktype AAD`", parse_mode="Markdown")
        return
    
    t = context.args[0].upper()
    if t not in ["BEN", "ACC", "AAD"]:
        await update.message.reply_text("⚠️ BEN, ACC, ya AAD likhein", parse_mode="Markdown")
        return
    
    context.user_data["bulk_type"] = t
    context.user_data["bulk_mode"] = True
    await update.message.reply_text(f"✅ Type set: *{t}*\nAb IDs bhejein!", parse_mode="Markdown")


async def year_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Year set karo"""
    if not context.args:
        current = context.user_data.get("year", "2026-2027")
        await update.message.reply_text(
            f"📅 *Current Year:* {current}\n\nChange karne ke liye:\n`/year 2025-2026`\n`/year 2024-2025`",
            parse_mode="Markdown"
        )
        return
    
    year = context.args[0]
    valid_years = ["2026-2027", "2025-2026", "2024-2025", "2023-2024"]
    if year not in valid_years:
        await update.message.reply_text(f"⚠️ Valid years: {', '.join(valid_years)}", parse_mode="Markdown")
        return
    
    context.user_data["year"] = year
    await update.message.reply_text(f"✅ Year set: *{year}*", parse_mode="Markdown")


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bulk mode cancel karo"""
    context.user_data["bulk_mode"] = False
    await update.message.reply_text("❌ Bulk mode band ho gaya.\n\nSingle check ke liye: `/check BEN 123456789`", parse_mode="Markdown")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Normal message handle karo - bulk mode mein IDs process karo"""
    
    if not context.user_data.get("bulk_mode", False):
        await update.message.reply_text(
            "💡 ID check karne ke liye:\n`/check BEN 123456789`\n\nHelp ke liye: `/help`",
            parse_mode="Markdown"
        )
        return
    
    # Bulk mode - IDs parse karo
    text = update.message.text.strip()
    ids = [line.strip() for line in text.split('\n') if line.strip()]
    
    if not ids:
        await update.message.reply_text("⚠️ Koi ID nahi mili. Ek line mein ek ID likhein.")
        return
    
    search_type = context.user_data.get("bulk_type", "BEN")
    year = context.user_data.get("year", "2026-2027")
    
    # Progress message
    progress_msg = await update.message.reply_text(
        f"⏳ *{len(ids)} IDs check ho rahi hain...*\n0/{len(ids)} complete",
        parse_mode="Markdown"
    )
    
    results_text = f"📊 *Bulk Check Results*\n*Type:* {search_type} | *Year:* {year}\n━━━━━━━━━━━━━━━━\n"
    ok_count = 0
    fail_count = 0
    
    for i, id_val in enumerate(ids):
        result = check_pension_status(search_type, id_val, year)
        
        if result["found"]:
            ok_count += 1
            data = result.get("data", {})
            # Name nikalo agar ho
            name = ""
            for k, v in data.items():
                if "name" in k.lower() and v:
                    name = v
                    break
            results_text += f"✅ `{id_val}` {name}\n"
        else:
            fail_count += 1
            reason = result.get("reason", "")
            if reason == "no_record":
                results_text += f"❌ `{id_val}` - Not Found\n"
            elif reason == "timeout":
                results_text += f"⏳ `{id_val}` - Timeout\n"
            else:
                results_text += f"⚠️ `{id_val}` - Error\n"
        
        # Progress update (har 3 pe)
        if (i + 1) % 3 == 0 or i == len(ids) - 1:
            await progress_msg.edit_text(
                f"⏳ *Processing...*\n{i+1}/{len(ids)} complete",
                parse_mode="Markdown"
            )
    
    results_text += f"━━━━━━━━━━━━━━━━\n"
    results_text += f"✅ Found: {ok_count} | ❌ Not Found: {fail_count}"
    
    await progress_msg.edit_text(results_text, parse_mode="Markdown")
    
    # Bulk mode band karo
    context.user_data["bulk_mode"] = False
    await update.message.reply_text("✅ *Bulk check complete!*\n\nAur check karne ke liye `/bulk` likhein.", parse_mode="Markdown")


# =============================================
# MAIN
# =============================================
def main():
    app = Application.builder().token(TOKEN).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CommandHandler("bulk", bulk_command))
    app.add_handler(CommandHandler("bulktype", bulktype_command))
    app.add_handler(CommandHandler("year", year_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    
    # Normal messages (bulk mode ke liye)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Bihar Pension Bot chal raha hai...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
