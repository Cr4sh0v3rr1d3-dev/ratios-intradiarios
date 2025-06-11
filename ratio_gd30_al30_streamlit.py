
import streamlit as st
import requests
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import time

# Configuración inicial
st.set_page_config(page_title="Ratio GD30/AL30 en Tiempo Real", layout="wide")
st.title("📈 Ratio GD30 / AL30 en Tiempo Real")

# Endpoints
live_endpoint = "https://data912.com/live/arg_bonds"
historical_url_gd30 = "https://data912.com/historical/bonds/GD30"
historical_url_al30 = "https://data912.com/historical/bonds/AL30"

# Carga de datos históricos
@st.cache_data(ttl=3600)
def cargar_datos_historicos():
    gd30_hist = pd.DataFrame(requests.get(historical_url_gd30).json())
    al30_hist = pd.DataFrame(requests.get(historical_url_al30).json())

    gd30_hist['date'] = pd.to_datetime(gd30_hist['date'])
    al30_hist['date'] = pd.to_datetime(al30_hist['date'])

    merged = pd.merge(gd30_hist[['date', 'c']], al30_hist[['date', 'c']], on='date', suffixes=('_gd30', '_al30'))
    merged = merged.tail(100)
    merged['ratio'] = merged['c_gd30'] / merged['c_al30']
    merged = merged[['date', 'c_gd30', 'c_al30', 'ratio']]
    merged.rename(columns={'date': 'timestamp', 'c_gd30': 'gd30', 'c_al30': 'al30'}, inplace=True)
    return merged

data = cargar_datos_historicos()

# Actualización en vivo
placeholder = st.empty()

while True:
    try:
        response = requests.get(live_endpoint)
        datos = response.json()
        gd30 = next((item["c"] for item in datos if item["symbol"] == "GD30"), None)
        al30 = next((item["c"] for item in datos if item["symbol"] == "AL30"), None)

        if gd30 and al30 and al30 != 0:
            now = datetime.now()
            ratio = gd30 / al30
            nuevo = pd.DataFrame([{
                "timestamp": now,
                "gd30": gd30,
                "al30": al30,
                "ratio": ratio
            }])
            data = pd.concat([data, nuevo], ignore_index=True).tail(100)
            data["MM_21"] = data["ratio"].rolling(21).mean()
            promedio = data["ratio"].mean()

            with placeholder.container():
                st.subheader(f"Última actualización: {now.strftime('%H:%M:%S')}")
                fig, ax = plt.subplots(figsize=(15, 6))
                ax.plot(data["timestamp"], data["ratio"], label="Ratio GD30/AL30", color='b', marker='o', linewidth=2)
                if data["MM_21"].notna().sum() > 0:
                    ax.plot(data["timestamp"], data["MM_21"], label="MM21", color='y', linestyle='--')
                ax.axhline(y=promedio, color='red', linestyle='-', linewidth=2, label='Promedio')
                ax.set_title("Ratio GD30/AL30", fontsize=16)
                ax.set_xlabel("Fecha")
                ax.set_ylabel("Ratio")
                ax.legend()
                ax.grid(True)
                plt.xticks(rotation=45)
                st.pyplot(fig)

        time.sleep(6)

    except Exception as e:
        st.error(f"Error obteniendo datos: {e}")
        time.sleep(10)
