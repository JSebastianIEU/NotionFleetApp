from fastapi import FastAPI
import uvicorn
import os
import requests
from report_generator import generar_reporte_df
import pandas as pd

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_VERSION = "2022-06-28"
NOTION_BTN_DB_ID = os.getenv("NOTION_BTN_DB_ID")  # base con una fila y el botón
NOTION_DATA_DB_ID = os.getenv("NOTION_DATA_DB_ID")  # base de datos de registros

app = FastAPI()

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json"
}

def obtener_fila_de_control():
    url = f"https://api.notion.com/v1/databases/{NOTION_BTN_DB_ID}/query"
    response = requests.post(url, headers=headers)
    data = response.json()
    return data['results'][0]  # solo una fila

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
        next_cursor = data["next_cursor"]

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
        output_pdf = generar_reporte_df(df_completo, fecha_inicio, fecha_fin, propietario)

        # Subir el PDF a file.io
        with open(output_pdf, 'rb') as f:
            upload = requests.post('https://file.io', files={'file': f})
        if upload.status_code != 200:
            return {"error": "No se pudo subir el PDF."}
        pdf_url = upload.json().get("link")

        # Actualizar la fila con el link del PDF
        update_url = f"https://api.notion.com/v1/pages/{page_id}"
        body = {
            "properties": {
                "Reporte": {
                    "url": pdf_url
                }
            }
        }
        update = requests.patch(update_url, headers=headers, json=body)
        if update.status_code != 200:
            return {"error": "No se pudo actualizar la fila con el PDF."}

        return {"mensaje": "✅ PDF generado y subido con éxito.", "archivo": pdf_url}

    except Exception as e:
        return {"error": str(e)}

@app.get("/")
def root():
    return {"mensaje": "✅ API activa. POST /webhook para generar el PDF desde Notion."}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)