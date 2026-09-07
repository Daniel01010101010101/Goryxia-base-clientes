# Base de Clientes GoryxIA — Bogotá D.C.

Generador de una base masiva de PYMEs y negocios de Bogotá para prospección
comercial, construida **solo con fuentes públicas** y optimizada para una cosa:
conseguir la mayor cantidad posible de negocios a los que se pueda **escribir
por WhatsApp, llamar o enviar un correo hoy mismo**.

> El criterio de éxito no es el número de registros. Un negocio con celular
> vale más que veinte sin ningún canal de contacto. Todo el pipeline —las
> consultas, el enriquecimiento, el score y el orden final— está diseñado
> alrededor de esa idea.

---

## Cómo generar la base

### Opción A — en tu máquina

```bash
git clone https://github.com/Daniel01010101010101/Goryxia-base-clientes.git
cd Goryxia-base-clientes
pip install -r requirements.txt

python -m goryxia                 # toda Bogotá, todas las categorías
```

Al terminar quedan cuatro archivos en `data/`:

| Archivo | Para qué sirve |
|---|---|
| `Base_Clientes_GoryxIA.xlsx` | Hoja **Clientes** (filtros, enlaces de WhatsApp clicables) + hoja **Dashboard** con KPIs y gráficas |
| `Base_Clientes_GoryxIA.csv` | Importar a un CRM, Google Sheets o Looker Studio |
| `Base_Clientes_GoryxIA.pdf` | Informe ejecutivo + lista priorizada de llamadas |
| `clientes.geojson` | Mapa en QGIS, Google My Maps, Leaflet o Kepler |

### Opción B — en GitHub Actions (sin instalar nada)

En la pestaña **Actions** → **Generar base de clientes** → **Run workflow**.
El runner recorre Bogotá, genera los cuatro archivos y los deja como artefacto
descargable. Es la vía recomendada si no quieres montar Python localmente.

### Ejemplos de uso

```bash
python -m goryxia --prioritarias          # solo las 7 localidades priorizadas
python -m goryxia --muy-alta-prioridad    # solo odontólogos, veterinarias, restaurantes...
python -m goryxia --solo-contactables     # descarta lo que no tiene ningún contacto
python -m goryxia --localidades Bosa Kennedy --limite 5000
python -m goryxia --sin-web               # más rápido, pero rinde muchos menos celulares
python -m goryxia --minutos-web 20        # acota la fase de raspado a 20 minutos
python -m goryxia --con-google            # añade Google Places (requiere API key)
```

`python -m goryxia --help` lista todas las opciones.

---

## Qué hace por dentro

```
 1. Recolección       OpenStreetMap (Overpass) → Google Places → Datos Abiertos
 2. Deduplicación     place_id → teléfono → nombre normalizado + < 50 m
 3. Geografía         localidad y barrio reales de OSM + distancia a referencia
 4. Sitios web        raspado de las webs encontradas para sacar celular/WhatsApp
 5. Scoring           contactabilidad, presencia digital, prioridad comercial
 6. Orden             celular → WhatsApp → correo → web → sin contacto
 7. Exportación       XLSX (2 hojas) · CSV · PDF · GeoJSON
```

### Fuentes, en orden de prioridad

| # | Fuente | Estado | Qué aporta |
|---|---|---|---|
| 1 | **OpenStreetMap / Overpass API** | activa siempre | Nombre, categoría, dirección, coordenadas, teléfono, web, redes, horario. Es la columna vertebral. |
| 2 | **Google Places API** | opcional | Calificación, número de reseñas, horario verificado y teléfono confirmado. Requiere `GOOGLE_PLACES_API_KEY`. **Es de pago.** |
| 3 | **Datos Abiertos Bogotá / datos.gov.co** | configurable | Registros oficiales de establecimientos. Se activa con `GORYXIA_SOCRATA_DATASETS`. |
| 4 | **Sitios web oficiales de los negocios** | activa por defecto | La fase que **más celulares aporta**: extrae botones `wa.me`, enlaces `tel:`, correos y redes del propio sitio del negocio. |

### Cobertura

Se recorren las 20 localidades. El orden de recorrido empieza por las
priorizadas por la operación: **Bosa, Kennedy, Ciudad Bolívar, Tunjuelito,
Fontibón, Engativá y Puente Aranda**, y después el resto.

Bogotá se trocea en 127 mosaicos (~3 km de lado, más grandes en la zona rural
de Sumapaz). Cada mosaico se resuelve con **una sola consulta** que pide todas
las categorías a la vez, así que un barrido completo son ~127 peticiones a
Overpass: entre 10 y 15 minutos.

### Categorías objetivo

**Muy alta prioridad** — odontólogos, veterinarias, peluquerías, barberías,
centros estéticos, spas, gimnasios, restaurantes, cafeterías, panaderías,
consultorios, inmobiliarias, contadores, abogados y constructoras.

**Alta prioridad** — ferreterías, droguerías, papelerías, floristerías,
minimercados, tiendas de ropa y tiendas especializadas.

Cada categoría se mapea a varias etiquetas de OSM. Ver `goryxia/config.py`.

---

## Las reglas comerciales

### Score de contactabilidad

| Puntos | Condición |
|---|---|
| **100** | Celular o WhatsApp |
| **80** | Teléfono fijo **y** sitio web |
| **60** | Solo sitio web |
| **40** | Solo redes sociales |
| **30** | Solo fijo, o solo correo |
| **0** | Sin ningún contacto |

El escalón de 30 puntos es un añadido al esquema original: un fijo suelto
sigue siendo un canal de venta y no debía quedar empatado con un registro
totalmente mudo.

### WhatsApp

Todo número que cumple el plan de numeración móvil colombiano (`3XXXXXXXXX`)
se normaliza a `573XXXXXXXXX`, se marca como **WhatsApp probable — validar** y
se le genera el enlace `https://wa.me/573XXXXXXXXX`, clicable desde el Excel.

Los fijos se manejan aparte: los de 7 dígitos de la vieja numeración de Bogotá
se migran automáticamente al formato actual (`601` + los 7 dígitos).

### Presencia digital

`ALTA` = web + Facebook + Instagram · `MEDIA` = web o una red · `BAJA` = nada.

### Prioridad comercial

- **ALTA** — tiene celular/WhatsApp **y** presencia digital baja o media. Es el
  perfil ideal: se le puede escribir hoy y necesita justo lo que vendemos.
- **MEDIA** — hay fijo o página web, o tiene celular pero ya montó su presencia digital.
- **BAJA** — cadenas nacionales o multinacionales (compran de forma centralizada)
  y registros sin ningún contacto.

### Servicios sugeridos

| Giro | Paquete |
|---|---|
| Restaurantes y alimentación | Menú QR · Pedidos por WhatsApp · Chatbot IA · Página web |
| Salud, belleza y bienestar | Agenda online · CRM · Automatización de citas · Agente IA |
| Comercio | Inventario · Dashboard BI · Catálogo digital |
| Servicios profesionales | Landing page · CRM · Automatización de leads · Power BI |

El paquete se ajusta por registro: a quien no tiene web se le añade *Página
web*, a quien tiene celular *Automatización WhatsApp*, y así.

### Orden final de la base

1. Negocios con celular
2. Negocios con WhatsApp probable
3. Negocios con correo
4. Negocios con web
5. Negocios sin contacto

Dentro de cada escalón desempatan: score, prioridad comercial, localidad
priorizada, presencia digital baja (más necesidad de nuestros servicios) y
número de reseñas.

### Deduplicación

Tres pasadas, de identidad fuerte a débil: **place_id** → **teléfono
compartido** → **nombre normalizado a menos de 50 metros**.

Los duplicados no se descartan, se **fusionan**: si un registro traía el
celular y otro el sitio web, el resultado conserva ambos. Esa fusión es parte
de lo que sube la contactabilidad de la base.

---

## Configuración

Todo se ajusta por variables de entorno; ninguna es obligatoria.

| Variable | Por defecto | Para qué |
|---|---|---|
| `GOOGLE_PLACES_API_KEY` | vacío | Activa Google Places (fuente 2) |
| `GORYXIA_SOCRATA_DATASETS` | vacío | Datasets de Datos Abiertos: `dominio:dataset_id,dominio:dataset_id` |
| `SOCRATA_APP_TOKEN` | vacío | Sube el límite de peticiones de Socrata |
| `GORYXIA_REF_LAT` / `GORYXIA_REF_LON` | Plaza de Bolívar | Punto desde el que se mide *Distancia aprox. (km)* |
| `GORYXIA_WEB_WORKERS` | `8` | Hilos del raspador de sitios web |
| `GORYXIA_WEB_BUDGET_MIN` | `45` | Tope de minutos de la fase de raspado web (`0` = sin límite) |
| `GORYXIA_OVERPASS_PAUSE` | `2` | Segundos de pausa entre consultas a Overpass |
| `GORYXIA_OVERPASS_BUDGET_MIN` | `75` | Tope de minutos de la fase de OpenStreetMap (`0` = sin límite) |
| `GORYXIA_DATA_DIR` | `data/` | Carpeta de salida |

Ejemplo para medir distancias desde tu oficina en vez de desde el centro:

```bash
GORYXIA_REF_LAT=4.6486 GORYXIA_REF_LON=-74.1080 python -m goryxia
```

### Datos Abiertos: cómo conectarlo

Los identificadores de los datasets cambian con el tiempo, así que la fuente 3
no trae ninguno fijo. Busca el conjunto que te sirva en
[datos.gov.co](https://www.datos.gov.co) o
[datosabiertos.bogota.gov.co](https://datosabiertos.bogota.gov.co), copia su
identificador de cuatro-cuatro caracteres de la URL y ponlo así:

```bash
export GORYXIA_SOCRATA_DATASETS="www.datos.gov.co:abcd-1234"
python -m goryxia
```

El módulo detecta solo las columnas de nombre, dirección, teléfono, correo,
localidad y coordenadas por heurística sobre los nombres de campo, y clasifica
la categoría a partir de la actividad económica.

---

## Estructura

```
goryxia/
├── config.py           Categorías, localidades, prioridades, servicios, umbrales
├── phones.py           Plan de numeración colombiano y WhatsApp
├── geo.py              Haversine, point-in-polygon, localidad y barrio
├── models.py           El registro Negocio y el esquema de salida
├── dedupe.py           Las tres reglas de deduplicación
├── scoring.py          Score, presencia digital, prioridad y orden final
├── services.py         Servicios GoryxIA y observaciones comerciales
├── resumen.py          Métricas para el Dashboard y el PDF
├── pipeline.py         Orquestación completa
├── cli.py              Línea de comandos
├── sources/
│   ├── overpass.py         Fuente 1 — OpenStreetMap
│   ├── boundaries.py       Polígonos de localidades y nodos de barrio
│   ├── google_places.py    Fuente 2 — Google Places (opcional)
│   ├── datos_abiertos.py   Fuente 3 — Socrata
│   └── websites.py         Fuente 4 — sitios web oficiales
└── exporters/
    ├── excel.py            XLSX con hojas Clientes y Dashboard
    ├── csv_export.py       CSV UTF-8 con BOM
    ├── pdf_export.py       Informe ejecutivo + lista de llamadas
    └── geojson_export.py   Puntos para mapas
```

## Pruebas

```bash
python -m unittest discover -s tests      # 52 pruebas, no salen a la red
python scripts/generar_demo.py            # muestra de formato en data/demo/
```

`data/demo/` contiene una salida de ejemplo hecha con **datos sintéticos**
(nombres que empiezan por `DEMO`, teléfonos del rango de pruebas `300 000
XXXX`). Sirve para ver el formato de los entregables; no son negocios reales y
no deben mezclarse con la base de producción.

---

## Rendimiento y buenas prácticas

**Cuánto tarda.** Un barrido completo de Bogotá son ~127 consultas a Overpass.
Con los mirrors públicos respondiendo bien, entre 15 y 30 minutos; si están
congestionados, bastante más. El raspado web añade hasta 45 minutos.

**Las dos fases largas tienen presupuesto de tiempo** (`--minutos-overpass`,
75 por defecto, y `--minutos-web`, 45): al agotarse conservan todo lo ya
obtenido y siguen con el resto del pipeline. Nunca se pierde el trabajo hecho,
y como la caché persiste, la siguiente corrida retoma donde quedó la anterior
en vez de empezar de cero. Correr el pipeline dos o tres veces seguidas es una
forma perfectamente válida de completar la ciudad.

**Mirrors de Overpass.** El cliente rota entre tres servidores públicos y lleva
cuenta de la salud de cada uno: un `429`/`504` es congestión pasajera y se
reintenta con espera acotada, mientras que un error de TLS o DNS es permanente
y aparta ese mirror para el resto de la corrida. Sin esto, un mirror con el
certificado roto se lleva por delante horas de barrido.

**Caché.** Todo lo descargado se guarda en `data/cache/`. Volver a correr el
pipeline reutiliza lo que ya bajó, así que iterar sobre el scoring o los
exportadores es instantáneo. `--sin-cache` fuerza la descarga completa.

**Uso responsable de las fuentes.** El proyecto usa servidores públicos
gratuitos y se comporta como corresponde: pausa entre consultas, reintentos con
espera exponencial, rotación entre los mirrors de Overpass, `User-Agent`
identificable con correo de contacto, tope de bytes por página y respeto de
`robots.txt` al raspar sitios web. Si vas a hacer barridos frecuentes de toda
la ciudad, considera montar tu propia instancia de Overpass.

**Sobre los datos.** Todo sale de fuentes públicas: OpenStreetMap (ODbL, exige
atribución), portales de datos abiertos y los propios sitios web de los
negocios. Los teléfonos marcados como WhatsApp son **probables**: la columna
dice *validar* porque el número cumple el patrón de móvil colombiano, no porque
se haya comprobado que la línea tenga WhatsApp activo. Para el uso comercial de
estos datos aplica la Ley 1581 de 2012 de protección de datos personales y las
reglas de habeas data; conviene revisar el tratamiento con el área jurídica
antes de una campaña masiva.
