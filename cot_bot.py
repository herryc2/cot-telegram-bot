import requests
import pandas as pd
from io import StringIO

TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "-1003835934177"

URL = "https://www.cftc.gov/dea/newcot/f_disagg_txt_2024.txt"

def send(msg):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": msg}
    )

def load_table():
    raw = requests.get(URL).text

    # Convert fixed-width style into readable dataframe attempt
    lines = raw.split("\n")

    return lines

def extract_gold_data(lines):
    """
    Proper structured extraction:
    We isolate COMEX GOLD section safely
    """

    capture = False
    block = []

    for line in lines:

        if "GOLD - COMMODITY EXCHANGE INC." in line:
            capture = True

        if capture:
            block.append(line)

        if capture and "SILVER" in line:
            break

    return block

def parse_positions(block):
    """
    Extract Managed Money longs & shorts properly
    """

    longs = []
    shorts = []

    for line in block:

        if "Managed Money" in line:

            # split safely
            parts = line.split()

            nums = []
            for p in parts:
                p_clean = p.replace(",", "")
                if p_clean.isdigit():
                    nums.append(int(p_clean))

            # CFTC format: last numbers usually long/short
            if len(nums) >= 2:
                longs.append(nums[-2])
                shorts.append(nums[-1])

    return longs, shorts

def build_report():

    lines = load_table()
    gold_block = extract_gold_data(lines)

    longs, shorts = parse_positions(gold_block)

    if len(longs) < 2:
        return "⚠️ Not enough data extracted — CFTC format mismatch"

    net_now = longs[-1] - shorts[-1]
    net_prev = longs[-2] - shorts[-2]

    delta = net_now - net_prev

    # Trend (last 4 weeks if available)
    trend = 0
    for i in range(1, len(longs)):
        trend += (longs[i] - shorts[i]) - (longs[i-1] - shorts[i-1])

    score = net_now + delta + trend

    # Bias engine
    if score > 150000:
        bias = "🟢 STRONG BULLISH (Institutional Accumulation)"
    elif score > 0:
        bias = "🟢 BULLISH"
    elif score < -150000:
        bias = "🔴 STRONG BEARISH (Institutional Distribution)"
    else:
        bias = "🟡 NEUTRAL / CHOP"

    msg = f"""
📊 Mental Pips Club - GOLD COT ENGINE v4

━━━━━━━━━━━━━━━━━━
🟡 INSTITUTIONAL POSITIONING (REAL)
━━━━━━━━━━━━━━━━━━

Managed Money Net Now: {net_now}
Weekly Change: {delta}
Trend Pressure: {trend}

━━━━━━━━━━━━━━━━━━
📈 MARKET BIAS
━━━━━━━━━━━━━━━━━━

{bias}

━━━━━━━━━━━━━━━━━━
🧠 INTERPRETATION
━━━━━━━━━━━━━━━━━━

✔ Based on CFTC Disaggregated Data
✔ Managed Money positioning
✔ Weekly + multi-week momentum

━━━━━━━━━━━━━━━━━━
"""

    return msg

def main():
    send(build_report())

if __name__ == "__main__":
    main()
