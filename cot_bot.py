"""
Mental Pips Club — GOLD COT Telegram Bot
==========================================
Scrapes CFTC Futures-Only COT report for Gold (COMEX)
from https://www.cftc.gov/dea/futures/deacmxsf.htm
Sends a table-formatted weekly report to Telegram.

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
# PARSING
# ──────────────────────────────────────────────
def extract_gold_block(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text)
    match = re.search(
        r"GOLD\s*[-–]\s*COMMODITY EXCHANGE INC\.(.+?)(?=\w+\s*[-–]\s*COMMODITY|\Z)",
        text, re.DOTALL | re.IGNORECASE
    )
    if not match:
        raise ValueError("Gold section not found.")
    block = match.group(0)
    log.info("Gold block found (%d chars).", len(block))
    return block

def parse_report_date(block: str) -> str:
    m = re.search(r"AS OF\s+(\d{2}/\d{2}/\d{2,4})", block, re.IGNORECASE)
    return m.group(1) if m else "Unknown"

def parse_positions(block: str) -> dict:
    oi_match = re.search(r"OPEN INTEREST[:\s]+([\d,]+)", block, re.IGNORECASE)
    open_interest = int(oi_match.group(1).replace(",", "")) if oi_match else 0

    commit_match = re.search(
        r"COMMITMENTS\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)",
        block, re.IGNORECASE
    )
    if not commit_match:
        raise ValueError("Could not parse COMMITMENTS row.")

    nums = [int(x.replace(",", "")) for x in commit_match.groups()]
    nc_long, nc_short, nc_spread = nums[0], nums[1], nums[2]
    c_long,  c_short             = nums[3], nums[4]
    nr_long, nr_short            = nums[7], nums[8]

    change_match = re.search(
        r"CHANGES FROM[^(]+\([^)]+\)\s+(-?[\d,]+)\s+(-?[\d,]+)\s+(-?[\d,]+)\s+(-?[\d,]+)\s+(-?[\d,]+)",
        block, re.IGNORECASE
    )
    chg_nc_long = chg_nc_short = chg_c_long = chg_c_short = 0
    if change_match:
        cg = [int(x.replace(",", "")) for x in change_match.groups()]
        chg_nc_long, chg_nc_short = cg[0], cg[1]
        chg_c_long,  chg_c_short  = cg[2], cg[3]

    # Percent of OI
    pct_match = re.search(
        r"PERCENT OF OPEN INTEREST[^:]*:\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)",
        block, re.IGNORECASE
    )
    pct_nc_long = pct_nc_short = pct_c_long = pct_c_short = 0.0
    if pct_match:
        pg = [float(x) for x in pct_match.groups()]
        pct_nc_long, pct_nc_short = pg[0], pg[1]
        pct_c_long,  pct_c_short  = pg[3], pg[4]

    # Traders count
    traders_match = re.search(
        r"NUMBER OF TRADERS[^(]+\([^)]+\)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)",
        block, re.IGNORECASE
    )
    t_nc_long = t_nc_short = t_c_long = t_c_short = 0
    if traders_match:
        tg = [int(x.replace(",", "")) for x in traders_match.groups()]
        t_nc_long, t_nc_short = tg[0], tg[1]
        t_c_long,  t_c_short  = tg[3], tg[4]

    return {
        "open_interest": open_interest,
        "nc_long":  nc_long,  "nc_short":  nc_short,  "nc_spread": nc_spread,
        "c_long":   c_long,   "c_short":   c_short,
        "nr_long":  nr_long,  "nr_short":  nr_short,
        "chg_nc_long": chg_nc_long, "chg_nc_short": chg_nc_short,
        "chg_c_long":  chg_c_long,  "chg_c_short":  chg_c_short,
        "pct_nc_long": pct_nc_long, "pct_nc_short": pct_nc_short,
        "pct_c_long":  pct_c_long,  "pct_c_short":  pct_c_short,
        "t_nc_long": t_nc_long, "t_nc_short": t_nc_short,
        "t_c_long":  t_c_long,  "t_c_short":  t_c_short,
        "net":     nc_long - nc_short,
        "chg_net": chg_nc_long - chg_nc_short,
    }

# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────
def fmt(n: int) -> str:
    return f"{n:,}"

def fmtc(n: int) -> str:
    return f"+{n:,}" if n > 0 else f"{n:,}"

def arrow(n: int) -> str:
    return "▲" if n > 0 else ("▼" if n < 0 else "─")

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
        return "🟡 NEUTRAL / MIXED", "No clear conviction"

# ──────────────────────────────────────────────
# MESSAGE BUILDER — TABLE FORMAT
# ──────────────────────────────────────────────
def build_message(p: dict, report_date: str) -> str:
    bias_label, bias_detail = get_bias(p["net"], p["chg_net"])

    # Column widths
    C0, C1, C2 = 16, 12, 12
    # div = "─" * (C0 + C1 + C2 + 4) # Unused

    def row(label, long_val, short_val):
        return f"│{label:<{C0}}│{long_val:>{C1}}│{short_val:>{C2}}│"

    table = "\n".join([
        f"┌{'─'*C0}┬{'─'*C1}┬{'─'*C2}┐",
        f"│{'':^{C0}}│{'LONG':^{C1}}│{'SHORT':^{C2}}│",
        f"├{'─'*C0}┼{'─'*C1}┼{'─'*C2}┤",
        row("NON-COMMERCIAL", fmt(p["nc_long"]), fmt(p["nc_short"])),
        row("  Spreads", fmt(p["nc_spread"]), ""),
        f"├{'─'*C0}┼{'─'*C1}┼{'─'*C2}┤",
        row("COMMERCIAL", fmt(p["c_long"]), fmt(p["c_short"])),
        f"├{'─'*C0}┼{'─'*C1}┼{'─'*C2}┤",
        row("NON-REPORTABLE", fmt(p["nr_long"]), fmt(p["nr_short"])),
        f"└{'─'*C0}┴{'─'*C1}┴{'─'*C2}┘",
    ])

    changes = "\n".join([
        f"┌{'─'*C0}┬{'─'*C1}┬{'─'*C2}┐",
        f"│{'WEEKLY CHANGE':^{C0+C1+C2+2}}│",
        f"├{'─'*C0}┼{'─'*C1}┼{'─'*C2}┤",
        row("NON-COMMERCIAL", fmtc(p["chg_nc_long"]), fmtc(p["chg_nc_short"])),
        row("  Net Change", fmtc(p["chg_net"]), ""),
        f"└{'─'*C0}┴{'─'*C1}┴{'─'*C2}┘",
    ])

    pct = "\n".join([
        f"┌{'─'*C0}┬{'─'*C1}┬{'─'*C2}┐",
        f"│{'% OF OPEN INT.':^{C0+C1+C2+2}}│",
        f"├{'─'*C0}┼{'─'*C1}┼{'─'*C2}┤",
        row("NON-COMMERCIAL", f"{p['pct_nc_long']}%", f"{p['pct_nc_short']}%"),
        row("COMMERCIAL", f"{p['pct_c_long']}%", f"{p['pct_c_short']}%"),
        f"└{'─'*C0}┴{'─'*C1}┴{'─'*C2}┘",
    ])

    traders = "\n".join([
        f"┌{'─'*C0}┬{'─'*C1}┬{'─'*C2}┐",
        f"│{'NO. OF TRADERS':^{C0+C1+C2+2}}│",
        f"├{'─'*C0}┼{'─'*C1}┼{'─'*C2}┤",
        row("NON-COMMERCIAL", fmt(p["t_nc_long"]), fmt(p["t_nc_short"])),
        row("COMMERCIAL", fmt(p["t_c_long"]), fmt(p["t_c_short"])),
        f"└{'─'*C0}┴{'─'*C1}┴{'─'*C2}┘",
    ])

    msg = (
        f"📊 <b>Mental Pips Club — GOLD COT</b>\n"
        f"<i>COMEX Futures Only | As of {report_date}</i>\n"
        f"<i>Open Interest: {fmt(p['open_interest'])} contracts</i>\n\n"
        f"<pre>{table}</pre>\n"
        f"<pre>{changes}</pre>\n"
        f"<pre>{pct}</pre>\n"
        f"<pre>{traders}</pre>\n"
        f"{'─'*32}\n"
        f"<b>NET (Non-Comm):</b> {fmtc(p['net'])}  {arrow(p['chg_net'])} {fmtc(p['chg_net'])} wk\n"
        f"<b>BIAS: {bias_label}</b>\n"
        f"<i>{bias_detail}</i>\n"
        f"{'─'*32}\n"
        f"<i>src: CFTC Futures-Only COT</i>"
    )
    return msg

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

    log.info("Report date: %s | Net: %s", report_date, fmtc(positions["net"]))

    message = build_message(positions, report_date)

    log.info("Sending report to Telegram...")
    if not send(message):
        sys.exit(1)

    log.info("=== Done ===")


if __name__ == "__main__":
    run()
