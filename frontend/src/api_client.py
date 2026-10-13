"""Cliente HTTP del backend FastAPI para la app Flet.

Es síncrono a propósito: Flet ejecuta los manejadores síncronos en hilos
(https://docs.flet.dev/cookbook/async-apps), así que una petición no congela la
interfaz. `httpx.Client` es seguro entre hilos.
"""
import contextlib
import json
import os
from pathlib import Path

import httpx

URL_API = os.getenv("SIGE_API_URL", "http://127.0.0.1:8000")

# nombre visible del documento (el de main.DOCUMENTOS) -> campo multipart del backend
CAMPO_DOCUMENTO = {
    "Acta de nacimiento": "doc_acta_nacimiento",
    "CURP": "doc_curp",
    "Comprobante de domicilio": "doc_comprobante_domicilio",
    "INE": "doc_ine",
    "Certificado de preparatoria": "doc_certificado_preparatoria",
    "Certificado médico": "doc_certificado_medico",
}


class ApiError(Exception):
    """Error devuelto por la API (o de red, con status 0).

    `errores` mapea campo -> mensaje (validación); `extra` es el detalle completo.
    """

    def __init__(self, status: int, mensaje: str, errores: dict | None = None, extra: dict | None = None):
        super().__init__(mensaje)
        self.status = status
        self.mensaje = mensaje
        self.errores = errores or {}
        self.extra = extra or {}


class ApiClient:
    def __init__(self, base_url: str = URL_API):
        # Las subidas de PDF (hasta 500 MB cada uno) necesitan tiempos largos de escritura/lectura
        self._http = httpx.Client(base_url=base_url, timeout=httpx.Timeout(30.0, read=900.0, write=900.0))
        self.base_url = base_url
        self.token: str | None = None
        self.sesion_vencida = False     # lo marca un 401; la app lo revisa y regresa al login

    # ------------------------------------------------------------------
    def _request(self, metodo: str, ruta: str, **kw):
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            r = self._http.request(metodo, ruta, headers=headers, **kw)
        except httpx.ConnectError:
            raise ApiError(0, f"No se pudo conectar con el servidor ({self.base_url}).")
        except httpx.TimeoutException:
            raise ApiError(0, "El servidor tardó demasiado en responder.")
        except httpx.HTTPError as ex:
            raise ApiError(0, f"Error de red: {ex}")
        if r.is_success:
            return r.json() if r.content else None
        raise self._error(r, ruta)

    def _error(self, r: httpx.Response, ruta: str) -> ApiError:
        try:
            cuerpo = r.json()
            detalle = cuerpo.get("detail") if isinstance(cuerpo, dict) else None
        except ValueError:
            detalle = None
        if r.status_code == 401 and ruta != "/auth/login":
            self.sesion_vencida = True
            self.token = None
        if isinstance(detalle, dict):
            return ApiError(r.status_code, detalle.get("mensaje", "Error del servidor"),
                            detalle.get("errores"), detalle)
        if isinstance(detalle, str):
            return ApiError(r.status_code, detalle)
        if r.status_code == 422:
            return ApiError(422, "Los datos enviados no son válidos.")
        return ApiError(r.status_code, f"Error del servidor ({r.status_code}).")

    # ------------------------------------------------------------------
    def login(self, correo: str, password: str) -> dict:
        """Devuelve {"id_usuario", "correo", "nombre", "rol"}. 401 trae intentos_restantes
        y 423 (bloqueo) trae segundos en `ApiError.extra`."""
        datos = self._request("POST", "/auth/login", json={"correo": correo, "password": password})
        self.token = datos["token"]
        return datos["usuario"]

    def logout(self) -> None:
        if not self.token:
            return
        try:
            self._request("POST", "/auth/logout")
        finally:
            self.token = None

    def cupo(self) -> dict:
        """{"periodo", "turnos": {"Matutino": n, "Vespertino": n}, "total"}"""
        return self._request("GET", "/alumnos/cupo-ingreso")

    def verificar(self, ficha: str, curp: str) -> dict:
        """{"ficha": bool, "curp": bool} (True = ya registrada)"""
        return self._request("GET", "/alumnos/verificar", params={"ficha": ficha, "curp": curp})

    def resumen_panel(self) -> dict:
        return self._request("GET", "/panel/resumen")

    def expediente(self, q: str) -> dict:
        """Expediente por número de control o CURP. 404 si no existe."""
        return self._request("GET", "/alumnos/expediente", params={"q": q})

    def descargar_documento(self, id_documento: int, destino: Path) -> Path:
        """Descarga un PDF del servidor a `destino` por bloques (pueden pesar cientos de MB)."""
        ruta = f"/alumnos/documentos/{id_documento}"
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            with self._http.stream("GET", ruta, headers=headers) as r:
                if not r.is_success:
                    r.read()                    # en streaming hay que leer el cuerpo para poder parsear el error
                    raise self._error(r, ruta)
                with destino.open("wb") as f:
                    for bloque in r.iter_bytes(1024 * 1024):
                        f.write(bloque)
        except httpx.ConnectError:
            raise ApiError(0, f"No se pudo conectar con el servidor ({self.base_url}).")
        except httpx.TimeoutException:
            raise ApiError(0, "El servidor tardó demasiado en responder.")
        except httpx.HTTPError as ex:
            raise ApiError(0, f"Error de red: {ex}")
        return destino

    def registrar_alta(self, registro: dict) -> dict:
        """Envía el registro de FormAltas.registro(): datos en JSON y los PDF en multipart
        (se leen del disco por bloques, no se cargan completos en memoria)."""
        datos = {k: val for k, val in registro.items() if k not in ("documentos", "nombre_completo")}
        datos["fecha_nacimiento"] = registro["fecha_nacimiento"].isoformat()
        with contextlib.ExitStack() as pila:
            archivos = {}
            for doc, ruta in registro["documentos"].items():
                try:
                    f = pila.enter_context(open(ruta, "rb"))
                except OSError as ex:
                    raise ApiError(0, f"No se pudo leer «{doc}»: {ex.strerror or ex}")
                archivos[CAMPO_DOCUMENTO[doc]] = (Path(ruta).name, f, "application/pdf")
            return self._request("POST", "/alumnos", files=archivos,
                                 data={"datos": json.dumps(datos, ensure_ascii=False)})
