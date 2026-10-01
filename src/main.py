import flet as ft
import re

def main(page: ft.Page):
    page.title = "Proyecto Ambar - Sistema Integral de Gestión Escolar"
    print(ft.Colors)
    patron_email = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"

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
        #print(ruta)
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
    dpFechaNacimiento = ft.DatePicker()

    #TextFields
    txtFicha = ft.TextField(label="Número de ficha", width=500)
    txtApellidoPaterno = ft.TextField(label="Apellido Paterno", width=500)
    txtApellidoMaterno = ft.TextField(label="Apellido Materno", width=500)
    txtNombre = ft.TextField(label="Nombre", width=500)
    # txtFechaNacimiento = ft.Container(
    #     content=ft.Text("Fecha de nacimieno"),
    #     border=ft.Border(bottom=ft.BorderSide(1, ft.Colors.WHITE)),
    #     #on_click=dpFechaNacimiento
    # )
    txtFechaNacimiento = ft.TextField(
        label="Date",                            # Etiqueta pequeña superior
        value="Fecha de Nacimiento",             # Valor inicial o formateado
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
    dropGenero = ft.Dropdown(label="Genero", width=500, options=[
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
    txtNombrePreparatorio = ft.TextField(label="Nombre de la Preparatoria", width=500)
    txtPromedioPreparatoria = ft.TextField(label="Promedio general de la preparatoria", width=500)

    def ValidarAltas():
        # Limpiar campos
        campos = [
            txtFicha, txtApellidoPaterno, txtApellidoMaterno, txtNombre, 
            txtFechaNacimiento, txtCurp, txtIne, txtCp, dropGenero,
            txtColonia, txtCalle, txtCelular, txtCorreo, txtCorreoSecundario, 
            txtNombrePreparatorio, txtPromedioPreparatoria
        ]
        for campo in campos:
            campo.error = None
            # Validacion de Campos vacios
            if campo.value == "":
                campo.error = "Campo obligatoria"
                # page.update()
                # return
            page.update()

        # Validacion de longitud de nombre completo
        if (len(txtNombre.value.strip()) < 5) or (len(txtNombre.value.strip()) > 20):
            txtNombre.error = "Longitud de Nombre invalida"
        if (len(txtApellidoPaterno.value.strip()) <  5) or (len(txtApellidoPaterno.value.strip()) > 20):
            txtApellidoPaterno.error = "Longitud de Apellido Paterno invalida"
        if (len(txtApellidoMaterno.value.strip()) < 5) or (len(txtApellidoMaterno.value.strip()) > 20):
            txtApellidoMaterno.error = "Longitud de Apellido Materno invalida"

        # Validacion de formato de correo
        if not re.match(patron_email, txtCorreo.value.strip()):
            correo_input.error = "Formato de correo electrónico inválido"
            page.update()
            return
        if not re.match(patron_email, txtCorreoSecundario.value.strip()):
            correo_input.error = "Formato de correo electrónico inválido"
            page.update()
            return

        
        page.route = "/detalles_alumno"
        route_change()
    


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
                                        txtNombrePreparatorio,
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
                                    ]
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