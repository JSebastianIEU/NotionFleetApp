from fastapi import FastAPI, Request
import uvicorn
import os
import requests
from report_generator import generar_reporte

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_VERSION = "2022-06-28"

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
        # Notion envía los datos bajo 'event' → 'data' cuando usas botones en una automatización
        page_id = payload.get("event", {}).get("data", {}).get("id")
        if not page_id:
            return {"error": "No se encontró el page_id en el payload."}

        # Obtener datos completos de la página
        page_url = f"https://api.notion.com/v1/pages/{page_id}"
        page_response = requests.get(page_url, headers=headers)
        if page_response.status_code != 200:
            return {"error": "No se pudo obtener los datos de la página."}

        page_data = page_response.json()
        props = page_data["properties"]

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

        # Subir PDF a file.io (puedes cambiarlo por S3, etc.)
        with open(output_pdf, 'rb') as f:
            upload_response = requests.post('https://file.io', files={'file': f})
        if upload_response.status_code != 200:
            return {"error": "No se pudo subir el PDF."}
        pdf_url = upload_response.json().get("link")

        # Actualizar la misma página con la URL del PDF en la columna 'Reporte'
        update_url = f"https://api.notion.com/v1/pages/{page_id}"
        update_payload = {
            "properties": {
                "Reporte": {
                    "files": [
                        {
                            "name": f"Reporte_{propietario}.pdf",
                            "external": {"url": pdf_url}
                        }
                    ]
                }
            }
        }

        update_response = requests.patch(update_url, headers=headers, json=update_payload)
        if update_response.status_code != 200:
            return {"error": "No se pudo actualizar la página con el PDF."}

        return {"mensaje": "✅ Reporte generado y adjuntado con éxito.", "archivo": pdf_url}

    except Exception as e:
        return {"error": str(e)}

@app.get("/")
def root():
    return {"mensaje": "✅ API activa en Render. Usa POST /webhook para generar el reporte."}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
