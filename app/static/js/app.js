// JS mínimo; sem scripts inline (CSP).
document.addEventListener("DOMContentLoaded", function () {
  // Cor do avatar sem foto (atributo style inline é bloqueado pela CSP).
  document.querySelectorAll("[data-cor]").forEach(function (el) {
    el.style.backgroundColor = el.getAttribute("data-cor");
  });

  // Confirmação em formulários de ação.
  document.querySelectorAll("form[data-confirmar]").forEach(function (form) {
    form.addEventListener("submit", function (ev) {
      if (!window.confirm(form.getAttribute("data-confirmar"))) ev.preventDefault();
    });
  });

  // Evita duplo envio (ex.: duplo toque). A proteção real fica no servidor.
  document.querySelectorAll("form").forEach(function (form) {
    form.addEventListener("submit", function (ev) {
      if (ev.defaultPrevented) return;
      if (form.dataset.enviando) { ev.preventDefault(); return; }
      form.dataset.enviando = "1";
    });
  });
});
