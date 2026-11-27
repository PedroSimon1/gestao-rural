/*
 * Gestão Rural — conferência da nota: foco fora da barra de ações, soma das parcelas e resumo ao vivo.
 *
 * Só informa e rola a página: não altera valores, não envia nada e não substitui a validação do servidor.
 * Sem JavaScript a tela funciona igual (o aviso de soma fica oculto).
 */
(function () {
  "use strict";

  // A barra de ações fica fixa no rodapé e não pode cobrir o campo que recebeu o foco (WCAG 2.4.11): se cobrir,
  // rola o suficiente para o campo ficar acima dela. A margem de rolagem do CSS não basta com o campo já visível.
  var barra = document.querySelector(".acoes-rodape");
  if (barra) {
    document.addEventListener("focusin", function (evento) {
      var alvo = evento.target;
      if (!alvo || !alvo.getBoundingClientRect || barra.contains(alvo)) {
        return;
      }
      var campo = alvo.getBoundingClientRect();
      var faixa = barra.getBoundingClientRect();
      var cobre = campo.left < faixa.right && campo.right > faixa.left && campo.bottom > faixa.top && campo.top < faixa.bottom;
      if (cobre) {
        window.scrollBy(0, campo.bottom - faixa.top + 16);
      }
    });
  }

  // Campos dentro de um "Editar" fechado não aparecem; ao focar um deles (ex.: por erro), abre a linha.
  document.addEventListener("focusin", function (evento) {
    var linha = evento.target.closest ? evento.target.closest("details.editavel") : null;
    if (linha && !linha.open) {
      linha.open = true;
    }
  });

  var total = document.getElementById("id_valor_total");
  var aviso = document.querySelector("[data-soma-parcelas]");
  if (!total || !aviso) {
    return;
  }

  var situacao = aviso.querySelector("[data-soma-situacao]");
  var texto = aviso.querySelector("[data-soma-texto]");
  var resumoTotal = document.querySelector("[data-resumo-total]");
  var resumoSoma = document.querySelector("[data-resumo-soma]");
  var resumoFornecedor = document.querySelector("[data-resumo-fornecedor]");
  var fornecedor = document.getElementById("id_fornecedor_nome");
  var formato = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

  function centavos(valor) {
    var numero = parseFloat(String(valor).replace(",", "."));
    return isFinite(numero) ? Math.round(numero * 100) : 0;
  }

  function reais(emCentavos) {
    return formato.format(emCentavos / 100);
  }

  function campoDeParcela(elemento) {
    return elemento && /^parcelas-\d+-valor$/.test(elemento.name || "");
  }

  function atualizar() {
    var soma = 0;
    Array.prototype.forEach.call(document.querySelectorAll('input[name^="parcelas-"]'), function (campo) {
      if (campoDeParcela(campo)) {
        soma += centavos(campo.value);
      }
    });
    var alvo = centavos(total.value);
    var confere = soma === alvo;

    aviso.hidden = false;
    situacao.className = "st " + (confere ? "st--ok" : "st--erro");
    situacao.textContent = confere ? "OK" : "Diferença";
    texto.textContent = confere
      ? "A soma das parcelas confere com o total."
      : "A soma das parcelas difere do total em " + reais(Math.abs(soma - alvo)) + ".";

    if (resumoTotal) {
      resumoTotal.textContent = total.value === "" ? "—" : reais(alvo);
    }
    if (resumoSoma) {
      resumoSoma.textContent = reais(soma);
    }
    if (resumoFornecedor && fornecedor) {
      resumoFornecedor.textContent = fornecedor.value || "—";
    }
  }

  document.addEventListener("input", function (evento) {
    var alvo = evento.target;
    if (alvo === total || alvo === fornecedor || campoDeParcela(alvo)) {
      atualizar();
    }
  });

  atualizar();
})();
