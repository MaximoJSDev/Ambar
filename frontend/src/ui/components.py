"""Style-consistent controls shared by independently built views."""

import flet as ft

from ui.theme import BORDER, NAVY, OK_BG, OK_FG, TEXT, WARN_BG, WARN_FG, WHITE


def titulo_pagina(titulo: str, subtitulo: str) -> ft.Column:
    return ft.Column(spacing=6, controls=[
        ft.Text(titulo, size=30, weight=ft.FontWeight.BOLD, color=NAVY),
        ft.Text(subtitulo, size=15, color="#6B7A90"),
    ])


def _limpiar_error(e):
    if getattr(e.control, "error", None) or getattr(e.control, "error_text", None):
        if hasattr(e.control, "error"):
            e.control.error = None
        e.control.update()


def crear_campo_texto(texto_ayuda: str = "", **opciones) -> ft.TextField:
    return ft.TextField(
        hint_text=texto_ayuda,
        text_size=13,
        filled=True,
        fill_color=WHITE,
        border={
            ft.ControlState.DEFAULT: ft.OutlineInputBorder(
                border_radius=6,
                side=ft.BorderSide(color=BORDER),
            ),
            ft.ControlState.FOCUSED: ft.OutlineInputBorder(
                border_radius=6,
                side=ft.BorderSide(color=NAVY),
            ),
        },
        hint_style=ft.TextStyle(color="#7A8799", size=13),
        content_padding=ft.Padding.symmetric(horizontal=12, vertical=12),
        on_change=_limpiar_error,
        **opciones,
    )


def crear_campo_etiquetado(texto: str, control: ft.Control) -> ft.Column:
    return ft.Column(
        spacing=6,
        expand=1,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[ft.Text(texto, size=13, weight=ft.FontWeight.BOLD, color=TEXT), control],
    )


def crear_tarjeta(contenido: ft.Control, padding=24, **opciones) -> ft.Container:
    return ft.Container(
        content=contenido,
        bgcolor=WHITE,
        border=ft.Border.all(1, BORDER),
        border_radius=10,
        padding=padding,
        **opciones,
    )


def estilo_boton_primario() -> ft.ButtonStyle:
    return ft.ButtonStyle(
        bgcolor=NAVY,
        color=WHITE,
        shape=ft.RoundedRectangleBorder(radius=6),
        padding=ft.Padding.symmetric(horizontal=28, vertical=18),
    )


def estilo_boton_secundario() -> ft.ButtonStyle:
    return ft.ButtonStyle(
        color=NAVY,
        side=ft.BorderSide(1, NAVY),
        shape=ft.RoundedRectangleBorder(radius=6),
        padding=ft.Padding.symmetric(horizontal=28, vertical=18),
    )


def chip(texto: str, ok: bool) -> ft.Container:
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=4),
        border_radius=14,
        bgcolor=OK_BG if ok else WARN_BG,
        content=ft.Text(
            texto,
            size=12,
            weight=ft.FontWeight.BOLD,
            color=OK_FG if ok else WARN_FG,
        ),
    )


def chip_estado(estado: str) -> ft.Container:
    ok = estado == "Completada"
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=4),
        border_radius=14,
        bgcolor=OK_BG if ok else WARN_BG,
        content=ft.Text(
            estado,
            size=12,
            weight=ft.FontWeight.BOLD,
            color=OK_FG if ok else WARN_FG,
        ),
    )


def snackbar(page: ft.Page, texto: str):
    page.show_dialog(ft.SnackBar(ft.Text(texto), duration=4000))
