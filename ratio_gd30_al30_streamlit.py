# Configuración de la página - DEBE SER LA PRIMERA LÍNEA
import streamlit as st
st.set_page_config(page_title="@MDFinanzas - Ratio GD30/AL30 Trading", layout="wide")

import requests
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timedelta
import pytz  # Para manejo de zonas horarias
from streamlit_autorefresh import st_autorefresh
import sqlite3

# 🔄 Refresco automático cada 10 segundos
st_autorefresh(interval=10000, key="refresh")

# 🌍 Configuración de zona horaria Argentina
ARGENTINA_TZ = pytz.timezone('America/Argentina/Buenos_Aires')

def get_argentina_time():
    """Obtiene la hora actual en Argentina"""
    return datetime.now(ARGENTINA_TZ)

# 🎨 Configuración de matplotlib para fondo oscuro
plt.style.use('dark_background')
plt.rcParams['figure.facecolor'] = 'black'
plt.rcParams['axes.facecolor']   = 'black'

# 🗄️ SQLite para persistencia
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

def load_historical_data(minutes=15):
    conn = sqlite3.connect(DB_PATH)
    cutoff = (get_argentina_time() - timedelta(minutes=minutes)).isoformat()
    df = pd.read_sql_query(
        "SELECT * FROM historical_data WHERE timestamp>? ORDER BY timestamp ASC",
        conn, params=(cutoff,)
    )
    conn.close()
    return df

def detect_signal(current_ratio, banda_sup, banda_inf, previous_ratio=None):
    """
    Detecta señales de trading cuando el ratio toca las bandas
    """
    signal = ""
    
    # Señal cuando toca banda inferior: COMPRAR GD30, VENDER AL30
    if current_ratio <= banda_inf:
        signal = "🟢 COMPRAR GD30 / VENDER AL30"
    
    # Señal cuando toca banda superior: VENDER GD30, COMPRAR AL30
    elif current_ratio >= banda_sup:
        signal = "🔴 VENDER GD30 / COMPRAR AL30"
    
    return signal

# Inicializar DB
init_database()

# Encabezado
st.markdown("""
<div style="display:flex;justify-content:space-between;align-items:center">
  <h1>📊 Últimos 15 min · Datos cada 10s</h1>
  <h3>@MDFinanzas</h3>
</div>
""", unsafe_allow_html=True)

# Mostrar hora actual de Argentina
current_time_arg = get_argentina_time()
st.markdown(f"🕐 **Hora Argentina:** {current_time_arg.strftime('%H:%M:%S - %d/%m/%Y')}")

# Carga inicial
if "data" not in st.session_state:
    hist = load_historical_data(15)
    if not hist.empty:
        # Convertir timestamps a hora argentina
        timestamps_arg = (
            pd.to_datetime(hist.timestamp)
              .dt.tz_localize('UTC')
              .dt.tz_convert(ARGENTINA_TZ)
        )
        st.session_state["data"] = pd.DataFrame({
            "Hora": timestamps_arg.dt.strftime("%H:%M:%S"),
            "GD30": hist.gd30,
            "AL30": hist.al30,
            "Ratio": hist.ratio,
            "timestamp": timestamps_arg,
            "MM180": hist.mm180,
            "Banda_Sup": hist.banda_sup,
            "Banda_Inf": hist.banda_inf,
            "Signal": hist.signal if 'signal' in hist.columns else ""
        })
    else:
        st.session_state["data"] = pd.DataFrame(columns=[
            "Hora","GD30","AL30","Ratio","timestamp",
            "MM180","Banda_Sup","Banda_Inf","Signal"
        ])

# Endpoint en vivo
endpoint = "https://data912.com/live/arg_bonds"

# Obtener dato en vivo
try:
    resp = requests.get(endpoint)
    precios = resp.json()
    now_arg = get_argentina_time()

    gd = next(x for x in precios if x["symbol"] == "GD30")
    al = next(x for x in precios if x["symbol"] == "AL30")

    if al["c"] != 0:
        ratio = gd["c"] / al["c"]

        # temporal para cálculo de bandas
        temp = st.session_state["data"][["Ratio","timestamp"]].copy()
        temp = pd.concat([
            temp,
            pd.DataFrame([{"Ratio": ratio, "timestamp": now_arg}])
        ], ignore_index=True)

        w = max(1, min(180, len(temp)))
        mm = temp["Ratio"].rolling(window=w, min_periods=1).mean().iloc[-1]
        sd = temp["Ratio"].rolling(window=w, min_periods=1).std().fillna(0).iloc[-1]
        sup = mm + 1.5 * sd
        inf = mm - 1.5 * sd

        # Detectar señal de trading
        previous_ratio = (
            st.session_state["data"]["Ratio"].iloc[-1]
            if len(st.session_state["data"]) > 0 else None
        )
        signal = detect_signal(ratio, sup, inf, previous_ratio)

        nuevo = {
            "Hora": now_arg.strftime("%H:%M:%S"),
            "GD30": gd["c"],
            "AL30": al["c"],
            "Ratio": ratio,
            "timestamp": now_arg,
            "MM180": mm,
            "Banda_Sup": sup,
            "Banda_Inf": inf,
            "Signal": signal
        }

        st.session_state["data"] = pd.concat([
            st.session_state["data"],
            pd.DataFrame([nuevo])
        ], ignore_index=True).tail(90)

        save_to_database((
            now_arg.isoformat(), gd["c"], al["c"], ratio,
            mm, sup, inf, signal
        ))
        
        # Mostrar señal prominente si existe
        if signal:
            if "COMPRAR GD30" in signal:
                st.success(f"🚨 **SEÑAL DE COMPRA**: {signal}")
            elif "VENDER GD30" in signal:
                st.error(f"🚨 **SEÑAL DE VENTA**: {signal}")
            
except Exception as e:
    st.error(f"Error en vivo: {e}")
    st.stop()

data = st.session_state["data"]

# --- SOLO SE MODIFICÓ ESTA LÍNEA PARA EVITAR EL ERROR Tz-aware ---
data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True) \
                    .dt.tz_convert(ARGENTINA_TZ) \
                    .dt.tz_localize(None)
# ---------------------------------------------------------------

if not data.empty:
    # recalculo
    w2 = max(1, min(180, len(data)))
    data["MM180"]     = data["Ratio"].rolling(window=w2, min_periods=1).mean()
    data["std"]       = data["Ratio"].rolling(window=w2, min_periods=1).std().fillna(0)
    data["Banda_Sup"] = data["MM180"] + 1.5 * data["std"]
    data["Banda_Inf"] = data["MM180"] - 1.5 * data["std"]

    # Filtrar señales de hoy
    today_signals = data[data["timestamp"].dt.date == current_time_arg.date()]

    # Layout principal
    c1, c2 = st.columns([1, 2])
    
    with c1:
        st.subheader("📋 Tabla (últimos 15)")
        df_display = data[["Hora","GD30","AL30","Ratio","Signal"]].tail(15).copy()
        df_display["Signal"] = (
            df_display["Signal"].str[:20] + "..."
            if df_display["Signal"].str.len().max() > 20
            else df_display["Signal"]
        )
        st.dataframe(df_display.iloc[::-1], use_container_width=True, height=300)

    with c2:
        st.subheader("📈 Gráfico Intradiario")
        fig, ax = plt.subplots(figsize=(15,6), facecolor='black')
        x = data["timestamp"]

        ax.plot(x, data.Ratio,        label="Ratio",        color='cyan',   linewidth=2)
        ax.plot(x, data.MM180,        label="MM180",        color='yellow', linestyle='--')
        ax.plot(x, data.Banda_Sup,    label="Banda Superior", color='magenta')
        ax.plot(x, data.Banda_Inf,    label="Banda Inferior", color='red')
        ax.fill_between(x, data.Banda_Sup, data.Banda_Inf, alpha=0.1, color='yellow')

        signal_data = data[data["Signal"] != ""]
        if not signal_data.empty:
            buy_signals = signal_data[signal_data["Signal"].str.contains("COMPRAR", na=False)]
            sell_signals = signal_data[signal_data["Signal"].str.contains("VENDER GD30", na=False)]
            if not buy_signals.empty:
                ax.scatter(buy_signals["timestamp"], buy_signals["Ratio"], 
                          color='green', s=100, marker='^', label='Señal Compra GD30', zorder=5)
            if not sell_signals.empty:
                ax.scatter(sell_signals["timestamp"], sell_signals["Ratio"], 
                          color='red', s=100, marker='v', label='Señal Venta GD30', zorder=5)

        ax.tick_params(colors='white', labelrotation=45)
        ax.grid(True, linestyle='--', alpha=0.3)
        ax.legend(loc='upper left', frameon=True, facecolor='black', edgecolor='white')
        ax.set_title("Ratio GD30/AL30 con Bandas de Bollinger y Señales", color='white')
        ax.set_xlabel("Hora Argentina (HH:MM:SS)", color='white')
        ax.set_ylabel("Ratio", color='white')
        plt.tight_layout()
        st.pyplot(fig)

else:
    st.warning("⏳ Cargando datos...")

# Footer
st.markdown("---")
st.markdown("🔄 Actualización cada 10 segundos | 📊 Bonos ARG en vivo | 🇦🇷 Hora Argentina")
