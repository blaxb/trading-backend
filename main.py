from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import os
from dotenv import load_dotenv
import yfinance as yf
from datetime import datetime, timedelta

# Load environment variables from your env file
load_dotenv(dotenv_path="env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("❌ Missing Supabase credentials. Check your env file.")

app = FastAPI()

# Data model for alert input
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

        # Step 1: Check if user exists
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/users?email=eq.{alert.email}",
            headers=headers
        )

        print("\n===== USER LOOKUP RESPONSE =====")
        print("STATUS CODE:", r.status_code)
        print("RESPONSE TEXT:", r.text)
        print("=================================\n")

        try:
            users = r.json()
        except Exception:
            print("❌ Could not parse JSON from user lookup.")
            raise HTTPException(status_code=500, detail="Invalid response from Supabase user lookup.")

        if users:
            user_id = users[0]['id']
        else:
            # Step 2: Create user
            r = requests.post(
                f"{SUPABASE_URL}/rest/v1/users",
                headers=headers,
                json={"email": alert.email}
            )

            print("\n===== SUPABASE RESPONSE DEBUG =====")
            print("CREATE USER STATUS:", r.status_code)
            print("RESPONSE TEXT:", r.text)
            print("===================================\n")

            if r.status_code not in (200, 201):
                raise HTTPException(status_code=500, detail=f"User creation failed: {r.text}")

            try:
                user_id = r.json()[0]['id']
            except Exception:
                print("⚠️  Could not parse user ID from Supabase response.")
                print("Raw JSON:", r.json())
                raise HTTPException(status_code=500, detail="Supabase response format was invalid.")

        # Step 3: Create alert
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
            print("ALERT CREATION FAILED:", r.status_code, r.text)
            raise HTTPException(status_code=400, detail="Failed to submit alert.")

        return {
            "status": "Alert submitted successfully",
            "email": alert.email,
            "ticker": alert.ticker
        }

    except Exception as e:
        print("🔥 FINAL ERROR:", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/query_setups")
def query_setups():
    try:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }

        # Step 1: Get all alerts
        r = requests.get(f"{SUPABASE_URL}/rest/v1/alerts", headers=headers)
        alerts = r.json()

        matches = []

        for alert in alerts:
            ticker = alert["ticker"]
            try:
                # Step 2: Get recent 1h price data
                df = yf.download(ticker, period="7d", interval="1h", progress=False)

                if df.empty:
                    continue

                # Step 3: RSI calculation
                delta = df["Close"].diff()
                gain = delta.clip(lower=0).rolling(window=14).mean()
                loss = -delta.clip(upper=0).rolling(window=14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                latest_rsi = float(rsi.iloc[-1]) if not rsi.empty else None

                # Step 4: MACD calculation
                ema12 = df["Close"].ewm(span=12, adjust=False).mean()
                ema26 = df["Close"].ewm(span=26, adjust=False).mean()
                macd = ema12 - ema26
                latest_macd = float(macd.iloc[-1]) if not macd.empty else None

                # Step 5: Filter match check
                if latest_rsi is None or latest_macd is None:
                    continue

                rsi_ok = alert["rsi_min"] <= latest_rsi <= alert["rsi_max"]
                macd_ok = alert["macd_min"] <= latest_macd <= alert["macd_max"]

                if rsi_ok and macd_ok:
                    matches.append({
                        "ticker": ticker,
                        "rsi": round(latest_rsi, 2),
                        "macd": round(latest_macd, 2),
                        "user_id": alert["user_id"]
                    })

            except Exception as e:
                print(f"⚠️ Error checking {ticker}: {e}")
                continue

        return {"matches": matches}

    except Exception as e:
        print("🔥 FINAL ERROR IN query_setups:", e)
        raise HTTPException(status_code=500, detail=str(e))
