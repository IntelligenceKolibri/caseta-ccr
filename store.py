"""Datos de la caseta: Google Sheets (Bitácora Vehicular) o CSV local para pruebas."""
import os
import pandas as pd

BITACORA_COLS = ["ID", "Fecha y Hora", "Registro por voz", "Foto ID", "Escáner QR", "Nombre de la Visita",
                 "Casa Destino", "Placas", "Vehículo", "Quién Autoriza", "Registró"]
TABS = {
    "Paquetes": ["ID", "Casa", "Residente", "Paqueteria", "A nombre de", "Esperado", "Nota", "Estado",
                 "Foto", "Llego", "Entregado", "Registró"],
    "Pases": ["Codigo", "Casa", "Autoriza", "Visita", "Placas", "Vehiculo", "Tipo", "Vigencia", "Estado", "Creado"],
    "Usuarios caseta": ["Codigo", "Nombre", "Rol", "Activo"],
}
SEED_USUARIOS = [["1234", "Sharon", "Coordinador", "SI"]]


class LocalStore:
    nombre = "local"

    def __init__(self, hoja="Hoja 1", folder="data"):
        self.hoja, self.folder = hoja, folder
        os.makedirs(folder, exist_ok=True)

    def _p(self, t):
        return os.path.join(self.folder, t.replace(" ", "_") + ".csv")

    def cols(self, t):
        return BITACORA_COLS if t == self.hoja else TABS[t]

    def load(self, t):
        if not os.path.exists(self._p(t)):
            df = pd.DataFrame(SEED_USUARIOS if t == "Usuarios caseta" else [], columns=self.cols(t))
            df.to_csv(self._p(t), index=False)
        return pd.read_csv(self._p(t), dtype=str, keep_default_na=False)

    def append(self, t, row: dict):
        df = self.load(t)
        df = pd.concat([df, pd.DataFrame([{c: row.get(c, "") for c in df.columns}])], ignore_index=True)
        df.to_csv(self._p(t), index=False)

    def update(self, t, key_col, key, changes: dict):
        df = self.load(t)
        for c, v in changes.items():
            df.loc[df[key_col] == key, c] = v
        df.to_csv(self._p(t), index=False)

    def delete(self, t, key_col, key):
        df = self.load(t)
        df[df[key_col] != key].to_csv(self._p(t), index=False)


class SheetStore:
    nombre = "sheets"

    def __init__(self, info, url, hoja="Hoja 1"):
        import gspread
        self.gs = gspread
        self.sh = gspread.service_account_from_dict(dict(info)).open_by_url(url)
        self.hoja = hoja
        self._ws, self._hdr = {}, {}

    def ws(self, t):
        if t not in self._ws:
            try:
                w = self.sh.worksheet(t)
            except self.gs.WorksheetNotFound:
                if t not in TABS:
                    nombres = ", ".join(f"«{x.title}»" for x in self.sh.worksheets())
                    raise RuntimeError(f"No encontré la hoja «{t}» en tu Bitácora. Las hojas que existen son: {nombres}. "
                                       f"Pon el nombre exacto en los Secrets como bitacora_hoja.")
                w = self.sh.add_worksheet(t, rows=500, cols=len(TABS[t]))
                rows = [TABS[t]] + (SEED_USUARIOS if t == "Usuarios caseta" else [])
                w.update(values=rows, range_name="A1")
            self._ws[t] = w
        return self._ws[t]

    def header(self, t):
        if t not in self._hdr:
            h = self.ws(t).row_values(1)
            if t == self.hoja and "Registró" not in h:
                # agrega la columna "Registró" al final sin tocar las demás
                w = self.ws(t)
                if w.col_count < len(h) + 1:
                    w.add_cols(1)
                w.update_cell(1, len(h) + 1, "Registró")
                h = h + ["Registró"]
            self._hdr[t] = h
        return self._hdr[t]

    def load(self, t):
        vals = self.ws(t).get_all_values()
        h = self.header(t)
        rows = [r + [""] * (len(h) - len(r)) for r in vals[1:]]
        return pd.DataFrame([r[:len(h)] for r in rows], columns=h)

    def append(self, t, row: dict):
        """Escribe siempre en la primera fila libre después del último ID (aunque haya huecos)."""
        from gspread.utils import rowcol_to_a1
        h, w = self.header(t), self.ws(t)
        ids = w.col_values(1)                     # columna A (ID) hasta el último valor
        r = len(ids) + 1
        if r > w.row_count:
            w.add_rows(max(100, r - w.row_count))
        rng = f"A{r}:{rowcol_to_a1(r, len(h))}"
        w.update(values=[[row.get(c, "") for c in h]], range_name=rng, value_input_option="USER_ENTERED")

    def update(self, t, key_col, key, changes: dict):
        w, h = self.ws(t), self.header(t)
        col = w.col_values(h.index(key_col) + 1)
        if key not in col:
            return
        r = col.index(key) + 1
        for c, v in changes.items():
            w.update_cell(r, h.index(c) + 1, v)

    def delete(self, t, key_col, key):
        w, h = self.ws(t), self.header(t)
        col = w.col_values(h.index(key_col) + 1)
        if key in col:
            w.delete_rows(col.index(key) + 1)


def get_store(secrets):
    import json
    keys = [k for k in ("bitacora_url", "gcp_json", "gcp_service_account") if k in secrets]
    if not keys:
        return LocalStore()  # sin Secrets: modo prueba
    if "bitacora_url" not in secrets:
        raise RuntimeError("Falta 'bitacora_url' en los Secrets (la liga de tu Bitácora Vehicular).")
    if "gcp_json" not in secrets and "gcp_service_account" not in secrets:
        raise RuntimeError("Falta 'gcp_json' en los Secrets (el contenido del archivo JSON del robot).")
    try:
        info = json.loads(secrets["gcp_json"]) if "gcp_json" in secrets else dict(secrets["gcp_service_account"])
    except Exception:
        raise RuntimeError("El 'gcp_json' de los Secrets no se pudo leer: revisa que pegaste el JSON completo entre las triples comillas.")
    try:
        return SheetStore(info, secrets["bitacora_url"], secrets.get("bitacora_hoja", "Hoja 1"))
    except Exception as e:
        raise RuntimeError(f"No pude abrir tu Bitácora. ¿La compartiste como Editor con {info.get('client_email')}? Detalle: {e}")


def casas_residentes(secrets):
    """Lista de casas de la hoja Usuarios (Aplicación CCR) para el buscador de la caseta."""
    import json
    if "residentes_url" not in secrets:
        if os.path.exists("data/residentes.csv"):
            return sorted({c for c in pd.read_csv("data/residentes.csv", dtype=str, keep_default_na=False)["Casa"] if c})
        return []
    import gspread
    info = json.loads(secrets["gcp_json"]) if "gcp_json" in secrets else dict(secrets["gcp_service_account"])
    w = gspread.service_account_from_dict(info).open_by_url(secrets["residentes_url"]).worksheet(
        secrets.get("residentes_hoja", "Usuarios"))
    vals = w.get_all_values()
    if not vals:
        return []
    h = [x.strip().lower() for x in vals[0]]
    i = h.index("casa") if "casa" in h else 2
    return sorted({r[i].strip() for r in vals[1:] if len(r) > i and r[i].strip() and r[i].strip().lower() != "caseta"},
                  key=lambda c: (c.split(" ")[0], [int(n) for n in __import__("re").findall(r"\d+", c)] or [0], c))
