"""Acciones y presentación de documentos del expediente."""

import asyncio
from pathlib import Path

import flet as ft
from api_client import ApiError
from ambar_common import validators as v

from app_state import api
from ui.components import chip, snackbar
from ui.errors import manejar_error_api
from ui.files import descargar_pdf_y_abrir
from ui.theme import BORDER, DOCUMENTOS_MODIFICABLES, NAVY, TEXT


class DocumentosMixin:
    def ver_pdf(self, doc: dict):
        snackbar(self.page, f"Abriendo «{doc['documento']}»…")
        try:
            descargar_pdf_y_abrir(
                f"{self.datos['numero_control']}_{doc['id_documento']}.pdf",
                lambda destino: api.descargar_documento(
                    doc["id_documento"], destino, self.es_admin and self.incluir_bajas,
                ),
            )
        except ApiError as ex:
            manejar_error_api(ex, self.navegar, "/consultas", self.page)
        except OSError as ex:
            snackbar(self.page, f"No se pudo abrir el PDF: {ex}")

    async def _elegir_documento(self, documento: str):
        try:
            seleccionados = await self.picker.pick_files(
                dialog_title=f"Selecciona: {documento}",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["pdf"],
                allow_multiple=False,
            )
        except Exception as ex:
            snackbar(self.page, f"No se pudo abrir el selector de archivos: {ex}")
            return
        if not seleccionados:
            return

        archivo = seleccionados[0]
        error_pdf = v.validar_pdf(archivo.name or "", archivo.size, archivo.path)
        if error_pdf:
            snackbar(self.page, f"{documento}: {error_pdf}")
            return

        numero_control = self.datos["numero_control"]
        try:
            await asyncio.to_thread(
                api.actualizar_documentos,
                numero_control,
                {documento: archivo.path},
            )
        except ApiError as ex:
            manejar_error_api(ex, self.navegar, "/consultas", self.page)
            return

        try:
            self.datos = await asyncio.to_thread(
                api.expediente, numero_control, self.es_admin and self.incluir_bajas,
            )
        except ApiError as ex:
            manejar_error_api(
                ex, self.navegar, "/consultas", self.page,
                mostrar=lambda mensaje: snackbar(
                    self.page, f"El documento se guardó, pero no se pudo actualizar la vista: {mensaje}",
                ),
            )
            return

        self.seccion = "documentos"
        self._pintar()
        self.page.update()
        snackbar(self.page, f"«{documento}» se guardó correctamente.")

    async def descargar_pdf(self):
        if self.datos is None:
            return
        self.boton_descargar.disabled = True
        self.page.update()
        try:
            contenido = await asyncio.to_thread(
                api.descargar_expediente,
                self.datos["numero_control"],
                self.es_admin and self.incluir_bajas,
            )
            nombre = f"expediente_{self.datos['numero_control']}.pdf"
            carpeta_descargas = Path.home() / "Downloads"
            destino = await self.picker.save_file(
                dialog_title="Guardar expediente PDF",
                file_name=nombre,
                initial_directory=str(
                    carpeta_descargas if carpeta_descargas.is_dir() else Path.home()
                ),
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["pdf"],
                src_bytes=contenido,
            )
            if destino:
                snackbar(self.page, f"Expediente guardado en «{destino}».")
        except ApiError as ex:
            manejar_error_api(ex, self.navegar, "/consultas", self.page)
            return
        except OSError as ex:
            snackbar(self.page, f"No se pudo guardar el PDF: {ex}")
        except (OSError, RuntimeError, TimeoutError, ValueError) as ex:
            snackbar(self.page, f"No se pudo guardar el expediente PDF: {ex}")
        finally:
            self.boton_descargar.disabled = False
            self.page.update()

    def _documentos(self) -> ft.Control:
        def celda(contenido, expand):
            if isinstance(contenido, str):
                contenido = ft.Text(contenido, size=14, color=TEXT)
            return ft.Container(expand=expand, content=contenido)

        def encabezado(texto):
            return ft.Text(texto, size=13, weight=ft.FontWeight.BOLD, color=TEXT)

        filas = [ft.Container(
            bgcolor="#EEF2F8", border_radius=6,
            padding=ft.Padding.symmetric(horizontal=16, vertical=12),
            content=ft.Row(controls=[celda(encabezado("Documento"), 5), celda(encabezado("Estado"), 3),
                                     celda(encabezado("Acciones"), 3)]),
        )]
        for doc in self.datos["documentos"]:
            recibido = doc["estado"] == "Recibido"
            acciones = []
            if recibido:
                acciones.append(ft.TextButton(
                    "Ver PDF", style=ft.ButtonStyle(color=NAVY),
                    on_click=lambda e, d=doc: self.ver_pdf(d),
                ))
            if (
                self.modo_modificacion
                and not self.datos["eliminado"]
                and doc["documento"] in DOCUMENTOS_MODIFICABLES
            ):
                acciones.append(ft.TextButton(
                    "Cambiar PDF" if recibido else "Agregar PDF",
                    style=ft.ButtonStyle(color=NAVY),
                    on_click=lambda e, d=doc: self.page.run_task(
                        self._elegir_documento, d["documento"],
                    ),
                ))
            accion = ft.Row(spacing=0, controls=acciones) if acciones else ft.Text(
                "—", size=16, weight=ft.FontWeight.BOLD, color=TEXT,
            )
            filas.append(ft.Container(
                padding=ft.Padding.symmetric(horizontal=16, vertical=6),
                border=ft.Border.only(bottom=ft.BorderSide(1, BORDER)),
                content=ft.Row(vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=[
                    celda(doc["documento"], 5),
                    celda(ft.Row([chip(doc["estado"], recibido)]), 3),
                    celda(accion, 3),
                ]),
            ))
        return ft.Column(spacing=14, controls=[
            ft.Text("Documentos del expediente", size=19, weight=ft.FontWeight.BOLD, color=NAVY),
            ft.Column(spacing=0, controls=filas),
        ])
