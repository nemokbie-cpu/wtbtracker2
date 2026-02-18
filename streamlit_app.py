import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import json
import re

st.set_page_config(page_title="WTB Tracker", layout="wide", page_icon="👟")
st.title("👟 WTB Tracker – Auto SKU Lookup + Manual Sales Analysis")

# ─── API KEY (from secrets) ──────────────────────────────────────
api_key = st.secrets.get("STOCKX_API_KEY", None)
if not api_key:
    st.warning("No StockX API key found in secrets. Auto-lookup disabled – enter brand/model/colorway manually.")
    headers = None
else:
    headers = {"Authorization": f"Bearer {api_key}"}

# ─── PAYOUT FORMULA ──────────────────────────────────────────────
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

# ─── AUTO-FETCH SHOE INFO FROM STOCKX ────────────────────────────
@st.cache_data(ttl=3600)
def fetch_shoe_info(sku):
    if not headers:
        return None, "No API key configured"
    try:
        r = requests.get(f"https://api.stockx.com/v2/search?q={sku}", headers=headers, timeout=10)
        if r.status_code != 200:
            return None, f"Search failed: {r.status_code}"
        data = r.json()
        if not data.get("products"):
            return None, "No product found for SKU"
        product = data["products"][0]
        full_name = product["title"]
        # Basic parsing - StockX title is usually "Brand Model Colorway"
        parts = full_name.split(" ", 2)
        brand = parts[0] if len(parts) > 0 else "Unknown"
        model = parts[1] if len(parts) > 1 else ""
        colorway = parts[2] if len(parts) > 2 else ""
        return {
            "brand": brand,
            "model": model,
            "colorway": colorway,
            "full_name": full_name
        }, None
    except Exception as e:
        return None, str(e)

# ─── ANALYZE PASTED SALES ────────────────────────────────────────
def analyze_sales(raw_text, sku, size, listed_price, platform, priority):
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
        "Brand": "Auto",
        "Model": "Auto",
        "Colorway": "Auto",
        "Size": size,
        "Listed Price": listed_price,
        "Platform": platform,
        "Priority": priority,
        "#Sales 120D": n,
        "Avg Sale £": round(avg_sale, 2),
        "Avg Payout £": round(avg_net, 2),
        "ROI %": roi_pct,
        "Highest Bid": "—",
        "Lowest Ask": "—",
        "Recommended Pay £": rec_price,
        "Est Days to Sell": round(est_days, 1)
    }, None

# ─── TABLES ──────────────────────────────────────────────────────
platforms = ["Vinted", "eBay", "Other/Retail"]
if "tables" not in st.session_state:
    st.session_state.tables = {}
    for p in platforms:
        st.session_state.tables[p] = pd.DataFrame(columns=[
            "SKU", "Brand", "Model", "Colorway", "Size", "Listed Price", "Platform", "Priority",
            "#Sales 120D", "Avg Sale £", "Avg Payout £", "ROI %", "Highest Bid", "Lowest Ask",
            "Recommended Pay £", "Est Days to Sell"
        ])

# ─── ENTRY FORM ──────────────────────────────────────────────────
with st.expander("➕ Add New WTB Entry", expanded=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        sku = st.text_input("SKU")
        size = st.text_input("UK Size")
        if sku and st.button("Auto-Fetch Shoe Info"):
            info, err = fetch_shoe_info(sku)
            if err:
                st.error(err)
            else:
                st.session_state["auto_brand"] = info["brand"]
                st.session_state["auto_model"] = info["model"]
                st.session_state["auto_colorway"] = info["colorway"]
                st.success("Auto-filled from StockX!")

    with col2:
        platform = st.selectbox("Platform", platforms)
        listed_price = st.number_input("Listed Price (£)", min_value=0.0, value=0.0)
    with col3:
        priority = st.selectbox("Priority", ["High (Red)", "Medium (Yellow)", "Low (Green)"])
        raw_sales = st.text_area("Paste Raw StockX Sales Data (required for analysis)", height=120)

    if st.button("Analyze & Add to Table"):
        if sku and size and raw_sales:
            row, err = analyze_sales(raw_sales, sku, size, listed_price, platform, priority)
            if err:
                st.error(err)
            else:
                # Apply auto-filled info if available
                if "auto_brand" in st.session_state:
                    row["Brand"] = st.session_state["auto_brand"]
                    row["Model"] = st.session_state["auto_model"]
                    row["Colorway"] = st.session_state["auto_colorway"]
                st.session_state.tables[platform] = pd.concat(
                    [st.session_state.tables[platform], pd.DataFrame([row])],
                    ignore_index=True
                )
                st.success(f"Added {sku} {size} to {platform}")
        else:
            st.warning("Fill SKU, Size, Platform, Listed Price + paste sales data")

# ─── TABLES DISPLAY ──────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["Vinted", "eBay", "Other/Retail"])

def style_priority(df):
    def color_row(row):
        if row["Priority"] == "High (Red)":
            return ['background-color: #ffcccc'] * len(row)
        elif row["Priority"] == "Medium (Yellow)":
            return ['background-color: #ffffcc'] * len(row)
        else:
            return [''] * len(row)
    return df.style.apply(color_row, axis=1)

for tab, p in zip([tab1, tab2, tab3], platforms):
    with tab:
        df = st.session_state.tables[p]
        edited = st.data_editor(
            df,
            num_rows="dynamic",
            use_container_width=True,
            key=f"{p}_editor"
        )
        st.session_state.tables[p] = edited

# ─── HIGH BIDS / GOOD ROI FLAGS ──────────────────────────────────
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

# ─── DASHBOARD ───────────────────────────────────────────────────
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

# Export
if st.button("Export All to CSV"):
    all_df = pd.concat(st.session_state.tables.values(), ignore_index=True)
    st.download_button("Download CSV", all_df.to_csv(index=False), "wtb_tracker.csv")

st.caption("Auto-fetches Brand/Model/Colorway from StockX on SKU entry • Manual sales paste required for analysis")
