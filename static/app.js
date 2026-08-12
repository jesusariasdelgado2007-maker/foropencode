document.addEventListener("DOMContentLoaded", function () {
  const modal = document.getElementById("modal");
  const modalBody = document.getElementById("modal-body");

  function closeModal() {
    if (modal.open) modal.close();
  }
  document.querySelectorAll("[data-close]").forEach(function (el) {
    el.addEventListener("click", closeModal);
  });
  modal.addEventListener("click", function (e) {
    if (e.target === modal) closeModal();
  });

  function openForm(templateId, button) {
    const tpl = document.getElementById(templateId);
    if (!tpl) return;
    modalBody.innerHTML = tpl.innerHTML;
    const form = modalBody.querySelector("form");
    if (!form) return;

    if (button && button.dataset.id) {
      const formId = form.id || "";
      const fields = {
        nombre: "nombre", email: "email", telefono: "telefono", cargo: "cargo",
        empresa: "empresa_id", notas: "notas",
        sector: "sector", web: "web", direccion: "direccion",
        titulo: "titulo", valor: "valor", etapa: "etapa", fecha: "fecha_cierre",
        desc: "descripcion", contacto: "contacto_id", hora: "hora",
        fechaCierre: "fecha_cierre"
      };
      const idField = form.querySelector('input[name="id"]');
      if (idField) idField.value = button.dataset.id;

      if (formId.includes("contacto")) {
        form.querySelector('input[name="nombre"]').value = button.dataset.nombre || "";
        form.querySelector('input[name="email"]').value = button.dataset.email || "";
        form.querySelector('input[name="telefono"]').value = button.dataset.telefono || "";
        form.querySelector('input[name="cargo"]').value = button.dataset.cargo || "";
        form.querySelector('input[name="empresa_nombre"]').value = button.dataset.empresaNombre || "";
        form.querySelector('textarea[name="notas"]').value = button.dataset.notas || "";
      } else if (formId.includes("empresa")) {
        form.querySelector('input[name="nombre"]').value = button.dataset.nombre || "";
        form.querySelector('input[name="sector"]').value = button.dataset.sector || "";
        form.querySelector('input[name="telefono"]').value = button.dataset.telefono || "";
        form.querySelector('input[name="email"]').value = button.dataset.email || "";
        form.querySelector('input[name="web"]').value = button.dataset.web || "";
        form.querySelector('input[name="direccion"]').value = button.dataset.direccion || "";
        form.querySelector('textarea[name="notas"]').value = button.dataset.notas || "";
      } else if (formId.includes("venta")) {
        form.querySelector('input[name="titulo"]').value = button.dataset.titulo || "";
        form.querySelector('input[name="valor"]').value = button.dataset.valor || "";
        form.querySelector('select[name="etapa"]').value = button.dataset.etapa || "";
        form.querySelector('select[name="empresa_id"]').value = button.dataset.empresa || "";
        form.querySelector('select[name="contacto_id"]').value = button.dataset.contacto || "";
        form.querySelector('input[name="fecha_cierre"]').value = button.dataset.fecha || "";
        form.querySelector('textarea[name="descripcion"]').value = button.dataset.desc || "";
      } else if (formId.includes("cita")) {
        form.querySelector('input[name="titulo"]').value = button.dataset.titulo || "";
        form.querySelector('input[name="fecha"]').value = button.dataset.fecha || "";
        form.querySelector('input[name="hora"]').value = button.dataset.hora || "";
        form.querySelector('select[name="contacto_id"]').value = button.dataset.contacto || "";
        form.querySelector('select[name="empresa_id"]').value = button.dataset.empresa || "";
        form.querySelector('textarea[name="descripcion"]').value = button.dataset.desc || "";
      } else if (formId.includes("plantilla")) {
        form.querySelector('input[name="nombre"]').value = button.dataset.nombre || "";
        form.querySelector('select[name="canal"]').value = button.dataset.canal || "";
        form.querySelector('input[name="asunto"]').value = button.dataset.asunto || "";
        form.querySelector('textarea[name="cuerpo"]').value = button.dataset.cuerpo || "";
        form.querySelector('input[name="activa"]').checked = button.dataset.activa === "1";
      } else if (formId.includes("plan")) {
        form.querySelector('input[name="nombre"]').value = button.dataset.nombre || "";
        form.querySelector('input[name="precio_mensual"]').value = button.dataset.precioMensual || "";
        form.querySelector('input[name="precio_anual"]').value = button.dataset.precioAnual || "";
        form.querySelector('input[name="limite_usuarios"]').value = button.dataset.limiteUsuarios || "";
        form.querySelector('input[name="limite_contactos"]').value = button.dataset.limiteContactos || "";
        form.querySelector('textarea[name="descripcion"]').value = button.dataset.descripcion || "";
        form.querySelector('input[name="activo"]').checked = button.dataset.activo === "1";
      }

      form.querySelector("h3").textContent = "Editar";
      form.action = form.action.replace("/nueva", "/" + button.dataset.id + "/editar");
    } else {
      form.querySelector("h3").textContent = form.querySelector("h3").textContent.replace("Editar", "");
    }

    modalBody.querySelectorAll("[data-close]").forEach(function (el) {
      el.addEventListener("click", closeModal);
    });
    if (!modal.open) modal.showModal();
  }

  document.querySelectorAll("[data-open-form]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      openForm(btn.dataset.openForm, btn);
    });
  });
});
