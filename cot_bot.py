import requests

TOKEN = "Y8898099074:AAFk4I-Aczdif2mmYjuagQqBUdcs1_kc7UU"
CHAT_ID = "-1003835934177"

URL = "https://www.cftc.gov/dea/newcot/f_disagg_txt_2024.txt"

# -------------------------
# TELEGRAM SEND FUNCTION
# -------------------------
def send(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    r = requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    print(r.text)  # IMPORTANT debug for GitHub Actions logs

# -------------------------
# LOAD DATA
# -------------------------
def load_data():
    r = requests.get(URL, timeout=20)
    return r.text.split("\n")

# -------------------------
# FIND GOLD SECTION
# -------------------------
def extract_gold(lines):

    block = []
    capture = False

    for line in lines:

        # safer match
        if "GOLD" in line and "COMMODITY EXCHANGE" in line:
            capture = True

        if capture:
            block.append(line)

        # stop when next market appears
        if capture and "SILVER" in line:
            break

    return block

# -------------------------
# EXTRACT NUMBERS SAFELY
# -------------------------
def parse_mm(block):

    longs = []
    shorts = []

    for line in block:

        if "Managed Money" in line:

            nums = []
            temp = ""

            for c in line:
                if c.isdigit() or c == ",":
                    temp += c
                else:
                    if temp:
                        nums.append(int(temp.replace(",", "")))
                        temp = ""

            if temp:
                nums.append(int(temp.replace(",", "")))

            if len(nums) >= 2:
                longs.append(nums[-2])
                shorts.append(nums[-1])

    return longs, shorts

# -------------------------
# CALCULATION
# -------------------------
def compute(longs, shorts):

    net_series = [l - s for l, s in zip(longs, shorts)]

    net_now = net_series[-1]
    net_prev = net_series[-2] if len(net_series) > 1 else net_now

    delta = net_now - net_prev

    trend = sum([net_series[i] - net_series[i-1] for i in range(1, len(net_series))]) if len(net_series) > 1 else 0

    return net_now, delta, trend

# -------------------------
# BIAS
# -------------------------
def get_bias(net, trend):

    if net > 0 and trend > 0:
        return "🟢 BULLISH BIAS"
    elif net < 0 and trend < 0:
        return "🔴 BEARISH BIAS"
    else:
        return "🟡 NEUTRAL"

# -------------------------
# MAIN
# -------------------------
def run():

    try:
        lines = load_data()
        gold = extract_gold(lines)
        longs, shorts = parse_mm(gold)

        # DEBUG SAFETY
        if len(longs) == 0 or len(shorts) == 0:
            send("⚠️ COT parsing failed: no Managed Money data found\nCheck CFTC format update.")
            return

        net, delta, trend = compute(longs, shorts)
        bias = get_bias(net, trend)

        msg = f"""
📊 Mental Pips Club - GOLD COT REPORT

Net Position: {net}
Weekly Change: {delta}
Trend: {trend}

BIAS:
{bias}

Status: LIVE
"""

        send(msg)

    except Exception as e:
        send(f"⚠️ BOT ERROR:\n{str(e)}")

# -------------------------
# EXECUTE
# -------------------------
if __name__ == "__main__":
    run()
