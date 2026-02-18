import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import re

st.set_page_config(page_title="WTB Tracker", layout="wide", page_icon="👟")
st.title("👟 WTB Tracker – Manual Entry & Analysis")

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

def analyze_sales(raw_text, sku, brand, model, size, listed_price, platform, priority, highest_bid):
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

    return {
        "SKU": sku,
        "Brand": brand or "Manual",
        "Model": model or "Manual",
        "Colorway": "Manual",
        "Size": size,
        "Listed Price": listed_price,
        "Platform": platform,
        "Priority": priority,
        "#Sales 120D": n,
        "Avg Sale £": round(avg_sale, 2),
        "Avg Payout £": round(avg_net, 2),
        "ROI %": roi_pct,
        "Highest Bid": highest_bid or "—",
        "Lowest Ask": "—",
        "Recommended Pay £": rec_price,
        "Recommended ROI %": f"{roi_target*100:.0f}%",
        "Est Days to Sell": round(est_days, 1)
    }, None

# ─── TABLES SETUP ────────────────────────────────────────────────
platforms = ["Vinted", "eBay", "Other/Retail"]
if "tables" not in st.session_state:
    st.session_state.tables = {}
    for p in platforms:
        st.session_state.tables[p] = pd.DataFrame(columns=[
            "SKU", "Brand", "Model", "Colorway", "Size", "Listed Price", "Platform", "Priority",
            "#Sales 120D", "Avg Sale £", "Avg Payout £", "ROI %", "Highest Bid", "Lowest Ask",
            "Recommended Pay £", "Recommended ROI %", "Est Days to Sell"
        ])

# ─── ENTRY FORM ──────────────────────────────────────────────────
with st.expander("➕ Add New WTB Entry", expanded=True):
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        sku = st.text_input("SKU")
        size = st.text_input("UK Size")
    with col2:
        brand = st.text_input("Brand (optional)")
        model = st.text_input("Model (optional)")
    with col3:
        platform = st.selectbox("Platform", platforms)
        listed_price = st.number_input("Listed Price (£)", min_value=0.0, value=0.0)
    with col4:
        priority = st.selectbox("Priority", ["High (Red)", "Medium (Yellow)", "Low (Green)"])
        highest_bid = st.number_input("Highest Bid (£) – optional", min_value=0.0, value=0.0)
        raw_sales = st.text_area("Paste Raw StockX Sales Data (required)", height=140)

    if st.button("Analyze & Add"):
        if sku and size and raw_sales:
            row, err = analyze_sales(raw_sales, sku, brand, model, size, listed_price, platform, priority, highest_bid)
            if err:
                st.error(err)
            else:
                st.session_state.tables[platform] = pd.concat(
                    [st.session_state.tables[platform], pd.DataFrame([row])],
                    ignore_index=True
                )
                st.success(f"Added {sku} {size} to {platform}")
        else:
            st.warning("Fill SKU, Size, Platform, Listed Price + paste sales data")

# ─── SEPARATE PAGES FOR EACH PLATFORM ────────────────────────────
tab_dashboard, tab_vinted, tab_ebay, tab_other = st.tabs(["Dashboard", "Vinted", "eBay", "Other/Retail"])

def style_priority(df):
    def color_row(row):
        if row["Priority"] == "High (Red)":
            return ['background-color: #ffcccc'] * len(row)
        elif row["Priority"] == "Medium (Yellow)":
            return ['background-color: #ffffcc'] * len(row)
        else:
            return [''] * len(row)
    return df.style.apply(color_row, axis=1)

with tab_vinted:
    st.subheader("Vinted Listings")
    df_v = st.session_state.tables["Vinted"]
    st.dataframe(style_priority(df_v), use_container_width=True)

with tab_ebay:
    st.subheader("eBay Listings")
    df_e = st.session_state.tables["eBay"]
    st.dataframe(style_priority(df_e), use_container_width=True)

with tab_other:
    st.subheader("Other/Retail Listings")
    df_o = st.session_state.tables["Other/Retail"]
    st.dataframe(style_priority(df_o), use_container_width=True)

# ─── DASHBOARD ───────────────────────────────────────────────────
with tab_dashboard:
    st.header("📊 Dashboard")
    total = sum(len(df) for df in st.session_state.tables.values())
    high_cost = sum(df[df["Priority"] == "High (Red)"]["Recommended Pay £"].sum() for df in st.session_state.tables.values())
    med_cost = sum(df[df["Priority"] == "Medium (Yellow)"]["Recommended Pay £"].sum() for df in st.session_state.tables.values())
    low_cost = sum(df[df["Priority"] == "Low (Green)"]["Recommended Pay £"].sum() for df in st.session_state.tables.values())

    vinted_high = st.session_state.tables["Vinted"][st.session_state.tables["Vinted"]["Priority"] == "High (Red)"]["Recommended Pay £"].sum()
    ebay_high = st.session_state.tables["eBay"][st.session_state.tables["eBay"]["Priority"] == "High (Red)"]["Recommended Pay £"].sum()
    other_high = st.session_state.tables["Other/Retail"][st.session_state.tables["Other/Retail"]["Priority"] == "High (Red)"]["Recommended Pay £"].sum()

    cols = st.columns(5)
    cols[0].metric("Total Items", total)
    cols[1].metric("High Priority Cost", f"£{high_cost:,.0f}")
    cols[2].metric("Medium Priority Cost", f"£{med_cost:,.0f}")
    cols[3].metric("Vinted High Cost", f"£{vinted_high:,.0f}")
    cols[4].metric("eBay High Cost", f"£{ebay_high:,.0f}")

# ─── HIGH BIDS FLAGS ─────────────────────────────────────────────
st.header("🔥 High Bids / Good ROI Flags")
high_rows = []
for p in platforms:
    df = st.session_state.tables[p]
    if not df.empty:
        mask = (
            ((df["ROI %"] > 5) & (p == "Vinted")) |
            ((df["ROI %"] > 15) & (p == "Other/Retail")) |
            (p == "eBay")
        )
        high_rows.append(df[mask])

if high_rows:
    high_df = pd.concat(high_rows, ignore_index=True)
    st.dataframe(high_df, use_container_width=True)
else:
    st.info("No flagged items yet")

# Export
if st.button("Export All to CSV"):
    all_df = pd.concat(st.session_state.tables.values(), ignore_index=True)
    st.download_button("Download CSV", all_df.to_csv(index=False), "wtb_tracker_export.csv")

st.caption("Manual entry • Paste StockX sales data for analysis • Priority colors • Separate pages")
