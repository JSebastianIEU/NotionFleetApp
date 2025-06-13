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
    print("🔔 Webhook recibido:", payload)

    # ✅ CORREGIDO: obtener el page_id correctamente
    page_id = payload.get("data", {}).get("id")
    print("➡️ page_id determinado:", page_id)
    if not page_id:
        return {"error": "No se encontró page_id en el payload."}

    # OBTENER página para leer propiedad "Archivo CSV"
    page_url = f"https://api.notion.com/v1/pages/{page_id}"
    response = requests.get(page_url, headers=headers)
    print("Conexión Notion GET status:", response.status_code)
    if response.status_code != 200:
        print("❌ Error al obtener página:", response.text)
        return {"error": "No se pudieron obtener datos de Notion."}

    data = response.json()
    props = data.get("properties", {})
    print("Propiedades recibidas:", list(props.keys()))

    # Extraer fechas y propietario (solo para log)
    fecha_inicio = props.get("Fecha de inicio", {}).get("date", {}).get("start")
    fecha_fin = props.get("Fecha de fin", {}).get("date", {}).get("start")
    propietario = props.get("Propietario", {}).get("select", {}).get("name")
    print(f"Fechas: {fecha_inicio} → {fecha_fin}, Propietario: {propietario}")

    # Archivo CSV:
    files = props.get("Archivo CSV", {}).get("files", [])
    print("Archivos CSV encontrados:", files)
    if not files:
        return {"error": "No se subió ningún archivo CSV."}
    file_url = files[0].get("file", {}).get("url")
    print("URL del CSV:", file_url)

    # DESCARGAR CSV
    try:
        file_response = requests.get(file_url, headers={"Authorization": f"Bearer {NOTION_TOKEN}"})
        open("archivo_temporal.csv", "wb").write(file_response.content)
        print("✅ CSV descargado correctamente.")
    except Exception as e:
        print("❌ Error descargando CSV:", e)
        return {"error": "No se pudo descargar CSV."}

    # GENERAR PDF
    try:
        output_pdf = generar_reporte("archivo_temporal.csv", fecha_inicio, fecha_fin, propietario)
        print("✅ PDF generado:", output_pdf)
    except Exception as e:
        print("❌ Error generando PDF:", e)
        return {"error": "Fallo al generar el reporte PDF."}

    # SUBIR PDF a file.io
    try:
        resp = requests.post("https://file.io", files={'file': open(output_pdf, 'rb')})
        print("File.io response code:", resp.status_code)
        pdf_url = resp.json().get("link")
        print("📎 URL del PDF:", pdf_url)
    except Exception as e:
        print("❌ Error subiendo PDF:", e)
        return {"error": "No se pudo subir el PDF."}

    # ACTUALIZAR la misma fila con el PDF
    update_url = f"https://api.notion.com/v1/pages/{page_id}"
    update_payload = {
        "properties": {
            "Reporte": {
                "files": [
                    {"name": os.path.basename(output_pdf), "external": {"url": pdf_url}}
                ]
            }
        }
    }
    upd_resp = requests.patch(update_url, headers=headers, json=update_payload)
    print("PATCH Notion status:", upd_resp.status_code, upd_resp.text)
    if upd_resp.status_code != 200:
        return {"error": "No se pudo actualizar la página con el PDF."}

    print("✅ PDF agregado a Notion en columna 'Reporte'.")
    return {"mensaje": "✅ Reporte generado y adjuntado.", "pdf_url": pdf_url}

@app.get("/")
def root():
    return {"mensaje": "API activa — presiona el botón de Notion para generar reporte."}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)