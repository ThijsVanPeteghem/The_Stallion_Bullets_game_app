(() => {
  const chart = document.querySelector("[data-player-progress-chart]");
  const dataElement = document.getElementById("player-progress-chart-data");
  const legend = document.querySelector("[data-player-progress-legend]");
  const visibilityControls = document.querySelectorAll(
    "[data-player-progress-control]",
  );
  if (!chart || !dataElement || !legend) return;

  const data = JSON.parse(dataElement.textContent);
  if (!data.block_rounds.length || !data.players.length) return;

  const namespace = "http://www.w3.org/2000/svg";
  const width = 900;
  const height = 360;
  const margins = { top: 18, right: 20, bottom: 42, left: 52 };
  const plotWidth = width - margins.left - margins.right;
  const plotHeight = height - margins.top - margins.bottom;
  const lastRound = Math.max(1, data.block_rounds.at(-1));
  const maxMatches = Math.max(1, data.max_matches);
  const colors = [
    "#903726",
    "#16796c",
    "#b36b16",
    "#405f91",
    "#718d2d",
    "#9b4777",
    "#087d9a",
    "#ba4934",
  ];
  const x = (round) => margins.left + (round / lastRound) * plotWidth;
  const y = (matches) =>
    margins.top + ((maxMatches - matches) / maxMatches) * plotHeight;
  const createSvgElement = (name, attributes = {}) => {
    const element = document.createElementNS(namespace, name);
    for (const [key, value] of Object.entries(attributes)) {
      element.setAttribute(key, value);
    }
    return element;
  };
  const addText = (content, attributes = {}) => {
    const text = createSvgElement("text", attributes);
    text.textContent = content;
    chart.append(text);
  };
  const setPlayerVisibility = (button, group, visible) => {
    button.setAttribute("aria-pressed", String(visible));
    group.style.display = visible ? "" : "none";
  };

  for (let count = 0; count <= maxMatches; count += 1) {
    const position = y(count);
    chart.append(
      createSvgElement("line", {
        x1: margins.left,
        y1: position,
        x2: width - margins.right,
        y2: position,
        class: "chart-grid",
      }),
    );
    addText(String(count), {
      x: margins.left - 10,
      y: position + 4,
      class: "chart-label",
      "text-anchor": "end",
    });
  }

  chart.append(
    createSvgElement("line", {
      x1: margins.left,
      y1: margins.top,
      x2: margins.left,
      y2: height - margins.bottom,
      class: "chart-axis",
    }),
    createSvgElement("line", {
      x1: margins.left,
      y1: height - margins.bottom,
      x2: width - margins.right,
      y2: height - margins.bottom,
      class: "chart-axis",
    }),
  );

  for (const round of data.block_rounds) {
    addText(String(round), {
      x: x(round),
      y: height - margins.bottom + 22,
      class: "chart-label",
      "text-anchor": "middle",
    });
  }

  const playerVisibility = [];
  data.players.forEach((player, index) => {
    const color = colors[index % colors.length];
    const group = createSvgElement("g", { "data-player-id": player.id });
    const points = player.values
      .map((value, pointIndex) => `${x(data.block_rounds[pointIndex])},${y(value)}`)
      .join(" ");
    group.append(
      createSvgElement("polyline", {
        points,
        class: "chart-line",
        stroke: color,
      }),
    );
    player.values.forEach((value, pointIndex) => {
      group.append(
        createSvgElement("circle", {
          cx: x(data.block_rounds[pointIndex]),
          cy: y(value),
          r: 2.5,
          fill: color,
          class: "chart-point",
        }),
      );
    });
    chart.append(group);

    const button = document.createElement("button");
    button.type = "button";
    button.setAttribute("aria-pressed", "true");
    button.dataset.playerId = player.id;
    const swatch = document.createElement("span");
    swatch.className = "player-progress-legend-swatch";
    swatch.style.backgroundColor = color;
    button.append(swatch, document.createTextNode(player.name));
    button.addEventListener("click", () => {
      const visible = button.getAttribute("aria-pressed") !== "true";
      setPlayerVisibility(button, group, visible);
    });
    legend.append(button);
    playerVisibility.push({ button, group });
  });

  visibilityControls.forEach((control) => {
    control.addEventListener("click", () => {
      const visible = control.dataset.playerProgressControl === "show";
      playerVisibility.forEach(({ button, group }) => {
        setPlayerVisibility(button, group, visible);
      });
    });
  });
})();