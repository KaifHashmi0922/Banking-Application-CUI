from __future__ import annotations
from typing import Optional, Dict, List, Tuple
from datetime import datetime, date, timedelta
from random import choice, randint
import mysql.connector
import hashlib
import logging
import time
from tabulate import tabulate

# ================= CONFIG =================
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "root",
    "database": "Banking_Applicaton"
}

MIN_BALANCE = 500
ATM_PIN_LENGTH = 4
OTP_LENGTH = 6
NET_BANKING_SESSION_TIMEOUT = 300

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DatabaseConnection:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._conn = mysql.connector.connect(**DB_CONFIG)
            cls._instance._conn.autocommit = False
        return cls._instance

    def get_cursor(self):
        return self._conn.cursor(dictionary=True)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()


class BankingException(Exception):
    pass


class AccountNotFoundError(BankingException):
    pass


class InsufficientBalanceError(BankingException):
    pass


class InvalidPinError(BankingException):
    pass


class InvalidCredentialsError(BankingException):
    pass


class OtpExpiredError(BankingException):
    pass


class Customer:
    def __init__(self, data: Dict):
        self.customer_id = data['customer_id']
        self.full_name = data['full_name']
        self.phone = data['phone']
        self.email = data['email']


class Account:
    def __init__(self, data: Dict):
        self.account_id = data['account_id']
        self.account_no = data['account_no']
        self.customer_id = data['customer_id']
        self.account_type = data.get('account_type', 'SAVINGS')
        self.balance = float(data['balance'])
        self.branch_id = data['branch_id']
        self.status = data['status']


class AtmCard:
    def __init__(self, data: Dict):
        self.card_id = data['card_id']
        self.account_id = data['account_id']
        self.card_number = data['card_number']
        self.pin_hash = data.get('pin_hash')
        self.status = data['status']


class BankingService:
    def __init__(self):
        self.db = DatabaseConnection()

    def _execute_query(self, query: str, params: Tuple = ()) -> List[Dict]:
        cursor = self.db.get_cursor()
        cursor.execute(query, params)
        return cursor.fetchall()

    def _execute_one(self, query: str, params: Tuple = ()) -> Optional[Dict]:
        cursor = self.db.get_cursor()
        cursor.execute(query, params)
        return cursor.fetchone()

    def _execute_insert(self, query: str, params: Tuple = ()) -> int:
        cursor = self.db.get_cursor()
        cursor.execute(query, params)
        self.db.commit()
        return cursor.lastrowid

    def _execute_update(self, query: str, params: Tuple = ()) -> int:
        cursor = self.db.get_cursor()
        cursor.execute(query, params)
        self.db.commit()
        return cursor.rowcount

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _generate_account_no() -> int:
        return randint(1000000000, 9999999999)

    @staticmethod
    def _generate_card_no() -> str:
        return ''.join(choice('0123456789') for _ in range(16))

    @staticmethod
    def _generate_otp() -> str:
        return ''.join(choice('0123456789') for _ in range(OTP_LENGTH))

    @staticmethod
    def hash_pin(pin: str) -> str:
        return hashlib.sha256(pin.encode()).hexdigest()

    def get_customer(self, phone: str) -> Optional[Customer]:
        result = self._execute_query("SELECT * FROM customers WHERE phone = %s", (phone,))
        return Customer(result[0]) if result else None

    def create_customer(self, data: Dict) -> int:
        query = """
            INSERT INTO customers (
                full_name, father_name, dob, gender, email, phone,
                address_line, city, state, pincode
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        return self._execute_insert(query, tuple(data.values()))

    def create_account(self, customer_id: int, branch_id: int, initial_deposit: float) -> int:
        account_no = self._generate_account_no()
        while self.get_account(account_no):
            account_no = self._generate_account_no()

        query = """
            INSERT INTO accounts (customer_id, branch_id, account_no, account_type, balance, status)
            VALUES (%s, %s, %s, 'SAVINGS', %s, 'ACTIVE')
        """
        return self._execute_insert(query, (customer_id, branch_id, account_no, initial_deposit))

    def get_account(self, account_no: int) -> Optional[Account]:
        result = self._execute_query(
            "SELECT * FROM accounts WHERE account_no = %s AND status = 'ACTIVE'",
            (account_no,)
        )
        return Account(result[0]) if result else None

    def get_account_by_id(self, account_id: int) -> Optional[Account]:
        print(account_id)
        result = self._execute_query(
            "SELECT * FROM accounts WHERE account_id = %s AND status = 'ACTIVE'",
            (account_id,)
        )
        return Account(result[0]) if result else None

    def get_account_full_details(self, account_no: int) -> Optional[Dict]:
        print(account_no,"+++++++++++++++++++++++++++")
        result = self._execute_query("""
            SELECT
                a.account_id,
                a.account_no,
                a.account_type,
                a.balance,
                a.status,
                a.branch_id,
                c.full_name,
                c.phone,
                c.email,
                c.city,
                c.state,
                c.pincode
            FROM accounts a
            JOIN customers c ON a.customer_id = c.customer_id
            WHERE a.account_no = %s AND a.status = 'ACTIVE'
        """, (account_no,))
        return result[0] if result else None

    def deposit(self, account_no: int, amount: float, channel: str = 'BRANCH') -> Dict:
        account = self.get_account(account_no)
        if not account:
            raise AccountNotFoundError("Account not found")
        if amount <= 0:
            raise BankingException("Amount must be greater than zero")

        txn_ref = f"TXN{int(time.time() * 1000)}"
        txn_id = self._execute_insert("""
            INSERT INTO transactions (txn_ref, account_id, channel, txn_type, amount, balance_after, status, txn_time)
            VALUES (%s, %s, %s, 'DEPOSIT', %s, %s, 'SUCCESS', NOW())
        """, (txn_ref, account.account_id, channel, amount, account.balance + amount))

        cursor = self.db.get_cursor()
        cursor.execute("UPDATE accounts SET balance = balance + %s WHERE account_id = %s", (amount, account.account_id))
        self.db.commit()

        self._execute_insert("""
            INSERT INTO ledger_entries (txn_id, account_id, entry_type, amount, balance_after)
            VALUES (%s, %s, 'CREDIT', %s, %s)
        """, (txn_id, account.account_id, amount, account.balance + amount))

        return {"txn_ref": txn_ref, "new_balance": account.balance + amount}

    def withdraw(self, account_no: int, amount: float, pin: Optional[str] = None, channel: str = 'BRANCH') -> Dict:
        account = self.get_account(account_no)
        if not account:
            raise AccountNotFoundError("Account not found")
        if amount <= 0:
            raise BankingException("Amount must be greater than zero")
        if amount > account.balance:
            raise InsufficientBalanceError("Insufficient balance")

        if channel == 'ATM' and pin:
            card = self.get_atm_card_by_account(account.account_id)
            if card and card.pin_hash != self.hash_pin(pin):
                raise InvalidPinError("Invalid PIN")

        txn_ref = f"TXN{int(time.time() * 1000)}"
        txn_id = self._execute_insert("""
            INSERT INTO transactions (txn_ref, account_id, channel, txn_type, amount, balance_after, status, txn_time)
            VALUES (%s, %s, %s, 'WITHDRAW', %s, %s, 'SUCCESS', NOW())
        """, (txn_ref, account.account_id, channel, amount, account.balance - amount))

        cursor = self.db.get_cursor()
        cursor.execute("UPDATE accounts SET balance = balance - %s WHERE account_id = %s", (amount, account.account_id))
        self.db.commit()

        self._execute_insert("""
            INSERT INTO ledger_entries (txn_id, account_id, entry_type, amount, balance_after)
            VALUES (%s, %s, 'DEBIT', %s, %s)
        """, (txn_id, account.account_id, amount, account.balance - amount))

        return {"txn_ref": txn_ref, "new_balance": account.balance - amount}

    def transfer(self, from_account_no: int, to_account_no: int, amount: float, pin: str) -> Dict:
        from_account = self.get_account(from_account_no)
        to_account = self.get_account(to_account_no)

        if not from_account or not to_account:
            raise AccountNotFoundError("Account not found")
        if from_account.account_id == to_account.account_id:
            raise BankingException("Cannot transfer to same account")
        if amount <= 0:
            raise BankingException("Amount must be greater than zero")
        if amount > from_account.balance:
            raise InsufficientBalanceError("Insufficient balance")

        card = self.get_atm_card_by_account(from_account.account_id)
        if card and card.pin_hash != self.hash_pin(pin):
            raise InvalidPinError("Invalid PIN")

        txn_ref = f"TXN{int(time.time() * 1000)}"

        self._execute_insert("""
            INSERT INTO transactions (txn_ref, account_id, related_account_id, channel, txn_type, amount, balance_after, status, txn_time)
            VALUES (%s, %s, %s, 'TRANSFER', 'TRANSFER_DEBIT', %s, %s, 'SUCCESS', NOW())
        """, (txn_ref, from_account.account_id, to_account.account_id, amount, from_account.balance - amount))

        self._execute_insert("""
            INSERT INTO transactions (txn_ref, account_id, related_account_id, channel, txn_type, amount, balance_after, status, txn_time)
            VALUES (%s, %s, %s, 'TRANSFER', 'TRANSFER_CREDIT', %s, %s, 'SUCCESS', NOW())
        """, (txn_ref, to_account.account_id, from_account.account_id, amount, to_account.balance + amount))

        cursor = self.db.get_cursor()
        cursor.execute("UPDATE accounts SET balance = balance - %s WHERE account_id = %s", (amount, from_account.account_id))
        cursor.execute("UPDATE accounts SET balance = balance + %s WHERE account_id = %s", (amount, to_account.account_id))
        self.db.commit()

        return {"txn_ref": txn_ref, "new_balance": from_account.balance - amount}

    def get_atm_card_by_account(self, account_id: int) -> Optional[AtmCard]:
        result = self._execute_query(
            "SELECT * FROM atm_cards WHERE account_id = %s AND status = 'ACTIVE'",
            (account_id,)
        )
        return AtmCard(result[0]) if result else None

    def get_atm_card_by_number(self, card_number: str) -> Optional[AtmCard]:
        result = self._execute_query(
            "SELECT * FROM atm_cards WHERE card_number = %s AND status = 'ACTIVE'",
            (card_number,)
        )
        return AtmCard(result[0]) if result else None

    def set_card_pin(self, card_number: str, new_pin: str) -> bool:
        pin_hash = self.hash_pin(new_pin)
        count = self._execute_update(
            "UPDATE atm_cards SET pin_hash = %s WHERE card_number = %s",
            (pin_hash, card_number)
        )
        if count == 0:
            raise AccountNotFoundError("Card not found")
        return True

    def validate_card_pin(self, card_number: str, pin: str) -> Optional[int]:
        card = self.get_atm_card_by_number(card_number)
        if card and card.pin_hash == self.hash_pin(pin):
            return card.account_id
        return None

    def generate_otp(self, phone: str, purpose: str) -> str:
        otp = self._generate_otp()
        expires_at = (datetime.now() + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        self._execute_insert("""
            INSERT INTO otp_logs (phone, otp_code, purpose, expires_at, is_used)
            VALUES (%s, %s, %s, %s, FALSE)
        """, (phone, otp, purpose, expires_at))
        print(f"📱 OTP sent to {phone}: {otp} (valid for 5 min)")
        return otp

    def validate_otp(self, phone: str, otp: str, purpose: str) -> bool:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result = self._execute_query("""
            SELECT * FROM otp_logs
            WHERE phone = %s AND otp_code = %s AND purpose = %s AND expires_at > %s AND is_used = FALSE
            ORDER BY otp_id DESC
            LIMIT 1
        """, (phone, otp, purpose, now))
        if result:
            cursor = self.db.get_cursor()
            cursor.execute("UPDATE otp_logs SET is_used = TRUE WHERE otp_id = %s", (result[0]['otp_id'],))
            self.db.commit()
            return True
        return False

    def get_mini_statement(self, account_no: int, limit: int = 5) -> List[Dict]:
        account = self.get_account(account_no)
        if not account:
            return []
        return self._execute_query("""
            SELECT txn_ref, txn_type, channel, amount, balance_after, status, txn_time
            FROM transactions
            WHERE account_id = %s
            ORDER BY txn_time DESC
            LIMIT %s
        """, (account.account_id, limit))

    def get_mini_statement_by_id(self, account_id: int, limit: int = 5) -> List[Dict]:
        return self._execute_query("""
            SELECT txn_ref, txn_type, channel, amount, balance_after, status, txn_time
            FROM transactions
            WHERE account_id = %s
            ORDER BY txn_time DESC
            LIMIT %s
        """, (account_id, limit))

    def create_checkbook(self, account_no: int) -> int:
        account = self.get_account(account_no)
        if not account:
            raise AccountNotFoundError("Account not found")
        cheque_start = randint(1000000, 9999999)
        cheque_end = cheque_start + 24
        return self._execute_insert("""
            INSERT INTO checkbooks (account_id, request_date, start_cheque_no, end_cheque_no, leaves_count, status)
            VALUES (%s, NOW(), %s, %s, 25, 'ISSUED')
        """, (account.account_id, cheque_start, cheque_end))

    def issue_atm_card(self, account_no: int) -> str:
        account = self.get_account(account_no)
        if not account:
            raise AccountNotFoundError("Account not found")

        existing = self.get_atm_card_by_account(account.account_id)
        if existing:
            return existing.card_number

        card_number = self._generate_card_no()
        while self.get_atm_card_by_number(card_number):
            card_number = self._generate_card_no()

        self._execute_insert("""
            INSERT INTO atm_cards (account_id, card_number, card_type, expiry_month, expiry_year, status)
            VALUES (%s, %s, 'DEBIT', 12, 2030, 'ACTIVE')
        """, (account.account_id, card_number))
        return card_number

    def withdraw_by_id(self, account_id: int, amount: float, channel: str = 'ATM') -> Dict:
        account = self.get_account_by_id(account_id)
        if not account:
            raise AccountNotFoundError("Account not found")
        if amount <= 0:
            raise BankingException("Amount must be greater than zero")
        if amount > account.balance:
            raise InsufficientBalanceError("Insufficient balance")

        txn_ref = f"TXN{int(time.time() * 1000)}"
        txn_id = self._execute_insert("""
            INSERT INTO transactions (txn_ref, account_id, channel, txn_type, amount, balance_after, status, txn_time)
            VALUES (%s, %s, %s, 'WITHDRAW', %s, %s, 'SUCCESS', NOW())
        """, (txn_ref, account.account_id, channel, amount, account.balance - amount))

        cursor = self.db.get_cursor()
        cursor.execute("UPDATE accounts SET balance = balance - %s WHERE account_id = %s", (amount, account.account_id))
        self.db.commit()

        self._execute_insert("""
            INSERT INTO ledger_entries (txn_id, account_id, entry_type, amount, balance_after)
            VALUES (%s, %s, 'DEBIT', %s, %s)
        """, (txn_id, account.account_id, amount, account.balance - amount))

        return {"txn_ref": txn_ref, "amount": amount, "new_balance": account.balance - amount}

    def transfer_by_id(self, from_account_id: int, to_account_no: int, amount: float, pin: str) -> Dict:
        from_account = self.get_account_by_id(from_account_id)
        to_account = self.get_account(to_account_no)

        if not from_account or not to_account:
            raise AccountNotFoundError("One or both accounts not found")
        if from_account.account_id == to_account.account_id:
            raise BankingException("Cannot transfer to same account")
        if amount <= 0:
            raise BankingException("Amount must be greater than zero")
        if amount > from_account.balance:
            raise InsufficientBalanceError("Insufficient balance")

        card = self.get_atm_card_by_account(from_account.account_id)
        if card and card.pin_hash != self.hash_pin(pin):
            raise InvalidPinError("Invalid PIN")

        txn_ref = f"TXN{int(time.time() * 1000)}"

        self._execute_insert("""
            INSERT INTO transactions (txn_ref, account_id, related_account_id, channel, txn_type, amount, balance_after, status, txn_time)
            VALUES (%s, %s, %s, 'TRANSFER', 'TRANSFER_DEBIT', %s, %s, 'SUCCESS', NOW())
        """, (txn_ref, from_account.account_id, to_account.account_id, amount, from_account.balance - amount))

        self._execute_insert("""
            INSERT INTO transactions (txn_ref, account_id, related_account_id, channel, txn_type, amount, balance_after, status, txn_time)
            VALUES (%s, %s, %s, 'TRANSFER', 'TRANSFER_CREDIT', %s, %s, 'SUCCESS', NOW())
        """, (txn_ref, to_account.account_id, from_account.account_id, amount, to_account.balance + amount))

        cursor = self.db.get_cursor()
        cursor.execute("UPDATE accounts SET balance = balance - %s WHERE account_id = %s", (amount, from_account.account_id))
        cursor.execute("UPDATE accounts SET balance = balance + %s WHERE account_id = %s", (amount, to_account.account_id))
        self.db.commit()

        return {"txn_ref": txn_ref, "new_balance": from_account.balance - amount}

    def update_customer_basic(self, account_no: int, email: str, phone: str, city: str, state: str, pincode: str) -> bool:
        details = self.get_account_full_details(account_no)
        if not details:
            raise AccountNotFoundError("Account not found")
        count = self._execute_update(
            "UPDATE customers SET email = %s, phone = %s, city = %s, state = %s, pincode = %s WHERE customer_id = (SELECT customer_id FROM accounts WHERE account_no = %s)",
            (email, phone, city, state, pincode, account_no)
        )
        return count > 0

    def get_all_accounts(self) -> List[Dict]:
        return self._execute_query("""
            SELECT a.account_no, c.full_name, a.account_type, a.balance, a.status, a.branch_id
            FROM accounts a
            JOIN customers c ON a.customer_id = c.customer_id
            ORDER BY a.account_id DESC
        """)

    def close_account(self, account_no: int) -> bool:
        count = self._execute_update(
            "UPDATE accounts SET status = 'CLOSED' WHERE account_no = %s AND status = 'ACTIVE'",
            (account_no,)
        )
        return count > 0

    def change_net_banking_password(self, account_id: int, new_password: str) -> bool:
        password_hash = hashlib.sha256(new_password.encode()).hexdigest()
        count = self._execute_update(
            "UPDATE net_banking_users SET password_hash = %s WHERE account_id = %s AND is_active = TRUE",
            (password_hash, account_id)
        )
        return count > 0


class AccountManagement:
    def __init__(self, service: BankingService):
        self.service = service

    def menu(self):
        while True:
            print("" + "=" * 60)
            print("📋 ACCOUNT MANAGEMENT".center(60))
            print("=" * 60)
            print("1. Create Account")
            print("2. Modify Account")
            print("3. Add Checkbook")
            print("4. Add ATM Card")
            print("5. Add PAN Card")
            print("6. View Account Details")
            print("0. Back")

            choice_ = input("👉 Select: ").strip()

            if choice_ == '1':
                self.create_account()
            elif choice_ == '2':
                self.modify_account()
            elif choice_ == '3':
                self.add_checkbook()
            elif choice_ == '4':
                self.add_atm_card()
            elif choice_ == '5':
                self.add_pan_card()
            elif choice_ == '6':
                self.view_account()
            elif choice_ == '0':
                break
            else:
                print("❌ Invalid option")

    def create_account(self):
        print("👤 CUSTOMER DETAILS")
        name = input("Full Name: ").strip()
        father_name = input("Father Name: ").strip()
        dob_str = input("DOB (YYYY-MM-DD): ").strip()
        gender = input("Gender (Male/Female/Other): ").strip().upper()
        email = input("Email: ").strip()
        phone = input("Phone (10 digits): ").strip()
        address = input("Address: ").strip()
        city = input("City: ").strip()
        state = input("State: ").strip()
        pincode = input("Pincode: ").strip()

        try:
            amount = float(input(f"Initial Deposit (Min ₹{MIN_BALANCE}): "))
            if amount < MIN_BALANCE:
                print(f"❌ Minimum balance should be ₹{MIN_BALANCE}")
                return

            dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
            age = date.today().year - dob.year - ((date.today().month, date.today().day) < (dob.month, dob.day))
            if age <= 18:
                print("❌ Minimum age: 18 years")
                return

            customer_data = {
                'full_name': name,
                'father_name': father_name,
                'dob': dob,
                'gender': gender,
                'email': email,
                'phone': phone,
                'address_line': address,
                'city': city,
                'state': state,
                'pincode': pincode
            }

            customer_id = self.service.create_customer(customer_data)
            account_id = self.service.create_account(customer_id, 1, amount)
            account = self.service.get_account_by_id(account_id)

            print("✅ Account Created!")
            print(f"📋 Customer ID: {customer_id}")
            print(f"🏦 Account No: {account.account_no}")

        except Exception as e:
            print(f"❌ Error: {e}")

    def modify_account(self):
        try:
            account_no = int(input("Account No: ").strip())
        except ValueError:
            print("❌ Invalid account number")
            return

        details = self.service.get_account_full_details(account_no)
        if not details:
            print("❌ Account not found")
            return

        print("Leave field blank to keep old value")
        email = input(f"Email [{details.get('email', '')}]: ").strip() or details.get('email', '')
        phone = input(f"Phone [{details.get('phone', '')}]: ").strip() or details.get('phone', '')
        city = input(f"City [{details.get('city', '')}]: ").strip() or details.get('city', '')
        state = input(f"State [{details.get('state', '')}]: ").strip() or details.get('state', '')
        pincode = input(f"Pincode [{details.get('pincode', '')}]: ").strip() or details.get('pincode', '')

        try:
            self.service.update_customer_basic(account_no, email, phone, city, state, pincode)
            print("✅ Account details updated")
        except Exception as e:
            print(f"❌ Error: {e}")

    def view_account(self):
        try:
            account_number = int(input("Enter Account Number: ").strip())
        except ValueError:
            print("❌ Invalid account number.")
            return

        try:
            details = self.service.get_account_full_details(account_number)
            if not details:
                print("❌ Account not found.")
                return

            headers = ["Column Name", "Value"]
            rows = [
                ["Account ID", details.get("account_id", "N/A")],
                ["Account Number", details.get("account_no", "N/A")],
                ["Account Holder", details.get("full_name", "N/A")],
                ["Phone", details.get("phone", "N/A")],
                ["Email", details.get("email", "N/A")],
                ["Account Type", details.get("account_type", "N/A")],
                ["Balance", f"₹{float(details.get('balance', 0)):,.2f}"],
                ["Status", details.get("status", "N/A")],
                ["Branch ID", details.get("branch_id", "N/A")],
                ["City", details.get("city", "N/A")],
                ["State", details.get("state", "N/A")],
                ["Pincode", details.get("pincode", "N/A")]
            ]

            print("📋 ACCOUNT DETAILS")
            print(tabulate(rows, headers=headers, tablefmt="grid"))
            input("Press Enter to continue...")

        except Exception as e:
            print(f"❌ Error: {e}")

    def add_checkbook(self):
        try:
            account_no = int(input("Account No: "))
            checkbook_id = self.service.create_checkbook(account_no)
            print(f"✅ Checkbook issued! ID: {checkbook_id}")
        except Exception as e:
            print(f"❌ Error: {e}")

    def add_atm_card(self):
        try:
            account_no = int(input("Account No: "))
            card_no = self.service.issue_atm_card(account_no)
            print(f"✅ ATM Card issued! Card No: {card_no}")
            print("💡 Use ATM Services > Generate PIN to set PIN")
        except Exception as e:
            print(f"❌ Error: {e}")

    def add_pan_card(self):
        customer_phone = input("Customer Phone: ").strip()
        pan_no = input("PAN Number: ").upper().strip()
        try:
            customer = self.service.get_customer(customer_phone)
            if customer:
                self.service._execute_insert("""
                    INSERT INTO account_documents (customer_id, doc_type, doc_number, verified)
                    VALUES (%s, 'PAN', %s, TRUE)
                """, (customer.customer_id, pan_no))
                print("✅ PAN Card added")
            else:
                print("❌ Customer not found")
        except Exception as e:
            print(f"❌ Error: {e}")


class AtmServices:
    def __init__(self, service: BankingService):
        self.service = service

    def menu(self):
        while True:
            print("" + "=" * 60)
            print("💳 ATM SERVICES".center(60))
            print("=" * 60)
            print("1. Generate PIN")
            print("2. Change PIN")
            print("3. Forgot PIN (Phone OTP)")
            print("4. Check Balance")
            print("5. Mini Statement")
            print("6. Cash Withdrawal")
            print("7. Cash Deposit")
            print("8. Fund Transfer")
            print("0. Back")

            choice_ = input("👉 Select: ").strip()

            if choice_ == '1':
                self.generate_pin()
            elif choice_ == '2':
                self.change_pin()
            elif choice_ == '3':
                self.forgot_pin()
            elif choice_ == '4':
                self.check_balance()
            elif choice_ == '5':
                self.mini_statement()
            elif choice_ == '6':
                self.withdraw()
            elif choice_ == '7':
                self.deposit()
            elif choice_ == '8':
                self.transfer()
            elif choice_ == '0':
                break
            else:
                print("❌ Invalid option")

    def atm_login(self) -> Optional[int]:
        card_no = input("💳 Card Number (16 digits): ").strip()
        pin = input("🔒 PIN (4 digits): ").strip()
        account_id = self.service.validate_card_pin(card_no, pin)
        if account_id:
            print("✅ ATM Login Successful!")
            return account_id
        print("❌ Invalid Card/PIN")
        return None

    def generate_pin(self):
        card_no = input("💳 Card Number: ").strip()
        new_pin = input("🔐 New PIN (4 digits): ").strip()
        if len(new_pin) != 4 or not new_pin.isdigit():
            print("❌ PIN must be 4 digits")
            return
        try:
            self.service.set_card_pin(card_no, new_pin)
            print("✅ PIN generated successfully!")
        except Exception as e:
            print(f"❌ {e}")

    def change_pin(self):
        account_id = self.atm_login()
        if not account_id:
            return

        old_pin = input("🔒 Old PIN: ").strip()
        new_pin = input("🔐 New PIN: ").strip()
        if len(new_pin) != 4 or not new_pin.isdigit():
            print("❌ PIN must be 4 digits")
            return

        try:
            card = self.service.get_atm_card_by_account(account_id)
            if not card:
                print("❌ ATM card not found")
            elif card.pin_hash == self.service.hash_pin(old_pin):
                self.service.set_card_pin(card.card_number, new_pin)
                print("✅ PIN changed successfully!")
            else:
                print("❌ Invalid old PIN")
        except Exception as e:
            print(f"❌ Error changing PIN: {e}")

    def forgot_pin(self):
        phone = input("📱 Phone Number: ").strip()
        self.service.generate_otp(phone, 'FORGOT_PIN')
        otp = input("Enter OTP: ").strip()
        new_pin = input("🔐 New PIN: ").strip()

        if len(new_pin) != 4 or not new_pin.isdigit():
            print("❌ PIN must be 4 digits")
            return

        if self.service.validate_otp(phone, otp, 'FORGOT_PIN'):
            card_no = input("💳 Card Number: ").strip()
            try:
                self.service.set_card_pin(card_no, new_pin)
                print("✅ PIN reset successfully!")
            except Exception as e:
                print(f"❌ {e}")
        else:
            print("❌ Invalid/expired OTP")

    def check_balance(self):
        account_id = self.atm_login()
        if account_id:
            account = self.service.get_account_by_id(account_id)
            print(f"💰 Balance: ₹{account.balance:,.2f}")

    def mini_statement(self):
        account_id = self.atm_login()
        if account_id:
            print("📄 MINI STATEMENT (Last 5)")
            print("-" * 80)
            stmt = self.service.get_mini_statement_by_id(account_id)
            for txn in stmt:
                txn_time = str(txn['txn_time'])[:16]
                print(f"{txn_time} | {txn['txn_type']:<15} | ₹{float(txn['amount']):>10,.2f} | Bal: ₹{float(txn['balance_after']):>10,.2f}")

    def withdraw(self):
        account_id = self.atm_login()
        if account_id:
            try:
                amount = float(input("💸 Amount: "))
                result = self.service.withdraw_by_id(account_id, amount, channel='ATM')
                print(f"✅ Withdrawn ₹{result['amount']:,.2f}")
                print(f"💰 New Balance: ₹{result['new_balance']:,.2f}")
            except Exception as e:
                print(f"❌ {e}")

    def deposit(self):
        try:
            account_no = int(input("🏦 Account No: "))
            amount = float(input("💵 Deposit Amount: "))
            result = self.service.deposit(account_no, amount, 'ATM')
            print(f"✅ Deposited ₹{amount:,.2f}")
            print(f"💰 New Balance: ₹{result['new_balance']:,.2f}")
        except Exception as e:
            print(f"❌ {e}")

    def transfer(self):
        account_id = self.atm_login()
        if account_id:
            try:
                to_account_no = int(input("📤 To Account No: "))
                amount = float(input("💰 Amount: "))
                confirm_pin = input("🔒 Confirm PIN: ")
                self.service.transfer_by_id(account_id, to_account_no, amount, confirm_pin)
                print("✅ Transfer successful!")
            except Exception as e:
                print(f"❌ {e}")


class AdminPanel:
    def __init__(self, service: BankingService):
        self.service = service

    def menu(self):
        while True:
            print("" + "=" * 60)
            print("🔧 ADMIN PANEL".center(60))
            print("=" * 60)
            print("1. View Account Details")
            print("2. View All Accounts")
            print("3. Close Account")
            print("4. View ATM Cash Status")
            print("5. ATM Cash Load")
            print("6. ATM Reconciliation")
            print("7. Branch Management")
            print("0. Back")

            choice_ = input("👉 Select: ").strip()

            if choice_ == '1':
                self.view_account()
            elif choice_ == '2':
                self.view_all_accounts()
            elif choice_ == '3':
                self.close_account()
            elif choice_ == '4':
                self.atm_cash_status()
            elif choice_ == '5':
                self.atm_cash_load()
            elif choice_ == '6':
                self.atm_reconciliation()
            elif choice_ == '7':
                self.branch_management()
            elif choice_ == '0':
                break
            else:
                print("❌ Invalid option")

    def view_account(self):
        try:
            account_number = int(input("Enter Account Number: ").strip())
            details = self.service.get_account_full_details(account_number)
            if not details:
                print("❌ Account not found.")
                return
            rows = [[k.replace('_', ' ').title(), v] for k, v in details.items()]
            print("📋 ACCOUNT DETAILS")
            print(tabulate(rows, headers=["Column Name", "Value"], tablefmt="grid"))
        except Exception as e:
            print(f"❌ Error: {e}")

    def view_all_accounts(self):
        try:
            rows = self.service.get_all_accounts()
            if not rows:
                print("❌ No accounts found")
                return
            table = []
            for row in rows:
                table.append([
                    row['account_no'], row['full_name'], row['account_type'],
                    f"₹{float(row['balance']):,.2f}", row['status'], row['branch_id']
                ])
            print(tabulate(table, headers=["Account No", "Name", "Type", "Balance", "Status", "Branch ID"], tablefmt="grid"))
        except Exception as e:
            print(f"❌ Error: {e}")

    def close_account(self):
        try:
            account_no = int(input("Account No to close: ").strip())
            if self.service.close_account(account_no):
                print("✅ Account closed successfully")
            else:
                print("❌ Account not found or already closed")
        except Exception as e:
            print(f"❌ Error: {e}")

    def atm_cash_status(self):
        try:
            atms = self.service._execute_query("""
                SELECT a.atm_code, a.location_name, SUM(b.denomination * b.notes_count) AS cash_available
                FROM atm_machines a
                JOIN atm_cash_bins b ON a.atm_id = b.atm_id
                GROUP BY a.atm_id, a.atm_code, a.location_name
            """)
            print("💰 ATM CASH STATUS")
            print("-" * 70)
            for atm in atms:
                print(f"{atm['atm_code']:<10} | {atm['location_name']:<25} | ₹{float(atm['cash_available'] or 0):>12,.2f}")
        except Exception as e:
            print(f"❌ Error: {e}")

    def atm_cash_load(self):
        try:
            atm_code = input("ATM Code: ").strip()
            denomination = int(input("Denomination (100/200/500): "))
            notes_count = int(input("Notes Count: "))
            loaded_by = input("Loaded By: ").strip()

            atm_rows = self.service._execute_query("SELECT atm_id FROM atm_machines WHERE atm_code = %s", (atm_code,))
            if not atm_rows:
                print("❌ ATM not found")
                return

            atm_id = atm_rows[0]['atm_id']
            self.service._execute_insert("""
                INSERT INTO atm_cash_load_logs (atm_id, loaded_by, denomination, notes_added, total_amount)
                VALUES (%s, %s, %s, %s, %s)
            """, (atm_id, loaded_by, denomination, notes_count, denomination * notes_count))

            cursor = self.service.db.get_cursor()
            cursor.execute("""
                INSERT INTO atm_cash_bins (atm_id, denomination, notes_count)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE notes_count = notes_count + %s
            """, (atm_id, denomination, notes_count, notes_count))
            self.service.db.commit()
            print("✅ Cash loaded successfully!")
        except Exception as e:
            print(f"❌ Error: {e}")

    def atm_reconciliation(self):
        print("ℹ️ ATM reconciliation module not implemented yet.")

    def branch_management(self):
        print("ℹ️ Branch management module not implemented yet.")


class NetBanking:
    def __init__(self, service: BankingService):
        self.service = service
        self.session_active = False
        self.session_account_id = None

    def menu(self):
        while True:
            print("" + "=" * 60)
            print("🌐 NET BANKING".center(60))
            print("=" * 60)
            print("1. Register Net Banking")
            print("2. Login")
            print("3. View Balance")
            print("4. Transfer Funds")
            print("5. Transaction History")
            print("6. Change Password")
            print("0. Logout")

            choice_ = input("👉 Select: ").strip()

            if choice_ == '1':
                self.register()
            elif choice_ == '2':
                self.login()
            elif choice_ == '3' and self.session_active:
                self.view_balance()
            elif choice_ == '4' and self.session_active:
                self.transfer()
            elif choice_ == '5' and self.session_active:
                self.transaction_history()
            elif choice_ == '6' and self.session_active:
                self.change_password()
            elif choice_ == '0':
                self.logout()
                break
            else:
                print("❌ Please login first")

    def register(self):
        try:
            account_no = int(input("Account No: "))
            username = input("Username: ").strip()
            password = input("Password: ").strip()

            account = self.service.get_account(account_no)
            if account:
                password_hash = hashlib.sha256(password.encode()).hexdigest()
                self.service._execute_insert("""
                    INSERT INTO net_banking_users (account_id, username, password_hash)
                    VALUES (%s, %s, %s)
                """, (account.account_id, username, password_hash))
                print("✅ Net Banking registered!")
            else:
                print("❌ Account not found")
        except Exception as e:
            print(f"❌ Error: {e}")

    def login(self):
        username = input("Username: ").strip()
        password = input("Password: ").strip()
        result = self.service._execute_query("""
            SELECT nb.account_id, a.account_no
            FROM net_banking_users nb
            JOIN accounts a ON nb.account_id = a.account_id
            WHERE username = %s AND password_hash = %s AND is_active = TRUE
        """, (username, hashlib.sha256(password.encode()).hexdigest()))

        if result:
            self.session_active = True
            self.session_account_id = result[0]['account_id']
            print("✅ Net Banking Login Successful!")
        else:
            print("❌ Invalid credentials")

    def view_balance(self):
        account = self.service.get_account_by_id(self.session_account_id)
        print(f"💰 Balance: ₹{account.balance:,.2f}")

    def transfer(self):
        try:
            to_account_no = int(input("To Account No: "))
            amount = float(input("Amount: "))
            txn_pin = input("Transaction PIN: ")
            self.service.transfer_by_id(self.session_account_id, to_account_no, amount, txn_pin)
            print("✅ Transfer successful!")
        except Exception as e:
            print(f"❌ {e}")

    def transaction_history(self):
        stmt = self.service.get_mini_statement_by_id(self.session_account_id, 10)
        print("📄 TRANSACTION HISTORY")
        print("-" * 80)
        for txn in stmt:
            print(f"{str(txn['txn_time'])[:16]} | {txn['txn_type']:<15} | ₹{float(txn['amount']):>10,.2f}")

    def change_password(self):
        new_password = input("New Password: ").strip()
        if self.service.change_net_banking_password(self.session_account_id, new_password):
            print("✅ Password changed successfully")
        else:
            print("❌ Unable to change password")

    def logout(self):
        self.session_active = False
        self.session_account_id = None
        print("👋 Logged out")


class BankingCLI:
    def __init__(self):
        self.service = BankingService()
        self.account_mgmt = AccountManagement(self.service)
        self.atm = AtmServices(self.service)
        self.admin = AdminPanel(self.service)
        self.netbank = NetBanking(self.service)

    def print_banner(self):
        print("" + "*" * 20)
        print("COMPLETE BANKING SYSTEM v2.0".center(40))
        print("*" * 20)
        print(f" {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".center(40))

    def run(self):
        while True:
            self.print_banner()
            print("🔹 MAIN MENU")
            print("1️⃣  Account Management")
            print("2️⃣  ATM Services")
            print("3️⃣  Admin Panel")
            print("4️⃣  Net Banking")
            print("0️⃣  Exit")

            choice_ = input("👉 Select: ").strip()

            if choice_ == '1':
                self.account_mgmt.menu()
            elif choice_ == '2':
                self.atm.menu()
            elif choice_ == '3':
                self.admin.menu()
            elif choice_ == '4':
                self.netbank.menu()
            elif choice_ == '0':
                print("👋 Thank you for using our banking system!")
                break
            else:
                print("❌ Invalid option")


if __name__ == "__main__":
    app = BankingCLI()
    app.run()