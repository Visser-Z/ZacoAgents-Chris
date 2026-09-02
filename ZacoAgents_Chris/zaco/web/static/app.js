// Thin client over /api/*. Every action here is a JSON call to a documented endpoint, so
// nothing this interface does is unavailable to a React or Flutter frontend later (D1).
//
// Deliberately no CDN and no framework: the system has to run offline on `docker compose up`
// before it is hosted (D3), and a login page that needs the internet is not that.

async function api(method, url, body) {
  const response = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const detail = payload && payload.detail ? payload.detail : `Request failed (${response.status}).`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload;
}

function showError(element, message) {
  if (!element) return;
  element.textContent = message;
  element.hidden = !message;
}

function checkedValues(form, name) {
  return Array.from(form.querySelectorAll(`input[name="${name}"]:checked`)).map((i) => i.value);
}

// Wires a <form data-api="METHOD /path"> to the API. `transform` builds the JSON body.
function wireForm(form, transform, onSuccess) {
  const [method, url] = form.dataset.api.split(" ");
  const errorBox = form.querySelector("[data-error]");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    showError(errorBox, "");
    const button = form.querySelector("button[type=submit]");
    if (button) button.disabled = true;
    try {
      const result = await api(method, url, transform(form));
      onSuccess(result);
    } catch (error) {
      showError(errorBox, error.message);
    } finally {
      if (button) button.disabled = false;
    }
  });
}

function formObject(form) {
  const data = Object.fromEntries(new FormData(form).entries());
  delete data.permissions;
  return data;
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("form[data-api]").forEach((form) => {
    const wantsPermissions = form.querySelector('input[name="permissions"]') !== null;
    wireForm(
      form,
      (f) => {
        const body = formObject(f);
        if (wantsPermissions) body.permissions = checkedValues(f, "permissions");
        return body;
      },
      () => window.location.assign(form.dataset.then || window.location.pathname)
    );
  });

  document.querySelectorAll("[data-action]").forEach((element) => {
    element.addEventListener("click", async (event) => {
      event.preventDefault();
      const [method, url] = element.dataset.action.split(" ");
      const confirmText = element.dataset.confirm;
      if (confirmText && !window.confirm(confirmText)) return;
      let body;
      if (element.dataset.body) body = JSON.parse(element.dataset.body);
      try {
        await api(method, url, body);
        window.location.assign(element.dataset.then || window.location.pathname);
      } catch (error) {
        window.alert(error.message);
      }
    });
  });

  document.querySelectorAll("[data-copy]").forEach((element) => {
    element.addEventListener("click", async () => {
      await navigator.clipboard.writeText(element.dataset.copy);
      const original = element.textContent;
      element.textContent = "Copied";
      setTimeout(() => {
        element.textContent = original;
      }, 1200);
    });
  });
});
