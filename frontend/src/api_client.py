"""Cliente HTTP del backend FastAPI para la app Flet.

Es síncrono a propósito: Flet ejecuta los manejadores síncronos en hilos
(https://docs.flet.dev/cookbook/async-apps), así que una petición no congela la
interfaz. `httpx.Client` es seguro entre hilos.
"""
import contextlib
import json
import logging
import os
from pathlib import Path
import time

import httpx

from ambar_common.logging_config import configure_file_logging

URL_API = os.getenv("SIGE_API_URL", "http://127.0.0.1:8000")
log = configure_file_logging("sige.frontend", "frontend.log")

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
        started = time.perf_counter()
        try:
            r = self._http.request(metodo, ruta, headers=headers, **kw)
        except httpx.ConnectError as ex:
            log.warning(
                "API connection error method=%s path=%s error_type=%s elapsed_ms=%.1f",
                metodo, ruta, type(ex).__name__, (time.perf_counter() - started) * 1000,
            )
            raise ApiError(0, f"No se pudo conectar con el servidor ({self.base_url}).")
        except httpx.TimeoutException as ex:
            log.warning(
                "API timeout method=%s path=%s timeout_type=%s elapsed_ms=%.1f",
                metodo, ruta, type(ex).__name__, (time.perf_counter() - started) * 1000,
            )
            raise ApiError(0, "El servidor tardó demasiado en responder.")
        except httpx.HTTPError as ex:
            log.warning(
                "API HTTP error method=%s path=%s error_type=%s elapsed_ms=%.1f",
                metodo, ruta, type(ex).__name__, (time.perf_counter() - started) * 1000,
            )
            raise ApiError(0, f"Error de red: {ex}")
        elapsed_ms = (time.perf_counter() - started) * 1000
        log_method = log.warning if r.status_code >= 500 else log.info
        log_method(
            "API response method=%s path=%s status=%s elapsed_ms=%.1f",
            metodo, ruta, r.status_code, elapsed_ms,
        )
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

    def expediente(self, q: str, incluir_bajas: bool = False) -> dict:
        """Expediente por número de control o CURP. 404 si no existe."""
        return self._request(
            "GET", "/alumnos/expediente",
            params={"q": q, "incluir_bajas": incluir_bajas},
        )

    def descargar_expediente(self, q: str, incluir_bajas: bool = False) -> bytes:
        """Devuelve el PDF del expediente por número de control o CURP."""
        ruta = "/alumnos/expediente/pdf"
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        started = time.perf_counter()
        try:
            response = self._http.get(
                ruta, params={"q": q, "incluir_bajas": incluir_bajas}, headers=headers,
            )
        except httpx.ConnectError as ex:
            log.warning(
                "API connection error method=GET path=%s error_type=%s elapsed_ms=%.1f",
                ruta, type(ex).__name__, (time.perf_counter() - started) * 1000,
            )
            raise ApiError(0, f"No se pudo conectar con el servidor ({self.base_url}).")
        except httpx.TimeoutException as ex:
            log.warning(
                "API timeout method=GET path=%s timeout_type=%s elapsed_ms=%.1f",
                ruta, type(ex).__name__, (time.perf_counter() - started) * 1000,
            )
            raise ApiError(0, "El servidor tardó demasiado en responder.")
        except httpx.HTTPError as ex:
            log.warning(
                "API HTTP error method=GET path=%s error_type=%s elapsed_ms=%.1f",
                ruta, type(ex).__name__, (time.perf_counter() - started) * 1000,
            )
            raise ApiError(0, f"Error de red: {ex}")

        elapsed_ms = (time.perf_counter() - started) * 1000
        log_method = log.warning if response.status_code >= 500 else log.info
        log_method("API response method=GET path=%s status=%s elapsed_ms=%.1f",
                   ruta, response.status_code, elapsed_ms)
        if not response.is_success:
            raise self._error(response, ruta)
        return response.content

    def descargar_documento(
        self, id_documento: int, destino: Path, incluir_bajas: bool = False,
    ) -> Path:
        """Descarga un PDF del servidor a `destino` por bloques (pueden pesar cientos de MB)."""
        ruta = f"/alumnos/documentos/{id_documento}"
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            with self._http.stream(
                "GET", ruta, params={"incluir_bajas": incluir_bajas}, headers=headers,
            ) as r:
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

    def actualizar_alumno(self, numero_control: str, datos: dict) -> None:
        self._request("PUT", f"/alumnos/{numero_control}", json=datos)

    def eliminar_alumno(self, numero_control: str) -> dict:
        return self._request("DELETE", f"/alumnos/{numero_control}")

    def historial_alumno(self, numero_control: str) -> list[dict]:
        return self._request("GET", f"/alumnos/{numero_control}/historial")

    def secretarias(self) -> list[dict]:
        return self._request("GET", "/administracion/secretarias")

    def crear_secretaria(self, datos: dict) -> dict:
        return self._request("POST", "/administracion/secretarias", json=datos)

    def dar_baja_secretaria(self, id_usuario: int) -> dict:
        return self._request("DELETE", f"/administracion/secretarias/{id_usuario}")

    def crear_docente(self, datos: dict) -> dict:
        return self._request("POST", "/personal/docentes", json=datos)

    def docentes(self) -> list[dict]:
        return self._request("GET", "/personal/docentes")

    def dar_baja_docente(self, id_usuario: int) -> dict:
        return self._request("DELETE", f"/personal/docentes/{id_usuario}")

    def bitacora(self) -> list[dict]:
        return self._request("GET", "/administracion/bitacora")

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
