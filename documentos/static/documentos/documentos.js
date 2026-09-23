/*
 * Gestão Rural — proteção VISUAL contra clique duplo (GR-14).
 *
 * Só age em formulários marcados com data-submit-lock: no primeiro submit,
 * desabilita o botão e troca o texto (data-submit-texto). O POST continua
 * sendo um envio HTML normal; sem JavaScript tudo funciona igual.
 *
 * A proteção real contra processamento concorrente é da GR-12
 * (transaction.atomic + select_for_update em documentos/processamento.py).
 */
(function () {
  "use strict";

  var SELETOR_FORM = "form[data-submit-lock]";

  function botaoDoFormulario(form) {
    return form.querySelector('button[type="submit"]');
  }

  function travar(form) {
    var botao = botaoDoFormulario(form);
    form.setAttribute("data-enviando", "true");
    if (!botao) {
      return;
    }
    if (!botao.hasAttribute("data-texto-original")) {
      botao.setAttribute("data-texto-original", botao.textContent);
    }
    var texto = form.getAttribute("data-submit-texto");
    if (texto) {
      botao.textContent = texto;
    }
    botao.disabled = true;
    botao.setAttribute("aria-busy", "true");
  }

  function destravar(form) {
    var botao = botaoDoFormulario(form);
    form.removeAttribute("data-enviando");
    if (!botao) {
      return;
    }
    if (botao.hasAttribute("data-texto-original")) {
      botao.textContent = botao.getAttribute("data-texto-original");
    }
    botao.disabled = false;
    botao.removeAttribute("aria-busy");
  }

  function aoEnviar(evento) {
    var form = evento.currentTarget;
    if (form.getAttribute("data-enviando") === "true") {
      // Segundo envio (ex.: Enter repetido) enquanto o primeiro está em curso.
      evento.preventDefault();
      return;
    }
    // Não cancela o primeiro envio: o navegador segue com o POST normal.
    travar(form);
  }

  function formularios() {
    return document.querySelectorAll(SELETOR_FORM);
  }

  function iniciar() {
    Array.prototype.forEach.call(formularios(), function (form) {
      form.addEventListener("submit", aoEnviar);
    });
  }

  // Voltar pelo histórico pode restaurar a página com o botão travado.
  window.addEventListener("pageshow", function (evento) {
    if (evento.persisted) {
      Array.prototype.forEach.call(formularios(), destravar);
    }
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }
})();
