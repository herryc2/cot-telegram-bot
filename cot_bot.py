"""
Mental Pips Club — GOLD COT Telegram Bot
=========================================
Fetches CFTC Disaggregated COT data, parses Managed Money
positions for Gold (COMEX), computes net positioning, weekly
change, trend, and sends a formatted report to a Telegram chat.

GitHub Secrets required:
  - TELEGRAM_BOT_TOKEN
  - TELEGRAM_CHAT_ID
"""

import os
import sys
import logging
import re
from datetime import datetime, timezone
from typing import Optional
import requests
from requests.adapters import HTTPAdapter, Retry

# ──────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────
TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ──────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# HTTP SESSION WITH RETRIES
# ──────────────────────────────────────────────
def _make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

SESSION = _make_session()

# ──────────────────────────────────────────────
# AUTO-DETECT CORRECT CFTC URL
# ──────────────────────────────────────────────
def get_cot_url() -> str:
    year = datetime.now(timezone.utc).year
    for y in [year, year - 1]:
        url = f"https://www.cftc.gov/dea/newcot/f_disagg_txt_{y}.txt"
        try:
            r = SESSION.head(url, timeout=10)
            if r.status_code == 200:
                log.info("Using COT URL: %s", url)
                return url
        except Exception:
            continue
    fallback = f"https://www.cftc.gov/dea/newcot/f_disagg_txt_{year - 1}.txt"
    log.warning("Could not verify URL, falling back to: %s", fallback)
    return fallback

# ──────────────────────────────────────────────
# TELEGRAM
# ──────────────────────────────────────────────
def send(text: str, parse_mode: str = "HTML") -> bool:
    if not TOKEN or not CHAT_ID:
        log.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set.")
        return False
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    try:
        r = SESSION.post(url, json=payload, timeout=15)
        r.raise_for_status()
        log.info("Telegram message sent successfully.")
        return True
    except requests.RequestException as exc:
        log.error("Failed to send Telegram message: %s", exc)
        return False

def send_error(context: str, exc: Optional[Exception] = None) -> None:
    detail = f"\n<code>{exc}</code>" if exc else ""
    send(f"⚠️ <b>COT Bot Error</b>\n{context}{detail}")

# ──────────────────────────────────────────────
# DATA LOADING
# ──────────────────────────────────────────────
def load_cot_data() -> list[str]:
    cot_url = get_cot_url()
    log.info("Fetching COT data from: %s", cot_url)
    try:
        r = SESSION.get(cot_url, timeout=30)
        r.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not download COT file: {exc}") from exc
    lines = r.text.split("\n")
    log.info("Downloaded %d lines.", len(lines))
    return lines

# ──────────────────────────────────────────────
# PARSING
# ──────────────────────────────────────────────
def extract_gold_block(lines: list[str]) -> list[str]:
    block: list[str] = []
    capturing = False
    for line in lines:
        upper = line.upper()
        if not capturing and "GOLD" in upper and "COMMODITY EXCHANGE" in upper:
            capturing = True
        if capturing:
            if block and "SILVER" in upper:
                break
            block.append(line)
    if not block:
        raise ValueError("Gold block not found in COT file. CFTC may have changed the format.")
    log.info("Gold block captured: %d lines.", len(block))
    return block

def _extract_numbers(line: str) -> list[int]:
    return [int(n.replace(",", "")) for n in re.findall(r"[\d,]+", line)]

def parse_managed_money(block: list[str]) -> tuple[list[int], list[int], list[str]]:
    longs:  list[int] = []
    shorts: list[int] = []
    dates:  list[str] = []

    date_pattern = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")
    current_date: str = ""

    for line in block:
        dm = date_pattern.search(line)
        if dm:
            current_date = dm.group(1)
        if "Managed Money" in line:
            nums = _extract_numbers(line)
            if len(nums) >= 2:
                longs.append(nums[0])
                shorts.append(nums[1])
                dates.append(current_date or "N/A")
                log.debug("MM row — date=%s long=%d short=%d", current_date, nums[0], nums[1])

    return longs, shorts, dates

# ──────────────────────────────────────────────
# ANALYSIS
# ──────────────────────────────────────────────
def compute_metrics(longs: list[int], shorts: list[int]) -> dict:
    nets = [l - s for l, s in zip(longs, shorts)]

    net_now  = nets[-1]
    net_prev = nets[-2] if len(nets) > 1 else net_now
    delta    = net_now - net_prev

    if len(nets) >= 5:
        trend_4w = sum(nets[i] - nets[i - 1] for i in range(-4, 0))
    elif len(nets) > 1:
        trend_4w = sum(nets[i] - nets[i - 1] for i in range(1, len(nets)))
    else:
        trend_4w = 0

    total     = longs[-1] + shorts[-1]
    long_pct  = (longs[-1]  / total * 100) if total else 50.0
    short_pct = (shorts[-1] / total * 100) if total else 50.0

    return {
        "net_now":   net_now,
        "net_prev":  net_prev,
        "delta":     delta,
        "trend_4w":  trend_4w,
        "long_now":  longs[-1],
        "short_now": shorts[-1],
        "long_pct":  long_pct,
        "short_pct": short_pct,
        "history":   nets,
    }

def get_bias(metrics: dict) -> tuple[str, str]:
    net   = metrics["net_now"]
    delta = metrics["delta"]
    trend = metrics["trend_4w"]

    if net > 0 and trend > 0 and delta > 0:
        return "🟢 STRONGLY BULLISH", "Net long & accelerating"
    elif net > 0 and trend > 0:
        return "🟢 BULLISH", "Net long & trending up"
    elif net > 0 and delta < 0:
        return "🟡 BULLISH BUT FADING", "Net long but reducing"
    elif net < 0 and trend < 0 and delta < 0:
        return "🔴 STRONGLY BEARISH", "Net short & accelerating"
    elif net < 0 and trend < 0:
        return "🔴 BEARISH", "Net short & trending down"
    elif net < 0 and delta > 0:
        return "🟡 BEARISH BUT RECOVERING", "Net short but covering"
    else:
        return "🟡 NEUTRAL / MIXED", "No clear directional conviction"

def mini_sparkline(nets: list[int], n: int = 6) -> str:
    bars = " ▁▂▃▄▅▆▇█"
    recent = nets[-n:]
    if len(recent) < 2:
        return ""
    lo, hi = min(recent), max(recent)
    spread = hi - lo or 1
    return "".join(bars[round((v - lo) / spread * (len(bars) - 1))] for v in recent)

def format_number(n: int) -> str:
    sign = "+" if n > 0 else ""
    return f"{sign}{n:,}"

# ──────────────────────────────────────────────
# MESSAGE BUILDER
# ──────────────────────────────────────────────
def build_message(metrics: dict, report_date: str) -> str:
    bias_label, bias_detail = get_bias(metrics)
    spark = mini_sparkline(metrics["history"])
    arrow_delta = "▲" if metrics["delta"] > 0 else ("▼" if metrics["delta"] < 0 else "—")
    arrow_trend = "▲" if metrics["trend_4w"] > 0 else ("▼" if metrics["trend_4w"] < 0 else "—")

    return (
        f"📊 <b>Mental Pips Club — GOLD COT Report</b>\n"
        f"<i>COMEX Gold Futures | Report Date: {report_date}</i>\n"
        f"{'─' * 32}\n\n"
        f"<b>Managed Money Positioning</b>\n"
        f"  🟩 Longs  : {metrics['long_now']:>12,}  ({metrics['long_pct']:.1f}%)\n"
        f"  🟥 Shorts : {metrics['short_now']:>12,}  ({metrics['short_pct']:.1f}%)\n"
        f"  ⚖️ Net    : {format_number(metrics['net_now']):>12}\n\n"
        f"<b>Weekly Change</b>  {arrow_delta} {format_number(metrics['delta'])}\n"
        f"<b>4-Week Trend</b>   {arrow_trend} {format_number(metrics['trend_4w'])}\n\n"
        f"<b>6-Week Net Trend</b>\n"
        f"  <code>{spark}</code>\n\n"
        f"{'─' * 32}\n"
        f"<b>BIAS: {bias_label}</b>\n"
        f"<i>{bias_detail}</i>\n"
        f"{'─' * 32}\n"
        f"<i>Source: CFTC Disaggregated COT</i>"
    )

# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
def run() -> None:
    log.info("=== COT Gold Bot starting ===")

    try:
        lines = load_cot_data()
    except RuntimeError as exc:
        send_error("Failed to download COT data.", exc)
        sys.exit(1)

    try:
        gold_block = extract_gold_block(lines)
    except ValueError as exc:
        send_error("Failed to locate Gold section.", exc)
        sys.exit(1)

    try:
        longs, shorts, dates = parse_managed_money(gold_block)
    except Exception as exc:
        send_error("Unexpected error during parsing.", exc)
        sys.exit(1)

    if not longs or not shorts:
        send_error(
            "No Managed Money rows found.\n"
            "The CFTC may have changed their file format."
        )
        sys.exit(1)

    log.info("Parsed %d weeks of data.", len(longs))

    metrics     = compute_metrics(longs, shorts)
    report_date = dates[-1] if dates else "Unknown"
    message     = build_message(metrics, report_date)

    log.info("Sending report to Telegram...")
    if not send(message):
        sys.exit(1)

    log.info("=== Done ===")


if __name__ == "__main__":
    run()
