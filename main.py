from fastapi import FastAPI, Request
from pydantic import BaseModel
import uvicorn
import os
import requests
from report_generator import generar_reporte

NOTION_TOKEN = os.getenv("NOTION_TOKEN")  # debe estar definido en tus variables de entorno
NOTION_VERSION = "2022-06-28"
NOTION_DB_REPORTES_ID = os.getenv("NOTION_REPORTES_DB_ID")  # ID de la base de datos de reportes

app = FastAPI()

class WebhookPayload(BaseModel):
    page_id: str

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json"
}

@app.post("/webhook")
async def handle_webhook(payload: WebhookPayload):
    page_id = payload.page_id
    notion_page_url = f"https://api.notion.com/v1/pages/{page_id}"
    response = requests.get(notion_page_url, headers=headers)

    if response.status_code != 200:
        return {"error": "No se pudo obtener la página de Notion."}

    data = response.json()

    # Extraer propiedades
    props = data["properties"]
    fecha_inicio = props["Fecha de inicio"]["date"]["start"]
    fecha_fin = props["Fecha de fin"]["date"]["start"]
    propietario_deseado = props["Propietario"]["select"]["name"]

    # Descargar CSV subido en la columna "Archivo CSV"
    files = props['Archivo CSV'].get('files', [])
    if not files:
        return {"error": "No se ha subido ningún archivo CSV."}
    file_info = files[0]
    file_url = file_info['file']['url']

    csv_local_path = "archivo_temporal.csv"
    file_response = requests.get(file_url, headers={"Authorization": f"Bearer {NOTION_TOKEN}"})
    with open(csv_local_path, "wb") as f:
        f.write(file_response.content)

    # Generar el reporte
    output_pdf = generar_reporte(csv_local_path, fecha_inicio, fecha_fin, propietario_deseado)

    # Subir a file.io
    with open(output_pdf, 'rb') as f:
        upload_response = requests.post('https://file.io', files={'file': f})
        if upload_response.status_code != 200:
            return {"error": "No se pudo subir el PDF."}
        file_url = upload_response.json().get("link")

    # Crear entrada en base de datos de reportes en Notion
    create_url = "https://api.notion.com/v1/pages"
    new_page = {
        "parent": {"database_id": NOTION_DB_REPORTES_ID},
        "properties": {
            "Nombre": {
                "title": [{"text": {"content": f"Reporte {propietario_deseado} ({fecha_inicio} - {fecha_fin})"}}]
            },
            "PDF": {
                "url": file_url
            },
            "Propietario": {
                "select": {"name": propietario_deseado}
            },
            "Rango": {
                "rich_text": [{"text": {"content": f"{fecha_inicio} - {fecha_fin}"}}]
            }
        }
    }

    notion_create = requests.post(create_url, headers=headers, json=new_page)

    if notion_create.status_code != 200:
        return {"error": "No se pudo crear la entrada en Notion."}

    return {"mensaje": "✅ Reporte generado y subido con éxito.", "archivo": file_url}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)