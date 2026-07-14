# MVP Auxilios Calidad de Vida

Herramienta Python para analizar solicitudes de auxilios desde una carpeta local,
normalizar un histórico Excel a JSON canónico, validar documentos e historial
contra reglas parametrizables, y generar una recomendación trazable para revisión
humana.

La herramienta no toma la decisión final del negocio. Produce una recomendación
auditada con estado, razones, información faltante y evidencia.

## Qué Hace

El MVP ejecuta este flujo:

```text
Carpeta local
  -> histórico Excel
  -> reglas de beneficios en CSV
  -> carpetas de solicitudes con PDFs
  -> extracción/clasificación documental
  -> normalización del histórico
  -> evaluación local de reglas
  -> recomendación APROBAR / RECHAZAR / REVISION
  -> salidas JSON, CSV y trazabilidad
```

El flujo trabaja por solicitud. Cada solicitud vive en una carpeta cuyo nombre
contiene la cédula, el beneficio y el identificador de solicitud.

## Estructura De Carpetas

La carpeta local por defecto es:

```text
data/mvp_layout/
  00_Config/
    Historico_Auxilios.xlsx
    beneficios.csv
  01_EntradaSolicitudes/
    1020304050_LENTES_EMPLEADO_SOL001/
      factura.pdf
      formula.pdf
    1090403376_GIMNASIO_SOL002/
      factura.pdf
  02_SalidaReportes/
```

La estructura se puede cambiar en `.env`, pero para el MVP se recomienda mantener
estos nombres.

## Nombre De Carpeta De Solicitud

Cada carpeta de solicitud debe seguir este patrón:

```text
cedula_codigoBeneficio_idSolicitud
```

Ejemplo:

```text
1020304050_LENTES_EMPLEADO_SOL001
```

El parser interpreta:

- `1020304050`: cédula del empleado.
- `LENTES_EMPLEADO`: código o alias del beneficio.
- `SOL001`: identificador de solicitud.

Si el beneficio viene como código numérico, el sistema intenta normalizarlo como
código de concepto de 4 dígitos.

## Configuración

El archivo principal de configuración es `.env`.

Configuración local recomendada:

```env
APP_INPUT_MODE=local_layout
LOCAL_LAYOUT_ROOT_DIR=data/mvp_layout

PROCESSING_POLICY=skip_unchanged
PROCESSING_STATE_FILENAME=processing_state.json

LAYOUT_CONFIG_DIR=00_Config
LAYOUT_REQUESTS_DIR=01_EntradaSolicitudes
LAYOUT_REPORTS_DIR=02_SalidaReportes
HISTORY_EXCEL_FILENAME=Historico_Auxilios.xlsx
BENEFITS_FILENAME=beneficios.csv

AZURE_OPENAI_ENABLED=true
COSMOS_ENABLED=false
```

Variables principales:

- `APP_INPUT_MODE`: modo de entrada. Para este MVP debe ser `local_layout`.
- `LOCAL_LAYOUT_ROOT_DIR`: carpeta raíz donde se carga toda la información.
- `LAYOUT_CONFIG_DIR`: carpeta de configuración dentro de la raíz.
- `LAYOUT_REQUESTS_DIR`: carpeta con las solicitudes.
- `LAYOUT_REPORTS_DIR`: carpeta donde se escriben los resultados.
- `HISTORY_EXCEL_FILENAME`: nombre del Excel histórico.
- `BENEFITS_FILENAME`: nombre del CSV de reglas.
- `PROCESSING_POLICY`: controla reprocesamiento.
- `AZURE_OPENAI_ENABLED`: activa el uso de IA. Para análisis documental debe estar en `true`.
- `COSMOS_ENABLED`: activa/desactiva guardado de decisiones en Cosmos DB.

## Políticas De Reprocesamiento

`PROCESSING_POLICY` controla si una solicitud vuelve a evaluarse.

Valores:

- `skip_unchanged`: procesa solicitudes nuevas o modificadas. Recomendado para uso normal.
- `skip_existing`: no reprocesa solicitudes ya vistas, aunque cambien archivos.
- `reprocess_all`: reprocesa todo. Útil cuando se cambian reglas, prompts o lógica.

El estado se guarda en:

```text
data/mvp_layout/02_SalidaReportes/processing_state.json
```

La huella de una solicitud se calcula con los nombres y contenido de sus archivos.
Si no cambió, se puede saltar para evitar reprocesamiento.

## Instalación

Desde la raíz del proyecto:

```bash
python3 -m pip install -r requirements.txt
```

Si se usa ambiente virtual:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

## Ejecución

Ejecutar el flujo completo:

```bash
PYTHONPATH=src python3 run_mvp.py
```

La consola muestra el avance:

- carpeta raíz usada,
- histórico encontrado,
- reglas encontradas,
- cantidad de registros normalizados,
- solicitudes detectadas,
- documentos analizados,
- resultado por solicitud,
- rutas finales de salida.

## Salidas

Los resultados quedan en:

```text
data/mvp_layout/02_SalidaReportes/
```

Archivos generados:

- `history_normalized.json`: histórico Excel convertido a estructura canónica.
- `recommendations.json`: recomendaciones detalladas por solicitud.
- `recommendations.csv`: reporte tabular para revisión.
- `document_analyses.json`: análisis documental por archivo.
- `skipped_requests.json`: solicitudes saltadas por política de reprocesamiento.
- `processing_state.json`: estado usado para detectar solicitudes ya procesadas.
- `decisions.jsonl`: respaldo local de decisiones cuando `COSMOS_ENABLED=false`.

`recommendations.json` y `decisions.jsonl` conservan la estructura completa,
incluyendo evidencia y objetos devueltos por IA. `recommendations.csv` es una
vista plana para revisión humana; cuando el LLM devuelve listas u objetos en
campos como `reasons` o `missing_information`, el reporte los serializa como
texto JSON dentro de la celda para que el archivo no falle ni pierda contenido.

## Estados De Recomendación

El sistema usa tres estados:

- `APROBAR`: no se detectaron incumplimientos con la información disponible.
- `RECHAZAR`: existe un incumplimiento objetivo de reglas.
- `REVISION`: falta información, hay ambigüedad, baja calidad documental, histórico no confiable o inconsistencia.

## Archivo `beneficios.csv`

Ubicación principal en el layout:

```text
data/mvp_layout/00_Config/beneficios.csv
```

También existe una copia base en:

```text
config/beneficios.csv
```

La copia usada por el flujo es la que está dentro de `data/mvp_layout/00_Config/`.

### Función Del CSV

`beneficios.csv` es la tabla de parametrización de reglas por tipo de auxilio.
El código no debería tener reglas quemadas por beneficio; las reglas operativas
deben venir desde este CSV.

El archivo se carga en:

```text
src/auxilios_mvp/benefits.py
```

Cada fila se convierte en un objeto `BenefitRule`. Luego el pipeline busca la
regla correspondiente para cada solicitud usando el código de beneficio extraído
del nombre de la carpeta.

Ejemplo:

```text
1020304050_GIMNASIO_SOL001
```

El sistema toma `GIMNASIO`, busca esa clave en las reglas cargadas y usa esa
configuración para evaluar la solicitud.

### Columnas Del CSV

Columnas actuales:

- `beneficio_codigo`: código funcional del auxilio. Ejemplo: `GIMNASIO`.
- `beneficio_nombre`: nombre legible del auxilio.
- `concepto_codigo`: código de concepto asociado al histórico o nómina.
- `aliases`: nombres alternativos separados por `;` o `,`.
- `aplica_beneficiario`: indica si la validación debe considerar beneficiario.
- `documentos_esperados`: tipos documentales requeridos.
- `vigencia_factura_meses`: vigencia máxima permitida para factura.
- `vigencia_formula_meses`: vigencia máxima permitida para fórmula médica.
- `periodicidad_meses`: periodo de restricción para otorgamientos previos.
- `cantidad_maxima_periodo`: cantidad máxima permitida dentro del periodo.
- `requiere_historico`: indica si el histórico es obligatorio para decidir.
- `criterios_aceptacion`: criterios textuales de aprobación.
- `criterios_rechazo`: criterios textuales de rechazo.
- `criterios_revision_manual`: criterios textuales para revisión.

Columnas opcionales soportadas aunque no estén en el CSV actual:

- `tope_monto`
- `monto_maximo`
- `valor_maximo`

Si se agrega alguna de esas columnas, el evaluador valida el monto detectado en
los soportes contra ese tope.

### Cómo Se Usa En La Evaluación

El evaluador local usa el CSV para:

- validar que el beneficio exista;
- identificar documentos obligatorios;
- decidir si debe buscar beneficiario;
- validar vigencia de factura;
- validar vigencia de fórmula médica;
- cruzar histórico por empleado;
- cruzar histórico por beneficiario cuando aplique;
- validar periodicidad;
- validar cantidad máxima en el periodo;
- validar tope de monto si está parametrizado;
- incluir criterios del beneficio en la evidencia.

El resultado de cada regla queda en `rules_evaluated` dentro de
`recommendations.json`.

Ejemplo de evidencia:

```json
{
  "rule": "vigencia_factura",
  "status": "RECHAZAR",
  "reason": "El documento supera la vigencia maxima configurada de 3 meses.",
  "evidence": {
    "fecha": "2025-01-01",
    "edad_meses": 18,
    "maximo_meses": 3
  }
}
```

## Histórico Excel

Ubicación esperada:

```text
data/mvp_layout/00_Config/Historico_Auxilios.xlsx
```

El histórico puede tener formatos variables. El sistema intenta normalizarlo a
campos canónicos.

La normalización está en:

```text
src/auxilios_mvp/excel_history.py
```

Campos canónicos principales:

- `employee_id`
- `employee_name`
- `case_id`
- `benefit_code`
- `benefit_name`
- `beneficiary_id`
- `beneficiary_name`
- `relationship`
- `grant_date`
- `attention_date`
- `invoice_amount`
- `recognized_amount`
- `amount`
- `balance`
- `institution`
- `observations`
- `support_type`
- `payroll_concept`
- `status`
- `source_sheet`
- `source_row`

### Cómo Se Normaliza

El sistema:

1. Lee todas las hojas del Excel.
2. Detecta la fila de encabezado dentro de las primeras filas.
3. Evalúa nombres de columnas y muestras de datos.
4. Mapea columnas del Excel a campos canónicos.
5. Omite hojas que no parecen histórico transaccional.
6. Genera `history_normalized.json`.

Si `AZURE_OPENAI_ENABLED=true`, el prompt `mapear_historico_excel.txt` puede
ayudar a mejorar el mapeo. Si está en `false`, el sistema solo puede usar
inferencia local para esta normalización del histórico.

## Análisis Documental

El análisis documental está en:

```text
src/auxilios_mvp/document_analyzer.py
src/auxilios_mvp/document_media.py
```

El flujo actual requiere IA:

1. Prepara el archivo con `document_media.py`.
2. Si es PDF, renderiza las primeras páginas como imágenes con PyMuPDF.
3. Si el PDF tiene texto extraíble, lo adjunta como contexto adicional.
4. Envía imágenes y texto al prompt `clasificar_documentos.txt`.
4. La IA clasifica semánticamente el soporte, sin depender de palabras clave
   exactas ni nombres de campos fijos:
   - `factura`
   - `formula_medica`
   - `certificado_eps`
   - `certificado_escolar`
   - `soporte_pago`
   - `otro`
5. Después llama `extraer_datos_documento.txt` con el mismo contenido multimodal
   para extraer datos estructurados
   con criterio semántico:
   - emisor,
   - número de documento,
   - fechas,
   - identificaciones,
   - beneficiario,
   - conceptos,
   - montos,
   - banderas de calidad,
   - evidencia auditable.
6. Si Azure OpenAI no está configurado, el flujo se detiene con un error claro.

Ya no existe clasificación local por palabras clave dentro del analizador
documental.

Nota importante: para que el análisis documental funcione hay que tener
`AZURE_OPENAI_ENABLED=true` y configurar endpoint, API key y deployment.

## Evaluador Local De Reglas

La evaluación principal está en:

```text
src/auxilios_mvp/recommendation.py
```

Evalúa estas reglas:

- `documentos_requeridos`
- `calidad_documental`
- `confianza_extraccion`
- `historico_disponible`
- `periodicidad_empleado`
- `beneficiario_requerido`
- `periodicidad_beneficiario`
- `vigencia_factura`
- `vigencia_formula_medica`
- `tope_monto`

### Criterio De Estado Final

El estado final se calcula así:

1. Si alguna regla queda en `RECHAZAR`, la recomendación final es `RECHAZAR`.
2. Si no hay rechazo pero alguna regla queda en `REVISION`, la recomendación final es `REVISION`.
3. Si todas las reglas evaluadas cumplen, la recomendación final es `APROBAR`.

Esto evita aprobar automáticamente solicitudes con información incompleta.

## Prompts `.txt`

Los prompts están en:

```text
prompts/
```

Importante: los prompts se usan cuando `AZURE_OPENAI_ENABLED=true`.
Para este MVP, el análisis documental requiere:

```env
AZURE_OPENAI_ENABLED=true
```

Si Azure OpenAI no está configurado, el flujo se detiene antes de analizar
documentos.

### `prompts/mapear_historico_excel.txt`

Función:

Ayuda a mapear columnas del Excel histórico a campos canónicos cuando el formato
del Excel no es estándar.

Se usa en:

```text
src/auxilios_mvp/excel_history.py
```

Entrada que recibe:

- nombres de columnas,
- muestras de filas,
- mapeo inicial inferido por heurísticas,
- lista de campos canónicos esperados.

Salida esperada:

Un JSON con una lista de columnas mapeadas:

```json
{
  "mapping": [
    {
      "canonical_field": "employee_id",
      "source_column": "Cedula",
      "confidence": 0.9,
      "reason": "La columna contiene la cédula del empleado"
    }
  ],
  "warnings": []
}
```

Si la IA está apagada, este prompt no se ejecuta.

### `prompts/extraer_datos_documento.txt`

Función:

Extrae datos estructurados desde documentos de soporte.

Se usa en:

```text
src/auxilios_mvp/document_analyzer.py
```

Entrada que recibe:

- nombre del archivo,
- tipo documental clasificado por IA,
- resultado de `clasificar_documentos.txt`,
- imágenes renderizadas del PDF o imagen original,
- texto extraído del PDF cuando existe,
- tipos documentales soportados.

Salida esperada:

```json
{
  "document_type": "factura",
  "issuer_name": "Proveedor",
  "issuer_id": "900000000",
  "document_number": "FV-123",
  "issue_date": "2026-07-01",
  "employee_id": "1020304050",
  "employee_name": "Nombre",
  "beneficiary_id": null,
  "beneficiary_name": null,
  "concepts": ["gimnasio"],
  "total_amount": 120000,
  "quality_flags": [],
  "confidence": 0.85,
  "evidence": []
}
```

Si la IA está apagada o incompleta, este prompt no se ejecuta y el flujo falla
de forma explícita. No hay extractor documental local por expresiones regulares.

### `prompts/generar_recomendacion.txt`

Función:

Permite que IA ayude a redactar o complementar la recomendación, pero sin
contradecir las reglas locales.

Se usa en:

```text
src/auxilios_mvp/recommendation.py
```

Entrada que recibe:

- solicitud,
- regla del beneficio,
- documentos analizados,
- `rules_evaluated`,
- recomendación inicial local.

Regla clave:

Si una regla local está en `RECHAZAR`, la IA no debe convertirla en `APROBAR`.
Si una regla local está en `REVISION`, la IA debe mantener revisión salvo que
haya evidencia clara para resolver la excepción.

La respuesta del LLM puede traer `reasons`, `missing_information` y `evidence`
como texto simple o como objetos estructurados. `recommendation.py` normaliza
esas salidas antes de guardarlas para que el JSON y el CSV sean estables.

Si la IA está apagada, este prompt no se ejecuta.

### `prompts/clasificar_documentos.txt`

Función:

Clasificar documentos por tipo documental usando IA:

- `factura`
- `formula_medica`
- `certificado_eps`
- `certificado_escolar`
- `soporte_pago`
- `otro`

Estado actual:

Este prompt sí se usa directamente en `document_analyzer.py` cuando
`AZURE_OPENAI_ENABLED=true`. Es la primera llamada de IA del análisis documental.
Su objetivo es evitar que la clasificación dependa de palabras clave rígidas,
porque los proveedores pueden escribir con estructuras, nombres y formatos
distintos.

La salida de este prompt alimenta `extraer_datos_documento.txt`, que hace la
extracción estructurada.

## Módulos Principales Del Código

### `run_mvp.py`

Punto de entrada simple. Llama a `auxilios_mvp.runner.main()`.

### `src/auxilios_mvp/runner.py`

Lee configuración desde `.env`, imprime mensajes de avance y lanza el pipeline
local.

### `src/auxilios_mvp/settings.py`

Centraliza variables de entorno y flags:

- rutas,
- nombres de carpetas,
- estado de Azure OpenAI,
- estado de Cosmos DB,
- política de reprocesamiento.

### `src/auxilios_mvp/schemas.py`

Define las estructuras internas de datos del flujo. No contiene modelos de IA.
Agrupa objetos como solicitud, análisis documental, regla del beneficio,
registro histórico y recomendación para que los módulos compartan el mismo
contrato.

### `src/auxilios_mvp/pipeline.py`

Orquesta el flujo:

1. Valida carpetas.
2. Encuentra histórico y CSV de reglas.
3. Normaliza histórico.
4. Carga reglas.
5. Lista solicitudes.
6. Analiza documentos.
7. Recomienda.
8. Guarda salidas.

### `src/auxilios_mvp/request_parser.py`

Interpreta nombres de carpetas de solicitud y construye el contexto:

- `request_id`,
- `employee_id`,
- `benefit_code`,
- `concept_code`,
- archivos asociados.

### `src/auxilios_mvp/benefits.py`

Carga `beneficios.csv` y crea reglas por:

- código del beneficio,
- código de concepto,
- aliases.

Esto permite que una solicitud encuentre su regla aunque el nombre venga como
alias o concepto.

### `src/auxilios_mvp/excel_history.py`

Normaliza el histórico Excel a JSON canónico.

### `src/auxilios_mvp/document_analyzer.py`

Coordina el análisis documental con Azure OpenAI. Llama primero al prompt de
clasificación y luego al prompt de extracción. No contiene clasificación local
por palabras clave.

### `src/auxilios_mvp/document_media.py`

Prepara archivos para el modelo omnimodal. Renderiza páginas de PDF como
imágenes, adjunta imágenes originales cuando aplique y agrega texto extraído
solo como contexto auxiliar.

### `src/auxilios_mvp/recommendation.py`

Ejecuta el motor local de reglas, llama al LLM para complementar la recomendación
y normaliza la respuesta de IA para que razones, faltantes y evidencia queden en
formatos persistibles.

### `src/auxilios_mvp/processing_state.py`

Calcula huellas de solicitudes y controla reprocesamiento.

### `src/auxilios_mvp/reporting.py`

Genera `recommendations.csv`. Convierte valores complejos devueltos por IA
como listas o diccionarios a texto JSON dentro de las celdas.

### `src/auxilios_mvp/json_utils.py`

Contiene utilidades de JSON usadas por salidas locales y llamadas a Azure
OpenAI. Convierte tipos no serializables directamente, como `Timestamp`, fechas,
valores `NaN` y tipos numpy/pandas, a valores JSON seguros.

### `src/auxilios_mvp/cosmos_store.py`

Guarda decisiones:

- en `decisions.jsonl` si `COSMOS_ENABLED=false`;
- en Cosmos DB si `COSMOS_ENABLED=true` y hay credenciales.

## Cosmos DB

Por defecto está desactivado:

```env
COSMOS_ENABLED=false
```

Para activarlo:

```env
COSMOS_ENABLED=true
COSMOS_ENDPOINT=https://...
COSMOS_KEY=...
COSMOS_DATABASE=calidad_vida_auxilios
COSMOS_CONTAINER_DECISIONS=decisions
```

Si las solicitudes ya fueron procesadas y se quieren reenviar a Cosmos, usar:

```env
PROCESSING_POLICY=reprocess_all
```

## Azure OpenAI

Para análisis documental está requerido:

```env
AZURE_OPENAI_ENABLED=true
```

Para activarlo:

```env
AZURE_OPENAI_ENABLED=true
AZURE_OPENAI_ENDPOINT=https://...
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_DEPLOYMENT_TEXT=...
AZURE_OPENAI_DEPLOYMENT_OMNIMODAL=...
```

Con IA apagada, el MVP no analiza documentos. Las reglas determinísticas que
quedan son reglas de negocio auditables, no lectura documental.

## Operación Recomendada

1. Cargar o actualizar `data/mvp_layout/00_Config/Historico_Auxilios.xlsx`.
2. Revisar o actualizar `data/mvp_layout/00_Config/beneficios.csv`.
3. Crear una carpeta por solicitud en `data/mvp_layout/01_EntradaSolicitudes/`.
4. Poner los PDFs de soporte dentro de cada carpeta.
5. Ejecutar:

```bash
PYTHONPATH=src python3 run_mvp.py
```

6. Revisar resultados en `data/mvp_layout/02_SalidaReportes/`.

## Cuándo Usar `reprocess_all`

Usar:

```env
PROCESSING_POLICY=reprocess_all
```

cuando:

- se cambió `beneficios.csv`;
- se cambió la lógica de reglas;
- se cambiaron prompts;
- se quiere reenviar información a Cosmos;
- se quiere regenerar salidas completas.

Después de validar, volver a:

```env
PROCESSING_POLICY=skip_unchanged
```

## Limitaciones Actuales

- El análisis documental depende de Azure OpenAI y de un deployment compatible con contenido multimodal.
- Por costo y latencia, se envían las primeras páginas configuradas del PDF al modelo.
- Los criterios textuales del CSV se incluyen como evidencia y contexto; las reglas que quedan son validaciones de negocio sobre campos estructurados.
- La publicación o consolidación semanal externa no forma parte del flujo local actual.

## Resultado Esperado

Al final de una ejecución exitosa, la consola debe mostrar algo como:

```text
Proceso terminado. Recomendaciones generadas: 2; saltadas: 0
Recomendaciones JSON: data/mvp_layout/02_SalidaReportes/recommendations.json
Reporte CSV: data/mvp_layout/02_SalidaReportes/recommendations.csv
Listo.
```

Ese es el punto de entrega para revisión humana.
