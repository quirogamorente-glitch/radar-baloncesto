#!/usr/bin/env python3
"""Radar de baloncesto: lee las fuentes de fuentes.yml y guarda las novedades
en noticias.json (y el estado de cada fuente en estado.json).

Lo ejecuta GitHub Actions cada 20 minutos. También se puede ejecutar a mano:
    pip install feedparser pyyaml requests
    python radar.py
"""
import hashlib
import html
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus

import feedparser
import requests
import yaml

BASE = Path(__file__).resolve().parent
FUENTES = BASE / "fuentes.yml"
SALIDA = BASE / "noticias.json"
ESTADO = BASE / "estado.json"

HORAS_VENTANA = 72          # noticias más antiguas que esto se descartan
MAX_NOTICIAS = 400          # tope de piezas en noticias.json
TIMEOUT = 20
AGENTE = "Mozilla/5.0 (compatible; RadarBaloncesto/1.0; +https://github.com/quirogamorente-glitch/radar-baloncesto)"
AHORA = datetime.now(timezone.utc)


def url_google(q: str) -> str:
    return f"https://news.google.com/rss/search?q={quote_plus(q + ' when:3d')}&hl=es&gl=ES&ceid=ES:es"


def limpiar(texto: str) -> str:
    texto = html.unescape(re.sub(r"<[^>]+>", " ", texto or ""))
    return re.sub(r"\s+", " ", texto).strip()


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", texto).strip()


def contiene(texto_norm: str, palabra: str) -> bool:
    p = normalizar(palabra)
    return re.search(rf"(?<![a-z0-9]){re.escape(p)}(?![a-z0-9])", texto_norm) is not None


def fecha_de(entrada):
    for campo in ("published_parsed", "updated_parsed"):
        t = entrada.get(campo)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def leer_fuente(f: dict):
    url = url_google(f["q"]) if f["tipo"] == "google" else f["url"]
    r = requests.get(url, headers={"User-Agent": AGENTE}, timeout=TIMEOUT)
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    if feed.bozo and not feed.entries:
        raise ValueError(f"no es un RSS válido ({feed.bozo_exception})")
    piezas = []
    for e in feed.entries:
        titulo = limpiar(e.get("title", ""))
        if not titulo:
            continue
        medio = f["nombre"]
        if f["tipo"] == "google":
            # Google pone el medio al final: «Titular - Medio»
            src = e.get("source") or {}
            medio = src.get("title") or medio
            sufijo = f" - {medio}"
            if titulo.endswith(sufijo):
                titulo = titulo[: -len(sufijo)].strip()
        resumen = limpiar(e.get("summary", ""))[:300]
        piezas.append({
            "titulo": titulo,
            "enlace": e.get("link", ""),
            "medio": medio,
            "resumen": "" if f["tipo"] == "google" else resumen,
            "publicada": (fecha_de(e) or AHORA).isoformat(timespec="minutes"),
            "via": f["nombre"],
            "enlace_es_google": f["tipo"] == "google",
        })
    return piezas


def main():
    conf = yaml.safe_load(FUENTES.read_text(encoding="utf-8"))
    etiquetas = conf.get("etiquetas", {})
    previas = {}
    if SALIDA.exists():
        try:
            for n in json.loads(SALIDA.read_text(encoding="utf-8")).get("noticias", []):
                previas[n["id"]] = n
        except Exception:
            pass

    estado, nuevas = [], {}
    limite = AHORA - timedelta(hours=HORAS_VENTANA)
    for f in conf.get("fuentes", []):
        try:
            piezas = leer_fuente(f)
            guardadas = 0
            for p in piezas:
                if datetime.fromisoformat(p["publicada"]) < limite:
                    continue
                texto = normalizar(f'{p["titulo"]} {p["resumen"]}')
                if f.get("filtro") and not any(contiene(texto, w) for w in f["filtro"]):
                    continue
                pid = hashlib.sha1(normalizar(p["titulo"]).encode()).hexdigest()[:12]
                p["id"] = pid
                p["etiquetas"] = sorted(k for k, ws in etiquetas.items() if any(contiene(texto, w) for w in ws))
                previa = previas.get(pid) or nuevas.get(pid)
                if previa:
                    # misma noticia vista en otra fuente: se conserva la primera y se suman vías
                    vias = set(previa.get("vias", [previa.get("via")])) | {p["via"]}
                    previa["vias"] = sorted(v for v in vias if v)
                    if previa.get("enlace_es_google") and not p["enlace_es_google"]:
                        previa["enlace"], previa["enlace_es_google"] = p["enlace"], False
                    previa["etiquetas"] = sorted(set(previa.get("etiquetas", [])) | set(p["etiquetas"]))
                    nuevas[pid] = previa
                else:
                    p["detectada"] = AHORA.isoformat(timespec="minutes")
                    p["vias"] = [p.pop("via")]
                    nuevas[pid] = p
                guardadas += 1
            estado.append({"fuente": f["nombre"], "ok": True, "leidas": len(piezas), "guardadas": guardadas})
        except Exception as ex:  # una fuente caída no para el radar
            estado.append({"fuente": f["nombre"], "ok": False, "error": str(ex)[:200]})

    # conserva lo anterior que siga dentro de la ventana aunque hoy no haya salido
    for pid, n in previas.items():
        if pid not in nuevas and datetime.fromisoformat(n["publicada"]) >= limite:
            nuevas[pid] = n

    lista = sorted(nuevas.values(), key=lambda n: n["publicada"], reverse=True)[:MAX_NOTICIAS]
    for n in lista:
        n.pop("via", None)

    salida = {
        "actualizado": AHORA.isoformat(timespec="minutes"),
        "ventana_horas": HORAS_VENTANA,
        "total": len(lista),
        "nota": "Avisos de noticias detectadas. NO están verificadas: comprobar siempre en la fuente original. "
                "Los enlaces de Google Noticias (enlace_es_google=true) no se abren directamente: buscar el titular.",
        "noticias": lista,
    }
    # solo se reescriben los archivos si cambia algo más que la hora (evita guardados vacíos)
    def cambia(ruta: Path, clave: str, valor) -> bool:
        try:
            return json.loads(ruta.read_text(encoding="utf-8")).get(clave) != valor
        except Exception:
            return True

    if cambia(SALIDA, "noticias", lista):
        SALIDA.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    resumen_estado = [{"fuente": e["fuente"], "ok": e["ok"]} for e in estado]
    try:
        antes = [{"fuente": e["fuente"], "ok": e["ok"]}
                 for e in json.loads(ESTADO.read_text(encoding="utf-8")).get("fuentes", [])]
    except Exception:
        antes = None
    if antes != resumen_estado or SALIDA.stat().st_mtime >= AHORA.timestamp() - 60:
        ESTADO.write_text(json.dumps({"actualizado": salida["actualizado"], "fuentes": estado},
                                     ensure_ascii=False, indent=1), encoding="utf-8")
    ok = sum(1 for e in estado if e["ok"])
    print(f"Fuentes OK: {ok}/{len(estado)} · noticias en ventana: {len(lista)}")
    for e in estado:
        if not e["ok"]:
            print(f"  ✗ {e['fuente']}: {e['error']}", file=sys.stderr)


if __name__ == "__main__":
    main()
