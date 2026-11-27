
/*
 * Gestão Rural — proteção VISUAL contra clique duplo.
 *
 * Só age em formulários marcados com data-submit-lock: no primeiro submit,
 * trava o botão que foi acionado e troca o texto dele (data-submit-texto no
 * botão ou, se faltar, no formulário), indicando que o processamento está em
 * andamento. Um segundo envio enquanto o primeiro está em curso é ignorado.
 * O POST continua sendo um envio HTML normal; sem JavaScript tudo funciona igual.
 */
(function () {
  "use strict";

  var SELETOR_FORM = "form[data-submit-lock]";

  // O botão acionado (pode estar fora do <form>, ligado por form="id"); sem ele, o primeiro de envio.
  function botaoAcionado(evento, form) {
    var acionado = evento.submitter;
    if (acionado && acionado.tagName === "BUTTON") {
      return acionado;
    }
    return form.querySelector('button[type="submit"]');
  }

  function botoesTravados(form) {
    return Array.prototype.filter.call(document.querySelectorAll("[data-texto-original]"), function (botao) {
      return botao.form === form;
    });
  }

  function travar(form, botao) {
    form.setAttribute("data-enviando", "true");
    // Aviso de espera (opcional): só existe nos formulários com [data-estado].
    var estado = form.querySelector("[data-estado]");
    if (estado) {
      estado.hidden = false;
    }
    if (!botao) {
      return;
    }
    if (!botao.hasAttribute("data-texto-original")) {
      botao.setAttribute("data-texto-original", botao.textContent);
    }
    var texto = botao.getAttribute("data-submit-texto") || form.getAttribute("data-submit-texto");
    if (texto) {
      botao.textContent = texto;
    }
    if (botao.name) {
      // O navegador monta os dados do envio depois deste evento e deixa de fora um botão desabilitado:
      // um botão com name (ex.: acao=salvar) precisa continuar habilitado para levar o seu valor.
      botao.setAttribute("aria-disabled", "true");
    } else {
      botao.disabled = true;
    }
    botao.setAttribute("aria-busy", "true");
  }

  function destravar(form) {
    form.removeAttribute("data-enviando");
    var aviso = form.querySelector("[data-estado]");
    if (aviso) {
      aviso.hidden = true;
    }
    botoesTravados(form).forEach(function (botao) {
      botao.textContent = botao.getAttribute("data-texto-original");
      botao.removeAttribute("data-texto-original");
      botao.disabled = false;
      botao.removeAttribute("aria-disabled");
      botao.removeAttribute("aria-busy");
    });
  }

  function aoEnviar(evento) {
    var form = evento.currentTarget;
    if (form.getAttribute("data-enviando") === "true") {
      // Segundo envio (ex.: Enter repetido) enquanto o primeiro está em curso.
      evento.preventDefault();
      return;
    }
    // Não cancela o primeiro envio: o navegador segue com o POST normal.
    travar(form, botaoAcionado(evento, form));
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
