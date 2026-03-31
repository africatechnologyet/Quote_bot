import asyncio
import os
import logging
import warnings
from datetime import date

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.warnings import PTBUserWarning
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, ContextTypes, filters,
)
from pdf_generator import generate_quote_pdf

warnings.filterwarnings("ignore", category=PTBUserWarning)

logging.basicConfig(format="%(asctime)s  %(name)s  %(levelname)s  %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR     = os.environ.get("DATA_DIR", "/data")
PDF_DIR      = os.path.join(DATA_DIR, "quotes")
COUNTER_FILE = os.path.join(DATA_DIR, "counter.txt")
os.makedirs(PDF_DIR, exist_ok=True)

ALL_GRADES = ["C-20","C-25","C-30","C-35","C-40","C-45","C-50","C-55","C-60"]

(
    ASK_CLIENT, ASK_LOCATION, ASK_GRADE, ASK_MANUAL_GRADE,
    ASK_PRICE, ASK_VOLUME, ASK_PUMP_TYPE,
    ASK_PUMP_RATE, ASK_VALIDITY, ASK_NEW_QUOTE,
) = range(10)

# ── Helpers ────────────────────────────────────────────────────────

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
        "pump": None, "validity": "3 Days",
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
        [InlineKeyboardButton("🐘 Elephant Pump",    callback_data="pump:elephant"),
         InlineKeyboardButton("🏗️ Stationary Pump",  callback_data="pump:stationary")],
        [InlineKeyboardButton("🚫 No Pump",           callback_data="pump:none")],
        [InlineKeyboardButton("◀️ Back",              callback_data="back:grades")],
    ])

def pump_rate_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭️ Skip (TBD)", callback_data="pumprate:skip")],
        [InlineKeyboardButton("◀️ Back", callback_data="back:pump_type")],
    ])

# ── Step Logic ─────────────────────────────────────────────────────

async def cmd_quote(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data.clear(); init_session(ctx)
    await update.message.reply_text("📄 *CoBuilt Solutions — Quote Generator*\n\n👤 *Step 1:* Enter Client Name:", parse_mode="Markdown")
    return ASK_CLIENT

async def got_client(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["client"] = update.message.text.strip()
    await update.message.reply_text("📍 *Step 2:* Enter Project Location:", parse_mode="Markdown")
    return ASK_LOCATION

async def got_location(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["location"] = update.message.text.strip()
    await update.message.reply_text("🏗️ *Step 3:* Select Concrete Grades:", reply_markup=grade_select_kb([]))
    return ASK_GRADE

async def cb_grade_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    action = query.data.split(":", 1)[1]
    selected = ctx.user_data.setdefault("selected_grades", [])

    if action == "MANUAL":
        await query.edit_message_text("✍️ Enter a custom grade label:")
        return ASK_MANUAL_GRADE

    if action == "DONE":
        if not selected: return ASK_GRADE
        ctx.user_data["grade_queue"] = list(selected)
        return await _ask_price(query, ctx)

    if action in selected: selected.remove(action)
    else: selected.append(action)
    await query.edit_message_text("🏗️ *Step 3:* Select Concrete Grades:", reply_markup=grade_select_kb(selected))
    return ASK_GRADE

async def _ask_price(q_or_m, ctx) -> int:
    queue = ctx.user_data["grade_queue"]
    if not queue: return await _go_pump(q_or_m, ctx)
    grade = queue[0]
    ctx.user_data["_cur_grade"] = grade
    text = f"💰 *Price for {grade}*\nEnter unit price per m³ (ETB):"
    if hasattr(q_or_m, "edit_message_text"): await q_or_m.edit_message_text(text, parse_mode="Markdown")
    else: await q_or_m.reply_text(text, parse_mode="Markdown")
    return ASK_PRICE

async def got_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["_cur_price"] = float(update.message.text.replace(",", ""))
    await update.message.reply_text(f"📊 Enter volume (m³) for *{ctx.user_data['_cur_grade']}*:", parse_mode="Markdown")
    return ASK_VOLUME

async def got_volume(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    vol = float(update.message.text.replace(",", ""))
    grade, price = ctx.user_data.pop("_cur_grade"), ctx.user_data.pop("_cur_price")
    ctx.user_data["grades"].append({"grade": grade, "volume": vol, "unit_price": price, "total": price * vol})
    ctx.user_data["grade_queue"].pop(0)
    return await _ask_price(update.message, ctx)

async def _go_pump(m_or_q, ctx) -> int:
    text = "🚰 *Step 5:* Select Pump Service:"
    kb = pump_type_kb()
    if hasattr(m_or_q, "reply_text"): await m_or_q.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    else: await m_or_q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    return ASK_PUMP_TYPE

async def cb_pump_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    action = query.data.split(":", 1)[1]
    if action == "none":
        ctx.user_data["pump"] = None
        return await _ask_validity(query.message, ctx)
    ctx.user_data["_pump_type"] = action
    await query.edit_message_text("💰 Enter pump price per m³ (ETB):", reply_markup=pump_rate_kb())
    return ASK_PUMP_RATE

async def got_pump_rate(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    rate = float(update.message.text.replace(",", ""))
    ptype = ctx.user_data.pop("_pump_type")
    label = "Elephant Pump" if ptype == "elephant" else "Stationary Pump"
    total_vol = sum(g["volume"] for g in ctx.user_data["grades"])
    ctx.user_data["pump"] = {"type": label, "rate": rate, "total": rate * total_vol}
    return await _ask_validity(update.message, ctx)

async def cb_pump_rate_skip(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    ptype = ctx.user_data.pop("_pump_type", "elephant")
    ctx.user_data["pump"] = {"type": "Elephant Pump" if ptype == "elephant" else "Stationary Pump", "rate": None, "total": 0}
    return await _ask_validity(query.message, ctx)

async def _ask_validity(message, ctx) -> int:
    await message.reply_text("⏳ *Final Step:* Enter quote validity period (e.g., '3 Days', '7 Days'):", parse_mode="Markdown")
    return ASK_VALIDITY

async def got_validity(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["validity"] = update.message.text.strip()
    return await _generate_quote(update.message, ctx)

# ── PDF Generation Logic ───────────────────────────────────────────

async def _generate_quote(message, ctx) -> int:
    await message.reply_text("⏳ Generating official quote PDF...")
    # ... (Path and naming logic same as previous)
    try:
        generate_quote_pdf(
            path=pdf_path, 
            client=ctx.user_data["client"], 
            location=ctx.user_data["location"],
            grades=ctx.user_data["grades"], 
            pump=ctx.user_data["pump"], 
            validity=ctx.user_data["validity"], # New variable
            quote_no=next_quote_number(), 
            date_str=date.today().strftime("%b %d, %Y")
        )
        with open(pdf_path, "rb") as f:
            await message.reply_document(document=f, caption="📄 Quote is ready!")
    except Exception as e:
        logger.error(f"PDF Error: {e}")
        await message.reply_text("❌ Generation failed.")
    return ConversationHandler.END

# ... (Rest of the standard boilerplate)
