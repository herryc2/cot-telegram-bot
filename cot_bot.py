import requests
import pandas as pd

TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "-1003835934177"

URL = "https://www.cftc.gov/dea/newcot/deacot.txt"

def send(msg):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": msg}
    )

def load_data():
    return requests.get(URL).text.split("\n")

def extract_gold(lines):
    """
    Clean extraction: isolate Gold COMEX block
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

def parse_managed_money(block):
    """
    Extract ONLY Managed Money Long/Short correctly
    """

    longs = []
    shorts = []

    for line in block:

        if "Managed Money" in line:

            parts = line.split()

            nums = []
            for p in parts:
                p_clean = p.replace(",", "")
                if p_clean.isdigit():
                    nums.append(int(p_clean))

            if len(nums) >= 2:
                longs.append(nums[-2])
                shorts.append(nums[-1])

    return longs, shorts

def compute(longs, shorts):

    net_series = [l - s for l, s in zip(longs, shorts)]

    net_now = net_series[-1]
    net_prev = net_series[-2]

    delta = net_now - net_prev

    # 4-week momentum
    trend = 0
    for i in range(1, len(net_series)):
        trend += net_series[i] - net_series[i-1]

    # Z-score
    mean = sum(net_series) / len(net_series)
    std = (sum([(x - mean) ** 2 for x in net_series]) / len(net_series)) ** 0.5

    z = (net_now - mean) / (std + 1e-9)

    return net_now, delta, trend, z

def bias(z, net_now, trend):

    if z > 1.5:
        return "🔴 EXTREME LONG (Reversal Risk)"
    if z < -1.5:
        return "🟢 EXTREME SHORT (Rebound Risk)"
    if net_now > 0 and trend > 0:
        return "🟢 STRONG BULLISH"
    if net_now < 0 and trend < 0:
        return "🔴 STRONG BEARISH"
    if net_now > 0:
        return "🟢 BULLISH"
    if net_now < 0:
        return "🔴 BEARISH"
    return "🟡 NEUTRAL"

def run():

    lines = load_data()
    gold_block = extract_gold(lines)

    longs, shorts = parse_managed_money(gold_block)

    if len(longs) < 2:
        send("⚠️ COT data parsing failed — check CFTC format")
        return

    net, delta, trend, z = compute(longs, shorts)

    signal = bias(z, net, trend)

    msg = f"""
📊 Mental Pips Club - GOLD COT ENGINE (FINAL)

━━━━━━━━━━━━━━━━━━
🟡 INSTITUTIONAL POSITIONING
━━━━━━━━━━━━━━━━━━

Net Position: {net}
Weekly Change: {delta}
Trend Strength: {trend}
Z-Score: {round(z,2)}

━━━━━━━━━━━━━━━━━━
📈 MARKET BIAS
━━━━━━━━━━━━━━━━━━

{signal}

━━━━━━━━━━━━━━━━━━
🧠 NOTES
━━━━━━━━━━━━━━━━━━

✔ Managed Money positioning
✔ Weekly momentum
✔ 4-week trend analysis
✔ Extreme detection model

━━━━━━━━━━━━━━━━━━
"""

    send(msg)

if __name__ == "__main__":
    run()
