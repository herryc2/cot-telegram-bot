import sys
import os

# Add the scratch directory to sys.path so we can import the module
sys.path.append('/Users/herrychng/.gemini/antigravity/scratch/cot_bot')

from cot_bot import build_message

def test_build_message():
    # Mock data
    p = {
        "open_interest": 500000,
        "nc_long": 250000,
        "nc_short": 150000,
        "nc_spread": 50000,
        "c_long": 100000,
        "c_short": 200000,
        "nr_long": 20000,
        "nr_short": 10000,
        "chg_nc_long": 5000,
        "chg_nc_short": -2000,
        "chg_c_long": 1000,
        "chg_c_short": 500,
        "pct_nc_long": 50.0,
        "pct_nc_short": 30.0,
        "pct_c_long": 20.0,
        "pct_c_short": 40.0,
        "t_nc_long": 100,
        "t_nc_short": 80,
        "t_c_long": 50,
        "t_c_short": 120,
        "net": 100000,
        "chg_net": 7000,
    }
    report_date = "06/09/26"
    
    try:
        msg = build_message(p, report_date)
        print("Verification Successful! Message built without errors.")
        print("-" * 20)
        print(msg)
        print("-" * 20)
    except Exception as e:
        print(f"Verification Failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_build_message()
