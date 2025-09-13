Equilibra - Tu espacio emocional seguro 
 Descripción

Equilibra es una aplicación web desarrollada en Flask (Python) que actúa como un espacio seguro para explorar emociones y, si es necesario, agendar citas con un profesional.

La aplicación permite:

Un chat conversacional que guía al usuario según sus síntomas.

Gestión de sesiones para mantener el historial de la conversación.

Agendamiento de citas sincronizado con Google Calendar.

Notificaciones por correo al profesional asignado.

Una interfaz amigable y con soporte de modo oscuro.

 Estructura del proyecto
.
├── app.py              # Backend en Flask
├── templates/
│   └── index.html      # Frontend (chat e interfaz de usuario)
├── static/
│   └── logo.png        # Logo de la aplicación
├── conversaciones/     # Carpeta donde se almacenan historiales (si aplica)
├── .env                # Variables de entorno (Google API, credenciales)
└── README.md           # Documentación

1. Requisitos Previos
•	Python 3.12 o superior instalado


 
•	Cuenta en Render.com para despliegue


 
•	Cuenta de Google Cloud para Calendar API


•	Cuenta de Gmail para notificaciones por correo



2. Configuración de Variables de Entorno en Render
   
1.	En el dashboard de Render, ve a Environment Variables y configura:
FLASK_SECRET_KEY=tu_clave_secreta_generada_aleatoriamente

EMAIL_USER=tu_email@gmail.com
EMAIL_PASSWORD=tu_contraseña_de_aplicacion
PSICOLOGO_EMAIL=email_del_psicologo@dominio.com
GOOGLE_CREDENTIALS={...} # JSON completo de las credenciales de 
Google
FLASK_DEBUG: True
FLASK_HOST: 0.0.0.0
FLASK_PORT: 5000



 
3. Configuración de Google Calendar API
1.	Ve a Google Cloud Console
  

   
 
2	Crea un nuevo proyecto o selecciona uno existente


 
3.	Habilita la API de Google Calendar


   
 
4.	Crea una cuenta de servicio y descarga las credenciales JSON


   
5.	Copia el contenido completo del JSON a la variable GOOGLE_CREDENTIALS en Render


 


4. Configuración de Email (Gmail)
1.	Activa la verificación en 2 pasos en tu cuenta de Gmail


2.	Genera una contraseña de aplicación específica


3.	Usa esta contraseña en la variable EMAIL_PASSWORD, que verifica la disponibilidad de horarios antes de agendar una cita.
 
Guía de Uso para el Psicólogo
1. Acceso al Sistema
•	La aplicación estará disponible en la URL proporcionada por Render
 <img width="717" height="356" alt="image" src="https://github.com/user-attachments/assets/cf9ddd5f-15b6-45ee-9a7a-9a85ccc098ab" />

•	Comparte este enlace con tus pacientes
https://equlibra.onrender.com/
2. Monitoreo de Citas
•	Revisa tu correo regularmente para notificaciones de nuevas citas
 <img width="429" height="344" alt="image" src="https://github.com/user-attachments/assets/3e30fd3f-d4ef-48a7-be37-910a9f87e978" />

•	Las citas se agregan automáticamente a tu Google Calendar
Guía de Uso para los Pacientes
1. Inicio de Sesión
•	Accede al enlace compartido por el psicólogo
https://equlibra.onrender.com/

•	No es necesario crear cuenta ni iniciar sesión
 
2. Proceso de Interacción
1.	Selección de síntoma: Elige entre los 27 síntomas disponibles
   
 <img width="511" height="384" alt="image" src="https://github.com/user-attachments/assets/df905348-5188-44cb-9b9b-d11068aa6b93" />

 
2.-     Evaluación temporal: Indica desde cuándo experimentas el síntoma

<img width="469" height="385" alt="image" src="https://github.com/user-attachments/assets/f7742ee7-f31a-4e9e-b6ce-dc677a95b501" />

 3.- Diálogo con el sistema: Conversa con el sistema, basado en respuestas proporcionadas por un psicólogo profesional
 
 <img width="502" height="178" alt="image" src="https://github.com/user-attachments/assets/91d04146-f446-4635-9f9b-93ad1dafbd77" />

 
4.-Agendamiento de cita (opcional): Programa una cita presencial si es necesario
 
 

<img width="526" height="526" alt="image" src="https://github.com/user-attachments/assets/a2a51ab9-0ae4-4d37-8dc7-14d6ca6b5ca7" />

