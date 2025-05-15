from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import os
from dotenv import load_dotenv
import yfinance as yf
from datetime import datetime, timedelta

# Create the app instance
app = FastAPI()

# Load environment variables
load_dotenv(dotenv_path="env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("❌ Missing Supabase credentials. Check your env file.")

# Root route (to confirm app is live)
@app.get("/")
def root():
    return {"status": "Backend is live"}

# Alert input model
class AlertIn(BaseModel):
    email: str
    ticker: str
    rsi_min: float
    rsi_max: float
    macd_min: float
    macd_max: float

@app.post("/submit_alert")
def submit_alert(alert: AlertIn):
    try:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/users?email=eq.{alert.email}",
            headers=headers
        )

        users = r.json()
        user_id = users[0]["id"] if users else None

        if not user_id:
            r = requests.post(
                f"{SUPABASE_URL}/rest/v1/users",
                headers=headers,
                json={"email": alert.email}
            )
            user_id = r.json()[0]["id"]

        payload = {
            "user_id": user_id,
            "ticker": alert.ticker,
            "rsi_min": alert.rsi_min,
            "rsi_max": alert.rsi_max,
            "macd_min": alert.macd_min,
            "macd_max": alert.macd_max
        }

        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/alerts",
            headers=headers,
            json=payload
        )

        if r.status_code not in (200, 201):
            raise HTTPException(status_code=400, detail="Failed to submit alert.")

        return {"status": "Alert submitted"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/query_setups")
def query_setups():
    try:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }

        r = requests.get(f"{SUPABASE_URL}/rest/v1/alerts", headers=headers)
        alerts = r.json()

        matches = []

        for alert in alerts:
            ticker = alert["ticker"]
            try:
                df = yf.download(ticker, period="7d", interval="1h", progress=False)
                if df.empty:
                    continue

                delta = df["Close"].diff()
                gain = delta.clip(lower=0).rolling(window=14).mean()
                loss = -delta.clip(upper=0).rolling(window=14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                latest_rsi = float(rsi.iloc[-1].item()) if not rsi.empty else None

                ema12 = df["Close"].ewm(span=12, adjust=False).mean()
                ema26 = df["Close"].ewm(span=26, adjust=False).mean()
                macd = ema12 - ema26
                latest_macd = float(macd.iloc[-1].item()) if not macd.empty else None

                if latest_rsi is None or latest_macd is None:
                    continue

                if (
                    alert["rsi_min"] <= latest_rsi <= alert["rsi_max"] and
                    alert["macd_min"] <= latest_macd <= alert["macd_max"]
                ):
                    matches.append({
                        "ticker": ticker,
                        "rsi": round(latest_rsi, 2),
                        "macd": round(latest_macd, 2),
                        "user_id": alert["user_id"]
                    })

            except Exception:
                continue

        return {"matches": matches}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
