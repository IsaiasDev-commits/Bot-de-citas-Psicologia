Equilibra - Tu espacio emocional seguro 💙
📖 Descripción

Equilibra es una aplicación web desarrollada en Flask (Python) que actúa como un espacio seguro para explorar emociones y, si es necesario, agendar citas con un profesional.

La aplicación permite:

Un chat conversacional que guía al usuario según sus síntomas.

Gestión de sesiones para mantener el historial de la conversación.

Agendamiento de citas sincronizado con Google Calendar.

Notificaciones por correo al profesional asignado.

Una interfaz amigable y con soporte de modo oscuro.

📂 Estructura del proyecto
.
├── app.py              # Backend en Flask
├── templates/
│   └── index.html      # Frontend (chat e interfaz de usuario)
├── static/
│   └── logo.png        # Logo de la aplicación
├── conversaciones/     # Carpeta donde se almacenan historiales (si aplica)
├── .env                # Variables de entorno (Google API, credenciales)
└── README.md           # Documentación

⚙️ Instalación y ejecución

Clonar el repositorio

git clone https://github.com/tuusuario/equilibra.git
cd equilibra


Crear entorno virtual e instalar dependencias

python -m venv venv
source venv/bin/activate  # En Linux/Mac
venv\Scripts\activate     # En Windows

pip install -r requirements.txt


Configurar variables de entorno (.env)

FLASK_SECRET_KEY=tu_clave_secreta
EMAIL_USER=tu_correo@gmail.com
EMAIL_PASSWORD=tu_password
PSICOLOGO_EMAIL=correo_del_psicologo@gmail.com
GOOGLE_CREDENTIALS={JSON_de_servicio_de_Google}


Ejecutar la aplicación

python app.py


Accede en el navegador a: http://localhost:5000
