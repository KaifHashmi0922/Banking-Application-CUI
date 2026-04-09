# Banking-Application-CUI
Production-ready banking system with Account Management, ATM Services, Admin Panel, and Net Banking modules. Built with proper database normalization, transaction audit trails, ATM reconciliation, and enterprise-grade validation.


| Module                | Core Capabilities                                                        |
| --------------------- | ------------------------------------------------------------------------ |
| 📋 Account Management | Create/Modify accounts, Issue Checkbooks, ATM Cards, PAN linking         |
| 💳 ATM Services       | PIN generation/change, Forgot PIN via OTP, Balance check, Mini-statement |
| ⚙️ Admin Panel        | Full account/branch/ATM management, Cash tracking, Reconciliation        |
| 🌐 Net Banking        | User registration, Secure login, Fund transfers, Transaction history     |


Core Banking Design (Enterprise Pattern)
├── Customers → Accounts → Cards/Checkbooks (1:M relationships)
├── Branches ↔ Accounts ↔ ATMs (Centralized posting)
├── Transactions → Ledger Entries (Immutable audit trail)
├── ATM Cash Bins → Load Logs → Electronic Journal (Reconciliation ready)
└── Net Banking → Centralized Account Updates (Single source of truth)


01. customers (KYC + personal data)
02. branches (IFSC + branch master)
03. account_documents (PAN/Aadhaar verification)
04. accounts (Balance + status management)
05. checkbooks (Cheque leaf tracking)
06. atm_cards (16-digit cards + PIN hash)
07. atm_pin_reset_logs (PIN change audit)
08. atm_machines (Location + status)
09. atm_cash_bins (Denomination-wise cash tracking)
10. atm_cash_load_logs (Cassette refill records)
11. net_banking_users (Username + 2FA)
12. otp_logs (Phone verification records)
13. transactions (All channel transactions)
14. ledger_entries (Debit/Credit double-entry)
15. atm_ej_logs (ATM Electronic Journal)
16. atm_reconciliation (Switch/Core matching)
17. audit_logs (Complete change tracking)




# 1. Install & Run MySQL
docker run -p 3306:3306 -e MYSQL_ROOT_PASSWORD=root123 mysql:8.0

# 2. Create Database + Tables
mysql -u root -p banking_system_v2 < schema.sql

# 3. Load Sample Data
mysql -u root -p banking_system_v2 < sample_data.sql

# 4. Run Banking CLI
python banking_system.py



🏦 BANKING SYSTEM v2.0 - CORE BANKING SOLUTION
═══════════════════════════════════════════════════════════════

1️⃣  ACCOUNT MANAGEMENT
   ├─ 1️⃣ Create Account (KYC + Documents)
   ├─ 2️⃣ Modify Account Details  
   ├─ 3️⃣ Issue Checkbook (25 leaves)
   ├─ 4️⃣ Issue ATM/Debit Card (PIN protected)
   └─ 5️⃣ Link PAN Card

2️⃣  ATM SERVICES  
   ├─ 1️⃣ Generate ATM PIN
   ├─ 2️⃣ Change ATM PIN
   ├─ 3️⃣ Forgot PIN (Phone OTP)
   ├─ 4️⃣ Check Balance
   └─ 5️⃣ Mini Statement (Last 5 Txns)

3️⃣  ADMIN PANEL
   ├─ 1️⃣ Manage All Accounts
   ├─ 2️⃣ Manage Branches (IFSC)
   ├─ 3️⃣ Track ATM Cash (₹100/200/500 notes)
   └─ 4️⃣ ATM Reconciliation

4️⃣  NET BANKING
   ├─ 1️⃣ Register/Login
   ├─ 2️⃣ Fund Transfer
   └─ 3️⃣ Transaction History

0️⃣  EXIT


| Operation        | Validations Applied                                       | Error Prevention                          |
| ---------------- | --------------------------------------------------------- | ----------------------------------------- |
| Account Creation | Phone/Email unique, Min age 18, Valid PAN/Aadhaar format  | Duplicate account prevention              |
| ATM PIN          | 4-digit numeric only, Phone OTP verification              | Brute force + shoulder surfing protection |
| Cash Withdrawal  | Daily limit ₹25K, Min balance ₹500, ATM cash availability | Overdraft + ATM dry prevention            |
| Fund Transfer    | Valid account exists, Sufficient balance, Transaction PIN | Failed transfer reversal                  |
| ATM Cash Load    | Denomination matching, Physical note count validation     | Cash reconciliation accuracy              |


-- Mini Statement (Last 5 transactions)
SELECT txn_ref, txn_type, amount, balance_after, txn_time 
FROM transactions WHERE account_id = 1 
ORDER BY txn_time DESC LIMIT 5;

-- ATM Cash Status (All machines)
SELECT atm_code, SUM(denomination * notes_count) as cash_available 
FROM atm_machines m JOIN atm_cash_bins b ON m.atm_id = b.atm_id 
GROUP BY m.atm_id;

-- Account Statement (30 days)
SELECT c.full_name, t.txn_ref, t.channel, t.amount, t.balance_after 
FROM transactions t JOIN accounts a ON t.account_id = a.account_id 
JOIN customers c ON a.customer_id = c.customer_id 
WHERE a.account_no = 1000000001 AND t.txn_time >= NOW() - INTERVAL 30 DAY;


✅ Phone OTP for sensitive operations (PIN reset, password reset)
✅ Password hashing (bcrypt/sha256) for net banking
✅ PIN hashing (never store plain PIN)
✅ Transaction audit trail (immutable ledger)
✅ Account status management (BLOCKED/INACTIVE)
✅ Daily withdrawal limits enforcement
✅ Minimum balance validation
✅ Duplicate detection (phone/email/account_no)
✅ SQL injection prevention (prepared statements)


• Normalized schema (No data duplication)
• Centralized transaction posting (All channels → single ledger)
• Audit-ready design (Complete change tracking)
• ATM reconciliation support (EJ logs + core matching)
• Multi-branch architecture (IFSC + branch linking)
• Transaction reference numbering (Unique txn_ref)
