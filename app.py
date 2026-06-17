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
        category TEXT,
        contact_person TEXT,
        phone TEXT,
        email TEXT,
        address TEXT,
        gst_no TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Combined Product Master (RM, FG, Moulding, Powder)
    cursor.execute('''CREATE TABLE IF NOT EXISTS product_master (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_name TEXT UNIQUE NOT NULL,
        category TEXT NOT NULL,
        unit TEXT DEFAULT 'PCS',
        rate REAL DEFAULT 0,
        per_pc_wt REAL,
        dimension_h REAL,
        dimension_w REAL,
        dimension_l REAL,
        description TEXT,
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
        party_name TEXT,
        product_name TEXT NOT NULL,
        category TEXT,
        product_category TEXT,
        qty REAL NOT NULL,
        unit TEXT,
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
        category TEXT,
        product_category TEXT,
        qty REAL NOT NULL,
        unit TEXT,
        rate REAL DEFAULT 0,
        amount REAL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS production_register (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        challan_no TEXT,
        date TEXT NOT NULL,
        party_name TEXT,
        fg_product TEXT NOT NULL,
        product_category TEXT,
        produced_qty REAL NOT NULL,
        unit TEXT,
        description TEXT,
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
    
    # Inventory Tables - Track overall stock per product
    cursor.execute('''CREATE TABLE IF NOT EXISTS rm_inventory (
        product_name TEXT PRIMARY KEY,
        opening_stock REAL DEFAULT 0,
        total_purchased_qty REAL DEFAULT 0,
        total_consumed_qty REAL DEFAULT 0,
        closing_stock REAL DEFAULT 0,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # RM Stock Movement - Track each transaction separately with running balance
    cursor.execute('''CREATE TABLE IF NOT EXISTS rm_stock_movement (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_date TEXT NOT NULL,
        challan_no TEXT,
        product_name TEXT NOT NULL,
        transaction_type TEXT NOT NULL,
        qty REAL NOT NULL,
        opening_balance REAL DEFAULT 0,
        closing_balance REAL DEFAULT 0,
        reference_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS fg_inventory (
        product_name TEXT PRIMARY KEY,
        opening_stock REAL DEFAULT 0,
        produced_qty REAL DEFAULT 0,
        sold_qty REAL DEFAULT 0,
        rejected_qty REAL DEFAULT 0,
        closing_stock REAL DEFAULT 0,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    conn.commit()
    
    # Run migration to handle schema changes
    migrate_database(cursor)
    
    conn.commit()
    conn.close()

def migrate_database(cursor):
    """Migrate database schema to handle column name changes"""
    try:
        # Check if old columns exist in rm_inventory
        cursor.execute("PRAGMA table_info(rm_inventory)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # If old column names exist, rename them
        if 'purchased_qty' in columns and 'total_purchased_qty' not in columns:
            cursor.execute("ALTER TABLE rm_inventory RENAME COLUMN purchased_qty TO total_purchased_qty")
            print("✅ Migrated: purchased_qty -> total_purchased_qty")
        
        if 'consumed_qty' in columns and 'total_consumed_qty' not in columns:
            cursor.execute("ALTER TABLE rm_inventory RENAME COLUMN consumed_qty TO total_consumed_qty")
            print("✅ Migrated: consumed_qty -> total_consumed_qty")
            
        # Add product_category column if not exists
        cursor.execute("PRAGMA table_info(purchase_transactions)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'product_category' not in columns:
            cursor.execute("ALTER TABLE purchase_transactions ADD COLUMN product_category TEXT")
            print("✅ Added product_category to purchase_transactions")
        
        cursor.execute("PRAGMA table_info(sales_transactions)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'product_category' not in columns:
            cursor.execute("ALTER TABLE sales_transactions ADD COLUMN product_category TEXT")
            print("✅ Added product_category to sales_transactions")
        
        cursor.execute("PRAGMA table_info(production_register)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'product_category' not in columns:
            cursor.execute("ALTER TABLE production_register ADD COLUMN product_category TEXT")
            print("✅ Added product_category to production_register")
        
        if 'party_name' not in columns:
            cursor.execute("ALTER TABLE production_register ADD COLUMN party_name TEXT")
            print("✅ Added party_name to production_register")
            
    except Exception as e:
        print(f"Migration warning: {e}")

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

def calculate_rm_opening_balance(product_name, before_date=None):
    """Calculate opening balance for a product up to a specific date"""
    if before_date:
        query = """
            SELECT COALESCE(SUM(CASE WHEN transaction_type='PURCHASE' THEN qty 
                                    WHEN transaction_type='CONSUMPTION' THEN -qty 
                                    ELSE 0 END), 0) as balance
            FROM rm_stock_movement 
            WHERE product_name = ? AND transaction_date < ?
        """
        result = fetch_data(query, (product_name, before_date))
    else:
        query = """
            SELECT COALESCE(SUM(CASE WHEN transaction_type='PURCHASE' THEN qty 
                                    WHEN transaction_type='CONSUMPTION' THEN -qty 
                                    ELSE 0 END), 0) as balance
            FROM rm_stock_movement 
            WHERE product_name = ?
        """
        result = fetch_data(query, (product_name,))
    
    return result['balance'].iloc[0] if not result.empty else 0

def update_rm_inventory(product, qty, transaction_type='PURCHASE', transaction_date=None, challan_no=None, reference_id=None):
    """Update RM inventory with proper running balance tracking"""
    
    # Calculate opening balance before this transaction
    opening_balance = calculate_rm_opening_balance(product, transaction_date)
    
    # Calculate closing balance
    if transaction_type == 'PURCHASE':
        closing_balance = opening_balance + qty
        # Update total purchased
        execute_query("UPDATE rm_inventory SET total_purchased_qty = total_purchased_qty + ? WHERE product_name = ?", (qty, product))
    elif transaction_type == 'CONSUMPTION':
        closing_balance = opening_balance - qty
        # Update total consumed
        execute_query("UPDATE rm_inventory SET total_consumed_qty = total_consumed_qty + ? WHERE product_name = ?", (qty, product))
    else:
        closing_balance = opening_balance
    
    # Record the movement
    execute_query('''INSERT INTO rm_stock_movement 
        (transaction_date, challan_no, product_name, transaction_type, qty, opening_balance, closing_balance, reference_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (transaction_date, challan_no, product, transaction_type, qty, opening_balance, closing_balance, reference_id))
    
    # Update closing stock in main inventory
    execute_query("UPDATE rm_inventory SET closing_stock = ? WHERE product_name = ?", (closing_balance, product))
    
    return closing_balance

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
                execute_query("INSERT OR IGNORE INTO product_master (product_name, category) VALUES (?, 'RM Product')", (product,))
                execute_query("INSERT OR IGNORE INTO rm_inventory (product_name) VALUES (?)", (product,))
                
                # Insert purchase transaction
                purchase_id = execute_query('''INSERT INTO purchase_transactions 
                    (challan_no, date, party_name, product_name, qty, entry_type)
                    VALUES (?, ?, ?, ?, ?, 'PURCHASE')''',
                    (challan_no, date, contractor, product, float(qty)))
                
                # Update inventory with running balance
                update_rm_inventory(product, float(qty), 'PURCHASE', date, challan_no, purchase_id)
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
        
        execute_query("INSERT OR IGNORE INTO product_master (product_name, category) VALUES (?, 'FG Product')", (product,))
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
                    execute_query("INSERT OR IGNORE INTO party_master (party_name, category) VALUES (?, 'Sales Party')", (party,))
                    execute_query('''INSERT INTO sales_transactions 
                        (challan_no, date, party_name, product_name, qty)
                        VALUES (?, ?, ?, ?, ?)''',
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
    .edit-btn {
        background-color: #4CAF50;
        color: white;
        border: none;
        padding: 5px 10px;
        margin: 2px;
        border-radius: 3px;
        cursor: pointer;
    }
    .delete-btn {
        background-color: #f44336;
        color: white;
        border: none;
        padding: 5px 10px;
        margin: 2px;
        border-radius: 3px;
        cursor: pointer;
    }
</style>
""", unsafe_allow_html=True)

init_db()

# Initialize session state for edit mode
if 'edit_mode' not in st.session_state:
    st.session_state.edit_mode = False
if 'edit_id' not in st.session_state:
    st.session_state.edit_id = None
if 'edit_table' not in st.session_state:
    st.session_state.edit_table = None

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
    
    df_rm_products = fetch_data("SELECT COUNT(*) as count FROM product_master WHERE category='RM Product'")
    df_fg_products = fetch_data("SELECT COUNT(*) as count FROM product_master WHERE category IN ('FG Product', 'Moulding Product', 'Powder')")
    df_total_production = fetch_data("SELECT SUM(qty_produced) as total FROM production_register")
    df_total_sales = fetch_data("SELECT SUM(qty) as total_qty FROM sales_transactions")
    
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
        df_recent_sal = fetch_data("SELECT party_name, product_name, qty, date FROM sales_transactions ORDER BY date DESC LIMIT 5")
        if not df_recent_sal.empty:
            st.dataframe(df_recent_sal, use_container_width=True)

# ======================= MASTERS =======================
elif page == "📦 Masters":
    st.subheader("📦 Master Management")
    
    tab1, tab2, tab3 = st.tabs(["👥 Parties", "📦 Products", "🔧 Contractors"])
    
    with tab1:
        st.markdown("### Add New Party")
        col1, col2 = st.columns(2)
        with col1:
            party_name = st.text_input("Party Name *", key="party_name")
            party_category = st.selectbox("Category", ["Purchase Party", "Moulder", "Sales Party", "Contractor", "Powder"], key="party_category")
            contact_person = st.text_input("Contact Person", key="party_contact_person")
            phone = st.text_input("Phone", key="party_phone")
        with col2:
            email = st.text_input("Email", key="party_email")
            address = st.text_area("Address", key="party_address")
            gst_no = st.text_input("GST Number", key="party_gst_no")
        
        if st.button("Add Party", type="primary", key="add_party_btn"):
            if party_name:
                try:
                    execute_query('''INSERT INTO party_master 
                        (party_name, category, contact_person, phone, email, address, gst_no)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''',
                        (party_name, party_category, contact_person, phone, email, address, gst_no))
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
            
            st.markdown("### Edit/Delete Party")
            col1, col2 = st.columns(2)
            with col1:
                party_to_edit = st.selectbox("Select Party to Edit/Delete", df_parties['party_name'].tolist(), key="select_party_edit")
            with col2:
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("✏️ Edit", key="edit_party_btn"):
                        st.session_state.edit_mode = True
                        st.session_state.edit_id = party_to_edit
                        st.session_state.edit_table = 'party'
                        st.rerun()
                with col_b:
                    if st.button("🗑️ Delete", key="delete_party_btn"):
                        execute_query("DELETE FROM party_master WHERE party_name = ?", (party_to_edit,))
                        st.success("✅ Party deleted!")
                        st.rerun()
            
            # Edit form
            if st.session_state.edit_mode and st.session_state.edit_table == 'party':
                st.markdown("### Edit Party")
                party_data = fetch_data("SELECT * FROM party_master WHERE party_name = ?", (st.session_state.edit_id,))
                if not party_data.empty:
                    with st.form("edit_party_form"):
                        col1, col2 = st.columns(2)
                        with col1:
                            edit_party_name = st.text_input("Party Name", value=party_data['party_name'].iloc[0], key="edit_party_name_field")
                            edit_party_category = st.selectbox("Category", ["Purchase Party", "Moulder", "Sales Party", "Contractor", "Powder"], 
                                                              index=["Purchase Party", "Moulder", "Sales Party", "Contractor", "Powder"].index(party_data['category'].iloc[0]) if party_data['category'].iloc[0] in ["Purchase Party", "Moulder", "Sales Party", "Contractor", "Powder"] else 0, 
                                                              key="edit_party_category_field")
                            edit_contact_person = st.text_input("Contact Person", value=party_data['contact_person'].iloc[0] if pd.notna(party_data['contact_person'].iloc[0]) else "", key="edit_party_contact_field")
                            edit_phone = st.text_input("Phone", value=party_data['phone'].iloc[0] if pd.notna(party_data['phone'].iloc[0]) else "", key="edit_party_phone_field")
                        with col2:
                            edit_email = st.text_input("Email", value=party_data['email'].iloc[0] if pd.notna(party_data['email'].iloc[0]) else "", key="edit_party_email_field")
                            edit_address = st.text_area("Address", value=party_data['address'].iloc[0] if pd.notna(party_data['address'].iloc[0]) else "", key="edit_party_address_field")
                            edit_gst_no = st.text_input("GST Number", value=party_data['gst_no'].iloc[0] if pd.notna(party_data['gst_no'].iloc[0]) else "", key="edit_party_gst_field")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.form_submit_button("💾 Save Changes", type="primary"):
                                execute_query('''UPDATE party_master SET 
                                    party_name=?, category=?, contact_person=?, phone=?, email=?, address=?, gst_no=?
                                    WHERE party_name=?''',
                                    (edit_party_name, edit_party_category, edit_contact_person, edit_phone, edit_email, edit_address, edit_gst_no, st.session_state.edit_id))
                                st.success("✅ Party updated successfully!")
                                st.session_state.edit_mode = False
                                st.session_state.edit_id = None
                                st.rerun()
                        with col2:
                            if st.form_submit_button("❌ Cancel"):
                                st.session_state.edit_mode = False
                                st.session_state.edit_id = None
                                st.rerun()
    
    with tab2:
        st.markdown("### Add Product")
        col1, col2 = st.columns(2)
        with col1:
            product_name = st.text_input("Product Name *", key="product_name")
            product_category = st.selectbox("Category", ["RM Product", "FG Product", "Moulding Product", "Powder"], key="product_category")
            unit = st.text_input("Unit", value="PCS", key="product_unit")
            rate = st.number_input("Rate", min_value=0.0, step=0.01, key="product_rate")
        with col2:
            per_pc_wt = st.number_input("Per Pc Weight", min_value=0.0, step=0.001, key="product_weight")
            dim_h = st.number_input("Dimension H", min_value=0.0, step=0.01, key="product_dim_h")
            dim_w = st.number_input("Dimension W", min_value=0.0, step=0.01, key="product_dim_w")
            dim_l = st.number_input("Dimension L", min_value=0.0, step=0.01, key="product_dim_l")
            description = st.text_area("Description", key="product_desc")
        
        if st.button("Add Product", type="primary", key="add_product_btn"):
            if product_name:
                try:
                    execute_query('''INSERT INTO product_master 
                        (product_name, category, unit, rate, per_pc_wt, dimension_h, dimension_w, dimension_l, description)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                        (product_name, product_category, unit, rate, per_pc_wt, dim_h, dim_w, dim_l, description))
                    
                    # Add to appropriate inventory
                    if product_category == 'RM Product':
                        execute_query("INSERT OR IGNORE INTO rm_inventory (product_name) VALUES (?)", (product_name,))
                    else:
                        execute_query("INSERT OR IGNORE INTO fg_inventory (product_name) VALUES (?)", (product_name,))
                    
                    st.success(f"✅ Product '{product_name}' added successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
            else:
                st.warning("Please enter product name")
        
        st.markdown("### Products List")
        df_products = fetch_data("SELECT * FROM product_master ORDER BY product_name")
        if not df_products.empty:
            st.dataframe(df_products, use_container_width=True)
            
            st.markdown("### Edit/Delete Product")
            col1, col2 = st.columns(2)
            with col1:
                product_to_edit = st.selectbox("Select Product to Edit/Delete", df_products['product_name'].tolist(), key="select_product_edit")
            with col2:
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("✏️ Edit", key="edit_product_btn"):
                        st.session_state.edit_mode = True
                        st.session_state.edit_id = product_to_edit
                        st.session_state.edit_table = 'product'
                        st.rerun()
                with col_b:
                    if st.button("🗑️ Delete", key="delete_product_btn"):
                        execute_query("DELETE FROM product_master WHERE product_name = ?", (product_to_edit,))
                        st.success("✅ Product deleted!")
                        st.rerun()
            
            # Edit form
            if st.session_state.edit_mode and st.session_state.edit_table == 'product':
                st.markdown("### Edit Product")
                product_data = fetch_data("SELECT * FROM product_master WHERE product_name = ?", (st.session_state.edit_id,))
                if not product_data.empty:
                    with st.form("edit_product_form"):
                        col1, col2 = st.columns(2)
                        with col1:
                            edit_product_name = st.text_input("Product Name", value=product_data['product_name'].iloc[0], key="edit_product_name_field")
                            edit_product_category = st.selectbox("Category", ["RM Product", "FG Product", "Moulding Product", "Powder"], 
                                                                index=["RM Product", "FG Product", "Moulding Product", "Powder"].index(product_data['category'].iloc[0]) if product_data['category'].iloc[0] in ["RM Product", "FG Product", "Moulding Product", "Powder"] else 0, 
                                                                key="edit_product_category_field")
                            edit_unit = st.text_input("Unit", value=product_data['unit'].iloc[0] if pd.notna(product_data['unit'].iloc[0]) else "PCS", key="edit_product_unit_field")
                            edit_rate = st.number_input("Rate", min_value=0.0, value=float(product_data['rate'].iloc[0]) if pd.notna(product_data['rate'].iloc[0]) else 0.0, step=0.01, key="edit_product_rate_field")
                        with col2:
                            edit_per_pc_wt = st.number_input("Per Pc Weight", min_value=0.0, value=float(product_data['per_pc_wt'].iloc[0]) if pd.notna(product_data['per_pc_wt'].iloc[0]) else 0.0, step=0.001, key="edit_product_weight_field")
                            edit_dim_h = st.number_input("Dimension H", min_value=0.0, value=float(product_data['dimension_h'].iloc[0]) if pd.notna(product_data['dimension_h'].iloc[0]) else 0.0, step=0.01, key="edit_product_dim_h_field")
                            edit_dim_w = st.number_input("Dimension W", min_value=0.0, value=float(product_data['dimension_w'].iloc[0]) if pd.notna(product_data['dimension_w'].iloc[0]) else 0.0, step=0.01, key="edit_product_dim_w_field")
                            edit_dim_l = st.number_input("Dimension L", min_value=0.0, value=float(product_data['dimension_l'].iloc[0]) if pd.notna(product_data['dimension_l'].iloc[0]) else 0.0, step=0.01, key="edit_product_dim_l_field")
                            edit_description = st.text_area("Description", value=product_data['description'].iloc[0] if pd.notna(product_data['description'].iloc[0]) else "", key="edit_product_desc_field")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.form_submit_button("💾 Save Changes", type="primary"):
                                execute_query('''UPDATE product_master SET 
                                    product_name=?, category=?, unit=?, rate=?, per_pc_wt=?, dimension_h=?, dimension_w=?, dimension_l=?, description=?
                                    WHERE product_name=?''',
                                    (edit_product_name, edit_product_category, edit_unit, edit_rate, edit_per_pc_wt, edit_dim_h, edit_dim_w, edit_dim_l, edit_description, st.session_state.edit_id))
                                st.success("✅ Product updated successfully!")
                                st.session_state.edit_mode = False
                                st.session_state.edit_id = None
                                st.rerun()
                        with col2:
                            if st.form_submit_button("❌ Cancel"):
                                st.session_state.edit_mode = False
                                st.session_state.edit_id = None
                                st.rerun()
    
    with tab3:
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
            
            st.markdown("### Edit/Delete Contractor")
            col1, col2 = st.columns(2)
            with col1:
                cont_to_edit = st.selectbox("Select Contractor to Edit/Delete", df_cont['contractor_name'].tolist(), key="select_cont_edit")
            with col2:
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("✏️ Edit", key="edit_cont_btn"):
                        st.session_state.edit_mode = True
                        st.session_state.edit_id = cont_to_edit
                        st.session_state.edit_table = 'contractor'
                        st.rerun()
                with col_b:
                    if st.button("🗑️ Delete", key="delete_cont_btn"):
                        execute_query("DELETE FROM contractor_master WHERE contractor_name = ?", (cont_to_edit,))
                        st.success("✅ Contractor deleted!")
                        st.rerun()
            
            # Edit form
            if st.session_state.edit_mode and st.session_state.edit_table == 'contractor':
                st.markdown("### Edit Contractor")
                cont_data = fetch_data("SELECT * FROM contractor_master WHERE contractor_name = ?", (st.session_state.edit_id,))
                if not cont_data.empty:
                    with st.form("edit_contractor_form"):
                        col1, col2 = st.columns(2)
                        with col1:
                            edit_cont_name = st.text_input("Contractor Name", value=cont_data['contractor_name'].iloc[0], key="edit_cont_name_field")
                            edit_cont_person = st.text_input("Contact Person", value=cont_data['contact_person'].iloc[0] if pd.notna(cont_data['contact_person'].iloc[0]) else "", key="edit_cont_person_field")
                            edit_cont_phone = st.text_input("Phone", value=cont_data['phone'].iloc[0] if pd.notna(cont_data['phone'].iloc[0]) else "", key="edit_cont_phone_field")
                        with col2:
                            edit_cont_address = st.text_area("Address", value=cont_data['address'].iloc[0] if pd.notna(cont_data['address'].iloc[0]) else "", key="edit_cont_address_field")
                            edit_cont_gst = st.text_input("GST Number", value=cont_data['gst_no'].iloc[0] if pd.notna(cont_data['gst_no'].iloc[0]) else "", key="edit_cont_gst_field")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.form_submit_button("💾 Save Changes", type="primary"):
                                execute_query('''UPDATE contractor_master SET 
                                    contractor_name=?, contact_person=?, phone=?, address=?, gst_no=?
                                    WHERE contractor_name=?''',
                                    (edit_cont_name, edit_cont_person, edit_cont_phone, edit_cont_address, edit_cont_gst, st.session_state.edit_id))
                                st.success("✅ Contractor updated successfully!")
                                st.session_state.edit_mode = False
                                st.session_state.edit_id = None
                                st.rerun()
                        with col2:
                            if st.form_submit_button("❌ Cancel"):
                                st.session_state.edit_mode = False
                                st.session_state.edit_id = None
                                st.rerun()

# ======================= PURCHASE ENTRY =======================
elif page == "🛒 Purchase Entry":
    st.subheader("🛒 Purchase Entry")
    
    # Get all party types for purchase
    df_parties = fetch_data("""
        SELECT party_name FROM party_master 
        WHERE category IN ('Purchase Party', 'Moulder', 'Contractor', 'Powder') 
        ORDER BY party_name
    """)
    df_products = fetch_data("SELECT product_name, rate, unit, category FROM product_master ORDER BY product_name")
    
    party_list = df_parties['party_name'].tolist() if not df_parties.empty else []
    product_list = df_products['product_name'].tolist() if not df_products.empty else []
    product_rates = dict(zip(df_products['product_name'], df_products['rate'])) if not df_products.empty else {}
    product_units = dict(zip(df_products['product_name'], df_products['unit'])) if not df_products.empty else {}
    product_categories = dict(zip(df_products['product_name'], df_products['category'])) if not df_products.empty else {}
    
    # Unit options
    unit_options = ["kg", "Gross", "g", "Pcs", "PCS"]
    
    with st.form("purchase_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            challan_no = st.text_input("Challan No *")
            purchase_date = st.date_input("Date", datetime.now())
            party = st.selectbox("Party/Moulder/Contractor", party_list if party_list else ["No parties added yet"])
        
        with col2:
            product = st.selectbox("Product", product_list if product_list else ["No products added yet"])
            category = st.selectbox("Category", ["Party", "Moulder", "Contractor", "Powder"])
            product_category = st.selectbox("Product Category", ["FG Product", "Moulding Product", "RM Product", "Powder"], 
                                           index=["FG Product", "Moulding Product", "RM Product", "Powder"].index(product_categories.get(product, "RM Product")) if product_categories.get(product, "RM Product") in ["FG Product", "Moulding Product", "RM Product", "Powder"] else 2)
            qty = st.number_input("Quantity *", min_value=0.0, step=1.0)
        
        with col3:
            unit = st.selectbox("Unit", unit_options, index=unit_options.index(product_units.get(product, 'PCS')) if product_units.get(product, 'PCS') in unit_options else 4)
            rate = st.number_input("Rate per Unit", min_value=0.0, value=product_rates.get(product, 0.0), step=0.01)
            if qty and rate:
                amount = qty * rate
                st.metric("Total Amount", f"₹{amount:,.2f}")
        
        submitted = st.form_submit_button("Save Purchase", type="primary")
        
        if submitted:
            if all([challan_no, party and party != "No parties added yet", product and product != "No products added yet", qty > 0]):
                try:
                    # Insert purchase transaction
                    purchase_id = execute_query('''INSERT INTO purchase_transactions 
                        (challan_no, date, party_name, product_name, category, product_category, qty, unit, rate, amount, entry_type)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PURCHASE')''',
                        (challan_no, purchase_date.strftime('%Y-%m-%d'), party, product, category, product_category, qty, unit, rate, qty*rate))
                    
                    execute_query("INSERT OR IGNORE INTO rm_inventory (product_name) VALUES (?)", (product,))
                    
                    # Update inventory with running balance
                    update_rm_inventory(product, qty, 'PURCHASE', purchase_date.strftime('%Y-%m-%d'), challan_no, purchase_id)
                    
                    st.success("✅ Purchase entry saved successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
            else:
                st.warning("Please fill all required fields")
    
    st.markdown("### Recent Purchases")
    df_purchases = fetch_data("SELECT challan_no, date, party_name, product_name, category, product_category, qty, unit, rate, amount FROM purchase_transactions ORDER BY date DESC LIMIT 50")
    if not df_purchases.empty:
        st.dataframe(df_purchases, use_container_width=True)
        st.metric("Total Purchase Value", f"₹{df_purchases['amount'].sum():,.2f}")

# ======================= PRODUCTION ENTRY =======================
elif page == "🏭 Production Entry":
    st.subheader("🏭 Production Entry")
    
    # Get all party types (Party, Moulder, Contractor)
    df_parties = fetch_data("""
        SELECT party_name FROM party_master 
        WHERE category IN ('Purchase Party', 'Moulder', 'Contractor', 'Powder') 
        ORDER BY party_name
    """)
    df_products = fetch_data("SELECT product_name, unit, category FROM product_master ORDER BY product_name")
    
    party_list = df_parties['party_name'].tolist() if not df_parties.empty else []
    product_list = df_products['product_name'].tolist() if not df_products.empty else []
    product_units = dict(zip(df_products['product_name'], df_products['unit'])) if not df_products.empty else {}
    product_categories = dict(zip(df_products['product_name'], df_products['category'])) if not df_products.empty else {}
    
    # Unit options
    unit_options = ["kg", "Gross", "g", "Pcs", "PCS"]
    
    with st.form("production_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            challan_no = st.text_input("Challan No")
            prod_date = st.date_input("Date", datetime.now())
            party_name = st.selectbox("Party/Moulder/Contractor", party_list if party_list else ["No parties added yet"])
        
        with col2:
            fg_product = st.selectbox("Product", product_list if product_list else ["No products added yet"])
            product_category = st.selectbox("Product Category", ["FG Product", "Moulding Product", "RM Product", "Powder"], 
                                           index=["FG Product", "Moulding Product", "RM Product", "Powder"].index(product_categories.get(fg_product, "FG Product")) if product_categories.get(fg_product, "FG Product") in ["FG Product", "Moulding Product", "RM Product", "Powder"] else 0)
            produced_qty = st.number_input("Produced Qty *", min_value=0.0, step=1.0)
            unit = st.selectbox("Unit", unit_options, index=unit_options.index(product_units.get(fg_product, 'PCS')) if product_units.get(fg_product, 'PCS') in unit_options else 4)
        
        with col3:
            description = st.text_area("Description")
        
        submitted = st.form_submit_button("Save Production", type="primary")
        
        if submitted:
            if all([party_name and party_name != "No parties added yet", fg_product and fg_product != "No products added yet", produced_qty > 0]):
                try:
                    execute_query('''INSERT INTO production_register 
                        (challan_no, date, party_name, fg_product, product_category, produced_qty, unit, description)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                        (challan_no, prod_date.strftime('%Y-%m-%d'), party_name, fg_product, product_category, produced_qty, unit, description))
                    execute_query("INSERT OR IGNORE INTO fg_inventory (product_name) VALUES (?)", (fg_product,))
                    update_fg_inventory(fg_product, produced_qty, 'PRODUCE')
                    
                    st.success("✅ Production entry saved successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
            else:
                st.warning("Please fill all required fields")
    
    st.markdown("### Recent Production")
    df_prod = fetch_data("SELECT challan_no, date, party_name, fg_product, product_category, produced_qty, unit, description FROM production_register ORDER BY date DESC LIMIT 50")
    if not df_prod.empty:
        st.dataframe(df_prod, use_container_width=True)

# ======================= SALES ENTRY =======================
elif page == "💰 Sales Entry":
    st.subheader("💰 Sales Entry")
    
    # Get all party types for sales
    df_parties = fetch_data("""
        SELECT party_name FROM party_master 
        WHERE category IN ('Sales Party', 'Moulder', 'Contractor', 'Powder', 'Purchase Party') 
        ORDER BY party_name
    """)
    df_products = fetch_data("SELECT product_name, rate, unit, category FROM product_master ORDER BY product_name")
    
    party_list = df_parties['party_name'].tolist() if not df_parties.empty else []
    product_list = df_products['product_name'].tolist() if not df_products.empty else []
    product_rates = dict(zip(df_products['product_name'], df_products['rate'])) if not df_products.empty else {}
    product_units = dict(zip(df_products['product_name'], df_products['unit'])) if not df_products.empty else {}
    product_categories = dict(zip(df_products['product_name'], df_products['category'])) if not df_products.empty else {}
    
    # Unit options
    unit_options = ["kg", "Gross", "g", "Pcs", "PCS"]
    
    with st.form("sales_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            challan_no = st.text_input("Challan No *")
            sales_date = st.date_input("Date", datetime.now())
            party = st.selectbox("Sales Party", party_list if party_list else ["No parties added yet"])
        
        with col2:
            product = st.selectbox("Product", product_list if product_list else ["No products added yet"])
            category = st.selectbox("Category", ["Party", "Moulder", "Contractor", "Powder"])
            product_category = st.selectbox("Product Category", ["FG Product", "Moulding Product", "RM Product", "Powder"], 
                                           index=["FG Product", "Moulding Product", "RM Product", "Powder"].index(product_categories.get(product, "FG Product")) if product_categories.get(product, "FG Product") in ["FG Product", "Moulding Product", "RM Product", "Powder"] else 0)
            qty = st.number_input("Quantity *", min_value=0.0, step=1.0)
        
        with col3:
            unit = st.selectbox("Unit", unit_options, index=unit_options.index(product_units.get(product, 'PCS')) if product_units.get(product, 'PCS') in unit_options else 4)
            rate = st.number_input("Rate per Unit", min_value=0.0, value=product_rates.get(product, 0.0), step=0.01)
            if qty and rate:
                amount = qty * rate
                st.metric("Total Amount", f"₹{amount:,.2f}")
        
        submitted = st.form_submit_button("Save Sale", type="primary")
        
        if submitted:
            if all([challan_no, party and party != "No parties added yet", product and product != "No products added yet", qty > 0]):
                df_stock = fetch_data("SELECT closing_stock FROM fg_inventory WHERE product_name = ?", (product,))
                available = df_stock['closing_stock'].iloc[0] if not df_stock.empty else 0
                
                if available < qty:
                    st.warning(f"⚠️ Insufficient stock! Available: {available:.0f}, Requested: {qty:.0f}")
                else:
                    try:
                        execute_query('''INSERT INTO sales_transactions 
                            (challan_no, date, party_name, product_name, category, product_category, qty, unit, rate, amount)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                            (challan_no, sales_date.strftime('%Y-%m-%d'), party, product, category, product_category, qty, unit, rate, qty*rate))
                        execute_query("INSERT OR IGNORE INTO fg_inventory (product_name) VALUES (?)", (product,))
                        update_fg_inventory(product, qty, 'SALE')
                        
                        st.success("✅ Sale entry saved successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
            else:
                st.warning("Please fill all required fields")
    
    st.markdown("### Recent Sales")
    df_sales = fetch_data("SELECT challan_no, date, party_name, product_name, category, product_category, qty, unit, rate, amount FROM sales_transactions ORDER BY date DESC LIMIT 50")
    if not df_sales.empty:
        st.dataframe(df_sales, use_container_width=True)
        st.metric("Total Sales Value", f"₹{df_sales['amount'].sum():,.2f}")

# ======================= REJECTIONS =======================
elif page == "⚠️ Rejections":
    st.subheader("⚠️ Rejection Management")
    
    tab1, tab2 = st.tabs(["Market Rejection", "Party Rejection"])
    
    df_parties = fetch_data("SELECT party_name FROM party_master")
    df_products = fetch_data("SELECT product_name FROM product_master")
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
    
    tab1, tab2, tab3 = st.tabs(["RM Inventory Summary", "RM Stock Movement", "FG Inventory"])
    
    with tab1:
        st.markdown("### RM (Raw Material) Inventory Summary")
        df_rm_inv = fetch_data("""
            SELECT i.product_name, i.opening_stock, i.total_purchased_qty, i.total_consumed_qty, i.closing_stock, m.rate, m.unit
            FROM rm_inventory i LEFT JOIN product_master m ON i.product_name = m.product_name 
            WHERE m.category='RM Product' OR m.category IS NULL
            ORDER BY i.product_name
        """)
        
        if not df_rm_inv.empty:
            col1, col2, col3 = st.columns(3)
            with col1: st.metric("Total RM Products", len(df_rm_inv))
            with col2: st.metric("Total Stock Value", f"₹{(df_rm_inv['closing_stock'] * df_rm_inv['rate'].fillna(0)).sum():,.2f}")
            with col3: st.metric("Total Purchased", f"{df_rm_inv['total_purchased_qty'].sum():,.0f}")
            
            st.dataframe(df_rm_inv, use_container_width=True)
            
            st.markdown("### Update Opening Stock")
            col1, col2 = st.columns(2)
            with col1: rm_product = st.selectbox("Select RM Product", df_rm_inv['product_name'].tolist())
            with col2: new_opening = st.number_input("New Opening Stock", min_value=0.0, step=1.0)
            
            if st.button("Update Opening Stock", type="primary"):
                if rm_product:
                    execute_query("UPDATE rm_inventory SET opening_stock = ? WHERE product_name = ?", (new_opening, rm_product))
                    # Recalculate closing stock
                    current_purchased = fetch_data("SELECT total_purchased_qty FROM rm_inventory WHERE product_name = ?", (rm_product,))['total_purchased_qty'].iloc[0]
                    current_consumed = fetch_data("SELECT total_consumed_qty FROM rm_inventory WHERE product_name = ?", (rm_product,))['total_consumed_qty'].iloc[0]
                    new_closing = new_opening + current_purchased - current_consumed
                    execute_query("UPDATE rm_inventory SET closing_stock = ? WHERE product_name = ?", (new_closing, rm_product))
                    st.success("✅ Opening stock updated!")
                    st.rerun()
        else:
            st.info("No RM inventory data available")
    
    with tab2:
        st.markdown("### RM Stock Movement (Detailed)")
        st.info("This shows each transaction with running balance")
        
        # Get unique products
        df_products = fetch_data("SELECT DISTINCT product_name FROM rm_stock_movement ORDER BY product_name")
        
        if not df_products.empty:
            selected_product = st.selectbox("Select Product to View Movement", df_products['product_name'].tolist())
            
            df_movement = fetch_data("""
                SELECT transaction_date, challan_no, transaction_type, qty, opening_balance, closing_balance
                FROM rm_stock_movement 
                WHERE product_name = ?
                ORDER BY transaction_date, id
            """, (selected_product,))
            
            if not df_movement.empty:
                st.dataframe(df_movement, use_container_width=True)
                
                # Show summary
                col1, col2, col3 = st.columns(3)
                total_purchases = df_movement[df_movement['transaction_type']=='PURCHASE']['qty'].sum()
                total_consumptions = df_movement[df_movement['transaction_type']=='CONSUMPTION']['qty'].sum()
                final_balance = df_movement['closing_balance'].iloc[-1]
                
                with col1: st.metric("Total Purchases", f"{total_purchases:,.0f}")
                with col2: st.metric("Total Consumptions", f"{total_consumptions:,.0f}")
                with col3: st.metric("Current Balance", f"{final_balance:,.0f}")
            else:
                st.info("No movement records for this product")
        else:
            st.info("No RM stock movement data available")
    
    with tab3:
        st.markdown("### FG (Finished Goods) Inventory")
        df_fg_inv = fetch_data("""
            SELECT i.product_name, i.opening_stock, i.produced_qty, i.sold_qty, i.rejected_qty, i.closing_stock, m.rate, m.unit
            FROM fg_inventory i LEFT JOIN product_master m ON i.product_name = m.product_name 
            WHERE m.category IN ('FG Product', 'Moulding Product', 'Powder') OR m.category IS NULL
            ORDER BY i.product_name
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
            SELECT fg_product, COUNT(*) as production_days, SUM(produced_qty) as total_produced, AVG(produced_qty) as avg_daily
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
            FROM sales_transactions GROUP BY product_name ORDER BY total_amount DESC
        """)
        if not df.empty:
            st.dataframe(df, use_container_width=True)
            st.bar_chart(df.set_index('product_name')['total_amount'])
        else:
            st.info("No sales data available")
    
    elif report_type == "Contractor Performance":
        st.markdown("### Contractor Performance Report")
        df = fetch_data("""
            SELECT party_name, COUNT(DISTINCT DATE(date)) as working_days, SUM(produced_qty) as total_produced
            FROM production_register GROUP BY party_name ORDER BY total_produced DESC
        """)
        if not df.empty:
            st.dataframe(df, use_container_width=True)
            st.bar_chart(df.set_index('party_name')['total_produced'])
        else:
            st.info("No production data available")
    
    elif report_type == "Party-wise Sales":
        st.markdown("### Party-wise Sales Report")
        df = fetch_data("""
            SELECT party_name, COUNT(*) as transactions, SUM(qty) as total_qty, SUM(amount) as total_amount
            FROM sales_transactions GROUP BY party_name ORDER BY total_amount DESC
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
            df = fetch_data("SELECT product_name, opening_stock, total_purchased_qty as additions, total_consumed_qty as deductions, closing_stock FROM rm_inventory ORDER BY product_name")
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
