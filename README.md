# Instagram Followers Hide Bot

A Telegram bot that hides an Instagram account's **followers** and **following** lists using the account's own `sessionid` cookie. It includes a token economy, referral rewards, a redeem shop, force-join channels/groups, and a full admin panel.

![Python](https://img.shields.io/badge/python-3.12-blue)
![aiogram](https://img.shields.io/badge/aiogram-3.x-2CA5E0)
![License](https://img.shields.io/badge/license-MIT-green)

> **Status:** educational / self-hosted project. There is no official hosted service.

---

## ⚠️ Disclaimer

**Read this before using or deploying the project.**

- This project is provided for **educational and personal use only**.
- Use it **only on your own Instagram account**, with your own `sessionid`.
- **Never** submit someone else's `sessionid`. Accessing an account without permission can be illegal (for example, unauthorized-access and computer-misuse laws) and is strictly against this project's intended use.
- This project is **not affiliated with, endorsed by, or supported by Instagram or Meta**.
- Automating Instagram through an unofficial endpoint **violates Instagram's Terms of Service** and may result in account restrictions, challenges, or bans.
- The software is provided **"as is"**, without warranty of any kind. You are responsible for how you use and deploy it.
- This is **not legal advice**. If you plan to operate this publicly or commercially, consult a qualified lawyer in your jurisdiction.

By using this software you accept these risks.

---

## 🔐 Privacy: what happens to the session ID

The `sessionid` is a sensitive bearer credential — treat it like a password.

- **The bot does not store the session ID.** It is never written to the database.
- The user's message containing the `sessionid` is **deleted immediately** after it is read.
- The value is kept **only in memory** for the single Instagram request and is then discarded.
- It is **not logged**. Error messages redact the token, `sessionid`, and authorization header.
- Outbound requests use a **15-second timeout**, a **1 MB response limit**, and **refuse redirects** so credentials cannot be forwarded to another host.

What the bot *does* store is limited to normal bot data: Telegram user ID, username, first name, token balance, referral link/credit status, successful-hide count, join date, required chats, redeem items, and redemption requests.

**Recommendation:** use a secondary Instagram account and change the password after hiding your lists.

---

## ✨ Features

### User side

- **Hide followers & following** by sending an Instagram `sessionid`.
- **Token system** — each successful hide costs tokens.
- **Referral program** — invite friends and earn 1 token per successful referral.
- **Redeem shop** — spend tokens on rewards with automatic or manual delivery.
- **Profile** — see token balance, successful hides, and referral stats.
- **Help menu** — clear, step-by-step instructions for getting the session ID on PC.
- **Force join** — users must join all required channels/groups before using the bot.
- **No link previews** — previews are disabled globally.

### Admin side

- **Required Chats** — add/remove channels and groups users must join.
- **Token Settings** — configure referral reward, hide cost, and welcome bonus.
- **Redeem Items** — add/edit/delete rewards, set cost, stock, delivery type, reward text, and enable/disable.
- **Give Tokens** — add tokens to a user or set their exact balance.
- **Pending Redemptions** — mark manual rewards as completed and notify the user.
- **Statistics** — users, successful hides, tokens held, referrals, and pending requests.
- **Unlimited admin tokens** — admin accounts hide and redeem for free.

---

## 🧠 How it works

### After the user sends a `sessionid`

1. The bot **deletes the message** containing the session ID.
2. It sends a temporary `⌛ Working…` status.
3. It validates the format: a numeric Instagram user ID followed by `:` or `%3A`.
4. It reserves the hide cost from the user's token balance.
5. It builds an Instagram authorization header from the session ID.
6. It sends Instagram's own GraphQL mutation for the privacy setting `hide_followers_following_list`.
7. It checks that Instagram returned `{"value": true}`.
8. On failure, the reserved token is **refunded** and the user sees an error.
9. On success, the successful-hide counter increases.
10. If this is the invited user's **first** successful hide, the referrer receives referral tokens.
11. The user sees the result, tokens spent, and remaining balance.

The request toggles exactly one Instagram privacy setting. It **does not**:

- log in with a password,
- delete the account,
- unfollow anyone,
- remove followers,
- post anything,
- or store the session ID.

### Why hides can fail

The Instagram session can expire, require a verification challenge, or be blocked because of a new device/IP. In that case the user must log in again and copy a fresh `sessionid`.

---

## 🪙 Token system

| Setting | Default | Meaning |
|---|---|---|
| Referral reward | `1` | Tokens earned per successful referral |
| Hide cost | `1` | Tokens spent per successful hide |
| Welcome bonus | `1` | Tokens given to every new user |

- A new user receives the welcome bonus on signup.
- The hide cost is reserved before the request and refunded if the hide fails.
- A referral is credited only after the invited user completes their **first successful hide**.
- Users with no tokens see a low-credit notice with a contact button.
- Admin accounts have **♾ unlimited** tokens.
- Settings can be changed anytime in **Admin → Token Settings**.

---

## 🛠 Admin panel

Open the bot and send `/admin` from an account listed in `ADMIN_IDS`.

- **📢 Required Chats** — users must join all listed chats.
  - The bot must be an **administrator** in each channel/group.
  - For private chats, grant the *Invite users* permission.
- **⚙️ Token Settings** — referral reward, hide cost, welcome bonus.
- **🎁 Redeem Items** — create and manage rewards.
- **🪙 Give Tokens** — add tokens or set an exact balance for any user.
- **⏳ Pending Redemptions** — complete manual deliveries.
- **🔄 Refresh** — reload the panel.

---

## 🚀 Local setup

### Requirements

- Python **3.12+**
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Your numeric Telegram user ID from [@userinfobot](https://t.me/userinfobot)

### Steps

```bash
git clone git@github.com:ekaivafu/Instagram-followers-hide.git
cd Instagram-followers-hide

python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

Create your `.env` from the example:

```bash
copy .env.example .env      # Windows
cp .env.example .env        # Linux/macOS
```

Edit `.env`:

```env
BOT_TOKEN=your-bot-token
ADMIN_IDS=your-telegram-user-id
SUPPORT_USERNAME=@your_username
```

Run:

```bash
python bot.py
```

On Windows you can also double-click **`run.bat`** — it creates `.venv`, installs dependencies the first time, and starts the bot.

Without webhook settings the bot uses **long polling** and stores data in `bot.db` (SQLite).

---

## ⚙️ Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `BOT_TOKEN` | ✅ | — | Telegram bot token |
| `ADMIN_IDS` | ❌ | empty | Comma-separated Telegram IDs allowed to use `/admin` |
| `SUPPORT_USERNAME` | ❌ | `@tgekaiva` | Contact shown in help and low-credit messages; empty hides the line |
| `DATABASE_URL` | ❌ | `sqlite+aiosqlite:///./bot.db` | SQLite locally; Postgres on Render |
| `WEBHOOK_URL` | ❌ | auto | Full webhook URL, e.g. `https://app.onrender.com/webhook` |
| `WEBHOOK_SECRET` | ❌ | empty | Secret token for webhook validation |
| `PORT` | ❌ | `8080` | HTTP port in webhook mode |

**Never commit `.env`.** It is already excluded by `.gitignore`.

---

## ☁️ Deploy on Render

### Option A — Blueprint (recommended)

1. Push the repository to GitHub.
2. In Render choose **New → Blueprint** and select the repo.
3. Render reads `render.yaml` and creates a free Postgres database.
4. Enter:
   - `BOT_TOKEN`
   - `ADMIN_IDS`
5. Deploy. Render sets `RENDER_EXTERNAL_URL` automatically, so the bot switches to webhook mode and exposes `/health`.

### Option B — Manual

1. Create a **Postgres** database (Render, Neon, Supabase, etc.).
2. Create a **Web Service**:
   - Build command: `pip install -r requirements.txt`
   - Start command: `python bot.py`
   - Health check path: `/health`
3. Add environment variables:
   - `BOT_TOKEN`
   - `ADMIN_IDS`
   - `DATABASE_URL`
   - `WEBHOOK_SECRET`
4. Deploy.

### Free-tier notes

- Free Render web services sleep after inactivity; the first update wakes them (cold start).
- Free Render Postgres databases expire after a limited period. For long-term use, use a paid database or an external provider.
- `postgres://` and `postgresql://` URLs are converted automatically. `sslmode=require` enables SSL.

---

## 📁 Project structure

```
bot.py                     entrypoint (polling or webhook)
app/
  config.py                environment settings
  db.py                    SQLAlchemy models and database setup
  instagram.py             Instagram hide request
  middlewares.py           database session + force-join gate
  membership.py            join verification and cache
  keyboards.py             inline keyboards
  services.py              registration, referrals, links
  states.py                FSM states
  handlers/
    base.py                /start, menu, profile, help
    hide.py                sessionid flow, token charge, referral credit
    referral.py            referrals and redeem shop (user side)
    admin.py               admin stats, chats, token settings, give tokens
    admin_items.py         redeem item management
    fallback.py            unknown messages and buttons
render.yaml                Render blueprint
run.bat                    Windows one-click launcher
requirements.txt           Python dependencies
```

---

## ❓ FAQ

**Does the bot store my session ID?**  
No. The message is deleted immediately, the value is used only in memory for one request, and it is never written to the database or logs.

**Does it unfollow people or remove followers?**  
No. It only toggles Instagram's "Hide followers and following" privacy setting.

**Why does my session ID fail?**  
It may be expired, require a verification challenge, or be blocked because of a new device/IP. Log in again and copy a fresh value.

**Can I get the session ID on mobile?**  
No. Use a PC or laptop browser and follow the steps in the bot's Hide menu.

**Do admins pay tokens?**  
No. Admin accounts have unlimited tokens and hide/redeem for free.

**Can I have multiple admins?**  
Yes. Add comma-separated IDs to `ADMIN_IDS`.

**How do I give a user tokens?**  
Admin panel → **🪙 Give Tokens** → enter the user ID → **➕ Add tokens** or **✏️ Set exact balance**.

---

## 🤝 Contributing

Issues and pull requests are welcome. Please:

- keep changes focused and readable,
- run `ruff check bot.py app --select F,E9` before opening a PR,
- never commit secrets, `.env`, or database files,
- follow the responsible-use disclaimer above.

---

## 📄 License

Released under the [MIT License](LICENSE).

Copyright © 2026 [ekaivafu](https://github.com/ekaivafu)

---

## 💬 Contact

- GitHub: [@ekaivafu](https://github.com/ekaivafu)
- Telegram support: configured with `SUPPORT_USERNAME` (default `@tgekaiva`)

If this project helped you, consider starring the repository.
