import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import re
import json
import os

st.set_page_config(page_title="WTB Tracker", layout="wide", page_icon="👟")
st.title("👟 WTB Tracker – Manual Analysis")

# ─── PERSISTENCE (data saved across reloads) ─────────────────────
DATA_FILE = "wtb_data.json"

if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        saved = json.load(f)
        if "tables" not in st.session_state:
            st.session_state.tables = {}
            for p in ["Vinted", "eBay", "Other/Retail"]:
                st.session_state.tables[p] = pd.DataFrame(saved.get(p, []))
else:
    if "tables" not in st.session_state:
        st.session_state.tables = {}
        for p in ["Vinted", "eBay", "Other/Retail"]:
            st.session_state.tables[p] = pd.DataFrame(columns=[
                "SKU", "Brand", "Model", "Colorway", "Size", "Listed Price", "Platform", "Priority",
                "#Sales 120D", "Avg Payout £", "ROI %", "Highest Bid", "Recommended Pay £", "Est Days to Sell"
            ])

def save_data():
    data_to_save = {p: df.to_dict(orient="records") for p, df in st.session_state.tables.items()}
    with open(DATA_FILE, "w") as f:
        json.dump(data_to_save, f)

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

# ─── PARSE FULL NAME ─────────────────────────────────────────────
def parse_full_name(full_name):
    # Example: "adidas Yeezy Boost 700 V2 Geode UK 8"
    match = re.search(r'(UK|US)\s*([\d.]+)', full_name, re.IGNORECASE)
    size = match.group(0) if match else ""
    name_part = full_name.replace(size, "").strip()

    parts = name_part.split()
    brand = parts[0] if parts else "Manual"
    colorway = parts[-1] if len(parts) > 1 else ""
    model = " ".join(parts[1:-1]) if len(parts) > 2 else " ".join(parts[1:])

    return brand, model, colorway, size

# ─── ANALYZE SALES ───────────────────────────────────────────────
def analyze_sales(raw_text, sku, brand, model, colorway, size, listed_price, platform, highest_bid):
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
    avg_net = sum(calculate_net(p) for p in prices) / n
    est_days = 120 / n if n > 0 else 999
    roi_target = get_target_roi(est_days)
    rec_price = round(avg_net / (1 + roi_target), 2) if avg_net > 0 else 0
    roi_pct = round((avg_net - listed_price) / listed_price * 100, 1) if listed_price > 0 else 0

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
        "Avg Payout £": round(avg_net, 2),
        "ROI %": roi_pct,
        "Highest Bid": highest_bid if highest_bid > 0 else "—",
        "Recommended Pay £": rec_price if platform != "Other/Retail" else "—",
        "Est Days to Sell": round(est_days, 1)
    }, None

# ─── ENTRY FORM (Single Full Name Field) ─────────────────────────
with st.expander("➕ Add New WTB Entry", expanded=True):
    full_name = st.text_input("Full Shoe Name (e.g. adidas Yeezy Boost 700 V2 Geode UK 8)", placeholder="adidas Yeezy Boost 700 V2 Geode UK 8")

    col1, col2, col3 = st.columns(3)
    with col1:
        platform = st.selectbox("Platform", ["Vinted", "eBay", "Other/Retail"])
        listed_price = st.number_input("Listed Price (£)", min_value=0.0, value=0.0)
    with col2:
        highest_bid = st.number_input("Highest Bid (£) – optional", min_value=0.0, value=0.0)
        priority = st.selectbox("Priority", ["Low", "Medium", "High"])
    with col3:
        raw_sales = st.text_area("Paste Raw StockX Sales Data (required)", height=140)

    if st.button("Parse Name + Analyze & Add"):
        if full_name and raw_sales:
            brand, model, colorway, size = parse_full_name(full_name)
            sku = st.text_input("SKU (optional)", value="")  # optional SKU
            if not sku:
                sku = "Manual"

            row, err = analyze_sales(raw_sales, sku, brand, model, colorway, size, listed_price, platform, highest_bid)
            if err:
                st.error(err)
            else:
                st.session_state.tables[platform] = pd.concat(
                    [st.session_state.tables[platform], pd.DataFrame([row])],
                    ignore_index=True
                )
                save_data()
                st.success(f"Added {brand} {model} {size} to {platform}")
        else:
            st.warning("Paste Full Shoe Name + Sales Data")

# ─── TABS ────────────────────────────────────────────────────────
tab_vinted, tab_ebay, tab_other, tab_fast, tab_strong, tab_slow, tab_highmed, tab_dashboard = st.tabs([
    "Vinted", "eBay", "Other/Retail", "Fast Movers", "Strong Return", "Slower Movers", "High + Medium Priority", "Dashboard"
])

def style_priority(df):
    def color_row(row):
        if row["Priority"] == "High":
            return ['background-color: #ffcccc'] * len(row)
        elif row["Priority"] == "Medium":
            return ['background-color: #ffebcc'] * len(row)
        else:
            return ['background-color: #ccffcc'] * len(row)
    return df.style.apply(color_row, axis=1)

for tab, p in zip([tab_vinted, tab_ebay, tab_other], ["Vinted", "eBay", "Other/Retail"]):
    with tab:
        st.subheader(p)
        df = st.session_state.tables[p].sort_values("ROI %", ascending=False)
        st.data_editor(df, num_rows="dynamic", use_container_width=True, key=f"{p}_editor")

# Fast, Strong, Slower, High+Medium tabs (same as before)
with tab_fast:
    st.subheader("Fast Movers (<15 days + ≥25% ROI)")
    all_df = pd.concat(st.session_state.tables.values(), ignore_index=True)
    fast = all_df[(all_df["Est Days to Sell"] < 15) & (all_df["ROI %"] >= 25)].sort_values("ROI %", ascending=False)
    st.data_editor(fast, num_rows="dynamic", use_container_width=True)

with tab_strong:
    st.subheader("Strong Return (≥30% ROI & <30 days)")
    all_df = pd.concat(st.session_state.tables.values(), ignore_index=True)
    strong = all_df[(all_df["ROI %"] >= 30) & (all_df["Est Days to Sell"] < 30)].sort_values("ROI %", ascending=False)
    st.data_editor(strong, num_rows="dynamic", use_container_width=True)

with tab_slow:
    st.subheader("Slower Movers (≥30% ROI & >30 days)")
    all_df = pd.concat(st.session_state.tables.values(), ignore_index=True)
    slow = all_df[(all_df["ROI %"] >= 30) & (all_df["Est Days to Sell"] >= 30)].sort_values("ROI %", ascending=False)
    st.data_editor(slow, num_rows="dynamic", use_container_width=True)

with tab_highmed:
    st.subheader("High + Medium Priority SKUs")
    all_df = pd.concat(st.session_state.tables.values(), ignore_index=True)
    highmed = all_df[all_df["Priority"].isin(["High", "Medium"])].sort_values("ROI %", ascending=False)
    st.data_editor(highmed, num_rows="dynamic", use_container_width=True)

# Dashboard
with tab_dashboard:
    st.header("📊 Dashboard")
    total = sum(len(df) for df in st.session_state.tables.values())
    high_cost = sum(df[df["Priority"] == "High"]["Recommended Pay £"].sum() for df in st.session_state.tables.values() if "Recommended Pay £" in df.columns)
    med_cost = sum(df[df["Priority"] == "Medium"]["Recommended Pay £"].sum() for df in st.session_state.tables.values() if "Recommended Pay £" in df.columns)
    low_cost = sum(df[df["Priority"] == "Low"]["Recommended Pay £"].sum() for df in st.session_state.tables.values() if "Recommended Pay £" in df.columns)

    cols = st.columns(4)
    cols[0].metric("Total Items", total)
    cols[1].metric("High Priority Cost", f"£{high_cost:,.0f}")
    cols[2].metric("Medium Priority Cost", f"£{med_cost:,.0f}")
    cols[3].metric("Low Priority Cost", f"£{low_cost:,.0f}")

if st.button("Export All Tables to CSV"):
    all_df = pd.concat(st.session_state.tables.values(), ignore_index=True)
    st.download_button("Download CSV", all_df.to_csv(index=False), "wtb_tracker.csv")

st.caption("Paste full name like 'adidas Yeezy Boost 700 V2 Geode UK 8' • Data saved automatically • Priority dropdown with colors")
