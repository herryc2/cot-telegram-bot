"""
Mental Pips Club — GOLD COT Telegram Bot
==========================================
Scrapes CFTC Futures-Only COT report for Gold (COMEX)
from https://www.cftc.gov/dea/futures/deacmxsf.htm
Sends a beautifully formatted weekly report to Telegram.

GitHub Secrets required:
  - TELEGRAM_BOT_TOKEN
  - TELEGRAM_CHAT_ID
"""

import os
import sys
import logging
import re
from typing import Optional
from datetime import datetime
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
# HTTP SESSION WITH RETRIES & BROWSER HEADERS
# ──────────────────────────────────────────────
def _make_session() -> requests.Session:
    session = requests.Session()
    # Adding modern browser headers to avoid HTTP 403 Forbidden from CFTC
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })
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
# PARSING & UTILS
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

def format_date(date_str: str) -> str:
    """Formats MM/DD/YY or MM/DD/YYYY to a beautiful long date (e.g. June 16, 2026)."""
    try:
        for fmt_pattern in ("%m/%d/%y", "%m/%d/%Y"):
            try:
                dt = datetime.strptime(date_str, fmt_pattern)
                return dt.strftime("%B %d, %Y")
            except ValueError:
                continue
        return date_str
    except Exception:
        return date_str

def parse_positions(block: str) -> dict:
    # 1. Parse Open Interest
    oi_match = re.search(r"OPEN INTEREST[:\s]+([\d,]+)", block, re.IGNORECASE)
    open_interest = int(oi_match.group(1).replace(",", "")) if oi_match else 0

    # 2. Parse Commitments (All 9 columns: NC Long/Short/Spread, C Long/Short, Total Long/Short, NR Long/Short)
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

    # 3. Parse Change in Open Interest & Weekly Changes row
    chg_oi = 0
    oi_chg_match = re.search(r"CHANGE IN OPEN INTEREST[:\s]+(-?[\d,]+)", block, re.IGNORECASE)
    if oi_chg_match:
        chg_oi = int(oi_chg_match.group(1).replace(",", ""))

    change_match = re.search(
        r"CHANGES FROM[^(]+\([^)]+\)\s+(-?[\d,]+)\s+(-?[\d,]+)\s+(-?[\d,]+)\s+(-?[\d,]+)\s+(-?[\d,]+)\s+(-?[\d,]+)\s+(-?[\d,]+)\s+(-?[\d,]+)\s+(-?[\d,]+)",
        block, re.IGNORECASE
    )
    
    chg_nc_long = chg_nc_short = chg_nc_spread = chg_c_long = chg_c_short = 0
    chg_nr_long = chg_nr_short = 0
    if change_match:
        cg = [int(x.replace(",", "")) for x in change_match.groups()]
        chg_nc_long, chg_nc_short, chg_nc_spread = cg[0], cg[1], cg[2]
        chg_c_long,  chg_c_short                 = cg[3], cg[4]
        chg_nr_long, chg_nr_short                 = cg[7], cg[8]
    else:
        # Fallback to older 5-column format if CFTC page layout differs
        fallback_chg = re.search(
            r"CHANGES FROM[^(]+\([^)]+\)\s+(-?[\d,]+)\s+(-?[\d,]+)\s+(-?[\d,]+)\s+(-?[\d,]+)\s+(-?[\d,]+)",
            block, re.IGNORECASE
        )
        if fallback_chg:
            cg = [int(x.replace(",", "")) for x in fallback_chg.groups()]
            chg_nc_long, chg_nc_short = cg[0], cg[1]
            chg_c_long,  chg_c_short  = cg[2], cg[3]

    # 4. Parse Percent of Open Interest (Fixed bug: removed colon requirement)
    pct_match = re.search(
        r"PERCENT OF OPEN INTEREST[^0-9\n]*\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)",
        block, re.IGNORECASE
    )
    pct_nc_long = pct_nc_short = pct_nc_spread = pct_c_long = pct_c_short = 0.0
    pct_nr_long = pct_nr_short = 0.0
    if pct_match:
        pg = [float(x) for x in pct_match.groups()]
        pct_nc_long, pct_nc_short, pct_nc_spread = pg[0], pg[1], pg[2]
        pct_c_long,  pct_c_short                 = pg[3], pg[4]
        pct_nr_long, pct_nr_short                 = pg[7], pg[8]
    else:
        fallback_pct = re.search(
            r"PERCENT OF OPEN INTEREST[^0-9\n]*\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)",
            block, re.IGNORECASE
        )
        if fallback_pct:
            pg = [float(x) for x in fallback_pct.groups()]
            pct_nc_long, pct_nc_short = pg[0], pg[1]
            pct_c_long,  pct_c_short  = pg[3], pg[4]

    # 5. Parse Number of Traders (7 columns)
    traders_match = re.search(
        r"NUMBER OF TRADERS[^0-9\n]*\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)",
        block, re.IGNORECASE
    )
    t_nc_long = t_nc_short = t_nc_spread = t_c_long = t_c_short = 0
    if traders_match:
        tg = [int(x.replace(",", "")) for x in traders_match.groups()]
        t_nc_long, t_nc_short, t_nc_spread = tg[0], tg[1], tg[2]
        t_c_long,  t_c_short               = tg[3], tg[4]
    else:
        fallback_traders = re.search(
            r"NUMBER OF TRADERS[^(]+\([^)]+\)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)",
            block, re.IGNORECASE
        )
        if fallback_traders:
            tg = [int(x.replace(",", "")) for x in fallback_traders.groups()]
            t_nc_long, t_nc_short = tg[0], tg[1]
            t_c_long,  t_c_short  = tg[3], tg[4]

    return {
        "open_interest": open_interest,
        "chg_oi": chg_oi,
        "nc_long":  nc_long,  "nc_short":  nc_short,  "nc_spread": nc_spread,
        "c_long":   c_long,   "c_short":   c_short,
        "nr_long":  nr_long,  "nr_short":  nr_short,
        "chg_nc_long": chg_nc_long, "chg_nc_short": chg_nc_short, "chg_nc_spread": chg_nc_spread,
        "chg_c_long":  chg_c_long,  "chg_c_short":  chg_c_short,
        "chg_nr_long": chg_nr_long, "chg_nr_short": chg_nr_short,
        "pct_nc_long": pct_nc_long, "pct_nc_short": pct_nc_short, "pct_nc_spread": pct_nc_spread,
        "pct_c_long":  pct_c_long,  "pct_c_short":  pct_c_short,
        "pct_nr_long": pct_nr_long, "pct_nr_short": pct_nr_short,
        "t_nc_long": t_nc_long, "t_nc_short": t_nc_short, "t_nc_spread": t_nc_spread,
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

def get_bias(net: int, chg_net: int) -> tuple[str, str]:
    abs_net = abs(net)
    chg_pct = (chg_net / abs_net * 100) if abs_net > 0 else 0
    
    if net > 0:
        if chg_net > 0:
            if chg_pct > 5:
                return "🟢 STRONGLY BULLISH", f"Speculators are net long ({fmt(net)}) and aggressively increasing positions (+{fmt(chg_net)} or +{chg_pct:.1f}% this week)."
            else:
                return "🟢 BULLISH", f"Speculators are net long ({fmt(net)}) and slightly increasing positions (+{fmt(chg_net)} this week)."
        else:
            if abs(chg_pct) > 5:
                return "🟡 BULLISH BUT FADING", f"Speculators are net long ({fmt(net)}) but significantly reducing exposure ({fmtc(chg_net)} or {chg_pct:.1f}% this week)."
            else:
                return "🟢 BULLISH (STABLE)", f"Speculators are net long ({fmt(net)}) with minor weekly change ({fmtc(chg_net)} this week)."
    else:
        if chg_net < 0:
            if abs(chg_pct) > 5:
                return "🔴 STRONGLY BEARISH", f"Speculators are net short ({fmt(net)}) and aggressively increasing short positions ({fmtc(chg_net)} or +{abs(chg_pct):.1f}% short this week)."
            else:
                return "🔴 BEARISH", f"Speculators are net short ({fmt(net)}) and slightly increasing short positions ({fmtc(chg_net)} this week)."
        else:
            if chg_pct > 5:
                return "🟡 BEARISH BUT COVERING", f"Speculators are net short ({fmt(net)}) but significantly covering shorts (+{fmt(chg_net)} or +{chg_pct:.1f}% this week)."
            else:
                return "🔴 BEARISH (STABLE)", f"Speculators are net short ({fmt(net)}) with minor weekly change (+{fmt(chg_net)} this week)."

def draw_ratio_bar(long_val: int, short_val: int) -> str:
    """Generates a beautiful green/red visual progress bar for Long vs Short ratio."""
    total = long_val + short_val
    if total == 0:
        return "[░░░░░░░░░░] 0%"
    ratio = long_val / total
    green_blocks = int(round(ratio * 10))
    red_blocks = 10 - green_blocks
    bar = "🟩" * green_blocks + "redo_blocks"
    # Replacing placeholder with emoji blocks:
    bar = "🟩" * green_blocks + "🟥" * red_blocks
    return f"{bar} {ratio * 100:.1f}% Long"

# ──────────────────────────────────────────────
# MESSAGE BUILDER — RICH TEXT FORMAT
# ──────────────────────────────────────────────
def build_message(p: dict, report_date: str) -> str:
    formatted_date = format_date(report_date)
    bias_label, bias_detail = get_bias(p["net"], p["chg_net"])
    
    # Speculators Long/Short ratio visual representation
    ratio_bar = draw_ratio_bar(p["nc_long"], p["nc_short"])
    
    # Calculate Net positions for other groups
    comm_net = p["c_long"] - p["c_short"]
    comm_chg_net = p["chg_c_long"] - p["chg_c_short"]
    
    retail_net = p["nr_long"] - p["nr_short"]
    retail_chg_net = p["chg_nr_long"] - p["chg_nr_short"]
    
    oi_change_str = f" ({fmtc(p['chg_oi'])})" if p["chg_oi"] != 0 else ""
    
    msg = (
        f"👑 <b>GOLD (COMEX) COT REPORT</b>\n"
        f"📅 <b>As of:</b> {formatted_date}\n"
        f"📈 <b>Open Interest:</b> {fmt(p['open_interest'])}{oi_change_str}\n"
        f"────────────────────\n\n"
        
        f"👥 <b>NON-COMMERCIAL (Speculators)</b>\n"
        f"<i>Smart money & trend followers</i>\n"
        f"🟢 <b>Longs:</b> {fmt(p['nc_long'])} <code>({fmtc(p['chg_nc_long'])} / {p['pct_nc_long']}%)</code>\n"
        f"🔴 <b>Shorts:</b> {fmt(p['nc_short'])} <code>({fmtc(p['chg_nc_short'])} / {p['pct_nc_short']}%)</code>\n"
        f"📊 <b>Spreads:</b> {fmt(p['nc_spread'])} <code>({fmtc(p['chg_nc_spread'])} / {p['pct_nc_spread']}%)</code>\n"
        f"⚖️ <b>Ratio:</b> {ratio_bar}\n"
        f"💼 <b>Net Pos:</b> <b>{fmtc(p['net'])}</b> <code>({fmtc(p['chg_net'])} wk)</code>\n\n"
        
        f"🏢 <b>COMMERCIALS (Hedgers)</b>\n"
        f"<i>Producers & institutional hedgers</i>\n"
        f"🟢 <b>Longs:</b> {fmt(p['c_long'])} <code>({fmtc(p['chg_c_long'])} / {p['pct_c_long']}%)</code>\n"
        f"🔴 <b>Shorts:</b> {fmt(p['c_short'])} <code>({fmtc(p['chg_c_short'])} / {p['pct_c_short']}%)</code>\n"
        f"💼 <b>Net Pos:</b> <b>{fmtc(comm_net)}</b> <code>({fmtc(comm_chg_net)} wk)</code>\n\n"
        
        f"👤 <b>NON-REPORTABLE (Retail)</b>\n"
        f"<i>Smaller participants</i>\n"
        f"🟢 <b>Longs:</b> {fmt(p['nr_long'])} <code>({fmtc(p['chg_nr_long'])} / {p['pct_nr_long']}%)</code>\n"
        f"🔴 <b>Shorts:</b> {fmt(p['nr_short'])} <code>({fmtc(p['chg_nr_short'])} / {p['pct_nr_short']}%)</code>\n"
        f"💼 <b>Net Pos:</b> <b>{fmtc(retail_net)}</b> <code>({fmtc(retail_chg_net)} wk)</code>\n\n"
        
        f"────────────────────\n"
        f"🎯 <b>SENTIMENT BIAS:</b> {bias_label}\n"
        f"<i>{bias_detail}</i>\n"
        f"────────────────────\n"
        f"<i>Source: CFTC Futures-Only COT</i>"
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
