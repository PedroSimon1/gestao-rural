"use strict";
document.querySelectorAll("[data-parcelas-manuais]").forEach((form) => {
  const total = form.querySelector('[name="parcelas-TOTAL_FORMS"]');
  const lista = form.querySelector("[data-lista-parcelas]");
  const modelo = form.querySelector("[data-nova-parcela]");
  const adicionar = form.querySelector("[data-adicionar-parcela]");
  const aviso = form.querySelector("[data-aviso-parcelas]");
  const limite = Number(form.dataset.limite);
  adicionar.addEventListener("click", () => {
    const indice = Number(total.value);
    if (!Number.isInteger(indice) || indice >= limite) {
      aviso.textContent = `Limite de ${limite} linhas. Para reutilizar uma linha, desmarque sua remoção e altere os dados.`;
      return;
    }
    const copia = document.createElement("template");
    copia.innerHTML = modelo.innerHTML.replaceAll("__prefix__", String(indice));
    lista.append(copia.content.cloneNode(true));
    total.value = String(indice + 1);
    aviso.textContent = `${indice + 1} linha(s) de parcela no formulário.`;
  });
});
