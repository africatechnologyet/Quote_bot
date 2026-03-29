# CoBuilt Solutions — Quote Bot

A Telegram bot that generates professional concrete price-quote PDFs for CoBuilt Solutions.

## File Structure

```
├── bot.py                   # Telegram bot + conversation flow
├── pdf_generator.py         # PDF creation (ReportLab)
├── requirements.txt         # Python dependencies
├── render.yaml              # Render.com service config
└── assets/
    ├── logo_clean.png       # CoBuilt logo (transparent bg)
    ├── stamp_clean.png      # Signature stamp (transparent bg)
    └── SPORTE_COLLEGE.ttf   # Custom headline font
```

> **Important:** Place `logo_clean.png`, `stamp_clean.png`, and `SPORTE_COLLEGE.ttf`
> inside an `assets/` folder next to `bot.py` before deploying.

---

## Bot Flow

| Step | What the bot asks |
|------|-------------------|
| 1 | Client / Company Name |
| 2 | Project Location |
| 3 | Concrete Grades (multi-select + custom) |
| 4 | Unit price per m³ + volume for each grade |
| 5 | Pump service — Elephant / Stationary / No Pump + price per m³ |
| 6 | Additional services total (ETB) — shown on PDF, excluded from pricing |

Every step has a **◀️ Back** button. Grades support multiple selection with a **✔️ Done** confirm button.

## Commands

| Command | Action |
|---------|--------|
| `/start` | Welcome message |
| `/quote` | Start a new quote |
| `/cancel` | Cancel current session |

---

## Deploy on Render (Background Worker)

### Step 1 — Push to GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/cobuilt-quote-bot.git
git push -u origin main
```

### Step 2 — Create Background Worker on Render
1. Go to [render.com](https://render.com) → **New** → **Background Worker**
2. Connect your GitHub repo
3. Fill in:

| Setting | Value |
|---------|-------|
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `python bot.py` |

### Step 3 — Add Persistent Disk
- **Name:** `bot-data`
- **Mount Path:** `/data`
- **Size:** 1 GB

### Step 4 — Set Environment Variable
- **Key:** `BOT_TOKEN`
- **Value:** your token from [@BotFather](https://t.me/botfather)

### Step 5 — Deploy
Click **Deploy**. Logs should show:
```
Starting CoBuilt Quote Bot…
```
