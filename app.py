import io
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from db import (
    add_transaction,
    delete_transaction,
    get_transactions,
    get_budgets,
    set_budget,
    get_month_summary,
    get_category_totals,
    init_db,
)

st.set_page_config(
    page_title="FinTrack | Kişisel Finans",
    page_icon="💸",
    layout="wide",
)

CATEGORIES = {
    "Gelir": ["Maaş", "Burs", "Freelance", "Diğer gelir"],
    "Gider": ["Yemek", "Ulaşım", "Kira", "Faturalar", "Eğitim", "Alışveriş", "Sağlık", "Eğlence", "Diğer gider"],
}

init_db()

st.title("💸 FinTrack")
st.caption("Kişisel finanslarını takip et, bütçeni planla ve harcamalarını analiz et.")

with st.sidebar:
    st.header("Filtreler")
    selected_month = st.date_input(
        "Ay seç (ayın herhangi bir gününü seçebilirsin)",
        value=date.today().replace(day=1),
    )
    month_key = selected_month.strftime("%Y-%m")
    st.divider()
    page = st.radio("Menü", ["Genel Bakış", "İşlem Ekle", "İşlemler", "Bütçe Yönetimi"])
    st.caption("Bu uygulama demo amaçlıdır; banka hesabına bağlanmaz.")

summary = get_month_summary(month_key)
income = summary["income"]
expenses = summary["expenses"]
balance = income - expenses
savings_rate = (balance / income * 100) if income > 0 else 0

if page == "Genel Bakış":
    st.subheader(f"{selected_month.strftime('%Y-%m')} finansal özeti")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Toplam gelir", f"₺{income:,.2f}")
    c2.metric("Toplam gider", f"₺{expenses:,.2f}")
    c3.metric("Kalan bakiye", f"₺{balance:,.2f}", delta=None)
    c4.metric("Tasarruf oranı", f"%{savings_rate:.1f}")

    st.divider()
    transactions = get_transactions(month=month_key)
    if transactions.empty:
        st.info("Bu ay henüz işlem yok. Sol menüden 'İşlem Ekle' bölümüne geçerek ilk kaydını oluştur.")
    else:
        left, right = st.columns(2)
        with left:
            st.markdown("#### Gelir ve gider dağılımı")
            flow_df = pd.DataFrame({
                "Tür": ["Gelir", "Gider"],
                "Tutar": [income, expenses],
            })
            fig = px.bar(flow_df, x="Tür", y="Tutar", color="Tür", title="Aylık toplamlar")
            st.plotly_chart(fig, use_container_width=True)
        with right:
            st.markdown("#### Gider kategorileri")
            category_df = get_category_totals(month_key, "Gider")
            if category_df.empty:
                st.info("Bu ay gider kaydı bulunmuyor.")
            else:
                fig = px.pie(category_df, names="category", values="total", hole=0.45, title="Giderlerin kategorilere göre dağılımı")
                st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### Son işlemler")
        display_df = transactions.copy()
        display_df["amount"] = display_df["amount"].map(lambda x: f"₺{x:,.2f}")
        st.dataframe(
            display_df.rename(columns={
                "id": "ID", "transaction_date": "Tarih", "kind": "Tür",
                "category": "Kategori", "amount": "Tutar", "description": "Açıklama"
            }),
            use_container_width=True,
            hide_index=True,
        )

elif page == "İşlem Ekle":
    st.subheader("Yeni işlem ekle")
    with st.form("transaction_form", clear_on_submit=True):
        kind = st.selectbox("İşlem türü", ["Gider", "Gelir"])
        category = st.selectbox("Kategori", CATEGORIES[kind])
        amount = st.number_input("Tutar (₺)", min_value=0.01, value=100.0, step=10.0, format="%.2f")
        transaction_date = st.date_input("Tarih", value=date.today())
        description = st.text_input("Açıklama", max_chars=120, placeholder="Örn. market alışverişi")
        submitted = st.form_submit_button("İşlemi kaydet", type="primary")

        if submitted:
            try:
                add_transaction(
                    transaction_date=transaction_date.isoformat(),
                    kind=kind,
                    category=category,
                    amount=float(amount),
                    description=description.strip(),
                )
                st.success("İşlem başarıyla kaydedildi.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

elif page == "İşlemler":
    st.subheader("İşlem geçmişi")
    transactions = get_transactions(month=month_key)
    if transactions.empty:
        st.info("Seçilen ay için işlem bulunamadı.")
    else:
        st.dataframe(
            transactions.rename(columns={
                "id": "ID", "transaction_date": "Tarih", "kind": "Tür",
                "category": "Kategori", "amount": "Tutar", "description": "Açıklama"
            }),
            use_container_width=True,
            hide_index=True,
        )
        transaction_ids = transactions["id"].astype(int).tolist()
        chosen_id = st.selectbox("Silmek istediğin işlem ID'si", transaction_ids)
        if st.button("Seçili işlemi sil", type="secondary"):
            delete_transaction(int(chosen_id))
            st.success(f"{chosen_id} numaralı işlem silindi.")
            st.rerun()

        csv_bytes = transactions.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "İşlemleri CSV olarak indir",
            data=csv_bytes,
            file_name=f"fintrack_{month_key}.csv",
            mime="text/csv",
        )

elif page == "Bütçe Yönetimi":
    st.subheader(f"{month_key} kategori bütçeleri")
    st.write("Her gider kategorisi için aylık bir limit belirleyebilirsin.")
    budgets = get_budgets(month_key)
    spent_df = get_category_totals(month_key, "Gider")
    spent_map = dict(zip(spent_df["category"], spent_df["total"])) if not spent_df.empty else {}

    with st.form("budget_form"):
        budget_category = st.selectbox("Gider kategorisi", CATEGORIES["Gider"])
        current_budget = float(budgets.get(budget_category, 0.0))
        budget_amount = st.number_input(
            "Aylık bütçe (₺)",
            min_value=0.0,
            value=current_budget,
            step=100.0,
            format="%.2f",
        )
        save_budget = st.form_submit_button("Bütçeyi kaydet", type="primary")
        if save_budget:
            set_budget(month_key, budget_category, float(budget_amount))
            st.success("Bütçe kaydedildi.")
            st.rerun()

    st.divider()
    rows = []
    all_categories = CATEGORIES["Gider"]
    for category_name in all_categories:
        limit = float(budgets.get(category_name, 0.0))
        spent = float(spent_map.get(category_name, 0.0))
        rows.append({
            "Kategori": category_name,
            "Bütçe (₺)": limit,
            "Harcanan (₺)": spent,
            "Kalan (₺)": limit - spent if limit > 0 else None,
            "Durum": "Limit aşıldı" if limit > 0 and spent > limit else ("Limit içinde" if limit > 0 else "Bütçe belirlenmedi"),
        })
    budget_df = pd.DataFrame(rows)
    st.dataframe(budget_df, use_container_width=True, hide_index=True)
    for row in rows:
        if row["Bütçe (₺)"] > 0 and row["Harcanan (₺)"] > row["Bütçe (₺)"]:
            st.warning(f'{row["Kategori"]}: bütçe limiti aşıldı! Harcama ₺{row["Harcanan (₺)"]:,.2f}, limit ₺{row["Bütçe (₺)"]:,.2f}.')
