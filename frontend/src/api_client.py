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

# nombre visible del documento -> campo multipart del backend
CAMPO_DOCUMENTO = {
    "Acta de nacimiento": "doc_acta_nacimiento",
    "CURP": "doc_curp",
    "Comprobante de domicilio": "doc_comprobante_domicilio",
    "INE": "doc_ine",
    "Certificado de preparatoria": "doc_certificado_preparatoria",
    "Certificado médico": "doc_certificado_medico",
    "Constancia de situación fiscal": "doc_constancia_situacion_fiscal",
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

    def opciones_domicilio(self, codigo_postal: str) -> dict:
        """Opciones de estado, municipio y colonia almacenadas localmente para el CP."""
        return self._request("GET", f"/alumnos/domicilios/{codigo_postal}")

    def verificar(
        self,
        ficha: str = "",
        curp: str = "",
        nss: str = "",
        rfc: str = "",
        ine: str = "",
        correo: str = "",
    ) -> dict:
        """Indica si los datos identificadores ya están registrados."""
        return self._request(
            "GET",
            "/alumnos/verificar",
            params={
                "ficha": ficha, "curp": curp, "nss": nss,
                "rfc": rfc, "ine": ine, "correo": correo,
            },
        )

    def resumen_panel(self) -> dict:
        return self._request("GET", "/panel/resumen")

    def expediente(self, q: str, incluir_bajas: bool = False) -> dict:
        """Expediente por número de control o CURP. 404 si no existe."""
        return self._request(
            "GET", "/alumnos/expediente",
            params={"q": q, "incluir_bajas": incluir_bajas},
        )

    def _descargar_pdf(self, ruta: str, params: dict | None = None) -> bytes:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        started = time.perf_counter()
        try:
            response = self._http.get(
                ruta, params=params, headers=headers,
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

    def descargar_expediente(self, q: str, incluir_bajas: bool = False) -> bytes:
        """Devuelve el PDF del expediente por número de control o CURP."""
        return self._descargar_pdf(
            "/alumnos/expediente/pdf",
            {"q": q, "incluir_bajas": incluir_bajas},
        )

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

    def actualizar_documentos(self, numero_control: str, documentos: dict[str, str]) -> None:
        """Agrega o reemplaza documentos PDF del expediente usando multipart."""
        ruta = f"/alumnos/{numero_control}/documentos"
        with contextlib.ExitStack() as pila:
            archivos = {}
            for documento, path in documentos.items():
                try:
                    archivo = pila.enter_context(open(path, "rb"))
                except OSError as ex:
                    raise ApiError(0, f"No se pudo leer «{documento}»: {ex.strerror or ex}")
                archivos[CAMPO_DOCUMENTO[documento]] = (Path(path).name, archivo, "application/pdf")
            self._request("PUT", ruta, files=archivos)

    def eliminar_alumno(self, numero_control: str) -> dict:
        return self._request("DELETE", f"/alumnos/{numero_control}")

    def estado_horario(self, numero_control: str) -> dict:
        return self._request("GET", f"/horarios/alumnos/{numero_control}")

    def paquetes_horario(self, semestre: int) -> list[dict]:
        return self._request("GET", "/horarios/paquetes", params={"semestre": semestre})

    def asignar_paquete(self, numero_control: str, id_paquete: int) -> dict:
        return self._request(
            "POST",
            f"/horarios/alumnos/{numero_control}/paquete",
            json={"id_paquete": id_paquete},
        )

    def migrar_paquete(self, numero_control: str, id_paquete: int) -> dict:
        return self._request(
            "PUT",
            f"/horarios/alumnos/{numero_control}/paquete",
            json={"id_paquete": id_paquete},
        )

    def descargar_horario_alumno(self, numero_control: str) -> bytes:
        return self._descargar_pdf(f"/horarios/alumnos/{numero_control}/pdf")

    def grupos_horario(self) -> list[dict]:
        return self._request("GET", "/horarios/grupos")

    def detalle_grupo_horario(self, id_paquete: int) -> dict:
        return self._request("GET", f"/horarios/grupos/{id_paquete}")

    def lista_alumnos_grupo(self, id_paquete: int) -> dict:
        return self._request("GET", f"/horarios/grupos/{id_paquete}/alumnos")

    def descargar_lista_grupo(self, id_paquete: int) -> bytes:
        return self._descargar_pdf(f"/horarios/grupos/{id_paquete}/alumnos/pdf")

    def docentes_horario(self) -> list[dict]:
        return self._request("GET", "/horarios/docentes")

    def grupos_docente(self) -> list[dict]:
        return self._request("GET", "/horarios/docente/grupos")

    def descargar_grupos_docente(self) -> bytes:
        return self._descargar_pdf("/horarios/docente/grupos/pdf")

    def descargar_lista_alumnos_docente(self, id_grupo: int) -> bytes:
        return self._descargar_pdf(f"/horarios/docente/grupos/{id_grupo}/alumnos/pdf")

    def descargar_calificaciones_docente(self, id_grupo: int) -> bytes:
        return self._descargar_pdf(f"/horarios/docente/grupos/{id_grupo}/calificaciones/pdf")

    def guardar_calificacion_docente(
        self, id_grupo: int, numero_control: str, periodo: str, valor: int,
    ) -> dict:
        return self._request(
            "PUT",
            f"/horarios/docente/grupos/{id_grupo}/alumnos/{numero_control}/calificaciones/{periodo}",
            json={"valor": valor},
        )

    def confirmar_calificacion_final(self, id_grupo: int, numero_control: str) -> dict:
        return self._request(
            "POST",
            f"/horarios/docente/grupos/{id_grupo}/alumnos/{numero_control}/calificaciones/final",
        )

    def asignar_docente_grupo(self, id_grupo: int, id_docente: int | None) -> dict:
        return self._request(
            "PUT",
            f"/horarios/grupos/{id_grupo}/docente",
            json={"id_docente": id_docente},
        )

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

    def periodos_escolares(self) -> list[dict]:
        return self._request("GET", "/administracion/periodos")

    def guardar_periodo_escolar(
        self,
        periodo: str,
        fecha_inicio: str,
        periodo_anterior: str | None = None,
    ) -> dict:
        return self._request(
            "PUT",
            "/administracion/periodos",
            json={
                "periodo": periodo,
                "fecha_inicio": fecha_inicio,
                "periodo_anterior": periodo_anterior,
            },
        )

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
