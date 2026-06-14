import requests
import pandas as pd

TOKEN = "8898099074:AAFk4I-Aczdif2mmYjuagQqBUdcs1_kc7UU"
CHAT_ID = "-1003835934177"

URL = "https://www.cftc.gov/dea/newcot/deacot.txt"

# ---------------------------
# SEND MESSAGE TO TELEGRAM
# ---------------------------
def send(msg):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": msg}
    )

# ---------------------------
# LOAD DATA
# ---------------------------
def load_data():
    return requests.get(URL).text.split("\n")

# ---------------------------
# EXTRACT GOLD SECTION
# ---------------------------
def extract_gold(lines):
    capture = False
    block = []

    for line in lines:
        if "GOLD - COMMODITY EXCHANGE INC" in line:
            capture = True

        if capture:
            block.append(line)

        if capture and "SILVER" in line:
            break

    return block

# ---------------------------
# PARSE MANAGED MONEY DATA
# ---------------------------
def parse_mm(block):
    longs, shorts = [], []

    for line in block:
        if "Managed Money" in line:

            parts = line.split()
            nums = [p.replace(",", "") for p in parts if p.replace(",", "").isdigit()]

            if len(nums) >= 2:
                longs.append(int(nums[-2]))
                shorts.append(int(nums[-1]))

    return longs, shorts

# ---------------------------
# CALCULATIONS
# ---------------------------
def compute(longs, shorts):

    net = [l - s for l, s in zip(longs, shorts)]

    net_now = net[-1]
    net_prev = net[-2]

    delta = net_now - net_prev

    trend = sum([net[i] - net[i-1] for i in range(1, len(net))])

    mean = sum(net) / len(net)
    std = (sum([(x - mean) ** 2 for x in net]) / len(net)) ** 0.5

    z = (net_now - mean) / (std + 1e-9)

    return net_now, delta, trend, z

# ---------------------------
# BIAS LOGIC (OPTION A SIMPLE)
# ---------------------------
def get_bias(net, trend, z):

    if z > 1.5:
        return "🔴 EXTREME LONG (Watch for Pullback)"
    elif z < -1.5:
        return "🟢 EXTREME SHORT (Watch for Bounce)"
    elif net > 0 and trend > 0:
        return "🟢 BULLISH BIAS"
    elif net < 0 and trend < 0:
        return "🔴 BEARISH BIAS"
    else:
        return "🟡 NEUTRAL / NO CLEAR EDGE"

# ---------------------------
# MAIN REPORT
# ---------------------------
def run():

    lines = load_data()
    gold = extract_gold(lines)

    longs, shorts = parse_mm(gold)

    if len(longs) < 2:
        send("⚠️ COT data not available or format changed")
        return

    net, delta, trend, z = compute(longs, shorts)

    bias = get_bias(net, trend, z)

    msg = f"""
📊 Mental Pips Club - GOLD COT WEEKLY BIAS

━━━━━━━━━━━━━━━━━━
🟡 INSTITUTIONAL POSITIONING
━━━━━━━━━━━━━━━━━━

Net Position: {net}
Weekly Change: {delta}
Trend Strength: {trend}
Z-Score: {round(z, 2)}

━━━━━━━━━━━━━━━━━━
📈 BIAS VIEW (NOT TRADE SIGNAL)
━━━━━━━━━━━━━━━━━━

{bias}

━━━━━━━━━━━━━━━━━━
🧠 HOW TO USE
━━━━━━━━━━━━━━━━━━

- Use this as weekly direction filter
- Combine with price action
- Do NOT enter blindly

━━━━━━━━━━━━━━━━━━
"""

    send(msg)

# ---------------------------
# EXECUTE
# ---------------------------
if __name__ == "__main__":
    run()
