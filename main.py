from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn
import os
import requests
from report_generator import generar_reporte_df
import pandas as pd
from datetime import datetime
import unicodedata
import re

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_VERSION = "2022-06-28"
NOTION_BTN_DB_ID = os.getenv("NOTION_BTN_DB_ID")
NOTION_DATA_DB_ID = os.getenv("NOTION_DATA_DB_ID")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json"
}

def slugify(value):
    value = str(value)
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value).strip().lower()
    return re.sub(r'[-\s]+', '_', value)

def obtener_fila_de_control():
    url = f"https://api.notion.com/v1/databases/{NOTION_BTN_DB_ID}/query"
    response = requests.post(url, headers=headers)
    data = response.json()
    return data['results'][0]

def obtener_datos_tabulares():
    url = f"https://api.notion.com/v1/databases/{NOTION_DATA_DB_ID}/query"
    registros = []
    next_cursor = None

    while True:
        payload = {"start_cursor": next_cursor} if next_cursor else {}
        res = requests.post(url, headers=headers, json=payload)
        data = res.json()
        registros.extend(data['results'])
        if not data.get("has_more"):
            break
        next_cursor = data.get("next_cursor")

    rows = []
    for r in registros:
        props = r["properties"]
        rows.append({
            "Fecha": props["Fecha de Movimiento"]["date"]["start"] if props["Fecha de Movimiento"]["date"] else None,
            "Vehiculo": props["Vehiculo"]["title"][0]["text"]["content"] if props["Vehiculo"]["title"] else "",
            "Entrega": props["Entrega"]["rich_text"][0]["text"]["content"] if props["Entrega"]["rich_text"] else "",
            "Ahorro": props["Ahorro"]["rich_text"][0]["text"]["content"] if props["Ahorro"]["rich_text"] else "",
            "Factura/Gasto": props["Factura/Gasto"]["rich_text"][0]["text"]["content"] if props["Factura/Gasto"]["rich_text"] else "",
            "Balance": props["Balance"]["rich_text"][0]["text"]["content"] if props["Balance"]["rich_text"] else "",
            "Propietario": props["Propietario"]["select"]["name"] if props["Propietario"]["select"] else "",
            "Comprobante": props["Comprobante"]["rich_text"][0]["text"]["content"] if props["Comprobante"]["rich_text"] else ""
        })
    return pd.DataFrame(rows)

@app.post("/webhook")
async def handle_webhook():
    try:
        fila = obtener_fila_de_control()
        props = fila["properties"]
        page_id = fila["id"]

        fecha_inicio = props["Fecha de inicio"]["date"]["start"]
        fecha_fin = props["Fecha de fin"]["date"]["start"]
        propietario = props["Propietario"]["select"]["name"]

        df_completo = obtener_datos_tabulares()

        # Generar y sanitizar nombre del PDF
        raw_filename = generar_reporte_df(df_completo, fecha_inicio, fecha_fin, propietario)
        sanitized_name = slugify(raw_filename)
        sanitized_pdf_path = f"static/{sanitized_name}"

        # Renombrar si es necesario
        os.rename(f"static/{raw_filename}", sanitized_pdf_path)

        public_url = f"https://notionfleetapp.onrender.com/static/{sanitized_name}"
        print(f"🔗 PDF URL generado: {public_url}")

        # Actualizar campo "Reporte" con URL pública del PDF
        update_url = f"https://api.notion.com/v1/pages/{page_id}"
        body = {
            "properties": {
                "Reporte": {
                    "type": "url",
                    "url": public_url
                }
            }
        }
        update = requests.patch(update_url, headers=headers, json=body)
        print(f"📤 PATCH Status: {update.status_code} | Response: {update.text}")

        if update.status_code != 200:
            return {"error": "No se pudo actualizar Notion con la URL del PDF."}

        return {"mensaje": "✅ PDF generado y disponible.", "archivo": public_url}

    except Exception as e:
        return {"error": str(e)}

@app.get("/")
def root():
    return {"mensaje": "✅ API activa. POST /webhook para generar el PDF desde Notion."}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)