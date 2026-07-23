import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from io import BytesIO
import os
import time

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
        party_name TEXT,
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

    cursor.execute('''CREATE TABLE IF NOT EXISTS fg_stock_movement (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_date TEXT NOT NULL,
        challan_no TEXT,
        party_name TEXT,
        product_name TEXT NOT NULL,
        transaction_type TEXT NOT NULL,
        qty REAL NOT NULL,
        opening_balance REAL DEFAULT 0,
        closing_balance REAL DEFAULT 0,
        reference_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

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

        if df_parties.empty and 'party_name' not in df_parties.columns:
            df_parties = pd.DataFrame(columns=['party_name'])

        if df_products.empty and 'product_name' not in df_products.columns:
            df_products = pd.DataFrame(columns=['product_name', 'rate', 'unit', 'category'])

        return df_parties, df_products
    except Exception as e:
        st.error(f"Error in get_dynamic_lists: {e}")
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

        cursor.execute("PRAGMA table_info(rm_stock_movement)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'party_name' not in columns:
            cursor.execute("ALTER TABLE rm_stock_movement ADD COLUMN party_name TEXT")

        cursor.execute("PRAGMA table_info(fg_stock_movement)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'party_name' not in columns:
            cursor.execute("ALTER TABLE fg_stock_movement ADD COLUMN party_name TEXT")

    except Exception as e:
        print(f"Migration warning: {e}")

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

def execute_query(query, params=()):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        conn.commit()
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

def update_rm_inventory(product, qty, transaction_type='PURCHASE', transaction_date=None, challan_no=None, reference_id=None, rate=0, party_name=None):
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

def update_fg_inventory(product, qty, transaction_type='PRODUCE', transaction_date=None, challan_no=None, reference_id=None, party_name=None, rate=0):
    """
    Updates FG Inventory and Stock Movement records.
    Recalculates running balances for ALL movements of this product to ensure consistency.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Ensure product exists in inventory table
        cursor.execute("""
            INSERT OR IGNORE INTO fg_inventory
            (product_name, opening_stock, produced_qty, sold_qty, rejected_qty, purchased_qty, closing_stock)
            VALUES (?, 0, 0, 0, 0, 0, 0)
        """, (product,))
        
        # 1. Get Master Opening Stock
        cursor.execute("SELECT opening_stock FROM fg_inventory WHERE product_name = ?", (product,))
        row = cursor.fetchone()
        base_opening = row[0] if row else 0
        
        # 2. Fetch ALL movements for this product ordered by date and ID
        cursor.execute(
            "SELECT id, transaction_date, transaction_type, qty FROM fg_stock_movement WHERE product_name = ? ORDER BY transaction_date, id", 
            (product,)
        )
        movements = cursor.fetchall()
        
        # If no movements, just update master closing stock to opening
        if not movements:
            cursor.execute("UPDATE fg_inventory SET closing_stock = ? WHERE product_name = ?", 
                           (base_opening, product))
            conn.commit()
            return base_opening
        
        # 3. Recalculate running balances
        current_balance = base_opening
        movement_updates = []
        
        for mov in movements:
            mid, m_date, m_type, m_qty = mov
            
            if m_type == 'PRODUCE':
                current_balance += m_qty
            elif m_type == 'PURCHASE':
                current_balance += m_qty
            elif m_type == 'SALE':
                current_balance -= m_qty
            elif m_type == 'REJECT':
                current_balance -= m_qty
            
            movement_updates.append((current_balance, mid))
        
        # 4. Batch update all closing balances
        for bal, mid in movement_updates:
            cursor.execute("UPDATE fg_stock_movement SET closing_balance = ? WHERE id = ?", (bal, mid))
        
        # 5. Update Master Inventory totals and closing stock
        # Calculate totals from movements
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN transaction_type = 'PRODUCE' THEN qty ELSE 0 END), 0) as produced,
                COALESCE(SUM(CASE WHEN transaction_type = 'PURCHASE' THEN qty ELSE 0 END), 0) as purchased,
                COALESCE(SUM(CASE WHEN transaction_type = 'SALE' THEN qty ELSE 0 END), 0) as sold,
                COALESCE(SUM(CASE WHEN transaction_type = 'REJECT' THEN qty ELSE 0 END), 0) as rejected
            FROM fg_stock_movement
            WHERE product_name = ?
        """, (product,))
        totals = cursor.fetchone()
        produced_qty, purchased_qty, sold_qty, rejected_qty = totals
        
        final_closing = base_opening + produced_qty + purchased_qty - sold_qty - rejected_qty
        
        cursor.execute("""
            UPDATE fg_inventory 
            SET produced_qty = ?, purchased_qty = ?, sold_qty = ?, rejected_qty = ?, closing_stock = ?
            WHERE product_name = ?
        """, (produced_qty, purchased_qty, sold_qty, rejected_qty, final_closing, product))
        
        conn.commit()
        return final_closing

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def consume_rm_for_fg_sale(fg_product, fg_qty, sale_date, challan_no, sale_id):
    """
    Automatically consume RM materials based on BOM when FG is sold.
    """
    bom_items = fetch_data("""
        SELECT rm_product, required_qty
        FROM bom_master
        WHERE fg_product = ?
    """, (fg_product,))
    
    if bom_items.empty:
        return []
        
    consumed_items = []
    for _, bom_row in bom_items.iterrows():
        rm_product = bom_row['rm_product']
        rm_qty_needed = bom_row['required_qty'] * fg_qty
        
        rm_check = fetch_data("SELECT closing_stock FROM rm_inventory WHERE product_name = ?", (rm_product,))
        if rm_check.empty:
            st.warning(f"⚠️ RM Product '{rm_product}' not found in inventory!")
            continue
            
        available_stock = rm_check['closing_stock'].iloc[0]
        
        if available_stock < rm_qty_needed:
            st.warning(f"⚠️ Insufficient RM stock for {rm_product}. Available: {available_stock}, Required: {rm_qty_needed}. Skipping RM deduction.")
            continue
        
        try:
            # Get party name from sales transaction
            party_name = fetch_data("SELECT party_name FROM sales_transactions WHERE id = ?", (sale_id,))
            party = party_name['party_name'].iloc[0] if not party_name.empty else None
            
            update_rm_inventory(rm_product, rm_qty_needed, 'CONSUMPTION', sale_date, challan_no, sale_id, party_name=party)
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

                update_rm_inventory(product, float(qty), 'PURCHASE', date, challan_no, purchase_id, party_name=contractor)
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
                    prod_id = execute_query('''INSERT INTO production_register 
                        (date, party_name, fg_product, produced_qty)
                        VALUES (?, ?, ?, ?)''',
                        (datetime.now().strftime('%Y-%m-%d'), contractor, product, float(qty)))
                    execute_query('''INSERT INTO fg_stock_movement
                        (transaction_date, challan_no, party_name, product_name, transaction_type, qty, opening_balance, closing_balance, reference_id)
                        VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?)''',
                        (datetime.now().strftime('%Y-%m-%d'), 'FG-IMPORT', contractor, product, 'PRODUCE', float(qty), prod_id))
                    update_fg_inventory(product, 0, 'PRODUCE')
                    records_imported += 1

        sales_cols = ['W Sales', 'B Sales', 'Total Sales']
        for col in sales_cols:
            if col in df.columns:
                qty = row.get(col)
                if pd.notna(qty) and isinstance(qty, (int, float)) and qty > 0:
                    party = 'Wholesale' if 'W' in col else ('Retail' if 'B' in col else 'General')
                    execute_query("INSERT OR IGNORE INTO party_master (party_name, category) VALUES (?, 'Sales Party')", (party,))
                    sale_id = execute_query('''INSERT INTO sales_transactions 
                        (challan_no, date, party_name, product_name, qty)
                        VALUES (?, ?, ?, ?, ?)''',
                        ('FG-IMPORT', datetime.now().strftime('%Y-%m-%d'), party, product, float(qty)))
                    execute_query('''INSERT INTO fg_stock_movement
                        (transaction_date, challan_no, party_name, product_name, transaction_type, qty, opening_balance, closing_balance, reference_id)
                        VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?)''',
                        (datetime.now().strftime('%Y-%m-%d'), 'FG-IMPORT', party, product, 'SALE', float(qty), sale_id))
                    update_fg_inventory(product, 0, 'SALE')
                    records_imported += 1

        if 'Difference (Actual Sold- Production)' in df.columns:
            diff = row.get('Difference (Actual Sold- Production)')
            if pd.notna(diff) and isinstance(diff, (int, float)) and diff < 0:
                rej_id = execute_query('''INSERT INTO market_rejection_register 
                    (date, product_name, qty_rejected, reason)
                    VALUES (?, ?, ?, ?)''',
                    (datetime.now().strftime('%Y-%m-%d'), product, abs(float(diff)), 'Import - Stock Difference'))
                execute_query('''INSERT INTO fg_stock_movement
                    (transaction_date, challan_no, party_name, product_name, transaction_type, qty, opening_balance, closing_balance, reference_id)
                    VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?)''',
                    (datetime.now().strftime('%Y-%m-%d'), 'FG-IMPORT', None, product, 'REJECT', abs(float(diff)), rej_id))
                update_fg_inventory(product, 0, 'REJECT')
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

        df_rm_mov = fetch_data("SELECT * FROM rm_stock_movement ORDER BY transaction_date, id")
        df_rm_mov.to_excel(writer, sheet_name='RM Movement', index=False)

        df_fg_mov = fetch_data("SELECT * FROM fg_stock_movement ORDER BY transaction_date, id")
        df_fg_mov.to_excel(writer, sheet_name='FG Movement', index=False)

    output.seek(0)
    return output

def check_rm_availability_for_fg(fg_product, fg_qty):
    """
    Check if all required RM materials are available for a given FG product and quantity.
    Returns (is_available, list_of_shortages)
    """
    bom_items = fetch_data("""
        SELECT rm_product, required_qty
        FROM bom_master
        WHERE fg_product = ?
    """, (fg_product,))
    
    if bom_items.empty:
        return True, []  # No BOM defined, allow sale
    
    shortages = []
    is_available = True
    
    for _, bom_row in bom_items.iterrows():
        rm_product = bom_row['rm_product']
        required_qty = bom_row['required_qty'] * fg_qty
        
        # Get current stock
        stock_df = fetch_data("SELECT closing_stock FROM rm_inventory WHERE product_name = ?", (rm_product,))
        available_stock = float(stock_df['closing_stock'].iloc[0]) if not stock_df.empty and pd.notna(stock_df['closing_stock'].iloc[0]) else 0.0
        
        if available_stock < required_qty:
            is_available = False
            shortages.append({
                'rm_product': rm_product,
                'required': required_qty,
                'available': available_stock,
                'shortage': required_qty - available_stock
            })
    
    return is_available, shortages

# ======================= PROFESSIONAL UI CONFIGURATION =======================
st.set_page_config(
    page_title="Jinay ERP System",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ======================= PROFESSIONAL CSS =======================
st.markdown("""
<style>
    /* ===== RESET & BASE ===== */
    .stApp {
        background: #0a0e14 !important;
    }
    .stApp > header {
        background: transparent !important;
    }
    
    /* ===== SCROLLBAR ===== */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: #121820; }
    ::-webkit-scrollbar-thumb { background: #2a3a55; border-radius: 10px; }
    ::-webkit-scrollbar-thumb:hover { background: #3a4f73; }
    
    /* ===== SIDEBAR ===== */
    .css-1d391kg, .css-1r6slb0, .css-1a32fsj, .css-17eq0hr {
        background: #0d121c !important;
        border-right: 1px solid #1f2838 !important;
    }
    .sidebar-content {
        padding: 1.5rem 0.8rem !important;
    }
    .css-1d391kg .stMarkdown, .css-1d391kg .stText, .css-1d391kg label {
        color: #e8edf5 !important;
    }
    
    /* ===== SIDEBAR RADIO ===== */
    .stRadio > div[role="radiogroup"] {
        background: #111a26 !important;
        padding: 8px 6px !important;
        border-radius: 16px !important;
        border: 1px solid #1f2a3a !important;
        gap: 2px !important;
    }
    .stRadio label {
        padding: 10px 14px !important;
        border-radius: 12px !important;
        color: #8a9bbf !important;
        font-weight: 500 !important;
        font-size: 0.9rem !important;
        transition: all 0.2s !important;
    }
    .stRadio label:hover {
        background: #1a2538 !important;
        color: #d0defa !important;
    }
    .stRadio label[data-selected="true"] {
        background: linear-gradient(135deg, #2a3f6a, #1f3152) !important;
        color: #ffffff !important;
        box-shadow: 0 4px 14px rgba(30, 60, 120, 0.3) !important;
    }
    .stRadio label[data-selected="true"]:hover {
        background: linear-gradient(135deg, #314a7a, #253a60) !important;
    }
    
    /* ===== METRIC CARDS ===== */
    div[data-testid="stMetric"] {
        background: linear-gradient(145deg, #131c2a, #0e1520) !important;
        padding: 18px 20px !important;
        border-radius: 18px !important;
        border: 1px solid #212c3e !important;
        box-shadow: 0 6px 18px rgba(0,0,0,0.4) !important;
        transition: all 0.25s ease !important;
    }
    div[data-testid="stMetric"]:hover {
        border-color: #3a5078 !important;
        box-shadow: 0 8px 28px rgba(30, 60, 130, 0.2) !important;
        transform: translateY(-2px) !important;
    }
    div[data-testid="stMetric"] label {
        color: #8fa2c7 !important;
        font-weight: 500 !important;
        letter-spacing: 0.3px !important;
        text-transform: uppercase !important;
        font-size: 0.7rem !important;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        color: #f0f4ff !important;
        font-weight: 700 !important;
        font-size: 1.8rem !important;
    }
    
    /* ===== CONTAINERS / CARDS ===== */
    .stContainer, .stForm, div[data-testid="stForm"] {
        background: linear-gradient(145deg, #121b28, #0d141f) !important;
        padding: 24px !important;
        border-radius: 24px !important;
        border: 1px solid #1e2a3c !important;
        box-shadow: 0 8px 24px rgba(0,0,0,0.45) !important;
        transition: border-color 0.2s !important;
    }
    .stContainer:hover, .stForm:hover {
        border-color: #2d3f5a !important;
    }
    
    /* ===== INPUT FIELDS ===== */
    .stTextInput > div, .stSelectbox > div, .stNumberInput > div,
    .stDateInput > div, .stTextArea > div {
        background: #0e1622 !important;
        border-radius: 14px !important;
        border: 1px solid #1f2c40 !important;
        transition: all 0.2s !important;
    }
    .stTextInput > div:hover, .stSelectbox > div:hover,
    .stNumberInput > div:hover, .stDateInput > div:hover,
    .stTextArea > div:hover {
        border-color: #3a5280 !important;
        box-shadow: 0 0 0 3px rgba(50, 80, 150, 0.15) !important;
    }
    .stTextInput > div input, .stSelectbox > div input,
    .stNumberInput > div input, .stDateInput > div input,
    .stTextArea > div textarea {
        color: #e8eff9 !important;
        background: transparent !important;
        font-size: 0.9rem !important;
    }
    .stSelectbox > div div {
        color: #e8eff9 !important;
        background: #0e1622 !important;
    }
    .stSelectbox > div div[role="listbox"] {
        background: #141e2e !important;
        border: 1px solid #25324a !important;
    }
    
    /* ===== LABELS ===== */
    .stMarkdown label, .stSelectbox label, .stNumberInput label,
    .stTextInput label, .stDateInput label, .stTextArea label {
        color: #b0c4e8 !important;
        font-weight: 500 !important;
        font-size: 0.85rem !important;
        letter-spacing: 0.2px !important;
    }
    
    /* ===== BUTTONS ===== */
    .stButton > button {
        border-radius: 14px !important;
        font-weight: 600 !important;
        padding: 10px 22px !important;
        background: linear-gradient(135deg, #2e4570, #1f3150) !important;
        color: #ffffff !important;
        border: 1px solid #3a5580 !important;
        box-shadow: 0 4px 16px rgba(20, 40, 90, 0.3) !important;
        transition: all 0.25s ease !important;
        letter-spacing: 0.2px !important;
    }
    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 28px rgba(30, 60, 140, 0.4) !important;
        border-color: #4e6f9e !important;
        background: linear-gradient(135deg, #365282, #253b60) !important;
    }
    .stButton > button:active {
        transform: translateY(0px) !important;
    }
    .stButton > button:focus {
        box-shadow: 0 0 0 3px rgba(60, 100, 200, 0.3) !important;
    }
    
    /* ===== DATA FRAMES ===== */
    .stDataFrame {
        border-radius: 18px !important;
        overflow: hidden !important;
        border: 1px solid #1f2b3d !important;
    }
    .stDataFrame table {
        background: #0d1520 !important;
        border-collapse: collapse !important;
    }
    .stDataFrame thead tr th {
        background: linear-gradient(135deg, #172234, #0e1826) !important;
        color: #c6d6f5 !important;
        font-weight: 600 !important;
        padding: 14px 16px !important;
        border-bottom: 2px solid #283a54 !important;
        font-size: 0.8rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.4px !important;
    }
    .stDataFrame tbody tr {
        background: #0d1520 !important;
        color: #d6e2f5 !important;
        border-bottom: 1px solid #182233 !important;
    }
    .stDataFrame tbody tr:nth-child(even) {
        background: #111b2a !important;
    }
    .stDataFrame tbody tr:hover {
        background: #1a263a !important;
        transition: background 0.15s !important;
    }
    .stDataFrame tbody td {
        color: #d6e2f5 !important;
        padding: 12px 16px !important;
        font-size: 0.85rem !important;
    }
    
    /* ===== ALERTS / TOASTS ===== */
    .stAlert {
        border-radius: 16px !important;
        border-left: 5px solid !important;
        background: #121c2a !important;
        color: #e8f0fa !important;
        padding: 16px 20px !important;
        box-shadow: 0 4px 14px rgba(0,0,0,0.3) !important;
    }
    .stSuccess {
        border-left-color: #4ec98a !important;
        background: linear-gradient(135deg, #12241e, #0a1a14) !important;
        border: 1px solid #2a6a4a !important;
    }
    .stError {
        border-left-color: #e6606a !important;
        background: linear-gradient(135deg, #2a181e, #1a0e12) !important;
        border: 1px solid #6a3a42 !important;
    }
    .stWarning {
        border-left-color: #e8b45c !important;
        background: linear-gradient(135deg, #2a2618, #1a160e) !important;
        border: 1px solid #6a5a2a !important;
    }
    .stInfo {
        border-left-color: #5a8ad9 !important;
        background: linear-gradient(135deg, #18222e, #0e1620) !important;
        border: 1px solid #2a4a6a !important;
    }
    
    /* ===== TABS ===== */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px !important;
        background: #0d1622 !important;
        padding: 8px 10px !important;
        border-radius: 18px !important;
        border: 1px solid #1d2a3a !important;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 12px !important;
        padding: 8px 18px !important;
        color: #8a9fc5 !important;
        font-weight: 500 !important;
        font-size: 0.85rem !important;
        transition: all 0.2s !important;
    }
    .stTabs [data-baseweb="tab"]:hover {
        background: #1a263a !important;
        color: #d0defa !important;
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        background: linear-gradient(135deg, #2a3f6a, #1f3152) !important;
        color: #ffffff !important;
        box-shadow: 0 4px 16px rgba(30, 60, 120, 0.25) !important;
    }
    
    /* ===== EXPANDERS ===== */
    div[data-testid="stExpander"] {
        background: #0d1622 !important;
        border-radius: 18px !important;
        border: 1px solid #1d2a3a !important;
    }
    div[data-testid="stExpander"] summary {
        background: #111c2a !important;
        border-radius: 18px !important;
        padding: 14px 20px !important;
        font-weight: 600 !important;
        color: #d0defa !important;
    }
    div[data-testid="stExpander"] summary:hover {
        background: #162234 !important;
    }
    
    /* ===== HEADINGS ===== */
    h1, h2, h3, h4, h5, h6 {
        color: #e8eff9 !important;
        font-weight: 600 !important;
        letter-spacing: -0.2px !important;
    }
    h1 { font-size: 2.2rem !important; }
    h2 { font-size: 1.6rem !important; border-bottom: 2px solid #1f2a3a !important; padding-bottom: 10px !important; }
    h3 { font-size: 1.25rem !important; }
    .stMarkdown p, .stText {
        color: #c6d4ee !important;
    }
    
    /* ===== DIVIDERS ===== */
    hr {
        border-color: #1f2a3a !important;
        margin: 28px 0 !important;
    }
    
    /* ===== FILE UPLOADER ===== */
    .stFileUploader > div {
        background: #0e1622 !important;
        border: 2px dashed #1f2c40 !important;
        border-radius: 18px !important;
        color: #b0c4e8 !important;
        padding: 24px !important;
    }
    .stFileUploader > div:hover {
        border-color: #3a5280 !important;
    }
    
    /* ===== MULTI SELECT ===== */
    .stMultiSelect > div {
        background: #0e1622 !important;
        border: 1px solid #1f2c40 !important;
        border-radius: 14px !important;
    }
    .stMultiSelect > div:hover {
        border-color: #3a5280 !important;
    }
    .stMultiSelect > div div {
        color: #e8eff9 !important;
    }
    
    /* ===== CHECKBOX ===== */
    .stCheckbox label {
        color: #c6d4ee !important;
    }
    .stCheckbox label span {
        color: #c6d4ee !important;
    }
    
    /* ===== SIDEBAR BOTTOM ===== */
    .sidebar-footer {
        margin-top: 28px;
        padding: 16px 12px 0;
        border-top: 1px solid #1a2436;
        color: #5a6d8a;
        font-size: 0.75rem;
        display: flex;
        justify-content: space-between;
    }
    
    /* ===== CUSTOM BADGE ===== */
    .badge {
        display: inline-block;
        padding: 2px 14px;
        border-radius: 40px;
        font-size: 0.7rem;
        font-weight: 600;
        background: #1f2a3a;
        color: #b0c4e8;
    }
    .badge-success { background: #1a3a2a; color: #6ad99a; }
    .badge-danger { background: #3a1a22; color: #e66a7a; }
    .badge-warning { background: #3a2a1a; color: #e8b45c; }
    .badge-info { background: #1a2a3a; color: #6a9ad9; }
    
    /* ===== METRIC ROW HELPER ===== */
    .metric-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        gap: 16px;
        margin-bottom: 24px;
    }
    
    /* ===== OVERDUE ALERT ===== */
    .overdue-item {
        background: #1a1018;
        border-left: 4px solid #e6606a;
        padding: 12px 18px;
        border-radius: 12px;
        margin-bottom: 8px;
        border: 1px solid #3a2a2e;
    }
    .overdue-item strong { color: #f0b0ba; }
    
    /* ===== RESPONSIVE ===== */
    @media (max-width: 768px) {
        .stApp { padding: 0.5rem !important; }
        .stContainer, .stForm { padding: 16px !important; }
        .metric-grid { grid-template-columns: 1fr 1fr; }
    }
    
    /* ===== STREAMLIT HACKS ===== */
    .css-1aumxhk, .css-18e3th9 { background: transparent !important; }
    div[data-testid="stImage"] { background: transparent !important; }
</style>
""", unsafe_allow_html=True)

# ======================= INITIALIZE =======================
init_db()

if 'edit_mode' not in st.session_state:
    st.session_state.edit_mode = False
if 'edit_id' not in st.session_state:
    st.session_state.edit_id = None
if 'edit_table' not in st.session_state:
    st.session_state.edit_table = None

# ======================= SIDEBAR =======================
with st.sidebar:
    st.markdown("""
    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
        <div style="background: linear-gradient(135deg, #2a3f6a, #1f3152); padding: 10px; border-radius: 16px;">
            <span style="font-size: 1.8rem;">🏭</span>
        </div>
        <div>
            <div style="font-weight: 700; font-size: 1.4rem; color: #e8eff9; letter-spacing: -0.5px;">Jinay</div>
            <div style="font-weight: 500; font-size: 0.8rem; color: #7a8fb0; letter-spacing: 1px; text-transform: uppercase;">ERP System</div>
        </div>
    </div>
    <hr style="margin: 12px 0 18px 0;">
    """, unsafe_allow_html=True)
    
    page = st.radio(
        "NAVIGATION",
        ["📊 Dashboard", "📦 Masters", "🛒 Purchase", "🏭 Production", 
         "💰 Sales", "📒 Ledger", "⚠️ Rejections", "📈 Inventory", "📋 Reports", "📤 Import/Export"],
        index=0,
        key="main_nav"
    )
    
    st.markdown("""
    <div class="sidebar-footer">
        <span>v2.5.0</span>
        <span>⚡ Live</span>
    </div>
    """, unsafe_allow_html=True)

# ======================= DASHBOARD =======================
if page == "📊 Dashboard":
    st.markdown("""
    <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 24px;">
        <div style="background: linear-gradient(135deg, #2a3f6a, #1f3152); padding: 10px 16px; border-radius: 16px;">
            <span style="font-size: 1.8rem;">📊</span>
        </div>
        <div>
            <h1 style="font-size: 2rem; margin: 0;">Dashboard</h1>
            <p style="color: #8a9fc5; margin: 0;">Real-time overview of your ERP system</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Overdue Alerts
    overdue_payments = check_overdue_payments()
    if not overdue_payments.empty:
        for _, payment in overdue_payments.head(3).iterrows():
            st.markdown(f"""
            <div class="overdue-item">
                <strong>{payment['party_name']}</strong> · Challan: {payment['challan_no']} · 
                ₹{payment['balance_amount']:,.2f} overdue · 
                <span style="color: #e6606a; font-weight: 600;">{int(payment['days_overdue'])} days</span>
            </div>
            """, unsafe_allow_html=True)
        if len(overdue_payments) > 3:
            st.warning(f"… and {len(overdue_payments) - 3} more overdue receivables")

    overdue_payables = check_overdue_payables()
    if not overdue_payables.empty:
        for _, payment in overdue_payables.head(3).iterrows():
            st.markdown(f"""
            <div class="overdue-item" style="border-left-color: #e8b45c;">
                <strong>{payment['party_name']}</strong> · Challan: {payment['challan_no']} · 
                ₹{payment['balance_amount']:,.2f} overdue · 
                <span style="color: #e8b45c; font-weight: 600;">{int(payment['days_overdue'])} days</span>
            </div>
            """, unsafe_allow_html=True)

    # Metrics
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

    # Charts
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📈 Production vs Sales")
        df_chart = fetch_data("""
            SELECT DATE(date) as date, SUM(produced_qty) as production 
            FROM production_register GROUP BY DATE(date)
        """)
        if not df_chart.empty:
            st.line_chart(df_chart.set_index('date')['production'])
        else:
            st.info("No production data available")

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
            st.info("No contractor data available")

    # Recent Activity
    st.subheader("📋 Recent Activity")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**🛒 Recent Purchases**")
        df_recent_pur = fetch_data("SELECT challan_no, date, product_name, qty, amount FROM purchase_transactions ORDER BY date DESC LIMIT 5")
        if not df_recent_pur.empty:
            st.dataframe(df_recent_pur, use_container_width=True)
    with col2:
        st.markdown("**🏭 Recent Production**")
        df_recent_prod = fetch_data("SELECT party_name, fg_product, produced_qty, date FROM production_register ORDER BY date DESC LIMIT 5")
        if not df_recent_prod.empty:
            st.dataframe(df_recent_prod, use_container_width=True)
    with col3:
        st.markdown("**💰 Recent Sales**")
        df_recent_sal = fetch_data("SELECT party_name, product_name, qty, amount, date FROM sales_transactions ORDER BY date DESC LIMIT 5")
        if not df_recent_sal.empty:
            st.dataframe(df_recent_sal, use_container_width=True)

# ======================= MASTERS =======================
elif page == "📦 Masters":
    st.markdown("""
    <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 24px;">
        <div style="background: linear-gradient(135deg, #2a3f6a, #1f3152); padding: 10px 16px; border-radius: 16px;">
            <span style="font-size: 1.8rem;">📦</span>
        </div>
        <div>
            <h1 style="font-size: 2rem; margin: 0;">Master Management</h1>
            <p style="color: #8a9fc5; margin: 0;">Manage parties, products, and BOM</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    tab1, tab2, tab3 = st.tabs(["👥 Parties", "📦 Products", "🔧 BOM"])

    with tab1:
        st.markdown("### Add New Party")
        with st.form("add_party_form"):
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
            
            if st.form_submit_button("➕ Add Party", type="primary"):
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

    with tab2:
        st.markdown("### Add Product")
        with st.form("add_product_form"):
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
            
            if st.form_submit_button("➕ Add Product", type="primary"):
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

    with tab3:
        st.markdown("### 🔧 BOM Management")
        
        # Auto-populate BOM data
        BOM_DATA = {
            "5A SSC with JB": {"5A STC": 1, "5A DTC": 1, "5A W/S": 2, "5A C/C": 1, "5A Action": 1, "5A Earting Pin": 1, "5A Live Pin": 1, "5A Threading Patti": 2, "5/15A Bulb": 1},
            "5A 8x1 with JB": {"5A STC": 2, "5A DTC": 2, "5A W/S": 4, "5A C/C": 2, "5A Action": 2, "5A Earting Pin": 2, "5A Live Pin": 2, "5A Threading Patti": 4, "5/15A Bulb": 2},
            "5A 10x1 with JB": {"5A STC": 2, "5A DTC": 2, "5A W/S": 4, "5A C/C": 2, "5A Action": 2, "5A Earting Pin": 2, "5A Live Pin": 2, "5A Threading Patti": 2, "5/15A Bulb": 2, "5A 2 Pin": 2},
            "15A SSC with JB": {"15A STC": 1, "15A DTC": 1, "15A W/S": 2, "15A C/C": 1, "15A Earting Pin": 1, "15A Live Pin": 2, "15A MS Action": 1, "15A Threading Patti": 1},
            "15A SSC Consil": {"15A STC": 1, "15A DTC": 1, "15A W/S": 2, "15A C/C": 1, "15A Earting Pin": 1, "15A Live Pin": 2, "15A MS Action": 1, "15A Threading Patti": 1},
            "15A SSC with Jb IND": {"15A STC": 1, "15A DTC": 1, "15A W/S": 2, "15A C/C": 1, "15A Earting Pin": 1, "15A Live Pin": 2, "15A MS Action": 1, "15A Threading Patti": 1, "5/15A Bulb": 1},
            "15A SSC IND Consil": {"15A STC": 1, "15A DTC": 1, "15A W/S": 2, "15A C/C": 1, "15A Earting Pin": 1, "15A Live Pin": 2, "15A MS Action": 1, "15A Threading Patti": 1, "5/15A Bulb": 1},
            "15A SSC MCB": {"15A Earting Pin": 1, "15A Live Pin": 2},
            "15A DSSC with JB": {"15A STC": 2, "15A DTC": 2, "15A W/S": 4, "15A C/C": 2, "15A Earting Pin": 2, "15A Live Pin": 4, "15A MS Action": 2, "15A Threading Patti": 2, "5/15A Bulb": 2},
            "15A DSSC With JB (Brass)": {"15A STC": 2, "15A DTC": 2, "15A W/S": 4, "15A C/C": 2, "15A Earting Pin": 2, "15A Live Pin": 4, "15A Action 21+5 Brass": 2, "15A Threading Patti": 2, "5/15A Bulb": 2},
            "15A DSSC Spike 3mt": {"15A STC": 2, "15A DTC": 2, "15A W/S": 4, "15A C/C": 2, "15A Earting Pin": 2, "15A Live Pin": 4, "15A MS Action": 2, "15A Threading Patti": 2, "5/15A Bulb": 2, "DSSC Spike 3 mt": 1},
            "15A DSSC Spike 5 mt": {"15A STC": 2, "15A DTC": 2, "15A W/S": 4, "15A C/C": 2, "15A Earting Pin": 2, "15A Live Pin": 4, "15A MS Action": 2, "15A Threading Patti": 2, "5/15A Bulb": 2, "DSSC Spike 5 mt": 1},
            "15A DSSC 1Mt Connector": {"15A STC": 2, "15A DTC": 2, "15A W/S": 4, "15A C/C": 2, "15A Earting Pin": 2, "15A Live Pin": 4, "15A MS Action": 2, "15A Threading Patti": 2, "5/15A Bulb": 2, "DSSC Spike 1 mt": 1},
            "TSSC": {"15A STC": 3, "15A DTC": 3, "15A W/S": 6, "15A C/C": 3, "15A Earting Pin": 3, "15A Live Pin": 6, "15A MS Action": 3, "15A Threading Patti": 3, "5/15A Bulb": 3},
            "5X1 with JB": {"15A STC": 1, "15A DTC": 1, "15A W/S": 2, "15A C/C": 1, "15A Earting Pin": 1, "15A Live Pin": 2, "15A MS Action": 1, "15A Threading Patti": 1, "5A DTC": 2, "5A W/S": 2, "5x1 Bulb": 1, "Kitkat Part Set": 1},
            "5x1 Consil": {"15A STC": 1, "15A DTC": 1, "15A W/S": 2, "15A C/C": 1, "15A Earting Pin": 1, "15A Live Pin": 2, "15A MS Action": 1, "15A Threading Patti": 1, "5A DTC": 2, "5A W/S": 2, "5x1 Bulb": 1, "Kitkat Part Set": 1}
        }
        
        if 'bom_initialized' not in st.session_state:
            existing_bom = fetch_data("SELECT COUNT(*) as count FROM bom_master")
            if existing_bom.empty or existing_bom['count'].iloc[0] == 0:
                records = 0
                for fg_product, rm_dict in BOM_DATA.items():
                    for rm_product, qty in rm_dict.items():
                        try:
                            execute_query("INSERT OR REPLACE INTO bom_master (fg_product, rm_product, required_qty) VALUES (?, ?, ?)", 
                                         (fg_product, rm_product, float(qty)))
                            records += 1
                        except Exception as e:
                            st.warning(f"Could not insert BOM for {fg_product} -> {rm_product}: {e}")
                if records > 0:
                    st.success(f"✅ Auto-populated {records} BOM entries from template data!")
                st.session_state.bom_initialized = True

        st.markdown("#### Add BOM Entry")
        with st.form("add_bom_form"):
            col1, col2, col3 = st.columns(3)
            with col1:
                df_fg = fetch_data("SELECT product_name FROM product_master WHERE category IN ('FG Product', 'Moulding Product') ORDER BY product_name")
                fg_list = df_fg['product_name'].tolist() if not df_fg.empty else []
                bom_fg = st.selectbox("FG Product", fg_list if fg_list else ["No FG products"], key="bom_fg")
            with col2:
                df_rm = fetch_data("SELECT product_name FROM product_master WHERE category = 'RM Product' ORDER BY product_name")
                rm_list = df_rm['product_name'].tolist() if not df_rm.empty else []
                bom_rm = st.selectbox("RM Material", rm_list if rm_list else ["No RM products"], key="bom_rm")
            with col3:
                bom_qty = st.number_input("Required Qty", min_value=0.001, step=1.0, value=1.0, key="bom_qty")
            
            if st.form_submit_button("➕ Add BOM", type="primary"):
                if bom_fg != "No FG products" and bom_rm != "No RM products":
                    try:
                        execute_query("INSERT OR REPLACE INTO bom_master (fg_product, rm_product, required_qty) VALUES (?, ?, ?)", 
                                     (bom_fg, bom_rm, bom_qty))
                        st.success(f"✅ BOM added: {bom_fg} → {bom_rm} (Qty: {bom_qty})")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")

        st.markdown("#### BOM List")
        df_bom = fetch_data("""
            SELECT b.fg_product, b.rm_product, b.required_qty, p.unit as rm_unit
            FROM bom_master b LEFT JOIN product_master p ON b.rm_product = p.product_name
            ORDER BY b.fg_product, b.rm_product
        """)
        if not df_bom.empty:
            st.dataframe(df_bom, use_container_width=True)

# ======================= PURCHASE =======================
elif page == "🛒 Purchase":
    st.markdown("""
    <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 24px;">
        <div style="background: linear-gradient(135deg, #2a3f6a, #1f3152); padding: 10px 16px; border-radius: 16px;">
            <span style="font-size: 1.8rem;">🛒</span>
        </div>
        <div>
            <h1 style="font-size: 2rem; margin: 0;">Purchase Entry</h1>
            <p style="color: #8a9fc5; margin: 0;">Record raw material and product purchases</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    if 'pur_party_filter' not in st.session_state:
        st.session_state.pur_party_filter = "Purchase Party"
    if 'pur_prod_filter' not in st.session_state:
        st.session_state.pur_prod_filter = "RM Product"
    
    unit_options = ["kg", "Gross", "g", "Pcs", "PCS"]
    
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        party_filter = st.selectbox(
            "Party Category",
            ["Purchase Party", "Moulder", "Contractor", "Powder", "All"],
            key="pur_party_filter_select"
        )
        if party_filter != st.session_state.pur_party_filter:
            st.session_state.pur_party_filter = party_filter
            st.rerun()
    with col_f2:
        prod_cat_filter = st.selectbox(
            "Product Category",
            ["RM Product", "FG Product", "Moulding Product", "Powder", "All"],
            key="pur_prod_filter_select"
        )
        if prod_cat_filter != st.session_state.pur_prod_filter:
            st.session_state.pur_prod_filter = prod_cat_filter
            st.rerun()
    
    df_parties, _ = get_dynamic_lists(st.session_state.pur_party_filter)
    party_list = df_parties['party_name'].tolist() if not df_parties.empty else []
    _, df_products = get_dynamic_lists(st.session_state.pur_prod_filter)
    product_list = df_products['product_name'].tolist() if not df_products.empty else []
    product_details_map = dict(zip(df_products['product_name'], zip(df_products['rate'], df_products['unit'], df_products['category']))) if not df_products.empty else {}
    
    with st.form("purchase_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            challan_no = st.text_input("Challan No *")
            purchase_date = st.date_input("Date", datetime.now())
            party = st.selectbox("Party", party_list if party_list else ["No parties added"])
        with col2:
            product = st.selectbox("Product", product_list if product_list else ["No products found"])
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
        
        if st.form_submit_button("💾 Save Purchase", type="primary"):
            if all([challan_no, party and party != "No parties added", product and product != "No products found", qty > 0]):
                try:
                    existing_challan = fetch_data("SELECT id FROM purchase_transactions WHERE challan_no = ?", (challan_no,))
                    if not existing_challan.empty:
                        st.error(f"❌ Challan No '{challan_no}' already exists!")
                    else:
                        purchase_amount = qty * rate
                        purchase_id = execute_query('''INSERT INTO purchase_transactions
                            (challan_no, date, party_name, product_name, category, product_category, qty, unit, rate, amount, entry_type)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PURCHASE')''',
                            (challan_no, purchase_date.strftime('%Y-%m-%d'), party, product, category, actual_prod_cat, qty, unit, rate, purchase_amount))
                        
                        if actual_prod_cat == 'RM Product':
                            execute_query("INSERT OR IGNORE INTO rm_inventory (product_name, opening_stock, total_purchased_qty, total_consumed_qty, closing_stock) VALUES (?, 0, 0, 0, 0)", (product,))
                            execute_query('''INSERT INTO rm_stock_movement
                                (transaction_date, challan_no, party_name, product_name, transaction_type, qty, opening_balance, closing_balance, reference_id)
                                VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?)''',
                                (purchase_date.strftime('%Y-%m-%d'), challan_no, party, product, 'PURCHASE', qty, purchase_id))
                            execute_query("UPDATE rm_inventory SET total_purchased_qty = COALESCE(total_purchased_qty, 0) + ? WHERE product_name = ?", (qty, product))
                            update_rm_inventory(product, 0, 'PURCHASE', purchase_date.strftime('%Y-%m-%d'), challan_no, purchase_id, rate=rate, party_name=party)
                        else:
                            execute_query("INSERT OR IGNORE INTO fg_inventory (product_name, opening_stock, produced_qty, sold_qty, rejected_qty, purchased_qty, closing_stock) VALUES (?, 0, 0, 0, 0, 0, 0)", (product,))
                            execute_query('''INSERT INTO fg_stock_movement
                                (transaction_date, challan_no, party_name, product_name, transaction_type, qty, opening_balance, closing_balance, reference_id)
                                VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?)''',
                                (purchase_date.strftime('%Y-%m-%d'), challan_no, party, product, 'PURCHASE', qty, purchase_id))
                            update_fg_inventory(product, 0, 'PURCHASE')
                        
                        create_payable_entry(party, challan_no, purchase_date.strftime('%Y-%m-%d'), purchase_amount, payment_days)
                        st.success(f"✅ Purchase saved! Amount: ₹{purchase_amount:,.2f}")
                        st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
            else:
                st.warning("Please fill all required fields")
    
    st.markdown("---")
    st.markdown("### All Purchase Entries")
    df_all_purchases = fetch_data("SELECT id, challan_no, date, party_name, product_name, qty, unit, rate, amount FROM purchase_transactions ORDER BY date DESC")
    if not df_all_purchases.empty:
        st.dataframe(df_all_purchases, use_container_width=True)
        st.metric("Total Purchase Value", f"₹{df_all_purchases['amount'].sum():,.2f}")

# ======================= PRODUCTION =======================
elif page == "🏭 Production":
    st.markdown("""
    <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 24px;">
        <div style="background: linear-gradient(135deg, #2a3f6a, #1f3152); padding: 10px 16px; border-radius: 16px;">
            <span style="font-size: 1.8rem;">🏭</span>
        </div>
        <div>
            <h1 style="font-size: 2rem; margin: 0;">Production Entry</h1>
            <p style="color: #8a9fc5; margin: 0;">Record production from contractors</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    if 'prod_party_filter' not in st.session_state:
        st.session_state.prod_party_filter = "Moulder"
    if 'prod_prod_filter' not in st.session_state:
        st.session_state.prod_prod_filter = "All"
    
    unit_options = ["kg", "Gross", "g", "Pcs", "PCS"]
    
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        party_filter = st.selectbox(
            "Party Category",
            ["Moulder", "Contractor", "Purchase Party", "All"],
            key="prod_party_filter_select"
        )
        if party_filter != st.session_state.prod_party_filter:
            st.session_state.prod_party_filter = party_filter
            st.rerun()
    with col_f2:
        prod_cat_filter = st.selectbox(
            "Product Category",
            ["All", "FG Product", "Moulding Product", "RM Product", "Powder"],
            key="prod_prod_filter_select"
        )
        if prod_cat_filter != st.session_state.prod_prod_filter:
            st.session_state.prod_prod_filter = prod_cat_filter
            st.rerun()
    
    df_parties, _ = get_dynamic_lists(st.session_state.prod_party_filter)
    party_list = df_parties['party_name'].tolist() if not df_parties.empty else []
    _, df_products = get_dynamic_lists(st.session_state.prod_prod_filter)
    product_list = df_products['product_name'].tolist() if not df_products.empty else []
    product_details_map = {}
    if not df_products.empty:
        for _, row in df_products.iterrows():
            product_details_map[row['product_name']] = (row['rate'], row['unit'], row['category'])
    
    with st.form("production_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            challan_no = st.text_input("Challan No")
            prod_date = st.date_input("Date", datetime.now())
            party_name = st.selectbox("Party/Moulder/Contractor", party_list if party_list else ["No parties added"])
        with col2:
            fg_product = st.selectbox("Product to Produce", product_list if product_list else ["No products found"])
            unit_val = 'PCS'
            actual_prod_cat = "FG Product"
            if fg_product in product_details_map:
                r, u, c = product_details_map[fg_product]
                unit_val = u
                actual_prod_cat = c
            produced_qty = st.number_input("Produced Qty *", min_value=0.0, step=1.0)
            unit = st.selectbox("Unit", unit_options, index=unit_options.index(unit_val) if unit_val in unit_options else 4)
        with col3:
            description = st.text_area("Description")
        
        if st.form_submit_button("💾 Save Production", type="primary"):
            if all([party_name and party_name != "No parties added", fg_product and fg_product != "No products found", produced_qty > 0]):
                try:
                    prod_id = execute_query('''INSERT INTO production_register
                        (challan_no, date, party_name, fg_product, product_category, produced_qty, unit, description)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                        (challan_no, prod_date.strftime('%Y-%m-%d'), party_name, fg_product, actual_prod_cat, produced_qty, unit, description))
                    
                    if actual_prod_cat == 'RM Product':
                        execute_query("INSERT OR IGNORE INTO rm_inventory (product_name, opening_stock, total_purchased_qty, total_consumed_qty, closing_stock) VALUES (?, 0, 0, 0, 0)", (fg_product,))
                        execute_query('''INSERT INTO rm_stock_movement
                            (transaction_date, challan_no, party_name, product_name, transaction_type, qty, opening_balance, closing_balance, reference_id)
                            VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?)''',
                            (prod_date.strftime('%Y-%m-%d'), challan_no, party_name, fg_product, 'PURCHASE', produced_qty, prod_id))
                        execute_query("UPDATE rm_inventory SET total_purchased_qty = COALESCE(total_purchased_qty, 0) + ? WHERE product_name = ?", (produced_qty, fg_product))
                        update_rm_inventory(fg_product, 0, 'PURCHASE', prod_date.strftime('%Y-%m-%d'), challan_no, prod_id, party_name=party_name)
                    else:
                        execute_query("INSERT OR IGNORE INTO fg_inventory (product_name, opening_stock, produced_qty, sold_qty, rejected_qty, purchased_qty, closing_stock) VALUES (?, 0, 0, 0, 0, 0, 0)", (fg_product,))
                        execute_query('''INSERT INTO fg_stock_movement
                            (transaction_date, challan_no, party_name, product_name, transaction_type, qty, opening_balance, closing_balance, reference_id)
                            VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?)''',
                            (prod_date.strftime('%Y-%m-%d'), challan_no, party_name, fg_product, 'PRODUCE', produced_qty, prod_id))
                        update_fg_inventory(fg_product, 0, 'PRODUCE')
                    
                    st.success(f"✅ Production saved successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
            else:
                st.warning("Please fill all required fields")
    
    st.markdown("---")
    st.markdown("### All Production Entries")
    df_all_production = fetch_data("SELECT id, challan_no, date, party_name, fg_product, produced_qty, unit FROM production_register ORDER BY date DESC")
    if not df_all_production.empty:
        st.dataframe(df_all_production, use_container_width=True)

# ======================= SALES =======================
elif page == "💰 Sales":
    st.markdown("""
    <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 24px;">
        <div style="background: linear-gradient(135deg, #2a3f6a, #1f3152); padding: 10px 16px; border-radius: 16px;">
            <span style="font-size: 1.8rem;">💰</span>
        </div>
        <div>
            <h1 style="font-size: 2rem; margin: 0;">Sales Entry</h1>
            <p style="color: #8a9fc5; margin: 0;">Record sales to customers</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    if 'sale_party_filter' not in st.session_state:
        st.session_state.sale_party_filter = "Sales Party"
    if 'sale_prod_filter' not in st.session_state:
        st.session_state.sale_prod_filter = "FG Product"
    
    unit_options = ["kg", "Gross", "g", "Pcs", "PCS"]
    
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        party_filter = st.selectbox(
            "Party Category",
            ["Sales Party", "Purchase Party", "Moulder", "Contractor", "All"],
            key="sale_party_filter_select"
        )
        if party_filter != st.session_state.sale_party_filter:
            st.session_state.sale_party_filter = party_filter
            st.rerun()
    with col_f2:
        prod_cat_filter = st.selectbox(
            "Product Category",
            ["FG Product", "Moulding Product", "RM Product", "Powder", "All"],
            key="sale_prod_filter_select"
        )
        if prod_cat_filter != st.session_state.sale_prod_filter:
            st.session_state.sale_prod_filter = prod_cat_filter
            st.rerun()
    
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
            party = st.selectbox("Sales Party", party_list if party_list else ["No parties added"])
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
        
        if st.form_submit_button("💾 Save Sale", type="primary"):
            if all([challan_no, party and party != "No parties added", product and product != "No products found", qty > 0]):
                try:
                    existing_challan = fetch_data("SELECT id FROM sales_transactions WHERE challan_no = ?", (challan_no,))
                    if not existing_challan.empty:
                        st.error(f"❌ Challan No '{challan_no}' already exists!")
                    else:
                        # Stock check for FG products
                        if actual_prod_cat in ['FG Product', 'Moulding Product']:
                            df_stock = fetch_data("SELECT closing_stock FROM fg_inventory WHERE product_name = ?", (product,))
                            available_fg = float(df_stock['closing_stock'].iloc[0]) if not df_stock.empty and pd.notna(df_stock['closing_stock'].iloc[0]) else 0.0
                            if available_fg < qty:
                                st.warning(f"⚠️ Insufficient FG stock! Available: {available_fg:.2f}, Requested: {qty:.2f}")
                                st.stop()
                            
                            is_available, shortages = check_rm_availability_for_fg(product, qty)
                            if not is_available:
                                st.error("❌ Insufficient RM stock for this FG product!")
                                for s in shortages:
                                    st.warning(f"⚠️ {s['rm_product']}: Need {s['required']:.2f}, Available: {s['available']:.2f}")
                                st.stop()
                        
                        sale_amount = qty * rate
                        sale_id = execute_query('''INSERT INTO sales_transactions
                            (challan_no, date, party_name, product_name, category, product_category, qty, unit, rate, amount, payment_terms_days, due_date)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                            (challan_no, sales_date.strftime('%Y-%m-%d'), party, product, category, actual_prod_cat, qty, unit, rate, sale_amount, payment_days, 
                             (sales_date + timedelta(days=payment_days)).strftime('%Y-%m-%d')))
                        
                        if actual_prod_cat == 'RM Product':
                            execute_query("INSERT OR IGNORE INTO rm_inventory (product_name, opening_stock, total_purchased_qty, total_consumed_qty, closing_stock) VALUES (?, 0, 0, 0, 0)", (product,))
                            execute_query('''INSERT INTO rm_stock_movement
                                (transaction_date, challan_no, party_name, product_name, transaction_type, qty, opening_balance, closing_balance, reference_id)
                                VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?)''',
                                (sales_date.strftime('%Y-%m-%d'), challan_no, party, product, 'SALE', qty, sale_id))
                            execute_query("UPDATE rm_inventory SET total_consumed_qty = COALESCE(total_consumed_qty, 0) + ? WHERE product_name = ?", (qty, product))
                            update_rm_inventory(product, 0, 'PURCHASE', sales_date.strftime('%Y-%m-%d'), challan_no, sale_id, rate=rate, party_name=party)
                        else:
                            execute_query('''INSERT INTO fg_stock_movement
                                (transaction_date, challan_no, party_name, product_name, transaction_type, qty, opening_balance, closing_balance, reference_id)
                                VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?)''',
                                (sales_date.strftime('%Y-%m-%d'), challan_no, party, product, 'SALE', qty, sale_id))
                            update_fg_inventory(product, 0, 'SALE')
                            
                            # Consume RM for FG sale
                            if actual_prod_cat in ['FG Product', 'Moulding Product']:
                                bom_items = fetch_data("SELECT rm_product, required_qty FROM bom_master WHERE fg_product = ?", (product,))
                                for _, bom_row in bom_items.iterrows():
                                    rm_product = bom_row['rm_product']
                                    rm_qty_needed = bom_row['required_qty'] * qty
                                    rm_check = fetch_data("SELECT closing_stock FROM rm_inventory WHERE product_name = ?", (rm_product,))
                                    if not rm_check.empty and rm_check['closing_stock'].iloc[0] >= rm_qty_needed:
                                        update_rm_inventory(rm_product, rm_qty_needed, 'CONSUMPTION', sales_date.strftime('%Y-%m-%d'), challan_no, sale_id, party_name=party)
                        
                        create_receivable_entry(party, challan_no, sales_date.strftime('%Y-%m-%d'), sale_amount, payment_days)
                        st.success(f"✅ Sale saved! Amount: ₹{sale_amount:,.2f}")
                        st.balloons()
                        st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
            else:
                st.warning("Please fill all required fields")
    
    st.markdown("---")
    st.markdown("### All Sales Entries")
    df_all_sales = fetch_data("SELECT id, challan_no, date, party_name, product_name, qty, unit, rate, amount FROM sales_transactions ORDER BY date DESC")
    if not df_all_sales.empty:
        st.dataframe(df_all_sales, use_container_width=True)
        st.metric("Total Sales Value", f"₹{df_all_sales['amount'].sum():,.2f}")

# ======================= LEDGER =======================
elif page == "📒 Ledger":
    st.markdown("""
    <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 24px;">
        <div style="background: linear-gradient(135deg, #2a3f6a, #1f3152); padding: 10px 16px; border-radius: 16px;">
            <span style="font-size: 1.8rem;">📒</span>
        </div>
        <div>
            <h1 style="font-size: 2rem; margin: 0;">Payable / Receivable Ledger</h1>
            <p style="color: #8a9fc5; margin: 0;">Manage payments and receipts</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["💰 Receivables", "💸 Payables"])
    
    with tab1:
        st.markdown("### Receivables (Customer owes you)")
        overdue = check_overdue_payments()
        if not overdue.empty:
            st.warning(f"⚠️ {len(overdue)} overdue receivable(s)")
        
        df_recv = fetch_data("""
            SELECT id, party_name, challan_no, invoice_date, due_date, amount, paid_amount, balance_amount, payment_status
            FROM payable_receivable_ledger WHERE transaction_type = 'RECEIVABLE' ORDER BY due_date
        """)
        if not df_recv.empty:
            col1, col2, col3, col4 = st.columns(4)
            with col1: st.metric("Total Invoices", len(df_recv))
            with col2: st.metric("Total Billed", f"₹{df_recv['amount'].sum():,.2f}")
            with col3: st.metric("Total Received", f"₹{df_recv['paid_amount'].sum():,.2f}")
            with col4: st.metric("Outstanding", f"₹{df_recv['balance_amount'].sum():,.2f}")
            
            st.dataframe(df_recv, use_container_width=True)
            
            # Payment recording
            unpaid = df_recv[(df_recv['payment_status'] != 'PAID') & (df_recv['balance_amount'] > 0)]
            if not unpaid.empty:
                st.markdown("---")
                st.markdown("### Record Payment Received")
                with st.form("recv_payment_form"):
                    recv_options = {f"{row['challan_no']} | {row['party_name']} | ₹{float(row['balance_amount']):,.2f}": row['id'] for _, row in unpaid.iterrows()}
                    selected = st.selectbox("Select Invoice", list(recv_options.keys()))
                    selected_id = recv_options.get(selected)
                    if selected_id:
                        current = fetch_data("SELECT balance_amount FROM payable_receivable_ledger WHERE id = ?", (selected_id,))
                        balance = float(current['balance_amount'].iloc[0]) if not current.empty else 0
                        amount = st.number_input("Payment Amount", min_value=0.01, max_value=balance, value=balance, step=0.01)
                        if st.form_submit_button("💵 Record Payment", type="primary"):
                            if selected_id and amount > 0:
                                current = fetch_data("SELECT paid_amount, balance_amount FROM payable_receivable_ledger WHERE id = ?", (selected_id,))
                                if not current.empty:
                                    new_paid = float(current['paid_amount'].iloc[0]) + amount
                                    new_balance = float(current['balance_amount'].iloc[0]) - amount
                                    status = 'PAID' if new_balance <= 0 else 'PARTIAL'
                                    execute_query("""
                                        UPDATE payable_receivable_ledger 
                                        SET paid_amount = ?, balance_amount = ?, payment_status = ? 
                                        WHERE id = ?
                                    """, (new_paid, new_balance, status, selected_id))
                                    st.success(f"✅ Payment of ₹{amount:,.2f} recorded!")
                                    st.rerun()
        else:
            st.info("No receivable records found")
    
    with tab2:
        st.markdown("### Payables (You owe suppliers)")
        overdue_pay = check_overdue_payables()
        if not overdue_pay.empty:
            st.warning(f"⚠️ {len(overdue_pay)} overdue payable(s)")
        
        df_pay = fetch_data("""
            SELECT id, party_name, challan_no, invoice_date, due_date, amount, paid_amount, balance_amount, payment_status
            FROM payable_receivable_ledger WHERE transaction_type = 'PAYABLE' ORDER BY due_date
        """)
        if not df_pay.empty:
            col1, col2, col3, col4 = st.columns(4)
            with col1: st.metric("Total Invoices", len(df_pay))
            with col2: st.metric("Total Billed", f"₹{df_pay['amount'].sum():,.2f}")
            with col3: st.metric("Total Paid", f"₹{df_pay['paid_amount'].sum():,.2f}")
            with col4: st.metric("Outstanding", f"₹{df_pay['balance_amount'].sum():,.2f}")
            
            st.dataframe(df_pay, use_container_width=True)
            
            unpaid_pay = df_pay[(df_pay['payment_status'] != 'PAID') & (df_pay['balance_amount'] > 0)]
            if not unpaid_pay.empty:
                st.markdown("---")
                st.markdown("### Record Payment Made")
                with st.form("pay_payment_form"):
                    pay_options = {f"{row['challan_no']} | {row['party_name']} | ₹{float(row['balance_amount']):,.2f}": row['id'] for _, row in unpaid_pay.iterrows()}
                    selected = st.selectbox("Select Invoice", list(pay_options.keys()), key="pay_select")
                    selected_id = pay_options.get(selected)
                    if selected_id:
                        current = fetch_data("SELECT balance_amount FROM payable_receivable_ledger WHERE id = ?", (selected_id,))
                        balance = float(current['balance_amount'].iloc[0]) if not current.empty else 0
                        amount = st.number_input("Payment Amount", min_value=0.01, max_value=balance, value=balance, step=0.01, key="pay_amount")
                        if st.form_submit_button("💸 Record Payment", type="primary"):
                            if selected_id and amount > 0:
                                current = fetch_data("SELECT paid_amount, balance_amount FROM payable_receivable_ledger WHERE id = ?", (selected_id,))
                                if not current.empty:
                                    new_paid = float(current['paid_amount'].iloc[0]) + amount
                                    new_balance = float(current['balance_amount'].iloc[0]) - amount
                                    status = 'PAID' if new_balance <= 0 else 'PARTIAL'
                                    execute_query("""
                                        UPDATE payable_receivable_ledger 
                                        SET paid_amount = ?, balance_amount = ?, payment_status = ? 
                                        WHERE id = ?
                                    """, (new_paid, new_balance, status, selected_id))
                                    st.success(f"✅ Payment of ₹{amount:,.2f} recorded!")
                                    st.rerun()
        else:
            st.info("No payable records found")

# ======================= REJECTIONS =======================
elif page == "⚠️ Rejections":
    st.markdown("""
    <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 24px;">
        <div style="background: linear-gradient(135deg, #2a3f6a, #1f3152); padding: 10px 16px; border-radius: 16px;">
            <span style="font-size: 1.8rem;">⚠️</span>
        </div>
        <div>
            <h1 style="font-size: 2rem; margin: 0;">Rejection Management</h1>
            <p style="color: #8a9fc5; margin: 0;">Track market and party rejections</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["Market Rejection", "Party Rejection"])
    
    df_parties = fetch_data("SELECT party_name FROM party_master")
    df_products = fetch_data("SELECT product_name FROM product_master")
    party_list = df_parties['party_name'].tolist() if not df_parties.empty else []
    product_list = df_products['product_name'].tolist() if not df_products.empty else []
    
    with tab1:
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
            
            if st.form_submit_button("Save Market Rejection", type="primary"):
                if all([mr_product, mr_qty > 0]):
                    try:
                        rej_id = execute_query('''INSERT INTO market_rejection_register 
                            (date, party_name, product_name, qty_rejected, reason, challan_ref)
                            VALUES (?, ?, ?, ?, ?, ?)''',
                            (mr_date.strftime('%Y-%m-%d'), mr_party, mr_product, mr_qty, mr_reason, mr_challan))
                        
                        execute_query("INSERT OR IGNORE INTO fg_inventory (product_name, opening_stock, produced_qty, sold_qty, rejected_qty, purchased_qty, closing_stock) VALUES (?, 0, 0, 0, 0, 0, 0)", (mr_product,))
                        execute_query('''INSERT INTO fg_stock_movement
                            (transaction_date, challan_no, party_name, product_name, transaction_type, qty, opening_balance, closing_balance, reference_id)
                            VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?)''',
                            (mr_date.strftime('%Y-%m-%d'), mr_challan, mr_party, mr_product, 'REJECT', mr_qty, rej_id))
                        update_fg_inventory(mr_product, 0, 'REJECT')
                        
                        st.success("✅ Market rejection saved!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
                else:
                    st.warning("Please fill all required fields")
        
        df_mr = fetch_data("SELECT date, party_name, product_name, qty_rejected, reason, challan_ref FROM market_rejection_register ORDER BY date DESC LIMIT 50")
        if not df_mr.empty:
            st.dataframe(df_mr, use_container_width=True)
    
    with tab2:
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
            
            if st.form_submit_button("Save Party Rejection", type="primary"):
                if all([pr_party, pr_product, pr_qty > 0]):
                    try:
                        execute_query('''INSERT INTO party_rejection_register 
                            (date, party_name, product_name, qty_rejected, reason, challan_ref)
                            VALUES (?, ?, ?, ?, ?, ?)''',
                            (pr_date.strftime('%Y-%m-%d'), pr_party, pr_product, pr_qty, pr_reason, pr_challan))
                        st.success("✅ Party rejection saved!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
                else:
                    st.warning("Please fill all required fields")
        
        df_pr = fetch_data("SELECT date, party_name, product_name, qty_rejected, reason, challan_ref FROM party_rejection_register ORDER BY date DESC LIMIT 50")
        if not df_pr.empty:
            st.dataframe(df_pr, use_container_width=True)

# ======================= INVENTORY =======================
elif page == "📈 Inventory":
    st.markdown("""
    <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 24px;">
        <div style="background: linear-gradient(135deg, #2a3f6a, #1f3152); padding: 10px 16px; border-radius: 16px;">
            <span style="font-size: 1.8rem;">📈</span>
        </div>
        <div>
            <h1 style="font-size: 2rem; margin: 0;">Inventory Management</h1>
            <p style="color: #8a9fc5; margin: 0;">RM and FG inventory overview</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    tab1, tab2, tab3 = st.tabs(["RM Inventory", "FG Inventory", "FG → RM Calculator"])
    
    with tab1:
        st.markdown("### Raw Material Inventory")
        df_rm = fetch_data("""
            SELECT i.product_name, i.opening_stock, i.total_purchased_qty, i.total_consumed_qty, i.closing_stock, i.rate
            FROM rm_inventory i ORDER BY i.product_name
        """)
        if not df_rm.empty:
            df_rm['closing_stock'] = pd.to_numeric(df_rm['closing_stock'], errors='coerce').fillna(0)
            st.dataframe(df_rm, use_container_width=True)
            
            col1, col2 = st.columns(2)
            with col1:
                total_value = (df_rm['closing_stock'] * df_rm['rate'].fillna(0)).sum()
                st.metric("Total Stock Value", f"₹{total_value:,.2f}")
    
    with tab2:
        st.markdown("### Finished Goods Inventory")
        df_fg = fetch_data("""
            SELECT i.product_name, i.opening_stock, i.produced_qty, i.purchased_qty, i.sold_qty, i.rejected_qty, i.closing_stock
            FROM fg_inventory i ORDER BY i.product_name
        """)
        if not df_fg.empty:
            st.dataframe(df_fg, use_container_width=True)
    
    with tab3:
        st.markdown("### FG to RM Material Calculator")
        
        df_fg_products = fetch_data("""
            SELECT product_name FROM product_master
            WHERE category IN ('FG Product', 'Moulding Product') ORDER BY product_name
        """)
        fg_list = df_fg_products['product_name'].tolist() if not df_fg_products.empty else []
        
        if fg_list:
            col1, col2 = st.columns(2)
            with col1:
                fg_product = st.selectbox("Select FG Product", fg_list)
            with col2:
                fg_qty = st.number_input("Quantity", min_value=0.0, step=1.0, value=1.0)
            
            if st.button("Calculate RM Requirements", type="primary"):
                if fg_product and fg_qty > 0:
                    bom_items = fetch_data("""
                        SELECT rm_product, required_qty FROM bom_master WHERE fg_product = ?
                    """, (fg_product,))
                    
                    if not bom_items.empty:
                        results = []
                        for _, row in bom_items.iterrows():
                            rm_name = row['rm_product']
                            required = row['required_qty'] * fg_qty
                            stock = fetch_data("SELECT closing_stock, rate FROM rm_inventory WHERE product_name = ?", (rm_name,))
                            available = float(stock['closing_stock'].iloc[0]) if not stock.empty and pd.notna(stock['closing_stock'].iloc[0]) else 0.0
                            rate = float(stock['rate'].iloc[0]) if not stock.empty and pd.notna(stock['rate'].iloc[0]) else 0.0
                            results.append({
                                "RM Product": rm_name,
                                "Required": round(required, 2),
                                "Available": round(available, 2),
                                "Shortage": round(required - available, 2),
                                "Status": "✅ OK" if available >= required else "❌ Shortage"
                            })
                        
                        df_results = pd.DataFrame(results)
                        st.dataframe(df_results, use_container_width=True)
                        
                        if any(r["Status"] == "❌ Shortage" for r in results):
                            st.error("⚠️ Some RM materials are in shortage!")
                        else:
                            st.success("✅ All RM materials available!")
                    else:
                        st.warning(f"No BOM defined for {fg_product}")
        else:
            st.info("No FG products found in master")

# ======================= REPORTS =======================
elif page == "📋 Reports":
    st.markdown("""
    <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 24px;">
        <div style="background: linear-gradient(135deg, #2a3f6a, #1f3152); padding: 10px 16px; border-radius: 16px;">
            <span style="font-size: 1.8rem;">📋</span>
        </div>
        <div>
            <h1 style="font-size: 2rem; margin: 0;">Reports & Analytics</h1>
            <p style="color: #8a9fc5; margin: 0;">Insights and summaries</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    report_type = st.selectbox("Select Report", 
        ["Production Summary", "Sales Summary", "Purchase Summary", "Contractor Performance", "Rejection Analysis"])
    
    if report_type == "Production Summary":
        df = fetch_data("""
            SELECT fg_product, COUNT(*) as days, SUM(produced_qty) as total, AVG(produced_qty) as avg
            FROM production_register GROUP BY fg_product ORDER BY total DESC
        """)
        if not df.empty:
            st.dataframe(df, use_container_width=True)
            st.bar_chart(df.set_index('fg_product')['total'])
    
    elif report_type == "Sales Summary":
        df = fetch_data("""
            SELECT product_name, COUNT(*) as transactions, SUM(qty) as total_qty, SUM(amount) as total_amount
            FROM sales_transactions GROUP BY product_name ORDER BY total_amount DESC
        """)
        if not df.empty:
            st.dataframe(df, use_container_width=True)
            st.bar_chart(df.set_index('product_name')['total_amount'])
    
    elif report_type == "Purchase Summary":
        df = fetch_data("""
            SELECT product_name, COUNT(*) as transactions, SUM(qty) as total_qty, SUM(amount) as total_amount
            FROM purchase_transactions GROUP BY product_name ORDER BY total_amount DESC
        """)
        if not df.empty:
            st.dataframe(df, use_container_width=True)
            st.bar_chart(df.set_index('product_name')['total_amount'])
    
    elif report_type == "Contractor Performance":
        df = fetch_data("""
            SELECT party_name, COUNT(DISTINCT DATE(date)) as days, SUM(produced_qty) as total
            FROM production_register GROUP BY party_name ORDER BY total DESC
        """)
        if not df.empty:
            st.dataframe(df, use_container_width=True)
            st.bar_chart(df.set_index('party_name')['total'])
    
    elif report_type == "Rejection Analysis":
        col1, col2 = st.columns(2)
        with col1:
            df_mr = fetch_data("SELECT product_name, SUM(qty_rejected) as total FROM market_rejection_register GROUP BY product_name ORDER BY total DESC")
            if not df_mr.empty:
                st.markdown("**Market Rejections**")
                st.dataframe(df_mr, use_container_width=True)
        with col2:
            df_pr = fetch_data("SELECT product_name, SUM(qty_rejected) as total FROM party_rejection_register GROUP BY product_name ORDER BY total DESC")
            if not df_pr.empty:
                st.markdown("**Party Rejections**")
                st.dataframe(df_pr, use_container_width=True)

# ======================= IMPORT/EXPORT =======================
elif page == "📤 Import/Export":
    st.markdown("""
    <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 24px;">
        <div style="background: linear-gradient(135deg, #2a3f6a, #1f3152); padding: 10px 16px; border-radius: 16px;">
            <span style="font-size: 1.8rem;">📤</span>
        </div>
        <div>
            <h1 style="font-size: 2rem; margin: 0;">Import / Export</h1>
            <p style="color: #8a9fc5; margin: 0;">Bulk data operations</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["Import Excel", "Export Data"])
    
    with tab1:
        uploaded_file = st.file_uploader("Choose Excel file", type=['xlsx', 'xls'])
        if uploaded_file is not None:
            if st.button("Import Data", type="primary"):
                with st.spinner("Importing..."):
                    messages = load_excel_data(uploaded_file)
                    for msg in messages:
                        if "✅" in msg: st.success(msg)
                        elif "❌" in msg: st.error(msg)
                st.success("Import completed!")
    
    with tab2:
        if st.button("Generate Excel Export", type="primary"):
            try:
                excel_data = export_to_excel()
                st.download_button(
                    label="📥 Download Excel",
                    data=excel_data,
                    file_name=f"jinay_erp_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                st.success("Export generated successfully!")
            except Exception as e:
                st.error(f"Error: {str(e)}")

# ======================= FOOTER =======================
st.markdown("""
<hr style="margin: 32px 0 16px;">
<div style="display: flex; justify-content: space-between; color: #5a6d8a; font-size: 0.8rem; padding: 0 8px;">
    <span>© 2026 Jinay ERP System</span>
    <span>Built with ❤️ · Streamlit · SQLite</span>
</div>
""", unsafe_allow_html=True)
