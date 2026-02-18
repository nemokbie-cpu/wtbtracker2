import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import json

st.set_page_config(page_title="Sneaker WTB Tracker", layout="wide", page_icon="👟")
st.title("🚀 Sneaker WTB Tracker – StockX Powered")

# ====================== API KEY ======================
api_key = st.sidebar.text_input("StockX API Key", value="QHeLTV6iWH1zzT0rXj6AS5FmZrF1D2cY1Jgmbvgq", type="password")
headers = {"Authorization": f"Bearer {api_key}"}

# ====================== PAYOUT FORMULA ======================
def calculate_net(price):
    if price < 57:
        return round(price - 4.5 - (price * 0.03) - 4.00, 2)
    else:
        return round(price - (price * 0.08) - (price * 0.03) - 4.00, 2)

# ====================== FETCH FROM STOCKX ======================
@st.cache_data(ttl=300)
def fetch_stockx_data(sku, uk_size):
    try:
        # Search for product
        search = requests.get(f"https://api.stockx.com/v2/search?q={sku}", headers=headers, timeout=10).json()
        if not search.get("products"):
            return None
        product_id = search["products"][0]["id"]
        name = search["products"][0]["title"]
        colorway = search["products"][0].get("colorway", "")

        # Market data
        market = requests.get(f"https://api.stockx.com/v2/products/{product_id}", headers=headers, timeout=10).json()
        highest_bid = market.get("market", {}).get("highestBid", 0)
        lowest_ask = market.get("market", {}).get("lowestAsk", 0)
        num_asks = market.get("market", {}).get("numberOfAsks", 0)

        # Recent sales
        sales_resp = requests.get(
            f"https://api.stockx.com/v2/products/{product_id}/activity?limit=100&type=sale",
            headers=headers, timeout=10
        ).json()
        sales = []
        cutoff = datetime.now() - timedelta(days=120)
        for item in sales_resp.get("data", []):
            try:
                sale_date = datetime.fromisoformat(item["createdAt"].replace("Z", "+00:00"))
                if sale_date >= cutoff and item.get("size") == f"UK {uk_size}":
                    sales.append(float(item["amount"]))
            except:
                continue

        return {
            "name": name,
            "colorway": colorway,
            "highest_bid": highest_bid,
            "lowest_ask": lowest_ask,
            "num_asks": num_asks,
            "sales_120d": len(sales),
            "avg_sale": round(sum(sales)/len(sales), 2) if sales else 0,
            "sales_list": sales[:50]  # last 50
        }
    except:
        return None

# ====================== DASHBOARD ======================
st.sidebar.header("Dashboard")
total_items = 0
high_cost = med_cost = low_cost = 0
vinted_high = ebay_high = other_high = 0

# ====================== TABLES ======================
platforms = ["Vinted", "eBay", "Other/Retail"]
tables = {}
for p in platforms:
    if p not in st.session_state:
        st.session_state[p] = pd.DataFrame(columns=[
            "SKU", "Brand", "Model", "Colorway", "Size", "Listed Price", "Priority",
            "#Sales 120D", "Avg Sale £", "Avg Payout £", "ROI %", "Highest Bid", "Lowest Ask",
            "Recommended Pay £", "Est Days to Sell"
        ])
    tables[p] = st.session_state[p]

# Add new entry form
with st.expander("➕ Add New WTB Entry", expanded=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        sku = st.text_input("SKU")
        size = st.text_input("UK Size (e.g. 6.5)")
        platform = st.selectbox("Platform", platforms)
    with col2:
        listed_price = st.number_input("Listed Price (£)", min_value=0.0, value=0.0)
        if platform == "eBay":
            end_date = st.date_input("Auction End Date (optional)")
        else:
            end_date = None
    with col3:
        priority = st.selectbox("Priority", ["High (Red)", "Medium (Yellow)", "Low (Green)"])

    if st.button("Fetch from StockX + Add"):
        if sku and size and api_key:
            data = fetch_stockx_data(sku, size)
            if data:
                n = data["sales_120d"]
                avg_sale = data["avg_sale"]
                avg_net = sum(calculate_net(p) for p in data["sales_list"]) / n if n > 0 else 0
                est_days = 120 / n if n > 0 else 999

                if est_days < 5:
                    roi_target = 0.30
                elif 6 <= est_days <= 25:
                    roi_target = 0.35
                else:
                    roi_target = 0.40

                rec_price = round(avg_net / (1 + roi_target), 2)

                new_row = {
                    "SKU": sku,
                    "Brand": "Auto",
                    "Model": data["name"],
                    "Colorway": data["colorway"],
                    "Size": size,
                    "Listed Price": listed_price,
                    "Priority": priority,
                    "#Sales 120D": n,
                    "Avg Sale £": avg_sale,
                    "Avg Payout £": round(avg_net, 2),
                    "ROI %": round((avg_net - listed_price) / listed_price * 100, 1) if listed_price > 0 else 0,
                    "Highest Bid": data["highest_bid"],
                    "Lowest Ask": data["lowest_ask"],
                    "Recommended Pay £": rec_price,
                    "Est Days to Sell": round(est_days, 1)
                }
                tables[platform] = pd.concat([tables[platform], pd.DataFrame([new_row])], ignore_index=True)
                st.session_state[platform] = tables[platform]
                st.success(f"Added {sku} {size} to {platform}")
            else:
                st.error("Could not fetch from StockX")
        else:
            st.warning("Fill SKU, Size and API key")

# Display tables
tab1, tab2, tab3 = st.tabs(["Vinted", "eBay", "Other/Retail"])
for tab, p in zip([tab1, tab2, tab3], platforms):
    with tab:
        edited = st.data_editor(
            tables[p],
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Priority": st.column_config.SelectboxColumn("Priority", options=["High (Red)", "Medium (Yellow)", "Low (Green)"]),
            }
        )
        tables[p] = edited
        st.session_state[p] = edited

# High Bids Section
st.header("🔥 High Bids Auto-Tracker")
high_bids_df = pd.DataFrame()
for p in platforms:
    df = tables[p].copy()
    if not df.empty:
        high_mask = (
            ((df["ROI %"] > 5) & (p == "Vinted")) |
            ((df["ROI %"] > 15) & (p == "Other/Retail")) |
            (p == "eBay")
        )
        high_bids_df = pd.concat([high_bids_df, df[high_mask]])

if not high_bids_df.empty:
    st.dataframe(high_bids_df, use_container_width=True)
else:
    st.info("No high-bid opportunities yet (add entries first)")

# Dashboard Counters
st.header("📊 Dashboard")
cols = st.columns(5)
cols[0].metric("Total Items", sum(len(t) for t in tables.values()))
cols[1].metric("High Priority Cost", "£" + str(sum(t[t["Priority"] == "High (Red)"]["Recommended Pay £"].sum() for t in tables.values())))
cols[2].metric("Medium Priority Cost", "£" + str(sum(t[t["Priority"] == "Medium (Yellow)"]["Recommended Pay £"].sum() for t in tables.values())))
cols[3].metric("Vinted High Cost", "£" + str(tables["Vinted"][tables["Vinted"]["Priority"] == "High (Red)"]["Recommended Pay £"].sum()))
cols[4].metric("eBay High Cost", "£" + str(tables["eBay"][tables["eBay"]["Priority"] == "High (Red)"]["Recommended Pay £"].sum()))

# Save / Load
col_save, col_load = st.columns(2)
with col_save:
    if st.button("💾 Download All Data"):
        all_data = {p: tables[p].to_dict() for p in platforms}
        st.download_button("Download JSON", data=json.dumps(all_data), file_name="wtb_tracker_backup.json")
with col_load:
    uploaded = st.file_uploader("Upload backup JSON")
    if uploaded:
        data = json.load(uploaded)
        for p in platforms:
            if p in data:
                st.session_state[p] = pd.DataFrame(data[p])
        st.success("Restored!")

st.caption("Made for you with your StockX API key • Minimal & fast")
