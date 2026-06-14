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

def load_data():
    # CFTC file is fixed-width, not CSV → we read raw
    r = requests.get(URL)
    lines = r.text.split("\n")
    return lines

def build_report():
    lines = load_data()

    # We are not fully parsing everything yet (next upgrade step)
    report = f"""📊 Mental Pips Club - Weekly COT Bot

Status: ✅ Running
Data Source: CFTC Disaggregated Report

Next Upgrade:
- Gold / EUR / JPY extraction
- Net positioning calculation
- Bullish/Bearish scoring engine
"""

    return report

def main():
    msg = build_report()
    send(msg)

if __name__ == "__main__":
    main()
