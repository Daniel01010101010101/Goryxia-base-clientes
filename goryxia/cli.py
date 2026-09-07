"""Interfaz de linea de comandos del generador de base de clientes."""
from __future__ import annotations

import argparse
import logging
import sys

from .config import (
    CATEGORIAS,
    GOOGLE_PLACES_HABILITADO,
    LOCALIDADES_BOGOTA,
    LOCALIDADES_PRIORITARIAS,
    Ajustes,
)
from .geo import quitar_tildes
from .pipeline import ejecutar
from .resumen import kpis


def configurar_log(verboso: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verboso else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def _resolver_localidades(pedidas: list[str] | None, solo_prioritarias: bool) -> list[str]:
    if solo_prioritarias:
        return list(LOCALIDADES_PRIORITARIAS)
    if not pedidas:
        # Orden de recorrido: primero las priorizadas por la operacion.
        resto = [l for l in LOCALIDADES_BOGOTA if l not in LOCALIDADES_PRIORITARIAS]
        return LOCALIDADES_PRIORITARIAS + resto

    canonicas = {quitar_tildes(l).lower(): l for l in LOCALIDADES_BOGOTA}
    resueltas = []
    for pedida in pedidas:
        clave = quitar_tildes(pedida).lower().strip()
        if clave in canonicas:
            resueltas.append(canonicas[clave])
        else:
            print(f"Localidad desconocida: {pedida}", file=sys.stderr)
    return resueltas


def _resolver_categorias(pedidas: list[str] | None, solo_muy_alta: bool) -> list[str]:
    if solo_muy_alta:
        return [c.nombre for c in CATEGORIAS if c.prioridad == "Muy Alta"]
    if not pedidas:
        return [c.nombre for c in CATEGORIAS]

    canonicas = {quitar_tildes(c.nombre).lower(): c.nombre for c in CATEGORIAS}
    resueltas = []
    for pedida in pedidas:
        clave = quitar_tildes(pedida).lower().strip()
        if clave in canonicas:
            resueltas.append(canonicas[clave])
        else:
            print(f"Categoria desconocida: {pedida}", file=sys.stderr)
    return resueltas


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="goryxia",
        description="Genera la base de PYMEs de Bogota para prospeccion de GoryxIA.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplos:\n"
            "  python -m goryxia                      # toda Bogota, todas las categorias\n"
            "  python -m goryxia --prioritarias       # solo las 7 localidades priorizadas\n"
            "  python -m goryxia --muy-alta-prioridad # solo categorias de muy alta prioridad\n"
            "  python -m goryxia --solo-contactables  # descarta los registros sin contacto\n"
            "  python -m goryxia --localidades Bosa Kennedy --sin-web\n"
        ),
    )
    parser.add_argument("--localidades", nargs="+", metavar="NOMBRE",
                        help="Localidades a recorrer (por defecto: todas)")
    parser.add_argument("--prioritarias", action="store_true",
                        help="Solo las 7 localidades priorizadas por la operacion")
    parser.add_argument("--categorias", nargs="+", metavar="NOMBRE",
                        help="Categorias a buscar (por defecto: todas)")
    parser.add_argument("--muy-alta-prioridad", action="store_true",
                        help="Solo las categorias de muy alta prioridad")

    parser.add_argument("--sin-overpass", action="store_true",
                        help="No consultar OpenStreetMap")
    parser.add_argument("--con-google", action="store_true",
                        help="Activar Google Places (requiere GOOGLE_PLACES_API_KEY)")
    parser.add_argument("--sin-datos-abiertos", action="store_true",
                        help="No consultar Datos Abiertos Bogota")
    parser.add_argument("--sin-web", action="store_true",
                        help="No raspar los sitios web de los negocios "
                             "(mas rapido, pero se pierden muchos celulares)")
    parser.add_argument("--max-webs", type=int, default=4000, metavar="N",
                        help="Maximo de sitios web a analizar (por defecto 4000)")
    parser.add_argument("--minutos-web", type=float, default=45.0, metavar="MIN",
                        help="Tope de tiempo de la fase de raspado web "
                             "(por defecto 45 minutos; 0 = sin limite)")
    parser.add_argument("--minutos-overpass", type=float, default=75.0, metavar="MIN",
                        help="Tope de tiempo de la fase de OpenStreetMap "
                             "(por defecto 75 minutos; 0 = sin limite)")

    parser.add_argument("--sin-cache", action="store_true",
                        help="Ignorar la cache local y volver a descargar todo")
    parser.add_argument("--limite", type=int, metavar="N",
                        help="Corta la base en los N mejores registros")
    parser.add_argument("--solo-contactables", action="store_true",
                        help="Exporta unicamente negocios con celular, fijo o correo")
    parser.add_argument("--score-minimo", type=int, default=0, metavar="N",
                        help="Descarta registros con score menor a N")
    parser.add_argument("--sin-exportar", action="store_true",
                        help="Corre el pipeline sin escribir archivos")
    parser.add_argument("-v", "--verbose", action="store_true", help="Log detallado")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)
    configurar_log(args.verbose)
    log = logging.getLogger("goryxia")

    if args.con_google and not GOOGLE_PLACES_HABILITADO:
        log.error("--con-google requiere la variable de entorno GOOGLE_PLACES_API_KEY")
        return 2

    ajustes = Ajustes(
        localidades=_resolver_localidades(args.localidades, args.prioritarias),
        categorias=_resolver_categorias(args.categorias, args.muy_alta_prioridad),
        usar_overpass=not args.sin_overpass,
        usar_google=args.con_google,
        usar_datos_abiertos=not args.sin_datos_abiertos,
        scrapear_webs=not args.sin_web,
        max_webs=args.max_webs,
        minutos_web=args.minutos_web,
        minutos_overpass=args.minutos_overpass,
        usar_cache=not args.sin_cache,
        limite=args.limite,
    )

    if not ajustes.localidades or not ajustes.categorias:
        log.error("No queda ninguna localidad o categoria valida por procesar")
        return 2

    log.info("Localidades: %s", ", ".join(ajustes.localidades))
    log.info("Categorias : %s", len(ajustes.categorias))

    resultado = ejecutar(ajustes, exportar=False)

    negocios = resultado.negocios
    if args.solo_contactables:
        antes = len(negocios)
        negocios = [n for n in negocios
                    if n.tiene_celular or n.tiene_fijo or n.tiene_correo]
        log.info("Filtro contactables: %s -> %s registros", antes, len(negocios))
    if args.score_minimo:
        antes = len(negocios)
        negocios = [n for n in negocios if n.score >= args.score_minimo]
        log.info("Filtro score >= %s: %s -> %s registros",
                 args.score_minimo, antes, len(negocios))

    if negocios is not resultado.negocios:
        from .resumen import construir
        resultado.negocios = negocios
        resultado.resumen = construir(negocios)

    if not args.sin_exportar and negocios:
        from .pipeline import exportar_todo
        resultado.archivos = exportar_todo(negocios, resultado.resumen)

    _imprimir_informe(resultado)
    return 0 if negocios else 1


def _imprimir_informe(resultado) -> None:
    resumen = resultado.resumen
    ancho = 66
    print()
    print("=" * ancho)
    print("BASE DE CLIENTES GORYXIA - BOGOTA D.C.".center(ancho))
    print("=" * ancho)
    for etiqueta, valor, comentario in kpis(resumen):
        print(f"{etiqueta:<32} {valor:>8,}".replace(",", ".") + f"   {comentario}")

    if resultado.duplicados:
        print("-" * ancho)
        print("Duplicados fusionados:",
              ", ".join(f"{k}={v}" for k, v in resultado.duplicados.items()))
    if resultado.ganancia_web:
        g = resultado.ganancia_web
        print(f"Sitios web analizados: {g.get('analizados', 0)}/{g.get('sitios', 0)} -> "
              f"+{g.get('nuevos_celulares', 0)} celulares, "
              f"+{g.get('nuevos_correos', 0)} correos, "
              f"+{g.get('nuevas_redes', 0)} redes")
        if g.get("sin_analizar_por_tiempo"):
            print(f"  {g['sin_analizar_por_tiempo']} sitios quedaron sin analizar "
                  "por el tope de tiempo (--minutos-web)")

    if resumen.por_localidad:
        print("-" * ancho)
        print("Top localidades por celulares obtenidos:")
        for localidad, total, celulares in resumen.por_localidad[:10]:
            print(f"  {localidad:<24} {total:>6} negocios   {celulares:>6} con celular")

    if resultado.archivos:
        print("-" * ancho)
        print("Archivos generados:")
        for tipo, ruta in resultado.archivos.items():
            print(f"  {tipo:<8} {ruta}")

    print("=" * ancho)
    print(f"Tiempo total: {resultado.segundos:.1f} s")
    print()


if __name__ == "__main__":
    raise SystemExit(main())
