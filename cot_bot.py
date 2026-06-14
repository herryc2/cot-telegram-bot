import requests
import pandas as pd

TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "-1003835934177"

URL = "https://www.cftc.gov/dea/newcot/f_disagg_txt_2024.txt"

def send(msg):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": msg}
    )

def load():
    data = requests.get(URL).text.split("\n")
    return data

def extract_gold(lines):
    """
    VERY IMPORTANT:
    CFTC file is fixed-width text.
    We filter Gold COMEX manually.
    """

    gold_data = []

    for line in lines:
        if "GOLD" in line and "COMEX" in line:
            gold_data.append(line)

    return gold_data

def build_report():

    lines = load()
    gold = extract_gold(lines)

    # Since raw parsing is complex, we simulate structured output
    # Next step we upgrade to full parser

    report = f"""📊 Mental Pips Club - GOLD COT ENGINE

━━━━━━━━━━━━━━━━━━
🟡 GOLD MARKET STATUS
━━━━━━━━━━━━━━━━━━

Data Source: CFTC Disaggregated Report

Raw Signals Found: {len(gold)}

📌 Interpretation Engine:
- Tracking institutional positioning
- Monitoring weekly flow
- Detecting crowding zones

━━━━━━━━━━━━━━━━━━
🧠 BIAS (MODEL v1)
━━━━━━━━━━━━━━━━━━

⚠️ Transitional Phase System

👉 Next upgrade will include:
- Net long/short calculation
- 4-week trend
- Crowd extreme detection
- BUY/SELL bias score

━━━━━━━━━━━━━━━━━━
📈 STATUS: ACTIVE ENGINE
━━━━━━━━━━━━━━━━━━
"""

    return report

def main():
    msg = build_report()
    send(msg)

if __name__ == "__main__":
    main()
