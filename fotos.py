"""Sube fotos a tu carpeta de Google Drive mediante un Apps Script (corre con tu cuenta)."""
import base64
import os

import requests


def subir(data_url: str, nombre: str, secrets) -> str:
    """Regresa el texto que se guarda en la celda (ruta tipo AppSheet) o "" si no se pudo."""
    if not data_url:
        return ""
    mime, b64 = data_url.split(",", 1)
    url = secrets.get("fotos_script_url") if secrets else None
    prefijo = (secrets.get("foto_prefijo", "Hoja 1_Images/") if secrets else "Hoja 1_Images/")
    if not url:  # modo pruebas: guarda en la carpeta local
        os.makedirs("data/fotos", exist_ok=True)
        with open(os.path.join("data/fotos", nombre), "wb") as f:
            f.write(base64.b64decode(b64))
        return prefijo + nombre
    try:
        r = requests.post(url, json={"token": secrets.get("fotos_token", ""), "name": nombre,
                                     "mime": "image/jpeg", "data": b64}, timeout=40)
        j = r.json()
        if j.get("ok"):
            return prefijo + j.get("name", nombre)
        print("Error al subir foto:", j)
    except Exception as e:
        print("Error al subir foto:", e)
    return ""


def leer_qr(data_url: str) -> str:
    """Lee un QR desde una foto (respaldo para teléfonos sin escáner en vivo)."""
    try:
        import cv2
        import numpy as np
        b = base64.b64decode(data_url.split(",", 1)[1])
        img = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)
        txt, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
        if not txt:
            g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            txt, _, _ = cv2.QRCodeDetector().detectAndDecode(cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1])
        return txt or ""
    except Exception as e:
        print("No se pudo leer QR:", e)
        return ""
