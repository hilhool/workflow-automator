const toast = document.getElementById("toast");

function showToast(message, ms = 6000) {
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => { toast.hidden = true; }, ms);
}

async function post(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail?.message || payload.detail || `HTTP ${response.status}`);
  }
  return payload;
}

document.querySelectorAll("button.run").forEach((button) => {
  button.addEventListener("click", async () => {
    const name = button.dataset.workflow;
    button.disabled = true;
    button.textContent = "Выполняется…";
    try {
      const result = await post(`/api/workflows/${name}/run`);
      const head = result.status === "success" ? "Готово" : `Ошибка: ${result.error}`;
      showToast(`${head}\n\n${(result.text || "").slice(0, 600)}`, 12000);
    } catch (error) {
      showToast(`Не удалось запустить: ${error.message}`);
    } finally {
      button.disabled = false;
      button.textContent = "Запустить сейчас";
      setTimeout(() => window.location.reload(), 1500);
    }
  });
});

document.getElementById("reload").addEventListener("click", async () => {
  try {
    const result = await post("/api/reload");
    const broken = Object.keys(result.errors || {}).length;
    showToast(`Воркфлоу: ${result.workflows}, в расписании: ${result.scheduled}` +
      (broken ? `, с ошибками: ${broken}` : ""));
    setTimeout(() => window.location.reload(), 1200);
  } catch (error) {
    showToast(`Ошибка перезагрузки: ${error.message}`);
  }
});

document.querySelectorAll("button.done").forEach((button) => {
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await post(`/api/items/${button.dataset.item}/status`, { status: "done" });
      window.location.reload();
    } catch (error) {
      showToast(`Не удалось закрыть запись: ${error.message}`);
      button.disabled = false;
    }
  });
});
