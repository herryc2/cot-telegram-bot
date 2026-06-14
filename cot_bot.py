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

def get_data():
    text = requests.get(URL).text.split("\n")
    return text

def extract_gold_block(lines):
    """
    Extract only Gold COMEX section properly
    """
    capture = False
    gold_block = []

    for line in lines:
        if "GOLD - COMMODITY EXCHANGE INC." in line:
            capture = True

        if capture:
            gold_block.append(line)

        if capture and line.strip() == "":
            break

    return gold_block

def parse_numbers(block):
    """
    Extract numeric values from structured CFTC lines
    """

    longs = []
    shorts = []

    for line in block:
        if "Managed Money" in line:
            parts = line.split()

            nums = [p for p in parts if p.replace(",", "").isdigit()]

            if len(nums) >= 2:
                longs.append(int(nums[-2].replace(",", "")))
                shorts.append(int(nums[-1].replace(",", "")))

    return longs, shorts

def build_report():

    lines = get_data()
    gold_block = extract_gold_block(lines)

    longs, shorts = parse_numbers(gold_block)

    if not longs or not shorts:
        return "⚠️ Data parsing failed — CFTC format may have changed"

    net = longs[-1] - shorts[-1]

    delta = (net - (longs[-2] - shorts[-2])) if len(longs) > 1 else 0

    # Trend strength
    trend = sum([(longs[i] - shorts[i]) for i in range(len(longs))])

    # Bias logic
    score = net + delta + trend

    if score > 100000:
        bias = "🟢 STRONG BULLISH"
    elif score > 0:
        bias = "🟢 BULLISH"
    elif score < -100000:
        bias = "🔴 STRONG BEARISH"
    elif score < 0:
        bias = "🔴 BEARISH"
    else:
        bias = "🟡 NEUTRAL"

    msg = f"""
📊 Mental Pips Club - GOLD COT ENGINE v3

━━━━━━━━━━━━━━━━━━
🟡 REAL INSTITUTIONAL FLOW
━━━━━━━━━━━━━━━━━━

Net Position: {net}
Weekly Change: {delta}
Trend Score: {trend}

━━━━━━━━━━━━━━━━━━
📈 BIAS RESULT
━━━━━━━━━━━━━━━━━━

{bias}

Confidence Score: {min(100, abs(score)//10000)}

━━━━━━━━━━━━━━━━━━
🧠 INTERPRETATION
━━━━━━━━━━━━━━━━━━

- Based on Managed Money positioning
- Includes weekly momentum
- Includes multi-week trend pressure

━━━━━━━━━━━━━━━━━━
"""

    return msg

def main():
    send(build_report())

if __name__ == "__main__":
    main()
