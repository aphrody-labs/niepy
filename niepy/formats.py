"""Décodage des formats du jeu : détection, `cfg.bin` → dict, G4TX → PNG.

Le travail réel est fait par `nie-formats` en Rust. Ce module ne fait que traverser la
frontière FFI et rendre des objets Python.
"""

from __future__ import annotations

import ctypes
import json
from typing import Any

from ._ffi import NieBytes, bibliotheque

__all__ = ["decoder", "detecter", "g4tx_vers_png", "nom_format", "prendre_octets", "version"]


def prendre_octets(tampon: NieBytes) -> bytes:
    """Copie un `NieBytes` en `bytes` Python **et libère la mémoire Rust**.

    C'est le seul point de la bibliothèque qui libère un tampon natif. Il est appelé
    exactement une fois par tampon, y compris quand celui-ci est vide : la lib traite le
    pointeur null comme un no-op, mais la copie doit quand même rendre `b""`.
    """
    if not tampon.ptr:
        return b""
    try:
        return bytes(ctypes.cast(tampon.ptr, ctypes.POINTER(ctypes.c_ubyte * tampon.len)).contents)
    finally:
        bibliotheque().nie_bytes_free_fields(tampon.ptr, tampon.len, tampon.cap)


def _vue(donnees: bytes):
    """Rend un pointeur `c_ubyte*` sur un `bytes` Python, sans copie."""
    return (ctypes.c_ubyte * len(donnees)).from_buffer_copy(donnees)


def version() -> str:
    """Version du crate `nie-ffi` chargé."""
    brut = bibliotheque().nie_version()
    return brut.decode("utf-8") if brut else "?"


def detecter(donnees: bytes) -> int:
    """Discriminant numérique stable du format d'un tampon."""
    tampon = _vue(donnees)
    return int(bibliotheque().nie_detect(tampon, len(donnees)))


def nom_format(discriminant: int) -> str:
    """Nom court d'un format, depuis son discriminant."""
    brut = bibliotheque().nie_format_name(discriminant)
    return brut.decode("utf-8") if brut else "inconnu"


def decoder(donnees: bytes) -> Any:
    """Décode un tampon par auto-détection et rend la structure Python correspondante.

    Lève `ValueError` quand le format n'est pas géré — la lib rend alors un tampon vide,
    qu'il serait trompeur de confondre avec un document vide légitime.
    """
    tampon = _vue(donnees)
    sortie = NieBytes()
    bibliotheque().nie_decode_json_out(tampon, len(donnees), ctypes.byref(sortie))
    brut = prendre_octets(sortie)
    if not brut:
        nom = nom_format(detecter(donnees))
        raise ValueError(f"format non décodable en JSON (détecté : {nom})")
    return json.loads(brut)


def g4tx_vers_png(donnees: bytes) -> bytes:
    """Décode la première texture d'un G4TX et rend les octets PNG.

    Lève `ValueError` si le tampon n'est pas un G4TX exploitable.
    """
    tampon = _vue(donnees)
    sortie = NieBytes()
    bibliotheque().nie_g4tx_to_png_out(tampon, len(donnees), ctypes.byref(sortie))
    png = prendre_octets(sortie)
    if not png:
        raise ValueError("G4TX non décodable en PNG")
    return png
