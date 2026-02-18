import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import json

st.set_page_config(page_title="Sneaker WTB Tracker", layout="wide", page_icon="👟")
st.title("🚀 Sneaker WTB Tracker – StockX Powered")

# ====================== SECURE API KEY ======================
api_key = st.secrets.get("STOCKX_API_KEY", None)
if not api_key:
    st.error("StockX API key not found in secrets. Add it in Settings → Secrets as STOCKX_API_KEY")
    st.stop()

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
        st.write("DEBUG: Starting search for SKU:", sku, "Size:", uk_size)
        
        # Step 1: Search for product
        search_url = f"https://api.stockx.com/v2/search?q={sku}"
        st.write("DEBUG: Search URL:", search_url)
        search = requests.get(search_url, headers=headers, timeout=10)
        st.write("DEBUG: Search status code:", search.status_code)
        
        if search.status_code != 200:
            st.error(f"Search failed with status {search.status_code}: {search.text[:200]}...")
            return None

        search_json = search.json()
        st.write("DEBUG: Search response keys:", list(search_json.keys()))
        
        if not search_json.get("products") or len(search_json["products"]) == 0:
            st.error("No products found for this SKU")
            return None

        # Take first matching product
        product = search_json["products"][0]
        product_id = product["id"]
        name = product["title"]
        colorway = product.get("colorway", "N/A")
        
        st.write("DEBUG: Found product ID:", product_id)
        st.write("DEBUG: Shoe name:", name)
        st.write("DEBUG: Colorway:", colorway)

        # Step 2: Get market data (highest bid, lowest ask, # asks)
        market_url = f"https://api.stockx.com/v2/products/{product_id}"
        market = requests.get(market_url, headers=headers, timeout=10)
        st.write("DEBUG: Market status code:", market.status_code)
        
        if market.status_code != 200:
            st.error(f"Market data failed with status {market.status_code}")
            return None

        market_data = market.json().get("market", {})
        highest_bid = market_data.get("highestBid", 0)
        lowest_ask  = market_data.get("lowestAsk", 0)
        num_asks    = market_data.get("numberOfAsks", 0)

        # Step 3: Get recent sales activity
        sales_url = f"https://api.stockx.com/v2/products/{product_id}/activity?limit=100&type=sale"
        sales_resp = requests.get(sales_url, headers=headers, timeout=10)
        st.write("DEBUG: Sales status code:", sales_resp.status_code)
        
        if sales_resp.status_code != 200:
            st.error(f"Sales fetch failed with status {sales_resp.status_code}")
            return None

        sales_data = sales_resp.json().get("data", [])
        sales = []
        cutoff = datetime.now() - timedelta(days=120)
        
        for item in sales_data:
            try:
                sale_date_str = item.get("createdAt")
                if not sale_date_str:
                    continue
                sale_date = datetime.fromisoformat(sale_date_str.replace("Z", "+00:00"))
                if sale_date >= cutoff and str(item.get("size")) == f"UK {uk_size}":
                    amount = float(item.get("amount", 0))
                    if amount > 0:
                        sales.append(amount)
            except Exception as e:
                st.write("DEBUG: Skipped sale entry:", str(e))
                continue

        return {
            "name": name,
            "colorway": colorway,
            "highest_bid": highest_bid,
            "lowest_ask": lowest_ask,
            "num_asks": num_asks,
            "sales_120d": len(sales),
            "avg_sale": round(sum(sales)/len(sales), 2) if sales else 0,
            "sales_list": sales[:50]  # last 50 for payout calc
        }
    except Exception as e:
        st.error(f"Unexpected error in fetch: {str(e)}")
        return None

# ====================== SESSION STATE TABLES ======================
platforms = ["Vinted", "eBay", "Other/Retail"]

if "tables" not in st.session_state:
    st.session_state.tables = {}
    for p in platforms:
        st.session_state.tables[p] = pd.DataFrame(columns=[
            "SKU", "Brand", "Model", "Colorway", "Size", "Listed Price", "Priority",
            "#Sales 120D", "Avg Sale £", "Avg Payout £", "ROI %", "Highest Bid", "Lowest Ask",
            "Recommended Pay £", "Est Days to Sell"
        ])

# ====================== ADD NEW ENTRY ======================
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

                rec_price = round(avg_net / (1 + roi_target), 2) if avg_net > 0 else 0

                roi_pct = round((avg_net - listed_price) / listed_price * 100, 1) if listed_price > 0 else 0

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
                    "ROI %": roi_pct,
                    "Highest Bid": data["highest_bid"],
                    "Lowest Ask": data["lowest_ask"],
                    "Recommended Pay £": rec_price,
                    "Est Days to Sell": round(est_days, 1)
                }
                st.session_state.tables[platform] = pd.concat(
                    [st.session_state.tables[platform], pd.DataFrame([new_row])],
                    ignore_index=True
                )
                st.success(f"Added {sku} {size} to {platform}")
            else:
                st.error("Could not fetch from StockX – check SKU/size/API key")
        else:
            st.warning("Fill SKU, Size and ensure API key is set in secrets")

# ====================== DISPLAY TABLES ======================
tab1, tab2, tab3 = st.tabs(["Vinted", "eBay", "Other/Retail"])

with tab1:
    edited_vinted = st.data_editor(
        st.session_state.tables["Vinted"],
        num_rows="dynamic",
        use_container_width=True,
        key="vinted_editor"
    )
    st.session_state.tables["Vinted"] = edited_vinted

with tab2:
    edited_ebay = st.data_editor(
        st.session_state.tables["eBay"],
        num_rows="dynamic",
        use_container_width=True,
        key="ebay_editor"
    )
    st.session_state.tables["eBay"] = edited_ebay

with tab3:
    edited_other = st.data_editor(
        st.session_state.tables["Other/Retail"],
        num_rows="dynamic",
        use_container_width=True,
        key="other_editor"
    )
    st.session_state.tables["Other/Retail"] = edited_other

# ====================== HIGH BIDS SECTION ======================
st.header("🔥 High Bids Auto-Tracker")
high_bids = []
for p in platforms:
    df = st.session_state.tables[p].copy()
    if not df.empty:
        mask = (
            ((df["ROI %"] > 5) & (p == "Vinted")) |
            ((df["ROI %"] > 15) & (p == "Other/Retail")) |
            (p == "eBay")
        )
        high_bids.append(df[mask])

if high_bids:
    high_df = pd.concat(high_bids, ignore_index=True)
    st.dataframe(high_df, use_container_width=True)
else:
    st.info("No high-bid opportunities yet – add entries first")

# ====================== DASHBOARD ======================
st.header("📊 Dashboard")
total_items = sum(len(df) for df in st.session_state.tables.values())
high_cost = sum(df[df["Priority"] == "High (Red)"]["Recommended Pay £"].sum() for df in st.session_state.tables.values())
med_cost = sum(df[df["Priority"] == "Medium (Yellow)"]["Recommended Pay £"].sum() for df in st.session_state.tables.values())
low_cost = sum(df[df["Priority"] == "Low (Green)"]["Recommended Pay £"].sum() for df in st.session_state.tables.values())

vinted_high = st.session_state.tables["Vinted"][st.session_state.tables["Vinted"]["Priority"] == "High (Red)"]["Recommended Pay £"].sum()
ebay_high = st.session_state.tables["eBay"][st.session_state.tables["eBay"]["Priority"] == "High (Red)"]["Recommended Pay £"].sum()
other_high = st.session_state.tables["Other/Retail"][st.session_state.tables["Other/Retail"]["Priority"] == "High (Red)"]["Recommended Pay £"].sum()

cols = st.columns(5)
cols[0].metric("Total Items", total_items)
cols[1].metric("High Priority Cost", f"£{high_cost:,.0f}")
cols[2].metric("Medium Priority Cost", f"£{med_cost:,.0f}")
cols[3].metric("Vinted High Cost", f"£{vinted_high:,.0f}")
cols[4].metric("eBay High Cost", f"£{ebay_high:,.0f}")

# ====================== BACKUP / RESTORE ======================
col1, col2 = st.columns(2)
with col1:
    if st.button("💾 Download All Data"):
        all_data = {p: df.to_dict(orient="records") for p, df in st.session_state.tables.items()}
        st.download_button(
            label="Download JSON Backup",
            data=json.dumps(all_data, indent=2),
            file_name="wtb_tracker_backup.json",
            mime="application/json"
        )

with col2:
    uploaded = st.file_uploader("Upload Backup JSON")
    if uploaded:
        try:
            data = json.load(uploaded)
            for p in platforms:
                if p in data:
                    st.session_state.tables[p] = pd.DataFrame(data[p])
            st.success("Backup restored!")
        except:
            st.error("Invalid backup file")

st.caption("Powered by your StockX API key • Private & secure • Minimal design")
