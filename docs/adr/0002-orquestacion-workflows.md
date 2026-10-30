# ADR-0002: Orquestación con Cloud Scheduler + Workflows

**Estado:** Aceptada · **Fecha:** 2026-10-30

## Contexto
El pipeline debe correr solo: una vez al mes (o al día), ejecutar la ingesta y, **solo si terminó bien**, ejecutar dbt.
Si algo falla, debe quedar registrado y avisar. Hay que decidir qué lo dispara y qué encadena los pasos.

Restricciones:
- **Forma del flujo:** lineal y corto: `ingest → dbt`, con reintento y aviso en caso de error. No hay decenas de tareas en paralelo.
- **Costo:** prueba gratuita de 90 días y luego nada. Un costo fijo mensual consume el crédito aunque el pipeline no corra.
- **Plataforma:** ingest y dbt serán Cloud Run Jobs (fase 4), con cuentas de servicio y permisos mínimos.
- **Portafolio:** demostrar orquestación e IAM entre servicios, y poder explicar por qué no se usó la herramienta "famosa".

## Opciones consideradas
### A. Cron en GitHub Actions que lanza los jobs
- A favor: ya usaremos GitHub Actions para CI/CD; gratis en repos públicos.
- En contra: GitHub desactiva los workflows programados de repos públicos tras 60 días sin actividad; la hora de
  ejecución no está garantizada; GitHub necesita permisos sobre GCP (más superficie de ataque); los logs quedan fuera de GCP.

### B. Cloud Scheduler solo, disparando cada Cloud Run Job
- A favor: lo más simple; nivel gratuito para pocos jobs.
- En contra: no encadena: para que dbt corra después de la ingesta habría que programarlo "una hora después" y esperar
  que la ingesta haya terminado bien. Frágil.

### C. Cloud Scheduler + Workflows
- A favor: Workflows ejecuta los pasos en orden, espera a que cada job termine, reintenta y maneja errores; es
  serverless y se cobra por paso (con nivel gratuito); obliga a configurar IAM entre servicios (Scheduler → Workflows → Cloud Run).
- En contra: se escribe en YAML con una sintaxis propia y limitada; no tiene la interfaz de un DAG como Airflow; es
  conocimiento menos transferible fuera de GCP.

### D. Cloud Composer (Airflow gestionado)
- A favor: Airflow es el estándar de la industria y aparece en muchas ofertas de empleo; interfaz completa de DAGs.
- En contra: el entorno queda encendido todo el mes, con un costo fijo alto que consumiría la prueba gratuita; es
  desproporcionado para un flujo de dos pasos.

### E. Dagster o Prefect
- A favor: herramientas modernas; buen desarrollo local; Dagster modela datos como *assets* y se integra con dbt.
- En contra: autoalojado exige un servicio siempre encendido y una base de datos; las versiones gestionadas son de pago
  o tienen niveles gratuitos limitados; a esta escala no aportan algo que Workflows no haga, y dbt ya da el grafo de la transformación.

## Decisión
_Cloud Scheduler y Workflows es la alternativa seleccionada, dado que cumple con las dos necesidades mínimas identificadas para este proyecto: programar tareas según las fechas publicadas por las Fuentes y también validar que los pasos de transformación se inicien sólo bajo una ingesta validada._

## Consecuencias
- **El flujo vive en `orchestration/workflow.yaml`:** ingest → (solo si terminó bien) transformación en Dataform (ADR-0001).
  Si falla, queda un log `ERROR`/`CRITICAL` (convención de la 0.7) y se dispara una alerta.
- **IAM entre servicios:** Scheduler necesita permiso para invocar el workflow, y el workflow para ejecutar el job de
  ingesta e invocar Dataform. Esos bindings los escribe Rafael en la fase 2.
- **Calendario:** cada fuente publica en fechas distintas. En la fase 4 se decide entre varios *schedules* (uno por
  fuente o grupo) y una corrida diaria que solo procesa lo nuevo (la idempotencia por sha256 lo permite).
- **Se acepta:** YAML con sintaxis limitada, sin interfaz de DAG, y menos transferible que Airflow. El README explicará
  cómo se vería con Composer.

## Referencias
- `docs/plan.md` §3 (arquitectura objetivo), §6 (costos), §8 (decisiones tomadas: "Cloud Scheduler + Workflows. Sin Dagster").
- Precios: Workflows https://cloud.google.com/workflows/pricing · Scheduler https://cloud.google.com/scheduler/pricing ·
  Composer https://cloud.google.com/composer/pricing
- Workflows programados en GitHub Actions: https://docs.github.com/actions/using-workflows/events-that-trigger-workflows#schedule
