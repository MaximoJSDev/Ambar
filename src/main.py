import flet as ft
import re

def main(page: ft.Page):
    page.title = "Proyecto Ambar - Sistema Integral de Gestión Escolar"
    print(ft.Colors)

    # =====================================================================
    # 1. CONTROLES Y FUNCIONES DE LOGIN (Ruta: "/")
    # =====================================================================
    correo_input = ft.TextField(label="Ingresa correo electrónico", width=500)
    password_input = ft.TextField(label="Ingresa Contraseña", password=True, can_reveal_password=True, width=500)
    mensaje_salida = ft.Text(value="", color=ft.Colors.RED)

    def autenticar(e):
        correo = correo_input.value
        contrasena = password_input.value
        patron_email = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        
        # if not re.match(patron_email, correo):
        #     mensaje_salida.value = "Formato de correo electrónico inválido"
        #     page.update()
        #     return

        #if correo == "secretaria@ambar.edu" and contrasena == "admin123":
        if correo == "" and contrasena == "":
            # Limpiar campos
            correo_input.value = ""
            password_input.value = ""
            mensaje_salida.value = ""
            
            # Cambiar la ruta a la sección de secretaria
            page.route = "/secretaria"
            # SOLUCIÓN: Llamamos manualmente a route_change para procesar la nueva vista
            route_change()
        else:
            mensaje_salida.value = "Correo electrónico o contraseña incorrecta"
            page.update()


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
                                margin=ft.Margin.only(top=10),
                                content=mensaje_salida
                            ),
                            ft.Container(
                                margin=ft.Margin.only(top=-10),
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
                                        ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
                                        ft.TextField(label="Número de ficha", width=500),
                                        ft.TextField(label="Apellido Paterno", width=500),
                                        ft.TextField(label="Apellido Materno", width=500),
                                        ft.TextField(label="Nombre", width=500),
                                        ft.Divider(height=20, color=ft.Colors.TRANSPARENT), # Espacio despues del Nombre 
                                        ft.TextField(label="Fecha de nacimiento", width=500),
                                        ft.TextField(label="Curp", width=500),
                                        ft.TextField(label="INE", width=500),
                                        ft.Divider(height=20, color=ft.Colors.TRANSPARENT), # Espacio despues del INE 
                                        ft.Dropdown(label="Genero", width=500, options=[
                                                ft.DropdownOption(key="masculino", text="Masculino"),
                                                ft.DropdownOption(key="femenino", text="Femenino"),
                                                ft.DropdownOption(key="no_binario", text="No binario"),
                                        ]),
                                        ft.TextField(label="CP", width=500),
                                        ft.TextField(label="Colonia", width=500),
                                        ft.TextField(label="Calle", width=500),
                                        ft.TextField(label="Número de Calle", width=500),
                                        ft.Divider(height=20, color=ft.Colors.TRANSPARENT), # Espacio despues del Domicilio 
                                        ft.TextField(label="Número celular", width=500),
                                        ft.TextField(label="Correo electrónico personal", width=500),
                                        ft.TextField(label="Correo electrónico secundario", width=500),
                                        ft.TextField(label="Nombre de la Preparatoria", width=500),
                                        ft.TextField(label="Promedio general de la preparatoria", width=500),
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