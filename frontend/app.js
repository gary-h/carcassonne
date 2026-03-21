const state = {
  gameId: new URLSearchParams(window.location.search).get("game") || "",
  playerId: localStorage.getItem("carcassonne.playerId") || "",
  playerName: localStorage.getItem("carcassonne.playerName") || "",
  botCatalog: [],
  botSelections: [],
  rotation: 0,
  selectedMove: null,
  selectedFeatureId: "",
  lastGame: null,
  pollHandle: null,
};

const elements = {
  authPanel: document.getElementById("auth-panel"),
  gamePanel: document.getElementById("game-panel"),
  turnPanel: document.getElementById("turn-panel"),
  playerName: document.getElementById("player-name"),
  initialMeeples: document.getElementById("initial-meeples"),
  useVoidCards: document.getElementById("use-void-cards"),
  insertBot: document.getElementById("insert-bot"),
  botConfigList: document.getElementById("bot-config-list"),
  createGame: document.getElementById("create-game"),
  joinGameId: document.getElementById("join-game-id"),
  joinGame: document.getElementById("join-game"),
  gameIdLabel: document.getElementById("game-id-label"),
  copyLink: document.getElementById("copy-link"),
  lobbyActions: document.getElementById("lobby-actions"),
  startGame: document.getElementById("start-game"),
  turnBanner: document.getElementById("turn-banner"),
  playerList: document.getElementById("player-list"),
  remainingTiles: document.getElementById("remaining-tiles"),
  discardedTiles: document.getElementById("discarded-tiles"),
  currentTileImage: document.getElementById("current-tile-image"),
  currentTileName: document.getElementById("current-tile-name"),
  currentTileEdges: document.getElementById("current-tile-edges"),
  rotateLeft: document.getElementById("rotate-left"),
  rotateRight: document.getElementById("rotate-right"),
  selectionBox: document.getElementById("selection-box"),
  meepleSelect: document.getElementById("meeple-select"),
  submitMove: document.getElementById("submit-move"),
  messageLog: document.getElementById("message-log"),
  statusLine: document.getElementById("status-line"),
  board: document.getElementById("board"),
};

const standingMeeples = {
  red: "/assets/img/meeple/red_standing.png",
  blue: "/assets/img/meeple/blue_standing.png",
  green: "/assets/img/meeple/green_standing.png",
  yellow: "/assets/img/meeple/yellow_standing.png",
  black: "/assets/img/meeple/black_standing.png",
};

const lyingMeeples = {
  red: "/assets/img/meeple/red_lying.png",
  blue: "/assets/img/meeple/blue_lying.png",
  green: "/assets/img/meeple/green_lying.png",
  yellow: "/assets/img/meeple/yellow_lying.png",
  black: "/assets/img/meeple/black_lying.png",
};

const portVectors = {
  N: [0, -1],
  E: [1, 0],
  S: [0, 1],
  W: [-1, 0],
  Nw: [-0.55, -1],
  Ne: [0.55, -1],
  En: [1, -0.55],
  Es: [1, 0.55],
  Se: [0.55, 1],
  Sw: [-0.55, 1],
  Ws: [-1, 0.55],
  Wn: [-1, -0.55],
};

function init() {
  const storedGameId = localStorage.getItem("carcassonne.gameId") || "";
  if (state.gameId && storedGameId && storedGameId !== state.gameId) {
    state.playerId = "";
    localStorage.removeItem("carcassonne.playerId");
  }
  elements.playerName.value = state.playerName;
  elements.joinGameId.value = state.gameId;
  bindEvents();
  loadBotCatalog();
  if (state.gameId) {
    startPolling();
  }
}

function bindEvents() {
  elements.createGame.addEventListener("click", createGame);
  elements.joinGame.addEventListener("click", joinGame);
  elements.copyLink.addEventListener("click", copyLink);
  elements.insertBot.addEventListener("click", insertBotSelection);
  elements.startGame.addEventListener("click", startGame);
  elements.rotateLeft.addEventListener("click", () => rotate(-1));
  elements.rotateRight.addEventListener("click", () => rotate(1));
  elements.submitMove.addEventListener("click", submitMove);
  elements.meepleSelect.addEventListener("change", (event) => {
    state.selectedFeatureId = event.target.value || "";
  });
  document.addEventListener("keydown", (event) => {
    if (event.key.toLowerCase() === "r") {
      rotate(1);
    }
  });
}

async function createGame() {
  const rawName = elements.playerName.value.trim();
  const botCounts = currentBotCounts();
  const botTotal = Object.values(botCounts).reduce((sum, value) => sum + value, 0);
  const botOnly = rawName === "" && botTotal >= 2;
  const response = await fetchJson("/games/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      bot_counts: botCounts,
      bot_only: botOnly,
      initial_meeples: Number(elements.initialMeeples.value || 7),
      use_void_cards: elements.useVoidCards.checked,
    }),
  });
  state.gameId = response.game_id;
  updateUrl();
  if (botOnly) {
    state.playerId = "";
    state.playerName = "";
    localStorage.removeItem("carcassonne.playerId");
    render(response.game);
    startPolling();
    return;
  }
  await joinCurrentGame(rawName || "Player");
}

async function joinGame() {
  state.gameId = elements.joinGameId.value.trim();
  if (!state.gameId) {
    setStatus("Enter a game ID to join.");
    return;
  }
  updateUrl();
  await joinCurrentGame(normalizedPlayerName());
}

async function joinCurrentGame(name) {
  const response = await fetchJson(`/games/${state.gameId}/join`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  state.playerId = response.player_id;
  state.playerName = name;
  localStorage.setItem("carcassonne.playerId", state.playerId);
  localStorage.setItem("carcassonne.playerName", state.playerName);
  localStorage.setItem("carcassonne.gameId", state.gameId);
  render(response.game);
  startPolling();
}

function startPolling() {
  if (state.pollHandle) {
    clearInterval(state.pollHandle);
  }
  refreshGame();
  state.pollHandle = setInterval(refreshGame, 2000);
}

async function refreshGame() {
  if (!state.gameId) {
    return;
  }
  const suffix = state.playerId ? `?player_id=${encodeURIComponent(state.playerId)}` : "";
  const game = await fetchJson(`/games/${state.gameId}${suffix}`);
  render(game);
}

function render(game) {
  state.lastGame = game;
  elements.authPanel.classList.add("hidden");
  elements.gamePanel.classList.remove("hidden");
  elements.gameIdLabel.textContent = game.game_id;
  elements.remainingTiles.textContent = String(game.remaining_tiles);
  elements.discardedTiles.textContent = String(game.discarded_tiles);
  elements.statusLine.textContent = describeStatus(game);
  renderLobbyActions(game);
  renderPlayers(game);
  renderTurn(game);
  renderBoard(game);
  renderLog(game.messages || []);
}

function renderLobbyActions(game) {
  const canStart = game.status === "waiting"
    && game.host_player_id === state.playerId
    && game.players.length >= game.min_players_to_start;
  elements.lobbyActions.classList.toggle("hidden", !canStart);
  elements.startGame.disabled = !canStart;
}

function renderPlayers(game) {
  elements.playerList.innerHTML = "";
  for (const player of game.players) {
    const card = document.createElement("div");
    const isCurrent = game.current_player_id === player.id;
    const isViewer = state.playerId === player.id;
    card.className = `player-card${isCurrent ? " current" : ""}${isViewer ? " you" : ""}`;
    card.innerHTML = `
      <img class="avatar" src="${standingMeeples[player.color]}" alt="${player.color} meeple">
      <div>
        <strong>${escapeHtml(player.name)}${isViewer ? " (you)" : ""}${game.host_player_id === player.id ? " (host)" : ""}</strong>
        <div class="muted">Score ${player.score} · Meeples ${player.meeples_available}${player.is_bot ? ` · ${formatBotPolicy(player.bot_policy)}` : ""}</div>
      </div>
      <div>${isCurrent ? "Turn" : ""}</div>
    `;
    elements.playerList.appendChild(card);
  }
}

function renderTurn(game) {
  const turn = game.current_turn;
  const isViewerTurn = game.current_player_id && game.current_player_id === state.playerId;
  if (!turn) {
    elements.turnPanel.classList.add("hidden");
    if (game.status === "waiting") {
      const seatsOpen = game.max_players - game.players.length;
      if (game.players.length < game.min_players_to_start) {
        const needed = game.min_players_to_start - game.players.length;
        elements.turnBanner.textContent = `Waiting for ${needed} more player${needed === 1 ? "" : "s"} to join.`;
      } else if (game.host_player_id === state.playerId) {
        elements.turnBanner.textContent = `Lobby ready. Start now or wait for ${seatsOpen} more player${seatsOpen === 1 ? "" : "s"}.`;
      } else {
        elements.turnBanner.textContent = "Waiting for the host to start the game.";
      }
    } else {
      elements.turnBanner.textContent = "Game finished.";
    }
    return;
  }

  const availableMoves = turn.legal_moves.filter((move) => move.rotation === state.rotation);
  if (availableMoves.length === 0) {
    state.rotation = 0;
    state.selectedMove = null;
    state.selectedFeatureId = "";
  } else if (state.selectedMove) {
    const stillValid = availableMoves.find((move) => move.x === state.selectedMove.x && move.y === state.selectedMove.y);
    if (!stillValid) {
      state.selectedMove = null;
      state.selectedFeatureId = "";
    }
  }

  elements.turnPanel.classList.remove("hidden");
  elements.currentTileImage.src = turn.tile.image_path;
  elements.currentTileImage.style.transform = `rotate(${state.rotation * 90}deg)`;
  elements.currentTileName.textContent = turn.tile.name;
  elements.currentTileEdges.textContent = `Edges: ${Object.entries(turn.tile.edges).map(([side, kind]) => `${side}:${kind}`).join(" · ")}`;
  elements.turnBanner.textContent = isViewerTurn
    ? "Your turn. Rotate, select a highlighted cell, then place the tile."
    : "Opponent's turn. The board updates automatically.";
  elements.submitMove.disabled = !isViewerTurn || !state.selectedMove;
  elements.rotateLeft.disabled = !isViewerTurn;
  elements.rotateRight.disabled = !isViewerTurn;
  updateSelectionBox();
}

function renderBoard(game) {
  const { min_x, max_x, min_y, max_y } = game.viewport;
  const width = max_x - min_x + 1;
  const height = max_y - min_y + 1;
  elements.board.style.gridTemplateColumns = `repeat(${width}, var(--tile-size))`;
  elements.board.innerHTML = "";

  const tileByPosition = new Map(game.board.map((tile) => [`${tile.x},${tile.y}`, tile]));
  const legalMoves = new Map();
  if (game.current_turn && game.current_player_id === state.playerId) {
    for (const move of game.current_turn.legal_moves.filter((move) => move.rotation === state.rotation)) {
      legalMoves.set(`${move.x},${move.y}`, move);
    }
  }

  for (let y = min_y; y <= max_y; y += 1) {
    for (let x = min_x; x <= max_x; x += 1) {
      const cell = document.createElement("div");
      const tile = tileByPosition.get(`${x},${y}`);
      const legalMove = legalMoves.get(`${x},${y}`);
      cell.className = `cell${legalMove ? " legal" : ""}${state.selectedMove && state.selectedMove.x === x && state.selectedMove.y === y ? " selected" : ""}`;
      cell.innerHTML = `<div class="coordinate">${x},${y}</div>`;

      if (tile) {
        const image = document.createElement("img");
        image.className = "tile";
        image.src = tile.tile.image_path;
        image.alt = tile.tile.name;
        image.style.transform = `rotate(${tile.rotation * 90}deg)`;
        cell.appendChild(image);
        if (tile.meeple) {
          const owner = game.players.find((player) => player.id === tile.meeple.player_id);
          if (owner) {
            const meeplePosition = getMeeplePosition(tile);
            const meeple = document.createElement("img");
            meeple.className = "meeple";
            meeple.src = tile.meeple.kind === "field" ? lyingMeeples[owner.color] : standingMeeples[owner.color];
            meeple.alt = `${owner.name} meeple`;
            meeple.style.left = `${meeplePosition.left}%`;
            meeple.style.top = `${meeplePosition.top}%`;
            cell.appendChild(meeple);
          }
        }
      } else if (legalMove) {
        cell.addEventListener("click", () => {
          state.selectedMove = legalMove;
          state.selectedFeatureId = "";
          updateSelectionBox();
          renderBoard(game);
        });
      }

      elements.board.appendChild(cell);
    }
  }
}

function renderLog(messages) {
  elements.messageLog.innerHTML = "";
  for (const message of messages.slice().reverse()) {
    const item = document.createElement("div");
    item.className = "log-entry";
    item.textContent = message;
    elements.messageLog.appendChild(item);
  }
}

function updateSelectionBox() {
  const game = state.lastGame;
  const canAct = game && game.current_turn && game.current_player_id === state.playerId;
  if (!canAct) {
    elements.selectionBox.innerHTML = `<p class="muted">Waiting for the active player.</p>`;
    elements.meepleSelect.innerHTML = `<option value="">No meeple</option>`;
    elements.meepleSelect.value = "";
    elements.submitMove.disabled = true;
    return;
  }

  if (!state.selectedMove) {
    elements.selectionBox.innerHTML = `<p class="muted">Rotation ${state.rotation * 90}°. Click a highlighted cell to select a placement.</p>`;
    elements.meepleSelect.innerHTML = `<option value="">No meeple</option>`;
    elements.meepleSelect.value = "";
    elements.submitMove.disabled = true;
    return;
  }

  elements.selectionBox.innerHTML = `
    <strong>Selected placement</strong>
    <p class="muted">x ${state.selectedMove.x}, y ${state.selectedMove.y}, rotation ${state.selectedMove.rotation * 90}°</p>
  `;
  elements.meepleSelect.innerHTML = "";
  for (const option of state.selectedMove.meeple_options) {
    const el = document.createElement("option");
    el.value = option.feature_id || "";
    el.textContent = option.label;
    elements.meepleSelect.appendChild(el);
  }
  const validFeatureIds = new Set(state.selectedMove.meeple_options.map((option) => option.feature_id || ""));
  if (!validFeatureIds.has(state.selectedFeatureId)) {
    state.selectedFeatureId = "";
  }
  elements.meepleSelect.value = state.selectedFeatureId;
  elements.submitMove.disabled = false;
}

async function submitMove() {
  if (!state.lastGame || !state.lastGame.current_turn || !state.selectedMove) {
    return;
  }
  const featureId = elements.meepleSelect.value || null;
  const response = await fetchJson(`/moves/${state.gameId}/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      player_id: state.playerId,
      x: state.selectedMove.x,
      y: state.selectedMove.y,
      rotation: state.selectedMove.rotation,
      feature_id: featureId,
    }),
  });
  state.selectedMove = null;
  state.selectedFeatureId = "";
  state.rotation = 0;
  render(response.game);
}

function rotate(delta) {
  if (!state.lastGame || !state.lastGame.current_turn || state.lastGame.current_player_id !== state.playerId) {
    return;
  }
  state.rotation = (state.rotation + delta + 4) % 4;
  state.selectedMove = null;
  state.selectedFeatureId = "";
  render(state.lastGame);
}

function describeStatus(game) {
  if (game.status === "waiting") {
    return `Lobby ${game.game_id}: ${game.players.length}/${game.max_players} players joined. ${game.initial_meeples} meeples each.${game.use_void_cards ? " Void cards on." : ""}`;
  }
  if (game.status === "finished") {
    const names = game.players.filter((player) => game.winner_ids.includes(player.id)).map((player) => player.name);
    return `Game over. Winner${names.length > 1 ? "s" : ""}: ${names.join(", ") || "n/a"}.`;
  }
  const current = game.players.find((player) => player.id === game.current_player_id);
  return current ? `${current.name}${current.is_bot ? " (bot)" : ""} to play. ${game.initial_meeples} meeples each.${game.use_void_cards ? " Void cards on." : ""}` : "Game in progress.";
}

function formatBotPolicy(policy) {
  const match = state.botCatalog.find((bot) => bot.slug === policy);
  return match ? match.name : "Bot";
}

async function startGame() {
  if (!state.gameId || !state.playerId) {
    return;
  }
  const response = await fetchJson(`/games/${state.gameId}/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ player_id: state.playerId }),
  });
  render(response.game);
}

function copyLink() {
  if (!state.gameId) {
    return;
  }
  navigator.clipboard.writeText(window.location.href);
  setStatus("Game link copied to clipboard.");
}

function normalizedPlayerName() {
  const raw = elements.playerName.value.trim();
  return raw || "Player";
}

async function loadBotCatalog() {
  try {
    const response = await fetchJson("/games/bots");
    state.botCatalog = response.bots || [];
  } catch (error) {
    state.botCatalog = [];
  }
  renderBotControls();
}

function renderBotControls() {
  elements.botConfigList.innerHTML = "";
  if (state.botSelections.length === 0) {
    const hint = document.createElement("p");
    hint.className = "muted";
    hint.textContent = state.botCatalog.length === 0
      ? "No bots available in /bots."
      : "No bots inserted yet.";
    elements.botConfigList.appendChild(hint);
    return;
  }
  state.botSelections.forEach((slug, index) => {
    const row = document.createElement("div");
    row.className = "actions";

    const select = document.createElement("select");
    select.dataset.botIndex = String(index);
    for (const bot of state.botCatalog) {
      const option = document.createElement("option");
      option.value = bot.slug;
      option.textContent = bot.name;
      option.selected = bot.slug === slug;
      select.appendChild(option);
    }
    select.addEventListener("change", (event) => {
      state.botSelections[index] = event.target.value;
      renderBotControls();
    });

    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "secondary";
    removeButton.textContent = "Remove";
    removeButton.addEventListener("click", () => {
      state.botSelections.splice(index, 1);
      renderBotControls();
    });

    row.appendChild(select);
    row.appendChild(removeButton);
    elements.botConfigList.appendChild(row);

    const selectedBot = state.botCatalog.find((bot) => bot.slug === slug);
    if (selectedBot && selectedBot.description) {
      const hint = document.createElement("p");
      hint.className = "muted";
      hint.textContent = selectedBot.description;
      elements.botConfigList.appendChild(hint);
    }
  });
}

function insertBotSelection() {
  if (state.botCatalog.length === 0) {
    setStatus("No bots are available to insert.");
    return;
  }
  const hasHuman = elements.playerName.value.trim() !== "";
  const maxBots = hasHuman ? 4 : 5;
  if (state.botSelections.length >= maxBots) {
    setStatus("A game can include at most five total players.");
    return;
  }
  state.botSelections.push(state.botCatalog[0].slug);
  renderBotControls();
}

function currentBotCounts() {
  const counts = {};
  for (const slug of state.botSelections) {
    counts[slug] = (counts[slug] || 0) + 1;
  }
  return counts;
}

function updateUrl() {
  const url = new URL(window.location.href);
  if (state.gameId) {
    url.searchParams.set("game", state.gameId);
  }
  history.replaceState({}, "", url);
}

function setStatus(message) {
  elements.statusLine.textContent = message;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = "Request failed";
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch (error) {
      detail = `${detail} (${response.status})`;
    }
    setStatus(detail);
    throw new Error(detail);
  }
  return response.json();
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function getMeeplePosition(tile) {
  const defaultPosition = { left: 50, top: 50 };
  if (!tile.meeple) {
    return defaultPosition;
  }
  const feature = tile.tile.features.find((candidate) => candidate.id === tile.meeple.feature_id);
  if (!feature) {
    return defaultPosition;
  }
  const rotatedEdges = (feature.edges || []).map((edge) => rotatePort(edge, tile.rotation));
  const vectors = rotatedEdges
    .map((edge) => portVectors[edge])
    .filter(Boolean);

  if (feature.center) {
    return { left: 50, top: 50 };
  }

  if (vectors.length === 0) {
    return defaultPosition;
  }

  const [sumX, sumY] = vectors.reduce(
    (accumulator, [x, y]) => [accumulator[0] + x, accumulator[1] + y],
    [0, 0],
  );
  const magnitude = Math.hypot(sumX, sumY) || 1;
  const unitX = sumX / magnitude;
  const unitY = sumY / magnitude;

  let radius = 0.26;
  if (tile.meeple.kind === "city") {
    radius = rotatedEdges.length >= 2 ? 0.27 : 0.34;
  } else if (tile.meeple.kind === "road") {
    radius = rotatedEdges.length >= 2 ? 0.18 : 0.33;
  } else if (tile.meeple.kind === "field") {
    radius = 0.33;
  }

  const x = 50 + unitX * radius * 50;
  const y = 50 + unitY * radius * 50;
  return {
    left: clamp(x, 18, 82),
    top: clamp(y, 18, 82),
  };
}

function rotatePort(port, turns) {
  const order = ["Nw", "Ne", "En", "Es", "Se", "Sw", "Ws", "Wn"];
  const cardinal = ["N", "E", "S", "W"];
  if (cardinal.includes(port)) {
    return cardinal[(cardinal.indexOf(port) + turns) % cardinal.length];
  }
  if (!order.includes(port)) {
    return port;
  }
  return order[(order.indexOf(port) + turns * 2) % order.length];
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

init();
