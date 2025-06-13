import pandas as pd
from fpdf import FPDF
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from matplotlib.ticker import FuncFormatter
import re
import os
from datetime import datetime
from slugify import slugify

FONT_PATH = "times.ttf"

def clean_currency(val):
    if isinstance(val, str):
        return float(val.replace("COP", "").replace(",", "").replace(" ", "").strip() or 0)
    return float(val) if val != "" else 0.0

def generar_reporte_df(df, fecha_inicio, fecha_fin, propietario_deseado):
    df.fillna("", inplace=True)
    df.rename(columns={"Fecha de Movimiento": "Fecha"}, inplace=True)
    df['Vehiculo'] = df['Vehiculo'].apply(lambda x: re.match(r'^\w+', str(x)).group(0) if isinstance(x, str) else "")
    df['Fecha'] = pd.to_datetime(df['Fecha'], dayfirst=True).dt.date

    for col in ["Entrega", "Ahorro", "Factura/Gasto", "Balance"]:
        df[col] = df[col].apply(clean_currency)

    fecha_inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
    fecha_fin_dt = datetime.strptime(fecha_fin, "%Y-%m-%d").date()
    df_filtrado = df[(df['Fecha'] >= fecha_inicio_dt) & (df['Fecha'] <= fecha_fin_dt)]
    df_filtrado = df_filtrado[df_filtrado['Propietario'] == propietario_deseado]

    df_filtrado.drop(columns=['Propietario', 'Comprobante'], inplace=True, errors='ignore')
    df_filtrado.fillna(0.0, inplace=True)
    rango_fechas = f"{fecha_inicio_dt.strftime('%d/%m/%Y')} - {fecha_fin_dt.strftime('%d/%m/%Y')}"

    total_registros = len(df_filtrado)
    total_entregado = df_filtrado["Entrega"].sum()
    total_ahorro = df_filtrado["Ahorro"].sum()
    total_gastos = df_filtrado["Factura/Gasto"].sum()
    total_balance = df_filtrado["Balance"].sum()

    sns.set_style("whitegrid")
    plt.rcParams['font.family'] = 'DejaVu Sans'
    formatter = FuncFormatter(lambda x, _: f'{int(x):,}')

    def save_plot(data, title, ylabel, filename, color_palette):
        fig, ax = plt.subplots(figsize=(9, 3))
        bars = ax.bar(data.index, data.values, color=sns.color_palette(color_palette, len(data)), alpha=0.8)
        for bar in bars:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(), f'{int(bar.get_height()):,}', 
                    ha='center', va='bottom', fontsize=6)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.yaxis.set_major_formatter(formatter)
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        plt.savefig(filename, dpi=300, transparent=True)
        plt.close()

    pivot_line = df_filtrado.groupby(['Fecha', 'Vehiculo'])['Balance'].sum().reset_index()
    pivot_line = pivot_line.pivot(index='Fecha', columns='Vehiculo', values='Balance').fillna(0).cumsum()
    fig1, ax1 = plt.subplots(figsize=(9, 3))
    for col in pivot_line.columns:
        smooth = np.convolve(pivot_line[col], np.ones(3)/3, mode='same')
        ax1.plot(pivot_line.index, smooth, label=col, alpha=0.7, linewidth=2)
    ax1.set_title("Balance Acumulado")
    ax1.set_ylabel("COP")
    ax1.set_xlabel("Fecha")
    ax1.yaxis.set_major_formatter(formatter)
    ax1.legend(loc="upper left", fontsize=6)
    plt.tight_layout()
    plt.savefig("balance_moderno.png", dpi=300, transparent=True)
    plt.close()

    ahorro = df_filtrado.groupby("Vehiculo")["Ahorro"].sum()
    save_plot(ahorro[ahorro > 0], "Ahorro por Vehículo", "COP", "ahorro_moderno.png", "Blues")

    gastos = df_filtrado.groupby("Vehiculo")["Factura/Gasto"].sum().sort_values(ascending=False)
    save_plot(gastos, "Gastos por Taxi", "COP", "gastos_moderno.png", "flare")

    entregas = df_filtrado.groupby("Vehiculo")["Entrega"].sum().sort_values(ascending=False)
    save_plot(entregas, "Entregas por Taxi", "COP", "entregas_moderno.png", "crest")

    class PDF(FPDF):
        def __init__(self):
            super().__init__()
            self.set_auto_page_break(auto=True, margin=15)
            self.set_margins(10, 10, 10)
            self.add_font("Times", "", FONT_PATH, uni=True)
            self.add_font("Times", "B", FONT_PATH, uni=True)
            self.set_font("Times", size=12)

        def header(self):
            self.set_font("Times", "B", 16)
            self.cell(0, 10, "Reporte de Vehículos", ln=True, align="C")
            self.ln(3)
            self.set_font("Times", "", 12)
            self.cell(0, 10, f"Rango de fechas: {rango_fechas}", ln=True, align="C")
            self.ln(3)
            self.set_font("Times", "", 10)
            self.cell(0, 10, f"Propietario: {propietario_deseado}", ln=True)
            self.ln(5)

        def seccion_metricas(self):
            self.set_font("Times", "B", 12)
            self.cell(0, 10, "Resumen General", ln=True)
            self.set_font("Times", "", 11)
            for line in [
                f"• Total de registros: {total_registros}",
                f"• Total entregado: COP {int(total_entregado):,}",
                f"• Total ahorro: COP {int(total_ahorro):,}",
                f"• Total de gastos: COP {int(total_gastos):,}",
                f"• Suma total del balance: COP {int(total_balance):,}"
            ]:
                self.cell(0, 8, line, ln=True)
            self.ln(5)

        def insertar_graficos(self):
            self.set_font("Times", "B", 12)
            graficos = ["balance_moderno.png", "ahorro_moderno.png", "gastos_moderno.png", "entregas_moderno.png"]
            for i in range(0, len(graficos), 2):
                self.add_page()
                self.cell(0, 10, "Visualización de Datos", ln=True, align="C")
                self.ln(5)
                for img in graficos[i:i+2]:
                    if os.path.exists(img):
                        img_width = 180
                        x = (self.w - img_width) / 2
                        self.image(img, x=x, w=img_width)
                        self.ln(5)
                    else:
                        self.cell(0, 10, f"{img} no encontrado", ln=True, align="C")

        def tabla(self, dataframe):
            self.set_font("Times", "B", 10)
            col_width = (self.w - 20) / len(dataframe.columns)
            dataframe = dataframe.copy()
            dataframe["Fecha"] = pd.to_datetime(dataframe["Fecha"]).dt.strftime("%d/%m/%Y")
            for col in dataframe.columns:
                self.cell(col_width, 10, col, border=1, align="C")
            self.ln()
            self.set_font("Times", "", 9)
            for _, row in dataframe.iterrows():
                for col in dataframe.columns:
                    x = self.get_x()
                    y = self.get_y()
                    self.multi_cell(col_width, 5, str(row[col]), border=1)
                    self.set_xy(x + col_width, y)
                self.ln()

    safe_name = slugify(f"{propietario_deseado}_{fecha_inicio}")
    output_name = f"reporte_{safe_name}.pdf"
    output_path = os.path.join("static", output_name)

    pdf = PDF()
    pdf.add_page()
    pdf.seccion_metricas()
    pdf.insertar_graficos()
    pdf.add_page()
    pdf.tabla(df_filtrado)
    pdf.output(output_path)

    for img in ["balance_moderno.png", "ahorro_moderno.png", "gastos_moderno.png", "entregas_moderno.png"]:
        if os.path.exists(img):
            os.remove(img)

    return output_name