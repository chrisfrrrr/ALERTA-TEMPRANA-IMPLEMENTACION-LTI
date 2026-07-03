# AVE — Sistema de alerta temprana y seguimiento académico

Aplicación profesional en Streamlit para analizar cursos de **cinco semanas**, clasificar el riesgo académico, enviar mensajes por Canvas, generar derivaciones a bienestar y conservar el historial en Supabase.

## Funciones incluidas

- Inicio de sesión institucional con **Canvas OAuth2**.
- Eliminación del ingreso manual de token en la interfaz.
- Developer Key configurable desde Canvas con `client_id`, `client_secret`, `redirect_uri` y scopes opcionales.
- Roles internos en Supabase: `admin`, `asesor_academico`, `asesor_bienestar` y `consulta`.
- Bitácora de auditoría para accesos, análisis, mensajes, respuestas y derivaciones.
- Selección de curso, sección, semana 1–5 y fecha de corte.
- Meta semanal acumulada: `techo(total de actividades × semana / 5)`.
- Análisis de actividades, promedio, puntualidad, actividad en Canvas y respuesta a comunicaciones.
- Dashboard general y expediente individual por estudiante.
- Mensajes personalizados por riesgo y envío mediante Conversations API de Canvas.
- Registro de mensajes y sincronización posterior de respuestas.
- Selección múltiple de estudiantes para derivación.
- Generación de un ZIP con carpetas por asesor de bienestar, informe general e Excel individual por estudiante.
- Detección de derivaciones recientes para evitar duplicados.
- Historial semanal en Supabase y visualización de mejora, estabilidad o deterioro.
- Modo demostración navegable sin credenciales, si `ALLOW_DEMO_MODE=true`.
- Base de bienestar limpia incluida en `data/bienestar_base.csv`.

## Estructura

```text
app.py
pages/                  Páginas de Streamlit
services/               Canvas, OAuth2, riesgo, Supabase, mensajes y derivaciones
components/             Diseño y gráficas
models/                 Configuración tipada
utils/                  Fechas, limpieza y extracción de carné
sql/schema.sql          Estructura completa de Supabase, usuarios y auditoría
data/bienestar_base.csv Base inicial normalizada
tests/                  Pruebas del cálculo semanal y del motor de riesgo
```

## Instalación local

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

## Configurar Canvas OAuth2

Solicite al administrador de Canvas la creación de una **Developer Key** para la aplicación AVE.

Parámetros sugeridos:

| Campo | Valor recomendado |
|---|---|
| Nombre | AVE Alerta Temprana |
| Redirect URI | URL pública de la app Streamlit, por ejemplo `https://ave-alerta.streamlit.app` |
| Client ID | Generado por Canvas |
| Client Secret | Generado por Canvas, guardar solo en secretos |
| Scopes | Lectura de cursos, usuarios, actividades, entregas y conversaciones; envío de mensajes si la institución usa scopes granulares |

Después de crear la Developer Key, coloque los valores en `.streamlit/secrets.toml` o en **Streamlit Cloud > Settings > Secrets**.

## Configurar Supabase

1. Cree un proyecto en Supabase.
2. Abra **SQL Editor**.
3. Ejecute todo el contenido de `sql/schema.sql`.
4. Copie `.streamlit/secrets.toml.example` como `.streamlit/secrets.toml`.
5. Complete `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY`.
6. Ingrese a la app como administrador y registre usuarios autorizados desde **Configuración > Usuarios y OAuth2**.

La `service_role` debe permanecer exclusivamente en los secretos del servidor. No la coloque en el repositorio ni en campos visibles de la aplicación.

## Secrets de Streamlit

```toml
CANVAS_URL = "https://uvg.instructure.com"
CANVAS_OAUTH_CLIENT_ID = "CLIENT_ID_DE_LA_DEVELOPER_KEY"
CANVAS_OAUTH_CLIENT_SECRET = "CLIENT_SECRET_DE_LA_DEVELOPER_KEY"
CANVAS_OAUTH_REDIRECT_URI = "https://TU-APP.streamlit.app"
CANVAS_OAUTH_SCOPES = ""

ALLOW_DEMO_MODE = true
REQUIRE_AUTHORIZED_USER = false

SUPABASE_URL = "https://SU-PROYECTO.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "SU_SERVICE_ROLE_KEY"
USE_SUPABASE = true
```

### Modo piloto y modo producción

Para piloto inicial puede usar:

```toml
ALLOW_DEMO_MODE = true
REQUIRE_AUTHORIZED_USER = false
```

Para producción institucional se recomienda:

```toml
ALLOW_DEMO_MODE = false
REQUIRE_AUTHORIZED_USER = true
```

Con `REQUIRE_AUTHORIZED_USER=true`, solamente podrán entrar usuarios registrados en la tabla `authorized_users`.

## Roles internos

| Rol | Alcance recomendado |
|---|---|
| `admin` | Configuración, usuarios, auditoría, análisis e intervenciones. |
| `asesor_academico` | Análisis de cursos, dashboards, mensajes y derivaciones. |
| `asesor_bienestar` | Consulta de seguimiento de estudiantes derivados a su cargo. |
| `consulta` | Lectura de reportes sin acciones operativas. |

La versión actual aplica restricción de navegación por rol en Streamlit. Para endurecimiento institucional, se recomienda complementar con políticas RLS específicas por usuario en Supabase.

## Uso recomendado

1. Entre a **Acceso institucional**.
2. Presione **Iniciar sesión con Canvas**.
3. Autorice el acceso desde Canvas.
4. Entre a **Conexión y análisis**.
5. Cargue cursos desde Canvas.
6. Seleccione curso, sección, semana y fecha de corte.
7. Active Page Views solo cuando la Developer Key tenga permiso y se necesite estimar sesiones.
8. Ejecute el análisis.
9. Revise el dashboard general y los expedientes individuales.
10. Envíe mensajes desde **Mensajería Canvas**.
11. Prepare derivaciones desde **Derivaciones**.
12. Compare cortes desde **Historial y evolución**.
13. Revise auditoría desde **Configuración > Auditoría**.

## Regla semanal

Para 15 actividades:

| Semana | Meta acumulada |
|---:|---:|
| 1 | 3 |
| 2 | 6 |
| 3 | 9 |
| 4 | 12 |
| 5 | 15 |

Para cantidades no divisibles entre cinco se utiliza redondeo hacia arriba. Por ejemplo, 17 actividades producen metas acumuladas de 4, 7, 11, 14 y 17.

## Consideraciones de Canvas

- El conteo exacto de ingresos depende del permiso para consultar Page Views.
- Cuando Page Views no está disponible, la app utiliza `last_activity_at` de la inscripción y no inventa una cantidad de sesiones.
- Las actividades se filtran para excluir elementos no publicados y no calificables. Las actividades de cero puntos pueden incluirse desde la interfaz.
- Las entregas tardías cuentan como actividades completadas, pero afectan el indicador de puntualidad.
- La detección de respuestas se realiza sobre conversaciones enviadas por la aplicación y registradas en Supabase.
- OAuth2 reemplaza el ingreso manual de token; el access token se mantiene en sesión y no se almacena en Supabase.

## Pruebas

```bash
pytest -q
```

Las pruebas verifican, entre otros casos, la distribución de 15 y 17 actividades a lo largo de cinco semanas.

## Actualización 1.3: seguridad institucional

Esta versión incorpora autenticación Canvas OAuth2, elimina el campo visible de token manual, agrega roles internos en Supabase y registra auditoría de las acciones principales. Para producción, use `REQUIRE_AUTHORIZED_USER=true` y registre previamente a los usuarios autorizados.
