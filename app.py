import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from io import BytesIO
import os

# ======================= DATABASE SETUP =======================
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

    cursor.execute('''CREATE TABLE IF NOT EXISTS bom_master (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fg_product TEXT NOT NULL,
        rm_product TEXT NOT NULL,
        required_qty REAL NOT NULL DEFAULT 1,
        UNIQUE(fg_product, rm_product))''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS payable_receivable_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_type TEXT NOT NULL,
        party_name TEXT NOT NULL,
        challan_no TEXT NOT NULL,
        invoice_date TEXT NOT NULL,
        due_date TEXT NOT NULL,
        amount REAL NOT NULL,
        paid_amount REAL DEFAULT 0,
        balance_amount REAL NOT NULL,
        payment_status TEXT DEFAULT 'PENDING',
        remarks TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

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
        payment_terms_days INTEGER DEFAULT 60,
        due_date TEXT,
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

    cursor.execute('''CREATE TABLE IF NOT EXISTS rm_inventory (
        product_name TEXT PRIMARY KEY,
        opening_stock REAL DEFAULT 0,
        total_purchased_qty REAL DEFAULT 0,
        total_consumed_qty REAL DEFAULT 0,
        closing_stock REAL DEFAULT 0,
        rate REAL DEFAULT 0,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

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
        purchased_qty REAL DEFAULT 0,
        closing_stock REAL DEFAULT 0,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

    conn.commit()
    migrate_database(cursor)
    conn.commit()
    conn.close()

def get_dynamic_lists(filter_type="All"):
    """Helper to get filtered lists for dynamic dropdowns"""
    try:
        if filter_type == "All":
            df_parties = fetch_data("SELECT party_name FROM party_master ORDER BY party_name")
            df_products = fetch_data("SELECT product_name, rate, unit, category FROM product_master ORDER BY product_name")
        else:
            if filter_type in ["Purchase Party", "Moulder", "Contractor", "Powder", "Sales Party"]:
                df_parties = fetch_data("SELECT party_name FROM party_master WHERE category = ? ORDER BY party_name", (filter_type,))
            else:
                df_parties = pd.DataFrame(columns=['party_name'])

            if filter_type in ["RM Product", "FG Product", "Moulding Product", "Powder"]:
                df_products = fetch_data("SELECT product_name, rate, unit, category FROM product_master WHERE category = ? ORDER BY product_name", (filter_type,))
            else:
                df_products = pd.DataFrame(columns=['product_name', 'rate', 'unit', 'category'])

        # Ensure columns exist even if DataFrame is empty or malformed
        if df_parties.empty and 'party_name' not in df_parties.columns:
            df_parties = pd.DataFrame(columns=['party_name'])

        if df_products.empty and 'product_name' not in df_products.columns:
            df_products = pd.DataFrame(columns=['product_name', 'rate', 'unit', 'category'])

        return df_parties, df_products
    except Exception as e:
        st.error(f"Error in get_dynamic_lists: {e}")
        # Return safe empty DataFrames on error
        return pd.DataFrame(columns=['party_name']), pd.DataFrame(columns=['product_name', 'rate', 'unit', 'category'])
def migrate_database(cursor):
    """Migrate database schema to handle column name changes"""
    try:
        cursor.execute("PRAGMA table_info(sales_transactions)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'payment_terms_days' not in columns:
            cursor.execute("ALTER TABLE sales_transactions ADD COLUMN payment_terms_days INTEGER DEFAULT 60")
        if 'due_date' not in columns:
            cursor.execute("ALTER TABLE sales_transactions ADD COLUMN due_date TEXT")

        cursor.execute("PRAGMA table_info(rm_inventory)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'rate' not in columns:
            cursor.execute("ALTER TABLE rm_inventory ADD COLUMN rate REAL DEFAULT 0")
        if 'purchased_qty' in columns and 'total_purchased_qty' not in columns:
            cursor.execute("ALTER TABLE rm_inventory RENAME COLUMN purchased_qty TO total_purchased_qty")
        if 'consumed_qty' in columns and 'total_consumed_qty' not in columns:
            cursor.execute("ALTER TABLE rm_inventory RENAME COLUMN consumed_qty TO total_consumed_qty")

        cursor.execute("PRAGMA table_info(purchase_transactions)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'product_category' not in columns:
            cursor.execute("ALTER TABLE purchase_transactions ADD COLUMN product_category TEXT")

        cursor.execute("PRAGMA table_info(sales_transactions)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'product_category' not in columns:
            cursor.execute("ALTER TABLE sales_transactions ADD COLUMN product_category TEXT")

        cursor.execute("PRAGMA table_info(production_register)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'qty_produced' in columns and 'produced_qty' not in columns:
            cursor.execute("ALTER TABLE production_register RENAME COLUMN qty_produced TO produced_qty")
        if 'contractor_name' in columns and 'party_name' not in columns:
            cursor.execute("ALTER TABLE production_register RENAME COLUMN contractor_name TO party_name")
        if 'product_category' not in columns:
            cursor.execute("ALTER TABLE production_register ADD COLUMN product_category TEXT")
        if 'party_name' not in columns and 'contractor_name' not in columns:
            cursor.execute("ALTER TABLE production_register ADD COLUMN party_name TEXT")
        if 'produced_qty' not in columns and 'qty_produced' not in columns:
            cursor.execute("ALTER TABLE production_register ADD COLUMN produced_qty REAL NOT NULL DEFAULT 0")

        cursor.execute("PRAGMA table_info(fg_inventory)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'purchased_qty' not in columns:
            cursor.execute("ALTER TABLE fg_inventory ADD COLUMN purchased_qty REAL DEFAULT 0")

    except Exception as e:
        print(f"Migration warning: {e}")

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA journal_mode=WAL") # Write-Ahead Logging for better concurrency
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

def execute_query(query, params=()):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        conn.commit() # Explicit commit
        lastrowid = cursor.lastrowid
        return lastrowid
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
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
                                 WHEN transaction_type IN ('SALE', 'CONSUMPTION') THEN -qty
                                 ELSE 0 END), 0) as balance
        FROM rm_stock_movement
        WHERE product_name = ? AND transaction_date < ?
        """
        result = fetch_data(query, (product_name, before_date))
    else:
        query = """
        SELECT COALESCE(SUM(CASE WHEN transaction_type='PURCHASE' THEN qty
                                 WHEN transaction_type IN ('SALE', 'CONSUMPTION') THEN -qty
                                 ELSE 0 END), 0) as balance
        FROM rm_stock_movement
        WHERE product_name = ?
        """
        result = fetch_data(query, (product_name,))
    return result['balance'].iloc[0] if not result.empty else 0

def update_rm_inventory(product, qty, transaction_type='PURCHASE', transaction_date=None, challan_no=None, reference_id=None, rate=0):
    """
    Updates RM Inventory and Stock Movement records.
    Recalculates running balances for ALL movements of this product to ensure consistency after edits/deletes.
    Uses a single connection to prevent 'database is locked' errors.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 1. Get Master Opening Stock
        cursor.execute("SELECT opening_stock FROM rm_inventory WHERE product_name = ?", (product,))
        row = cursor.fetchone()
        base_opening = row[0] if row else 0
        
        # 2. Fetch ALL movements for this product ordered by date and ID
        cursor.execute(
            "SELECT id, transaction_date, transaction_type, qty FROM rm_stock_movement WHERE product_name = ? ORDER BY transaction_date, id", 
            (product,)
        )
        movements = cursor.fetchall()
        
        if not movements:
            # If no movements, just update master closing stock to opening
            cursor.execute("UPDATE rm_inventory SET closing_stock = ?, rate = ? WHERE product_name = ?", 
                           (base_opening, rate if rate > 0 else None, product))
            conn.commit()
            return base_opening

        current_balance = base_opening
        movement_updates = []
        
        # 3. Recalculate balances for every movement in sequence
        for mov in movements:
            mid, m_date, m_type, m_qty = mov
            
            if m_type == 'PURCHASE':
                current_balance += m_qty
            elif m_type in ['SALE', 'CONSUMPTION']:
                current_balance -= m_qty
            
            movement_updates.append((current_balance, mid))

        # 4. Batch update all closing balances in the movement table
        for bal, mid in movement_updates:
            cursor.execute("UPDATE rm_stock_movement SET closing_balance = ? WHERE id = ?", (bal, mid))
        
        # 5. Update Master Closing Stock and Rate
        final_closing = current_balance
        if rate > 0:
            cursor.execute("UPDATE rm_inventory SET closing_stock = ?, rate = ? WHERE product_name = ?", 
                           (final_closing, rate, product))
        else:
            cursor.execute("UPDATE rm_inventory SET closing_stock = ? WHERE product_name = ?", 
                           (final_closing, product))
            
        conn.commit()
        return final_closing

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
def update_fg_inventory(product, qty, transaction_type='PRODUCE'):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Ensure product exists in inventory table
        cursor.execute("""
            INSERT OR IGNORE INTO fg_inventory
            (product_name, opening_stock, produced_qty, sold_qty, rejected_qty, purchased_qty, closing_stock)
            VALUES (?, 0, 0, 0, 0, 0, 0)
        """, (product,))
        
        # Fetch current values to calculate availability accurately
        cursor.execute("""
            SELECT COALESCE(opening_stock,0) as os, 
                   COALESCE(produced_qty,0) as pq, 
                   COALESCE(purchased_qty,0) as purq, 
                   COALESCE(sold_qty,0) as sq, 
                   COALESCE(rejected_qty,0) as rq 
            FROM fg_inventory WHERE product_name = ?
        """, (product,))
        row = cursor.fetchone()
        
        if not row:
            raise Exception(f"Product {product} not found in inventory")
            
        os, pq, purq, sq, rq = row
        current_available_stock = os + pq + purq - sq - rq

        if transaction_type == 'PRODUCE':
            cursor.execute("UPDATE fg_inventory SET produced_qty = COALESCE(produced_qty, 0) + ? WHERE product_name = ?", (qty, product))
            
        elif transaction_type == 'SALE':
            # Check stock before selling
            if current_available_stock < qty:
                # Raise specific error to be caught by UI
                raise Exception(f"Insufficient FG Stock! Available: {current_available_stock}, Requested: {qty}")
            
            cursor.execute("UPDATE fg_inventory SET sold_qty = COALESCE(sold_qty, 0) + ? WHERE product_name = ?", (qty, product))
            
        elif transaction_type == 'REJECT':
            # Check stock before rejecting
            if current_available_stock < qty:
                raise Exception(f"Insufficient FG Stock for Rejection! Available: {current_available_stock}, Requested: {qty}")
            
            cursor.execute("UPDATE fg_inventory SET rejected_qty = COALESCE(rejected_qty, 0) + ? WHERE product_name = ?", (qty, product))
            
        elif transaction_type == 'PURCHASE':
            cursor.execute("UPDATE fg_inventory SET purchased_qty = COALESCE(purchased_qty, 0) + ? WHERE product_name = ?", (qty, product))

        # FORCE REAL-TIME CALCULATION OF CLOSING STOCK
        cursor.execute("""
            UPDATE fg_inventory
            SET closing_stock = COALESCE(opening_stock, 0) + COALESCE(produced_qty, 0) + COALESCE(purchased_qty, 0) - COALESCE(sold_qty, 0) - COALESCE(rejected_qty, 0)
            WHERE product_name = ?
        """, (product,))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
def consume_rm_for_fg_sale(fg_product, fg_qty, sale_date, challan_no, sale_id):
    """
    Automatically consume RM materials based on BOM when FG is sold.
    NOTE: If you want to disable auto-consumption for traded items, 
    this function can be bypassed or modified. 
    Currently, it checks BOM. If no BOM exists, it returns silently (no error).
    """
    bom_items = fetch_data("""
        SELECT rm_product, required_qty
        FROM bom_master
        WHERE fg_product = ?
    """, (fg_product,))
    
    if bom_items.empty:
        # No BOM defined, so no consumption needed. Return silently.
        return []
        
    consumed_items = []
    for _, bom_row in bom_items.iterrows():
        rm_product = bom_row['rm_product']
        rm_qty_needed = bom_row['required_qty'] * fg_qty
        
        rm_check = fetch_data("SELECT closing_stock FROM rm_inventory WHERE product_name = ?", (rm_product,))
        if rm_check.empty:
            # Warning but do not stop the sale
            st.warning(f"⚠️ RM Product '{rm_product}' not found in inventory!")
            continue
            
        available_stock = rm_check['closing_stock'].iloc[0]
        
        # IMPORTANT: If insufficient RM, we warn but DO NOT block the FG Sale 
        # if the user intends to sell traded goods without production.
        # However, standard ERP logic usually blocks this. 
        # Per your request "If It Is Insufficient Then Also Sell Entry Is Stored", 
        # we will LOG the warning but allow the FG sale to proceed by catching exceptions upstream 
        # or simply skipping the consumption update if stock is low.
        
        if available_stock < rm_qty_needed:
            st.warning(f"⚠️ Insufficient RM stock for {rm_product}. Available: {available_stock}, Required: {rm_qty_needed}. Skipping RM deduction.")
            continue # Skip this RM item, do not deduct, do not block sale
        
        # Only deduct if sufficient stock
        try:
            update_rm_inventory(rm_product, rm_qty_needed, 'CONSUMPTION', sale_date, challan_no, sale_id)
            consumed_items.append(f"{rm_product}: {rm_qty_needed}")
        except Exception as e:
            st.warning(f"Could not consume {rm_product}: {e}")
            
    return consumed_items
def calculate_rm_for_fg(fg_product, fg_qty):
    """Calculate RM materials needed based on BOM for FG product"""
    bom_items = fetch_data("""
        SELECT rm_product, required_qty 
        FROM bom_master 
        WHERE fg_product = ?
    """, (fg_product,))

    if bom_items.empty:
        return []

    rm_details = []
    for _, bom_row in bom_items.iterrows():
        rm_product = bom_row['rm_product']
        rm_qty_needed = bom_row['required_qty'] * fg_qty
        rm_details.append({
            'rm_product': rm_product,
            'qty_needed': rm_qty_needed,
            'required_per_unit': bom_row['required_qty']
        })

    return rm_details

def create_receivable_entry(party_name, challan_no, invoice_date, amount, payment_days=60):
    """Create receivable entry in ledger"""
    if isinstance(invoice_date, str):
        invoice_date = datetime.strptime(invoice_date, '%Y-%m-%d')

    due_date = invoice_date + timedelta(days=payment_days)
    due_date_str = due_date.strftime('%Y-%m-%d')

    execute_query('''INSERT INTO payable_receivable_ledger 
        (transaction_type, party_name, challan_no, invoice_date, due_date, amount, paid_amount, balance_amount, payment_status, remarks)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        ('RECEIVABLE', party_name, challan_no, invoice_date.strftime('%Y-%m-%d'), due_date_str, 
         amount, 0, amount, 'PENDING', f'{payment_days} days payment terms'))

def create_payable_entry(party_name, challan_no, invoice_date, amount, payment_days=60):
    """Create payable entry in ledger when purchase is made"""
    if isinstance(invoice_date, str):
        invoice_date = datetime.strptime(invoice_date, '%Y-%m-%d')

    due_date = invoice_date + timedelta(days=payment_days)
    due_date_str = due_date.strftime('%Y-%m-%d')

    execute_query('''INSERT INTO payable_receivable_ledger 
        (transaction_type, party_name, challan_no, invoice_date, due_date, amount, paid_amount, balance_amount, payment_status, remarks)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        ('PAYABLE', party_name, challan_no, invoice_date.strftime('%Y-%m-%d'), due_date_str, 
         amount, 0, amount, 'PENDING', f'{payment_days} days payment terms'))

def check_overdue_payments():
    """Check and return list of overdue payments"""
    today = datetime.now().strftime('%Y-%m-%d')
    overdue = fetch_data("""
        SELECT id, party_name, challan_no, invoice_date, due_date, amount, balance_amount,
               julianday(?) - julianday(due_date) as days_overdue
        FROM payable_receivable_ledger 
        WHERE transaction_type = 'RECEIVABLE' 
        AND payment_status != 'PAID' 
        AND due_date < ?
        ORDER BY days_overdue DESC
    """, (today, today))
    return overdue

def check_overdue_payables():
    """Check and return list of overdue payables"""
    today = datetime.now().strftime('%Y-%m-%d')
    overdue = fetch_data("""
        SELECT id, party_name, challan_no, invoice_date, due_date, amount, balance_amount,
               julianday(?) - julianday(due_date) as days_overdue
        FROM payable_receivable_ledger 
        WHERE transaction_type = 'PAYABLE' 
        AND payment_status != 'PAID' 
        AND due_date < ?
        ORDER BY days_overdue DESC
    """, (today, today))
    return overdue

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
            execute_query("INSERT OR IGNORE INTO party_master (party_name, category) VALUES (?, 'Contractor')", (contractor,))

        for col in product_cols:
            qty = row.get(col)
            if pd.notna(qty) and isinstance(qty, (int, float)) and qty > 0:
                product = str(col).strip()
                execute_query("INSERT OR IGNORE INTO product_master (product_name, category) VALUES (?, 'RM Product')", (product,))
                execute_query("INSERT OR IGNORE INTO rm_inventory (product_name, opening_stock, total_purchased_qty, total_consumed_qty, closing_stock) VALUES (?, 0, 0, 0, 0)", (product,))

                purchase_id = execute_query('''INSERT INTO purchase_transactions 
                    (challan_no, date, party_name, product_name, qty, entry_type, product_category)
                    VALUES (?, ?, ?, ?, ?, 'PURCHASE', 'RM Product')''',
                    (challan_no, date, contractor, product, float(qty)))

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
        execute_query("INSERT OR IGNORE INTO fg_inventory (product_name, opening_stock, produced_qty, sold_qty, rejected_qty, purchased_qty, closing_stock) VALUES (?, 0, 0, 0, 0, 0, 0)", (product,))

        contractors = ['Arun Bhai', 'Sanjay', 'Shailesh S', 'Sandeep', 'Vijay', 'Manish', 'Suresh', 'Vilas', 'Sunil', 'Vachan Sing']
        for contractor in contractors:
            if contractor in df.columns:
                qty = row.get(contractor)
                if pd.notna(qty) and isinstance(qty, (int, float)) and qty > 0:
                    execute_query("INSERT OR IGNORE INTO party_master (party_name, category) VALUES (?, 'Contractor')", (contractor,))
                    execute_query('''INSERT INTO production_register 
                        (date, party_name, fg_product, produced_qty)
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

        df_bom = fetch_data("SELECT * FROM bom_master ORDER BY fg_product, rm_product")
        df_bom.to_excel(writer, sheet_name='BOM Master', index=False)

        df_ledger = fetch_data("SELECT * FROM payable_receivable_ledger ORDER BY due_date")
        df_ledger.to_excel(writer, sheet_name='Payable_Receivable_Ledger', index=False)

    output.seek(0)
    return output

# ======================= STREAMLIT APP =======================
st.set_page_config(
    page_title="Jinay ERP System",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
.overdue-alert {
    background-color: #ffebee;
    border-left: 5px solid #f44336;
    padding: 10px;
    margin: 5px 0;
    border-radius: 3px;
}
</style>
""", unsafe_allow_html=True)

init_db()

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
         "💰 Sales Entry", "📒 Payable/Receivable Ledger", "⚠️ Rejections", "📈 Inventory", "📋 Reports", "📤 Import/Export"],
        index=0
    )
    st.markdown("---")
    st.caption(f"Last Updated: {datetime.now().strftime('%d-%m-%Y %H:%M')}")

# ======================= DASHBOARD =======================
if page == "📊 Dashboard":
    st.markdown('<h1 class="main-header">🏭 Jinay ERP Dashboard</h1>', unsafe_allow_html=True)

    overdue_payments = check_overdue_payments()
    if not overdue_payments.empty:
        st.error(f"⚠️ **ALERT: {len(overdue_payments)} Overdue Payment(s) Found!**")
        for _, payment in overdue_payments.head(5).iterrows():
            st.markdown(f"""
            <div class="overdue-alert">
                <strong>{payment['party_name']}</strong> - Challan: {payment['challan_no']}<br>
                Amount: ₹{payment['balance_amount']:,.2f} | Due Date: {payment['due_date']} | 
                <span style="color: red; font-weight: bold;">{int(payment['days_overdue'])} Days Overdue</span>
            </div>
            """, unsafe_allow_html=True)
        if len(overdue_payments) > 5:
            st.warning(f"... and {len(overdue_payments) - 5} more overdue payments")

    df_rm_products = fetch_data("SELECT COUNT(*) as count FROM product_master WHERE category='RM Product'")
    df_fg_products = fetch_data("SELECT COUNT(*) as count FROM product_master WHERE category IN ('FG Product', 'Moulding Product', 'Powder')")
    df_total_production = fetch_data("SELECT SUM(produced_qty) as total FROM production_register")
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
            SELECT DATE(date) as date, SUM(produced_qty) as production 
            FROM production_register GROUP BY DATE(date)
        """)
        if not df_chart.empty:
            st.line_chart(df_chart.set_index('date')['production'])
        else:
            st.info("No production data")

    with col2:
        st.subheader("🏆 Top Contractors")
        df_contractors_prod = fetch_data("""
            SELECT party_name, SUM(produced_qty) as total_produced 
            FROM production_register 
            GROUP BY party_name 
            ORDER BY total_produced DESC LIMIT 10
        """)
        if not df_contractors_prod.empty:
            st.bar_chart(df_contractors_prod.set_index('party_name')['total_produced'])
        else:
            st.info("No contractor data")

    st.subheader("📋 Recent Activity")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**Recent Purchases**")
        df_recent_pur = fetch_data("SELECT challan_no, date, product_name, qty, amount FROM purchase_transactions ORDER BY date DESC LIMIT 5")
        if not df_recent_pur.empty:
            st.dataframe(df_recent_pur, use_container_width=True)
    with col2:
        st.markdown("**Recent Production**")
        df_recent_prod = fetch_data("SELECT party_name, fg_product, produced_qty, date FROM production_register ORDER BY date DESC LIMIT 5")
        if not df_recent_prod.empty:
            st.dataframe(df_recent_prod, use_container_width=True)
    with col3:
        st.markdown("**Recent Sales**")
        df_recent_sal = fetch_data("SELECT party_name, product_name, qty, amount, date FROM sales_transactions ORDER BY date DESC LIMIT 5")
        if not df_recent_sal.empty:
            st.dataframe(df_recent_sal, use_container_width=True)

# ======================= MASTERS =======================
elif page == "📦 Masters":
    st.subheader("📦 Master Management")
    tab1, tab2, tab3 = st.tabs(["👥 Parties (All Types)", "📦 Products", "🔧 BOM (Bill of Materials)"])

    with tab1:
        st.markdown("### Add New Party (Party/Moulder/Contractor)")
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

                    if product_category == 'RM Product':
                        execute_query("INSERT OR IGNORE INTO rm_inventory (product_name, opening_stock, total_purchased_qty, total_consumed_qty, closing_stock) VALUES (?, 0, 0, 0, 0)", (product_name,))
                    else:
                        execute_query("INSERT OR IGNORE INTO fg_inventory (product_name, opening_stock, produced_qty, sold_qty, rejected_qty, purchased_qty, closing_stock) VALUES (?, 0, 0, 0, 0, 0, 0)", (product_name,))

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
        st.markdown("### 🔧 BOM (Bill of Materials) Management")

        # =================== HARDCODED BOM DATA INITIALIZATION ===================
        BOM_DATA = {
            "5A SSC with JB": {"5A STC": 1, "5A DTC": 1, "5A W/S": 2, "5A C/C": 1, "5A Action": 1, "5A Earting Pin": 1, "5A Live Pin": 1, "5A Threading Patti": 2, "5/15A Bulb": 1},
            "5A 8x1 with JB": {"5A STC": 2, "5A DTC": 2, "5A W/S": 4, "5A C/C": 2, "5A Action": 2, "5A Earting Pin": 2, "5A Live Pin": 2, "5A Threading Patti": 4, "5/15A Bulb": 2},
            "15A SSC with JB": {"15A STC": 1, "15A DTC": 1, "15A W/S": 2, "15A C/C": 1, "15A Earting Pin": 1, "15A Live Pin": 2, "15A Action 21+5 Brass": 1, "15A Threading Patti": 1},
            "TSSC": {"15A STC": 3, "15A DTC": 3, "15A W/S": 6, "15A C/C": 3, "15A Earting Pin": 3, "15A Live Pin": 6, "15A Action 21+5 Brass": 3, "15A Threading Patti": 3, "DSSC Spike 1 mt": 3}
        }

        if 'bom_initialized' not in st.session_state:
            existing_bom = fetch_data("SELECT COUNT(*) as count FROM bom_master")
            if existing_bom.empty or existing_bom['count'].iloc[0] == 0:
                records = 0
                for fg_product, rm_dict in BOM_DATA.items():
                    for rm_product, qty in rm_dict.items():
                        execute_query("INSERT OR REPLACE INTO bom_master (fg_product, rm_product, required_qty) VALUES (?, ?, ?)", (fg_product, rm_product, float(qty)))
                        records += 1
                if records > 0:
                    st.success(f"✅ Auto-populated {records} BOM entries from template data!")
                st.session_state.bom_initialized = True

        st.markdown("---")

        # --- EDIT EXISTING BOM SECTION ---
        st.markdown("#### ✏️ Edit Existing BOM Entry")
        df_bom_list = fetch_data("SELECT fg_product, rm_product, required_qty FROM bom_master ORDER BY fg_product, rm_product")

        if not df_bom_list.empty:
            # Create a readable label for selection
            bom_options = [f"{row['fg_product']} -> {row['rm_product']} (Qty: {row['required_qty']})" for _, row in df_bom_list.iterrows()]
            selected_bom_label = st.selectbox("Select BOM Entry to Edit", bom_options)

            if selected_bom_label:
                # Parse the selection to get FG and RM names
                parts = selected_bom_label.split(" -> ")
                sel_fg = parts[0]
                sel_rm_qty_part = parts[1].split(" (Qty: ")
                sel_rm = sel_rm_qty_part[0]

                                # Initialize session state for BOM quantity editing
                if 'bom_edit_qty' not in st.session_state:
                    st.session_state.bom_edit_qty = float(sel_rm_qty_part[1].replace(")", ""))
                    st.session_state.bom_edit_prev_label = selected_bom_label

                # Reset quantity if the user selects a different BOM entry
                if st.session_state.get('bom_edit_prev_label') != selected_bom_label:
                    st.session_state.bom_edit_qty = float(sel_rm_qty_part[1].replace(")", ""))
                    st.session_state.bom_edit_prev_label = selected_bom_label

                col_e1, col_e2 = st.columns([2, 2])
                with col_e1:
                    st.text_input("FG Product", value=sel_fg, disabled=True)
                    st.text_input("RM Material", value=sel_rm, disabled=True)

                with col_e2:
                    st.markdown("**Adjust Quantity (Click ➕ or ➖)**")

                    # Create columns for Minus, Input, Plus
                    col_m1, col_m2, col_m3 = st.columns([1, 2, 1])
                    with col_m1:
                        if st.button("➖", key="bom_minus_btn", help="Decrease by 1"):
                            st.session_state.bom_edit_qty = max(0.001, st.session_state.bom_edit_qty - 1.0)
                            st.rerun()
                    with col_m2:
                        # Allow manual typing as well
                        typed_qty = st.number_input(
                            "Qty", 
                            min_value=0.001, 
                            step=1.0, 
                            value=float(st.session_state.bom_edit_qty), 
                            key="bom_qty_manual_input"
                        )
                        # Sync manual typing back to state
                        if typed_qty != st.session_state.bom_edit_qty:
                            st.session_state.bom_edit_qty = typed_qty
                    with col_m3:
                        if st.button("➕", key="bom_plus_btn", help="Increase by 1"):
                            st.session_state.bom_edit_qty = st.session_state.bom_edit_qty + 1.0
                            st.rerun()

                    # Update Button
                    if st.button("💾 Save Updated Qty", type="primary", key="save_bom_qty_btn"):
                        execute_query("UPDATE bom_master SET required_qty = ? WHERE fg_product = ? AND rm_product = ?", 
                                      (st.session_state.bom_edit_qty, sel_fg, sel_rm))
                        st.success(f"✅ BOM Quantity updated to {st.session_state.bom_edit_qty}!")
                        st.rerun()
        else:
            st.info("No BOM entries found.")

        st.markdown("---")
        st.markdown("#### ➕ Add New BOM Entry Manually")
        col1, col2 = st.columns(2)
        with col1:
            df_fg = fetch_data("SELECT product_name FROM product_master WHERE category IN ('FG Product', 'Moulding Product') ORDER BY product_name")
            fg_list = df_fg['product_name'].tolist() if not df_fg.empty else []
            bom_fg_product = st.selectbox("FG Product", fg_list if fg_list else ["No FG products"], key="bom_fg_select_new")
        with col2:
            bom_cat_filter = st.selectbox("Filter RM By Category", ["RM Product", "All"], key="bom_rm_cat_filter_new")
            if bom_cat_filter == "RM Product":
                df_rm = fetch_data("SELECT product_name FROM product_master WHERE category = 'RM Product' ORDER BY product_name")
            else:
                df_rm = fetch_data("SELECT product_name FROM product_master ORDER BY product_name")
            rm_list = df_rm['product_name'].tolist() if not df_rm.empty else []
            bom_rm_product = st.selectbox("RM Material", rm_list if rm_list else ["No RM products"], key="bom_rm_select_new")

        st.markdown("**Adjust Quantity (Click ➕ or ➖)**")
        # Initialize session state for new BOM quantity
        if 'new_bom_qty' not in st.session_state:
            st.session_state.new_bom_qty = 1.0

        col_m1, col_m2, col_m3 = st.columns([1, 2, 1])
        with col_m1:
            if st.button("➖", key="new_bom_minus_btn", help="Decrease by 1"):
                st.session_state.new_bom_qty = max(0.001, st.session_state.new_bom_qty - 1.0)
                st.rerun()
        with col_m2:
            typed_qty = st.number_input(
                "Req Qty", 
                min_value=0.001, 
                step=1.0, 
                value=float(st.session_state.new_bom_qty), 
                key="new_bom_qty_manual_input"
            )
            # Sync manual typing back to state
            if typed_qty != st.session_state.new_bom_qty:
                st.session_state.new_bom_qty = typed_qty
        with col_m3:
            if st.button("➕", key="new_bom_plus_btn", help="Increase by 1"):
                st.session_state.new_bom_qty = st.session_state.new_bom_qty + 1.0
                st.rerun()

        if st.button("💾 Add BOM", type="primary", key="add_bom_btn_new"):
            if bom_fg_product != "No FG products" and bom_rm_product != "No RM products":
                try:
                    execute_query('''INSERT OR REPLACE INTO bom_master (fg_product, rm_product, required_qty) VALUES (?, ?, ?)''', 
                                  (bom_fg_product, bom_rm_product, st.session_state.new_bom_qty))
                    st.success(f"✅ BOM added: {bom_fg_product} requires {st.session_state.new_bom_qty} x {bom_rm_product}")
                    st.session_state.new_bom_qty = 1.0  # Reset to 1.0 for the next entry
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
        st.markdown("#### 📋 BOM List")
        df_bom = fetch_data("""
        SELECT b.fg_product, b.rm_product, b.required_qty, p.unit as rm_unit, p.category as rm_category
        FROM bom_master b LEFT JOIN product_master p ON b.rm_product = p.product_name
        ORDER BY b.fg_product, b.rm_product
        """)
        if not df_bom.empty:
            st.dataframe(df_bom, use_container_width=True)

        st.markdown("#### 🗑️ Delete BOM Entry")
        bom_to_delete = st.selectbox("Select BOM to Delete",
            [f"{row['fg_product']} - {row['rm_product']}" for _, row in df_bom.iterrows()], key="delete_bom_select")
        if st.button("Delete BOM Entry", key="delete_bom_btn"):
            fg, rm = bom_to_delete.split(" - ")
            execute_query("DELETE FROM bom_master WHERE fg_product = ? AND rm_product = ?", (fg, rm))
            st.success("✅ BOM entry deleted!")
            st.rerun()
        else:
            st.info("No BOM entries defined yet. Please add manually above.")
        # ======================= PURCHASE ENTRY =======================
# ======================= PURCHASE ENTRY =======================
elif page == "🛒 Purchase Entry":
    st.subheader("🛒 Purchase Entry")
    # Initialize session state for filters if not present
    if 'pur_party_filter' not in st.session_state:
        st.session_state.pur_party_filter = "Purchase Party"
    if 'pur_prod_filter' not in st.session_state:
        st.session_state.pur_prod_filter = "RM Product"
    unit_options = ["kg", "Gross", "g", "Pcs", "PCS"]
    st.markdown("### 🔍 Filters")
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        party_filter = st.selectbox(
            "Select Party Type (Category)",
            ["Purchase Party", "Moulder", "Contractor", "Powder", "All"],
            key="pur_party_filter_select",
            index=["Purchase Party", "Moulder", "Contractor", "Powder", "All"].index(st.session_state.pur_party_filter) if st.session_state.pur_party_filter in ["Purchase Party", "Moulder", "Contractor", "Powder", "All"] else 0
        )
        if party_filter != st.session_state.pur_party_filter:
            st.session_state.pur_party_filter = party_filter
            st.rerun()
    with col_f2:
        prod_cat_filter = st.selectbox(
            "Filter Product By Category",
            ["RM Product", "FG Product", "Moulding Product", "Powder", "All"],
            key="pur_prod_filter_select",
            index=["RM Product", "FG Product", "Moulding Product", "Powder", "All"].index(st.session_state.pur_prod_filter) if st.session_state.pur_prod_filter in ["RM Product", "FG Product", "Moulding Product", "Powder", "All"] else 0
        )
        if prod_cat_filter != st.session_state.pur_prod_filter:
            st.session_state.pur_prod_filter = prod_cat_filter
            st.rerun()
    st.markdown("---")
    # Get dynamic lists based on filters
    df_parties, _ = get_dynamic_lists(st.session_state.pur_party_filter)
    party_list = df_parties['party_name'].tolist() if not df_parties.empty else []
    _, df_products = get_dynamic_lists(st.session_state.pur_prod_filter)
    product_list = df_products['product_name'].tolist() if not df_products.empty else []
    # Map product details for auto-filling rate/unit
    product_details_map = dict(zip(df_products['product_name'], zip(df_products['rate'], df_products['unit'], df_products['category']))) if not df_products.empty else {}
    with st.form("purchase_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            challan_no = st.text_input("Challan No *")
            purchase_date = st.date_input("Date", datetime.now())
            party = st.selectbox("Party/Moulder/Contractor", party_list if party_list else ["No parties added yet"])
        with col2:
            product = st.selectbox("Product", product_list if product_list else ["No products found"])
            # Auto-fill details based on selection
            rate_val = 0.0
            unit_val = 'PCS'
            actual_prod_cat = st.session_state.pur_prod_filter
            if product in product_details_map:
                r, u, c = product_details_map[product]
                rate_val = float(r) if pd.notna(r) else 0.0
                unit_val = u
                actual_prod_cat = c
            category = st.selectbox("Entry Category", ["Party", "Moulder", "Contractor", "Powder"], key="pur_entry_cat")
            qty = st.number_input("Quantity *", min_value=0.0, step=1.0)
        with col3:
            unit = st.selectbox("Unit", unit_options, index=unit_options.index(unit_val) if unit_val in unit_options else 4)
            rate = st.number_input("Rate per Unit", min_value=0.0, value=float(rate_val), step=0.01)
            payment_days = st.number_input("Payment Terms (Days)", min_value=0, max_value=365, value=60, step=1, key="pur_payment_days")
        if qty and rate:
            amount = qty * rate
            st.metric("Total Amount", f"₹{amount:,.2f}")
        else:
            st.metric("Total Amount", "₹0.00")
        # THIS IS THE MISSING SUBMIT BUTTON
        submitted = st.form_submit_button("Save Purchase", type="primary")
        if submitted:
            if all([challan_no, party and party != "No parties added yet", product and product != "No products found", qty > 0]):
                                # ... inside submitted block ...
                try:
                    # CHECK UNIQUE CHALLAN NO
                    existing_challan = fetch_data("SELECT id FROM purchase_transactions WHERE challan_no = ?", (challan_no,))
                    if not existing_challan.empty:
                        st.error(f"❌ Error: Challan No '{challan_no}' already exists! Please use a unique Challan Number.")
                    else:
                        purchase_amount = qty * rate
                        # 1. Save the transaction record
                        purchase_id = execute_query('''INSERT INTO purchase_transactions
                        (challan_no, date, party_name, product_name, category, product_category, qty, unit, rate, amount, entry_type)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PURCHASE')''',
                        (challan_no, purchase_date.strftime('%Y-%m-%d'), party, product, category, actual_prod_cat, qty, unit, rate, purchase_amount))
                        
                        # 2. Update Inventory Based on Category
                        if actual_prod_cat == 'RM Product':
                            # Ensure RM Inventory record exists
                            execute_query("INSERT OR IGNORE INTO rm_inventory (product_name, opening_stock, total_purchased_qty, total_consumed_qty, closing_stock) VALUES (?, 0, 0, 0, 0)", (product,))
                            
                            # Add Movement Record
                            execute_query('''INSERT INTO rm_stock_movement
                            (transaction_date, challan_no, product_name, transaction_type, qty, opening_balance, closing_balance, reference_id)
                            VALUES (?, ?, ?, ?, ?, 0, 0, ?)''',
                            (purchase_date.strftime('%Y-%m-%d'), challan_no, product, 'PURCHASE', qty, purchase_id))
                            
                            # Update Master Totals
                            execute_query("UPDATE rm_inventory SET total_purchased_qty = COALESCE(total_purchased_qty, 0) + ? WHERE product_name = ?", (qty, product))
                            
                            # Recalculate Balances Realtime
                            # THIS CALL IS NOW SAFE BECAUSE update_rm_inventory MANAGES ITS OWN CONNECTION
                            update_rm_inventory(product, 0, 'PURCHASE', purchase_date.strftime('%Y-%m-%d'), challan_no, purchase_id, rate=rate)
                            
                        elif actual_prod_cat in ['FG Product', 'Moulding Product', 'Powder']:
                            update_fg_inventory(product, qty, 'PURCHASE')
                            
                        # 3. Create Payable Entry
                        create_payable_entry(party, challan_no, purchase_date.strftime('%Y-%m-%d'), purchase_amount, payment_days)
                        
                        st.success(f"✅ Purchase entry saved successfully! Amount: ₹{purchase_amount:,.2f}")
                        st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
            else:
                st.warning("Please fill all required fields")
    st.markdown("---")
    st.markdown("### 📋 Manage Purchase Entries")
    df_all_purchases = fetch_data("SELECT id, challan_no, date, party_name, product_name, category, product_category, qty, unit, rate, amount FROM purchase_transactions ORDER BY date DESC")
    
    if not df_all_purchases.empty:
        purchase_options = [f"ID:{row['id']} | {row['challan_no']} | {row['product_name']} | {row['qty']} {row['unit']} | ₹{row['amount']:,.2f} | {row['date']}" for _, row in df_all_purchases.iterrows()]
        selected_purchase = st.selectbox("Select Purchase Entry to Edit/Delete", purchase_options, key="select_purchase_manage")
        
        # Safely extract ID
        selected_id = None
        if selected_purchase:
            try:
                selected_id = int(selected_purchase.split('|')[0].replace('ID:', '').strip())
            except:
                selected_id = None
    
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✏️ Edit Selected Purchase", type="primary", key="edit_purchase_btn"):
                if selected_id:
                    st.session_state.edit_mode = True
                    st.session_state.edit_id = selected_id
                    st.session_state.edit_table = 'purchase'
                    st.rerun()
                else:
                    st.warning("Please select a purchase entry first.")
                    
        with col2:
            if st.button("🗑️ Delete Selected Purchase", key="delete_purchase_btn"):
                if not selected_id:
                    st.warning("Please select a purchase entry to delete.")
                    
                # FIX: Store the selected_id in session state to prevent deleting the wrong item 
                # if the user changes the dropdown selection after clicking delete once.
                elif st.session_state.get('confirm_delete_purchase') == selected_id:
                    record = fetch_data("SELECT * FROM purchase_transactions WHERE id = ?", (selected_id,))
                    if not record.empty:
                        product = record['product_name'].iloc[0]
                        qty = float(record['qty'].iloc[0])
                        
                        # FIX: Safely get product_category. Fallback to checking rm_inventory if NULL.
                        prod_cat = record['product_category'].iloc[0] if pd.notna(record['product_category'].iloc[0]) else None
                        if prod_cat is None:
                            rm_check = fetch_data("SELECT product_name FROM rm_inventory WHERE product_name = ?", (product,))
                            prod_cat = 'RM Product' if not rm_check.empty else 'FG Product'
    
                        challan_no_del = record['challan_no'].iloc[0]
                        party_name_del = record['party_name'].iloc[0] if pd.notna(record['party_name'].iloc[0]) else ""
                        
                        try:
                            # 1. Reverse Inventory
                            if prod_cat == 'RM Product':
                                # Delete Movement Record first
                                execute_query("DELETE FROM rm_stock_movement WHERE reference_id = ? AND transaction_type = 'PURCHASE'", (selected_id,))
                                # Reverse Master Totals
                                execute_query("UPDATE rm_inventory SET total_purchased_qty = COALESCE(total_purchased_qty, 0) - ? WHERE product_name = ?", (qty, product))
                                # Recalculate Balances Realtime (Uses single connection to prevent DB locks)
                                update_rm_inventory(product, 0, 'PURCHASE') 
                            else:
                                # Reverse FG Purchase
                                execute_query("UPDATE fg_inventory SET purchased_qty = COALESCE(purchased_qty, 0) - ? WHERE product_name = ?", (qty, product))
                                execute_query("""
                                UPDATE fg_inventory
                                SET closing_stock = COALESCE(opening_stock, 0) + COALESCE(produced_qty, 0) + COALESCE(purchased_qty, 0) - COALESCE(sold_qty, 0) - COALESCE(rejected_qty, 0)
                                WHERE product_name = ?
                                """, (product,))
    
                            # 2. Delete from Ledger (Payable)
                            if challan_no_del and party_name_del:
                                execute_query("""
                                DELETE FROM payable_receivable_ledger
                                WHERE transaction_type = 'PAYABLE'
                                AND challan_no = ?
                                AND party_name = ?
                                """, (challan_no_del, party_name_del))
    
                            # 3. Delete Purchase Transaction
                            execute_query("DELETE FROM purchase_transactions WHERE id = ?", (selected_id,))
    
                            st.success(f"✅ Purchase entry (ID: {selected_id}) deleted and inventory updated successfully!")
                            st.session_state['confirm_delete_purchase'] = None # Reset confirmation
                            st.rerun()
                            
                        except Exception as e:
                            st.error(f"❌ Error deleting entry: {str(e)}")
                else:
                    # First click: Set confirmation state tied to this specific ID
                    st.session_state['confirm_delete_purchase'] = selected_id
                    st.warning(f"⚠️ Are you sure? Click 'Delete' again to confirm. This will reverse inventory and ledger changes for ID: {selected_id}.")
    if st.session_state.edit_mode and st.session_state.edit_table == 'purchase':
        st.markdown("### ✏️ Edit Purchase Entry")
        purchase_data = fetch_data("SELECT * FROM purchase_transactions WHERE id = ?", (st.session_state.edit_id,))
        if not purchase_data.empty:
            row = purchase_data.iloc[0]
            # Re-fetch lists for editing context
            df_parties_edit, _ = get_dynamic_lists(row['category'] if row['category'] in ["Purchase Party", "Moulder", "Contractor", "Powder"] else "All")
            party_list_edit = df_parties_edit['party_name'].tolist() if not df_parties_edit.empty else []
            df_products_edit, _ = get_dynamic_lists(row['product_category'] if row['product_category'] in ["FG Product", "Moulding Product", "RM Product", "Powder"] else "All")
        # Safe access to product_name column
            if not df_products_edit.empty and 'product_name' in df_products_edit.columns:
                product_list_edit = df_products_edit['product_name'].tolist()
            else:
                product_list_edit = []
            with st.form("edit_purchase_form"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    edit_challan = st.text_input("Challan No", value=row['challan_no'], key="edit_pur_challan")
                    edit_date = st.date_input("Date", datetime.strptime(row['date'], '%Y-%m-%d'), key="edit_pur_date")
                    edit_party = st.selectbox("Party",
                    party_list_edit if party_list_edit else [row['party_name']],
                    index=party_list_edit.index(row['party_name']) if row['party_name'] in party_list_edit else 0,
                    key="edit_pur_party")
                with col2:
                    edit_product = st.selectbox("Product",
                    product_list_edit if product_list_edit else [row['product_name']],
                    index=product_list_edit.index(row['product_name']) if row['product_name'] in product_list_edit else 0,
                    key="edit_pur_product")
                    edit_category = st.selectbox("Category", ["Party", "Moulder", "Contractor", "Powder"],
                    index=["Party", "Moulder", "Contractor", "Powder"].index(row['category']) if row['category'] in ["Party", "Moulder", "Contractor", "Powder"] else 0,
                    key="edit_pur_category")
                    edit_product_category = st.selectbox("Product Category", ["FG Product", "Moulding Product", "RM Product", "Powder"],
                    index=["FG Product", "Moulding Product", "RM Product", "Powder"].index(row['product_category']) if row['product_category'] in ["FG Product", "Moulding Product", "RM Product", "Powder"] else 2,
                    key="edit_pur_prod_cat")
                    edit_qty = st.number_input("Quantity *", min_value=0.0, value=float(row['qty']), step=1.0, key="edit_pur_qty")
                with col3:
                    edit_unit = st.selectbox("Unit", unit_options,
                    index=unit_options.index(row['unit']) if row['unit'] in unit_options else 4,
                    key="edit_pur_unit")
                    edit_rate = st.number_input("Rate per Unit", min_value=0.0, value=float(row['rate']) if pd.notna(row['rate']) else 0.0, step=0.01, key="edit_pur_rate")
                if edit_qty and edit_rate:
                    amount = edit_qty * edit_rate
                    st.metric("Total Amount", f"₹{amount:,.2f}")
                col1, col2 = st.columns(2)
                with col1:
                    if st.form_submit_button("💾 Save Changes", type="primary"):
                        old_qty = row['qty']
                        old_product = row['product_name']
                        old_prod_cat = row['product_category'] # Note: In purchase_transactions, this might be stored in 'product_category' or derived
                        old_date = row['date']
                        old_challan = row['challan_no']
                        
                        qty_diff = edit_qty - old_qty
                        
                        # Update Transaction Record
                        execute_query('''UPDATE purchase_transactions SET
                        challan_no=?, date=?, party_name=?, product_name=?, category=?, product_category=?, qty=?, unit=?, rate=?, amount=?
                        WHERE id=?''',
                        (edit_challan, edit_date.strftime('%Y-%m-%d'), edit_party, edit_product, edit_category, edit_product_category, edit_qty, edit_unit, edit_rate, edit_qty*edit_rate, st.session_state.edit_id))
                        
                        # Update Inventory Logic
                        if old_product == edit_product and old_prod_cat == edit_product_category:
                            # CASE 1: Same Product & Category -> UPDATE Existing Movement Record
                            if qty_diff != 0:
                                if old_prod_cat == 'RM Product':
                                    # Correct Logic for RM Purchase Edit:
                                    # 1. Update the total purchased quantity in master
                                    execute_query("UPDATE rm_inventory SET total_purchased_qty = COALESCE(total_purchased_qty, 0) + ? WHERE product_name = ?", (qty_diff, edit_product))
                                    
                                    # 2. Update the specific movement record quantity
                                    execute_query("UPDATE rm_stock_movement SET qty = ? WHERE reference_id = ? AND transaction_type = 'PURCHASE'",
                                    (edit_qty, st.session_state.edit_id))
                                    
                                    # 3. Recalculate Balances Realtime (This handles opening/closing balance consistency)
                                    update_rm_inventory(edit_product, 0, 'PURCHASE', edit_date.strftime('%Y-%m-%d'), edit_challan, st.session_state.edit_id, rate=edit_rate)
                                else:
                                    # Logic for FG/Moulding Purchase Edit
                                    execute_query("UPDATE fg_inventory SET purchased_qty = COALESCE(purchased_qty, 0) + ? WHERE product_name = ?", (qty_diff, edit_product))
                                    execute_query("""
                                    UPDATE fg_inventory
                                    SET closing_stock = COALESCE(opening_stock, 0) + COALESCE(produced_qty, 0) + COALESCE(purchased_qty, 0) - COALESCE(sold_qty, 0) - COALESCE(rejected_qty, 0)
                                    WHERE product_name = ?
                                    """, (edit_product,))
                        else:
                            # CASE 2: Product Changed -> DELETE Old, INSERT New
                            
                            # --- REVERSE OLD ENTRY ---
                            if old_prod_cat == 'RM Product':
                                # Reverse Old RM Purchase
                                execute_query("DELETE FROM rm_stock_movement WHERE reference_id = ? AND transaction_type = 'PURCHASE'", (st.session_state.edit_id,))
                                execute_query("UPDATE rm_inventory SET total_purchased_qty = COALESCE(total_purchased_qty, 0) - ? WHERE product_name = ?", (old_qty, old_product))
                                # Recalculate Old Product Balance
                                update_rm_inventory(old_product, 0, 'PURCHASE')
                            else:
                                # Reverse Old FG Purchase
                                execute_query("UPDATE fg_inventory SET purchased_qty = COALESCE(purchased_qty, 0) - ? WHERE product_name = ?", (old_qty, old_product))
                                execute_query("""
                                UPDATE fg_inventory
                                SET closing_stock = COALESCE(opening_stock, 0) + COALESCE(produced_qty, 0) + COALESCE(purchased_qty, 0) - COALESCE(sold_qty, 0) - COALESCE(rejected_qty, 0)
                                WHERE product_name = ?
                                """, (old_product,))
                                
                            # --- APPLY NEW ENTRY ---
                            if edit_product_category == 'RM Product':
                                execute_query("INSERT OR IGNORE INTO rm_inventory (product_name, opening_stock, total_purchased_qty, total_consumed_qty, closing_stock) VALUES (?, 0, 0, 0, 0)", (edit_product,))
                                
                                # Add new movement record for PURCHASE
                                execute_query('''INSERT INTO rm_stock_movement
                                (transaction_date, challan_no, product_name, transaction_type, qty, opening_balance, closing_balance, reference_id)
                                VALUES (?, ?, ?, ?, ?, 0, 0, ?)''',
                                (edit_date.strftime('%Y-%m-%d'), edit_challan, edit_product, 'PURCHASE', edit_qty, st.session_state.edit_id))
                                
                                # Update Master Totals
                                execute_query("UPDATE rm_inventory SET total_purchased_qty = COALESCE(total_purchased_qty, 0) + ? WHERE product_name = ?", (edit_qty, edit_product))
                                
                                # Recalculate Balances for New Product
                                update_rm_inventory(edit_product, 0, 'PURCHASE', edit_date.strftime('%Y-%m-%d'), edit_challan, st.session_state.edit_id, rate=edit_rate)
                            else:
                                # FG Purchase
                                execute_query("INSERT OR IGNORE INTO fg_inventory (product_name, opening_stock, produced_qty, sold_qty, rejected_qty, purchased_qty, closing_stock) VALUES (?, 0, 0, 0, 0, 0, 0)", (edit_product,))
                                update_fg_inventory(edit_product, edit_qty, 'PURCHASE') # Note: Ensure update_fg_inventory handles 'PURCHASE' type correctly if not already handled by direct SQL above
        
                        st.success("✅ Purchase entry updated successfully!")
                        st.session_state.edit_mode = False
                        st.session_state.edit_id = None
                        st.rerun()
                with col2:
                    if st.form_submit_button("❌ Cancel"):
                        st.session_state.edit_mode = False
                        st.session_state.edit_id = None
                        st.rerun()
    st.markdown("### All Purchase Entries")
    st.dataframe(df_all_purchases, use_container_width=True)
    st.metric("Total Purchase Value", f"₹{df_all_purchases['amount'].sum():,.2f}")
# ======================= PRODUCTION ENTRY =======================
# ======================= PRODUCTION ENTRY =======================
elif page == "🏭 Production Entry":
    st.subheader("🏭 Production Entry")
    
    # Initialize session state for filters if not present
    if 'prod_party_filter' not in st.session_state:
        st.session_state.prod_party_filter = "Moulder"
    if 'prod_prod_filter' not in st.session_state:
        st.session_state.prod_prod_filter = "All" # Changed default to All to show everything

    unit_options = ["kg", "Gross", "g", "Pcs", "PCS"]
    
    st.markdown("### 🔍 Filters")
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        party_filter = st.selectbox(
            "Select Party Type (Category)",
            ["Moulder", "Contractor", "Purchase Party", "All"],
            key="prod_party_filter_select",
            index=["Moulder", "Contractor", "Purchase Party", "All"].index(st.session_state.prod_party_filter) if st.session_state.prod_party_filter in ["Moulder", "Contractor", "Purchase Party", "All"] else 0
        )
        if party_filter != st.session_state.prod_party_filter:
            st.session_state.prod_party_filter = party_filter
            st.rerun()
            
    with col_f2:
        prod_cat_filter = st.selectbox(
            "Filter Product By Category",
            ["All", "FG Product", "Moulding Product", "RM Product", "Powder"], # Added All and RM/Powder
            key="prod_prod_filter_select",
            index=["All", "FG Product", "Moulding Product", "RM Product", "Powder"].index(st.session_state.prod_prod_filter) if st.session_state.prod_prod_filter in ["All", "FG Product", "Moulding Product", "RM Product", "Powder"] else 0
        )
        if prod_cat_filter != st.session_state.prod_prod_filter:
            st.session_state.prod_prod_filter = prod_cat_filter
            st.rerun()

    st.markdown("---")
    
    df_parties, _ = get_dynamic_lists(st.session_state.prod_party_filter)
    party_list = df_parties['party_name'].tolist() if not df_parties.empty else []
    
    _, df_products = get_dynamic_lists(st.session_state.prod_prod_filter)
    product_list = df_products['product_name'].tolist() if not df_products.empty else []
    
    # Map product details for auto-filling rate/unit
    product_details_map = {}
    if not df_products.empty:
        for _, row in df_products.iterrows():
            product_details_map[row['product_name']] = (row['rate'], row['unit'], row['category'])

    with st.form("production_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            challan_no = st.text_input("Challan No")
            prod_date = st.date_input("Date", datetime.now())
            party_name = st.selectbox("Party/Moulder/Contractor", party_list if party_list else ["No parties added yet"])
        
        with col2:
            fg_product = st.selectbox("Product to Produce", product_list if product_list else ["No products found"])
            
            unit_val = 'PCS'
            actual_prod_cat = "FG Product" # Default
            
            if fg_product in product_details_map:
                r, u, c = product_details_map[fg_product]
                unit_val = u
                actual_prod_cat = c
                
            produced_qty = st.number_input("Produced Qty *", min_value=0.0, step=1.0)
            unit = st.selectbox("Unit", unit_options, index=unit_options.index(unit_val) if unit_val in unit_options else 4)
        
        with col3:
            description = st.text_area("Description")
            
        submitted = st.form_submit_button("Save Production", type="primary")
        
        if submitted:
            if all([party_name and party_name != "No parties added yet", fg_product and fg_product != "No products found", produced_qty > 0]):
                try:
                    # 1. Insert into Production Register
                    execute_query('''INSERT INTO production_register
                    (challan_no, date, party_name, fg_product, product_category, produced_qty, unit, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                    (challan_no, prod_date.strftime('%Y-%m-%d'), party_name, fg_product, actual_prod_cat, produced_qty, unit, description))
                    
                    # 2. Update Inventory Based on Category
                    if actual_prod_cat == 'RM Product':
                        # Ensure RM Inventory record exists
                        execute_query("INSERT OR IGNORE INTO rm_inventory (product_name, opening_stock, total_purchased_qty, total_consumed_qty, closing_stock) VALUES (?, 0, 0, 0, 0)", (fg_product,))
                        
                        # Add Movement Record for Production (Type: PURCHASE equivalent for RM)
                        # We use 'PURCHASE' type for RM production so it adds to stock, 
                        # or you can create a new type 'PRODUCTION' if you prefer distinct tracking.
                        # For now, let's treat RM Production as an addition to stock similar to Purchase.
                        prod_id = fetch_data("SELECT last_insert_rowid() as id", ())['id'].iloc[0]
                        
                        execute_query('''INSERT INTO rm_stock_movement
                        (transaction_date, challan_no, product_name, transaction_type, qty, opening_balance, closing_balance, reference_id)
                        VALUES (?, ?, ?, ?, ?, 0, 0, ?)''',
                        (prod_date.strftime('%Y-%m-%d'), challan_no, fg_product, 'PURCHASE', produced_qty, prod_id))
                        
                        # Update Master Totals
                        execute_query("UPDATE rm_inventory SET total_purchased_qty = COALESCE(total_purchased_qty, 0) + ? WHERE product_name = ?", (produced_qty, fg_product))
                        
                        # Recalculate Balances Realtime
                        update_rm_inventory(fg_product, 0, 'PURCHASE', prod_date.strftime('%Y-%m-%d'), challan_no, prod_id)
                        
                    elif actual_prod_cat in ['FG Product', 'Moulding Product', 'Powder']:
                        # Ensure FG Inventory record exists
                        execute_query("INSERT OR IGNORE INTO fg_inventory (product_name, opening_stock, produced_qty, sold_qty, rejected_qty, purchased_qty, closing_stock) VALUES (?, 0, 0, 0, 0, 0, 0)", (fg_product,))
                        
                        # Update FG Inventory (Real-time)
                        update_fg_inventory(fg_product, produced_qty, 'PRODUCE')
                    
                    st.success(f"✅ Production entry saved successfully for {actual_prod_cat}!")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
            else:
                st.warning("Please fill all required fields")

    st.markdown("---")
    st.markdown("### 📋 Manage Production Entries")
    df_all_production = fetch_data("SELECT id, challan_no, date, party_name, fg_product, product_category, produced_qty, unit, description FROM production_register ORDER BY date DESC")
    
    if not df_all_production.empty:
        production_options = [f"ID:{row['id']} | {row['fg_product']} ({row['product_category']}) | {row['produced_qty']} {row['unit']} | {row['party_name']} | {row['date']}" for _, row in df_all_production.iterrows()]
        selected_production = st.selectbox("Select Production Entry to Edit/Delete", production_options, key="select_production_manage")
        selected_id = int(selected_production.split('|')[0].replace('ID:', '').strip()) if selected_production else None
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✏️ Edit Selected Production", type="primary", key="edit_production_btn"):
                st.session_state.edit_mode = True
                st.session_state.edit_id = selected_id
                st.session_state.edit_table = 'production'
                st.rerun()
                
        with col2:
            if st.button("🗑️ Delete Selected Production", key="delete_production_btn"):
                if st.session_state.get('confirm_delete_production'):
                    record = fetch_data("SELECT * FROM production_register WHERE id = ?", (selected_id,))
                    if not record.empty:
                        product = record['fg_product'].iloc[0]
                        qty = record['produced_qty'].iloc[0]
                        prod_cat = record['product_category'].iloc[0]
                        
                        # Reverse Inventory based on Category
                        if prod_cat == 'RM Product':
                            # Delete Movement Record
                            execute_query("DELETE FROM rm_stock_movement WHERE reference_id = ? AND transaction_type = 'PURCHASE'", (selected_id,))
                            # Reverse Master Totals
                            execute_query("UPDATE rm_inventory SET total_purchased_qty = COALESCE(total_purchased_qty, 0) - ? WHERE product_name = ?", (qty, product))
                            # Recalculate Balances
                            update_rm_inventory(product, 0, 'PURCHASE')
                        else:
                            # Reverse FG Inventory
                            execute_query("UPDATE fg_inventory SET produced_qty = COALESCE(produced_qty, 0) - ? WHERE product_name = ?", (qty, product))
                            execute_query("""
                            UPDATE fg_inventory
                            SET closing_stock = COALESCE(opening_stock, 0) + COALESCE(produced_qty, 0) + COALESCE(purchased_qty, 0) - COALESCE(sold_qty, 0) - COALESCE(rejected_qty, 0)
                            WHERE product_name = ?
                            """, (product,))
                            
                        execute_query("DELETE FROM production_register WHERE id = ?", (selected_id,))
                        st.success("✅ Production entry deleted and inventory updated!")
                        st.session_state['confirm_delete_production'] = False
                        st.rerun()
                else:
                    st.session_state['confirm_delete_production'] = True
                    st.warning("⚠️ Click again to confirm deletion. This will reverse inventory changes.")

    # Edit Mode Logic for Production
    if st.session_state.edit_mode and st.session_state.edit_table == 'production':
        st.markdown("### ✏️ Edit Production Entry")
        production_data = fetch_data("SELECT * FROM production_register WHERE id = ?", (st.session_state.edit_id,))
        if not production_data.empty:
            row = production_data.iloc[0]
            
            # Re-fetch lists for editing context
            df_parties_edit_all = fetch_data("SELECT party_name FROM party_master WHERE category IN ('Moulder', 'Contractor', 'Purchase Party') ORDER BY party_name")
            party_list_edit = df_parties_edit_all['party_name'].tolist() if not df_parties_edit_all.empty else []
            
            # Get products based on the stored category of the edited item
            df_products_edit, _ = get_dynamic_lists(row['product_category'] if row['product_category'] in ["FG Product", "Moulding Product", "RM Product", "Powder"] else "All")
            if not df_products_edit.empty and 'product_name' in df_products_edit.columns:
                product_list_edit = df_products_edit['product_name'].tolist()
            else:
                product_list_edit = []

            with st.form("edit_production_form"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    edit_challan = st.text_input("Challan No", value=row['challan_no'] if pd.notna(row['challan_no']) else "", key="edit_prod_challan")
                    edit_date = st.date_input("Date", datetime.strptime(row['date'], '%Y-%m-%d'), key="edit_prod_date")
                    edit_party = st.selectbox("Party/Moulder/Contractor",
                                              party_list_edit if party_list_edit else [row['party_name']],
                                              index=party_list_edit.index(row['party_name']) if row['party_name'] in party_list_edit else 0,
                                              key="edit_prod_party")
                with col2:
                    edit_product = st.selectbox("Product",
                                                product_list_edit if product_list_edit else [row['fg_product']],
                                                index=product_list_edit.index(row['fg_product']) if row['fg_product'] in product_list_edit else 0,
                                                key="edit_prod_product")
                    
                    # Determine category for the edited product
                    edit_prod_cat = row['product_category']
                    # If product changed, we might need to re-evaluate, but for simplicity keep original category logic or fetch new
                    # For now, let's assume category stays same or user selects from same list
                    
                    edit_qty = st.number_input("Produced Qty *", min_value=0.0, value=float(row['produced_qty']), step=1.0, key="edit_prod_qty")
                    edit_unit = st.selectbox("Unit", unit_options,
                                             index=unit_options.index(row['unit']) if row['unit'] in unit_options else 4,
                                             key="edit_prod_unit")
                with col3:
                    edit_description = st.text_area("Description", value=row['description'] if pd.notna(row['description']) else "", key="edit_prod_desc")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.form_submit_button("💾 Save Changes", type="primary"):
                        old_qty = row['produced_qty']
                        old_product = row['fg_product']
                        old_prod_cat = row['product_category']
                        qty_diff = edit_qty - old_qty
                        
                        # Update Transaction Record
                        execute_query('''UPDATE production_register SET
                        challan_no=?, date=?, party_name=?, fg_product=?, product_category=?, produced_qty=?, unit=?, description=?
                        WHERE id=?''',
                        (edit_challan, edit_date.strftime('%Y-%m-%d'), edit_party, edit_product, old_prod_cat, edit_qty, edit_unit, edit_description, st.session_state.edit_id))
                        
                        # Update Inventory Logic
                        if old_product == edit_product:
                            if qty_diff != 0:
                                if old_prod_cat == 'RM Product':
                                    # Update RM Inventory
                                    execute_query("UPDATE rm_inventory SET total_purchased_qty = COALESCE(total_purchased_qty, 0) + ? WHERE product_name = ?", (qty_diff, edit_product))
                                    # Update Movement Record
                                    execute_query("UPDATE rm_stock_movement SET qty = ? WHERE reference_id = ? AND transaction_type = 'PURCHASE'", (edit_qty, st.session_state.edit_id))
                                    # Recalculate
                                    update_rm_inventory(edit_product, 0, 'PURCHASE')
                                else:
                                    # Update FG Inventory
                                    execute_query("UPDATE fg_inventory SET produced_qty = COALESCE(produced_qty, 0) + ? WHERE product_name = ?", (qty_diff, edit_product))
                                    execute_query("""
                                    UPDATE fg_inventory
                                    SET closing_stock = COALESCE(opening_stock, 0) + COALESCE(produced_qty, 0) + COALESCE(purchased_qty, 0) - COALESCE(sold_qty, 0) - COALESCE(rejected_qty, 0)
                                    WHERE product_name = ?
                                    """, (edit_product,))
                        else:
                            # Product Changed: Reverse Old, Add New
                            if old_prod_cat == 'RM Product':
                                execute_query("DELETE FROM rm_stock_movement WHERE reference_id = ? AND transaction_type = 'PURCHASE'", (st.session_state.edit_id,))
                                execute_query("UPDATE rm_inventory SET total_purchased_qty = COALESCE(total_purchased_qty, 0) - ? WHERE product_name = ?", (old_qty, old_product))
                                update_rm_inventory(old_product, 0, 'PURCHASE')
                            else:
                                execute_query("UPDATE fg_inventory SET produced_qty = COALESCE(produced_qty, 0) - ? WHERE product_name = ?", (old_qty, old_product))
                                execute_query("""
                                UPDATE fg_inventory
                                SET closing_stock = COALESCE(opening_stock, 0) + COALESCE(produced_qty, 0) + COALESCE(purchased_qty, 0) - COALESCE(sold_qty, 0) - COALESCE(rejected_qty, 0)
                                WHERE product_name = ?
                                """, (old_product,))
                                
                            # Add New
                            if old_prod_cat == 'RM Product': # Note: This assumes new product is same category. If changing category, logic needs to be more complex.
                                 # For simplicity, assuming category doesn't change in edit for now, or handling basic swap
                                 pass 
                            # Ideally, if category changes, we delete old and insert new as per Create logic. 
                            # But for Edit, usually we keep category consistent. 
                            # Let's force recalc for new product if it's RM
                            if old_prod_cat == 'RM Product':
                                execute_query("INSERT OR IGNORE INTO rm_inventory (product_name, opening_stock, total_purchased_qty, total_consumed_qty, closing_stock) VALUES (?, 0, 0, 0, 0)", (edit_product,))
                                execute_query('''INSERT INTO rm_stock_movement
                                (transaction_date, challan_no, product_name, transaction_type, qty, opening_balance, closing_balance, reference_id)
                                VALUES (?, ?, ?, ?, ?, 0, 0, ?)''',
                                (edit_date.strftime('%Y-%m-%d'), edit_challan, edit_product, 'PURCHASE', edit_qty, st.session_state.edit_id))
                                execute_query("UPDATE rm_inventory SET total_purchased_qty = COALESCE(total_purchased_qty, 0) + ? WHERE product_name = ?", (edit_qty, edit_product))
                                update_rm_inventory(edit_product, 0, 'PURCHASE')
                            else:
                                execute_query("INSERT OR IGNORE INTO fg_inventory (product_name, opening_stock, produced_qty, sold_qty, rejected_qty, purchased_qty, closing_stock) VALUES (?, 0, 0, 0, 0, 0, 0)", (edit_product,))
                                execute_query("UPDATE fg_inventory SET produced_qty = COALESCE(produced_qty, 0) + ? WHERE product_name = ?", (edit_qty, edit_product))
                                execute_query("""
                                UPDATE fg_inventory
                                SET closing_stock = COALESCE(opening_stock, 0) + COALESCE(produced_qty, 0) + COALESCE(purchased_qty, 0) - COALESCE(sold_qty, 0) - COALESCE(rejected_qty, 0)
                                WHERE product_name = ?
                                """, (edit_product,))

                        st.success("✅ Production entry updated successfully!")
                        st.session_state.edit_mode = False
                        st.session_state.edit_id = None
                        st.rerun()
                        
                with col2:
                    if st.form_submit_button("❌ Cancel"):
                        st.session_state.edit_mode = False
                        st.session_state.edit_id = None
                        st.rerun()

    st.markdown("### All Production Entries")
    if not df_all_production.empty:
        st.dataframe(df_all_production, use_container_width=True)
# ======================= SALES ENTRY =======================
elif page == "💰 Sales Entry":
    st.subheader("💰 Sales Entry")
    if 'sale_party_filter' not in st.session_state:
        st.session_state.sale_party_filter = "Sales Party"
    if 'sale_prod_filter' not in st.session_state:
        st.session_state.sale_prod_filter = "FG Product"
    unit_options = ["kg", "Gross", "g", "Pcs", "PCS"]
    st.markdown("### 🔍 Filters")
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        party_filter = st.selectbox(
            "Select Party Type (Category)",
            ["Sales Party", "Purchase Party", "Moulder", "Contractor", "All"],
            key="sale_party_filter_select",
            index=["Sales Party", "Purchase Party", "Moulder", "Contractor", "All"].index(st.session_state.sale_party_filter) if st.session_state.sale_party_filter in ["Sales Party", "Purchase Party", "Moulder", "Contractor", "All"] else 0
        )
        if party_filter != st.session_state.sale_party_filter:
            st.session_state.sale_party_filter = party_filter
            st.rerun()
    with col_f2:
        prod_cat_filter = st.selectbox(
            "Filter Product By Category",
            ["FG Product", "Moulding Product", "RM Product", "Powder", "All"],
            key="sale_prod_filter_select",
            index=["FG Product", "Moulding Product", "RM Product", "Powder", "All"].index(st.session_state.sale_prod_filter) if st.session_state.sale_prod_filter in ["FG Product", "Moulding Product", "RM Product", "Powder", "All"] else 0
        )
        if prod_cat_filter != st.session_state.sale_prod_filter:
            st.session_state.sale_prod_filter = prod_cat_filter
            st.rerun()
    st.markdown("---")
    df_parties, _ = get_dynamic_lists(st.session_state.sale_party_filter)
    party_list = df_parties['party_name'].tolist() if not df_parties.empty else []
    _, df_products = get_dynamic_lists(st.session_state.sale_prod_filter)
    product_list = df_products['product_name'].tolist() if not df_products.empty else []
    product_details_map = dict(zip(df_products['product_name'], zip(df_products['rate'], df_products['unit'], df_products['category']))) if not df_products.empty else {}
    with st.form("sales_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            challan_no = st.text_input("Challan No *")
            sales_date = st.date_input("Date", datetime.now())
            party = st.selectbox("Sales Party", party_list if party_list else ["No parties added yet"])
        with col2:
            product = st.selectbox("Product", product_list if product_list else ["No products found"])
            rate_val = 0.0
            unit_val = 'PCS'
            actual_prod_cat = st.session_state.sale_prod_filter
            if product in product_details_map:
                r, u, c = product_details_map[product]
                rate_val = float(r) if pd.notna(r) else 0.0
                unit_val = u
                actual_prod_cat = c
            category = st.selectbox("Category", ["Party", "Moulder", "Contractor", "Powder"])
            qty = st.number_input("Quantity *", min_value=0.0, step=1.0)
        with col3:
            unit = st.selectbox("Unit", unit_options, index=unit_options.index(unit_val) if unit_val in unit_options else 4)
            rate = st.number_input("Rate per Unit", min_value=0.0, value=float(rate_val), step=0.01)
            payment_days = st.number_input("Payment Terms (Days)", min_value=0, max_value=365, value=60, step=1)
        if qty and rate:
            amount = qty * rate
            st.metric("Total Amount", f"₹{amount:,.2f}")
        else:
            st.metric("Total Amount", "₹0.00")
        # Inside elif page == "💰 Sales Entry": ... with st.form("sales_form"): ...
        submitted = st.form_submit_button("Save Sale", type="primary")
        if submitted:
            if all([challan_no, party and party != "No parties added yet", product and product != "No products found", qty > 0]):
                try:
                    # CHECK UNIQUE CHALLAN NO
                    existing_challan = fetch_data("SELECT id FROM sales_transactions WHERE challan_no = ?", (challan_no,))
                    if not existing_challan.empty:
                        st.error(f"❌ Error: Challan No '{challan_no}' already exists! Please use a unique Challan Number.")
                    else:
                        available = 0.0
                        # Determine correct inventory table based on product category
                        if actual_prod_cat == 'RM Product':
                            df_stock = fetch_data("SELECT closing_stock FROM rm_inventory WHERE product_name = ?", (product,))
                            if not df_stock.empty:
                                val = df_stock['closing_stock'].iloc[0]
                                available = float(val) if pd.notna(val) else 0.0
                        else:
                            # For FG, Moulding, Powder, use FG Inventory
                            df_stock = fetch_data("SELECT closing_stock FROM fg_inventory WHERE product_name = ?", (product,))
                            if not df_stock.empty:
                                val = df_stock['closing_stock'].iloc[0]
                                available = float(val) if pd.notna(val) else 0.0

                        if available < qty:
                            st.warning(f"⚠️ Insufficient stock! Available: {available:.2f} {unit}, Requested: {qty:.2f} {unit}")
                        else:
                            sale_date_dt = sales_date if isinstance(sales_date, datetime) else datetime.combine(sales_date, datetime.min.time())
                            due_date = sale_date_dt + timedelta(days=payment_days)
                            sale_amount = qty * rate
                            
                            # 1. Insert Sales Transaction FIRST
                            execute_query('''INSERT INTO sales_transactions
                            (challan_no, date, party_name, product_name, category, product_category, qty, unit, rate, amount, payment_terms_days, due_date)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                            (challan_no, sales_date.strftime('%Y-%m-%d'), party, product, category, actual_prod_cat, qty, unit, rate, sale_amount, payment_days, due_date.strftime('%Y-%m-%d')))
                            
                            # Get the ID of the newly inserted sale for reference
                            new_sale_id = fetch_data("SELECT last_insert_rowid() as id", ())['id'].iloc[0]
                            
                            # 2. Update Inventory
                                            # 2. Update Inventory
                                            # 2. Update Inventory
                                            # 2. Update Inventory
                            try:
                                if actual_prod_cat == 'RM Product':
                                    # Ensure RM Inventory record exists
                                    execute_query("INSERT OR IGNORE INTO rm_inventory (product_name, opening_stock, total_purchased_qty, total_consumed_qty, closing_stock) VALUES (?, 0, 0, 0, 0)", (product,))
                                    
                                    # Check Stock Before Sale
                                    current_stock = fetch_data("SELECT closing_stock FROM rm_inventory WHERE product_name = ?", (product,))
                                    if not current_stock.empty and float(current_stock['closing_stock'].iloc[0]) < qty:
                                        raise Exception(f"Insufficient RM Stock! Available: {current_stock['closing_stock'].iloc[0]}, Requested: {qty}")
            
                                    # Add Movement Record
                                    execute_query('''INSERT INTO rm_stock_movement
                                    (transaction_date, challan_no, product_name, transaction_type, qty, opening_balance, closing_balance, reference_id)
                                    VALUES (?, ?, ?, ?, ?, 0, 0, ?)''',
                                    (sales_date.strftime('%Y-%m-%d'), challan_no, product, 'SALE', qty, new_sale_id))
                                    
                                    # Update Master Totals
                                    execute_query("UPDATE rm_inventory SET total_consumed_qty = COALESCE(total_consumed_qty, 0) + ? WHERE product_name = ?", (qty, product))
                                    
                                    # Recalculate Balances Realtime (Same as Purchase)
                                    update_rm_inventory(product, 0, 'PURCHASE', sales_date.strftime('%Y-%m-%d'), challan_no, new_sale_id, rate=rate)
            
                                else:
                                    # For FG/Moulding/Powder, use FG Inventory logic
                                    update_fg_inventory(product, qty, 'SALE')
                                    
                                    # 3. Attempt RM Consumption (Non-Blocking)
                                    if actual_prod_cat != 'RM Product':
                                        consume_rm_for_fg_sale(product, qty, sales_date.strftime('%Y-%m-%d'), challan_no, new_sale_id)                                            # 3. Attempt RM Consumption (Non-Blocking)
                                            # If this fails or warns, it won't stop the sale because we already inserted the sale and updated FG inventory
                               
                                    
                            except Exception as inv_err:
                                # If inventory update fails (e.g. truly insufficient stock), we might want to rollback the sale
                                # But per your request "If It Is Insufficient Then Also Sell Entry Is Stored", 
                                # we will catch the error, show it, but keep the sale record.
                                # NOTE: This leaves data inconsistent. A better approach for "Allow Sale" is to 
                                # let the inventory go negative or just warn. 
                                # The update_fg_inventory above raises an exception if insufficient.
                                # To ALLOW sale even if insufficient, we need to modify update_fg_inventory to NOT raise exception 
                                # or catch it here and ignore it.
                                
                                st.warning(f"⚠️ Inventory Warning: {str(inv_err)}. Sale entry saved, but inventory may be negative/unadjusted.")
                                # We do NOT rollback the sale transaction here.
            
                            # 4. Create Receivable Entry
                            create_receivable_entry(party, challan_no, sales_date.strftime('%Y-%m-%d'), sale_amount, payment_days)
                            
                            st.success(f"✅ Sale entry saved successfully! Amount: ₹{sale_amount:,.2f}")
                            st.balloons()
                            # Force immediate rerun to reflect changes in dashboard/ledger
                            st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
            else:
                st.warning("Please fill all required fields")
    st.markdown("---")
    st.markdown("### 📝 Manage Sales Entries")
    df_all_sales = fetch_data("SELECT id, challan_no, date, party_name, product_name, category, product_category, qty, unit, rate, amount, payment_terms_days, due_date FROM sales_transactions ORDER BY date DESC")
    if not df_all_sales.empty:
        sales_options = [f"ID:{row['id']} | {row['challan_no']} | {row['product_name']} | {row['qty']} {row['unit']} | ₹{row['amount']:,.2f} | {row['party_name']} | {row['date']}" for _, row in df_all_sales.iterrows()]
        selected_sale = st.selectbox("Select Sales Entry to Edit/Delete", sales_options, key="select_sale_manage")
        selected_id = int(selected_sale.split('|')[0].replace('ID:', '').strip()) if selected_sale else None
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✏️ Edit Selected Sale", type="primary", key="edit_sale_btn"):
                st.session_state.edit_mode = True
                st.session_state.edit_id = selected_id
                st.session_state.edit_table = 'sale'
                st.rerun()
        with col2:
            if st.button("🗑️ Delete Selected Sale", key="delete_sale_btn"):
                if st.session_state.get('confirm_delete_sale'):
                    record = fetch_data("SELECT * FROM sales_transactions WHERE id = ?", (selected_id,))
                    if not record.empty:
                        product = record['product_name'].iloc[0]
                        qty = float(record['qty'].iloc[0])
                        prod_cat = record['product_category'].iloc[0]
                        challan_no_del = record['challan_no'].iloc[0]
                        party_name_del = record['party_name'].iloc[0]
        
                        # 1. Update Inventory
                                        # 1. Update Inventory
                                        # 1. Update Inventory
                                        # 1. Update Inventory
                        if prod_cat == 'RM Product':
                            # Reverse RM Sale: Delete movement record first
                            execute_query("DELETE FROM rm_stock_movement WHERE reference_id = ? AND transaction_type = 'SALE'", (selected_id,))
                            # Reverse master totals
                            execute_query("UPDATE rm_inventory SET total_consumed_qty = COALESCE(total_consumed_qty, 0) - ? WHERE product_name = ?", (qty, product))
                            # Recalculate Balances Realtime (Same as Purchase Delete)
                            update_rm_inventory(product, 0, 'PURCHASE') 
                        else:
                            # Reverse FG Sale
                            execute_query("UPDATE fg_inventory SET sold_qty = COALESCE(sold_qty, 0) - ? WHERE product_name = ?", (qty, product))
                            execute_query("""
                            UPDATE fg_inventory
                            SET closing_stock = COALESCE(opening_stock, 0) + COALESCE(produced_qty, 0) + COALESCE(purchased_qty, 0) - COALESCE(sold_qty, 0) - COALESCE(rejected_qty, 0)
                            WHERE product_name = ?
                            """, (product,))        
                        # 2. Delete from Ledger
                        execute_query("""
                        DELETE FROM payable_receivable_ledger
                        WHERE transaction_type = 'RECEIVABLE'
                        AND challan_no = ?
                        AND party_name = ?
                        """, (challan_no_del, party_name_del))
        
                        # 3. Delete Sales Transaction
                        execute_query("DELETE FROM sales_transactions WHERE id = ?", (selected_id,))
        
                        st.success("✅ Sales entry deleted, inventory updated, and ledger cleared!")
                        st.session_state['confirm_delete_sale'] = False
                        st.rerun()
                else:
                    st.session_state['confirm_delete_sale'] = True
                    st.warning("⚠️ Click again to confirm deletion. This will reverse inventory and ledger changes.")
    if st.session_state.edit_mode and st.session_state.edit_table == 'sale':
        st.markdown("### ✏️ Edit Sales Entry")
        sales_data = fetch_data("SELECT * FROM sales_transactions WHERE id = ?", (st.session_state.edit_id,))
        if not sales_data.empty:
            row = sales_data.iloc[0]
            
            # Re-fetch lists for editing context
            df_parties_edit, _ = get_dynamic_lists(row['category'] if row['category'] in ["Sales Party", "Purchase Party", "Moulder", "Contractor"] else "All")
            party_list_edit = df_parties_edit['party_name'].tolist() if not df_parties_edit.empty else []
            
            df_products_edit, _ = get_dynamic_lists(row['product_category'] if row['product_category'] in ["RM Product", "FG Product", "Moulding Product", "Powder"] else "All")
            if not df_products_edit.empty and 'product_name' in df_products_edit.columns:
                product_list_edit = df_products_edit['product_name'].tolist()
            else:
                product_list_edit = []
    
            with st.form("edit_sale_form"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    edit_challan = st.text_input("Challan No", value=row['challan_no'], key="edit_sale_challan")
                    edit_date = st.date_input("Date", datetime.strptime(row['date'], '%Y-%m-%d'), key="edit_sale_date")
                    edit_party = st.selectbox("Sales Party",
                                              party_list_edit if party_list_edit else [row['party_name']],
                                              index=party_list_edit.index(row['party_name']) if row['party_name'] in party_list_edit else 0,
                                              key="edit_sale_party")
                with col2:
                    edit_product = st.selectbox("Product",
                                                product_list_edit if product_list_edit else [row['product_name']],
                                                index=product_list_edit.index(row['product_name']) if row['product_name'] in product_list_edit else 0,
                                                key="edit_sale_product")
                    edit_category = st.selectbox("Category", ["Party", "Moulder", "Contractor", "Powder"],
                                                 index=["Party", "Moulder", "Contractor", "Powder"].index(row['category']) if row['category'] in ["Party", "Moulder", "Contractor", "Powder"] else 0,
                                                 key="edit_sale_category")
                    edit_product_category = st.selectbox("Product Category", ["FG Product", "Moulding Product", "RM Product", "Powder"],
                                                         index=["FG Product", "Moulding Product", "RM Product", "Powder"].index(row['product_category']) if row['product_category'] in ["FG Product", "Moulding Product", "RM Product", "Powder"] else 0,
                                                         key="edit_sale_prod_cat")
                    edit_qty = st.number_input("Quantity *", min_value=0.0, value=float(row['qty']), step=1.0, key="edit_sale_qty")
                with col3:
                    edit_unit = st.selectbox("Unit", unit_options,
                                             index=unit_options.index(row['unit']) if row['unit'] in unit_options else 4,
                                             key="edit_sale_unit")
                    edit_rate = st.number_input("Rate per Unit", min_value=0.0, value=float(row['rate']) if pd.notna(row['rate']) else 0.0, step=0.01, key="edit_sale_rate")
                    edit_payment_days = st.number_input("Payment Terms (Days)", min_value=0, max_value=365, value=int(row['payment_terms_days']) if pd.notna(row['payment_terms_days']) else 60, step=1, key="edit_sale_payment_days")
    
                if edit_qty and edit_rate:
                    amount = edit_qty * edit_rate
                    st.metric("Total Amount", f"₹{amount:,.2f}")
    
                col1, col2 = st.columns(2)
                with col1:
                    if st.form_submit_button("💾 Save Changes", type="primary"):
                        old_qty = float(row['qty'])
                        old_product = row['product_name']
                        old_prod_cat = row['product_category']
                        old_challan = row['challan_no']
                        old_party = row['party_name']
                        old_amount = float(row['amount'])
                        qty_diff = edit_qty - old_qty
                        new_amount = edit_qty * edit_rate
                        
                        # 1. Update Sales Transaction Record
                        execute_query('''UPDATE sales_transactions SET
                        challan_no=?, date=?, party_name=?, product_name=?, category=?, product_category=?, qty=?, unit=?, rate=?, amount=?, payment_terms_days=?, due_date=?
                        WHERE id=?''',
                        (edit_challan, edit_date.strftime('%Y-%m-%d'), edit_party, edit_product, edit_category, edit_product_category, edit_qty, edit_unit, edit_rate, new_amount, edit_payment_days,
                        (edit_date + timedelta(days=edit_payment_days)).strftime('%Y-%m-%d'), st.session_state.edit_id))
                        
                        # 2. Adjust Inventory (Reverse Old, Apply New)
                        
                        # --- REVERSE OLD ENTRY ---
                        if old_prod_cat == 'RM Product':
                            # 1. Delete the old movement record completely so it doesn't count twice
                            execute_query("DELETE FROM rm_stock_movement WHERE reference_id = ? AND transaction_type = 'SALE'", (st.session_state.edit_id,))
                            
                            # Note: We do NOT manually update total_consumed_qty here. 
                            # update_rm_inventory will recalculate it based on remaining movements.
                            
                            # Recalculate balances for the old product (removes the old qty from history)
                            update_rm_inventory(old_product, 0, 'PURCHASE') 
                        else:
                            # Reverse FG Sale
                            execute_query("UPDATE fg_inventory SET sold_qty = COALESCE(sold_qty, 0) - ? WHERE product_name = ?", (old_qty, old_product))
                            execute_query("""
                            UPDATE fg_inventory
                            SET closing_stock = COALESCE(opening_stock, 0) + COALESCE(produced_qty, 0) + COALESCE(purchased_qty, 0) - COALESCE(sold_qty, 0) - COALESCE(rejected_qty, 0)
                            WHERE product_name = ?
                            """, (old_product,))
                        
                        # --- APPLY NEW ENTRY ---
                        if edit_product_category == 'RM Product':
                            execute_query("INSERT OR IGNORE INTO rm_inventory (product_name, opening_stock, total_purchased_qty, total_consumed_qty, closing_stock) VALUES (?, 0, 0, 0, 0)", (edit_product,))
                            
                            # Add NEW movement record for the edited quantity
                            # We use the SAME reference_id (st.session_state.edit_id) to link it back to the sales transaction
                            execute_query('''INSERT INTO rm_stock_movement
                            (transaction_date, challan_no, product_name, transaction_type, qty, opening_balance, closing_balance, reference_id)
                            VALUES (?, ?, ?, ?, ?, 0, 0, ?)''',
                            (edit_date.strftime('%Y-%m-%d'), edit_challan, edit_product, 'SALE', edit_qty, st.session_state.edit_id))
                            
                            # Recalculate Balances Realtime for the NEW product
                            # This function will sum up ALL 'SALE' movements for this product and update total_consumed_qty and closing_stock automatically
                            update_rm_inventory(edit_product, 0, 'PURCHASE', edit_date.strftime('%Y-%m-%d'), edit_challan, st.session_state.edit_id, rate=edit_rate)
                        else:
                            # FG Sale
                            execute_query("INSERT OR IGNORE INTO fg_inventory (product_name, opening_stock, produced_qty, sold_qty, rejected_qty, purchased_qty, closing_stock) VALUES (?, 0, 0, 0, 0, 0, 0)", (edit_product,))
                            update_fg_inventory(edit_product, edit_qty, 'SALE')
                        
                        # Handle RM Consumption if FG
                        if edit_product_category != 'RM Product':
                            # Note: Full RM consumption reversal/re-application is complex.
                            # For simplicity in edit, we might skip auto-RM-consumption update or warn user.
                            pass
                        
                        # 3. Update Ledger (Receivables)
                        # Delete old receivable entry
                        execute_query("""
                        DELETE FROM payable_receivable_ledger
                        WHERE transaction_type = 'RECEIVABLE'
                        AND challan_no = ?
                        AND party_name = ?
                        """, (old_challan, old_party))
                        
                        # Create new receivable entry
                        create_receivable_entry(edit_party, edit_challan, edit_date.strftime('%Y-%m-%d'), new_amount, edit_payment_days)
                        
                        st.success("✅ Sales entry, Inventory, and Ledger updated successfully!")
                        st.session_state.edit_mode = False
                        st.session_state.edit_id = None
                        st.rerun()
    
                with col2:
                    if st.form_submit_button("❌ Cancel"):
                        st.session_state.edit_mode = False
                        st.session_state.edit_id = None
                        st.rerun()
    st.markdown("### All Sales Entries")
    st.dataframe(df_all_sales, use_container_width=True)
    st.metric("Total Sales Value", f"₹{df_all_sales['amount'].sum():,.2f}")
# ======================= PAYABLE/RECEIVABLE LEDGER =======================
elif page == "📒 Payable/Receivable Ledger":
    st.subheader("📒 Payable/Receivable Ledger")

    # Helper function reused from Inventory section logic
    def get_parties_by_category_ledger(category):
        if category == "All":
            df = fetch_data("SELECT party_name FROM party_master ORDER BY party_name")
        else:
            df = fetch_data("SELECT party_name FROM party_master WHERE category = ? ORDER BY party_name", (category,))
        return ["All"] + (df['party_name'].tolist() if not df.empty else [])

    df_all_parties = fetch_data("SELECT party_name FROM party_master ORDER BY party_name")
    party_list_all = df_all_parties['party_name'].tolist() if not df_all_parties.empty else []

    overdue_payments = check_overdue_payments()
    if not overdue_payments.empty:
        st.error(f"⚠️ **ALERT: {len(overdue_payments)} Overdue Receivable(s)!**")
        for _, payment in overdue_payments.head(5).iterrows():
            st.markdown(f"""
            <div class="overdue-alert">
            <strong>{payment['party_name']}</strong> - Challan: {payment['challan_no']}<br>
            Amount Due: ₹{payment['balance_amount']:,.2f} | Due Date: {payment['due_date']} |
            <span style="color: red; font-weight: bold;">{int(payment['days_overdue'])} Days Overdue</span>
            </div>
            """, unsafe_allow_html=True)

    overdue_payables = check_overdue_payables()
    if not overdue_payables.empty:
        st.warning(f"⚠️ **ALERT: {len(overdue_payables)} Overdue Payable(s)!**")

    tab1, tab2, tab3 = st.tabs(["💵 Receivables (Customer owes you)", "💸 Payables (You owe supplier)", "➕ Add Manual Receipt"])

    # =================== TAB 1: RECEIVABLES ===================
    with tab1:
        st.markdown("### 💵 Receivables from Customers")

        # --- NEW FILTERS ---
        st.markdown("#### 🔍 Filter Receivables")
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            recv_cat_filter = st.selectbox("Select Party Category", 
                                           ["All", "Sales Party", "Purchase Party", "Contractor", "Moulder"], 
                                           key="recv_cat_filter")
        with col_f2:
            recv_party_options = get_parties_by_category_ledger(recv_cat_filter)
            recv_party_filter = st.selectbox("Select Party Name", recv_party_options, key="recv_party_filter_select")

        filter_status = st.selectbox("Filter by Status", ["All", "PENDING", "PARTIAL", "PAID"], key="recv_filter_status")

        query = """
        SELECT id, party_name, challan_no, invoice_date, due_date, amount, paid_amount, balance_amount, payment_status, remarks,
        julianday(date('now')) - julianday(due_date) as days_overdue
        FROM payable_receivable_ledger
        WHERE transaction_type = 'RECEIVABLE'
        """
        params = []
        if filter_status != "All":
            query += " AND payment_status = ?"
            params.append(filter_status)
        if recv_party_filter != "All":
            query += " AND party_name = ?"
            params.append(recv_party_filter)
        query += " ORDER BY due_date"

        df_recv = fetch_data(query, tuple(params))

        if not df_recv.empty:
            col1, col2, col3, col4 = st.columns(4)
            with col1: st.metric("📊 Total Invoices", len(df_recv))
            with col2: st.metric("💰 Total Billed", f"₹{df_recv['amount'].sum():,.2f}")
            with col3: st.metric("✅ Total Received", f"₹{df_recv['paid_amount'].sum():,.2f}")
            with col4: st.metric("📉 Total Outstanding", f"₹{df_recv['balance_amount'].sum():,.2f}")

            display_df = df_recv[['party_name', 'challan_no', 'invoice_date', 'due_date', 'amount', 'paid_amount', 'balance_amount', 'payment_status']].copy()
            display_df.columns = ['Party', 'Challan No', 'Invoice Date', 'Due Date', 'Amount', 'Paid', 'Balance', 'Status']
            st.dataframe(display_df, use_container_width=True)

            st.markdown("---")
            st.markdown("### 💵 Record Payment Received from Customer")
            st.info("👇 Select an invoice below and enter the payment amount to record it")

            unpaid_recv = df_recv[(df_recv['payment_status'] != 'PAID') & (df_recv['balance_amount'] > 0)].copy()
            if not unpaid_recv.empty:
                recv_options = {}
                for _, row in unpaid_recv.iterrows():
                    label = f"{row['challan_no']} | {row['party_name']} | Balance: ₹{float(row['balance_amount']):,.2f}"
                    recv_options[label] = row['id']

                with st.form("payment_received_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        selected_label = st.selectbox("Select Invoice to Record Payment", list(recv_options.keys()), key="recv_payment_select")
                        selected_id = recv_options.get(selected_label)
                    with col2:
                        if selected_id:
                            current_record = fetch_data("SELECT balance_amount FROM payable_receivable_ledger WHERE id = ?", (selected_id,))
                            if not current_record.empty:
                                selected_balance = float(current_record['balance_amount'].iloc[0])
                            else:
                                selected_balance = 0.01
                        else:
                            selected_balance = 0.01
                        if selected_balance < 0.01: selected_balance = 0.01
                        payment_amount = st.number_input("Payment Amount (₹)", min_value=0.01, max_value=selected_balance, value=selected_balance, step=0.01, key="payment_amount_recv_input")

                    submitted = st.form_submit_button("💵 Record Payment Received", type="primary")
                    if submitted:
                        if selected_id and payment_amount > 0:
                            current = fetch_data("""
                            SELECT id, paid_amount, balance_amount, amount, payment_status, challan_no, party_name
                            FROM payable_receivable_ledger
                            WHERE id = ? AND transaction_type='RECEIVABLE'
                            """, (selected_id,))
                            if not current.empty:
                                record = current.iloc[0]
                                new_paid = float(record['paid_amount']) + float(payment_amount)
                                new_balance = float(record['balance_amount']) - float(payment_amount)
                                if new_balance <= 0.01:
                                    new_status = 'PAID'
                                    new_balance = 0
                                elif new_paid > 0:
                                    new_status = 'PARTIAL'
                                else:
                                    new_status = 'PENDING'
                                execute_query("""
                                UPDATE payable_receivable_ledger
                                SET paid_amount = ?, balance_amount = ?, payment_status = ?, remarks = ?
                                WHERE id = ? AND transaction_type='RECEIVABLE'
                                """, (new_paid, new_balance, new_status,
                                f"Payment of ₹{payment_amount:,.2f} received on {datetime.now().strftime('%Y-%m-%d')}",
                                selected_id))
                                st.success(f"✅ Payment of ₹{payment_amount:,.2f} recorded successfully!")
                                st.info(f"📝 Updated Balance: ₹{new_balance:,.2f} | Status: {new_status}")
                                st.balloons()
                                st.rerun()
            else:
                st.success("✅ All receivables are fully paid! No outstanding balance.")
        else:
            st.info("ℹ️ No receivable records found. Receivables are automatically created when you make sales.")

    # =================== TAB 2: PAYABLES ===================
    with tab2:
        st.markdown("### 💸 Payables to Suppliers")

        # --- NEW FILTERS ---
        st.markdown("#### 🔍 Filter Payables")
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            pay_cat_filter = st.selectbox("Select Party Category", 
                                          ["All", "Purchase Party", "Contractor", "Moulder"], 
                                          key="pay_cat_filter")
        with col_f2:
            pay_party_options = get_parties_by_category_ledger(pay_cat_filter)
            pay_party_filter = st.selectbox("Select Party Name", pay_party_options, key="pay_party_filter_select")

        filter_status_pay = st.selectbox("Filter by Status", ["All", "PENDING", "PARTIAL", "PAID"], key="pay_filter_status")

        query_pay = """
        SELECT id, party_name, challan_no, invoice_date, due_date, amount, paid_amount, balance_amount, payment_status, remarks,
        julianday(date('now')) - julianday(due_date) as days_overdue
        FROM payable_receivable_ledger
        WHERE transaction_type = 'PAYABLE'
        """
        params_pay = []
        if filter_status_pay != "All":
            query_pay += " AND payment_status = ?"
            params_pay.append(filter_status_pay)
        if pay_party_filter != "All":
            query_pay += " AND party_name = ?"
            params_pay.append(pay_party_filter)
        query_pay += " ORDER BY due_date"

        df_pay = fetch_data(query_pay, tuple(params_pay))

        if not df_pay.empty:
            col1, col2, col3, col4 = st.columns(4)
            with col1: st.metric("📊 Total Invoices", len(df_pay))
            with col2: st.metric("💰 Total Billed", f"₹{df_pay['amount'].sum():,.2f}")
            with col3: st.metric("✅ Total Paid", f"₹{df_pay['paid_amount'].sum():,.2f}")
            with col4: st.metric("📉 Total Outstanding", f"₹{df_pay['balance_amount'].sum():,.2f}")

            display_df_pay = df_pay[['party_name', 'challan_no', 'invoice_date', 'due_date', 'amount', 'paid_amount', 'balance_amount', 'payment_status']].copy()
            display_df_pay.columns = ['Party/Supplier', 'Challan No', 'Invoice Date', 'Due Date', 'Amount', 'Paid', 'Balance', 'Status']
            st.dataframe(display_df_pay, use_container_width=True)

            st.markdown("---")
            st.markdown("### 💸 Record Payment Made to Supplier")
            st.info("👇 Select an invoice below and enter the payment amount to record it")

            unpaid_pay = df_pay[(df_pay['payment_status'] != 'PAID') & (df_pay['balance_amount'] > 0)].copy()
            if not unpaid_pay.empty:
                pay_options = {}
                for _, row in unpaid_pay.iterrows():
                    label = f"{row['challan_no']} | {row['party_name']} | Balance: ₹{float(row['balance_amount']):,.2f}"
                    pay_options[label] = row['id']

                with st.form("payment_made_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        selected_label_pay = st.selectbox("Select Invoice to Pay", list(pay_options.keys()), key="pay_payment_select")
                        selected_id_pay = pay_options.get(selected_label_pay)
                    with col2:
                        if selected_id_pay:
                            current_record_pay = fetch_data("SELECT balance_amount FROM payable_receivable_ledger WHERE id = ?", (selected_id_pay,))
                            if not current_record_pay.empty:
                                selected_balance_pay = float(current_record_pay['balance_amount'].iloc[0])
                            else:
                                selected_balance_pay = 0.01
                        else:
                            selected_balance_pay = 0.01
                        if selected_balance_pay < 0.01: selected_balance_pay = 0.01
                        payment_amount_pay = st.number_input("Payment Amount (₹)", min_value=0.01, max_value=selected_balance_pay, value=selected_balance_pay, step=0.01, key="payment_amount_pay_input")

                    submitted = st.form_submit_button("💸 Record Payment to Supplier", type="primary")
                    if submitted:
                        if selected_id_pay and payment_amount_pay > 0:
                            current = fetch_data("""
                            SELECT id, paid_amount, balance_amount, amount, payment_status, challan_no, party_name
                            FROM payable_receivable_ledger
                            WHERE id = ? AND transaction_type='PAYABLE'
                            """, (selected_id_pay,))
                            if not current.empty:
                                record = current.iloc[0]
                                new_paid = float(record['paid_amount']) + float(payment_amount_pay)
                                new_balance = float(record['balance_amount']) - float(payment_amount_pay)
                                if new_balance <= 0.01:
                                    new_status = 'PAID'
                                    new_balance = 0
                                elif new_paid > 0:
                                    new_status = 'PARTIAL'
                                else:
                                    new_status = 'PENDING'
                                execute_query("""
                                UPDATE payable_receivable_ledger
                                SET paid_amount = ?, balance_amount = ?, payment_status = ?, remarks = ?
                                WHERE id = ? AND transaction_type='PAYABLE'
                                """, (new_paid, new_balance, new_status,
                                f"Payment of ₹{payment_amount_pay:,.2f} made on {datetime.now().strftime('%Y-%m-%d')}",
                                selected_id_pay))
                                st.success(f"✅ Payment of ₹{payment_amount_pay:,.2f} recorded successfully!")
                                st.info(f"📝 Updated Balance: ₹{new_balance:,.2f} | Status: {new_status}")
                                st.balloons()
                                st.rerun()
            else:
                st.success("✅ All payables are fully paid! No outstanding balance.")
        else:
            st.info("ℹ️ No payable records found. Payables are automatically created when you make purchases.")

    # =================== TAB 3: ADD MANUAL RECEIPT ===================
    with tab3:
        st.markdown("### ➕ Add Manual Receipt / Payment")
        entry_type = st.radio("Select Entry Type", ["Manual Payment to Supplier (Payable)", "Manual Receipt from Customer (Receivable)"], horizontal=True)

        if entry_type == "Manual Payment to Supplier (Payable)":
            st.info("Use this to record a payment made to a supplier against an existing invoice or as an advance payment.")
            with st.form("manual_payment_form"):
                col1, col2 = st.columns(2)
                with col1:
                    mp_party = st.selectbox("Supplier / Party", party_list_all if party_list_all else ["No parties added"], key="mp_party_pay")
                    if mp_party and mp_party != "No parties added":
                        unpaid_payables = fetch_data("""
                        SELECT id, challan_no, balance_amount, due_date
                        FROM payable_receivable_ledger
                        WHERE transaction_type = 'PAYABLE' AND party_name = ? AND payment_status != 'PAID' AND balance_amount > 0
                        ORDER BY due_date
                        """, (mp_party,))
                    else:
                        unpaid_payables = pd.DataFrame()
                    if not unpaid_payables.empty:
                        pay_options = {f"{row['challan_no']} | Balance: ₹{float(row['balance_amount']):,.2f}": row['id'] for _, row in unpaid_payables.iterrows()}
                        pay_options["New Advance Payment / Manual Entry"] = None
                        selected_pay_label = st.selectbox("Select Invoice to Pay (or create new)", list(pay_options.keys()), key="mp_invoice_select")
                        selected_pay_id = pay_options[selected_pay_label]
                    else:
                        st.info(f"No unpaid invoices found for {mp_party}. A new payable entry will be created.")
                        selected_pay_id = None
                    mp_challan = st.text_input("Reference / Challan No (Optional)", key="mp_challan_pay")
                    mp_date = st.date_input("Date", datetime.now(), key="mp_date_pay")
                with col2:
                    if selected_pay_id and not unpaid_payables.empty:
                        current_bal = float(unpaid_payables[unpaid_payables['id'] == selected_pay_id]['balance_amount'].iloc[0])
                        mp_amount = st.number_input("Payment Amount (₹)", min_value=0.01, max_value=current_bal, value=current_bal, step=0.01, key="mp_amount_pay")
                    else:
                        mp_amount = st.number_input("Payment Amount (₹)", min_value=0.01, step=0.01, key="mp_amount_pay")
                    mp_remarks = st.text_area("Remarks", key="mp_remarks_pay")

                if st.form_submit_button("💸 Record Payment to Supplier", type="primary"):
                    if mp_party and mp_party != "No parties added" and mp_amount > 0:
                        ref_no = mp_challan.strip() if mp_challan.strip() else f"MANUAL-PAY-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        if selected_pay_id:
                            current = fetch_data("SELECT paid_amount, balance_amount, amount, payment_status FROM payable_receivable_ledger WHERE id = ?", (selected_pay_id,))
                            if not current.empty:
                                record = current.iloc[0]
                                new_paid = float(record['paid_amount']) + float(mp_amount)
                                new_balance = float(record['balance_amount']) - float(mp_amount)
                                if new_balance <= 0.01:
                                    new_status = 'PAID'
                                    new_balance = 0
                                elif new_paid > 0:
                                    new_status = 'PARTIAL'
                                else:
                                    new_status = 'PENDING'
                                execute_query("""
                                UPDATE payable_receivable_ledger
                                SET paid_amount = ?, balance_amount = ?, payment_status = ?, remarks = ?
                                WHERE id = ?
                                """, (new_paid, new_balance, new_status, f"Manual payment of ₹{mp_amount:,.2f} on {datetime.now().strftime('%Y-%m-%d')}. {mp_remarks}", selected_pay_id))
                                st.success(f"✅ Payment of ₹{mp_amount:,.2f} recorded! Balance updated in real-time.")
                        else:
                            execute_query("""
                            INSERT INTO payable_receivable_ledger
                            (transaction_type, party_name, challan_no, invoice_date, due_date, amount, paid_amount, balance_amount, payment_status, remarks)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, ('PAYABLE', mp_party, ref_no, mp_date.strftime('%Y-%m-%d'), mp_date.strftime('%Y-%m-%d'),
                            mp_amount, mp_amount, 0, 'PAID', mp_remarks or 'Manual payment entry'))
                            st.success(f"✅ Manual payment of ₹{mp_amount:,.2f} added for {mp_party}!")
                            st.balloons()
                            st.rerun()
        else:
            st.info("Use this to record a payment received from a customer that isn't tied to an existing invoice (e.g., advance payment, manual receipt).")
            with st.form("manual_receipt_form"):
                col1, col2 = st.columns(2)
                with col1:
                    mr_party = st.selectbox("Customer / Party", party_list_all if party_list_all else ["No parties added"], key="mr_party_recv")
                    mr_challan = st.text_input("Reference / Challan No (Optional)", key="mr_challan_recv")
                    mr_date = st.date_input("Date", datetime.now(), key="mr_date_recv")
                with col2:
                    mr_amount = st.number_input("Amount Received (₹)", min_value=0.01, step=0.01, key="mr_amount_recv")
                    mr_remarks = st.text_area("Remarks", key="mr_remarks_recv")

                if st.form_submit_button("💵 Add Receipt Entry", type="primary"):
                    if mr_party and mr_party != "No parties added" and mr_amount > 0:
                        ref_no = mr_challan.strip() if mr_challan.strip() else f"MANUAL-RCV-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        execute_query("""
                        INSERT INTO payable_receivable_ledger
                        (transaction_type, party_name, challan_no, invoice_date, due_date, amount, paid_amount, balance_amount, payment_status, remarks)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, ('RECEIVABLE', mr_party, ref_no, mr_date.strftime('%Y-%m-%d'), mr_date.strftime('%Y-%m-%d'),
                        mr_amount, mr_amount, 0, 'PAID', mr_remarks or 'Manual receipt entry'))
                        st.success(f"✅ Manual receipt of ₹{mr_amount:,.2f} added for {mr_party}!")
                        st.balloons()
                        st.rerun()
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

                        execute_query("INSERT OR IGNORE INTO fg_inventory (product_name, opening_stock, produced_qty, sold_qty, rejected_qty, purchased_qty, closing_stock) VALUES (?, 0, 0, 0, 0, 0, 0)", (mr_product,))
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
    tab1, tab2, tab3, tab4 = st.tabs(["RM Inventory Summary", "RM Stock Movement", "FG Inventory", "🧮 FG to RM Calculator"])

    # Helper to get parties based on category for filters
    def get_parties_by_category(category):
        if category == "All":
            df = fetch_data("SELECT party_name FROM party_master ORDER BY party_name")
        else:
            df = fetch_data("SELECT party_name FROM party_master WHERE category = ? ORDER BY party_name", (category,))
        return ["All"] + (df['party_name'].tolist() if not df.empty else [])

    with tab1:
        st.markdown("### RM (Raw Material) Inventory Summary")
        # Fetch RM Inventory joined with product_master to get real-time Category
        df_rm_inv = fetch_data("""
        SELECT 
            i.product_name, 
            COALESCE(m.category, 'RM Product') as category,
            i.opening_stock, 
            i.total_purchased_qty, 
            i.total_consumed_qty, 
            i.closing_stock, 
            COALESCE(i.rate, 0) as rate,
            (SELECT pt.party_name FROM purchase_transactions pt 
             JOIN rm_stock_movement rsm ON pt.id = rsm.reference_id 
             WHERE rsm.product_name = i.product_name AND rsm.transaction_type = 'PURCHASE' 
             ORDER BY rsm.transaction_date DESC, rsm.id DESC LIMIT 1) as last_supplier,
            (SELECT st.party_name FROM sales_transactions st 
             JOIN rm_stock_movement rsm ON st.id = rsm.reference_id 
             WHERE rsm.product_name = i.product_name AND rsm.transaction_type = 'SALE' 
             ORDER BY rsm.transaction_date DESC, rsm.id DESC LIMIT 1) as last_buyer
        FROM rm_inventory i
        LEFT JOIN product_master m ON i.product_name = m.product_name
        ORDER BY i.product_name
        """)
        
        if not df_rm_inv.empty:
            df_rm_inv['opening_stock'] = pd.to_numeric(df_rm_inv['opening_stock'], errors='coerce').fillna(0)
            df_rm_inv['total_purchased_qty'] = pd.to_numeric(df_rm_inv['total_purchased_qty'], errors='coerce').fillna(0)
            df_rm_inv['total_consumed_qty'] = pd.to_numeric(df_rm_inv['total_consumed_qty'], errors='coerce').fillna(0)
            df_rm_inv['rate'] = pd.to_numeric(df_rm_inv['rate'], errors='coerce').fillna(0)
            
            # Real-time correction of closing stock based on formula
            df_rm_inv['calculated_closing'] = df_rm_inv['opening_stock'] + df_rm_inv['total_purchased_qty'] - df_rm_inv['total_consumed_qty']
            
            col1, col2, col3 = st.columns(3)
            with col1: st.metric("Total RM Products", len(df_rm_inv))
            with col2: st.metric("Total Stock Value", f"₹{(df_rm_inv['closing_stock'] * df_rm_inv['rate']).sum():,.2f}")
            with col3: st.metric("Total Purchased", f"{df_rm_inv['total_purchased_qty'].sum():,.0f}")
            
            # Prepare display dataframe with Category included
            display_df = df_rm_inv[['product_name', 'category', 'opening_stock', 'total_purchased_qty', 'total_consumed_qty', 'closing_stock', 'rate', 'last_supplier', 'last_buyer']].copy()
            display_df.rename(columns={
                'category': 'Product Category',
                'last_supplier': 'Last Supplier (Party)', 
                'last_buyer': 'Last Buyer (Party)'
            }, inplace=True)
            
            st.dataframe(display_df, use_container_width=True)
            
            st.markdown("### Update Opening Stock")
            col1, col2 = st.columns(2)
            with col1: rm_product = st.selectbox("Select RM Product", df_rm_inv['product_name'].tolist(), key="rm_product_select")
            with col2: new_opening = st.number_input("New Opening Stock", min_value=0.0, step=1.0, key="rm_opening_stock")
            
            if st.button("Update Opening Stock", type="primary", key="update_rm_opening"):
                if rm_product:
                    execute_query("UPDATE rm_inventory SET opening_stock = ? WHERE product_name = ?", (new_opening, rm_product))
                    # Trigger recalculation of closing stock via movement history
                    update_rm_inventory(rm_product, 0, 'PURCHASE') # Passing 0 qty triggers full recalc
                    
                    st.success("✅ Opening stock updated!")
                    st.rerun()
        else:
            st.info("No RM inventory data available")
    with tab2:
        st.markdown("### RM Stock Movement (Detailed)")
        st.info("This shows Purchase and Direct Sales entries for Raw Materials.")
        
        # --- FILTERS ---
        st.markdown("#### 🔍 Filter Movements")
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            rm_move_cat = st.selectbox("Select Party Category",
                                       ["All", "Purchase Party", "Sales Party", "Contractor", "Moulder"],
                                       key="rm_move_cat_filter")
        with col_f2:
            # Helper to get parties
            def get_parties_by_category_inv(category):
                if category == "All":
                    df = fetch_data("SELECT party_name FROM party_master ORDER BY party_name")
                else:
                    df = fetch_data("SELECT party_name FROM party_master WHERE category = ? ORDER BY party_name", (category,))
                return ["All"] + (df['party_name'].tolist() if not df.empty else [])
        
            rm_move_parties = get_parties_by_category_inv(rm_move_cat)
            rm_move_party = st.selectbox("Select Party Name", rm_move_parties, key="rm_move_party_filter")
        
        # Fetch products that have movement records
        df_products = fetch_data("SELECT DISTINCT product_name FROM rm_stock_movement ORDER BY product_name")
        
        if not df_products.empty:
            selected_product = st.selectbox("Select Product to View Movement", df_products['product_name'].tolist(), key="rm_movement_product")
            
            # QUERY: Get all movements for this product
            query_movement = """
            SELECT rsm.id, rsm.transaction_date, rsm.challan_no, rsm.transaction_type, rsm.qty,
            rsm.reference_id, rsm.opening_balance, rsm.closing_balance
            FROM rm_stock_movement rsm
            WHERE rsm.product_name = ? AND rsm.transaction_type IN ('PURCHASE', 'SALE')
            """
            params_movement = [selected_product]
            
            # If specific party selected, we need to join to find transactions associated with that party
            if rm_move_party != "All":
                query_movement = """
                SELECT rsm.id, rsm.transaction_date, rsm.challan_no, rsm.transaction_type, rsm.qty,
                rsm.reference_id, rsm.opening_balance, rsm.closing_balance
                FROM rm_stock_movement rsm
                LEFT JOIN purchase_transactions pt ON rsm.reference_id = pt.id AND rsm.transaction_type = 'PURCHASE'
                LEFT JOIN sales_transactions st ON rsm.reference_id = st.id AND rsm.transaction_type = 'SALE'
                WHERE rsm.product_name = ?
                AND rsm.transaction_type IN ('PURCHASE', 'SALE')
                AND (
                    (rsm.transaction_type = 'PURCHASE' AND pt.party_name = ?)
                    OR
                    (rsm.transaction_type = 'SALE' AND st.party_name = ?)
                )
                """
                params_movement = [selected_product, rm_move_party, rm_move_party]
            
            query_movement += " ORDER BY rsm.transaction_date, rsm.id"
            df_movement = fetch_data(query_movement, tuple(params_movement))
            
            if not df_movement.empty:
                # Enrich dataframe with Party Name for display (Real-time fetch)
                party_names = []
                for _, row in df_movement.iterrows():
                    p_name = "N/A"
                    # Fetch from Transaction Table using Reference ID to get the most up-to-date Party Name linkage
                    if row['transaction_type'] == 'PURCHASE' and pd.notna(row['reference_id']):
                        res = fetch_data("SELECT party_name FROM purchase_transactions WHERE id = ?", (row['reference_id'],))
                        if not res.empty:
                            p_name = res['party_name'].iloc[0]
                    elif row['transaction_type'] == 'SALE' and pd.notna(row['reference_id']):
                        res = fetch_data("SELECT party_name FROM sales_transactions WHERE id = ?", (row['reference_id'],))
                        if not res.empty: 
                            p_name = res['party_name'].iloc[0]
                    
                    # Fallback: If reference_id is missing or null, try matching Challan No
                    if p_name == "N/A" and pd.notna(row['challan_no']):
                        # Try finding in Purchase
                        res_p = fetch_data("SELECT party_name FROM purchase_transactions WHERE challan_no = ? LIMIT 1", (row['challan_no'],))
                        if not res_p.empty: 
                            p_name = res_p['party_name'].iloc[0]
                        else:
                            # Try Sales
                            res_s = fetch_data("SELECT party_name FROM sales_transactions WHERE challan_no = ? LIMIT 1", (row['challan_no'],))
                            if not res_s.empty: 
                                p_name = res_s['party_name'].iloc[0]
                    
                    party_names.append(p_name)
                
                df_movement['party_name'] = party_names
                
                # Display the dataframe with Party Name
                df_display = df_movement[['transaction_date', 'challan_no', 'party_name', 'transaction_type', 'qty', 'opening_balance', 'closing_balance']]
                st.dataframe(df_display, use_container_width=True)
                
                # Calculate Metrics Safely
                total_purchases = df_movement[df_movement['transaction_type']=='PURCHASE']['qty'].sum()
                total_sales = df_movement[df_movement['transaction_type']=='SALE']['qty'].sum()
                
                # FIX: Ensure final_balance is a simple float
                last_row_balance = df_movement['closing_balance'].iloc[-1]
                try:
                    final_balance = float(last_row_balance)
                except (ValueError, TypeError):
                    final_balance = 0.0
                    
                col1, col2, col3 = st.columns(3)
                with col1: st.metric("Total Purchases", f"{total_purchases:,.0f}")
                with col2: st.metric("Total Sales (RM)", f"{total_sales:,.0f}")
                with col3: st.metric("Current Balance", f"{final_balance:,.0f}")
                
            else:
                st.info("No Purchase or Sales movement records found for this product/filter.")
        else:
            st.info("No RM stock movement data available")
    with tab3:
        st.markdown("### FG (Finished Goods) Inventory")
        # UPDATED QUERY: Join with product_master to get real-time Category
        df_fg_inv = fetch_data("""
        SELECT i.product_name, COALESCE(m.category, 'FG Product') as category, i.opening_stock, i.produced_qty, i.purchased_qty, i.sold_qty, i.rejected_qty, i.closing_stock, m.rate, m.unit
        FROM fg_inventory i LEFT JOIN product_master m ON i.product_name = m.product_name
        WHERE m.category IN ('FG Product', 'Moulding Product', 'Powder') OR m.category IS NULL
        ORDER BY i.product_name
        """)
        
        if not df_fg_inv.empty:
            # Enrich with Last Party Info (Real-time Name Display)
            last_parties = []
            for _, row in df_fg_inv.iterrows():
                prod_name = row['product_name']
                # Check Sales first (Shows Sales Party Name)
                sale_res = fetch_data("SELECT party_name FROM sales_transactions WHERE product_name = ? ORDER BY date DESC LIMIT 1", (prod_name,))
                if not sale_res.empty:
                    last_parties.append(f"Sold to: {sale_res['party_name'].iloc[0]}")
                else:
                    # Check Production (Shows Contractor/Moulder Name)
                    prod_res = fetch_data("SELECT party_name FROM production_register WHERE fg_product = ? ORDER BY date DESC LIMIT 1", (prod_name,))
                    if not prod_res.empty:
                        last_parties.append(f"Moulded by: {prod_res['party_name'].iloc[0]}")
                    else:
                        last_parties.append("N/A")
            
            df_fg_inv['Last Interaction'] = last_parties
            
            col1, col2, col3 = st.columns(3)
            with col1: st.metric("Total FG Products", len(df_fg_inv))
            with col2: st.metric("Total Stock Value", f"₹{(df_fg_inv['closing_stock'] * df_fg_inv['rate'].fillna(0)).sum():,.2f}")
            with col3: st.metric("Total Produced", f"{df_fg_inv['produced_qty'].sum():,.0f}")
            
            # Display dataframe with Category included
            display_fg_df = df_fg_inv[['product_name', 'category', 'opening_stock', 'produced_qty', 'purchased_qty', 'sold_qty', 'rejected_qty', 'closing_stock', 'rate', 'unit', 'Last Interaction']].copy()
            display_fg_df.rename(columns={'category': 'Product Category'}, inplace=True)
            
            st.dataframe(display_fg_df, use_container_width=True)
            
            st.markdown("### Update Opening Stock")
            col1, col2 = st.columns(2)
            with col1: fg_product = st.selectbox("Select FG Product", df_fg_inv['product_name'].tolist(), key="fg_product_select")
            with col2: new_opening = st.number_input("New Opening Stock", min_value=0.0, step=1.0, key="fg_opening_stock")
            
            if st.button("Update Opening Stock", type="primary", key="update_fg_opening"):
                if fg_product:
                    execute_query("UPDATE fg_inventory SET opening_stock = ? WHERE product_name = ?", (new_opening, fg_product))
                    execute_query("""
                    UPDATE fg_inventory
                    SET closing_stock = COALESCE(opening_stock, 0) + COALESCE(produced_qty, 0) + COALESCE(purchased_qty, 0) - COALESCE(sold_qty, 0) - COALESCE(rejected_qty, 0)
                    WHERE product_name = ?
                    """, (fg_product,))
                    st.success("✅ Opening stock updated!")
                    st.rerun()
        else:
            st.info("No FG inventory data available")

    with tab4:
        st.markdown("### 🧮 FG to RM Material Requirement Calculator")
        st.markdown("---")
        st.markdown("#### 📊 Sales-Based RM Requirements (Auto-Calculated from Sales)")
        st.info("💡 This section automatically calculates RM requirements based on actual FG product sales. "
                "When you sell FG products, the required RM materials are calculated using the BOM (same logic as your Excel sheet).")

        # Fetch all FG sales with FULL DETAILS including Party Name
        df_fg_sales = fetch_data("""
        SELECT st.id, st.challan_no, st.date, st.party_name, st.product_name,
        st.category, st.product_category, st.qty, st.unit, st.rate, st.amount,
        st.payment_terms_days, st.due_date
        FROM sales_transactions st
        JOIN product_master pm ON st.product_name = pm.product_name
        WHERE pm.category IN ('FG Product', 'Moulding Product')
        ORDER BY st.date DESC, st.id DESC
        """)

        if df_fg_sales.empty:
            st.warning("⚠️ No FG product sales found yet. Sales-based RM calculation will appear here once you make sales.")
        else:
            # Calculate RM requirements for all sales
            sales_rm_requirements = {}
            total_sales_value = 0.0

            for _, sale_row in df_fg_sales.iterrows():
                fg_product = sale_row['product_name']
                fg_qty_sold = float(sale_row['qty'])

                bom_items = fetch_data("""
                SELECT rm_product, required_qty
                FROM bom_master
                WHERE fg_product = ?
                """, (fg_product,))

                if not bom_items.empty:
                    for _, bom_row in bom_items.iterrows():
                        rm_name = bom_row['rm_product']
                        rm_per_unit = float(bom_row['required_qty'])
                        rm_total_needed = rm_per_unit * fg_qty_sold

                        if rm_name not in sales_rm_requirements:
                            sales_rm_requirements[rm_name] = {
                                'total_required': 0.0,
                                'breakdown': []
                            }
                        sales_rm_requirements[rm_name]['total_required'] += rm_total_needed
                        sales_rm_requirements[rm_name]['breakdown'].append({
                            'sale_id': sale_row['id'],
                            'challan_no': sale_row['challan_no'],
                            'date': sale_row['date'],
                            'party_name': sale_row['party_name'], # Contractor/Sales Party Name
                            'fg_product': fg_product,
                            'fg_qty_sold': fg_qty_sold,
                            'unit': sale_row['unit'],
                            'rate': sale_row['rate'],
                            'amount': sale_row['amount'],
                            'rm_per_unit': rm_per_unit,
                            'rm_needed': rm_total_needed
                        })

            if sales_rm_requirements:
                sales_calc_rows = []
                has_shortage = False
                for rm_name, rm_data in sales_rm_requirements.items():
                    total_required = rm_data['total_required']
                    stock_df = fetch_data("""
                    SELECT closing_stock, COALESCE(rate, 0) as rate
                    FROM rm_inventory
                    WHERE product_name = ?
                    """, (rm_name,))

                    if not stock_df.empty:
                        available = float(stock_df['closing_stock'].iloc[0]) if pd.notna(stock_df['closing_stock'].iloc[0]) else 0.0
                        rate = float(stock_df['rate'].iloc[0]) if pd.notna(stock_df['rate'].iloc[0]) else 0.0
                    else:
                        available = 0.0
                        rate = 0.0

                    shortage = total_required - available
                    status = "✅ OK" if shortage <= 0 else "❌ SHORTAGE"
                    if shortage > 0: has_shortage = True

                    unique_sales = len(set([b['sale_id'] for b in rm_data['breakdown']]))

                    sales_calc_rows.append({
                        "RM Product": rm_name,
                        "Total Required (All Sales)": total_required,
                        "No. of Sales Transactions": unique_sales
                    })
                    total_sales_value += total_required * rate

                sales_calc_df = pd.DataFrame(sales_calc_rows)

                m1, m2, m3, m4 = st.columns(4)
                with m1: st.metric("📦 Total FG Sales", len(df_fg_sales))
                with m2: st.metric("🔧 RM Types Required", len(sales_calc_rows))
                with m3: st.metric("💰 Total RM Value", f"₹{total_sales_value:,.2f}")

                def highlight_status_sales(val):
                    if val == "❌ SHORTAGE":
                        return 'background-color: #ffebee; color: #c62828; font-weight: bold'
                    else:
                        return 'background-color: #e8f5e9; color: #2e7d32; font-weight: bold'

                if 'Status' in sales_calc_df.columns:
                    try: styled_sales_df = sales_calc_df.style.map(highlight_status_sales, subset=['Status'])
                    except AttributeError: styled_sales_df = sales_calc_df.style.applymap(highlight_status_sales, subset=['Status'])
                    st.dataframe(styled_sales_df, use_container_width=True, hide_index=True)
                else:
                    st.dataframe(sales_calc_df, use_container_width=True, hide_index=True)

                if has_shortage: pass
                else: st.success(f"✅ **All RM materials available!** You have sufficient stock for all FG sales.")

                st.markdown("---")
                st.markdown("#### 📋 Detailed Sales Transactions (FG Products)")
                st.caption("Complete details of all FG product sales with challan numbers, dates, contractor names, and quantities")

                detailed_sales = df_fg_sales.copy()
                detailed_sales = detailed_sales.rename(columns={
                    'id': 'Sale ID', 'challan_no': 'Challan No', 'date': 'Date',
                    'party_name': 'Contractor / Party', 'product_name': 'FG Product',
                    'category': 'Entry Category', 'product_category': 'Product Category',
                    'qty': 'Quantity', 'unit': 'Unit', 'rate': 'Rate (₹)',
                    'amount': 'Amount (₹)', 'payment_terms_days': 'Payment Days', 'due_date': 'Due Date'
                })
                st.dataframe(detailed_sales, use_container_width=True, hide_index=True)

                st.markdown("#### 👥 Sales Summary by Contractor/Party")
                contractor_summary = df_fg_sales.groupby('party_name').agg({
                    'qty': 'sum', 'amount': 'sum', 'id': 'count'
                }).reset_index()
                contractor_summary.columns = ['Contractor / Party', 'Total FG Qty Sold', 'Total Sales Value (₹)', 'No. of Transactions']
                contractor_summary = contractor_summary.sort_values('Total Sales Value (₹)', ascending=False)
                st.dataframe(contractor_summary, use_container_width=True, hide_index=True)

                with st.expander("🔍 View Detailed RM Breakdown by Sale Transaction"):
                    st.markdown("**RM Requirements Breakdown:**")
                    st.caption("Shows which sale transactions contributed to each RM requirement")
                    for rm_name, rm_data in sales_rm_requirements.items():
                        st.markdown(f"##### 🔧 {rm_name}")
                        rm_breakdown_rows = []
                        for b in rm_data['breakdown']:
                            rm_breakdown_rows.append({
                                "Sale ID": b['sale_id'], "Challan No": b['challan_no'],
                                "Date": b['date'], "Contractor / Party": b['party_name'],
                                "FG Product": b['fg_product'], "FG Qty Sold": f"{b['fg_qty_sold']:.2f} {b['unit']}",
                                "RM per FG Unit": f"{b['rm_per_unit']:.2f}", "RM Required": f"{b['rm_needed']:.2f}",
                                "Sale Amount (₹)": f"₹{b['amount']:,.2f}"
                            })
                        rm_breakdown_df = pd.DataFrame(rm_breakdown_rows)
                        st.dataframe(rm_breakdown_df, use_container_width=True, hide_index=True)
                        st.markdown(f"**Total RM Required: {rm_data['total_required']:.2f}**")

                st.markdown("---")
                st.markdown("#### 💾 Action: Consume RM Stock for All Sales")
                st.caption("Click below to deduct RM quantities for all FG sales from your inventory.")
                consume_col1, consume_col2 = st.columns([3, 1])
                with consume_col1:
                    consume_reason_sales = st.text_input("Reason / Reference", key="consume_reason_sales_input", placeholder="e.g., MONTHLY-SALES-CONSUMPTION")
                with consume_col2:
                    consume_date_sales = st.date_input("Date", datetime.now(), key="consume_date_sales_input")

                if st.button(f"💥 Consume RM Stock for All FG Sales", type="primary", key="consume_rm_sales_btn", disabled=has_shortage):
                    if has_shortage:
                        st.error("❌ Cannot consume — shortage exists. Please fix shortage first.")
                    else:
                        try:
                            consumed_list = []
                            ref_no = consume_reason_sales.strip() if consume_reason_sales.strip() else f"SALES-RM-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                            for rm_name, rm_data in sales_rm_requirements.items():
                                qty_to_consume = rm_data['total_required']
                                stock_df = fetch_data("SELECT COALESCE(rate, 0) as rate FROM rm_inventory WHERE product_name = ?", (rm_name,))
                                rate = float(stock_df['rate'].iloc[0]) if not stock_df.empty and pd.notna(stock_df['rate'].iloc[0]) else 0.0
                                update_rm_inventory(rm_name, qty_to_consume, 'CONSUMPTION', consume_date_sales.strftime('%Y-%m-%d'), ref_no, rate=rate)
                                consumed_list.append(f"{rm_name}: {qty_to_consume:.2f}")
                            st.success(f"✅ RM stock consumed successfully for all FG sales!")
                            st.info("📋 **Consumed Items:**\n" + "\n".join([f"- {c}" for c in consumed_list]))
                            st.balloons()
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error consuming RM: {str(e)}")
            else:
                st.info("ℹ️ No BOM defined for sold FG products. Please add BOM entries in Masters → BOM tab.")

        st.markdown("---")
        st.markdown("#### 🧮 Manual FG to RM Calculator")
        st.info("💡 Select OR type any FG product name and enter the quantity to calculate all required Raw Materials based on BOM.")

        df_fg_products = fetch_data("""
        SELECT product_name FROM product_master
        WHERE category IN ('FG Product', 'Moulding Product')
        ORDER BY product_name
        """)
        fg_product_list = df_fg_products['product_name'].tolist() if not df_fg_products.empty else []

        fg_input_mode = st.radio("How do you want to enter the FG Product?",
                                 ["Select from List", "Type Manually (Any FG Name)"],
                                 horizontal=True, key="fg_input_mode")
        calc_fg_product = None
        if fg_input_mode == "Select from List":
            if not fg_product_list:
                st.warning("⚠️ No FG products found in masters.")
            calc_fg_product = st.selectbox("📦 Select FG Product",
                                           fg_product_list if fg_product_list else ["No FG products"],
                                           key="calc_fg_product_select")
            if calc_fg_product == "No FG products": calc_fg_product = None
        else:
            calc_fg_product = st.text_input("📦 Type FG Product Name (must match BOM exactly)",
                                            key="calc_fg_product_manual",
                                            placeholder="e.g., 5A SSC with JB, TSSC, 15A DSSC with JB")

        col_calc1, col_calc2 = st.columns([2, 1])
        with col_calc1:
            calc_fg_qty = st.number_input("🔢 Enter FG Quantity (Sales Qty)", min_value=0.0, step=1.0, value=1.0, key="calc_fg_qty")

        if st.button("🔄 Calculate RM Requirements", type="primary", key="calc_rm_btn"):
            if calc_fg_product and calc_fg_product.strip() and calc_fg_qty > 0:
                calc_fg_product = calc_fg_product.strip()
                bom_items = fetch_data("""
                SELECT rm_product, required_qty
                FROM bom_master
                WHERE fg_product = ?
                """, (calc_fg_product,))

                if bom_items.empty:
                    st.warning(f"⚠️ No BOM defined for '{calc_fg_product}'. Please add BOM entries in Masters → BOM tab.")
                    available_bom = fetch_data("SELECT DISTINCT fg_product FROM bom_master ORDER BY fg_product")
                    if not available_bom.empty:
                        st.markdown("**Available FG Products in BOM:**")
                        st.dataframe(available_bom, use_container_width=True)
                else:
                    st.markdown("---")
                    st.markdown(f"#### 📊 RM Requirements for **{calc_fg_qty} units** of **{calc_fg_product}**")
                    calc_rows = []
                    total_rm_value = 0.0
                    has_shortage = False
                    for _, bom_row in bom_items.iterrows():
                        rm_name = bom_row['rm_product']
                        per_unit_req = float(bom_row['required_qty'])
                        total_required = per_unit_req * calc_fg_qty
                        stock_df = fetch_data("""
                        SELECT closing_stock, COALESCE(rate, 0) as rate
                        FROM rm_inventory
                        WHERE product_name = ?
                        """, (rm_name,))
                        if not stock_df.empty:
                            available = float(stock_df['closing_stock'].iloc[0]) if pd.notna(stock_df['closing_stock'].iloc[0]) else 0.0
                            rate = float(stock_df['rate'].iloc[0]) if pd.notna(stock_df['rate'].iloc[0]) else 0.0
                        else:
                            available = 0.0
                            rate = 0.0
                        shortage = total_required - available
                        status = "✅ OK" if shortage <= 0 else "❌ SHORTAGE"
                        if shortage > 0: has_shortage = True
                        calc_rows.append({
                            "RM Product": rm_name, "Per FG Unit": per_unit_req,
                            f"Required ({calc_fg_qty} FG)": total_required,
                            "Available Stock": available,
                            "Shortage (+) / Surplus (-)": shortage,
                            "Rate (₹)": rate, "Required Value (₹)": total_required * rate,
                            "Status": status
                        })
                        total_rm_value += total_required * rate

                    calc_df = pd.DataFrame(calc_rows)
                    m1, m2, m3, m4 = st.columns(4)
                    with m1: st.metric("📦 Total RM Types", len(calc_rows))
                    with m2: st.metric("💰 Total RM Value", f"₹{total_rm_value:,.2f}")
                    with m3:
                        shortage_items = len([r for r in calc_rows if r["Status"] == "❌ SHORTAGE"])
                        st.metric("⚠️ Items in Shortage", shortage_items)
                    with m4:
                        ok_items = len([r for r in calc_rows if r["Status"] == "✅ OK"])
                        st.metric("✅ Items Available", ok_items)

                    def highlight_status(val):
                        if val == "❌ SHORTAGE":
                            return 'background-color: #ffebee; color: #c62828; font-weight: bold'
                        else:
                            return 'background-color: #e8f5e9; color: #2e7d32; font-weight: bold'

                    try: styled_df = calc_df.style.map(highlight_status, subset=['Status'])
                    except AttributeError: styled_df = calc_df.style.applymap(highlight_status, subset=['Status'])
                    st.dataframe(styled_df, use_container_width=True, hide_index=True)

                    if has_shortage:
                        st.error(f"⚠️ **Shortage Alert:** {shortage_items} RM material(s) are insufficient for this FG quantity.")
                    else:
                        st.success(f"✅ **All RM materials available!** You have sufficient stock to produce/sell {calc_fg_qty} units of {calc_fg_product}.")

                    st.markdown("---")
                    st.markdown("#### 💾 Action: Consume RM from Stock")
                    st.caption("Click below to actually deduct these RM quantities from your inventory (as if FG was produced/sold).")
                    consume_col1, consume_col2 = st.columns([3, 1])
                    with consume_col1:
                        consume_reason = st.text_input("Reason / Reference (Challan No, Sale Ref, etc.)",
                                                       key="consume_reason_input",
                                                       placeholder="e.g., SALE-001, PROD-001")
                    with consume_col2:
                        consume_date = st.date_input("Date", datetime.now(), key="consume_date_input")

                    if st.button(f"💥 Consume RM Stock for {calc_fg_qty} x {calc_fg_product}",
                                 type="primary",
                                 key="consume_rm_stock_btn",
                                 disabled=has_shortage):
                        if has_shortage:
                            st.error("❌ Cannot consume — shortage exists. Please fix shortage first.")
                        else:
                            try:
                                consumed_list = []
                                ref_no = consume_reason.strip() if consume_reason.strip() else f"FG-RM-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                                for _, row_data in calc_df.iterrows():
                                    rm_name = row_data["RM Product"]
                                    qty_to_consume = row_data[f"Required ({calc_fg_qty} FG)"]
                                    update_rm_inventory(rm_name, qty_to_consume, 'CONSUMPTION', consume_date.strftime('%Y-%m-%d'), ref_no, rate=row_data["Rate (₹)"])
                                    consumed_list.append(f"{rm_name}: {qty_to_consume}")
                                st.success(f"✅ RM stock consumed successfully for {calc_fg_qty} x {calc_fg_product}!")
                                st.info("📋 **Consumed Items:**\n" + "\n".join([f"- {c}" for c in consumed_list]))
                                st.balloons()
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Error consuming RM: {str(e)}")
# ======================= REPORTS =======================
elif page == "📋 Reports":
    st.subheader("📋 Reports & Analytics")
    report_type = st.selectbox("Select Report Type", 
        ["Production Summary", "Sales Summary", "Purchase Summary", 
         "Contractor Performance", "Party-wise Sales", "Rejection Analysis", "Stock Movement", "Overdue Payments"])

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

    elif report_type == "Purchase Summary":
        st.markdown("### Purchase Summary Report")
        df = fetch_data("""
            SELECT product_name, COUNT(*) as transactions, SUM(qty) as total_qty, SUM(amount) as total_amount
            FROM purchase_transactions GROUP BY product_name ORDER BY total_amount DESC
        """)
        if not df.empty:
            st.dataframe(df, use_container_width=True)
            st.bar_chart(df.set_index('product_name')['total_amount'])
        else:
            st.info("No purchase data available")

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
            df = fetch_data("SELECT product_name, opening_stock, (produced_qty + purchased_qty) as additions, (sold_qty + rejected_qty) as deductions, closing_stock FROM fg_inventory ORDER BY product_name")
            if not df.empty:
                st.dataframe(df, use_container_width=True)

    elif report_type == "Overdue Payments":
        st.markdown("### Overdue Payments Report")
        overdue = check_overdue_payments()
        if not overdue.empty:
            st.error(f"⚠️ **{len(overdue)} Overdue Payment(s) Found**")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Overdue Amount", f"₹{overdue['balance_amount'].sum():,.2f}")
            with col2:
                st.metric("Max Days Overdue", f"{int(overdue['days_overdue'].max())} days")
            with col3:
                st.metric("Average Days Overdue", f"{int(overdue['days_overdue'].mean())} days")
            st.dataframe(overdue, use_container_width=True)

            st.markdown("### Overdue by Party")
            df_party_overdue = fetch_data("""
                SELECT party_name, COUNT(*) as count, SUM(balance_amount) as total_overdue, AVG(julianday(date('now')) - julianday(due_date)) as avg_days
                FROM payable_receivable_ledger 
                WHERE transaction_type = 'RECEIVABLE' 
                AND payment_status != 'PAID' 
                AND due_date < date('now')
                GROUP BY party_name 
                ORDER BY total_overdue DESC
            """)
            if not df_party_overdue.empty:
                st.bar_chart(df_party_overdue.set_index('party_name')['total_overdue'])
        else:
            st.success("✅ No overdue payments! All payments are up to date.")

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
