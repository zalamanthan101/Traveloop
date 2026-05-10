# 🌍 Traveloop – Full Python Web App

A complete travel planning platform built with **Flask + SQLite**, featuring an
amber-and-coral dark-theme UI with 10 fully functional screens.

---

## ✅ Features Implemented

| # | Screen | Status |
|---|--------|--------|
| 1 | Login / Signup | ✅ |
| 2 | Dashboard / Home | ✅ |
| 3 | Create Trip | ✅ |
| 4 | My Trips (list) | ✅ |
| 5 | Itinerary Builder | ✅ (drag-stop, add activities) |
| 6 | Itinerary View (timeline) | ✅ |
| 7 | City Search | ✅ (built into builder) |
| 8 | Activity Search/Add | ✅ (modal with types) |
| 9 | Budget & Cost Breakdown | ✅ (with Chart.js pie chart) |
| 10 | Packing Checklist | ✅ (with categories) |
| 11 | Shared / Public Itinerary | ✅ (/share/<id>) |
| 12 | User Profile | ✅ |
| 13 | Trip Notes / Journal | ✅ |

---

## 🚀 Step-by-Step Setup

### Step 1 – Prerequisites
Make sure Python 3.8+ is installed:
```
python --version
```

### Step 2 – Create a virtual environment (recommended)
```
python -m venv venv

# Windows:
venv\Scripts\activate

# Mac/Linux:
source venv/bin/activate
```

### Step 3 – Install dependencies
```
pip install -r requirements.txt
```
That's just one package: `flask`

### Step 4 – Run the app
```
python app.py
```
The server starts at: **http://localhost:5050**

### Step 5 – Open in browser
Navigate to: **http://localhost:5050**

### Step 6 – Log in with demo account
- **Email:** demo@traveloop.com
- **Password:** demo123

Or create a new account via Sign Up.

---

## 📁 Project Structure

```
traveloop/
├── app.py                  # Main Flask app (routes, DB, API)
├── requirements.txt        # Flask only
├── traveloop.db            # SQLite DB (auto-created on first run)
└── templates/
    ├── base.html           # Nav, design system, shared CSS
    ├── login.html          # Auth page (login + signup)
    ├── dashboard.html      # Home with stats & destinations
    ├── trips.html          # Trip list with actions
    ├── create_trip.html    # New trip form
    ├── builder.html        # Itinerary builder (cities + activities)
    ├── itinerary_view.html # Timeline view of itinerary
    ├── budget.html         # Budget breakdown + Chart.js pie
    ├── checklist.html      # Packing checklist with categories
    ├── notes.html          # Trip notes / journal
    ├── profile.html        # User profile settings
    └── public_view.html    # Shareable public itinerary page
```

---

## 🗄️ Database Schema

- **users** – id, name, email, password (SHA-256 hashed), photo
- **trips** – id, user_id, name, description, start/end dates, budget, is_public
- **stops** – id, trip_id, city, country, start/end dates, position
- **activities** – id, stop_id, name, type, cost, duration, description
- **checklist** – id, trip_id, item, category, packed
- **notes** – id, trip_id, stop_id, content, created_at

---

## 🌐 Key URLs

| URL | Description |
|-----|-------------|
| `/` | Login / Signup |
| `/dashboard` | Home dashboard |
| `/trips` | All my trips |
| `/trips/new` | Create trip |
| `/trips/<id>/builder` | Itinerary builder |
| `/trips/<id>/view` | Itinerary timeline |
| `/trips/<id>/budget` | Budget breakdown |
| `/trips/<id>/checklist` | Packing checklist |
| `/trips/<id>/notes` | Trip notes |
| `/share/<id>` | Public shareable page |
| `/profile` | User settings |

---

## 🎨 Design System

- **Font:** Playfair Display (headings) + DM Sans (body)
- **Theme:** Dark navy with amber + coral gradients
- **Colors:** `#1A1A2E` deep, `#E8A838` amber, `#E05C3A` coral, `#7BAF8F` sage
- **Components:** Cards with glassmorphism, animated buttons, timeline view
- **Charts:** Chart.js doughnut for budget breakdown

---

## 🔌 REST API Endpoints (for dynamic UI)

```
POST   /api/stops          – Add a city stop to a trip
DELETE /api/stops/<id>     – Remove a stop
POST   /api/activities     – Add activity to a stop
DELETE /api/activities/<id>– Remove activity
POST   /api/checklist/<id>/toggle – Toggle packed status
DELETE /api/checklist/<id> – Delete checklist item
DELETE /api/notes/<id>     – Delete a note
POST   /api/trips/<id>/toggle-public – Toggle public sharing
```
