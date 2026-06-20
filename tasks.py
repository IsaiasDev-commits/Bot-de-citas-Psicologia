"""
Tareas asíncronas de Equilibra via Celery.

Inicio del worker (desarrollo):
    celery -A tasks.celery_app worker --loglevel=info

Inicio del worker (producción):
    celery -A tasks.celery_app worker --loglevel=info --concurrency=2

Requiere REDIS_URL en las variables de entorno.
"""
import os
import logging
from celery import Celery

logger = logging.getLogger(__name__)

_redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

celery_app = Celery(
    'equilibra',
    broker=_redis_url,
    backend=_redis_url,
)

celery_app.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    timezone='America/Guayaquil',
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=100,
    broker_connection_retry_on_startup=True,
)


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name='tasks.send_confirmation_email',
)
def send_confirmation_email(
    self,
    destinatario: str,
    fecha: str,
    hora: str,
    telefono: str,
    sintoma: str,
) -> dict:
    """
    Envía email de confirmación de cita de forma asíncrona.
    Reintenta hasta 3 veces con 60 s entre intentos si el envío falla.
    """
    try:
        from services.appointment_service import enviar_correo_resend
        success = enviar_correo_resend(destinatario, fecha, hora, telefono, sintoma)
        if not success:
            raise RuntimeError("enviar_correo_resend devolvió False")
        logger.info(f"Email de confirmacion enviado: {fecha} {hora} a {destinatario}")
        return {"status": "sent", "to": destinatario, "fecha": fecha, "hora": hora}
    except Exception as exc:
        logger.error(
            f"Error enviando email (intento {self.request.retries + 1}/4): {exc}"
        )
        raise self.retry(exc=exc)
