# Configuración de la página - DEBE SER LA PRIMERA LÍNEA
import streamlit as st
st.set_page_config(page_title="@MDFinanzas - Ratio GD30/AL30 Trading", layout="wide")

import requests
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timedelta
import pytz
from streamlit_autorefresh import st_autorefresh
import sqlite3

# 🔄 Refresco automático cada 10 segundos
st_autorefresh(interval=10000, key="refresh")

# 🌍 Zona horaria Argentina
ARGENTINA_TZ = pytz.timezone('America/Argentina/Buenos_Aires')

def get_argentina_time():
    return datetime.now(ARGENTINA_TZ)

plt.style.use('dark_background')
plt.rcParams['figure.facecolor'] = 'black'
plt.rcParams['axes.facecolor']   = 'black'

DB_PATH = "trading_data.db"

def init_database():
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS historical_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            gd30 REAL, al30 REAL, ratio REAL,
            mm180 REAL, banda_sup REAL, banda_inf REAL,
            signal TEXT
        )
    ''')
    conn.commit(); conn.close()


def save_to_database(row):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute('''
      INSERT INTO historical_data
      (timestamp,gd30,al30,ratio,mm180,banda_sup,banda_inf,signal)
      VALUES (?,?,?,?,?,?,?,?)
    ''', row)
    conn.commit(); conn.close()


def load_historical_data(minutes=14400):
    conn = sqlite3.connect(DB_PATH)
    cutoff = (get_argentina_time() - timedelta(minutes=minutes)).isoformat()
    df = pd.read_sql_query(
        "SELECT * FROM historical_data WHERE timestamp>? ORDER BY timestamp ASC",
        conn, params=(cutoff,)
    )
    conn.close()
    return df

def detect_signal(current_ratio, banda_sup, banda_inf, previous_ratio=None):
    signal = ""
    if current_ratio <= banda_inf:
        signal = "🟢 COMPRAR GD30 / VENDER AL30"
    elif current_ratio >= banda_sup:
        signal = "🔴 VENDER GD30 / COMPRAR AL30"
    return signal

init_database()

current_time_arg = get_argentina_time()
st.markdown(f"# 🔹 Ratio GD30 / AL30 en Vivo")
st.markdown(f"**🕒 Hora Argentina:** {current_time_arg.strftime('%H:%M:%S - %d/%m/%Y')}")

if "data" not in st.session_state:
    hist = load_historical_data()
    if not hist.empty:
        timestamps_arg = pd.to_datetime(hist.timestamp).dt.tz_localize('UTC').dt.tz_convert(ARGENTINA_TZ)
        st.session_state["data"] = pd.DataFrame({
            "Hora": timestamps_arg.dt.strftime("%H:%M:%S"),
            "GD30": hist.gd30,
            "AL30": hist.al30,
            "Ratio": hist.ratio,
            "timestamp": timestamps_arg,
            "MM180": hist.mm180,
            "Banda_Sup": hist.banda_sup,
            "Banda_Inf": hist.banda_inf,
            "Signal": hist.signal
        })
    else:
        st.session_state["data"] = pd.DataFrame(columns=[
            "Hora","GD30","AL30","Ratio","timestamp",
            "MM180","Banda_Sup","Banda_Inf","Signal"])

endpoint = "https://data912.com/live/arg_bonds"
try:
    resp = requests.get(endpoint)
    precios = resp.json()
    now_arg = get_argentina_time()

    gd = next(x for x in precios if x["symbol"] == "GD30")
    al = next(x for x in precios if x["symbol"] == "AL30")

    if al["c"] != 0:
        ratio = gd["c"] / al["c"]
        temp = st.session_state["data"]["Ratio"].copy()
        temp = pd.concat([temp, pd.Series([ratio])], ignore_index=True)

        w = max(1, min(180, len(temp)))
        mm = temp.rolling(window=w, min_periods=1).mean().iloc[-1]
        sd = temp.rolling(window=w, min_periods=1).std().fillna(0).iloc[-1]
        sup = mm + 1.5 * sd
        inf = mm - 1.5 * sd

        prev_ratio = st.session_state["data"]["Ratio"].iloc[-1] if len(st.session_state["data"]) > 0 else None
        signal = detect_signal(ratio, sup, inf, prev_ratio)

        nuevo = {
            "Hora": now_arg.strftime("%H:%M:%S"),
            "GD30": gd["c"], "AL30": al["c"], "Ratio": ratio,
            "timestamp": now_arg, "MM180": mm,
            "Banda_Sup": sup, "Banda_Inf": inf, "Signal": signal
        }

        st.session_state["data"] = pd.concat([
            st.session_state["data"], pd.DataFrame([nuevo])
        ], ignore_index=True).tail(5000)

        save_to_database((now_arg.isoformat(), gd["c"], al["c"], ratio, mm, sup, inf, signal))

        if signal:
            if "COMPRAR GD30" in signal:
                st.success(f"🚨 **SEÑAL DE COMPRA**: {signal}")
            elif "VENDER GD30" in signal:
                st.error(f"🚨 **SEÑAL DE VENTA**: {signal}")

except Exception as e:
    st.error(f"Error en vivo: {e}")
    st.stop()

data = st.session_state["data"]
data = data.sort_values("timestamp").reset_index(drop=True)

if not data.empty:
    w2 = max(1, min(180, len(data)))
    data["MM180"]     = data["Ratio"].rolling(window=w2, min_periods=1).mean()
    data["std"]       = data["Ratio"].rolling(window=w2, min_periods=1).std().fillna(0)
    data["Banda_Sup"] = data["MM180"] + 1.5 * data["std"]
    data["Banda_Inf"] = data["MM180"] - 1.5 * data["std"]

    today = current_time_arg.date()
    data_today = data[data["timestamp"].dt.date == today]
    data_last5 = data[data["timestamp"] >= (current_time_arg - timedelta(days=5))]

    st.subheader("\U0001F4C8 Gráfico Intradiario GD30/AL30")
    fig, ax = plt.subplots(figsize=(15,6), facecolor='black')
    ax.plot(data["timestamp"], data["Ratio"], label="Ratio", color='cyan', linewidth=2)
    ax.plot(data["timestamp"], data["MM180"], label="MM180", color='yellow', linestyle='--')
    ax.plot(data["timestamp"], data["Banda_Sup"], label="Banda Sup", color='magenta')
    ax.plot(data["timestamp"], data["Banda_Inf"], label="Banda Inf", color='red')
    ax.fill_between(data["timestamp"], data["Banda_Sup"], data["Banda_Inf"], alpha=0.1, color='yellow')

    sig_data = data[data["Signal"] != ""]
    if not sig_data.empty:
        buys = sig_data[sig_data["Signal"].str.contains("COMPRAR")]
        sells = sig_data[sig_data["Signal"].str.contains("VENDER")]
        ax.scatter(buys["timestamp"], buys["Ratio"], color='green', s=100, marker='^', label='Compra')
        ax.scatter(sells["timestamp"], sells["Ratio"], color='red', s=100, marker='v', label='Venta')

    ax.legend(loc='upper left'); ax.grid(True, linestyle='--', alpha=0.3)
    ax.set_title("Ratio GD30/AL30 con Bandas de Bollinger", color='white')
    ax.set_xlabel("Hora", color='white'); ax.set_ylabel("Ratio", color='white')
    ax.tick_params(colors='white', labelrotation=45)
    plt.tight_layout()
    st.pyplot(fig)

    st.subheader("\U0001F4CA Datos Intradiarios")
    st.dataframe(data[["Hora","GD30","AL30","Ratio","Signal"]].iloc[::-1], use_container_width=True)

    st.subheader("\U0001F4DD Estadísticas")
    st.markdown("""
    - **Ratio promedio rueda anterior**: {:.4f}
    - **Ratio promedio últimas 5 ruedas**: {:.4f}
    - **Mínimo de la rueda**: {:.4f}
    - **Máximo de la rueda**: {:.4f}
    - **Media 180**: {:.4f}
    - **Banda superior**: {:.4f}
    - **Banda inferior**: {:.4f}
    - **Diferencia bandas (%)**: {:.2f}%
    """.format(
        data_today["Ratio"].mean(),
        data_last5["Ratio"].mean(),
        data_today["Ratio"].min(),
        data_today["Ratio"].max(),
        data["MM180"].iloc[-1],
        data["Banda_Sup"].iloc[-1],
        data["Banda_Inf"].iloc[-1],
        100 * (data["Banda_Sup"].iloc[-1] - data["Banda_Inf"].iloc[-1]) / data["MM180"].iloc[-1]
    ))

else:
    st.warning("⏳ Cargando datos...")


# Footer
st.markdown("---")
st.markdown("🔄 Actualización cada 20 segundos | 📊 Bonos ARG en vivo | 🇦🇷 Hora Argentina")
