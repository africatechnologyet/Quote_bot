import os
import logging
from datetime import date

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, ContextTypes, filters,
)
from pdf_generator import generate_quote_pdf

logging.basicConfig(format="%(asctime)s  %(name)s  %(levelname)s  %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR     = os.environ.get("DATA_DIR", "/data")
PDF_DIR      = os.path.join(DATA_DIR, "quotes")
COUNTER_FILE = os.path.join(DATA_DIR, "counter.txt")
os.makedirs(PDF_DIR, exist_ok=True)

ALL_GRADES = ["C-20","C-25","C-30","C-35","C-40","C-45","C-50","C-55","C-60"]

(
    ASK_CLIENT, ASK_LOCATION, ASK_GRADE, ASK_MANUAL_GRADE,
    ASK_PRICE, ASK_VOLUME, ASK_PUMP_TYPE, ASK_PUMP_RATE, ASK_ADDITIONAL,
) = range(9)


def next_quote_number() -> str:
    try:
        with open(COUNTER_FILE) as f:
            n = int(f.read().strip()) + 1
    except (FileNotFoundError, ValueError):
        n = 1
    with open(COUNTER_FILE, "w") as f:
        f.write(str(n))
    return f"RMX-{n:04d}"


def init_session(ctx):
    ctx.user_data.update({
        "client": "", "location": "",
        "selected_grades": [], "grades": [], "grade_queue": [],
        "pump": None, "extra_service": 0.0,
    })


def grade_select_kb(selected: list) -> InlineKeyboardMarkup:
    buttons, row = [], []
    for g in ALL_GRADES:
        label = f"✅ {g}" if g in selected else g
        row.append(InlineKeyboardButton(label, callback_data=f"gs:{g}"))
        if len(row) == 3:
            buttons.append(row); row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("⌨️ Add Custom Grade", callback_data="gs:MANUAL")])
    if selected:
        buttons.append([InlineKeyboardButton(f"✔️ Done  ({len(selected)} selected)", callback_data="gs:DONE")])
    buttons.append([InlineKeyboardButton("◀️ Back", callback_data="back:location")])
    return InlineKeyboardMarkup(buttons)


def pump_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🐘 Elephant Pump", callback_data="pump:elephant"),
         InlineKeyboardButton("🏗️ Stationary Pump", callback_data="pump:stationary")],
        [InlineKeyboardButton("🚫 No Pump", callback_data="pump:none")],
        [InlineKeyboardButton("◀️ Back", callback_data="back:grades")],
    ])


def back_kb(target: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data=f"back:{target}")]])


def grade_summary(ctx) -> str:
    return "\n".join(
        f"• {g['grade']}: {g['volume']:,.2f} m³ @ {g['unit_price']:,.2f} ETB = {g['total']:,.2f} ETB"
        for g in ctx.user_data["grades"]
    ) or "—"


# ── Commands ───────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to *CoBuilt Solutions* Quote Bot!\nSend /quote to generate a price quote.",
        parse_mode="Markdown")


async def cmd_quote(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data.clear(); init_session(ctx)
    await update.message.reply_text(
        "📄 *CoBuilt Solutions — Quote Generator*\n\n👤 *Step 1:* Enter Client / Company Name:",
        parse_mode="Markdown")
    return ASK_CLIENT


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data.clear()
    await update.message.reply_text("❌ Quote cancelled. Send /quote to start again.")
    return ConversationHandler.END


# ── Step 1: Client ─────────────────────────────────────────────────

async def got_client(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("⚠️ Client name cannot be empty. Try again:"); return ASK_CLIENT
    ctx.user_data["client"] = name
    await update.message.reply_text(
        "📍 *Step 2:* Enter Project Location:", parse_mode="Markdown",
        reply_markup=back_kb("client"))
    return ASK_LOCATION


# ── Step 2: Location ───────────────────────────────────────────────

async def got_location(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    loc = update.message.text.strip()
    if not loc:
        await update.message.reply_text("⚠️ Location cannot be empty. Try again:"); return ASK_LOCATION
    ctx.user_data["location"] = loc
    ctx.user_data["selected_grades"] = []
    await update.message.reply_text(
        "🏗️ *Step 3:* Select Concrete Grades — tap to toggle, press *✔️ Done* to confirm:",
        parse_mode="Markdown", reply_markup=grade_select_kb([]))
    return ASK_GRADE


# ── Step 3: Grade multi-select ─────────────────────────────────────

async def cb_grade_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    action = query.data.split(":", 1)[1]
    selected = ctx.user_data.setdefault("selected_grades", [])

    if action == "MANUAL":
        await query.edit_message_text(
            "✍️ Enter a custom grade label (e.g. C-55 Special):", parse_mode="Markdown")
        return ASK_MANUAL_GRADE

    if action == "DONE":
        if not selected:
            await query.answer("⚠️ Select at least one grade.", show_alert=True); return ASK_GRADE
        ctx.user_data["grade_queue"] = list(selected)
        ctx.user_data["grades"] = []
        return await _ask_price(query, ctx)

    if action in selected: selected.remove(action)
    else: selected.append(action)

    await query.edit_message_text(
        "🏗️ *Step 3:* Select Concrete Grades — tap to toggle, press *✔️ Done* to confirm:",
        parse_mode="Markdown", reply_markup=grade_select_kb(selected))
    return ASK_GRADE


async def got_manual_grade(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    grade = update.message.text.strip().upper()
    if not grade:
        await update.message.reply_text("⚠️ Enter a valid grade label:"); return ASK_MANUAL_GRADE
    selected = ctx.user_data.setdefault("selected_grades", [])
    if grade not in selected: selected.append(grade)
    await update.message.reply_text(
        f"✅ *{grade}* added.\n\nContinue selecting or press *✔️ Done*:",
        parse_mode="Markdown", reply_markup=grade_select_kb(selected))
    return ASK_GRADE


# ── Steps 4a+4b: Price + Volume per grade (looped) ─────────────────

async def _ask_price(q_or_m, ctx) -> int:
    queue = ctx.user_data["grade_queue"]
    if not queue:
        return await _go_pump(q_or_m, ctx)
    grade = queue[0]
    ctx.user_data["_cur_grade"] = grade
    text = f"💰 *Step 4 — Price for {grade}*\n\nEnter unit price per m³ (ETB):"
    kb = back_kb("grades")
    if hasattr(q_or_m, "edit_message_text"):
        await q_or_m.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await q_or_m.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    return ASK_PRICE


async def got_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        price = float(update.message.text.strip().replace(",", ""))
        if price <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ Enter a valid positive price (e.g. 14500):", reply_markup=back_kb("grades"))
        return ASK_PRICE
    grade = ctx.user_data["_cur_grade"]
    ctx.user_data["_cur_price"] = price
    await update.message.reply_text(
        f"📊 *Volume for {grade}*\n\nPrice locked: *{price:,.2f} ETB/m³*\nNow enter the volume (m³):",
        parse_mode="Markdown", reply_markup=back_kb("price"))
    return ASK_VOLUME


async def got_volume(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        vol = float(update.message.text.strip().replace(",", ""))
        if vol <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ Enter a valid positive volume:", reply_markup=back_kb("price"))
        return ASK_VOLUME

    grade = ctx.user_data.pop("_cur_grade")
    price = ctx.user_data.pop("_cur_price")
    total = price * vol
    ctx.user_data["grades"].append({"grade": grade, "volume": vol, "unit_price": price, "total": total})
    ctx.user_data["grade_queue"].pop(0)

    remaining = ctx.user_data["grade_queue"]
    done_line = f"✅ *{grade}* — {vol:,.2f} m³ × {price:,.2f} ETB = *{total:,.2f} ETB*"

    if remaining:
        await update.message.reply_text(done_line + f"\n\n_{len(remaining)} grade(s) remaining…_", parse_mode="Markdown")
        return await _ask_price(update.message, ctx)

    summary = grade_summary(ctx)
    await update.message.reply_text(f"{done_line}\n\n📋 *Grades Summary:*\n{summary}", parse_mode="Markdown")
    return await _go_pump(update.message, ctx)


# ── Step 5: Pump type ──────────────────────────────────────────────

async def _go_pump(m_or_q, ctx) -> int:
    text = "🚰 *Step 5:* Select Pump Service:"
    kb = pump_type_kb()
    if hasattr(m_or_q, "reply_text"):
        await m_or_q.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await m_or_q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    return ASK_PUMP_TYPE


async def cb_pump_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    action = query.data.split(":", 1)[1]

    if action == "none":
        ctx.user_data["pump"] = None
        await query.edit_message_text("🚫 No pump service.")
        return await _go_additional(query.message, ctx)

    label = "Elephant Pump" if action == "elephant" else "Stationary Pump"
    ctx.user_data["_pump_type"] = action
    await query.edit_message_text(
        f"💰 *{label} Rate*\n\nEnter pump price per m³ (ETB):",
        parse_mode="Markdown", reply_markup=back_kb("pump_type"))
    return ASK_PUMP_RATE


async def got_pump_rate(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        rate = float(update.message.text.strip().replace(",", ""))
        if rate <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ Enter a valid positive rate:", reply_markup=back_kb("pump_type"))
        return ASK_PUMP_RATE

    ptype = ctx.user_data.pop("_pump_type", "elephant")
    label = "Elephant Pump" if ptype == "elephant" else "Stationary Pump"
    total_vol = sum(g["volume"] for g in ctx.user_data["grades"])
    ctx.user_data["pump"] = {"type": label, "rate": rate, "total": rate * total_vol}
    await update.message.reply_text(
        f"✅ *{label}* — {rate:,.2f} ETB/m³ × {total_vol:,.2f} m³ = *{rate * total_vol:,.2f} ETB*",
        parse_mode="Markdown")
    return await _go_additional(update.message, ctx)


# ── Step 6: Additional services ────────────────────────────────────

async def _go_additional(message, ctx) -> int:
    await message.reply_text(
        "➕ *Step 6:* Additional Services\n\n"
        "Enter the total ETB for any extra services _(vibrator, labour, etc.)_\n"
        "Enter *0* if none.",
        parse_mode="Markdown", reply_markup=back_kb("pump_type"))
    return ASK_ADDITIONAL


async def got_additional(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amt = float(update.message.text.strip().replace(",", ""))
        if amt < 0: raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ Enter 0 or a positive amount:", reply_markup=back_kb("pump_type"))
        return ASK_ADDITIONAL
    ctx.user_data["extra_service"] = amt
    return await _generate_quote(update.message, ctx)


# ── Back button router ─────────────────────────────────────────────

async def cb_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    target = query.data.split(":", 1)[1]

    if target == "client":
        await query.edit_message_text("👤 *Step 1:* Enter Client / Company Name:", parse_mode="Markdown")
        return ASK_CLIENT

    if target == "location":
        await query.edit_message_text("📍 *Step 2:* Enter Project Location:", parse_mode="Markdown", reply_markup=back_kb("client"))
        return ASK_LOCATION

    if target == "grades":
        selected = ctx.user_data.get("selected_grades", [])
        await query.edit_message_text(
            "🏗️ *Step 3:* Select Concrete Grades — tap to toggle, press *✔️ Done* to confirm:",
            parse_mode="Markdown", reply_markup=grade_select_kb(selected))
        return ASK_GRADE

    if target == "price":
        grade = ctx.user_data.get("_cur_grade", "")
        await query.edit_message_text(
            f"💰 *Price for {grade}*\n\nEnter unit price per m³ (ETB):",
            parse_mode="Markdown", reply_markup=back_kb("grades"))
        return ASK_PRICE

    if target == "pump_type":
        await query.edit_message_text("🚰 *Step 5:* Select Pump Service:", parse_mode="Markdown", reply_markup=pump_type_kb())
        return ASK_PUMP_TYPE

    await query.edit_message_text("⚠️ Navigation error. Use /quote to restart.")
    return ConversationHandler.END


# ── PDF generation ─────────────────────────────────────────────────

async def _generate_quote(message, ctx) -> int:
    await message.reply_text("⏳ Generating your official quote PDF…")
    client   = ctx.user_data["client"]
    location = ctx.user_data["location"]
    grades   = ctx.user_data["grades"]
    pump     = ctx.user_data["pump"]
    extra    = ctx.user_data["extra_service"]
    quote_no = next_quote_number()
    today    = date.today().strftime("%b %d, %Y")
    safe     = client.replace(" ", "_").replace("/", "-")
    pdf_path = os.path.join(PDF_DIR, f"CoBuilt_Quote_{safe}_{quote_no}.pdf")
    try:
        generate_quote_pdf(
            path=pdf_path, client=client, location=location,
            grades=grades, pump=pump, extra_service=extra,
            quote_no=quote_no, date_str=today,
        )
    except Exception as e:
        logger.error(f"PDF error: {e}", exc_info=True)
        await message.reply_text("❌ Failed to generate PDF. Try /quote again.")
        return ConversationHandler.END
    with open(pdf_path, "rb") as f:
        await message.reply_document(
            document=f, filename=f"CoBuilt_Quote_{safe}_{quote_no}.pdf",
            caption=f"📄 Quote *{quote_no}* for *{client}* is ready!\n📍 {location}",
            parse_mode="Markdown")
    return ConversationHandler.END


async def unexpected(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚠️ Please use the buttons or follow the step.\nSend /cancel to abort.")


# ── Main ───────────────────────────────────────────────────────────

def main():
    import asyncio
    token = os.environ.get("BOT_TOKEN", "")
    if not token: raise RuntimeError("BOT_TOKEN not set!")
    logger.info("Starting CoBuilt Quote Bot…")
    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("quote", cmd_quote)],
        states={
            ASK_CLIENT:      [MessageHandler(filters.TEXT & ~filters.COMMAND, got_client)],
            ASK_LOCATION:    [MessageHandler(filters.TEXT & ~filters.COMMAND, got_location),
                              CallbackQueryHandler(cb_back, pattern=r"^back:")],
            ASK_GRADE:       [CallbackQueryHandler(cb_grade_select, pattern=r"^gs:"),
                              CallbackQueryHandler(cb_back, pattern=r"^back:")],
            ASK_MANUAL_GRADE:[MessageHandler(filters.TEXT & ~filters.COMMAND, got_manual_grade)],
            ASK_PRICE:       [MessageHandler(filters.TEXT & ~filters.COMMAND, got_price),
                              CallbackQueryHandler(cb_back, pattern=r"^back:")],
            ASK_VOLUME:      [MessageHandler(filters.TEXT & ~filters.COMMAND, got_volume),
                              CallbackQueryHandler(cb_back, pattern=r"^back:")],
            ASK_PUMP_TYPE:   [CallbackQueryHandler(cb_pump_type, pattern=r"^pump:"),
                              CallbackQueryHandler(cb_back, pattern=r"^back:")],
            ASK_PUMP_RATE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, got_pump_rate),
                              CallbackQueryHandler(cb_back, pattern=r"^back:")],
            ASK_ADDITIONAL:  [MessageHandler(filters.TEXT & ~filters.COMMAND, got_additional),
                              CallbackQueryHandler(cb_back, pattern=r"^back:")],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel),
                   MessageHandler(filters.TEXT & ~filters.COMMAND, unexpected)],
        allow_reentry=True,
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(conv)
    async def run():
        await app.initialize()
        await app.start()
        await app.updater.start_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )
        await app.updater.idle()
        await app.stop()
        await app.shutdown()

    asyncio.run(run())


if __name__ == "__main__":
    main()
