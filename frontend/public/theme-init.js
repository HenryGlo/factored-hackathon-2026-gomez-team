// Aplica el tema guardado (o el del sistema) antes del primer pintado, para que la página no parpadee en claro.
// Archivo aparte, no en línea: la CSP solo permite scripts del mismo origen. La misma regla vive en src/lib/theme.ts.
(function () {
  var theme = null;
  try { theme = localStorage.getItem("theme"); } catch (e) { /* sin almacenamiento */ }
  if (theme !== "light" && theme !== "dark") {
    theme = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  document.documentElement.setAttribute("data-theme", theme);
})();
