from fastapi import FastAPI, Request
import uvicorn
import os
import requests
from report_generator import generar_reporte

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_VERSION = "2022-06-28"
NOTION_DB_REPORTES_ID = os.getenv("NOTION_REPORTES_DB_ID")

app = FastAPI()

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json"
}

@app.post("/webhook")
async def handle_webhook(request: Request):
    payload = await request.json()

    try:
        props = payload["properties"]
        fecha_inicio = props["Fecha de inicio"]["date"]["start"]
        fecha_fin = props["Fecha de fin"]["date"]["start"]
        propietario = props["Propietario"]["select"]["name"]

        # Extraer archivo CSV subido en Notion
        files = props["Archivo CSV"].get("files", [])
        if not files:
            return {"error": "No se ha subido ningún archivo CSV."}
        file_url = files[0]["file"]["url"]

        # Descargar CSV localmente
        csv_local_path = "archivo_temporal.csv"
        file_response = requests.get(file_url, headers={"Authorization": f"Bearer {NOTION_TOKEN}"})
        with open(csv_local_path, "wb") as f:
            f.write(file_response.content)

        # Generar el PDF
        output_pdf = generar_reporte(csv_local_path, fecha_inicio, fecha_fin, propietario)

        # Subir PDF a file.io
        with open(output_pdf, 'rb') as f:
            upload_response = requests.post('https://file.io', files={'file': f})
        if upload_response.status_code != 200:
            return {"error": "No se pudo subir el PDF."}
        pdf_url = upload_response.json().get("link")

        # Crear nueva página en base de datos de reportes
        create_url = "https://api.notion.com/v1/pages"
        new_page = {
            "parent": {"database_id": NOTION_DB_REPORTES_ID},
            "properties": {
                "Nombre": {
                    "title": [{"text": {"content": f"Reporte {propietario} ({fecha_inicio} - {fecha_fin})"}}]
                },
                "PDF": {
                    "url": pdf_url
                },
                "Propietario": {
                    "select": {"name": propietario}
                },
                "Rango": {
                    "rich_text": [{"text": {"content": f"{fecha_inicio} - {fecha_fin}"}}]
                }
            }
        }

        notion_create = requests.post(create_url, headers=headers, json=new_page)
        if notion_create.status_code != 200:
            return {"error": "No se pudo crear la entrada en Notion."}

        return {"mensaje": "✅ Reporte generado y subido con éxito.", "archivo": pdf_url}

    except Exception as e:
        return {"error": str(e)}

@app.get("/")
def root():
    return {"mensaje": "✅ API activa en Render. Usa POST /webhook para generar el reporte."}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
