import flet as ft
import re

def main(page: ft.Page):
    page.title = "Proyecto Ambar - Sistema Integral de Gestión Escolar"

    # =====================================================================
    # 1. CONTROLES Y FUNCIONES DE LOGIN (Ruta: "/")
    # =====================================================================
    correo_input = ft.TextField(label="Ingresa correo electrónico", width=300)
    password_input = ft.TextField(label="Ingresa Contraseña", password=True, can_reveal_password=True, width=300)
    mensaje_salida = ft.Text(value="", color=ft.Colors.RED)

    def autenticar(e):
        correo = correo_input.value
        contrasena = password_input.value
        patron_email = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        
        if not re.match(patron_email, correo):
            mensaje_salida.value = "Formato de correo electrónico inválido"
            page.update()
            return

        if correo == "secretaria@ambar.edu" and contrasena == "admin123":
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

    boton_ingresar = ft.Button("Ingresar", on_click=autenticar)

    vista_login = ft.View(
        route="/",
        controls=[
            ft.SafeArea(
                content=ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text("Bienvenido al Sistema", size=24, weight=ft.FontWeight.BOLD),
                            correo_input,
                            password_input,
                            mensaje_salida,
                            boton_ingresar
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

    vista_secretaria = ft.View(
        route="/secretaria",
        controls=[
            ft.AppBar(
                title=ft.Text("Módulo General de Secretarias"), 
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST
            ),
            ft.SafeArea(
                content=ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text("Selecciona una opción del menú:", size=18, weight=ft.FontWeight.BOLD),
                            ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
                            ft.Row(
                                controls=[
                                    ft.Button("Altas"),
                                    ft.Button("Bajas"),
                                    ft.Button("Consultas"),
                                    ft.Button("Modificación"),
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