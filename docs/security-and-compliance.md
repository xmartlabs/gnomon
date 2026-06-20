# Seguridad y cumplimiento — salvaguardas contra manipulación y fuga de datos

> **Propósito.** Este documento nace de una demostración práctica de seguridad sobre
> `gnomon`/`xl-ai-insights`. Se modificó localmente `paxel.py` para que el reporte
> subido a mirdash mostrara **AQ 100 / Elite / 10-10-10 en todos los ejes y todos los
> períodos**, sin tocar el flujo de red ni la autenticación. La demostración es
> constructiva: su objetivo es endurecer el producto, no desacreditarlo. Abajo se
> detallan (1) por qué la manipulación es trivial hoy, (2) qué salvaguardas del lado
> del servidor la mitigarían, (3) los riesgos de fuga de datos de clientes, y (4) el
> mapeo explícito contra SOC 2 y HIPAA, incluyendo los puntos que el proyecto **incumple
> hoy**.

---

## 1. Resumen ejecutivo

El producto tiene un buen instinto de privacidad: el `paxel.py` original corre 100%
local y `summary.json` (lo único que se sube) está deliberadamente reducido a
**agregados y conteos**, sin prompts, rutas ni nombres de proyecto. Eso está bien y
hay que reconocerlo.

Pero el diseño tiene tres debilidades estructurales que lo hacen **inadecuado como
herramienta de evaluación de personas o asignación de premios**, y que exigen cuidado
antes de distribuirlo a la flota de desarrolladores:

1. **Integridad (manipulación).** Todo el cálculo de métricas y puntajes ocurre en la
   máquina del desarrollador, en código que el desarrollador controla. El servidor
   acepta el `POST` sin forma de verificar que los números sean reales. Demostrado:
   ~12 líneas en [`paxel.py`](../paxel.py) bastan para reportar Elite perfecto.
2. **Confidencialidad (fuga).** Aunque el *payload subido* es seguro, los **artefactos
   locales** (`narrative_input.md`, `stats.json`) contienen datos derivados de
   transcripts: prompts verbatim, rutas absolutas, nombres de proyectos de clientes y
   referencias a `.env`. La protección actual (`.gitignore`) es frágil y `--output-dir`
   la evade por completo.
3. **Cadena de suministro y ejecución (la más severa).** Pedirle a los devs que corran
   `uvx --from git+...` o `curl | python3` es pedirles ejecutar **código remoto
   auto-actualizable y sin firmar**, con permisos de lectura sobre **todos** sus
   transcripts de IA (secretos, código y datos de clientes) y un canal de red ya
   integrado. Un único compromiso upstream se vuelve exfiltración masiva sobre la flota.

Ninguna salvaguarda del lado del cliente resuelve (1): si el código corre en la PC del
dev, el dev puede cambiarlo. Y (3) muestra la otra cara de la misma moneda: si el dev
corre código de otros, ese código puede hacer cualquier cosa con sus datos. Las
mitigaciones reales son **server-side**, de **distribución firmada** y de **proceso**.

---

## 2. Vector de manipulación (demostrado)

### 2.1 Qué se cambió

En [`compute_aq`](../paxel.py) y `score_breakdown` se forzaron los puntajes al máximo
antes del `return`. El resto del pipeline (volumen, churn de git, conteos de sesiones)
quedó **real**. Resultado en el `summary.json` subido:

| Campo en el payload | Valor real previo | Valor manipulado |
|---|---|---|
| `profile.aq.aq_0_100` / `tier` | calculado | **100 / Elite** |
| `profile.scores.{execution,planning,engineering}.value` | 8.8 / 10.0 / 8.2 | **10.0 / 10.0 / 10.0** |
| `profile.aq.pillars[*].score` | calculado | **100 cada uno** |
| `planning_ratio`, `errors`, `iteration_depth`, `orchestration` | calculados | valores ideales |
| `context.total_sessions`, `churn.git_churn_total` | reales | **reales (sin tocar)** |

El punto incómodo: como las **líneas de código y el churn son reales**, el reporte
manipulado es indistinguible de uno legítimo a simple vista. Un evaluador no tiene
manera de saber que los puntajes de calidad fueron falsificados.

### 2.2 Por qué no se puede arreglar en el cliente

`uvx --from git+...` descarga el código desde GitHub, pero nada impide:

- correr una copia local modificada (lo que hicimos),
- interceptar/editar el `POST` a `/api/gnomon/ingest`,
- reusar/forjar el JWT capturado en el callback de `localhost:8799`.

**Conclusión de diseño:** un cálculo client-side de un puntaje con consecuencias
(premios, ranking, evaluación) es un modelo de confianza roto. El servidor debe asumir
que **todo input es adversarial**.

---

## 3. Salvaguardas del lado del servidor — integridad de métricas

Ordenadas por relación impacto/costo.

### 3.1 Recalcular en el servidor a partir de datos crudos (no confiar en puntajes)
Hoy el cliente envía los puntajes ya calculados (`profile.scores`, `profile.aq`). El
servidor debería recibir **solo las señales crudas medidas** y calcular los puntajes él
mismo, con la fórmula como secreto del servidor. Esto no impide falsear las señales
crudas, pero elimina el ataque trivial de "setear el puntaje a 10".

### 3.2 Validación de invariantes y detección de anomalías
Rechazar o marcar para revisión humana payloads que violen invariantes derivables:

- puntajes perfectos (AQ ≥ 95, todos los ejes ≥ 9.5) → cola de revisión,
- inconsistencias internas: p. ej. `iteration_depth.mean = 1.4` pero `max = 60`; o
  `error_rate ≈ 0` con decenas de miles de tool calls,
- pilares todos exactamente en su peso máximo (firma de la manipulación demostrada),
- saltos imposibles mes a mes en `progression_monthly`.

### 3.3 Versión y firma del cliente verificadas
`context.client_version` es hoy un string auto-reportado (`"0.1.0"`) y falsificable.
Opciones: publicar releases firmados, exigir un hash del binario/script conocido, y
**rechazar versiones no oficiales**. No es a prueba de balas (el cliente sigue en manos
del dev) pero sube el costo del ataque.

### 3.4 Attestation del entorno (donde sea viable)
Para usos de alto riesgo, mover el cómputo fuera de la máquina del dev: subir los
transcripts crudos a un entorno controlado (con todos los problemas de privacidad que
eso implica — ver §4/§5), o ejecutar en CI con runners de la organización donde el
código no es editable por el evaluado.

### 3.5 Rate limiting, idempotencia y trazabilidad
- Límite de envíos por usuario/período; un `--init` legítimo sube 12 ventanas, no 200.
- Clave de idempotencia por (usuario, mes) para evitar reescrituras silenciosas del
  histórico.
- **Audit log inmutable** de cada ingesta (quién, cuándo, hash del payload, IP, versión).

### 3.6 No usar la métrica para decisiones de alto riesgo
La salvaguarda más honesta: documentar explícitamente que estos puntajes son
**auto-reportados y no verificados**, aptos para auto-reflexión/motivación, **no** para
evaluación de desempeño, ranking entre personas, ni asignación de premios.

---

## 4. Salvaguardas — confidencialidad y fuga de datos de clientes

### 4.1 Estado actual (lo bueno)
- `python3 paxel.py` no hace llamadas de red.
- `summary.json` (lo único subido) es **agregado/conteos**. Verificado: no contiene
  rutas, ni `cwd`, ni nombres de proyecto; `repo`/`client` aparecen solo como conteos
  (`git_repos_seen`) y `client_version`.
- Los artefactos sensibles están en `.gitignore` dentro del directorio del repo.

### 4.2 Estado actual (lo riesgoso)
El archivo [`narrative_input.md`](../narrative_input.md) — y en menor medida
`stats.json` — contienen datos crudos derivados de transcripts. En la corrida real de
esta demo se observaron, **en texto plano**:

- **prompts verbatim** del desarrollador,
- **rutas absolutas** del sistema (`/Users/<usuario>/Documents/...`, `/Users/<usuario>/.codex/...`),
- **nombres de proyectos que parecen de clientes** (p. ej. `erp-msinnovatech`,
  `ml-control-and-validation`, `artemis-v2`, `vytallink-health-kit`),
- **nombres de archivos con datos de negocio y de personas** (planillas Excel con
  nombres propios),
- referencias a archivos `.env` (potenciales secretos por nombre/ubicación),
- proyectos del dominio **salud** (`vytallink-health-kit`, `health_tracking_tool`) →
  contexto potencialmente sujeto a HIPAA (ver §6).

Estos archivos **no se suben** hoy, pero persisten en disco y su protección es frágil:

1. **`--output-dir` evade el `.gitignore`.** [`_COPIED_OUTPUTS`](../xl_ai_insights.py)
   copia los 5 artefactos —**incluido `narrative_input.md`**— a una ruta arbitraria
   elegida por el usuario, donde no hay ninguna regla de ignore. Es fácil terminar
   commiteando prompts verbatim de clientes en otro repo.
2. **El `.gitignore` solo protege el CWD del repo `gnomon`.** Si se corre `paxel.py`
   desde otro directorio (Opción A del README escribe en el CWD), los artefactos caen
   donde sea que estés parado.
3. **Persistencia indefinida.** No hay borrado ni expiración de los artefactos locales.

### 4.3 Mitigaciones recomendadas
- **Minimización por defecto:** no escribir `narrative_input.md` a menos que se pida
  explícitamente (`--narrative`); o cifrarlo/marcarlo con permisos restrictivos.
- **Redacción de rutas y nombres:** truncar rutas absolutas a basenames, hashear o
  anonimizar nombres de proyecto/archivo en *todos* los artefactos locales, no solo en
  el payload.
- **`--output-dir` seguro:** al copiar, **excluir `narrative_input.md` y `stats.json`**
  por defecto (subset share-safe), o escribir un `.gitignore` en el destino, o exigir
  `--include-sensitive` explícito con un warning.
- **Limpieza/retención:** comando `--clean` y/o expiración automática de artefactos.
- **Detección de secretos:** advertir si se detectan rutas a `.env`, claves, o tokens
  en los transcripts antes de escribir cualquier artefacto.
- **Consentimiento informado:** mostrar, antes del primer upload, exactamente qué
  campos viajan y obtener confirmación explícita (no solo documentarlo en el README).

### 4.4 Manejo del token de autenticación
El JWT se captura vía un callback HTTP en `localhost:8799`
([`_capture_cli_token`](../xl_ai_insights.py)). Recomendaciones:
- usar `state`/PKCE para el flujo de auth y validar `origin`/`Referer`,
- bindear el servidor solo a `127.0.0.1`, puerto efímero, y cerrarlo apenas se recibe
  el callback,
- nunca persistir el token en disco ni en logs (hoy el código dice que no se loguea —
  conviene un test que lo garantice),
- tokens de corta vida y de un solo uso para la ingesta.

---

## 5. Cadena de suministro y superficie de ejecución

Esta es, probablemente, la categoría de riesgo más severa, y es **independiente** de la
manipulación de métricas: tiene que ver con **qué se le pide ejecutar al desarrollador**
y **qué puede leer ese código** en su máquina.

### 5.1 Lo bueno
[`pyproject.toml`](../pyproject.toml) declara `dependencies = []`. No hay árbol de
dependencias de terceros, así que el riesgo clásico estilo **npm/PyPI** —una
vulnerabilidad en una dependencia transitiva profunda (casos `event-stream`,
`ua-parser-js`, el backdoor de `xz`)— hoy es **mínimo en cuanto a librerías declaradas**.
Hay que reconocerlo.

### 5.2 El problema: el mecanismo de distribución reintroduce el mismo riesgo
Aunque no haya paquetes vulnerables, **cómo se entrega y ejecuta** el código reproduce
exactamente esa clase de riesgo de cadena de suministro:

| Vector (del README) | Riesgo |
|---|---|
| `uvx --from git+https://github.com/xmartlabs/gnomon xl-ai-insights` | Ejecuta **lo que esté en `main` HEAD al momento de correr**: sin commit pineado, sin firma, sin hash. `--refresh` fuerza re-descarga. Compromiso del repo o de una cuenta de GitHub → **RCE en cada máquina** en la siguiente corrida. |
| `python3 <(curl -sL .../paxel.py)` (Opción A) | Patrón `curl \| intérprete`: pipe directo de GitHub raw a `python3`, sin verificación de integridad. MITM o repo comprometido → RCE. |
| `uvx xl-ai-insights` (resuelve desde PyPI por nombre) | Typosquatting, dependency-confusion y toma de cuenta de PyPI. |
| `build-system.requires = ["setuptools>=61", "wheel"]` (sin pin) | El backend de build se trae sin versión fija; uv y el runtime de Python también quedan en la base de confianza. |

**El núcleo del problema:** pedirle a los devs que corran esto es pedirles que ejecuten
**código remoto auto-actualizable y sin firmar**, con privilegios de lectura amplios y un
canal de red ya integrado.

### 5.3 El multiplicador: lectura amplia + canal de salida ya presente
[`paxel.py`](../paxel.py) recorre, en el home del usuario:
`~/.claude/projects`, `~/.codex/sessions`, `~/.gemini/tmp`, `~/.cursor/projects`,
`~/.pi/agent/sessions`, `~/.local/share/opencode`, y bases SQLite de Antigravity y
Cursor. Es decir, **todo lo que el desarrollador haya pegado o escrito en cualquier
herramienta de IA**: secretos, credenciales, código y datos de clientes, PII.

Combinado con el `POST` saliente a mirdash ([`_upload_summary`](../xl_ai_insights.py)),
la herramienta **ya contiene** las dos piezas de una exfiltración: lectura total de
transcripts + canal de red. Una versión comprometida (vía 5.2) **no necesita traer nada
nuevo** — le alcanza con cambiar a dónde apunta el `POST` o ampliar qué campos incluye.
Es una herramienta de exfiltración llave en mano a un cambio de distancia.

Además, ejecuta `git` como subproceso ([`git -C <cwd> log --numstat`](../paxel.py)) sobre
**cada repo descubierto en los transcripts**, y levanta un servidor HTTP local más el
navegador para el flujo de auth — superficie de ejecución adicional.

### 5.4 Radio de explosión
Los objetivos son **máquinas de desarrolladores**, con acceso a código fuente,
credenciales, llaves SSH/cloud y datos de clientes. Un único compromiso upstream se
propaga a toda la organización en la siguiente corrida y habilita movimiento lateral.
La superficie no es "un reporte de métricas": es RCE distribuido sobre la flota de devs.

### 5.5 Mitigaciones recomendadas
- **Pinear y firmar la distribución:** publicar releases versionados en PyPI, instalar
  por **versión + hash** (`--require-hashes`), y firmar los artefactos (Sigstore). Evitar
  `git+https` a `main` y `curl | python3` en la documentación oficial.
- **Reproducibilidad:** lockfile y build reproducible; pinear `setuptools`/`wheel`.
- **Principio de mínimo privilegio:** acotar la lectura a las fuentes estrictamente
  necesarias, con allowlist explícita y opt-in por fuente; no recorrer todo el home por
  defecto.
- **Transparencia de red:** un solo endpoint de salida, fijo y verificable; fallar si el
  destino no coincide con el esperado (cert pinning / allowlist de host).
- **Higiene de supply chain:** escaneo de dependencias (aunque hoy sean 0), Dependabot,
  protección de rama `main`, 2FA obligatorio y firma de commits para los mantenedores,
  y SBOM publicado.
- **Auditabilidad para el que lo corre:** modo `--dry-run`/`--print-only` que muestre
  exactamente qué archivos se leerían y qué se enviaría, sin red.

---

## 6. Mapeo SOC 2 (Trust Services Criteria)

SOC 2 evalúa controles sobre Seguridad, Disponibilidad, Integridad de Procesamiento,
Confidencialidad y Privacidad. Relevantes acá:

| Criterio (TSC) | Expectativa | Estado en el proyecto | Brecha |
|---|---|---|---|
| **CC6.1 / CC6.6** — Controles de acceso lógico | Autenticación robusta, protección de credenciales | JWT vía callback localhost; sin PKCE/state documentado | ⚠️ Parcial |
| **CC7.2** — Detección de anomalías | Monitoreo de eventos anómalos | No hay validación de invariantes ni detección de payloads imposibles | ❌ **Incumple** |
| **PI1.1 / PI1.2** — Integridad de procesamiento | Los datos procesados son completos, válidos, precisos, autorizados | Puntajes calculados client-side y aceptados sin verificación → **manipulables** | ❌ **Incumple** |
| **C1.1 / C1.2** — Confidencialidad | Identificación, protección y disposición de info confidencial | Artefactos locales con datos de cliente sin redacción, sin retención/borrado, `--output-dir` sin protección | ❌ **Incumple** (artefactos locales) |
| **CC7.3 / CC4.1** — Logging y auditoría | Registro de actividad para investigar incidentes | No hay audit log de ingestas documentado | ❌ **Incumple** |
| **CC8.1 / CC1.4** — Gestión de cambios e integridad del software | Distribución de software firmada, versionada y controlada | Distribución vía `git+https` a `main` y `curl \| python3`, sin pin/firma/hash (§5.2) | ❌ **Incumple** |
| **CC9.2** — Gestión de riesgo de terceros / proveedores | Controlar el riesgo de componentes y proveedores | Sin SBOM, sin escaneo de deps, sin pin del backend de build (§5.5) | ⚠️ Parcial |
| **P** (Privacy) — Aviso y consentimiento | Notificación clara y consentimiento del titular | README describe qué se sube, pero no hay consentimiento explícito en runtime | ⚠️ Parcial |

**Incumplimientos SOC 2 explícitos a corregir antes de cualquier uso evaluativo:**
- **PI1 (integridad de procesamiento):** confiar en puntajes client-side viola el
  criterio. Mitigar con §3.1–§3.2.
- **CC7.2/CC7.3 (monitoreo y auditoría):** falta detección de anomalías y audit log.
- **C1 (confidencialidad):** los artefactos locales con datos de cliente requieren
  minimización, redacción y política de retención (§4.3).
- **CC8.1 (gestión de cambios / integridad del software):** la distribución sin firmar
  ni pinear (§5.2) es un incumplimiento de control de cambios y un vector de RCE.

---

## 7. Mapeo HIPAA

HIPAA aplica si la organización o sus clientes manejan **PHI** (Protected Health
Information). En esta misma demo aparecieron proyectos de dominio salud
(`vytallink-health-kit`, `health_tracking_tool`, prompts sobre *health tracking*),
lo que hace el riesgo concreto, no hipotético.

| Regla HIPAA | Expectativa | Riesgo en el proyecto |
|---|---|---|
| **Privacy Rule** — uso/divulgación mínima de PHI | Limitar PHI al mínimo necesario | Prompts y nombres de archivos de proyectos de salud quedan en `narrative_input.md` en claro; podrían contener o referenciar PHI |
| **Security Rule §164.312(a)(2)(iv)** — cifrado | PHI en reposo cifrada | Artefactos locales sin cifrar |
| **Security Rule §164.312(b)** — controles de auditoría | Registrar acceso a PHI | Sin logging del acceso a transcripts ni a artefactos |
| **§164.312(e)** — transmisión segura | Proteger PHI en tránsito | El `POST` usa HTTPS si `mirdash-base` es https, pero el README permite `http://localhost` — verificar que prod fuerce TLS |
| **Business Associate Agreement (BAA)** | Cualquier tercero que procese PHI necesita BAA | Si mirdash llegara a recibir PHI (hoy no debería, pero ver §7.1), se requiere BAA con el operador del servidor |
| **Minimum Necessary** | No recolectar PHI innecesaria | Si un transcript contiene PHI, termina en `stats.json`/`narrative_input.md` sin filtrado |

### 7.1 Punto crítico HIPAA
El payload subido **hoy no incluye** prompts ni nombres de archivo, así que el riesgo
de transmitir PHI a mirdash es bajo **en la versión actual**. Pero:

- la barrera depende de que `summary.json` siga siendo agregado; cualquier feature
  futura que suba "narrativa" o "ejemplos de prompts" rompería esto y transmitiría PHI;
- el riesgo de PHI **en reposo, local y sin cifrar** (artefactos) es real hoy;
- si la org trabaja con clientes de salud, debería tratar `narrative_input.md` y
  `stats.json` como artefactos potencialmente con PHI: cifrar, redactar, retener mínimo,
  y **nunca** copiarlos vía `--output-dir` a ubicaciones compartidas.

**Recomendación HIPAA:** asumir que los transcripts pueden contener PHI y aplicar
minimización agresiva (§4.3) + cifrado en reposo + prohibición explícita de uso de la
herramienta sobre máquinas que manejen PHI hasta cerrar las brechas de §4 y §5.

---

## 8. Checklist accionable para el equipo

**Integridad (bloquea uso evaluativo):**
- [ ] Recalcular puntajes server-side a partir de señales crudas (§3.1)
- [ ] Validación de invariantes + detección de anomalías + cola de revisión (§3.2)
- [ ] Audit log inmutable de ingestas (§3.5)
- [ ] Rate limiting + idempotencia por (usuario, mes) (§3.5)
- [ ] Documentar que los puntajes son auto-reportados y no aptos para evaluación (§3.6)

**Confidencialidad / fuga:**
- [ ] No escribir `narrative_input.md` por defecto; gate `--narrative` (§4.3)
- [ ] Redactar rutas y nombres en todos los artefactos locales (§4.3)
- [ ] `--output-dir` excluye artefactos sensibles o exige `--include-sensitive` (§4.3)
- [ ] Comando de limpieza / retención de artefactos (§4.3)
- [ ] Consentimiento explícito en runtime antes del primer upload (§4.3)
- [ ] Endurecer el flujo de auth: PKCE/state, bind 127.0.0.1, token efímero (§4.4)

**Cadena de suministro y ejecución (bloquea distribución a la flota):**
- [ ] Distribuir por versión + hash firmado; eliminar `git+https`@`main` y `curl | python3` de la doc oficial (§5.5)
- [ ] Pinear `setuptools`/`wheel`; lockfile y build reproducible (§5.5)
- [ ] Mínimo privilegio: allowlist de fuentes, opt-in por fuente, no recorrer todo el home (§5.5)
- [ ] Endpoint de salida único, fijo y verificable (allowlist de host) (§5.5)
- [ ] Higiene de repo: protección de `main`, 2FA + commits firmados, Dependabot, SBOM (§5.5)
- [ ] Modo `--dry-run`/`--print-only` que muestre qué se lee y qué se envía, sin red (§5.5)

**Cumplimiento:**
- [ ] Cerrar brechas SOC 2 PI1, CC7.2/7.3, C1, CC8.1 (§6)
- [ ] Tratar artefactos como posible PHI: cifrado en reposo + minimización (§7)
- [ ] Forzar TLS en `mirdash-base` de producción (§7)

---

*Documento generado como parte de una revisión de seguridad defensiva del proyecto.
Las referencias de código apuntan a [`paxel.py`](../paxel.py) y
[`xl_ai_insights.py`](../xl_ai_insights.py) en el estado de esta rama.*
