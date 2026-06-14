"""
Mental Pips Club — GOLD COT Telegram Bot
==========================================
Scrapes CFTC Futures-Only COT report for Gold (COMEX)
from https://www.cftc.gov/dea/futures/deacmxsf.htm
Parses Non-Commercial Long/Short positions and sends
a formatted weekly report to a Telegram chat.

GitHub Secrets required:
  - TELEGRAM_BOT_TOKEN
  - TELEGRAM_CHAT_ID
"""

import os
import sys
import logging
import re
from typing import Optional
import requests
from requests.adapters import HTTPAdapter, Retry

# ──────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────
TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

COT_URL = "https://www.cftc.gov/dea/futures/deacmxsf.htm"

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
def load_page() -> str:
    log.info("Fetching COT page: %s", COT_URL)
    try:
        r = SESSION.get(COT_URL, timeout=30)
        r.raise_for_status()
        return r.text
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not fetch COT page: {exc}") from exc

# ──────────────────────────────────────────────
# PARSING — extract Gold block from HTML/text
# ──────────────────────────────────────────────
def extract_gold_block(html: str) -> str:
    """Find the GOLD - COMMODITY EXCHANGE section."""
    # Strip HTML tags to get plain text
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text)

    # Find Gold section
    match = re.search(r"GOLD\s*[-–]\s*COMMODITY EXCHANGE INC\.(.+?)(?=\w+\s*[-–]\s*COMMODITY|\Z)", text, re.DOTALL | re.IGNORECASE)
    if not match:
        raise ValueError("Gold section not found. CFTC may have changed their format.")

    block = match.group(0)
    log.info("Gold block found (%d chars).", len(block))
    return block

def parse_report_date(block: str) -> str:
    m = re.search(r"AS OF\s+(\d{2}/\d{2}/\d{2,4})", block, re.IGNORECASE)
    return m.group(1) if m else "Unknown"

def extract_all_numbers(block: str) -> list[int]:
    """Extract all integers from the block."""
    raw = re.findall(r"-?[\d,]+", block)
    results = []
    for n in raw:
        try:
            results.append(int(n.replace(",", "")))
        except ValueError:
            continue
    return results

def parse_positions(block: str) -> dict:
    """
    Parse the COMMITMENTS row:
    NON-COMMERCIAL: LONG | SHORT | SPREADS
    COMMERCIAL:     LONG | SHORT
    TOTAL:          LONG | SHORT
    NONREPORTABLE:  LONG | SHORT

    Also parse CHANGES FROM row and OPEN INTEREST.
    """
    # Open interest
    oi_match = re.search(r"OPEN INTEREST[:\s]+([\d,]+)", block, re.IGNORECASE)
    open_interest = int(oi_match.group(1).replace(",", "")) if oi_match else 0

    # Get all number rows — COMMITMENTS row is the first big number group
    # Pattern: find COMMITMENTS section numbers
    commit_match = re.search(
        r"COMMITMENTS\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)",
        block, re.IGNORECASE
    )

    if not commit_match:
        raise ValueError("Could not parse COMMITMENTS row.")

    nums = [int(x.replace(",", "")) for x in commit_match.groups()]
    # Layout: NC_Long, NC_Short, NC_Spread, C_Long, C_Short, T_Long, T_Short, NR_Long, NR_Short
    nc_long   = nums[0]
    nc_short  = nums[1]
    nc_spread = nums[2]
    c_long    = nums[3]
    c_short   = nums[4]
    nr_long   = nums[7]
    nr_short  = nums[8]

    # CHANGES row
    change_match = re.search(
        r"CHANGES FROM[^(]+\([^)]+\)\s+(-?[\d,]+)\s+(-?[\d,]+)\s+(-?[\d,]+)\s+(-?[\d,]+)\s+(-?[\d,]+)",
        block, re.IGNORECASE
    )
    chg_nc_long  = 0
    chg_nc_short = 0
    if change_match:
        cg = [int(x.replace(",", "")) for x in change_match.groups()]
        chg_nc_long  = cg[0]
        chg_nc_short = cg[1]

    return {
        "open_interest": open_interest,
        "nc_long":       nc_long,
        "nc_short":      nc_short,
        "nc_spread":     nc_spread,
        "c_long":        c_long,
        "c_short":       c_short,
        "nr_long":       nr_long,
        "nr_short":      nr_short,
        "chg_nc_long":   chg_nc_long,
        "chg_nc_short":  chg_nc_short,
        "net":           nc_long - nc_short,
        "chg_net":       chg_nc_long - chg_nc_short,
    }

# ──────────────────────────────────────────────
# BIAS
# ──────────────────────────────────────────────
def get_bias(net: int, chg_net: int) -> tuple[str, str]:
    if net > 0 and chg_net > 0:
        return "🟢 BULLISH", "Net long & increasing"
    elif net > 0 and chg_net < 0:
        return "🟡 BULLISH BUT FADING", "Net long but reducing"
    elif net < 0 and chg_net < 0:
        return "🔴 BEARISH", "Net short & increasing"
    elif net < 0 and chg_net > 0:
        return "🟡 BEARISH BUT RECOVERING", "Net short but covering"
    else:
        return "🟡 NEUTRAL / MIXED", "No clear directional conviction"

def format_num(n: int) -> str:
    sign = "+" if n > 0 else ""
    return f"{sign}{n:,}"

# ──────────────────────────────────────────────
# MESSAGE BUILDER
# ──────────────────────────────────────────────
def build_message(p: dict, report_date: str) -> str:
    bias_label, bias_detail = get_bias(p["net"], p["chg_net"])

    total_nc = p["nc_long"] + p["nc_short"]
    long_pct  = (p["nc_long"]  / total_nc * 100) if total_nc else 50.0
    short_pct = (p["nc_short"] / total_nc * 100) if total_nc else 50.0

    arrow_net = "▲" if p["chg_net"] > 0 else ("▼" if p["chg_net"] < 0 else "—")
    arrow_l   = "▲" if p["chg_nc_long"]  > 0 else ("▼" if p["chg_nc_long"]  < 0 else "—")
    arrow_s   = "▲" if p["chg_nc_short"] > 0 else ("▼" if p["chg_nc_short"] < 0 else "—")

    return (
        f"📊 <b>Mental Pips Club — GOLD COT Report</b>\n"
        f"<i>COMEX Gold Futures Only | As of {report_date}</i>\n"
        f"{'─' * 32}\n\n"
        f"<b>Open Interest:</b> {p['open_interest']:,}\n\n"
        f"<b>Non-Commercial Positioning</b>\n"
        f"  🟩 Longs   : {p['nc_long']:>10,}  ({long_pct:.1f}%)  {arrow_l} {format_num(p['chg_nc_long'])}\n"
        f"  🟥 Shorts  : {p['nc_short']:>10,}  ({short_pct:.1f}%)  {arrow_s} {format_num(p['chg_nc_short'])}\n"
        f"  📊 Spreads : {p['nc_spread']:>10,}\n"
        f"  ⚖️ Net     : {format_num(p['net']):>10}  {arrow_net} {format_num(p['chg_net'])}\n\n"
        f"<b>Commercial</b>\n"
        f"  🟩 Longs   : {p['c_long']:>10,}\n"
        f"  🟥 Shorts  : {p['c_short']:>10,}\n\n"
        f"<b>Non-Reportable</b>\n"
        f"  🟩 Longs   : {p['nr_long']:>10,}\n"
        f"  🟥 Shorts  : {p['nr_short']:>10,}\n\n"
        f"{'─' * 32}\n"
        f"<b>BIAS: {bias_label}</b>\n"
        f"<i>{bias_detail}</i>\n"
        f"{'─' * 32}\n"
        f"<i>Source: CFTC Futures-Only COT Report</i>\n"
        f"<i>{COT_URL}</i>"
    )

# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
def run() -> None:
    log.info("=== COT Gold Bot starting ===")

    try:
        html = load_page()
    except RuntimeError as exc:
        send_error("Failed to fetch COT page.", exc)
        sys.exit(1)

    try:
        gold_block = extract_gold_block(html)
    except ValueError as exc:
        send_error("Failed to locate Gold section.", exc)
        sys.exit(1)

    try:
        report_date = parse_report_date(gold_block)
        positions   = parse_positions(gold_block)
    except Exception as exc:
        send_error("Failed to parse Gold positions.", exc)
        sys.exit(1)

    log.info("Parsed positions for date: %s", report_date)
    log.info("Net Non-Commercial: %s", format_num(positions["net"]))

    message = build_message(positions, report_date)

    log.info("Sending report to Telegram...")
    if not send(message):
        sys.exit(1)

    log.info("=== Done ===")


if __name__ == "__main__":
    run()
