import flet as ft
import re
import datetime

def main(page: ft.Page):
    page.title = "Proyecto Ambar - Sistema Integral de Gestión Escolar"
    patron_email = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    patron_celular = r'(744|781)\d{7}'

    # =====================================================================
    # 1. CONTROLES Y FUNCIONES DE LOGIN (Ruta: "/")
    # =====================================================================
    correo_input = ft.TextField(label="Ingresa correo electrónico", hint_text="hola", width=500)
    password_input = ft.TextField(label="Ingresa Contraseña", password=True, can_reveal_password=True, width=500)
    olvide_contraseña = ft.Text(value="Olvide contraseña", width=500, text_align=ft.TextAlign.LEFT ,color=ft.Colors.BLUE_600, style=ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE, decoration_color="#1A61E6"))

    def autenticar(e):
        correo = correo_input.value.strip()
        contrasena = password_input.value.strip()
        # Limpiar campos
        correo_input.error = None
        password_input.error = None
        
        if not re.match(patron_email, correo):
            correo_input.error = "Formato de correo electrónico inválido"
            page.update()
            return

        if contrasena == "":
            password_input.error = "Contraseña obligatoria"
            page.update()
            return
        
        if correo != "secretaria@ambar.edu":
            correo_input.error = "Ingrese un correo electronico valido"
            page.update()
            return
        if contrasena != "admin123":
            password_input.error = "Contraseña incorrecta"
            page.update()
            return
        
        page.route = "/secretaria"
        route_change()


    vista_login = ft.View(
        route="/",
        controls=[
            ft.SafeArea(
                content=ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text("Bienvenido al Sistema de Gestion Escolar", size=42, weight=ft.FontWeight.BOLD),
                            ft.Container(
                                margin=ft.Margin.only(top=30),
                                content=correo_input
                            ),
                            ft.Container(
                                margin=ft.Margin.only(top=15),
                                content=password_input
                            ),
                            ft.Container(
                                margin=ft.Margin.only(top=5),
                                content=olvide_contraseña,
                            ),
                            ft.Container(
                                margin=ft.Margin.only(top=10),
                                content=ft.Button(
                                    bgcolor="#1A61E6",
                                    icon=ft.Icons.ADD_HOME_OUTLINED,
                                    content=ft.Container(
                                        padding=ft.Padding.only(top=8, bottom=10, right=14, left=10),
                                        content= ft.Text(value="Iniciar sesión", size=16),
                                        #bgcolor="#1A61E6"
                                    ),
                                    on_click=autenticar
                                )
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=50
                )
            )
        ],
        vertical_alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER
    )

    # =====================================================================
    # 2. CONTROLES Y FUNCIONES DEL MENÚ SECRETARIA (Ruta: "/secretaria")
    # =====================================================================
    def cerrar_sesion(e):
        page.route = "/"
        # SOLUCIÓN: Llamamos a route_change para regresar al login
        route_change()

    def changeRoute(e):
        ruta = e.control.data
        page.route = ruta
        route_change()

    vista_secretaria = ft.View(
            route="/secretaria",
            controls=[
                ft.AppBar(
                    title=ft.Text("Módulo General de Secretarias"), 
                    bgcolor="#1A61E6",
                ),
                ft.SafeArea(
                    content=ft.Container(
                        content=ft.Column(
                            controls=[
                                ft.Text("Selecciona una opción del menú:", size=18, weight=ft.FontWeight.BOLD),
                                ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
                                ft.Row(
                                    controls=[
                                        ft.Button("Altas",data="/altas",on_click=changeRoute),
                                        ft.Button("Bajas",data="/bajas",on_click=changeRoute),
                                        ft.Button("Consultas",data="/consultas",on_click=changeRoute),
                                        ft.Button("Modificación",data="/modificacion",on_click=changeRoute),
                                    ],
                                    alignment=ft.MainAxisAlignment.CENTER
                                ),
                                ft.Row(
                                    controls=[
                                        ft.Button("Reinscripción"),
                                        ft.Button("Estadísticas"),
                                        ft.Button("Cambio de Campus"),
                                    ],
                                    alignment=ft.MainAxisAlignment.CENTER
                                ),
                                ft.Divider(height=40, color=ft.Colors.TRANSPARENT),
                                ft.Button("Salir (Cerrar Sesión)", on_click=cerrar_sesion)
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=15
                        ),
                        padding=40
                    )
                )
            ],
            vertical_alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )
    
    def handle_change(e):
        txtFechaNacimiento.error = None
        txtFechaNacimiento.value = e.control.value.strftime("%d/%m/%Y")
    
    def handle_dismissal():
        txtFechaNacimiento.error = "Selecciona una fecha valida"

    today = datetime.datetime.now()
    dpFechaNacimiento = ft.DatePicker(
        first_date=datetime.datetime(year=today.year - 70, month=1, day=1),
        last_date=datetime.datetime(year=today.year - 16, month=today.month, day=20),
        current_date=datetime.datetime(year=today.year - 18, month=1, day=1),
        on_change=handle_change,
        on_dismiss=handle_dismissal
    )

    #TextFields
    txtFicha = ft.TextField(label="Número de ficha", width=500, autofocus=True)
    txtApellidoPaterno = ft.TextField(label="Apellido Paterno", width=500)
    txtApellidoMaterno = ft.TextField(label="Apellido Materno", width=500)
    txtNombre = ft.TextField(label="Nombre", width=500)

    txtFechaNacimiento = ft.TextField(
        label="Date",                            # Etiqueta pequeña superior
        #value="Fecha de Nacimiento",             # Valor inicial o formateado
        read_only=True,                          # Evita que el usuario escriba directamente
        border=ft.OutlineInputBorder(),          # Aplica únicamente la línea inferior
        # icon=ft.Icons.CALENDAR_TODAY_OUTLINED,   # Icono del calendario a la izquierda
        prefix_icon=ft.Icons.CALENDAR_TODAY_OUTLINED,   # Icono del calendario a la izquierda
        suffix_icon=ft.Icons.ARROW_DROP_DOWN,    # Flecha hacia abajo a la derecha
        width=500,                               # Ancho del control
        label_style=ft.TextStyle(color=ft.Colors.GREY_600),
        on_click=lambda _: page.show_dialog(dpFechaNacimiento),
    )

    txtCurp = ft.TextField(label="Curp", width=500)
    txtIne = ft.TextField(label="INE", width=500)
    dropGenero = ft.Dropdown(label="Genero", data="genero", width=500, options=[
        ft.DropdownOption(key="masculino", text="Masculino"),
        ft.DropdownOption(key="femenino", text="Femenino"),
        ft.DropdownOption(key="no_binario", text="No binario")
    ])

    txtCp = ft.TextField(label="CP", width=500)
    txtColonia = ft.TextField(label="Colonia", width=500)
    txtCalle = ft.TextField(label="Calle", width=500)
    
    txtCelular = ft.TextField(label="Número celular", width=500)
    txtCorreo = ft.TextField(label="Correo electrónico personal", width=500)
    txtCorreoSecundario = ft.TextField(label="Correo electrónico secundario", width=500)
    txtNombrePreparatoria = ft.TextField(label="Nombre de la Preparatoria", width=500)
    txtPromedioPreparatoria = ft.TextField(label="Promedio general de la preparatoria", width=500)

    # Ventana de confirmación:
    # 1. Función para cerrar el diálogo
    def cerrar_dialogo():
        page.pop_dialog()
    # 2. Función si el usuario acepta
    def accion_continuar():
        page.route = "/secretaria"
        route_change()
        cerrar_dialogo()
    # 3. Crear el AlertDialog
    dialogo = ft.AlertDialog(
        title=ft.Text("¿Estás seguro que quieres continuar?"),
        actions=[
            ft.TextButton("Sí", on_click=accion_continuar),
            ft.TextButton("No", on_click=cerrar_dialogo),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    # 4. Función para abrir el diálogo
    def abrir_dialogo(): page.show_dialog(dialogo)

    def ValidarAltas(evt):
        # Limpiar campos
        formulario_valido = True
        campos = [
            txtFicha, txtApellidoPaterno, txtApellidoMaterno, txtNombre, 
            txtFechaNacimiento, txtCurp, txtIne, dropGenero, txtCp,
            txtColonia, txtCalle, txtCelular, txtCorreo, txtCorreoSecundario, 
            txtNombrePreparatoria, txtPromedioPreparatoria
        ]

        def validar_ficha(campo):
            if len(campo.value) != 10:
                return "El numero de ficha debe ser de 10 digitos"
            return None 
        def validar_nombre(campo, tipo="Nombre"):
            longitudNombre = len(campo.value.strip())
            if (longitudNombre < 3) or (longitudNombre > 20):
                return f"Longitud de {tipo} es invalida"
            return None
        def validar_apellido(campo):
            return validar_nombre(campo, "Apellido")
        def validar_correo(campo):
            if re.match(patron_email, campo.strip()):
                return "Formato de correo electrónico inválido"
            return None
        def validar_fechaNacimiento(campo):
            print("No esta entrando a esta funcion")
            if not campo.value:
                return "Selecciona una fecha valida"
            return None
        def validar_curp(campo):
            longitudCurp = len(campo.value)
            fechaNacimiento = "051111" #txtFechaNacimiento.value
            fechadecurp = campo.value[4:10] # CURP: Fecha de nacimiento
            if longitudCurp != 18:
                return "La longitud de curp debe ser de 15 caracteres"
            elif fechadecurp != fechaNacimiento:
                return "La fecha de nacimiento no corresponde a la seleccionada"
            return None
        def validar_ine(txtIne):
            # Patrón básico de 18 caracteres para la clave de elector del INE
            # patron = r'^[A-Z]{6}\d{6}[HMhm][A-Z]{5}\d{2}$'
            # if re.match(patron, txtIne.value.upper()):
            #     return "Formato de INE invalido"
            return None
        def validar_genero(campo):
            dropGenero.border_color = None
            genero = campo.value
            if not campo or (genero != "Masculino" or genero != "Femenino" or genero != "No binario"):
                dropGenero.border_color = ft.Colors.ERROR
                # dropGenero.label = "Selecciona un Genero valido"
            return None
        def validar_cp(campo):
            if not (campo.value.isdigit() and len(txtCp.value) == 5):
                return "Codigo Postal invalido"
            return None
        def validar_colonia(campo):
            return None
        def validar_calle(campo):
            return None
        def validar_celular(txtCel):
            if not re.fullmatch(patron_celular, txtCel.value):
                return "Número de telefono invalido. Lada aceptadas: 744 o 781"
            return     
        def validar_correo(campo):
            if not re.match(patron_email, campo.value.strip()):
                return "Formato de correo electrónico inválido"
            return None
        def validar_PromedioPreparatoria(campo):
            try:
                promedio = float(campo.value)
                if not (promedio > 0 and promedio < 100):
                    return "Ingresa un promedio del 1 al 100"
                return None
            except:
                return "Promedio Invalido"
        
        validaciones_especiales = {
            txtFicha: validar_ficha, txtApellidoPaterno: validar_apellido, 
            txtApellidoMaterno: validar_apellido, txtNombre: validar_nombre, 
            txtFechaNacimiento: validar_fechaNacimiento, txtCurp: validar_curp, 
            txtIne: validar_ine, dropGenero: validar_genero, txtCp: validar_cp,
            txtColonia: validar_colonia, txtCalle: validar_calle, txtCelular: validar_celular, 
            txtCorreo: validar_correo, txtCorreoSecundario: validar_correo, 
            txtNombrePreparatoria: validar_nombre, txtPromedioPreparatoria:validar_PromedioPreparatoria
        }
        
        for campo in campos:
            campo.error = None
            # Validacion de Campos vacios
            if not campo.value or campo.value.strip() == "":
                campo.error = "Campo obligatorio"
                formulario_valido = False
                # Campo especial para Genero
                if campo.data == "genero":
                    validar_genero(campo)
            
            # REGLA 2: Si NO está vacío, ¿tiene una validación especial asignada?
            elif campo in validaciones_especiales:
                funcion_validadora = validaciones_especiales[campo]
                mensaje_error = funcion_validadora(campo) # Ejecuta la función
                
                if mensaje_error:
                    campo.error = mensaje_error
                    formulario_valido = False

        # Actualizar pagina con todos los errores:
        page.update()

        if formulario_valido: abrir_dialogo()

    vista_altas = ft.View(
        route="/altas",
        controls=[
            ft.AppBar(
                title=ft.Text("Altas de Inscripción"), 
                bgcolor=ft.Colors.BLUE_800
            ),
            ft.SafeArea(
                expand=True, # 3. Expandir la columna
                
                content=ft.Container(                        
                    
                    content=ft.Column(
                        #expand=True, # 3. Expandir la columna
                        scroll=ft.ScrollMode.AUTO, # 4. HABILITAR EL SCROLL
                        
                        controls=[
                            ft.Container(
                                margin=10,
                                padding=10,
                                alignment=ft.Alignment.CENTER,
                                #bgcolor="#14192B6E",
                                width=600,
                                border_radius=10,
                                content=ft.Column(
                                    controls=[
                                        ft.Text("Ingrese los Datos para incribir un nuevo alumno", size=32, weight=ft.FontWeight.BOLD),
                                        ft.Divider(height=20, color=ft.Colors.TRANSPARENT), # Espacio despues del titulo
                                        txtFicha,
                                        txtNombre,
                                        txtApellidoPaterno,
                                        txtApellidoMaterno,
                                        ft.Divider(height=20, color=ft.Colors.TRANSPARENT), # Espacio despues del Nombre 
                                        txtFechaNacimiento,
                                        txtCurp,
                                        txtIne,
                                        ft.Divider(height=20, color=ft.Colors.TRANSPARENT), # Espacio despues del INE 
                                        dropGenero,
                                        txtCp,
                                        txtColonia,
                                        txtCalle,
                                        ft.Divider(height=20, color=ft.Colors.TRANSPARENT), # Espacio despues del Domicilio 
                                        txtCelular,
                                        txtCorreo,
                                        txtCorreoSecundario,
                                        txtNombrePreparatoria,
                                        txtPromedioPreparatoria,
                                        ft.Container( # Boton enviar
                                            margin=ft.Margin.only(top=30),
                                            content=ft.Button(
                                                bgcolor="#1A61E6",
                                                icon=ft.Icons.ADD_HOME_OUTLINED,
                                                content=ft.Container(
                                                    padding=ft.Padding.only(top=8, bottom=10, right=14, left=10),
                                                    content= ft.Text(value="Inscribir Alumno al sistema", size=16),
                                                ),
                                                on_click=ValidarAltas
                                            )
                                        ),
                                    ],
                                    spacing=15
                                )
                            )
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=15,
                        
                    ),
                    padding=40,
                )
            )
        ],
        vertical_alignment=ft.MainAxisAlignment.START,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER
    )

    # =====================================================================
    # 3. GESTIÓN DE RUTAS
    # =====================================================================
    def route_change(e=None):
        page.views.clear()
        # Siempre insertamos la vista base (login) debajo
        page.views.append(vista_login)
        
        # Si la ruta es secretaria, la apilamos encima
        if page.route == "/secretaria":
            page.views.append(vista_secretaria)

        if page.route =="/altas":
            page.views.append(vista_altas)
            
        page.update()

    def view_pop(e):
        if e.view is not None:
            page.views.remove(e.view)
            top_view = page.views[-1]
            page.route = top_view.route
            page.update()

    page.on_route_change = route_change
    page.on_view_pop = view_pop

    # Iniciar la aplicación
    page.route = "/"
    route_change()

if __name__ == "__main__":
    ft.run(main)