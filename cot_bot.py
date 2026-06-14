import requests
import pandas as pd
from io import StringIO

TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "-1003835934177"

URL = "https://www.cftc.gov/dea/newcot/deacot2024.txt"

def send(msg):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": msg}
    )

def load():
    raw = requests.get(URL).text
    return raw

def parse_table(raw):
    """
    Convert fixed width CFTC file into structured dataframe
    """

    lines = raw.split("\n")

    data = []

    for line in lines:
        if "GOLD" in line and "COMMODITY EXCHANGE INC" in line:

            parts = line.split()

            nums = [p.replace(",", "") for p in parts if p.replace(",", "").isdigit()]

            if len(nums) >= 4:
                data.append({
                    "long": int(nums[-2]),
                    "short": int(nums[-1])
                })

    return pd.DataFrame(data)

def build_signal(df):

    if len(df) < 2:
        return None

    df["net"] = df["long"] - df["short"]

    net_now = df["net"].iloc[-1]
    net_prev = df["net"].iloc[-2]

    delta = net_now - net_prev

    trend = df["net"].diff().rolling(3).mean().iloc[-1]

    # Z-score (simple normalization)
    z = (net_now - df["net"].mean()) / (df["net"].std() + 1e-9)

    score = net_now + delta + trend

    if z > 1.5:
        bias = "🔴 EXTREME LONG (Reversal Risk)"
    elif z < -1.5:
        bias = "🟢 EXTREME SHORT (Rebound Risk)"
    elif score > 0:
        bias = "🟢 BULLISH"
    else:
        bias = "🔴 BEARISH"

    return net_now, delta, trend, z, bias

def run():

    raw = load()
    df = parse_table(raw)

    result = build_signal(df)

    if not result:
        send("⚠️ COT parsing failed — data structure mismatch")
        return

    net, delta, trend, z, bias = result

    msg = f"""
📊 Mental Pips Club - GOLD COT ENGINE v5 (QUANT)

━━━━━━━━━━━━━━━━━━
🟡 INSTITUTIONAL FLOW
━━━━━━━━━━━━━━━━━━

Net Position: {net}
Weekly Change: {delta}
Trend Strength: {trend:.2f}
Z-Score: {z:.2f}

━━━━━━━━━━━━━━━━━━
📈 SIGNAL
━━━━━━━━━━━━━━━━━━

{bias}

━━━━━━━━━━━━━━━━━━
🧠 EDGE LOGIC
━━━━━━━━━━━━━━━━━━

✔ Real net positioning
✔ Momentum + trend
✔ Extreme detection (Z-score)

━━━━━━━━━━━━━━━━━━
"""

    send(msg)

if __name__ == "__main__":
    run()
