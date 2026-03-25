# 🐣 WhatsApp Scavenger Hunt (Twilio + Flask)

![Python](https://img.shields.io/badge/python-3.10+-blue)
![Flask](https://img.shields.io/badge/flask-lightweight-black)
![Twilio](https://img.shields.io/badge/twilio-whatsapp-red)
![Status](https://img.shields.io/badge/status-event--ready-green)

A lightweight, event-ready scavenger hunt powered by **WhatsApp**, **Twilio Sandbox**, and **Flask**.

Participants interact entirely through WhatsApp — scanning QR codes or tapping NFC tags to progress through clues, receive images/videos, and complete the hunt.

---

## ✨ Features

- 📱 WhatsApp as the UI (no app install required)
- 🧩 Multiple experiences (JSON-driven)
- 🧠 Stateful progression per participant
- 🖼️ Image + 🎥 video support
- 🔐 QR + NFC checkpoint triggers
- 📊 Live admin dashboard
- ⏱️ Time tracking (start → finish)

---

## 🧱 Architecture

```
User (WhatsApp)
      ↓
Twilio Sandbox
      ↓
Flask Webhook (/webhook)
      ↓
Game Engine (JSON-driven)
      ↓
State (state.json)
      ↓
Media (GitHub Pages)
```

---

## 🚀 Quick Start (5 mins)

```bash
git clone https://github.com/YOUR_USERNAME/easter-hunt.git
cd easter-hunt
python3 -m venv .venv
source .venv/bin/activate
pip install flask twilio python-dotenv
```

Create `.env`:

```
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
```

Run app:

```bash
python app.py
```

Start ngrok:

```bash
ngrok http 5001 --host-header=rewrite
```

Set Twilio webhook:

```
https://YOUR-NGROK-URL/webhook
```

---

## 📲 Joining the Sandbox

Send:

join {sanbox-name}

e.g.

```
join day-numeral
```

Or scan:

`https://wa.me/{twilio_number}?text=join%20{sandbox-name}`

e.g.

https://wa.me/14155238886?text=join%20day-numeral

---

## 🎮 Starting an Experience

- Experience 1 → `Hi, I missed a call from this number`
- Experience 2 → `Hop to it`

---

## 🧩 Checkpoints (QR / NFC)

Each checkpoint sends:

```
FOUND-mane
```

Example NFC payload:

```
wa.me/14155238886?text=FOUND-mane
```

---

## 🗂️ Project Structure

```
app.py
state.json
experiences/
templates/
```

---

## 📊 Admin Dashboard

```
http://localhost:5001/admin
```

- View participants
- Track progress
- See timing
- Reset players

---

## 🎥 Media Hosting

```
https://YOUR_USERNAME.github.io/easter-hunt-assets/
```

- Images ≤ 5MB  
- Videos ≤ 16MB (aim < 8MB)

---

## ⚠️ Twilio Sandbox Limits

- ~50 messages/day  
- Rolling 24h window  
- Each user must join once  

---

## 🧪 Example Flow

1. Scan QR → joins WhatsApp
2. Send start phrase
3. Receive clue (image/video)
4. Find object → scan/tap
5. Repeat until finish
6. Final video + reward

---

## 🟢 Notes

- Do not commit `.env`
- Reset `state.json` before events
- Keep media small for reliability

---

## 🚀 Future Ideas

- Leaderboard (fastest time)
- Hint controls in dashboard
- Multi-game support
- Cloud deployment

---

Enjoy the hunt 🐰
