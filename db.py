import os
import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(os.environ.get("FINTRACK_DB_PATH", Path(__file__).with_name("fintrack.db")))


def get_connection():
    """Open a SQLite connection to the application's database."""
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    """Create database tables if they do not already exist."""
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_date TEXT NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('Gelir', 'Gider')),
                category TEXT NOT NULL,
                amount REAL NOT NULL CHECK (amount > 0),
                description TEXT NOT NULL DEFAULT ''
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL CHECK (amount >= 0),
                UNIQUE(month, category)
            )
        """)


def add_transaction(transaction_date, kind, category, amount, description=""):
    """Validate and save one income/expense transaction."""
    if kind not in ("Gelir", "Gider"):
        raise ValueError("İşlem türü Gelir veya Gider olmalıdır.")
    if not category or not category.strip():
        raise ValueError("Kategori boş olamaz.")
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        raise ValueError("Tutar sayısal olmalıdır.") from None
    if amount <= 0:
        raise ValueError("Tutar sıfırdan büyük olmalıdır.")

    with get_connection() as connection:
        cursor = connection.execute(
            """INSERT INTO transactions
               (transaction_date, kind, category, amount, description)
               VALUES (?, ?, ?, ?, ?)""",
            (str(transaction_date), kind, category.strip(), amount, description.strip()),
        )
        return cursor.lastrowid


def get_transactions(month=None):
    """Return transactions as a Pandas DataFrame, newest first."""
    query = """
        SELECT id, transaction_date, kind, category, amount, description
        FROM transactions
    """
    params = ()
    if month:
        query += " WHERE substr(transaction_date, 1, 7) = ?"
        params = (month,)
    query += " ORDER BY transaction_date DESC, id DESC"

    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()
    return pd.DataFrame([dict(row) for row in rows], columns=[
        "id", "transaction_date", "kind", "category", "amount", "description"
    ])


def delete_transaction(transaction_id):
    """Delete a transaction by its numeric ID."""
    with get_connection() as connection:
        connection.execute("DELETE FROM transactions WHERE id = ?", (int(transaction_id),))


def get_month_summary(month):
    """Return total income and expense for YYYY-MM."""
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT kind, COALESCE(SUM(amount), 0) AS total
               FROM transactions
               WHERE substr(transaction_date, 1, 7) = ?
               GROUP BY kind""",
            (month,),
        ).fetchall()
    totals = {"income": 0.0, "expenses": 0.0}
    for row in rows:
        if row["kind"] == "Gelir":
            totals["income"] = float(row["total"])
        elif row["kind"] == "Gider":
            totals["expenses"] = float(row["total"])
    return totals


def get_category_totals(month, kind="Gider"):
    """Return totals grouped by category for a month and transaction type."""
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT category, SUM(amount) AS total
               FROM transactions
               WHERE substr(transaction_date, 1, 7) = ? AND kind = ?
               GROUP BY category
               ORDER BY total DESC""",
            (month, kind),
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows], columns=["category", "total"])


def set_budget(month, category, amount):
    """Create or update a monthly category budget."""
    amount = float(amount)
    if amount < 0:
        raise ValueError("Bütçe negatif olamaz.")
    if not category or not category.strip():
        raise ValueError("Kategori boş olamaz.")
    with get_connection() as connection:
        connection.execute(
            """INSERT INTO budgets (month, category, amount)
               VALUES (?, ?, ?)
               ON CONFLICT(month, category) DO UPDATE SET amount = excluded.amount""",
            (month, category.strip(), amount),
        )


def get_budgets(month):
    """Return category budgets for YYYY-MM as {category: amount}."""
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT category, amount FROM budgets WHERE month = ?",
            (month,),
        ).fetchall()
    return {row["category"]: float(row["amount"]) for row in rows}
