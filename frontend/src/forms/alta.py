"""Student admission form and its validation workflow."""

import asyncio
import datetime
import hashlib

import flet as ft
from api_client import ApiError
from ambar_common import validators as v

from app_state import api, log
from forms.domicilio import DomicilioCampos, formatear_ficha
from ui.components import (
    crear_campo_etiquetado,
    crear_campo_texto,
    crear_tarjeta,
    estilo_boton_primario,
    estilo_boton_secundario,
    titulo_pagina,
)
from ui.theme import (
    BORDER,
    DOCUMENTOS,
    MUTED,
    NAVY,
    OK_BG,
    OK_FG,
    REQUIERE_TODOS_LOS_DOCUMENTOS,
    SOFT_BLUE,
    TEXT,
    WARN_BG,
    WARN_FG,
    WHITE,
)

class FormAltas:
    PASOS = ["Datos personales", "Datos académicos", "Documentos", "Confirmación"]

    def __init__(
        self,
        page: ft.Page,
        selector_archivos,
        al_cancelar_captura,
        al_guardar_inscripcion,
    ):
        self.page = page
        self.selector_archivos = selector_archivos
        self.al_cancelar_captura = al_cancelar_captura
        self.al_guardar_inscripcion = al_guardar_inscripcion
        self.indice_paso_actual = 0
        self.fecha_nacimiento: datetime.date | None = None
        self.documentos_seleccionados: dict[str, dict] = {}
        self.errores_por_documento: dict[str, str] = {}

        filtro_letras = ft.InputFilter(regex_string=r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ '\-]*$", allow=True,
                                       replacement_string="", unicode=True)
        filtro_alfanumerico = ft.InputFilter(regex_string=r"^[A-Za-z0-9&Ññ]*$", allow=True,
                                             replacement_string="")
        capitalizacion_mayusculas = ft.TextCapitalization.CHARACTERS
        capitalizacion_por_palabra = ft.TextCapitalization.WORDS

        self.numero_ficha = crear_campo_texto(
            "Ej. 2026-00123",
            autofocus=True,
            input_filter=ft.InputFilter(
                regex_string=r"^[0-9\-]*$",
                allow=True,
                replacement_string="",
            ),
        )
        self.numero_ficha.on_change = self._normalizar_numero_ficha_al_cambiar
        self.nombre_alumno = crear_campo_texto(
            "Ingresa el nombre o nombres",
            max_length=50,
            input_filter=filtro_letras,
            capitalization=capitalizacion_por_palabra,
        )
        self.apellido_paterno = crear_campo_texto(
            "Ingresa el apellido paterno",
            max_length=50,
            input_filter=filtro_letras,
            capitalization=capitalizacion_por_palabra,
        )
        self.apellido_materno = crear_campo_texto(
            "Ingresa el apellido materno",
            max_length=50,
            input_filter=filtro_letras,
            capitalization=capitalizacion_por_palabra,
        )
        self.selector_fecha_nacimiento = ft.DatePicker(
            first_date=datetime.datetime.combine(v.hace_anios(v.EDAD_MAXIMA), datetime.time()),
            last_date=datetime.datetime.combine(v.hace_anios(v.EDAD_MINIMA), datetime.time()),
            current_date=datetime.datetime.combine(v.hace_anios(18), datetime.time()),
            help_text="Fecha de nacimiento",
            on_change=self._actualizar_fecha_nacimiento_seleccionada,
        )
        self.campo_fecha_nacimiento = crear_campo_texto(
            "DD / MM / AAAA",
            read_only=True,
            suffix_icon=ft.Icons.CALENDAR_TODAY_OUTLINED,
        )
        self.campo_fecha_nacimiento.on_click = lambda evento: self.page.show_dialog(
            self.selector_fecha_nacimiento
        )
        self.curp = crear_campo_texto(
            "Ingresa la CURP",
            input_filter=filtro_alfanumerico,
            capitalization=capitalizacion_mayusculas,
            max_length=18,
        )
        self.rfc = crear_campo_texto(
            "Ingresa el RFC",
            input_filter=filtro_alfanumerico,
            capitalization=capitalizacion_mayusculas,
            max_length=13,
        )
        self.numero_seguro_social = crear_campo_texto(
            "Ingresa el número de seguro social",
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.NumbersOnlyInputFilter(),
            max_length=11,
        )
        self.idmex = crear_campo_texto(
            "IDMEX (OCR, 13 dígitos)",
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.NumbersOnlyInputFilter(),
            max_length=13
        )
        self.idmex.on_change = self._normalizar_idmex_al_cambiar
        self.genero = ft.Dropdown(
            hint_text="Selecciona",
            text_size=13,
            border_radius=6,
            border_color=BORDER,
            expand=True,
            options=[
                ft.DropdownOption(key=clave_genero, text=etiqueta_genero)
                for clave_genero, etiqueta_genero in v.GENEROS.items()
            ],
            on_select=self._limpiar_error_genero_al_seleccionar,
        )
        self.celular_alumno = crear_campo_texto(
            "Número de 10 dígitos",
            keyboard_type=ft.KeyboardType.PHONE,
            input_filter=ft.NumbersOnlyInputFilter(),
            max_length=10,
        )
        self.correo_alumno = crear_campo_texto(
            "Correo electrónico del alumno",
            keyboard_type=ft.KeyboardType.EMAIL,
        )
        self.domicilio = DomicilioCampos(page)

        self.nombre_preparatoria = crear_campo_texto("Nombre de la preparatoria")
        self.promedio_general = crear_campo_texto("Ej. 9.5", keyboard_type=ft.KeyboardType.NUMBER,
                           input_filter=ft.InputFilter(regex_string=r"^[0-9.,]*$", allow=True, replacement_string=""))
        self.promedio_general.on_change = self._actualizar_turno_sugerido_al_cambiar_promedio
        self.celular_contacto_emergencia = crear_campo_texto(
            "Número de 10 dígitos",
            keyboard_type=ft.KeyboardType.PHONE,
            input_filter=ft.NumbersOnlyInputFilter(),
            max_length=10,
        )
        self.correo_contacto_emergencia = crear_campo_texto(
            "Correo del contacto de emergencia",
            keyboard_type=ft.KeyboardType.EMAIL,
        )
        self.tipo_sangre = ft.Dropdown(
            hint_text="Selecciona",
            text_size=13,
            border_radius=6,
            border_color=BORDER,
            expand=True,
            options=[
                ft.DropdownOption(key=tipo_sangre, text=tipo_sangre)
                for tipo_sangre in v.TIPOS_SANGRE
            ],
            on_select=self._limpiar_error_tipo_sangre_al_seleccionar,
        )
        self.alergias = crear_campo_texto("Escribe las alergias o deja vacío si no tiene")
        self.primer_control_por_paso = {
            0: self.numero_ficha,
            1: self.nombre_preparatoria,
        }

        self.indicador_pasos = ft.Row(spacing=0)
        self.titulo_paso = ft.Text("", size=21, weight=ft.FontWeight.BOLD, color=NAVY)
        # Separar el desplazamiento del área de contenido mantiene accesibles los controles al recorrer formularios largos.
        self.contenido_paso = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=0,
                                horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.botones_navegacion = ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        self.indicador_estado = ft.Container()
        self.turno_sugerido = ft.Text("Se sugiere según el promedio", size=14, color=TEXT)
        self.contador_documentos = ft.Text(f"0 de {len(DOCUMENTOS)} documentos", size=14, color=TEXT)
        self.resumen_horario = ft.Text("Se asigna desde Consultas después del alta", size=14, color=TEXT)
        self.aviso_documentos = ft.Text("", size=13, color=ft.Colors.RED_700, visible=False)

        tarjeta_form = ft.Container(
            expand=True,
            bgcolor=WHITE,
            border=ft.Border.all(1, BORDER),
            border_radius=10,
            padding=24,
            content=ft.Column(spacing=18, horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                              controls=[self.titulo_paso, self.contenido_paso, self.botones_navegacion]),
        )
        lateral = ft.Container(
            width=340,
            content=ft.Column(spacing=20, scroll=ft.ScrollMode.AUTO,
                              horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                              controls=[self._construir_resumen_lateral(), self._construir_nota_sobre_documentos()]),
        )
        self.vista = ft.Column(expand=True, spacing=24, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, controls=[
            titulo_pagina("Inscripción de nuevo ingreso",
                          "Captura la información del alumno para iniciar su expediente."),
            self.indicador_pasos,
            ft.Row(expand=True, spacing=24, vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                   controls=[tarjeta_form, lateral]),
        ])
        self._actualizar_vista_del_formulario()

    def _construir_resumen_lateral(self) -> ft.Control:
        def construir_dato_resumen(etiqueta, valor_resumen):
            return ft.Column(spacing=3, controls=[
                ft.Text(etiqueta, size=13, color=MUTED),
                valor_resumen if isinstance(valor_resumen, ft.Control)
                else ft.Text(valor_resumen, size=14, color=TEXT),
            ])
        return crear_tarjeta(ft.Column(spacing=18, controls=[
            ft.Text("Resumen del registro", size=19, weight=ft.FontWeight.BOLD, color=NAVY),
            ft.Column(spacing=3, controls=[ft.Text("Estatus", size=13, color=MUTED), self.indicador_estado]),
            construir_dato_resumen("Número de control", "Se genera al finalizar"),
            construir_dato_resumen("Turno", self.turno_sugerido),
            construir_dato_resumen("Paquete de horario", self.resumen_horario),
            construir_dato_resumen("Expediente", self.contador_documentos),
        ]))

    def _construir_nota_sobre_documentos(self) -> ft.Control:
        return ft.Container(
            bgcolor=SOFT_BLUE,
            border_radius=10,
            padding=20,
            content=ft.Text("Los documentos se adjuntan en el paso 3 (solo PDF).", size=14, color=NAVY),
        )

    def _actualizar_indicador_estado(self, texto_estado: str, estado_correcto: bool = False):
        self.indicador_estado.bgcolor = OK_BG if estado_correcto else WARN_BG
        self.indicador_estado.border_radius = 14
        self.indicador_estado.padding = ft.Padding.symmetric(horizontal=12, vertical=4)
        self.indicador_estado.content = ft.Text(
            texto_estado,
            size=12,
            weight=ft.FontWeight.BOLD,
            color=OK_FG if estado_correcto else WARN_FG,
        )

    def _actualizar_contador_documentos(self):
        cantidad_documentos_cargados = len(self.documentos_seleccionados)
        self.contador_documentos.value = f"{cantidad_documentos_cargados} de {len(DOCUMENTOS)} documentos"

    def _actualizar_fecha_nacimiento_seleccionada(self, evento):
        fecha_seleccionada = evento.control.value
        if fecha_seleccionada is None:
            return
        self.fecha_nacimiento = (
            fecha_seleccionada.date()
            if isinstance(fecha_seleccionada, datetime.datetime)
            else fecha_seleccionada
        )
        self.campo_fecha_nacimiento.value = self.fecha_nacimiento.strftime("%d/%m/%Y")
        self.campo_fecha_nacimiento.error = None
        self._actualizar_vista_del_formulario()

    def _normalizar_numero_ficha_al_cambiar(self, evento):
        numero_ficha_formateado = formatear_ficha(self.numero_ficha.value or "")
        if self.numero_ficha.value != numero_ficha_formateado:
            self.numero_ficha.value = numero_ficha_formateado
        self.numero_ficha.error = None
        self.page.update()

    def _limpiar_error_genero_al_seleccionar(self, evento):
        self.genero.error_text = None
        self.page.update()

    def _normalizar_idmex_al_cambiar(self, evento):
        idmex_capturado = self.idmex.value or ""
        idmex_normalizado = v.normalizar_ine(idmex_capturado)
        if idmex_capturado != idmex_normalizado:
            self.idmex.value = idmex_normalizado
        self.idmex.error = None
        self.page.update()

    def _limpiar_error_tipo_sangre_al_seleccionar(self, evento):
        self.tipo_sangre.error_text = None
        self.page.update()

    def _actualizar_turno_sugerido_al_cambiar_promedio(self, evento):
        self.promedio_general.error = None
        promedio_capturado = self._obtener_texto_limpio_del_campo(self.promedio_general)
        if promedio_capturado and v.validar_promedio(promedio_capturado) is None:
            turno_sugerido = v.turno_por_promedio(
                float(promedio_capturado.replace(",", "."))
            )
            self.turno_sugerido.value = (
                f"{turno_sugerido} "
                f"(promedio {'≥' if turno_sugerido == 'Matutino' else '<'} "
                f"{v.TURNO_MATUTINO_MIN})"
            )
        else:
            self.turno_sugerido.value = "Se asigna según el promedio"
        self.page.update()

    @staticmethod
    def _calcular_hash_sha256_del_pdf(ruta_pdf: str) -> str:
        hash_pdf = hashlib.sha256()
        with open(ruta_pdf, "rb") as archivo_pdf:
            for bloque_pdf in iter(lambda: archivo_pdf.read(1024 * 1024), b""):
                hash_pdf.update(bloque_pdf)
        return hash_pdf.hexdigest()

    async def _seleccionar_y_validar_pdf(self, nombre_documento: str):
        log.info(
            "Abriendo selector de PDF (control=%s, documento=%s, ruta=%s)",
            self.selector_archivos._i,
            nombre_documento,
            self.page.route,
        )
        try:
            archivos_pdf_seleccionados = await self.selector_archivos.pick_files(
                dialog_title=f"Selecciona: {nombre_documento}",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["pdf"],
                allow_multiple=False,
            )
        except Exception as error_selector:
            log.exception(
                "Falló FilePicker.pick_files (control=%s, documento=%s, ruta=%s)",
                self.selector_archivos._i,
                nombre_documento,
                self.page.route,
            )
            self.errores_por_documento[nombre_documento] = (
                f"No se pudo abrir el selector de archivos ({error_selector})"
            )
            self._actualizar_vista_del_formulario()
            return
        if not archivos_pdf_seleccionados:
            return
        archivo_pdf_seleccionado = archivos_pdf_seleccionados[0]
        mensaje_error_pdf = v.validar_pdf(
            archivo_pdf_seleccionado.name or "",
            archivo_pdf_seleccionado.size,
            archivo_pdf_seleccionado.path,
        )
        if mensaje_error_pdf:
            self.documentos_seleccionados.pop(nombre_documento, None)
            self.errores_por_documento[nombre_documento] = mensaje_error_pdf
        else:
            ruta_pdf = archivo_pdf_seleccionado.path
            if not ruta_pdf:
                self.documentos_seleccionados.pop(nombre_documento, None)
                self.errores_por_documento[nombre_documento] = (
                    "No se pudo leer el archivo para validar si está duplicado"
                )
                self._actualizar_vista_del_formulario()
                return
            try:
                hash_pdf = await asyncio.to_thread(
                    self._calcular_hash_sha256_del_pdf,
                    ruta_pdf,
                )
                nombre_documento_duplicado = None
                for otro_nombre_documento, datos_pdf_existente in self.documentos_seleccionados.items():
                    if otro_nombre_documento == nombre_documento:
                        continue
                    hash_pdf_existente = datos_pdf_existente.get("huella")
                    if hash_pdf_existente is None:
                        hash_pdf_existente = await asyncio.to_thread(
                            self._calcular_hash_sha256_del_pdf,
                            datos_pdf_existente["path"],
                        )
                        datos_pdf_existente["huella"] = hash_pdf_existente
                    if hash_pdf == hash_pdf_existente:
                        nombre_documento_duplicado = otro_nombre_documento
                        break
            except OSError:
                log.exception("No se pudo comprobar si el PDF seleccionado está duplicado")
                self.documentos_seleccionados.pop(nombre_documento, None)
                self.errores_por_documento[nombre_documento] = (
                    "No se pudo leer el archivo para validar si está duplicado"
                )
                self._actualizar_vista_del_formulario()
                return
            if nombre_documento_duplicado:
                self.documentos_seleccionados.pop(nombre_documento, None)
                self.errores_por_documento[nombre_documento] = (
                    f"Este PDF ya está cargado en «{nombre_documento_duplicado}». "
                    "Selecciona un archivo diferente."
                )
                self._actualizar_vista_del_formulario()
                return
            self.errores_por_documento.pop(nombre_documento, None)
            self.documentos_seleccionados[nombre_documento] = {
                "nombre": archivo_pdf_seleccionado.name,
                "path": ruta_pdf,
                "size": archivo_pdf_seleccionado.size,
                "huella": hash_pdf,
            }
        self._actualizar_vista_del_formulario()

    def _quitar_pdf_seleccionado(self, nombre_documento: str):
        self.documentos_seleccionados.pop(nombre_documento, None)
        self.errores_por_documento.pop(nombre_documento, None)
        self._actualizar_vista_del_formulario()

    @staticmethod
    def _obtener_texto_limpio_del_campo(control_campo) -> str:
        return (control_campo.value or "").strip()

    def _validar_campo_obligatorio(
        self,
        control_campo: ft.TextField,
        validador=None,
        **opciones_validador,
    ) -> bool:
        valor_campo = self._obtener_texto_limpio_del_campo(control_campo)
        control_campo.error = None
        if not valor_campo:
            control_campo.error = "Campo obligatorio"
            return False
        mensaje_error_validacion = (
            validador(valor_campo, **opciones_validador)
            if validador else None
        )
        if mensaje_error_validacion:
            control_campo.error = mensaje_error_validacion
            return False
        return True

    def _validar_identificadores_unicos(self) -> bool:
        try:
            identificadores_duplicados = api.verificar(
                ficha=self._obtener_texto_limpio_del_campo(self.numero_ficha),
                curp=self._obtener_texto_limpio_del_campo(self.curp).upper(),
                nss=self._obtener_texto_limpio_del_campo(self.numero_seguro_social),
                rfc=self._obtener_texto_limpio_del_campo(self.rfc).upper(),
                ine=v.normalizar_ine(self._obtener_texto_limpio_del_campo(self.idmex)),
                correo=self._obtener_texto_limpio_del_campo(self.correo_alumno),
            )
        except ApiError:
            # La validación no se bloquea por una consulta preventiva; el backend comprueba los duplicados al guardar.
            return True
        controles_identificadores = {
            "ficha": (self.numero_ficha, "Esta ficha ya está registrada"),
            "curp": (self.curp, "Esta CURP ya está registrada"),
            "nss": (self.numero_seguro_social, "Este NSS ya está registrado"),
            "rfc": (self.rfc, "Este RFC ya está registrado"),
            "ine": (self.idmex, "Este IDMEX ya está registrado"),
            "correo": (self.correo_alumno, "Este correo personal ya está registrado"),
        }
        identificadores_sin_duplicar = True
        for nombre_identificador, (control_campo, mensaje_error) in controles_identificadores.items():
            if identificadores_duplicados.get(nombre_identificador):
                control_campo.error = mensaje_error
                identificadores_sin_duplicar = False
        return identificadores_sin_duplicar

    def validar_datos_del_paso(self, indice_paso_actual: int) -> bool:
        datos_del_paso_validos = True
        if indice_paso_actual == 0:
            datos_del_paso_validos &= self._validar_campo_obligatorio(self.numero_ficha, v.validar_ficha)
            datos_del_paso_validos &= self._validar_campo_obligatorio(self.nombre_alumno, v.validar_nombre)
            datos_del_paso_validos &= self._validar_campo_obligatorio(self.apellido_paterno, v.validar_apellido)
            datos_del_paso_validos &= self._validar_campo_obligatorio(self.apellido_materno, v.validar_apellido)

            self.campo_fecha_nacimiento.error = v.validar_fecha_nacimiento(self.fecha_nacimiento)
            fecha_nacimiento_valida = self.campo_fecha_nacimiento.error is None
            datos_del_paso_validos &= fecha_nacimiento_valida
            fecha_nacimiento_validada = self.fecha_nacimiento if fecha_nacimiento_valida else None

            datos_del_paso_validos &= self._validar_campo_obligatorio(
                self.curp,
                v.validar_curp,
                fecha=fecha_nacimiento_validada,
                apellido_paterno=self._obtener_texto_limpio_del_campo(self.apellido_paterno),
                apellido_materno=self._obtener_texto_limpio_del_campo(self.apellido_materno),
                genero=self.genero.value,
            )
            mayor_de_18 = (
                self.fecha_nacimiento is not None
                and fecha_nacimiento_valida
                and v.es_mayor_de_18(self.fecha_nacimiento)
            )
            if mayor_de_18:
                datos_del_paso_validos &= self._validar_campo_obligatorio(self.rfc, v.validar_rfc, fecha=fecha_nacimiento_validada)
            else:
                self.rfc.error = v.validar_rfc(self._obtener_texto_limpio_del_campo(self.rfc), fecha=fecha_nacimiento_validada)
            datos_del_paso_validos &= self.rfc.error is None
            datos_del_paso_validos &= self._validar_campo_obligatorio(self.numero_seguro_social, v.validar_nss)
            if mayor_de_18:
                datos_del_paso_validos &= self._validar_campo_obligatorio(self.idmex, v.validar_ine)
            else:
                idmex_normalizado = v.normalizar_ine(
                    self._obtener_texto_limpio_del_campo(self.idmex)
                )
                self.idmex.error = (
                    v.validar_ine(idmex_normalizado)
                    if idmex_normalizado else None
                )
                datos_del_paso_validos &= self.idmex.error is None
            self.genero.error_text = v.validar_genero(self.genero.value)
            datos_del_paso_validos &= self.genero.error_text is None
            datos_del_paso_validos &= self._validar_campo_obligatorio(self.celular_alumno, v.validar_celular)
            datos_del_paso_validos &= self._validar_campo_obligatorio(self.correo_alumno, v.validar_correo_con_dominio, maximo=100)
            datos_del_paso_validos &= self.domicilio.validar()
            if self.numero_ficha.error is None and self.curp.error is None:
                datos_del_paso_validos &= self._validar_identificadores_unicos()
        elif indice_paso_actual == 1:
            datos_del_paso_validos &= self._validar_campo_obligatorio(self.nombre_preparatoria, v.validar_preparatoria)
            datos_del_paso_validos &= self._validar_campo_obligatorio(self.promedio_general, v.validar_promedio)
            datos_del_paso_validos &= self._validar_campo_obligatorio(self.celular_contacto_emergencia, v.validar_celular_emergencia,
                                  celular_alumno=self._obtener_texto_limpio_del_campo(self.celular_alumno))
            datos_del_paso_validos &= self._validar_campo_obligatorio(self.correo_contacto_emergencia, v.validar_correo_emergencia,
                                  correo_alumno=self._obtener_texto_limpio_del_campo(self.correo_alumno), maximo=100)
            self.tipo_sangre.error_text = v.validar_tipo_sangre(self.tipo_sangre.value)
            datos_del_paso_validos &= self.tipo_sangre.error_text is None
            self.alergias.error = v.validar_alergias(self._obtener_texto_limpio_del_campo(self.alergias))
            datos_del_paso_validos &= self.alergias.error is None
        elif indice_paso_actual == 2:
            documentos_pendientes = [
                nombre_documento
                for nombre_documento in DOCUMENTOS
                if nombre_documento not in self.documentos_seleccionados
            ]
            if REQUIERE_TODOS_LOS_DOCUMENTOS and documentos_pendientes:
                self.aviso_documentos.value = "Falta cargar: " + ", ".join(documentos_pendientes)
                self.aviso_documentos.visible = True
                datos_del_paso_validos = False
            else:
                self.aviso_documentos.visible = False
        return bool(datos_del_paso_validos)

    async def _desplazar_formulario_al_inicio(self):
        try:
            await self.contenido_paso.scroll_to(offset=0, duration=0)
        except Exception:
            # Un control recién cambiado puede no estar montado; no bloquear el paso evita perder la captura.
            pass

    async def _enfocar_primer_campo_del_paso(self):
        primer_control_del_paso = self.primer_control_por_paso.get(self.indice_paso_actual)
        if primer_control_del_paso is not None:
            await primer_control_del_paso.focus()

    def avanzar_al_siguiente_paso(self, evento=None):
        if self.indice_paso_actual < 3 and not self.validar_datos_del_paso(self.indice_paso_actual):
            self.page.update()
            return
        if self.indice_paso_actual == 3:
            self.confirmar_inscripcion()
            return
        self.indice_paso_actual += 1
        self._actualizar_vista_del_formulario()
        self.page.run_task(self._enfocar_primer_campo_del_paso)
        self.page.run_task(self._desplazar_formulario_al_inicio)

    def regresar_al_paso_anterior(self, evento=None):
        if self.indice_paso_actual > 0:
            self.indice_paso_actual -= 1
            self._actualizar_vista_del_formulario()
            self.page.run_task(self._enfocar_primer_campo_del_paso)
            self.page.run_task(self._desplazar_formulario_al_inicio)

    def contiene_datos_capturados(self) -> bool:
        controles_de_datos = [
            self.numero_ficha,
            self.nombre_alumno,
            self.apellido_paterno,
            self.apellido_materno,
            self.curp,
            self.rfc,
            self.numero_seguro_social,
            self.idmex,
            self.celular_alumno,
            self.correo_alumno,
            self.nombre_preparatoria,
            self.promedio_general,
            self.celular_contacto_emergencia,
            self.correo_contacto_emergencia,
            self.alergias,
        ]
        return (
            any(self._obtener_texto_limpio_del_campo(control) for control in controles_de_datos)
            or self.fecha_nacimiento is not None
            or any(self.domicilio.datos().values())
            or self.tipo_sangre.value is not None
            or self.genero.value is not None
            or bool(self.documentos_seleccionados)
        )

    def cancelar_captura(self, evento=None):
        if not self.contiene_datos_capturados():
            self.al_cancelar_captura()
            return

        def confirmar_cancelacion(_evento):
            self.page.pop_dialog()
            self.al_cancelar_captura()

        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text("¿Cancelar la captura?"),
            content=ft.Text("Se perderán los datos capturados."),
            actions=[
                ft.TextButton("Sí, cancelar", on_click=confirmar_cancelacion),
                ft.TextButton(
                    "Seguir capturando",
                    on_click=lambda _evento: self.page.pop_dialog(),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        ))

    def confirmar_inscripcion(self):
        # La confirmación puede quedar abierta después de la validación; repetirla evita enviar datos obsoletos.
        for indice_paso_a_validar in (0, 1, 2):
            if not self.validar_datos_del_paso(indice_paso_a_validar):
                self.indice_paso_actual = indice_paso_a_validar
                self._actualizar_vista_del_formulario()
                return
        def confirmar_guardado(_evento):
            self.page.pop_dialog()
            try:
                self.al_guardar_inscripcion(self.construir_datos_de_inscripcion())
            except ApiError as error_api:
                self._mostrar_errores_de_api(error_api)

        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text("¿Confirmar el alta?"),
            content=ft.Text("Se registrará al alumno, se guardarán sus documentos y se generará "
                            "su número de control. El paquete de horario se asignará después "
                            "desde Consultas."),
            actions=[
                ft.TextButton("Sí", on_click=confirmar_guardado),
                ft.TextButton("No", on_click=lambda _evento: self.page.pop_dialog()),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        ))

    def _mostrar_errores_de_api(self, error_api: ApiError):
        """Mantener aquí el mapeo separa el contrato del backend de los nombres visuales."""
        controles_por_nombre_campo = {
            "ficha": (self.numero_ficha, 0), "nombre": (self.nombre_alumno, 0), "ap_paterno": (self.apellido_paterno, 0),
            "ap_materno": (self.apellido_materno, 0), "fecha_nacimiento": (self.campo_fecha_nacimiento, 0),
            "curp": (self.curp, 0), "rfc": (self.rfc, 0), "nss": (self.numero_seguro_social, 0), "ine": (self.idmex, 0),
            "celular": (self.celular_alumno, 0), "correo": (self.correo_alumno, 0),
            "preparatoria": (self.nombre_preparatoria, 1), "promedio": (self.promedio_general, 1),
            "celular_emergencia": (self.celular_contacto_emergencia, 1),
            "correo_emergencia": (self.correo_contacto_emergencia, 1), "alergias": (self.alergias, 1),
        }
        indices_pasos_con_error = []
        for nombre_campo, mensaje_error_campo in error_api.errores.items():
            if nombre_campo in controles_por_nombre_campo:
                control_campo, indice_paso_actual = controles_por_nombre_campo[nombre_campo]
                control_campo.error = mensaje_error_campo
                indices_pasos_con_error.append(indice_paso_actual)
            elif nombre_campo == "genero":
                self.genero.error_text = mensaje_error_campo
                indices_pasos_con_error.append(0)
            elif nombre_campo == "tipo_sangre":
                self.tipo_sangre.error_text = mensaje_error_campo
                indices_pasos_con_error.append(1)
            elif nombre_campo in {
                "codigo_postal", "estado", "municipio", "colonia", "calle", "numero_exterior",
            }:
                self.domicilio.marcar_errores({nombre_campo: mensaje_error_campo})
                indices_pasos_con_error.append(0)
            elif nombre_campo == "documentos":
                self.aviso_documentos.value = mensaje_error_campo
                self.aviso_documentos.visible = True
                indices_pasos_con_error.append(2)
        if indices_pasos_con_error:
            self.indice_paso_actual = min(indices_pasos_con_error)
        self._mostrar_error_de_guardado(error_api.mensaje)

    def _mostrar_error_de_guardado(self, mensaje: str):
        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text("No se pudo completar el alta"),
            content=ft.Text(mensaje),
            actions=[ft.TextButton("Entendido", on_click=lambda _: self.page.pop_dialog())],
        ))
        self._actualizar_vista_del_formulario()

    def construir_datos_de_inscripcion(self) -> dict:
        obtener_texto_campo = self._obtener_texto_limpio_del_campo
        return {
            "ficha": obtener_texto_campo(self.numero_ficha),
            "nombre": obtener_texto_campo(self.nombre_alumno),
            "ap_paterno": obtener_texto_campo(self.apellido_paterno),
            "ap_materno": obtener_texto_campo(self.apellido_materno),
            "nombre_completo": f"{obtener_texto_campo(self.nombre_alumno)} {obtener_texto_campo(self.apellido_paterno)} {obtener_texto_campo(self.apellido_materno)}",
            "fecha_nacimiento": self.fecha_nacimiento,
            "curp": obtener_texto_campo(self.curp).upper(),
            "rfc": obtener_texto_campo(self.rfc).upper() or None,
            "nss": obtener_texto_campo(self.numero_seguro_social),
            "ine": v.normalizar_ine(obtener_texto_campo(self.idmex)),
            "genero": self.genero.value,
            "celular": obtener_texto_campo(self.celular_alumno),
            "correo": obtener_texto_campo(self.correo_alumno),
            **self.domicilio.datos(),
            "preparatoria": obtener_texto_campo(self.nombre_preparatoria),
            "promedio": float(obtener_texto_campo(self.promedio_general).replace(",", ".")),
            "celular_emergencia": obtener_texto_campo(self.celular_contacto_emergencia),
            "correo_emergencia": obtener_texto_campo(self.correo_contacto_emergencia),
            "tipo_sangre": self.tipo_sangre.value,
            "alergias": obtener_texto_campo(self.alergias) or "Ninguna",
            "documentos": {
                nombre_documento: datos_documento["path"]
                for nombre_documento, datos_documento in self.documentos_seleccionados.items()
            },
        }


    def _actualizar_indicador_de_pasos(self):
        controles_indicador_pasos = []
        for indice_paso, nombre_paso in enumerate(self.PASOS):
            es_paso_actual = indice_paso == self.indice_paso_actual
            paso_completado = indice_paso < self.indice_paso_actual
            indicador_visual_paso = ft.Container(
                width=34, height=34, border_radius=17, alignment=ft.Alignment.CENTER,
                bgcolor=NAVY if (es_paso_actual or paso_completado) else WHITE,
                border=ft.Border.all(1, NAVY if (es_paso_actual or paso_completado) else BORDER),
                content=(ft.Icon(ft.Icons.CHECK, size=16, color=WHITE) if paso_completado
                         else ft.Text(str(indice_paso + 1), size=13, weight=ft.FontWeight.BOLD,
                                      color=WHITE if es_paso_actual else MUTED)),
            )
            controles_indicador_pasos.append(ft.Container(expand=1, content=ft.Row(spacing=12, controls=[
                indicador_visual_paso,
                ft.Text(nombre_paso, size=14, weight=ft.FontWeight.BOLD, color=NAVY if (es_paso_actual or paso_completado) else MUTED),
            ])))
        self.indicador_pasos.controls = controles_indicador_pasos

    @staticmethod
    def _crear_fila_de_campos(*controles) -> ft.Row:
        return ft.Row(spacing=24, vertical_alignment=ft.CrossAxisAlignment.START, controls=list(controles))

    def _crear_fila_de_documento(self, nombre_documento: str) -> ft.Control:
        datos_documento = self.documentos_seleccionados.get(nombre_documento)
        mensaje_error_documento = self.errores_por_documento.get(nombre_documento)
        if datos_documento:
            texto_estado_documento = ft.Text(
                f"{datos_documento['nombre']} · {(datos_documento['size'] or 0) / 1024:,.0f} KB",
                size=12,
                color=OK_FG,
            )
            boton_documento = ft.TextButton(
                "Quitar",
                on_click=lambda evento: self._quitar_pdf_seleccionado(nombre_documento),
            )
            icono_estado_documento = ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color=OK_FG, size=20)
        else:
            texto_estado_documento = ft.Text(
                mensaje_error_documento or "Pendiente",
                size=12,
                color=ft.Colors.RED_700 if mensaje_error_documento else MUTED,
            )
            boton_documento = ft.OutlinedButton(
                "Seleccionar PDF",
                style=estilo_boton_secundario(),
                on_click=lambda evento: self.page.run_task(
                    self._seleccionar_y_validar_pdf,
                    nombre_documento,
                ),
            )
            icono_estado_documento = ft.Icon(
                ft.Icons.ERROR_OUTLINE if mensaje_error_documento else ft.Icons.RADIO_BUTTON_UNCHECKED,
                color=ft.Colors.RED_700 if mensaje_error_documento else MUTED,
                size=20,
            )
        return ft.Container(
            padding=ft.Padding.symmetric(vertical=10),
            border=ft.Border.only(bottom=ft.BorderSide(1, BORDER)),
            content=ft.Row(vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=[
                icono_estado_documento,
                ft.Column(expand=True, spacing=2, controls=[
                    ft.Text(nombre_documento, size=14, weight=ft.FontWeight.BOLD, color=TEXT),
                    texto_estado_documento,
                ]),
                boton_documento,
            ]),
        )

    def _actualizar_campos_del_paso(self):
        crear_fila_de_campos = self._crear_fila_de_campos
        if self.indice_paso_actual == 0:
            self.titulo_paso.value = "Datos personales"
            self.contenido_paso.controls = [
                crear_fila_de_campos(crear_campo_etiquetado("Número de ficha", self.numero_ficha), crear_campo_etiquetado("Nombre(s)", self.nombre_alumno)),
                crear_fila_de_campos(crear_campo_etiquetado("Apellido paterno", self.apellido_paterno), crear_campo_etiquetado("Apellido materno", self.apellido_materno)),
                crear_fila_de_campos(crear_campo_etiquetado("Fecha de nacimiento", self.campo_fecha_nacimiento), crear_campo_etiquetado("CURP", self.curp)),
                crear_fila_de_campos(crear_campo_etiquetado(self._construir_etiqueta_rfc("RFC"), self.rfc), crear_campo_etiquetado("Número de seguro social", self.numero_seguro_social)),
                crear_fila_de_campos(crear_campo_etiquetado(self._construir_etiqueta_idmex(), self.idmex), crear_campo_etiquetado("Género", ft.Row([self.genero]))),
                crear_fila_de_campos(crear_campo_etiquetado("Teléfono celular", self.celular_alumno), crear_campo_etiquetado("Correo personal", self.correo_alumno)),
                ft.Text("Domicilio", size=16, weight=ft.FontWeight.BOLD, color=NAVY),
                *self.domicilio.controles,
            ]
        elif self.indice_paso_actual == 1:
            self.titulo_paso.value = "Datos académicos"
            self.contenido_paso.controls = [
                crear_fila_de_campos(crear_campo_etiquetado("Nombre de la preparatoria", self.nombre_preparatoria),
                  crear_campo_etiquetado("Promedio general", self.promedio_general)),
                ft.Text("Contacto de emergencia y salud", size=16, weight=ft.FontWeight.BOLD, color=NAVY),
                crear_fila_de_campos(crear_campo_etiquetado("Celular de emergencia", self.celular_contacto_emergencia),
                  crear_campo_etiquetado("Correo electrónico de emergencia", self.correo_contacto_emergencia)),
                crear_fila_de_campos(crear_campo_etiquetado("Tipo de sangre", self.tipo_sangre),
                  crear_campo_etiquetado("Alergias (opcional)", self.alergias)),
            ]
        elif self.indice_paso_actual == 2:
            self.titulo_paso.value = "Documentos"
            self.contenido_paso.controls = [
                ft.Text(f"Carga los {len(DOCUMENTOS)} documentos en formato PDF "
                        f"(máximo {v.MAX_PDF_MB} MB por archivo).", size=13, color=MUTED),
                self.aviso_documentos,
                ft.Column(spacing=0, controls=[self._crear_fila_de_documento(nombre_documento) for nombre_documento in DOCUMENTOS]),
            ]
        else:
            self.titulo_paso.value = "Confirmación"
            self.contenido_paso.controls = [
                ft.Text("Revisa la información antes de inscribir al alumno.", size=13, color=MUTED),
                self._construir_resumen_de_confirmacion(),
            ]

    def _construir_etiqueta_rfc(self, nombre_campo: str) -> str:
        if self.fecha_nacimiento is None:
            return f"{nombre_campo} (obligatorio para mayores de edad)"
        requisito = "obligatorio" if v.es_mayor_de_18(self.fecha_nacimiento) else "opcional"
        return f"{nombre_campo} ({requisito})"

    def _construir_etiqueta_idmex(self) -> str:
        if self.fecha_nacimiento is None:
            return "IDMEX (OCR, 13 dígitos)"
        requisito = "obligatorio" if v.es_mayor_de_18(self.fecha_nacimiento) else "opcional"
        return f"IDMEX (OCR, 13 dígitos, {requisito})"

    def _construir_resumen_de_confirmacion(self) -> ft.Control:
        obtener_texto_campo = self._obtener_texto_limpio_del_campo
        etiqueta_genero = v.GENEROS.get(self.genero.value, "—")
        promedio_capturado = obtener_texto_campo(self.promedio_general)
        turno_sugerido = (
            v.turno_por_promedio(float(promedio_capturado.replace(",", ".")))
            if promedio_capturado else "—"
        )
        datos_resumen = [
            ("Ficha", obtener_texto_campo(self.numero_ficha)),
            ("Nombre", f"{obtener_texto_campo(self.nombre_alumno)} {obtener_texto_campo(self.apellido_paterno)} {obtener_texto_campo(self.apellido_materno)}"),
            ("Fecha de nacimiento", self.campo_fecha_nacimiento.value or "—"),
            ("CURP", obtener_texto_campo(self.curp).upper()), ("RFC", obtener_texto_campo(self.rfc).upper()),
            ("Seguro social", obtener_texto_campo(self.numero_seguro_social)), ("IDMEX", obtener_texto_campo(self.idmex).upper()),
            ("Género", etiqueta_genero),
            ("Celular", obtener_texto_campo(self.celular_alumno)), ("Correo personal", obtener_texto_campo(self.correo_alumno)),
            ("Domicilio", self.domicilio.texto()),
            ("Preparatoria", obtener_texto_campo(self.nombre_preparatoria)), ("Promedio", promedio_capturado), ("Turno", turno_sugerido),
            ("Contacto de emergencia", f"{obtener_texto_campo(self.celular_contacto_emergencia)} · {obtener_texto_campo(self.correo_contacto_emergencia)}"),
            ("Tipo de sangre", self.tipo_sangre.value or "—"),
            ("Alergias", obtener_texto_campo(self.alergias) or "Ninguna"),
            ("Documentos PDF", f"{len(self.documentos_seleccionados)} de {len(DOCUMENTOS)} cargados"),
        ]
        return ft.Column(spacing=0, controls=[
            ft.Container(
                padding=ft.Padding.symmetric(vertical=9),
                border=ft.Border.only(bottom=ft.BorderSide(1, BORDER)),
                content=ft.Row(vertical_alignment=ft.CrossAxisAlignment.START, controls=[
                    ft.Container(width=190, content=ft.Text(clave, size=13, color=MUTED)),
                    ft.Container(expand=True, content=ft.Text(valor_resumen, size=14, color=TEXT)),
                ]),
            ) for clave, valor_resumen in datos_resumen
        ])

    def _actualizar_botones_de_navegacion(self):
        es_ultimo_paso = self.indice_paso_actual == 3
        botones_de_avance = []
        if self.indice_paso_actual > 0:
            botones_de_avance.append(ft.OutlinedButton("Atrás", style=estilo_boton_secundario(), on_click=self.regresar_al_paso_anterior))
        botones_de_avance.append(ft.FilledButton("Inscribir alumno" if es_ultimo_paso else "Siguiente",
                                       style=estilo_boton_primario(), on_click=self.avanzar_al_siguiente_paso))
        self.botones_navegacion.controls = [
            ft.OutlinedButton("Cancelar", style=estilo_boton_secundario(), on_click=self.cancelar_captura),
            ft.Row(spacing=12, controls=botones_de_avance),
        ]

    def _actualizar_vista_del_formulario(self):
        self._actualizar_indicador_de_pasos()
        self._actualizar_campos_del_paso()
        self.contenido_paso.controls = [ft.Container(
            padding=ft.Padding.only(right=16),
            content=ft.Column(spacing=16, horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                              controls=self.contenido_paso.controls),
        )]
        self._actualizar_botones_de_navegacion()
        self._actualizar_contador_documentos()
        self._actualizar_indicador_estado(
            "Lista para confirmar" if self.indice_paso_actual == 3 else "En captura",
            estado_correcto=self.indice_paso_actual == 3,
        )
        self.page.update()


def build_formulario_inscripcion(
    page: ft.Page,
    selector_archivos,
    navegar,
) -> ft.Control:
    def cancelar_captura():
        navegar("/secretaria")

    def guardar_inscripcion(datos_inscripcion: dict):
        # El progreso visible evita que una carga larga parezca una interfaz congelada.
        page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text("Registrando alumno"),
            content=ft.Row(tight=True, spacing=16, controls=[
                ft.ProgressRing(width=28, height=28),
                ft.Text("Guardando datos y subiendo documentos…"),
            ]),
        ))
        try:
            datos_inscripcion = api.registrar_alta(datos_inscripcion)
        finally:
            page.pop_dialog()
        navegar("/secretaria")
        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Alta completada con éxito"),
            content=ft.Column(tight=True, spacing=10, controls=[
                ft.Text("Número de control generado", size=13, color=MUTED),
                ft.Text(datos_inscripcion["numero_control"], size=30, weight=ft.FontWeight.BOLD, color=NAVY),
                ft.Text(f"Alumno: {datos_inscripcion['nombre_completo']}", size=14),
                ft.Text(f"Correo institucional: {datos_inscripcion['correo_institucional']}", size=14),
                ft.Text(
                    f"Turno sugerido: {datos_inscripcion['turno']} · Horario pendiente de asignación"
                    if not datos_inscripcion.get("grupo")
                    else f"Turno: {datos_inscripcion['turno']} · Grupo {datos_inscripcion['grupo']}",
                    size=14,
                ),
                *([ft.Text(datos_inscripcion["aviso_turno"], size=13, color=WARN_FG)] if datos_inscripcion.get("aviso_turno") else []),
                ft.Text("Comunica este número de control al alumno.", size=13, color=MUTED),
            ]),
            actions=[ft.TextButton("Aceptar", on_click=lambda _: page.pop_dialog())],
        ))

    return FormAltas(page, selector_archivos, cancelar_captura, guardar_inscripcion).vista
