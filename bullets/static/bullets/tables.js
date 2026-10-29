(() => {
  function sortValue(cell) {
    const text = (cell?.dataset.sortValue || cell?.innerText || "")
      .replace(/\s+/g, " ")
      .trim();
    if (!text || text === "-" || /^—(?:\s|$)/.test(text)) {
      return { empty: true, type: "text", value: "" };
    }

    const dateMatch = text.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (dateMatch) {
      return {
        empty: false,
        type: "number",
        value: new Date(dateMatch[3], dateMatch[2] - 1, dateMatch[1]).getTime(),
      };
    }

    const numberMatch = text.match(/^(-?\d+(?:[.,]\d+)?)(?:\s*\/\s*\d+)?(?:\s*\([^)]*\))?$/);
    if (numberMatch) {
      return {
        empty: false,
        type: "number",
        value: Number(numberMatch[1].replace(",", ".")),
      };
    }
    return { empty: false, type: "text", value: text };
  }

  function compareValues(left, right, direction) {
    if (left.empty || right.empty) {
      return left.empty === right.empty ? 0 : left.empty ? 1 : -1;
    }
    if (left.type === "number" && right.type === "number") {
      return (left.value - right.value) * direction;
    }
    return String(left.value).localeCompare(String(right.value), "nl", {
      numeric: true,
      sensitivity: "base",
    }) * direction;
  }

  function makeSortable(table) {
    const headers = [...table.tHead?.rows[0]?.cells || []];
    headers.forEach((header, columnIndex) => {
      const label = header.innerText.trim();
      if (!label || header.colSpan > 1) return;

      const button = document.createElement("button");
      button.type = "button";
      button.className = "table-sort-button";
      button.setAttribute("aria-label", `Sorteren op ${label}`);
      for (const child of [...header.childNodes]) button.append(child);

      const indicator = document.createElement("span");
      indicator.className = "table-sort-indicator";
      indicator.setAttribute("aria-hidden", "true");
      indicator.textContent = "↕";
      button.append(indicator);
      header.append(button);
      header.setAttribute("aria-sort", "none");

      button.addEventListener("click", () => {
        const rows = [...table.tBodies].flatMap((body) => [...body.rows]);
        const sameColumn = table.dataset.sortColumn === String(columnIndex);
        const previousDirection = table.dataset.sortDirection;
        const sample = rows.map((row) => sortValue(row.cells[columnIndex]))
          .find((value) => !value.empty);
        const direction = sameColumn
          ? previousDirection === "ascending" ? "descending" : "ascending"
          : sample?.type === "number" ? "descending" : "ascending";
        const multiplier = direction === "ascending" ? 1 : -1;

        const orderedRows = rows
          .map((row, index) => ({
            row,
            index,
            value: sortValue(row.cells[columnIndex]),
          }))
          .sort((left, right) =>
            compareValues(left.value, right.value, multiplier) || left.index - right.index
          )
          .map(({ row }) => row);

        if (table.tBodies[0]) table.tBodies[0].append(...orderedRows);
        table.dataset.sortColumn = String(columnIndex);
        table.dataset.sortDirection = direction;
        for (const cell of table.tHead.rows[0].cells) {
          cell.setAttribute("aria-sort", cell === header ? direction : "none");
        }
        indicator.textContent = direction === "ascending" ? "↑" : "↓";
      });
    });
  }

  function fallbackCopy(html) {
    const container = document.createElement("div");
    container.contentEditable = "true";
    container.style.cssText = "position:fixed;left:-10000px;top:0;width:1px;height:1px;overflow:hidden;";
    container.innerHTML = html;
    document.body.append(container);
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(container);
    selection.removeAllRanges();
    selection.addRange(range);
    const copied = document.execCommand("copy");
    selection.removeAllRanges();
    container.remove();
    if (!copied) throw new Error("Clipboard copy failed");
  }

  async function copyHtml(html, plainText) {
    if (navigator.clipboard?.write && typeof ClipboardItem !== "undefined") {
      try {
        await navigator.clipboard.write([
          new ClipboardItem({
            "text/html": new Blob([html], { type: "text/html" }),
            "text/plain": new Blob([plainText], { type: "text/plain" }),
          }),
        ]);
        return;
      } catch {
        fallbackCopy(html);
        return;
      }
    }
    fallbackCopy(html);
  }

  function wordpressTableHtml(table) {
    const clone = table.cloneNode(true);
    clone.querySelectorAll(".copy-only").forEach((cell) => {
      cell.classList.remove("copy-only");
      cell.style.removeProperty("display");
    });
    clone.querySelectorAll(".table-sort-button").forEach((button) => {
      const contents = document.createDocumentFragment();
      for (const child of [...button.childNodes]) {
        if (!child.classList?.contains("table-sort-indicator")) {
          contents.append(child.cloneNode(true));
        }
      }
      button.replaceWith(contents);
    });
    clone.style.borderCollapse = "collapse";
    clone.style.width = "100%";
    clone.querySelectorAll("th, td").forEach((cell) => {
      cell.style.border = "1px solid #d8c9c5";
      cell.style.padding = "7px";
      cell.style.textAlign = "left";
    });
    return clone;
  }

  function wordpressSlipHtml(slip) {
    const clone = slip.cloneNode(true);
    clone.querySelectorAll(".match-slip-copy").forEach((control) => control.remove());
    clone.className = "wordpress-match-slip";
    clone.style.cssText = "width:100%;margin:0 0 16px;padding:12px;border:1px solid #d8c9c5;";
    const meta = clone.querySelector(".slip-meta");
    if (meta) meta.style.cssText = "display:flex;justify-content:space-between;gap:10px;margin-bottom:8px;";
    const referee = clone.querySelector(".slip-referee");
    if (referee) referee.style.marginTop = "8px";
    const table = clone.querySelector(".slip-table");
    if (table) {
      table.style.cssText = "width:100%;border-collapse:collapse;";
      table.querySelectorAll("th, td").forEach((cell) => {
        cell.style.border = "1px solid #d8c9c5";
        cell.style.padding = "7px";
        cell.style.textAlign = "left";
      });
    }
    return clone;
  }

  function makeCopyable(table) {
    const host = table.closest(".table-wrap") || table;
    const control = document.createElement("div");
    control.className = "table-copy-control";
    const button = document.createElement("button");
    button.className = "button button-secondary";
    button.type = "button";
    button.textContent = "Tabel kopiëren";
    const status = document.createElement("span");
    status.className = "export-status";
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    control.append(button, status);
    host.parentNode.insertBefore(control, host.nextSibling);

    button.addEventListener("click", async () => {
      button.disabled = true;
      status.textContent = "Kopiëren...";
      try {
        const clone = wordpressTableHtml(table);
        const html = clone.outerHTML;
        const plainText = clone.innerText;
        await copyHtml(html, plainText);
        status.textContent = "Tabel gekopieerd.";
      } catch {
        status.textContent = "Kopiëren is niet gelukt. Probeer het opnieuw.";
      } finally {
        button.disabled = false;
      }
    });
  }

  async function copyWordPressExport(button) {
    const group = button.closest("[data-export-group]");
    const status = group?.querySelector("[data-export-status]");
    button.disabled = true;
    if (status) status.textContent = "Export voorbereiden...";
    try {
      const response = await fetch(button.dataset.wordpressExportUrl, {
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error("Export request failed");
      const html = await response.text();
      const plainText = new DOMParser().parseFromString(html, "text/html").body.innerText;
      await copyHtml(html, plainText);
      if (status) status.textContent = "Gekopieerd. Plak de tabellen in WordPress.";
    } catch {
      if (status) status.textContent = "Kopiëren is niet gelukt. Probeer het opnieuw.";
    } finally {
      button.disabled = false;
    }
  }

  document.querySelectorAll("table:not(.result-entry-table):not(.slip-table)")
    .forEach((table) => {
      makeSortable(table);
      makeCopyable(table);
    });
  document.querySelectorAll("[data-wordpress-export-url]").forEach((button) => {
    button.addEventListener("click", () => copyWordPressExport(button));
  });
  document.querySelectorAll("[data-copy-slips]").forEach((button) => {
    button.addEventListener("click", async () => {
      const status = document.querySelector("[data-copy-slips-status]");
      button.disabled = true;
      if (status) status.textContent = "Kopiëren...";
      try {
        const clones = [...document.querySelectorAll('.match-slip[data-complete="true"]')]
          .map(wordpressSlipHtml);
        if (!clones.length) throw new Error("No completed slips");
        const html = `<div>${clones.map((clone) => clone.outerHTML).join("\\n")}</div>`;
        const plainText = clones.map((clone) => clone.innerText).join("\n\n");
        await copyHtml(html, plainText);
        if (status) status.textContent = `${clones.length} ingevulde briefjes gekopieerd.`;
      } catch {
        if (status) status.textContent = "Kopiëren is niet gelukt. Probeer het opnieuw.";
      } finally {
        button.disabled = false;
      }
    });
  });
})();