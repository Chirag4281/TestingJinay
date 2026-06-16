import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from io import BytesIO
import os

# ======================= DATABASE SETUP =======================
# Smart database path
if 'RAILWAY_VOLUME_MOUNT_PATH' in os.environ:
    DB_NAME = os.path.join(os.environ['RAILWAY_VOLUME_MOUNT_PATH'], "jinay_erp.db")
elif os.path.exists('/app/data'):
    DB_NAME = "/app/data/jinay_erp.db"
else:
    DB_NAME = "jinay_erp.db"

os.makedirs(os.path.dirname(DB_NAME) if os.path.dirname(DB_NAME) else '.', exist_ok=True)

def init_db():
    """Initialize database with all required tables"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Master Tables
    cursor.execute('''CREATE TABLE IF NOT EXISTS party_master (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        party_name TEXT UNIQUE NOT NULL,
        address TEXT,
        contact_person TEXT,
        phone TEXT,
        email TEXT,
        gst_no TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS rm_master (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_name TEXT UNIQUE NOT NULL,
        category TEXT,
        unit TEXT DEFAULT 'PCS',
        rate REAL DEFAULT 0,
        per_pc_wt REAL,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS fg_master (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_name TEXT UNIQUE NOT NULL,
        category TEXT,
        unit TEXT DEFAULT 'PCS',
        rate REAL DEFAULT 0,
        rm_required TEXT,
        holder_name TEXT,
        plate_name TEXT,
        jb_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS contractor_master (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        contractor_name TEXT UNIQUE NOT NULL,
        contact_person TEXT,
        phone TEXT,
        address TEXT,
        gst_no TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Transaction Tables
    cursor.execute('''CREATE TABLE IF NOT EXISTS purchase_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        challan_no TEXT NOT NULL,
        date TEXT NOT NULL,
        contractor_name TEXT,
        product_name TEXT NOT NULL,
        qty REAL NOT NULL,
        rate REAL DEFAULT 0,
        amount REAL DEFAULT 0,
        entry_type TEXT DEFAULT 'PURCHASE',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS sales_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        challan_no TEXT NOT NULL,
        date TEXT NOT NULL,
        party_name TEXT NOT NULL,
        product_name TEXT NOT NULL,
        qty REAL NOT NULL,
        rate REAL DEFAULT 0,
        amount REAL DEFAULT 0,
        is_market_rejection INTEGER DEFAULT 0,
        rejection_reason TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS production_register (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        contractor_name TEXT,
        fg_product TEXT NOT NULL,
        qty_produced REAL NOT NULL,
        rm_consumed TEXT,
        dp_part_fitting REAL DEFAULT 0,
        dp_action REAL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS market_rejection_register (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        party_name TEXT,
        product_name TEXT NOT NULL,
        qty_rejected REAL NOT NULL,
        reason TEXT,
        challan_ref TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS party_rejection_register (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        party_name TEXT NOT NULL,
        product_name TEXT NOT NULL,
        qty_rejected REAL NOT NULL,
        reason TEXT,
        challan_ref TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Inventory Tables
    cursor.execute('''CREATE TABLE IF NOT EXISTS rm_inventory (
        product_name TEXT PRIMARY KEY,
        opening_stock REAL DEFAULT 0,
        purchased_qty REAL DEFAULT 0,
        consumed_qty REAL DEFAULT 0,
        closing_stock REAL DEFAULT 0,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS fg_inventory (
        product_name TEXT PRIMARY KEY,
        opening_stock REAL DEFAULT 0,
        produced_qty REAL DEFAULT 0,
        sold_qty REAL DEFAULT 0,
        rejected_qty REAL DEFAULT 0,
        closing_stock REAL DEFAULT 0,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    conn.commit()
    conn.close()

def get_db_connection():
    return sqlite3.connect(DB_NAME)

def execute_query(query, params=()):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    lastrowid = cursor.lastrowid
    conn.close()
    return lastrowid

def fetch_data(query, params=()):
    conn = get_db_connection()
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def update_rm_inventory(product, qty, transaction_type='PURCHASE'):
    if transaction_type == 'PURCHASE':
        execute_query("UPDATE rm_inventory SET purchased_qty = purchased_qty + ? WHERE product_name = ?", (qty, product))
    elif transaction_type == 'CONSUME':
        execute_query("UPDATE rm_inventory SET consumed_qty = consumed_qty + ? WHERE product_name = ?", (qty, product))
    execute_query("UPDATE rm_inventory SET closing_stock = opening_stock + purchased_qty - consumed_qty WHERE product_name = ?", (product,))

def update_fg_inventory(product, qty, transaction_type='PRODUCE'):
    if transaction_type == 'PRODUCE':
        execute_query("UPDATE fg_inventory SET produced_qty = produced_qty + ? WHERE product_name = ?", (qty, product))
    elif transaction_type == 'SALE':
        execute_query("UPDATE fg_inventory SET sold_qty = sold_qty + ? WHERE product_name = ?", (qty, product))
    elif transaction_type == 'REJECT':
        execute_query("UPDATE fg_inventory SET rejected_qty = rejected_qty + ? WHERE product_name = ?", (qty, product))
    execute_query("UPDATE fg_inventory SET closing_stock = opening_stock + produced_qty - sold_qty - rejected_qty WHERE product_name = ?", (product,))

# ======================= EXCEL IMPORT FUNCTIONS =======================
def import_rm_sheet(df):
    records_imported = 0
    product_cols = df.columns[3:].tolist()
    
    for idx, row in df.iterrows():
        challan_no = str(row.get('Challan no.', '')).strip()
        if pd.isna(challan_no) or challan_no.upper() in ['OB', 'NAN', '']:
            continue
        
        date = row.get('Date')
        if isinstance(date, pd.Timestamp):
            date = date.strftime('%Y-%m-%d')
        elif pd.isna(date):
            date = datetime.now().strftime('%Y-%m-%d')
        
        contractor = str(row.get('Contractor', '')).strip()
        if contractor:
            execute_query("INSERT OR IGNORE INTO contractor_master (contractor_name) VALUES (?)", (contractor,))
        
        for col in product_cols:
            qty = row.get(col)
            if pd.notna(qty) and isinstance(qty, (int, float)) and qty > 0:
                product = str(col).strip()
                execute_query("INSERT OR IGNORE INTO rm_master (product_name) VALUES (?)", (product,))
                execute_query("INSERT OR IGNORE INTO rm_inventory (product_name) VALUES (?)", (product,))
                execute_query('''INSERT INTO purchase_transactions 
                    (challan_no, date, contractor_name, product_name, qty, entry_type)
                    VALUES (?, ?, ?, ?, ?, 'PURCHASE')''',
                    (challan_no, date, contractor, product, float(qty)))
                update_rm_inventory(product, float(qty), 'PURCHASE')
                records_imported += 1
    
    return records_imported

def import_fg_sheet(df):
    records_imported = 0
    
    for idx, row in df.iterrows():
        sr_no = row.get('Sr. No.')
        if pd.isna(sr_no):
            continue
        
        product = str(row.get('Products', '')).strip()
        if not product or product.upper() == 'NAN':
            continue
        
        execute_query("INSERT OR IGNORE INTO fg_master (product_name) VALUES (?)", (product,))
        execute_query("INSERT OR IGNORE INTO fg_inventory (product_name) VALUES (?)", (product,))
        
        contractors = ['Arun Bhai', 'Sanjay', 'Shailesh S', 'Sandeep', 'Vijay', 'Manish', 'Suresh', 'Vilas', 'Sunil', 'Vachan Sing']
        
        for contractor in contractors:
            if contractor in df.columns:
                qty = row.get(contractor)
                if pd.notna(qty) and isinstance(qty, (int, float)) and qty > 0:
                    execute_query("INSERT OR IGNORE INTO contractor_master (contractor_name) VALUES (?)", (contractor,))
                    execute_query('''INSERT INTO production_register 
                        (date, contractor_name, fg_product, qty_produced)
                        VALUES (?, ?, ?, ?)''',
                        (datetime.now().strftime('%Y-%m-%d'), contractor, product, float(qty)))
                    update_fg_inventory(product, float(qty), 'PRODUCE')
                    records_imported += 1
        
        sales_cols = ['W Sales', 'B Sales', 'Total Sales']
        for col in sales_cols:
            if col in df.columns:
                qty = row.get(col)
                if pd.notna(qty) and isinstance(qty, (int, float)) and qty > 0:
                    party = 'Wholesale' if 'W' in col else ('Retail' if 'B' in col else 'General')
                    execute_query("INSERT OR IGNORE INTO party_master (party_name) VALUES (?)", (party,))
                    execute_query('''INSERT INTO sales_transactions 
                        (challan_no, date, party_name, product_name, qty, is_market_rejection)
                        VALUES (?, ?, ?, ?, ?, 0)''',
                        ('FG-IMPORT', datetime.now().strftime('%Y-%m-%d'), party, product, float(qty)))
                    update_fg_inventory(product, float(qty), 'SALE')
                    records_imported += 1
        
        if 'Difference (Actual Sold- Production)' in df.columns:
            diff = row.get('Difference (Actual Sold- Production)')
            if pd.notna(diff) and isinstance(diff, (int, float)) and diff < 0:
                execute_query('''INSERT INTO market_rejection_register 
                    (date, product_name, qty_rejected, reason)
                    VALUES (?, ?, ?, ?)''',
                    (datetime.now().strftime('%Y-%m-%d'), product, abs(float(diff)), 'Import - Stock Difference'))
                update_fg_inventory(product, abs(float(diff)), 'REJECT')
                records_imported += 1
    
    return records_imported

def import_mr_pr_sheets(df, sheet_type='MR'):
    records_imported = 0
    
    for idx, row in df.iterrows():
        sr_no = row.get('Sr. No.')
        if pd.isna(sr_no):
            continue
        
        product = str(row.get('Products', '')).strip()
        if not product or product.upper() == 'NAN':
            continue
        
        parties = ['Arun Bhai', 'Sanjay', 'Shailesh S', 'Sandeep', 'Vijay', 'Manish', 'Suresh', 'Vilas', 'Sunil', 'Vachan sing']
        
        for party in parties:
            if party in df.columns:
                qty = row.get(party)
                if pd.notna(qty) and isinstance(qty, (int, float)) and qty > 0:
                    execute_query("INSERT OR IGNORE INTO party_master (party_name) VALUES (?)", (party,))
                    
                    if sheet_type == 'MR':
                        execute_query('''INSERT INTO market_rejection_register 
                            (date, party_name, product_name, qty_rejected)
                            VALUES (?, ?, ?, ?)''',
                            (datetime.now().strftime('%Y-%m-%d'), party, product, float(qty)))
                    else:
                        execute_query('''INSERT INTO party_rejection_register 
                            (date, party_name, product_name, qty_rejected)
                            VALUES (?, ?, ?, ?)''',
                            (datetime.now().strftime('%Y-%m-%d'), party, product, float(qty)))
                    
                    records_imported += 1
    
    return records_imported

def load_excel_data(file):
    messages = []
    try:
        xls = pd.ExcelFile(file)
        
        if 'RM' in xls.sheet_names:
            rm_df = pd.read_excel(xls, 'RM', header=0)
            rm_count = import_rm_sheet(rm_df)
            messages.append(f"✅ RM Sheet: {rm_count} purchase records imported")
        
        if 'FG' in xls.sheet_names:
            fg_df = pd.read_excel(xls, 'FG', header=0)
            fg_count = import_fg_sheet(fg_df)
            messages.append(f"✅ FG Sheet: {fg_count} production/sales records imported")
        
        if 'MR' in xls.sheet_names:
            mr_df = pd.read_excel(xls, 'MR', header=0)
            mr_count = import_mr_pr_sheets(mr_df, 'MR')
            messages.append(f"✅ MR Sheet: {mr_count} market rejection records imported")
        
        if 'PR' in xls.sheet_names:
            pr_df = pd.read_excel(xls, 'PR', header=0)
            pr_count = import_mr_pr_sheets(pr_df, 'PR')
            messages.append(f"✅ PR Sheet: {pr_count} party rejection records imported")
        
        return messages
    except Exception as e:
        return [f"❌ Error importing Excel: {str(e)}"]

def export_to_excel():
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_rm = fetch_data("SELECT * FROM rm_inventory ORDER BY product_name")
        df_rm.to_excel(writer, sheet_name='RM Inventory', index=False)
        
        df_fg = fetch_data("SELECT * FROM fg_inventory ORDER BY product_name")
        df_fg.to_excel(writer, sheet_name='FG Inventory', index=False)
        
        df_pur = fetch_data("SELECT * FROM purchase_transactions ORDER BY date DESC")
        df_pur.to_excel(writer, sheet_name='Purchases', index=False)
        
        df_sal = fetch_data("SELECT * FROM sales_transactions ORDER BY date DESC")
        df_sal.to_excel(writer, sheet_name='Sales', index=False)
        
        df_prod = fetch_data("SELECT * FROM production_register ORDER BY date DESC")
        df_prod.to_excel(writer, sheet_name='Production', index=False)
        
        df_mr = fetch_data("SELECT * FROM market_rejection_register ORDER BY date DESC")
        df_mr.to_excel(writer, sheet_name='Market Rejections', index=False)
        
        df_pr = fetch_data("SELECT * FROM party_rejection_register ORDER BY date DESC")
        df_pr.to_excel(writer, sheet_name='Party Rejections', index=False)
    
    output.seek(0)
    return output

# ======================= STREAMLIT APP =======================
st.set_page_config(
    page_title="Jinay ERP System",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        padding: 1rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: white;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        text-align: center;
        border-left: 5px solid #667eea;
    }
    .metric-value {
        font-size: 2rem;
        font-weight: bold;
        color: #667eea;
    }
    .metric-label {
        font-size: 0.9rem;
        color: #666;
        margin-top: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

init_db()

# ======================= SIDEBAR =======================
with st.sidebar:
    st.image("https://img.icons8.com/color/96/000000/enterprise.png", width=80)
    st.markdown("## 🏭 Jinay ERP")
    st.markdown("---")
    
    page = st.radio(
        "Navigation",
        ["📊 Dashboard", "📦 Masters", "🛒 Purchase Entry", "🏭 Production Entry", 
         "💰 Sales Entry", "⚠️ Rejections", "📈 Inventory", "📋 Reports", "📤 Import/Export"],
        index=0
    )
    
    st.markdown("---")
    st.caption(f"Last Updated: {datetime.now().strftime('%d-%m-%Y %H:%M')}")

# ======================= DASHBOARD =======================
if page == "📊 Dashboard":
    st.markdown('<h1 class="main-header">🏭 Jinay ERP Dashboard</h1>', unsafe_allow_html=True)
    
    df_rm_products = fetch_data("SELECT COUNT(*) as count FROM rm_master")
    df_fg_products = fetch_data("SELECT COUNT(*) as count FROM fg_master")
    df_total_production = fetch_data("SELECT SUM(qty_produced) as total FROM production_register")
    df_total_sales = fetch_data("SELECT SUM(qty) as total_qty FROM sales_transactions WHERE is_market_rejection=0")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("RM Products", df_rm_products['count'].iloc[0] if not df_rm_products.empty else 0)
    with col2:
        st.metric("FG Products", df_fg_products['count'].iloc[0] if not df_fg_products.empty else 0)
    with col3:
        val = df_total_production['total'].iloc[0] if not df_total_production.empty and pd.notna(df_total_production['total'].iloc[0]) else 0
        st.metric("Total Production", f"{val:,.0f}")
    with col4:
        val = df_total_sales['total_qty'].iloc[0] if not df_total_sales.empty and pd.notna(df_total_sales['total_qty'].iloc[0]) else 0
        st.metric("Total Sales", f"{val:,.0f}")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 Production vs Sales")
        df_chart = fetch_data("""
            SELECT DATE(date) as date, SUM(qty_produced) as production
            FROM production_register GROUP BY DATE(date)
        """)
        if not df_chart.empty:
            st.line_chart(df_chart.set_index('date')['production'])
        else:
            st.info("No production data")
    
    with col2:
        st.subheader("🏆 Top Contractors")
        df_contractors_prod = fetch_data("""
            SELECT contractor_name, SUM(qty_produced) as total_produced
            FROM production_register
            GROUP BY contractor_name
            ORDER BY total_produced DESC
            LIMIT 10
        """)
        if not df_contractors_prod.empty:
            st.bar_chart(df_contractors_prod.set_index('contractor_name')['total_produced'])
        else:
            st.info("No contractor data")
    
    st.subheader("📋 Recent Activity")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**Recent Purchases**")
        df_recent_pur = fetch_data("SELECT challan_no, date, product_name, qty FROM purchase_transactions ORDER BY date DESC LIMIT 5")
        if not df_recent_pur.empty:
            st.dataframe(df_recent_pur, use_container_width=True)
    
    with col2:
        st.markdown("**Recent Production**")
        df_recent_prod = fetch_data("SELECT contractor_name, fg_product, qty_produced, date FROM production_register ORDER BY date DESC LIMIT 5")
        if not df_recent_prod.empty:
            st.dataframe(df_recent_prod, use_container_width=True)
    
    with col3:
        st.markdown("**Recent Sales**")
        df_recent_sal = fetch_data("SELECT party_name, product_name, qty, date FROM sales_transactions WHERE is_market_rejection=0 ORDER BY date DESC LIMIT 5")
        if not df_recent_sal.empty:
            st.dataframe(df_recent_sal, use_container_width=True)

# ======================= MASTERS =======================
elif page == "📦 Masters":
    st.subheader("📦 Master Management")
    
    tab1, tab2, tab3, tab4 = st.tabs(["👥 Parties", "📦 RM Products", "🏭 FG Products", "🔧 Contractors"])
    
    with tab1:
        st.markdown("### Add New Party")
        col1, col2 = st.columns(2)
        with col1:
            party_name = st.text_input("Party Name *", key="party_name")
            contact_person = st.text_input("Contact Person", key="party_contact_person")
            phone = st.text_input("Phone", key="party_phone")
        with col2:
            address = st.text_area("Address", key="party_address")
            email = st.text_input("Email", key="party_email")
            gst_no = st.text_input("GST Number", key="party_gst_no")
        
        if st.button("Add Party", type="primary", key="add_party_btn"):
            if party_name:
                try:
                    execute_query('''INSERT INTO party_master 
                        (party_name, contact_person, phone, address, email, gst_no)
                        VALUES (?, ?, ?, ?, ?, ?)''',
                        (party_name, contact_person, phone, address, email, gst_no))
                    st.success(f"✅ Party '{party_name}' added successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
            else:
                st.warning("Please enter party name")
        
        st.markdown("### Party List")
        df_parties = fetch_data("SELECT * FROM party_master ORDER BY party_name")
        if not df_parties.empty:
            st.dataframe(df_parties, use_container_width=True)
    
    with tab2:
        st.markdown("### Add RM Product")
        col1, col2 = st.columns(2)
        with col1:
            rm_name = st.text_input("Product Name *", key="rm_name")
            rm_category = st.text_input("Category", key="rm_category")
            rm_unit = st.text_input("Unit", value="PCS", key="rm_unit")
        with col2:
            rm_rate = st.number_input("Rate", min_value=0.0, step=0.01, key="rm_rate")
            rm_weight = st.number_input("Per Pc Weight", min_value=0.0, step=0.001, key="rm_weight")
            rm_desc = st.text_area("Description", key="rm_desc")
        
        if st.button("Add RM Product", type="primary", key="add_rm_btn"):
            if rm_name:
                try:
                    execute_query('''INSERT INTO rm_master 
                        (product_name, category, unit, rate, per_pc_wt, description)
                        VALUES (?, ?, ?, ?, ?, ?)''',
                        (rm_name, rm_category, rm_unit, rm_rate, rm_weight, rm_desc))
                    execute_query("INSERT OR IGNORE INTO rm_inventory (product_name) VALUES (?)", (rm_name,))
                    st.success(f"✅ RM Product '{rm_name}' added successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
            else:
                st.warning("Please enter product name")
        
        st.markdown("### RM Products List")
        df_rm = fetch_data("SELECT * FROM rm_master ORDER BY product_name")
        if not df_rm.empty:
            st.dataframe(df_rm, use_container_width=True)
    
    with tab3:
        st.markdown("### Add FG Product")
        col1, col2 = st.columns(2)
        with col1:
            fg_name = st.text_input("Product Name *", key="fg_name")
            fg_category = st.text_input("Category", key="fg_category")
            fg_unit = st.text_input("Unit", value="PCS", key="fg_unit")
            fg_rate = st.number_input("Rate", min_value=0.0, step=0.01, key="fg_rate")
        with col2:
            fg_holder = st.text_input("Holder Name", key="fg_holder")
            fg_plate = st.text_input("Plate Name", key="fg_plate")
            fg_jb = st.text_input("JB Name", key="fg_jb")
            fg_rm_req = st.text_area("RM Required (comma separated)", key="fg_rm_req")
        
        if st.button("Add FG Product", type="primary", key="add_fg_btn"):
            if fg_name:
                try:
                    execute_query('''INSERT INTO fg_master 
                        (product_name, category, unit, rate, holder_name, plate_name, jb_name, rm_required)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                        (fg_name, fg_category, fg_unit, fg_rate, fg_holder, fg_plate, fg_jb, fg_rm_req))
                    execute_query("INSERT OR IGNORE INTO fg_inventory (product_name) VALUES (?)", (fg_name,))
                    st.success(f"✅ FG Product '{fg_name}' added successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
            else:
                st.warning("Please enter product name")
        
        st.markdown("### FG Products List")
        df_fg = fetch_data("SELECT * FROM fg_master ORDER BY product_name")
        if not df_fg.empty:
            st.dataframe(df_fg, use_container_width=True)
    
    with tab4:
        st.markdown("### Add Contractor")
        col1, col2 = st.columns(2)
        with col1:
            cont_name = st.text_input("Contractor Name *", key="cont_name")
            cont_person = st.text_input("Contact Person", key="cont_person")
            cont_phone = st.text_input("Phone", key="cont_phone")
        with col2:
            cont_address = st.text_area("Address", key="cont_address")
            cont_gst = st.text_input("GST Number", key="cont_gst")
        
        if st.button("Add Contractor", type="primary", key="add_contractor_btn"):
            if cont_name:
                try:
                    execute_query('''INSERT INTO contractor_master 
                        (contractor_name, contact_person, phone, address, gst_no)
                        VALUES (?, ?, ?, ?, ?)''',
                        (cont_name, cont_person, cont_phone, cont_address, cont_gst))
                    st.success(f"✅ Contractor '{cont_name}' added successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
            else:
                st.warning("Please enter contractor name")
        
        st.markdown("### Contractors List")
        df_cont = fetch_data("SELECT * FROM contractor_master ORDER BY contractor_name")
        if not df_cont.empty:
            st.dataframe(df_cont, use_container_width=True)

# ======================= PURCHASE ENTRY =======================
elif page == "🛒 Purchase Entry":
    st.subheader("🛒 Purchase Entry (RM)")
    
    df_cont = fetch_data("SELECT contractor_name FROM contractor_master ORDER BY contractor_name")
    df_rm = fetch_data("SELECT product_name, rate FROM rm_master ORDER BY product_name")
    
    contractor_list = df_cont['contractor_name'].tolist() if not df_cont.empty else []
    rm_list = df_rm['product_name'].tolist() if not df_rm.empty else []
    rm_rates = dict(zip(df_rm['product_name'], df_rm['rate'])) if not df_rm.empty else {}
    
    with st.form("purchase_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            challan_no = st.text_input("Challan No *")
            purchase_date = st.date_input("Date", datetime.now())
            contractor = st.selectbox("Contractor", contractor_list)
        
        with col2:
            product = st.selectbox("RM Product", rm_list)
            qty = st.number_input("Quantity *", min_value=0.0, step=1.0)
            rate = st.number_input("Rate per Unit", min_value=0.0, value=rm_rates.get(product, 0.0), step=0.01)
        
        with col3:
            if qty and rate:
                amount = qty * rate
                st.metric("Total Amount", f"₹{amount:,.2f}")
        
        submitted = st.form_submit_button("Save Purchase", type="primary")
        
        if submitted:
            if all([challan_no, contractor, product, qty > 0]):
                try:
                    execute_query('''INSERT INTO purchase_transactions 
                        (challan_no, date, contractor_name, product_name, qty, rate, amount, entry_type)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'PURCHASE')''',
                        (challan_no, purchase_date.strftime('%Y-%m-%d'), contractor, product, qty, rate, qty*rate))
                    execute_query("INSERT OR IGNORE INTO rm_inventory (product_name) VALUES (?)", (product,))
                    update_rm_inventory(product, qty, 'PURCHASE')
                    st.success("✅ Purchase entry saved successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
            else:
                st.warning("Please fill all required fields")
    
    st.markdown("### Recent Purchases")
    df_purchases = fetch_data("SELECT challan_no, date, contractor_name, product_name, qty, rate, amount FROM purchase_transactions ORDER BY date DESC LIMIT 50")
    if not df_purchases.empty:
        st.dataframe(df_purchases, use_container_width=True)
        st.metric("Total Purchase Value", f"₹{df_purchases['amount'].sum():,.2f}")

# ======================= PRODUCTION ENTRY =======================
elif page == "🏭 Production Entry":
    st.subheader("🏭 Production Entry (FG)")
    
    df_cont = fetch_data("SELECT contractor_name FROM contractor_master ORDER BY contractor_name")
    df_fg = fetch_data("SELECT product_name FROM fg_master ORDER BY product_name")
    
    contractor_list = df_cont['contractor_name'].tolist() if not df_cont.empty else []
    fg_list = df_fg['product_name'].tolist() if not df_fg.empty else []
    
    with st.form("production_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            prod_date = st.date_input("Date", datetime.now())
            contractor = st.selectbox("Contractor", contractor_list)
            fg_product = st.selectbox("FG Product", fg_list)
        
        with col2:
            qty_produced = st.number_input("Quantity Produced *", min_value=0.0, step=1.0)
            dp_part_fitting = st.number_input("DP Part Fitting", min_value=0.0, step=1.0)
            dp_action = st.number_input("DP Action", min_value=0.0, step=1.0)
        
        with col3:
            rm_consumed = st.text_area("RM Consumed (Product:Qty, comma separated)")
        
        submitted = st.form_submit_button("Save Production", type="primary")
        
        if submitted:
            if all([contractor, fg_product, qty_produced > 0]):
                try:
                    execute_query('''INSERT INTO production_register 
                        (date, contractor_name, fg_product, qty_produced, dp_part_fitting, dp_action, rm_consumed)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''',
                        (prod_date.strftime('%Y-%m-%d'), contractor, fg_product, qty_produced, 
                         dp_part_fitting, dp_action, rm_consumed))
                    execute_query("INSERT OR IGNORE INTO fg_inventory (product_name) VALUES (?)", (fg_product,))
                    update_fg_inventory(fg_product, qty_produced, 'PRODUCE')
                    
                    if rm_consumed:
                        for item in rm_consumed.split(','):
                            if ':' in item:
                                rm_prod, rm_qty = item.strip().split(':')
                                update_rm_inventory(rm_prod.strip(), float(rm_qty.strip()), 'CONSUME')
                    
                    st.success("✅ Production entry saved successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
            else:
                st.warning("Please fill all required fields")
    
    st.markdown("### Recent Production")
    df_prod = fetch_data("SELECT date, contractor_name, fg_product, qty_produced, dp_part_fitting, dp_action FROM production_register ORDER BY date DESC LIMIT 50")
    if not df_prod.empty:
        st.dataframe(df_prod, use_container_width=True)

# ======================= SALES ENTRY =======================
elif page == "💰 Sales Entry":
    st.subheader("💰 Sales Entry (FG)")
    
    df_parties = fetch_data("SELECT party_name FROM party_master ORDER BY party_name")
    df_fg = fetch_data("SELECT product_name, rate FROM fg_master ORDER BY product_name")
    
    party_list = df_parties['party_name'].tolist() if not df_parties.empty else []
    fg_list = df_fg['product_name'].tolist() if not df_fg.empty else []
    fg_rates = dict(zip(df_fg['product_name'], df_fg['rate'])) if not df_fg.empty else {}
    
    with st.form("sales_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            challan_no = st.text_input("Challan No *")
            sales_date = st.date_input("Date", datetime.now())
            party = st.selectbox("Party", party_list)
        
        with col2:
            product = st.selectbox("FG Product", fg_list)
            qty = st.number_input("Quantity *", min_value=0.0, step=1.0)
            rate = st.number_input("Rate per Unit", min_value=0.0, value=fg_rates.get(product, 0.0), step=0.01)
        
        with col3:
            is_rejection = st.checkbox("Market Rejection")
            if qty and rate:
                amount = qty * rate
                st.metric("Total Amount", f"₹{amount:,.2f}")
        
        rejection_reason = st.text_area("Rejection Reason") if is_rejection else None
        
        submitted = st.form_submit_button("Save Sale", type="primary")
        
        if submitted:
            if all([challan_no, party, product, qty > 0]):
                df_stock = fetch_data("SELECT closing_stock FROM fg_inventory WHERE product_name = ?", (product,))
                available = df_stock['closing_stock'].iloc[0] if not df_stock.empty else 0
                
                if available < qty and not is_rejection:
                    st.warning(f"⚠️ Insufficient stock! Available: {available:.0f}, Requested: {qty:.0f}")
                else:
                    try:
                        execute_query('''INSERT INTO sales_transactions 
                            (challan_no, date, party_name, product_name, qty, rate, amount, is_market_rejection, rejection_reason)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                            (challan_no, sales_date.strftime('%Y-%m-%d'), party, product, qty, rate, qty*rate,
                             1 if is_rejection else 0, rejection_reason))
                        execute_query("INSERT OR IGNORE INTO fg_inventory (product_name) VALUES (?)", (product,))
                        update_fg_inventory(product, qty, 'SALE')
                        
                        if is_rejection:
                            execute_query('''INSERT INTO market_rejection_register 
                                (date, party_name, product_name, qty_rejected, reason, challan_ref)
                                VALUES (?, ?, ?, ?, ?, ?)''',
                                (sales_date.strftime('%Y-%m-%d'), party, product, qty, rejection_reason, challan_no))
                        
                        st.success("✅ Sale entry saved successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
            else:
                st.warning("Please fill all required fields")
    
    st.markdown("### Recent Sales")
    df_sales = fetch_data("SELECT challan_no, date, party_name, product_name, qty, rate, amount, is_market_rejection FROM sales_transactions ORDER BY date DESC LIMIT 50")
    if not df_sales.empty:
        st.dataframe(df_sales, use_container_width=True)
        total_sales = df_sales[df_sales['is_market_rejection']==0]['amount'].sum()
        st.metric("Total Sales Value", f"₹{total_sales:,.2f}")

# ======================= REJECTIONS =======================
elif page == "⚠️ Rejections":
    st.subheader("⚠️ Rejection Management")
    
    tab1, tab2 = st.tabs(["Market Rejection", "Party Rejection"])
    
    df_parties = fetch_data("SELECT party_name FROM party_master")
    df_products = fetch_data("SELECT product_name FROM fg_master")
    party_list = df_parties['party_name'].tolist() if not df_parties.empty else []
    product_list = df_products['product_name'].tolist() if not df_products.empty else []
    
    with tab1:
        st.markdown("### Add Market Rejection")
        with st.form("mr_form"):
            col1, col2 = st.columns(2)
            with col1:
                mr_date = st.date_input("Date", datetime.now(), key="mr_date")
                mr_party = st.selectbox("Party", party_list, key="mr_party")
                mr_product = st.selectbox("Product", product_list, key="mr_product")
            with col2:
                mr_qty = st.number_input("Qty Rejected *", min_value=0.0, step=1.0, key="mr_qty")
                mr_reason = st.text_area("Reason", key="mr_reason")
                mr_challan = st.text_input("Challan Ref", key="mr_challan")
            
            submitted = st.form_submit_button("Save Market Rejection", type="primary")
            
            if submitted:
                if all([mr_product, mr_qty > 0]):
                    try:
                        execute_query('''INSERT INTO market_rejection_register 
                            (date, party_name, product_name, qty_rejected, reason, challan_ref)
                            VALUES (?, ?, ?, ?, ?, ?)''',
                            (mr_date.strftime('%Y-%m-%d'), mr_party, mr_product, mr_qty, mr_reason, mr_challan))
                        execute_query("INSERT OR IGNORE INTO fg_inventory (product_name) VALUES (?)", (mr_product,))
                        update_fg_inventory(mr_product, mr_qty, 'REJECT')
                        st.success("✅ Market rejection saved successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
                else:
                    st.warning("Please fill all required fields")
        
        st.markdown("### Market Rejection Records")
        df_mr = fetch_data("SELECT date, party_name, product_name, qty_rejected, reason, challan_ref FROM market_rejection_register ORDER BY date DESC LIMIT 50")
        if not df_mr.empty:
            st.dataframe(df_mr, use_container_width=True)
    
    with tab2:
        st.markdown("### Add Party Rejection")
        with st.form("pr_form"):
            col1, col2 = st.columns(2)
            with col1:
                pr_date = st.date_input("Date", datetime.now(), key="pr_date")
                pr_party = st.selectbox("Party", party_list, key="pr_party")
                pr_product = st.selectbox("Product", product_list, key="pr_product2")
            with col2:
                pr_qty = st.number_input("Qty Rejected *", min_value=0.0, step=1.0, key="pr_qty")
                pr_reason = st.text_area("Reason", key="pr_reason")
                pr_challan = st.text_input("Challan Ref", key="pr_challan")
            
            submitted = st.form_submit_button("Save Party Rejection", type="primary")
            
            if submitted:
                if all([pr_party, pr_product, pr_qty > 0]):
                    try:
                        execute_query('''INSERT INTO party_rejection_register 
                            (date, party_name, product_name, qty_rejected, reason, challan_ref)
                            VALUES (?, ?, ?, ?, ?, ?)''',
                            (pr_date.strftime('%Y-%m-%d'), pr_party, pr_product, pr_qty, pr_reason, pr_challan))
                        st.success("✅ Party rejection saved successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
                else:
                    st.warning("Please fill all required fields")
        
        st.markdown("### Party Rejection Records")
        df_pr = fetch_data("SELECT date, party_name, product_name, qty_rejected, reason, challan_ref FROM party_rejection_register ORDER BY date DESC LIMIT 50")
        if not df_pr.empty:
            st.dataframe(df_pr, use_container_width=True)

# ======================= INVENTORY =======================
elif page == "📈 Inventory":
    st.subheader("📈 Inventory Management")
    
    tab1, tab2 = st.tabs(["RM Inventory", "FG Inventory"])
    
    with tab1:
        st.markdown("### RM (Raw Material) Inventory")
        df_rm_inv = fetch_data("""
            SELECT i.product_name, i.opening_stock, i.purchased_qty, i.consumed_qty, i.closing_stock, m.rate, m.unit
            FROM rm_inventory i LEFT JOIN rm_master m ON i.product_name = m.product_name ORDER BY i.product_name
        """)
        
        if not df_rm_inv.empty:
            col1, col2, col3 = st.columns(3)
            with col1: st.metric("Total RM Products", len(df_rm_inv))
            with col2: st.metric("Total Stock Value", f"₹{(df_rm_inv['closing_stock'] * df_rm_inv['rate'].fillna(0)).sum():,.2f}")
            with col3: st.metric("Total Purchased", f"{df_rm_inv['purchased_qty'].sum():,.0f}")
            
            st.dataframe(df_rm_inv, use_container_width=True)
            
            st.markdown("### Update Opening Stock")
            col1, col2 = st.columns(2)
            with col1: rm_product = st.selectbox("Select RM Product", df_rm_inv['product_name'].tolist())
            with col2: new_opening = st.number_input("New Opening Stock", min_value=0.0, step=1.0)
            
            if st.button("Update Opening Stock", type="primary"):
                if rm_product:
                    execute_query("UPDATE rm_inventory SET opening_stock = ? WHERE product_name = ?", (new_opening, rm_product))
                    execute_query("UPDATE rm_inventory SET closing_stock = opening_stock + purchased_qty - consumed_qty WHERE product_name = ?", (rm_product,))
                    st.success("✅ Opening stock updated!")
                    st.rerun()
        else:
            st.info("No RM inventory data available")
    
    with tab2:
        st.markdown("### FG (Finished Goods) Inventory")
        df_fg_inv = fetch_data("""
            SELECT i.product_name, i.opening_stock, i.produced_qty, i.sold_qty, i.rejected_qty, i.closing_stock, m.rate, m.unit
            FROM fg_inventory i LEFT JOIN fg_master m ON i.product_name = m.product_name ORDER BY i.product_name
        """)
        
        if not df_fg_inv.empty:
            col1, col2, col3 = st.columns(3)
            with col1: st.metric("Total FG Products", len(df_fg_inv))
            with col2: st.metric("Total Stock Value", f"₹{(df_fg_inv['closing_stock'] * df_fg_inv['rate'].fillna(0)).sum():,.2f}")
            with col3: st.metric("Total Produced", f"{df_fg_inv['produced_qty'].sum():,.0f}")
            
            st.dataframe(df_fg_inv, use_container_width=True)
            
            st.markdown("### Update Opening Stock")
            col1, col2 = st.columns(2)
            with col1: fg_product = st.selectbox("Select FG Product", df_fg_inv['product_name'].tolist())
            with col2: new_opening = st.number_input("New Opening Stock", min_value=0.0, step=1.0)
            
            if st.button("Update Opening Stock", type="primary"):
                if fg_product:
                    execute_query("UPDATE fg_inventory SET opening_stock = ? WHERE product_name = ?", (new_opening, fg_product))
                    execute_query("UPDATE fg_inventory SET closing_stock = opening_stock + produced_qty - sold_qty - rejected_qty WHERE product_name = ?", (fg_product,))
                    st.success("✅ Opening stock updated!")
                    st.rerun()
        else:
            st.info("No FG inventory data available")

# ======================= REPORTS =======================
elif page == "📋 Reports":
    st.subheader("📋 Reports & Analytics")
    
    report_type = st.selectbox("Select Report Type",
        ["Production Summary", "Sales Summary", "Purchase Summary", 
         "Contractor Performance", "Party-wise Sales", "Rejection Analysis", "Stock Movement"])
    
    if report_type == "Production Summary":
        st.markdown("### Production Summary Report")
        df = fetch_data("""
            SELECT fg_product, COUNT(*) as production_days, SUM(qty_produced) as total_produced, AVG(qty_produced) as avg_daily
            FROM production_register GROUP BY fg_product ORDER BY total_produced DESC
        """)
        if not df.empty:
            st.dataframe(df, use_container_width=True)
            st.bar_chart(df.set_index('fg_product')['total_produced'])
        else:
            st.info("No production data available")
    
    elif report_type == "Sales Summary":
        st.markdown("### Sales Summary Report")
        df = fetch_data("""
            SELECT product_name, COUNT(*) as transactions, SUM(qty) as total_qty, SUM(amount) as total_amount
            FROM sales_transactions WHERE is_market_rejection = 0 GROUP BY product_name ORDER BY total_amount DESC
        """)
        if not df.empty:
            st.dataframe(df, use_container_width=True)
            st.bar_chart(df.set_index('product_name')['total_amount'])
        else:
            st.info("No sales data available")
    
    elif report_type == "Contractor Performance":
        st.markdown("### Contractor Performance Report")
        df = fetch_data("""
            SELECT contractor_name, COUNT(DISTINCT DATE(date)) as working_days, SUM(qty_produced) as total_produced
            FROM production_register GROUP BY contractor_name ORDER BY total_produced DESC
        """)
        if not df.empty:
            st.dataframe(df, use_container_width=True)
            st.bar_chart(df.set_index('contractor_name')['total_produced'])
        else:
            st.info("No production data available")
    
    elif report_type == "Party-wise Sales":
        st.markdown("### Party-wise Sales Report")
        df = fetch_data("""
            SELECT party_name, COUNT(*) as transactions, SUM(qty) as total_qty, SUM(amount) as total_amount
            FROM sales_transactions WHERE is_market_rejection = 0 GROUP BY party_name ORDER BY total_amount DESC
        """)
        if not df.empty:
            st.dataframe(df, use_container_width=True)
            st.bar_chart(df.set_index('party_name')['total_amount'])
        else:
            st.info("No sales data available")
    
    elif report_type == "Rejection Analysis":
        st.markdown("### Rejection Analysis Report")
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Market Rejections by Product**")
            df_mr = fetch_data("SELECT product_name, SUM(qty_rejected) as total_rejected FROM market_rejection_register GROUP BY product_name ORDER BY total_rejected DESC")
            if not df_mr.empty:
                st.dataframe(df_mr, use_container_width=True)
                st.bar_chart(df_mr.set_index('product_name')['total_rejected'])
        
        with col2:
            st.markdown("**Party Rejections by Product**")
            df_pr = fetch_data("SELECT product_name, SUM(qty_rejected) as total_rejected FROM party_rejection_register GROUP BY product_name ORDER BY total_rejected DESC")
            if not df_pr.empty:
                st.dataframe(df_pr, use_container_width=True)
                st.bar_chart(df_pr.set_index('product_name')['total_rejected'])
    
    elif report_type == "Stock Movement":
        st.markdown("### Stock Movement Report")
        tab1, tab2 = st.tabs(["RM Movement", "FG Movement"])
        
        with tab1:
            df = fetch_data("SELECT product_name, opening_stock, purchased_qty as additions, consumed_qty as deductions, closing_stock FROM rm_inventory ORDER BY product_name")
            if not df.empty:
                st.dataframe(df, use_container_width=True)
        
        with tab2:
            df = fetch_data("SELECT product_name, opening_stock, produced_qty as additions, (sold_qty + rejected_qty) as deductions, closing_stock FROM fg_inventory ORDER BY product_name")
            if not df.empty:
                st.dataframe(df, use_container_width=True)

# ======================= IMPORT/EXPORT =======================
elif page == "📤 Import/Export":
    st.subheader("📤 Data Import/Export")
    
    tab1, tab2 = st.tabs(["Import Excel", "Export Data"])
    
    with tab1:
        st.markdown("### Import Data from Excel")
        uploaded_file = st.file_uploader("Choose Excel file", type=['xlsx', 'xls'])
        
        if uploaded_file is not None:
            if st.button("Import Data", type="primary"):
                with st.spinner("Importing data..."):
                    messages = load_excel_data(uploaded_file)
                    for msg in messages:
                        if "✅" in msg: st.success(msg)
                        elif "❌" in msg: st.error(msg)
                    st.success("✅ Import completed!")
                    if st.button("Refresh"): st.rerun()
    
    with tab2:
        st.markdown("### Export All Data to Excel")
        if st.button("Generate Excel Export", type="primary"):
            try:
                excel_data = export_to_excel()
                st.download_button(
                    label="📥 Download Excel File",
                    data=excel_data,
                    file_name=f"jinay_erp_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                st.success("✅ Excel file generated successfully!")
            except Exception as e:
                st.error(f"❌ Error generating export: {str(e)}")

# Footer
st.markdown("---")
st.caption("© 2026 Jinay ERP System | Built with Streamlit | SQLite Database")
