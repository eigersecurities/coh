import os
import threading
from datetime import datetime
import tkinter as tk
from tkinter import messagebox, ttk

# =========================
# FORMAT
# =========================
def format_gbp(value):
    return f"£{value:,.2f}"


# =========================
# MYSQL (LAZY IMPORT)
# =========================
def load_mysql_data(currency, start_sql, end_sql):
    import pandas as pd
    import mysql.connector

    conn = mysql.connector.connect(
        host="gcs-ch.com",
        user="root",
        password="vaGcnV2i",
        database="gcsplatform_new"
    )

    query = f"""
    SELECT 
        DATE_FORMAT(trade_date, '%Y-%m-%d') as trade_date_str,
        nominal * 1000000 as nominal
    FROM GCSPLATFORM_INVOICE_LINE
    WHERE 
        CURRENCY = '{currency}'
        AND TRADE_DATE >= '{start_sql}'
        AND TRADE_DATE <= '{end_sql}'
        AND BROKER IN ('RMU','SWW','CDU','TSM','MCA','HAP','KDH','HSO','MTH')
        AND CONTRACT_NUMBER LIKE '%:b:%'
        AND deleted_by IS NULL
    ORDER BY TRADE_DATE;
    """

    df = pd.read_sql(query, conn)
    conn.close()
    return df


# =========================
# FX DATA (LAZY IMPORT)
# =========================
def load_fx_data(series_code, start_boe, end_boe, invert=False):
    import requests
    import pandas as pd
    import xml.etree.ElementTree as ET

    url = "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"

    params = {
        "CodeVer": "new",
        "xml.x": "true",
        "Datefrom": start_boe,
        "Dateto": end_boe,
        "SeriesCodes": series_code,
        "UsingCodes": "Y"
    }

    headers = {"User-Agent": "Mozilla/5.0"}

    r = requests.get(url, params=params, headers=headers)
    r.raise_for_status()

    root = ET.fromstring(r.text)

    ns = {
        "ns": "https://web.prod.iadb.ext.az.cloud.bankofengland.co.uk/website/agg_series"
    }

    data = []

    for c in root.findall(".//ns:Cube[@TIME]", ns):
        val = float(c.attrib["OBS_VALUE"])
        if invert:
            val = 1 / val

        data.append({
            "trade_date_str": c.attrib["TIME"],
            "fx_rate": val
        })

    return pd.DataFrame(data)


# =========================
# PROCESS
# =========================
def process_currency(currency, series, invert, start_dt, end_dt):
    import pandas as pd

    start_sql = start_dt.strftime("%Y-%m-%d")
    end_sql = end_dt.strftime("%Y-%m-%d")

    start_boe = start_dt.strftime("%d/%b/%Y")
    end_boe = end_dt.strftime("%d/%b/%Y")

    update_status(f"Loading {currency} data...")
    df = load_mysql_data(currency, start_sql, end_sql)

    update_status(f"Fetching {currency} FX...")
    fx = load_fx_data(series, start_boe, end_boe, invert)

    update_status(f"Merging {currency}...")
    merged = pd.merge(df, fx, on="trade_date_str", how="left")
    merged["fx_rate"] = merged["fx_rate"].ffill()
    merged["gbp"] = merged["nominal"] * merged["fx_rate"]

    total = merged["gbp"].sum()

    days = pd.bdate_range(start=start_dt, end=end_dt)
    avg = total / len(days)

    return currency, total, avg


# =========================
# THREAD WORKER
# =========================
def run_with_progress():
    try:
        progress.start()
        update_status("Starting report...")

        start = datetime.strptime(start_entry.get(), "%Y-%m-%d")
        end = datetime.strptime(end_entry.get(), "%Y-%m-%d")

        usd = process_currency("USD", "XUDLUSS", False, start, end)
        eur = process_currency("EUR", "XUDLERS", False, start, end)

        update_status("Finalising...")

        output = (
            f"===== USD =====\n"
            f"Total GBP: {format_gbp(usd[1])}\n"
            f"Average/day: {format_gbp(usd[2])}\n\n"
            f"===== EUR =====\n"
            f"Total GBP: {format_gbp(eur[1])}\n"
            f"Average/day: {format_gbp(eur[2])}\n"
        )

        app.after(0, lambda: result_box.delete("1.0", tk.END))
        app.after(0, lambda: result_box.insert(tk.END, output))

        update_status("Done ✅")

    except Exception as e:
        app.after(0, lambda: messagebox.showerror("Error", str(e)))
        update_status("Error ❌")

    finally:
        progress.stop()
        run_button.config(state="normal")


# =========================
# UI ACTION
# =========================
def generate():
    run_button.config(state="disabled")
    threading.Thread(target=run_with_progress).start()


# =========================
# SAFE UI UPDATE
# =========================
def update_status(message):
    app.after(0, lambda: status_label.config(text=message))


# =========================
# UI
# =========================
app = tk.Tk()
app.title("FX Daily Report Tool")
app.geometry("500x450")

# 🔥 Force instant render
app.update()

tk.Label(app, text="Start Date (YYYY-MM-DD)").pack()
start_entry = tk.Entry(app)
start_entry.pack()

tk.Label(app, text="End Date (YYYY-MM-DD)").pack()
end_entry = tk.Entry(app)
end_entry.pack()

run_button = tk.Button(app, text="Run Report", command=generate)
run_button.pack(pady=10)

status_label = tk.Label(app, text="Ready")
status_label.pack()

progress = ttk.Progressbar(app, mode="indeterminate")
progress.pack(fill=tk.X, padx=10, pady=5)

result_box = tk.Text(app, height=15)
result_box.pack(fill=tk.BOTH, expand=True)

app.mainloop()