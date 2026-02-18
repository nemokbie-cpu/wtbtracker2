import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import re

st.set_page_config(page_title="WTB Tracker", layout="wide", page_icon="👟")
st.title("👟 WTB Tracker – Manual Analysis")

# ─── PAYOUT & ROI LOGIC ──────────────────────────────────────────
def calculate_net(price):
    if price < 57:
        return round(price - 4.5 - (price * 0.03) - 4.00, 2)
    else:
        return round(price - (price * 0.08) - (price * 0.03) - 4.00, 2)

def get_target_roi(est_days):
    if est_days < 5:
        return 0.30
    elif 6 <= est_days <= 25:
        return 0.35
    else:
        return 0.40

def analyze_sales(raw_text, listed_price, highest_bid):
    prices = []
    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
    cutoff = datetime.now() - timedelta(days=120)
    i = 0
    while i < len(lines):
        line = lines[i]
        date_match = re.search(r'(\d{2}/\d{2}/\d{2})', line)
        if date_match:
            try:
                date = datetime.strptime(date_match.group(1), '%m/%d/%y')
                if date > datetime.now():
                    date = date.replace(year=date.year - 100)
                i += 1
                while i < len(lines):
                    price_match = re.search(r'£\s*([\d,]+)', lines[i])
                    if price_match:
                        price = float(price_match.group(1).replace(',', ''))
                        if date >= cutoff:
                            prices.append(price)
                        break
                    i += 1
                continue
            except:
                pass
        i += 1

    if not prices:
        return None, "No valid sales in last 120 days."

    n = len(prices)
    avg_sale = sum(prices) / n
    avg_net = sum(calculate_net(p) for p in prices) / n
    est_days = 120 / n if n > 0 else 999
    roi_target = get_target_roi(est_days)
    rec_price = round(avg_net / (1 + roi_target), 2) if avg_net > 0 else 0
    roi_pct = round((avg_net - listed_price) / listed_price * 100, 1) if listed_price > 0 else 0

    payout_on_bid = round(calculate_net(highest_bid), 2) if highest_bid > 0 else 0
    rec_on_bid = round(payout_on_bid / 1.30, 2) if payout_on_bid > 0 else 0

    return {
        "SKU": sku,
        "Brand": brand,
        "Model": model,
        "Colorway": colorway,
        "Size": size,
        "Listed Price": listed_price,
        "Platform": platform,
        "Priority": priority,
        "#Sales 120D": n,
        "Avg Sale £": round(avg_sale, 2),
        "Avg Payout £": round(avg_net, 2),
        "ROI %": roi_pct,
        "Highest Bid": highest_bid,
        "Payout on Highest Bid": payout_on_bid,
        "Recommended Pay £": rec_price,
        "Recommended ROI %": f"{roi_target*100:.0f}%",
        "Rec on Highest Bid (30%)": rec_on_bid,
        "Est Days to Sell": round(est_days, 1)
    }, None

# ─── SESSION STATE ───────────────────────────────────────────────
platforms = ["Vinted", "eBay", "Other/Retail"]
if "tables" not in st.session_state:
    st.session_state.tables = {}
    for p in platforms:
        st.session_state.tables[p] = pd.DataFrame(columns=[
            "SKU", "Brand", "Model", "Colorway", "Size", "Listed Price", "Platform", "Priority",
            "#Sales 120D", "Avg Sale £", "Avg Payout £", "ROI %", "Highest Bid", "Payout on Highest Bid",
            "Recommended Pay £", "Recommended ROI %", "Rec on Highest Bid (30%)", "Est Days to Sell"
        ])

# ─── ENTRY FORM ──────────────────────────────────────────────────
with st.expander("➕ Add New WTB Entry", expanded=True):
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        sku = st.text_input("SKU")
        size = st.text_input("UK Size")
    with col2:
        brand = st.text_input("Brand")
        model = st.text_input("Model")
        colorway = st.text_input("Colorway")
    with col3:
        platform = st.selectbox("Platform", platforms)
        listed_price = st.number_input("Listed Price (£)", min_value=0.0, value=0.0)
        highest_bid = st.number_input("Highest Bid (£) – optional", min_value=0.0, value=0.0)
    with col4:
        priority = st.selectbox("Priority", ["High (Red)", "Medium (Yellow)", "Low (Green)"])
        raw_sales = st.text_area("Paste Raw StockX Sales Data (required for calculations)", height=140)

    if st.button("Analyze & Add to Table"):
        if sku and size and raw_sales:
            row, err = analyze_sales(raw_sales, listed_price, highest_bid)
            if err:
                st.error(err)
            else:
                row["SKU"] = sku
                row["Brand"] = brand or "Manual"
                row["Model"] = model or "Manual"
                row["Colorway"] = colorway or "Manual"
                row["Size"] = size
                row["Listed Price"] = listed_price
                row["Platform"] = platform
                row["Priority"] = priority
                st.session_state.tables[platform] = pd.concat(
                    [st.session_state.tables[platform], pd.DataFrame([row])],
                    ignore_index=True
                )
                st.success(f"Added {sku} {size} to {platform}")
        else:
            st.warning("Fill SKU, Size, Platform, Listed Price + paste sales data")

# ─── TABS FOR EACH PLATFORM ──────────────────────────────────────
tab_vinted, tab_ebay, tab_other, tab_dashboard = st.tabs(["Vinted", "eBay", "Other/Retail", "Dashboard"])

for tab, p in zip([tab_vinted, tab_ebay, tab_other], platforms):
    with tab:
        st.subheader(f"{p} Table")
        df = st.session_state.tables[p]
        edited = st.data_editor(df, num_rows="dynamic", use_container_width=True, key=f"{p}_editor")
        st.session_state.tables[p] = edited

# ─── DASHBOARD ───────────────────────────────────────────────────
with tab_dashboard:
    st.header("📊 Dashboard")
    total = sum(len(df) for df in st.session_state.tables.values())
    high_cost = sum(df[df["Priority"] == "High (Red)"]["Recommended Pay £"].sum() for df in st.session_state.tables.values())
    med_cost = sum(df[df["Priority"] == "Medium (Yellow)"]["Recommended Pay £"].sum() for df in st.session_state.tables.values())
    low_cost = sum(df[df["Priority"] == "Low (Green)"]["Recommended Pay £"].sum() for df in st.session_state.tables.values())

    cols = st.columns(4)
    cols[0].metric("Total Items", total)
    cols[1].metric("High Priority Cost", f"£{high_cost:,.0f}")
    cols[2].metric("Medium Priority Cost", f"£{med_cost:,.0f}")
    cols[3].metric("Low Priority Cost", f"£{low_cost:,.0f}")

# ─── EXPORT ──────────────────────────────────────────────────────
if st.button("Export All Tables to CSV"):
    all_df = pd.concat(st.session_state.tables.values(), ignore_index=True)
    st.download_button("Download CSV", all_df.to_csv(index=False), "wtb_tracker.csv")

st.caption("Manual WTB Tracker – Paste sales data for calculations • Priority colors applied • Separate platform tabs")
