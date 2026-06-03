    // TEMA 
    function setTheme(theme) {
      document.body.setAttribute('data-theme', theme);
      localStorage.setItem('theme', theme);
      document.querySelector('.toggle-dark').textContent = theme === 'dark' ? '☀️' : '🌙';
      document.querySelector('.toggle-dark').setAttribute('aria-label', theme === 'dark' ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro');
    }

    function toggleDarkMode() {
      const currentTheme = document.body.getAttribute('data-theme');
      const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
      setTheme(newTheme);
    }

    // Cargar tema guardado o preferencia del sistema
    const savedTheme = localStorage.getItem('theme');
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    if (savedTheme) {
      setTheme(savedTheme);
    } else if (systemPrefersDark) {
      setTheme('dark');
    }

    // ===================== CHAT =====================
    function scrollToBottom() {
      const chatBox = document.getElementById('chatBox');
      if (chatBox) {
        chatBox.scrollTop = chatBox.scrollHeight;
      }
    }

    function mostrarEscribiendo() {
      const indicator = document.getElementById('typingIndicator');
      if (indicator) {
        indicator.style.display = 'flex';
        scrollToBottom();
      }
    }

    function ocultarEscribiendo() {
      const indicator = document.getElementById('typingIndicator');
      if (indicator) {
        indicator.style.display = 'none';
      }
    }

    function sanitizarTexto(texto) {
      const div = document.createElement('div');
      div.textContent = texto;
      return div.innerHTML;
    }

    // Función actualizada para solicitar cita
    function solicitarCita() {
      mostrarEscribiendo();
      
      // Establecer el valor del campo oculto a "true"
      document.getElementById('solicitarCitaHidden').value = "true";
      
      // Enviar el formulario
      document.querySelector('form').submit();
    }

    // Reiniciar chat 
    async function reiniciarChat() {
      mostrarEscribiendo();
      const btn = event.target.closest('button') || event.target;
      const originalText = btn.innerHTML;
      btn.innerHTML = 'Reiniciando... <span class="loading"></span>';
      btn.disabled = true;
      
      try {
        const response = await fetch('/reset', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': window.__CSRF_TOKEN__
          },
          credentials: 'same-origin'
        });
        
        if (response.ok) {
          window.location.href = '/';
        } else {
          throw new Error('Error en la respuesta del servidor');
        }
      } catch (error) {
        console.error('Error:', error);
        alert('Error al reiniciar. Intenta recargar la página.');
      } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
        ocultarEscribiendo();
      }
    }

    // Cancelar cita 
    async function cancelarCita() {
      mostrarEscribiendo();
      
      try {
        const response = await fetch('/cancelar_cita', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': window.__CSRF_TOKEN__
          }
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
          window.location.href = '/';
        } else {
          throw new Error(data.message || 'Error al cancelar la cita');
        }
      } catch (error) {
        console.error('Error:', error);
        alert('Error al cancelar la cita. Intenta recargar la página.');
        window.location.href = '/';
      } finally {
        ocultarEscribiendo();
      }
    }

    // ===================== HORARIOS MEJORADOS =====================
    const horariosPorDia = {
      0: ["14:00", "15:00", "16:00", "17:00", "18:00", "19:00"],
      1: ["14:00", "15:00", "16:00", "17:00", "18:00", "19:00"],
      2: ["14:00", "15:00", "16:00", "17:00", "18:00", "19:00"],
      3: ["14:00", "15:00", "16:00", "17:00", "18:00", "19:00"],
      4: ["14:00", "15:00", "16:00", "17:00", "18:00", "19:00"],
      5: ["08:00", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00"],
      6: []
    };

    const fechaCitaInput = document.querySelector('input[name="fecha_cita"]');
    const selectDesktop = document.getElementById('selectHorariosDesktop');
    const botonesMobile = document.getElementById('botonesHorariosMobile');
    const horaSeleccionadaInput = document.getElementById('horaSeleccionada');
    const sinAtencion = document.getElementById("sinAtencion");
    const cargandoHorarios = document.getElementById("cargandoHorarios");
    const citaForm = document.getElementById("citaForm");

    // Cache para horarios ya verificados
    const horariosCache = new Map();

    async function fetchWithRetry(url, options, maxRetries = 3) {
      for (let i = 0; i < maxRetries; i++) {
        try {
          const response = await fetch(url, options);
          
          if (response.status === 429) {
            const waitTime = Math.pow(2, i) * 1000;
            await new Promise(resolve => setTimeout(resolve, waitTime));
            continue;
          }
          
          return response;
        } catch (error) {
          if (i === maxRetries - 1) throw error;
          await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1)));
        }
      }
    }

    async function verificarDisponibilidad(fecha, hora) {
      try {
        const response = await fetchWithRetry('/verificar-horario', {
          method: 'POST',
          headers: { 
            'Content-Type': 'application/json',
            'X-CSRFToken': window.__CSRF_TOKEN__
          },
          body: JSON.stringify({ fecha, hora })
        });
        
        if (response.status === 429) {
          throw new Error('Demasiadas solicitudes. Por favor espera un momento.');
        }
        
        if (!response.ok) {
          throw new Error('Error al verificar disponibilidad');
        }
        
        return await response.json();
      } catch (error) {
        console.error('Error:', error);
        return { 
          disponible: false, 
          mensaje: error.message || 'Error al verificar disponibilidad' 
        };
      }
    }

    function actualizarInterfazHorarios(horarios) {
        const selectDesktop = document.getElementById('selectHorariosDesktop');
        const contenedorMobile = document.getElementById('botonesHorariosMobile');
        
        // Limpiar interfaces
        selectDesktop.innerHTML = '<option value="" disabled selected>Selecciona una hora</option>';
        contenedorMobile.innerHTML = '';
        
        // Variable para controlar selección única
        let horaYaSeleccionada = false;
        
        horarios.forEach(({ hora, disponible }) => {
            // ===== PARA DESKTOP (Select) =====
            const option = document.createElement('option');
            option.value = hora;
            option.textContent = disponible ? `${hora} ✔ Disponible` : `${hora} ✖ Ocupado`;
            option.disabled = !disponible;
            option.classList.add(disponible ? 'hora-disponible' : 'hora-ocupada');
            selectDesktop.appendChild(option);
            
            // ===== PARA MÓVIL (Botones) =====
            const boton = document.createElement('button');
            boton.type = 'button';
            boton.className = `boton-hora ${disponible ? 'disponible' : 'ocupado'}`;
            boton.textContent = disponible ? `${hora} ✔` : `${hora} ✖`;
            boton.dataset.hora = hora;
            boton.disabled = !disponible;
            
            if (disponible) {
                boton.addEventListener('click', function() {
                    // Prevenir doble selección
                    if (horaYaSeleccionada) {
                        document.querySelectorAll('.boton-hora.seleccionado').forEach(btn => {
                            btn.classList.remove('seleccionado');
                        });
                        horaYaSeleccionada = false;
                    }
                    
                    // Seleccionar este botón
                    this.classList.add('seleccionado');
                    document.getElementById('horaSeleccionada').value = this.dataset.hora;
                    horaYaSeleccionada = true;
                    
                    // También actualizar el select de desktop
                    selectDesktop.value = this.dataset.hora;
                });
            }
            
            contenedorMobile.appendChild(boton);
        });
        
        // Habilitar interfaces
        selectDesktop.disabled = horarios.length === 0;
        
        // Actualizar el select desktop cuando cambie
        selectDesktop.addEventListener('change', function() {
            document.getElementById('horaSeleccionada').value = this.value;
            
            // Actualizar botones móvil
            document.querySelectorAll('.boton-hora').forEach(boton => {
                boton.classList.remove('seleccionado');
                if (boton.dataset.hora === this.value) {
                    boton.classList.add('seleccionado');
                }
            });
        });

        // Ajustar interfaz según dispositivo
        ajustarInterfazHorarios();
    }

    function ajustarInterfazHorarios() {
        const isMobile = window.innerWidth <= 768;
        const selectDesktop = document.getElementById('selectHorariosDesktop');
        const botonesMobile = document.getElementById('botonesHorariosMobile');
        
        if (isMobile) {
            selectDesktop.style.display = 'none';
            botonesMobile.style.display = 'grid';
        } else {
            selectDesktop.style.display = 'block';
            botonesMobile.style.display = 'none';
        }
    }

    function mostrarError(mensaje) {
      const errorDiv = document.createElement('div');
      errorDiv.className = 'error-message';
      errorDiv.style.cssText = 'display: block; padding: 10px; margin: 10px 0; background: #ffebee; border: 1px solid #f44336; border-radius: 8px; color: #d32f2f;';
      errorDiv.textContent = mensaje;
      
      const form = document.querySelector('form');
      if (form) {
        form.insertBefore(errorDiv, form.firstChild);
        
        setTimeout(() => {
          errorDiv.remove();
        }, 5000);
      }
    }

    async function cargarHorariosDisponibles(fecha) {
      if (!fecha) return;
      
      if (horariosCache.has(fecha)) {
        const cached = horariosCache.get(fecha);
        actualizarInterfazHorarios(cached);
        return;
      }
      
      const fechaObj = new Date(fecha);
      const dia = fechaObj.getDay();

      if (selectDesktop) selectDesktop.disabled = true;
      if (cargandoHorarios) cargandoHorarios.style.display = "block";
      if (sinAtencion) sinAtencion.style.display = "none";

      if (dia === 6) {
        if (selectDesktop) {
          selectDesktop.innerHTML = '<option value="" disabled selected>🚫 No hay atención los domingos</option>';
          selectDesktop.disabled = true;
        }
        if (botonesMobile) {
          botonesMobile.innerHTML = '<button type="button" class="boton-hora ocupado" disabled>🚫 No hay atención</button>';
        }
        if (sinAtencion) sinAtencion.style.display = "block";
        if (cargandoHorarios) cargandoHorarios.style.display = "none";
        return;
      }

      const opciones = horariosPorDia[dia] || [];
      let horariosDisponibles = [];
      
      try {
        for (const hora of opciones) {
          try {
            const { disponible } = await verificarDisponibilidad(fecha, hora);
            horariosDisponibles.push({ hora, disponible });
          } catch (error) {
            console.error(`Error verificando hora ${hora}:`, error);
            horariosDisponibles.push({ hora, disponible: false, error: true });
          }
        }
        
        horariosCache.set(fecha, horariosDisponibles);
        actualizarInterfazHorarios(horariosDisponibles);
        
      } catch (error) {
        console.error('Error cargando horarios:', error);
        mostrarError('Error al cargar horarios. Intenta nuevamente.');
      } finally {
        if (cargandoHorarios) cargandoHorarios.style.display = "none";
      }
    }

    // Detectar cambios de tamaño para alternar interfaces
    window.addEventListener('resize', function() {
        ajustarInterfazHorarios();
    });

    if (fechaCitaInput) {
      fechaCitaInput.addEventListener("change", async function() {
        if (this.value) await cargarHorariosDisponibles(this.value);
      });

      fechaCitaInput.addEventListener('input', function() {
        if (this.value) {
          const fecha = new Date(this.value + 'T00:00');
          if (fecha.getDay() === 0) {
            this.value = "";
            if (selectDesktop) {
              selectDesktop.innerHTML = '<option value="" disabled selected>🚫 No hay atención los domingos</option>';
              selectDesktop.disabled = true;
            }
            if (botonesMobile) {
              botonesMobile.innerHTML = '<button type="button" class="boton-hora ocupado" disabled>🚫 No hay atención</button>';
            }
            if (sinAtencion) sinAtencion.style.display = "block";
            if (cargandoHorarios) cargandoHorarios.style.display = "none";
          }
        }
      });

      citaForm?.addEventListener('submit', async function(e) {
        e.preventDefault(); // Prevenir envío tradicional
        
        const horaSeleccionada = horaSeleccionadaInput.value;
        const fecha = fechaCitaInput.value;
        const telefono = telefonoInput.value;
        
        if (!horaSeleccionada || !fecha || !telefono) {
          alert('Por favor completa todos los campos requeridos.');
          return;
        }
        
        // Validar teléfono localmente primero
        if (!validarTelefono(telefono)) {
          telefonoInput.classList.add('error');
          if (telefonoError) telefonoError.style.display = 'block';
          telefonoInput.focus();
          return;
        }
        
        // Verificar disponibilidad final
        const { disponible, mensaje } = await verificarDisponibilidad(fecha, horaSeleccionada);
        if (!disponible) {
          alert(`No se puede agendar: ${mensaje || 'El horario ya está ocupado'}`);
          await cargarHorariosDisponibles(fecha);
          return;
        }
        
        // Mostrar indicador de carga
        const submitBtn = document.getElementById('submitCita');
        const originalText = submitBtn.value;
        submitBtn.value = 'Agendando...';
        submitBtn.disabled = true;
        
        try {
          // Enviar datos al endpoint real
          const response = await fetch('/agendar-cita', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': window.__CSRF_TOKEN__
            },
            body: JSON.stringify({
              fecha: fecha,
              hora: horaSeleccionada,
              telefono: telefono,
              sintoma: window.__SINTOMA_ACTUAL__
            })
          });
          
          const data = await response.json();
          
          if (response.ok) {
            // Éxito: redirigir a la página principal para mostrar estado final
            window.location.href = "/";
          } else {
            // Error: mostrar mensaje específico
            alert(`Error: ${data.error || 'No se pudo agendar la cita'}`);
            submitBtn.value = originalText;
            submitBtn.disabled = false;
          }
        } catch (error) {
          console.error('Error:', error);
          alert('Error de conexión. Por favor intenta nuevamente.');
          submitBtn.value = originalText;
          submitBtn.disabled = false;
        }
      });

      if (fechaCitaInput.value) {
        cargarHorariosDisponibles(fechaCitaInput.value);
      }
    }

    // Inicializar interfaz de horarios al cargar
    document.addEventListener('DOMContentLoaded', function() {
        ajustarInterfazHorarios();
    });

    // ===================== VALIDACIÓN DE TELÉFONO =====================
    const telefonoInput = document.getElementById('telefonoInput');
    const telefonoError = document.getElementById('telefonoError');

    function validarTelefono(telefono) {
      const regex = /^09\d{8}$/;
      return regex.test(telefono);
    }

    if (telefonoInput) {
      telefonoInput.addEventListener('input', function() {
        const valor = this.value.replace(/\D/g, '');
        this.value = valor;
        
        if (!validarTelefono(valor)) {
          this.classList.add('error');
          if (telefonoError) telefonoError.style.display = 'block';
        } else {
          this.classList.remove('error');
          if (telefonoError) telefonoError.style.display = 'none';
        }
      });

      citaForm?.addEventListener('submit', function(e) {
        if (!validarTelefono(telefonoInput.value)) {
          e.preventDefault();
          telefonoInput.classList.add('error');
          if (telefonoError) telefonoError.style.display = 'block';
          telefonoInput.focus();
        }
      });

      telefonoInput.addEventListener('focus', function() {
        if (!validarTelefono(this.value)) {
          this.classList.add('error');
          if (telefonoError) telefonoError.style.display = 'block';
        }
      });

      telefonoInput.addEventListener('blur', function() {
        if (validarTelefono(this.value)) {
          this.classList.remove('error');
          if (telefonoError) telefonoError.style.display = 'none';
        }
      });
    }

    // Script para mejorar la experiencia táctil en móviles
    document.addEventListener('DOMContentLoaded', function() {
      const progressContainer = document.querySelector('.progress-container');
      
      if (progressContainer) {
        const activeStep = document.querySelector('.step.active');
        if (activeStep && window.innerWidth < 768) {
          setTimeout(() => {
            progressContainer.scrollTo({
              left: activeStep.offsetLeft - progressContainer.offsetWidth / 2 + activeStep.offsetWidth / 2,
              behavior: 'smooth'
            });
          }, 300);
        }

        let isDragging = false;
        let startX;
        let scrollLeft;

        progressContainer.addEventListener('mousedown', (e) => {
          isDragging = true;
          startX = e.pageX - progressContainer.offsetLeft;
          scrollLeft = progressContainer.scrollLeft;
          progressContainer.style.cursor = 'grabbing';
        });

        progressContainer.addEventListener('mouseleave', () => {
          isDragging = false;
          progressContainer.style.cursor = 'grab';
        });

        progressContainer.addEventListener('mouseup', () => {
          isDragging = false;
          progressContainer.style.cursor = 'grab';
        });

        progressContainer.addEventListener('mousemove', (e) => {
          if (!isDragging) return;
          e.preventDefault();
          const x = e.pageX - progressContainer.offsetLeft;
          const walk = (x - startX) * 2;
          progressContainer.scrollLeft = scrollLeft - walk;
        });

        progressContainer.addEventListener('touchstart', (e) => {
          startX = e.touches[0].pageX - progressContainer.offsetLeft;
          scrollLeft = progressContainer.scrollLeft;
        }, { passive: true });

        progressContainer.addEventListener('touchmove', (e) => {
          if (e.touches.length !== 1) return;
          const x = e.touches[0].pageX - progressContainer.offsetLeft;
          const walk = (x - startX) * 2;
          progressContainer.scrollLeft = scrollLeft - walk;
        }, { passive: true });
      }
    });

    const touchElements = document.querySelectorAll('button, input[type="submit"], label');
    touchElements.forEach(el => {
      el.addEventListener('touchstart', () => {
        el.style.transform = 'scale(0.98)';
      }, { passive: true });
      
      el.addEventListener('touchend', () => {
        el.style.transform = 'scale(1)';
      }, { passive: true });
    });

    document.addEventListener('dblclick', (e) => {
      e.preventDefault();
    }, { passive: false });

    
    // if (window.innerWidth < 600 && document.querySelector('input[name="fecha_cita"]')) {
    //   document.querySelector('input[name="fecha_cita"]').type = 'datetime-local';
    // }

    window.addEventListener('resize', () => {
      if (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA') {
        document.activeElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    });

    if (document.getElementById('typingIndicator')) {
      setTimeout(() => {
        scrollToBottom();
      }, 100);
    }

    document.getElementById('sintomasForm')?.addEventListener('submit', function(e) {
      const seleccionado = document.querySelector('input[name="sintomas"]:checked');
      if (!seleccionado) {
        e.preventDefault();
        alert('Por favor selecciona un síntoma para continuar');
      }
    });

    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') {
        reiniciarChat();
      }
      if (e.key === 'Enter' && e.ctrlKey) {
        const submitBtn = document.querySelector('form input[type="submit"], form button[type="submit"]');
        if (submitBtn) {
          submitBtn.click();
        }
      }
    });

    window.addEventListener('load', () => {
      setTimeout(() => {
        scrollToBottom();
      }, 300);
    });

    window.addEventListener('beforeunload', function() {
      const elements = document.querySelectorAll('button, input, textarea, select');
      elements.forEach(el => {
        const newEl = el.cloneNode(true);
        el.parentNode.replaceChild(newEl, el);
      });
    });